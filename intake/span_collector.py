from fastapi import APIRouter, Request, HTTPException
from aio_pika import Message, DeliveryMode
import json
import logging
from .span_models import SpanEvent
from .redis_client import RedisClient
from .config import Config
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()
redis_client = RedisClient(Config.REDIS_URL)

# Valid span types for validation
VALID_SPAN_TYPES = {"llm_call", "tool_use", "decision", "retrieval", "error", "custom"}


@router.post("/v1/spans")
async def ingest_span(request: Request, span: SpanEvent):
    """
    Accept a single agent execution span (streaming ingestion).

    Flow:
    1. Validate required fields (Pydantic auto-validates)
    2. Compute duration if missing
    3. Publish to RabbitMQ span_intake queue
    4. Return 202 Accepted immediately (async processing)
    """

    # Validate span_type
    if span.span_type not in VALID_SPAN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid span_type '{span.span_type}'. Must be one of: {', '.join(VALID_SPAN_TYPES)}"
        )

    # Parse and validate timestamps
    try:
        started = parse_timestamp(span.started_at)
        completed = parse_timestamp(span.completed_at)

        if not started or not completed:
            raise ValueError("Invalid timestamp format")

        # Compute duration if not provided
        if span.duration_ms is None:
            duration = (completed - started).total_seconds() * 1000
            span.duration_ms = int(duration)

        # Validate duration is positive
        if span.duration_ms < 0:
            raise ValueError("completed_at must be after started_at")

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timestamps: {str(e)}. Use ISO8601 format (e.g., '2024-03-30T10:00:00Z')"
        )

    # Log span ingestion
    logger.info(
        f"Received span {span.span_id} for run {span.run_id} "
        f"(agent: {span.agent_name}, project: {span.project_id}, "
        f"type: {span.span_type}, duration: {span.duration_ms}ms)"
    )

    # Check if this is the final span
    if span.is_final:
        logger.info(f"🏁 Final span received for run {span.run_id}")

    # Serialize span to JSON
    span_data = span.model_dump()

    # ========== HYBRID STRATEGY: Offload large fields to Redis ==========
    # Check if combined input_data + output_data exceeds threshold

    # Calculate combined size of input and output data
    input_size = len(json.dumps(span_data.get("input_data", {})))
    output_size = len(json.dumps(span_data.get("output_data", {})))
    combined_size = input_size + output_size

    # If combined size exceeds threshold, store both in Redis as one object
    if combined_size > Config.LARGE_FIELD_THRESHOLD:
        redis_key = f"span_data:{span.span_id}:io_data"

        # Store both input and output in a single Redis entry
        large_data = {}
        if span_data.get("input_data"):
            large_data["input_data"] = span_data["input_data"]
        if span_data.get("output_data"):
            large_data["output_data"] = span_data["output_data"]

        success = await redis_client.store_span_data(
            redis_key,
            large_data,
            ttl=Config.TRACE_TTL
        )

        if success:
            # Store Redis key directly (not as dict since we only have one key)
            span_data["_redis_ref"] = redis_key
            # Remove large fields from queue message
            span_data["input_data"] = None
            span_data["output_data"] = None
            logger.info(
                f"Stored large I/O data in Redis ({combined_size} bytes: "
                f"input={input_size}, output={output_size}) for span {span.span_id}"
            )

    # Publish to RabbitMQ span_intake queue
    channel = await request.app.state.rabbitmq_connection.channel()
    try:
        exchange = await channel.get_exchange("span_intake_exchange")

        msg = Message(
            body=json.dumps(span_data).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={
                "run_id": span.run_id,
                "agent": span.agent_name,
                "project": span.project_id,
                "span_type": span.span_type,
                "is_final": span.is_final,
            },
        )

        await exchange.publish(msg, routing_key="span")

        logger.info(
            f"✓ Published span {span.span_id} to span_intake queue "
            f"(type: {span.span_type}, final: {span.is_final})"
        )

    except Exception as e:
        logger.error(f"Failed to publish span to RabbitMQ: {e}")
        raise HTTPException(status_code=503, detail="Queue unavailable")
    finally:
        await channel.close()

    # Return immediately (don't wait for processing)
    return {
        "status": "accepted",
        "span_id": span.span_id,
        "run_id": span.run_id,
        "duration_ms": span.duration_ms,
        "message": "Span queued for processing"
    }


@router.get("/v1/spans/health")
async def span_health():
    """Health check for span ingestion endpoint"""
    return {
        "status": "ready",
        "endpoint": "/v1/spans",
        "valid_span_types": list(VALID_SPAN_TYPES)
    }


@router.post("/v1/traces")
async def ingest_trace_deprecated():
    """DEPRECATED: Batch trace upload no longer supported"""
    raise HTTPException(
        status_code=410,
        detail=(
            "Batch trace upload is deprecated. "
            "Use POST /v1/spans for streaming ingestion. "
            "Send individual spans as they complete."
        )
    )


def parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to timezone-naive datetime"""
    if not ts_str:
        return None
    try:
        # Handle Z suffix (UTC indicator)
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1] + '+00:00'

        dt = datetime.fromisoformat(ts_str)

        # Remove timezone info to make it naive (for PostgreSQL TIMESTAMP)
        return dt.replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")
        return None
