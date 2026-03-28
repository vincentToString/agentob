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
from .trace_collector import router as trace_router


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
        # Declare analyzer exchange and queue
        analyzer_exchange = await setup_channel.declare_exchange(
            "analyzer_exchange", ExchangeType.DIRECT, durable=True
        )
        trace_queue = await setup_channel.declare_queue(
            "trace_events", durable=True
        )
        await trace_queue.bind(analyzer_exchange, routing_key="trace")

        # Declare alert exchange and queues
        alert_exchange = await setup_channel.declare_exchange(
            "alert_exchange",
            ExchangeType.FANOUT,
            durable=True
        )
    
        await setup_channel.declare_queue("alerts", durable=True)
        await setup_channel.declare_queue("slack_msgs", durable=True)
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
