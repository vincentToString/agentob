import asyncpg
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_db_pool = None


async def get_db_pool():
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "agentob_user"),
            password=os.getenv("POSTGRES_PASSWORD", "agentob_password"),
            database=os.getenv("POSTGRES_DB", "agentob_db"),
            min_size=2,
            max_size=10,
        )
    return _db_pool

async def get_baseline(project_id: str, agent_name: str) -> Optional[dict]:
    """Fetch baseline statistics for an agent"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT avg_cost_usd, p50_duration_ms, p95_duration_ms, 
                   p99_duration_ms, avg_spans, sample_size
            FROM agent_baselines
            WHERE project_id = $1 AND agent_name = $2
            """,
            project_id,
            agent_name,
        )
        if row:
            return dict(row)
        return None
    
async def update_baseline(
    project_id: str,
    agent_name: str,
    cost: float,
    duration: int,
    span_count: int,
):
    """
    Update baseline with new run data.
    Uses exponential moving average for means, sliding window for percentiles.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Get current baseline
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
                # Exponential moving average for cost and span count (simple metrics)
                alpha = 0.1
                new_avg_cost = baseline["avg_cost_usd"] * (1 - alpha) + cost * alpha
                new_avg_spans = int(baseline["avg_spans"] * (1 - alpha) + span_count * alpha)
                
                # For percentiles: fetch last 100 runs and recompute from scratch
                # This is simple and fast enough for demo scale
                durations = await conn.fetch(
                    """
                    SELECT duration_ms FROM agent_runs
                    WHERE project_id = $1 AND agent_name = $2 
                    AND duration_ms IS NOT NULL
                    ORDER BY started_at DESC
                    LIMIT 100
                    """,
                    project_id,
                    agent_name,
                )

                def percentile(arr, p):
                    if not arr:
                        return None
                    k = int((len(arr) - 1) * p)
                    return arr[k]
                
                if durations:
                    # Convert to sorted list
                    duration_values = sorted([r["duration_ms"] for r in durations] + [duration])
                    n = len(duration_values)
                    
                    # Compute percentiles using nearest-rank method
                    new_p50 = percentile(duration_values, 0.50)
                    new_p95 = percentile(duration_values, 0.95)
                    new_p99 = percentile(duration_values, 0.99)
                else:
                    # Fallback if no historical data
                    new_p50 = duration
                    new_p95 = duration
                    new_p99 = duration
                
                sample_size = baseline["sample_size"] + 1
                
                await conn.execute(
                    """
                    UPDATE agent_baselines
                    SET avg_cost_usd = $3, p50_duration_ms = $4, 
                        p95_duration_ms = $5, p99_duration_ms = $6,
                        avg_spans = $7, sample_size = $8, last_updated = NOW()
                    WHERE project_id = $1 AND agent_name = $2
                    """,
                    project_id, agent_name, new_avg_cost, new_p50, 
                    new_p95, new_p99, new_avg_spans, sample_size,
                )
                logger.info(
                    f"Updated baseline for {agent_name}: "
                    f"sample_size={sample_size}, p95={new_p95}ms"
                )
            else:
                # First run - create baseline
                await conn.execute(
                    """
                    INSERT INTO agent_baselines 
                    (project_id, agent_name, avg_cost_usd, p50_duration_ms, 
                     p95_duration_ms, p99_duration_ms, avg_spans, sample_size)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 1)
                    """,
                    project_id, agent_name, cost, duration, 
                    duration, duration, span_count,
                )
                logger.info(f"Created baseline for {agent_name}")

async def store_trace_to_db(
    *,
    trace_data: dict,
    spans: list[dict],
    depth_map: dict,
    span_tree: list[dict],
    total_cost: float,
    total_tokens_in: int,
    total_tokens_out: int,
    total_duration: int,
    anomalies: list,
    llm_summary: str,
    baseline_deviation_score: float,
):
    """Store complete trace analysis to database"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Insert agent_run
            await conn.execute(
                """
                INSERT INTO agent_runs 
                (run_id, project_id, agent_name, agent_framework, model_id,
                 status, input_text, output_text,
                 total_tokens_input, total_tokens_output, total_cost_usd,
                 total_spans, anomaly_count, duration_ms, llm_summary, span_tree,
                 baseline_deviation_score,
                 started_at, completed_at, metadata, tags)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::jsonb,$17,$18::timestamp,$19::timestamp,$20::jsonb,$21)
                ON CONFLICT (run_id) DO UPDATE SET
                    llm_summary = EXCLUDED.llm_summary,
                    span_tree = EXCLUDED.span_tree,
                    anomaly_count = EXCLUDED.anomaly_count,
                    baseline_deviation_score = EXCLUDED.baseline_deviation_score
                """,
                trace_data["run_id"],
                trace_data.get("project_id", "default"),
                trace_data["agent_name"],
                trace_data.get("agent_framework"),
                trace_data.get("model_id"),
                trace_data.get("status", "completed"),
                trace_data.get("input_text"),
                trace_data.get("output_text"),
                total_tokens_in,
                total_tokens_out,
                total_cost,
                len(spans),
                len(anomalies),
                total_duration,
                llm_summary,
                json.dumps(span_tree),
                baseline_deviation_score,
                trace_data.get("started_at"),
                trace_data.get("completed_at"),
                json.dumps(trace_data.get("metadata", {})),
                trace_data.get("tags", []),
            )

            # Insert spans
            for span in spans:
                await conn.execute(
                    """
                    INSERT INTO spans
                    (span_id, run_id, parent_span_id, span_type, name,
                     input_data, output_data, model_id,
                     tokens_input, tokens_output, cost_usd,
                     tool_name, tool_status,
                     started_at, completed_at, duration_ms,
                     sequence_index, depth, is_anomalous, anomaly_type,
                     anomaly_description, metadata)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10,$11,$12,$13,
                            $14::timestamp,$15::timestamp,$16,$17,$18,$19,$20,$21,$22::jsonb)
                    ON CONFLICT (span_id) DO NOTHING
                    """,
                    span["span_id"],
                    trace_data["run_id"],
                    span.get("parent_span_id"),
                    span["span_type"],
                    span["name"],
                    json.dumps(span.get("input_data")),
                    json.dumps(span.get("output_data")),
                    span.get("model_id"),
                    span.get("tokens_input"),
                    span.get("tokens_output"),
                    span.get("cost_usd"),
                    span.get("tool_name"),
                    span.get("tool_status"),
                    span.get("started_at"),
                    span.get("completed_at"),
                    span.get("duration_ms"),
                    span.get("sequence_index", 0),
                    depth_map.get(span["span_id"], 0),
                    span.get("is_anomalous", False),
                    span.get("anomaly_type"),
                    span.get("anomaly_description"),
                    json.dumps(span.get("metadata", {})),
                )

            # Insert alerts for anomalies
            for anomaly in anomalies:
                alert_id = os.urandom(8).hex()
                await conn.execute(
                    """
                    INSERT INTO alerts (alert_id, run_id, span_id, alert_type, severity, title, description)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    alert_id,
                    trace_data["run_id"],
                    anomaly.span_id,
                    anomaly.anomaly_type,
                    anomaly.severity,
                    anomaly.title,
                    anomaly.description,
                )
            
            logger.info(
                f"Stored trace {trace_data['run_id']}: "
                f"{len(spans)} spans, {len(anomalies)} anomalies"
            )