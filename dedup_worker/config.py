"""Configuration for Dedup Worker"""
import os

class Config:
    # RabbitMQ
    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    # BloomBox gRPC
    BLOOMBOX_GRPC_HOST = os.getenv("BLOOMBOX_GRPC_HOST", "localhost")
    BLOOMBOX_GRPC_PORT = int(os.getenv("BLOOMBOX_GRPC_PORT", "50051"))
    BLOOMBOX_HTTP_URL = os.getenv("BLOOMBOX_HTTP_URL", "http://localhost:8080")

    # BloomBox filter settings
    BLOOM_EXPECTED_ITEMS = int(os.getenv("BLOOM_EXPECTED_ITEMS", "1000000"))  # 1M spans/day
    BLOOM_FALSE_POS_RATE = float(os.getenv("BLOOM_FALSE_POS_RATE", "0.01"))  # 1% FP rate

    # Worker settings
    PREFETCH_COUNT = int(os.getenv("DEDUP_PREFETCH_COUNT", "100"))
    HEALTHCHECK_INTERVAL = int(os.getenv("BLOOMBOX_HEALTHCHECK_INTERVAL", "30"))  # seconds

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
