from fastapi import APIRouter, Request, HTTPException
from aio_pika import Message, DeliveryMode
import json
import uuid
import logging
from .redis_client import RedisClient
from .config import Config
from .trace_models import AgentTrace

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

    # Store full trace in Redis for worker to fetch (same pattern as PR diff storage)
    trace_data = trace.model_dump()
    trace_data["trace_id"] = trace_id

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