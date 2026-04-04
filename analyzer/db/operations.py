"""Database operations for analyzer worker"""
import asyncpg
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Global connection pool
_db_pool: asyncpg.Pool | None = None

async def get_db_pool():
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        from analyzer.config import Config
        _db_pool = await asyncpg.create_pool(
            host=Config.POSTGRES_HOST,
            port=Config.POSTGRES_PORT,
            user=Config.POSTGRES_USER,
            password=Config.POSTGRES_PASSWORD,
            database=Config.POSTGRES_DB,
            min_size=2,
            max_size=10,
        )
        logger.info(f"[OK] Database pool created")
    return _db_pool  

async def close_db_pool():
    """Close database connection pool"""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None
        logger.info("[OK] Database pool closed")


def parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 timestamp (including trailing Z) into timezone-naive datetime."""
    if not ts_str:
        return None
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts_str)
        # Remove timezone info to make it naive (PostgreSQL TIMESTAMP without timezone)
        return dt.replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")
        return None

# ========== INSERT SPAN ==========
async def insert_span(span: dict) -> bool:
    """
    Insert span into spans table.
    Returns True if inserted, False if duplicate.
    """
    pool = await get_db_pool()
    
    # Convert timestamps from ISO8601 to datetime
    started_at = parse_timestamp(span.get("started_at"))
    completed_at = parse_timestamp(span.get("completed_at"))
    if started_at is None:
        raise ValueError(f"Invalid or missing started_at for span {span.get('span_id')}")
    if completed_at is None:
        raise ValueError(f"Invalid or missing completed_at for span {span.get('span_id')}")
    
    # Prepare JSONB fields
    input_data_json = json.dumps(span.get('input_data')) if span.get('input_data') else None
    output_data_json = json.dumps(span.get('output_data')) if span.get('output_data') else None
    metadata_json = json.dumps(span.get('metadata', {}))
    
    query = """
        INSERT INTO spans (
            span_id, run_id, parent_span_id, span_type, name,
            input_data, output_data, model_id, tokens_input, tokens_output,
            cost_usd, tool_name, tool_status, started_at, completed_at,
            duration_ms, is_final, sequence_index, depth, is_anomalous,
            anomaly_type, anomaly_description, metadata
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20,
            $21, $22, $23
        )
        ON CONFLICT (span_id) DO NOTHING
    """
    
    try:
        result = await pool.execute(
            query,
            span['span_id'],
            span['run_id'],
            span.get('parent_span_id'),
            span['span_type'],
            span['name'],
            input_data_json,
            output_data_json,
            span.get('model_id'),
            span.get('tokens_input'),
            span.get('tokens_output'),
            span.get('cost_usd'),
            span.get('tool_name'),
            span.get('tool_status'),
            started_at,
            completed_at,
            span.get('duration_ms'),
            span.get('is_final', False),
            span.get('sequence_index', 0),
            span.get('depth', 0),
            span.get('is_anomalous', False),
            span.get('anomaly_type'),
            span.get('anomaly_description'),
            metadata_json
        )
        
        # Check if row was inserted (vs duplicate skipped)
        inserted = "INSERT 0 1" in result
        if inserted:
            logger.debug(f"✓ Inserted span {span['span_id']}")
        else:
            logger.debug(f"⊗ Duplicate span {span['span_id']} skipped")
        
        return inserted
    
    except Exception as e:
        logger.error(f"Failed to insert span {span['span_id']}: {e}")
        raise


# ========== UPSERT RUN ==========
async def upsert_run(run_id: str, span: dict):
    """
    Insert new run or update existing run with incremental aggregates.
    """
    pool = await get_db_pool()
    
    # Parse started_at and completed_at
    started_at = parse_timestamp(span.get("started_at"))
    last_span_at = parse_timestamp(span.get("completed_at"))
    if started_at is None:
        raise ValueError(f"Invalid or missing started_at for run {run_id}")
    if last_span_at is None:
        raise ValueError(f"Invalid or missing completed_at for run {run_id}")
    
    # Extract values for INSERT
    project_id = span['project_id']
    agent_name = span['agent_name']
    cost_usd = span.get('cost_usd', 0) or 0
    tokens_input = span.get('tokens_input', 0) or 0
    tokens_output = span.get('tokens_output', 0) or 0
    model_id = span.get('model_id')
    
    query = """
        INSERT INTO agent_runs (
            run_id, project_id, agent_name, status, started_at,
            total_spans, total_cost_usd, total_tokens_input, total_tokens_output,
            last_span_at, model_id
        ) VALUES (
            $1, $2, $3, 'active', $4,
            1, $5, $6, $7,
            $8, $9
        )
        ON CONFLICT (run_id) DO UPDATE SET
            total_spans = agent_runs.total_spans + 1,
            total_cost_usd = agent_runs.total_cost_usd + EXCLUDED.total_cost_usd,
            total_tokens_input = agent_runs.total_tokens_input + EXCLUDED.total_tokens_input,
            total_tokens_output = agent_runs.total_tokens_output + EXCLUDED.total_tokens_output,
            last_span_at = EXCLUDED.last_span_at,
            model_id = COALESCE(agent_runs.model_id, EXCLUDED.model_id),
            status = 'active'
    """
    
    try:
        await pool.execute(
            query,
            run_id,
            project_id,
            agent_name,
            started_at,
            cost_usd,
            tokens_input,
            tokens_output,
            last_span_at,
            model_id
        )
        logger.debug(f"✓ Upserted run {run_id}")
    
    except Exception as e:
        logger.error(f"Failed to upsert run {run_id}: {e}")
        raise


# ========== GET RUN SPANS ==========
def _convert_to_json_serializable(obj):
    """Convert database types to JSON-serializable types"""
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_json_serializable(item) for item in obj]
    else:
        return obj


async def get_run_spans(run_id: str) -> list[dict]:
    """
    Fetch all spans for a run, ordered by started_at.
    """
    pool = await get_db_pool()

    query = "SELECT * FROM spans WHERE run_id = $1 ORDER BY started_at"

    try:
        rows = await pool.fetch(query, run_id)
        # Convert rows to dicts and handle type conversions for JSON
        spans = [_convert_to_json_serializable(dict(row)) for row in rows]
        logger.debug(f"✓ Fetched {len(spans)} spans for run {run_id}")
        return spans

    except Exception as e:
        logger.error(f"Failed to fetch spans for run {run_id}: {e}")
        return []


# ========== FINALIZE RUN ==========
async def finalize_run(
    run_id: str,
    span_tree: list,
    total_cost: float,
    total_duration_ms: int,
    anomaly_count: int
):
    """
    Mark run as complete and store final tree.
    """
    pool = await get_db_pool()
    
    # Convert span_tree to JSON string for JSONB column
    span_tree_json = json.dumps(span_tree)
    
    query = """
        UPDATE agent_runs SET
            status = 'completed',
            span_tree = $1,
            duration_ms = $2,
            total_cost_usd = $3,
            anomaly_count = $4,
            completed_at = NOW()
        WHERE run_id = $5
    """
    
    try:
        await pool.execute(
            query,
            span_tree_json,
            total_duration_ms,
            total_cost,
            anomaly_count,
            run_id
        )
        logger.info(f"✓ Finalized run {run_id} (duration: {total_duration_ms}ms, cost: ${total_cost:.4f})")
    
    except Exception as e:
        logger.error(f"Failed to finalize run {run_id}: {e}")
        raise


# ========== UPDATE BASELINE ==========
async def update_baseline(
    project_id: str,
    agent_name: str,
    cost: float,
    duration_ms: int,
    span_count: int
):
    """
    Update baseline with new run data.
    Uses exponential moving average for means, sliding window for percentiles.
    """
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                baseline = await conn.fetchrow(
                    """
                    SELECT avg_cost_usd, p50_duration_ms, p95_duration_ms,
                           p99_duration_ms, avg_spans, sample_size
                    FROM agent_baselines
                    WHERE project_id = $1 AND agent_name = $2
                    FOR UPDATE
                    """,
                    project_id,
                    agent_name,
                )

                if baseline and baseline["sample_size"] > 0:
                    alpha = 0.1
                    new_avg_cost = float(baseline["avg_cost_usd"]) * (1 - alpha) + float(cost) * alpha
                    new_avg_spans = int(float(baseline["avg_spans"]) * (1 - alpha) + float(span_count) * alpha)

                    # Use last 99 completed runs + current run to form a 100-point window.
                    duration_rows = await conn.fetch(
                        """
                        SELECT duration_ms
                        FROM agent_runs
                        WHERE project_id = $1
                          AND agent_name = $2
                          AND duration_ms IS NOT NULL
                          AND status = 'completed'
                        ORDER BY started_at DESC
                        LIMIT 99
                        """,
                        project_id,
                        agent_name,
                    )

                    duration_values = sorted([r["duration_ms"] for r in duration_rows] + [duration_ms])

                    def percentile(values: list[int], p: float) -> int:
                        idx = int((len(values) - 1) * p)
                        return values[idx]

                    new_p50 = percentile(duration_values, 0.50)
                    new_p95 = percentile(duration_values, 0.95)
                    new_p99 = percentile(duration_values, 0.99)
                    sample_size = baseline["sample_size"] + 1

                    await conn.execute(
                        """
                        UPDATE agent_baselines
                        SET avg_cost_usd = $3,
                            p50_duration_ms = $4,
                            p95_duration_ms = $5,
                            p99_duration_ms = $6,
                            avg_spans = $7,
                            sample_size = $8,
                            last_updated = NOW()
                        WHERE project_id = $1 AND agent_name = $2
                        """,
                        project_id,
                        agent_name,
                        new_avg_cost,
                        new_p50,
                        new_p95,
                        new_p99,
                        new_avg_spans,
                        sample_size,
                    )
                    logger.info(
                        f"Updated baseline for {project_id}/{agent_name}: "
                        f"sample_size={sample_size}, p95={new_p95}ms"
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO agent_baselines
                        (project_id, agent_name, avg_cost_usd, p50_duration_ms,
                         p95_duration_ms, p99_duration_ms, avg_spans, sample_size)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 1)
                        """,
                        project_id,
                        agent_name,
                        cost,
                        duration_ms,
                        duration_ms,
                        duration_ms,
                        span_count,
                    )
                    logger.info(f"Created baseline for {project_id}/{agent_name}")
    except Exception as e:
        logger.error(f"Failed to update baseline for {project_id}/{agent_name}: {e}")
        # Don't raise - baseline update failure shouldn't block span processing