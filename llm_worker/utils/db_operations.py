import asyncpg
import logging
from typing import Optional
from llm_worker.config import Config
from decimal import Decimal

logger = logging.getLogger(__name__)

# Global connection pool
_db_pool: asyncpg.Pool | None = None

async def get_db_pool():
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            host=Config.POSTGRES_HOST,
            port=Config.POSTGRES_PORT,
            user=Config.POSTGRES_USER,
            password=Config.POSTGRES_PASSWORD,
            database=Config.POSTGRES_DB,
            min_size=1,
            max_size=5,
        )
        logger.info("[OK] Database pool created")
    return _db_pool

async def close_db_pool():
    """Close database connection pool"""
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None
        logger.info("[OK] Database pool closed")

async def fetch_run_data(run_id: str) -> Optional[dict]:
    """
    Fetch run metadata + spans + alerts for summary generation.
    Returns None if run not found.
    """
    pool = await get_db_pool()
    
    # Fetch run metadata
    run_row = await pool.fetchrow(
        """
        SELECT run_id, project_id, agent_name, status,
               total_spans, total_cost_usd, total_tokens_input, total_tokens_output,
               duration_ms, anomaly_count, started_at, completed_at
        FROM agent_runs
        WHERE run_id = $1
        """,
        run_id
    )
    
    if not run_row:
        logger.warning(f"Run {run_id} not found in database")
        return None
    
    run_data = dict(run_row)
    
    # Convert Decimal to float
    if run_data.get("total_cost_usd"):
        run_data["total_cost_usd"] = float(run_data["total_cost_usd"])
    
    # Fetch spans (just high-level info, not full input/output)
    span_rows = await pool.fetch(
        """
        SELECT span_id, span_type, name, duration_ms, cost_usd,
               is_anomalous, anomaly_type, anomaly_description
        FROM spans
        WHERE run_id = $1
        ORDER BY started_at
        LIMIT 50
        """,
        run_id
    )
    
    spans = []
    for row in span_rows:
        span_dict = dict(row)
        if span_dict.get("cost_usd"):
            span_dict["cost_usd"] = float(span_dict["cost_usd"])
        spans.append(span_dict)
    
    # Fetch alerts
    alert_rows = await pool.fetch(
        """
        SELECT alert_type, severity, title, description
        FROM alerts
        WHERE run_id = $1
        ORDER BY created_at
        LIMIT 10
        """,
        run_id
    )
    
    alerts = [dict(row) for row in alert_rows]
    
    return {
        "run": run_data,
        "spans": spans,
        "alerts": alerts
    }

async def update_run_summary(run_id: str, summary: str):
    """Update agent_runs.llm_summary field"""
    pool = await get_db_pool()
    
    result = await pool.execute(
        """
        UPDATE agent_runs
        SET llm_summary = $2
        WHERE run_id = $1
        """,
        run_id,
        summary
    )
    
    if "UPDATE 1" in result:
        logger.info(f"✓ Updated summary for run {run_id}")
        return True
    else:
        logger.warning(f"Failed to update summary for run {run_id}")
        return False