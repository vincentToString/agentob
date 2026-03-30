from fastapi import APIRouter, Request, HTTPException
from aio_pika import Message, DeliveryMode
import json
import uuid
import logging
from .redis_client import RedisClient
from .config import Config
from .trace_models import AgentTrace
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()
redis_client = RedisClient(Config.REDIS_URL)

@router.post("/v1/traces")
async def ingest_trace(request: Request, trace: AgentTrace):
    """
    Accept a complete agent trace.
    Flow: validate -> (compress TODO) -> publish to RabbitMQ -> store in Redis -> worker picks up
    """
    trace_id = trace.run_id or str(uuid.uuid4())

    # Populate run_id for each span
    for span in trace.spans:
        if not span.run_id:
            span.run_id = trace_id

    # Store full trace in Redis for worker to fetch (same pattern as PR diff storage)
    trace_data = trace.model_dump()
    trace_data["trace_id"] = trace_id

    if trace.started_at and trace.completed_at:
        try:
            start = parse_timestamp(trace.started_at)
            end = parse_timestamp(trace.completed_at)
            if start and end:
                trace_data["duration_ms"] = int((end - start).total_seconds() * 1000)
        except Exception as e:
            logger.warning(f"Failed to calculate duration for trace {trace_id}: {e}")

    success = await redis_client.store_trace(
        trace_id, json.dumps(trace_data), ttl=Config.TRACE_TTL
    )
    if not success:
        raise HTTPException(status_code=503, detail="Failed to store trace data")

    # Publish trace_id to RabbitMQ 
    channel = await request.app.state.rabbitmq_connection.channel()
    try:
        exchange = await channel.get_exchange("analyzer_exchange")
        msg = Message(
            body=json.dumps({"trace_id": trace_id}).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={
                "agent": trace.agent_name,
                "project": trace.project_id or "default"
            },
        )
        await exchange.publish(msg, routing_key="trace")
        logger.info(
            f"Published trace {trace_id} for agent '{trace.agent_name}' "
            f"({len(trace.spans)} spans)"
        )
    except Exception as e:
        logger.error(f"Failed to publish to RabbitMQ: {e}")
        raise HTTPException(status_code=503, detail="Queue unavailable")
    finally:
        await channel.close()

    return {
        "status": "accepted",
        "trace_id": trace_id,
        "spans_received": len(trace.spans),
    }


@router.get("/v1/traces/health")
async def trace_health():
    return {"status": "collector_ready"}


def parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to timezone-naive datetime for PostgreSQL"""
    if not ts_str:
        return None
    try:
        # Parse and remove timezone info (PostgreSQL TIMESTAMP doesn't store timezone)
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(ts_str)
        # Remove timezone info to make it naive
        return dt.replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")
        return None