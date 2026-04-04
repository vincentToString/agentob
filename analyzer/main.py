import asyncio
from aio_pika.abc import AbstractIncomingMessage
import aio_pika
from aio_pika import Message, DeliveryMode
import os
import json
import logging
import signal
from .utils.redis_client import RedisClient
from .config import Config
from .health.heartbeat import WorkerHealthState, heartbeat_loop
import socket
from .models.span_models import SpanEvent

from .db.operations import (
    insert_span,
    upsert_run,
    get_run_spans,
    finalize_run as db_finalize_run,
    update_baseline,
    close_db_pool
)
from .utils.span_analyzer import (
    detect_span_anomalies,
)
from .utils.tree_builder import (
    build_span_tree,
    compute_depth_map
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

redis_client = RedisClient(Config.REDIS_URL)

# ========== WEBSOCKET PUBLISHER (for real-time dashboard updates) ==========
async def publish_to_websocket(channel, event: dict):
    """
    Publish event to websocket_events exchange for frontend.
    
    Event has parameter: types:
    - span_received: Individual span arrived
    - run_completed: Run finalized with tree
    - anomaly_detected: Anomaly found (optional)
    """
    try: 
        exchange = await channel.get_exchange("websocket_events")
        msg = Message(
            body=json.dumps(event).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={
                "event_type": event.get("type"), 
                "run_id": event.get("run_id"),
                # Optional: Add span_type if it's a span_received event
                "span_type": event.get("span", {}).get("span_type") if event.get("type") == "span_received" else None
            }
        )
        await exchange.publish(msg, routing_key="") # fanout no routing key needed for fanout exchange
        logger.info(f"Published event to websocket: {event.get('span_id')}")
    except Exception as e:
        logger.error(f"Failed to publish websocket event: {e}")


#  ========== RUN FINALIZATION ==========
async def finalize_run(run_id: str, channel):
    """
    Called when is_final=true received.
    
    Steps:
    1. Fetch all spans from PostgreSQL
    2. Build span tree
    3. Calculate final metrics
    4. Update database with tree and status='completed'
    5. Update baseline
    6. Publish WebSocket "run_completed" event
    7. Publish to llm_summary queue (for LLM worker)
    """
    try: 
        logger.info(f"🏁 Finalizing run {run_id}...")

        # 1. Fetch all spans for this run
        spans = await get_run_spans(run_id)
        if not spans:
            logger.warning(f"No spans found for run {run_id}")
            return
        
        # 2. Build full span tree
        span_tree = build_span_tree(spans)

        # 3. Calculate final metrics
        total_cost = sum((s.get("cost_usd") or 0) for s in spans)
        
        # Calculate total duration (max completed_at - min started_at)
        from datetime import datetime
        timestamps = [
            datetime.fromisoformat(str(s["started_at"]).replace("Z", "+00:00"))
            for s in spans if s.get("started_at")
        ]
        completed_timestamps = [
            datetime.fromisoformat(str(s["completed_at"]).replace("Z", "+00:00"))
            for s in spans if s.get("completed_at")
        ]
        
        if timestamps and completed_timestamps:
            total_duration_ms = int((max(completed_timestamps) - min(timestamps)).total_seconds() * 1000)
        else:
            total_duration_ms = 0

        # Count anomalies:
        anomaly_count = sum(1 for s in spans if s.get("is_anommalous", False))

        # 4. Update database
        await db_finalize_run(
            run_id=run_id, 
            span_tree=span_tree, 
            total_cost=total_cost,
            total_duration_ms=total_duration_ms, 
            anomaly_count=anomaly_count)
        
        # 5. Update baseline:
        if spans:
            project_id = spans[0].get("project_id")
            agent_name = spans[0].get("agent_name")
            if project_id and agent_name:
                await update_baseline(
                    project_id=project_id,
                    agent_name=agent_name,
                    cost=total_cost,
                    duration_ms=total_duration_ms,
                    span_count=len(spans)
                )

        # 6. Publish WebSocket event
        await publish_to_websocket(channel, {
            "type": "run_completed",
            "run_id": run_id,
            "span_tree": span_tree,
            "metrics": {
                "total_spans": len(spans),
                "total_cost": float(total_cost),
                "total_duration_ms": total_duration_ms,
                "anomaly_count": anomaly_count
            }
        })
        # 7. Publish to llm_summary queue (for LLM worker to generate summary)
        try:
            llm_exchange = await channel.get_exchange("llm_summary_exchange")
            llm_msg = Message(
                body=json.dumps({"run_id": run_id}).encode("utf-8"),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json"
            )
            await llm_exchange.publish(llm_msg, routing_key="trace")
            logger.info(f"[OK] Published to llm_summary queue for run {run_id}")
        except Exception as e:
            logger.warning(f"Failed to publish to llm_summary queue: {e}")
            # Don't fail - LLM summary is optional
        
        logger.info(f"✅ Finalized run {run_id}: {len(spans)} spans, ${total_cost:.4f}, {total_duration_ms}ms")
    
    except Exception as e:
        logger.error(f"Failed to finalize run {run_id}: {e}", exc_info=True)
        raise

# ========== Token Cost Estimator ==========
def estimate_cost(model_id: str, tokens_input: int, tokens_output: int) -> float:
    """
    Estimate cost based on model pricing.
    
    Pricing per 1M tokens (as of 2024):
    https://openai.com/pricing
    """
    # Pricing table (input/output per 1M tokens)
    pricing = {
        # OpenAI
        "gpt-4": (0.03, 0.06),
        "gpt-4-turbo": (0.01, 0.03),
        "gpt-4o": (0.005, 0.015),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-3.5-turbo": (0.0005, 0.0015),
        
        # Anthropic Claude
        "claude-3-opus": (0.015, 0.075),
        "claude-3-sonnet": (0.003, 0.015),
        "claude-3-haiku": (0.00025, 0.00125),
        "claude-3.5-sonnet": (0.003, 0.015),
        
        # Meta Llama
        "llama-3-8b": (0.0001, 0.0001),
        "llama-3-70b": (0.0006, 0.0006),
        
        # Mistral
        "mistral-7b": (0.0001, 0.0001),
        "mixtral-8x7b": (0.0005, 0.0005),
    }
    
    # Normalize model_id (remove provider prefix)
    if model_id:
        model_key = model_id.lower()
        for key in pricing.keys():
            if key in model_key:
                input_price, output_price = pricing[key]
                cost = (tokens_input / 1_000_000 * input_price) + (tokens_output / 1_000_000 * output_price)
                return round(cost, 8)
    
    # Default pricing if model not found (assume GPT-4o-mini rates)
    logger.debug(f"Unknown model '{model_id}', using default pricing")
    input_price, output_price = 0.00015, 0.0006
    cost = (tokens_input / 1_000_000 * input_price) + (tokens_output / 1_000_000 * output_price)
    return round(cost, 8)

# ========== Handle incoming span ==========
async def handle_message(message: AbstractIncomingMessage, channel):
    """Handle Incoming Span from RabbitMQ"""
    async with message.process(requeue=False):
        span_event = json.loads(message.body.decode("utf-8"))


        span_id = span_event.get("span_id")
        run_id = span_event.get("run_id")

        if not span_id:
            logger.error("No span_id in message")
            return
        if not run_id:
            logger.error("No run_id in message")
            return
        
        # if input/output data too huge, there will be a _redis_ref
        redis_key = span_event.get("_redis_ref")
        if redis_key:
            logger.info(f"Retrieving large data for span - f{span_id}")
            span_data = await redis_client.get_span_data(redis_key)
            if not span_data:
                logger.error(f"No span data found for span - ${span_id}")
                span_data = {"input_data": None, "output_data": None}
            span_event["input_data"] = span_data.get("input_data")
            span_event["output_data"] = span_data.get("output_data")

        # ========== Fill optional fields ==========
        if span_event.get("duration_ms") is None:
            try:
                from datetime import datetime
                started = datetime.fromisoformat(span_event["started_at"].replace("Z", "+00:00"))
                completed = datetime.fromisoformat(span_event["completed_at"].replace("Z", "+00:00"))
                duration_ms = int((completed - started).total_seconds() * 1000)
                span_event["duration_ms"] = duration_ms
                logger.debug(f"Computed duration: {duration_ms}ms for span {span_id}")
            except Exception as e:
                logger.warning(f"Failed to compute duration for span {span_id}: {e}")
                span_event["duration_ms"] = 0

            # Estimate cost_usd if not provided (based on model pricing)
        if span_event.get("cost_usd") is None and span_event.get("span_type") == "llm_call":
            model_id = span_event.get("model_id", "")
            tokens_input = span_event.get("tokens_input", 0) or 0
            tokens_output = span_event.get("tokens_output", 0) or 0
            
            if model_id and (tokens_input > 0 or tokens_output > 0):
                estimated_cost = estimate_cost(model_id, tokens_input, tokens_output)
                span_event["cost_usd"] = estimated_cost
                logger.debug(f"Estimated cost: ${estimated_cost:.6f} for span {span_id} ({model_id})")

        # ========== ANOMALY DETECTION ==========
        anomalies = detect_span_anomalies(span_event)
        if anomalies:
            severity_order = {"critical": 0, "warning": 1, "info": 2}
            sorted_anomalies = sorted(
                anomalies, 
                key=lambda a: severity_order.get(a.get("severity", "info"), 99)
            )
            span_event["is_anomalous"] = True
            span_event["anomaly_type"] = sorted_anomalies[0]["type"]
            span_event["anomaly_description"] = "; ".join(a["message"] for a in anomalies)
            logger.info(
                f"⚠️ {len(anomalies)} anomal{'y' if len(anomalies)==1 else 'ies'} detected in span {span_id}: "
                f"{span_event['anomaly_type']} (severity: {sorted_anomalies[0]['severity']})"
            )
        
        # ========== DATABASE OPERATIONS ==========
        try:
            # 1. Ensure run exists first (required for foreign key)
            await upsert_run(run_id, span_event)

            # 2. Insert span
            inserted = await insert_span(span_event)
            if not inserted:
                logger.info(f"Duplicate span {span_id} skipped")
                return  # Skip duplicate
        
        except Exception as e:
            logger.error(f"Database error for span {span_id}: {e}")
            # Requeue message for retry
            raise
        
        # ========== WEBSOCKET PUBLISHING ==========
        await publish_to_websocket(channel, {
            "type": "span_received",
            "run_id": run_id,
            "span": span_event
        })
        
        # ========== FINALIZATION CHECK ==========
        if span_event.get("is_final", False):
            logger.info(f"🏁 Final span received for run {run_id}")
            await finalize_run(run_id, channel)
        
        logger.info(f"[OK] Processed span {span_id}")


    return 

def _default_instance_id() -> str:
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"


async def main():
    """Main Analyzer Worker Loop"""

    state = WorkerHealthState()
    instance_id = _default_instance_id()

    
    # Start heartbeat
    hb_task = asyncio.create_task(
        heartbeat_loop(
            redis=redis_client,
            state=state,
            service_name="ai_service",
            instance_id=instance_id,
            interval_s=10,
        ),
        name=f"heartbeat:ai_service:{instance_id}",
    )

    conn = await aio_pika.connect_robust(Config.RABBITMQ_URL)
    channel = await conn.channel()
    await state.set_connected(True)

    await channel.set_qos(prefetch_count=1)

    span_queue = await channel.declare_queue("span_processing", durable=True)

    stop_event = asyncio.Event()

    async def consumer(msg: AbstractIncomingMessage):
        await state.on_msg_start()
        try:
            await handle_message(msg, channel)
            await state.on_msg_ok()
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            await state.on_msg_error()
        finally:
            await state.on_msg_done()

    await span_queue.consume(consumer)
    logger.info("[OK] Analyzer worker ready - consuming from span_processing queue")


    def _stop(*_):
        logger.info("Shutting down analyzer worker...")
        stop_event.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _stop)
        except NotImplementedError:
            pass

    await stop_event.wait()
    
    # Cleanup
    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass

    await redis_client.close()
    await conn.close()
    logger.info("[OK] Analyzer worker stopped")

if __name__ == "__main__":
    asyncio.run(main())
