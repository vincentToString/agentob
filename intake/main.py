from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel
import logging
from dotenv import load_dotenv
import os
from aio_pika import connect_robust, ExchangeType
from intake.config import Config
from .heartbeat import HeartbeatEmitter
from .redis_client import RedisClient
from .span_collector import router as trace_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

redis_client = RedisClient(Config.REDIS_URL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic"""
    # Startup
    logger.info("Starting intake service...")
    app.state.rabbitmq_connection = await connect_robust(Config.RABBITMQ_URL)

    setup_channel = await app.state.rabbitmq_connection.channel()

    try:
        # ========== NEW STREAMING ARCHITECTURE ==========

        # 1. Span intake exchange and queue (intake → dedup worker)
        span_intake_exchange = await setup_channel.declare_exchange(
            "span_intake_exchange", ExchangeType.DIRECT, durable=True
        )
        span_intake_queue = await setup_channel.declare_queue(
            "span_intake", durable=True
        )
        await span_intake_queue.bind(span_intake_exchange, routing_key="span")
        logger.info("[OK] Created span_intake queue")

        # 2. Span processing queue (dedup → analyzer worker)
        span_processing_exchange = await setup_channel.declare_exchange(
            "span_processing_exchange", ExchangeType.DIRECT, durable=True
        )
        span_processing_queue = await setup_channel.declare_queue(
            "span_processing", durable=True
        )
        await span_processing_queue.bind(span_processing_exchange, routing_key="span")
        logger.info("[OK] Created span_processing queue")

        # 3. LLM Summary Queue (analyzer worker -> llm summary)
        llm_summary_exchange = await setup_channel.declare_exchange(
            "llm_summary_exchange", ExchangeType.DIRECT, durable=True
        )
        llm_summary_queue = await setup_channel.declare_queue(
            "llm_summary", durable=True
        )
        await llm_summary_queue.bind(llm_summary_exchange, routing_key="trace")
        logger.info("[OK] Created span_processing queue")

        # 4. WebSocket events exchange (analyzer → websocket service)
        websocket_exchange = await setup_channel.declare_exchange(
            "websocket_events",
            ExchangeType.FANOUT,  # Broadcast to all websocket workers
            durable=True
        )
        logger.info("[OK] Created websocket_events exchange")

        # 5. Alert exchange and queues (existing - keep for compatibility)
        alert_exchange = await setup_channel.declare_exchange(
            "alert_exchange",
            ExchangeType.FANOUT,
            durable=True
        )
        await setup_channel.declare_queue("alerts", durable=True)
        await setup_channel.declare_queue("slack_msgs", durable=True)
        logger.info("[OK] Created alert queues")

        logger.info("[OK] All RabbitMQ queues initialized for streaming architecture")
    finally: 
        await setup_channel.close()
    
    app.state.heartbeat = HeartbeatEmitter(
        redis_client,
        service_name="intake",
        instance_id=Config.INSTANCE_ID,
        interval_s=Config.HEARTBEAT_INTERVAL_SECONDS,
        ttl_s=Config.HEARTBEAT_TTL_SECONDS,
        metadata={
            "port": 8000,
            "env": os.getenv("ENV", "dev"),
        },
    )
    await app.state.heartbeat.start()

    yield

    logger.info("Stopping heartbeat...")
    hb = getattr(app.state, "heartbeat", None)
    if hb:
        await redis_client.deregister_instance("intake", hb.instance_id)
        await hb.stop()

    logger.info("Closing Redis connection...")
    await redis_client.close()

    logger.info("Closing RabbitMQ connection")
    await app.state.rabbitmq_connection.close()
    

app = FastAPI(title="AgentOB trace Collector", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "trace_collector"}

app.include_router(trace_router)
