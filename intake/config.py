import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5"))
    HEARTBEAT_TTL_SECONDS = int(os.getenv("HEARTBEAT_TTL_SECONDS", "15"))

    # If you already have a SERVICE_NAME concept elsewhere, reuse it.
    SERVICE_NAME = os.getenv("SERVICE_NAME", "intake")

    # Use something stable-ish in containers:
    INSTANCE_ID = os.getenv("INSTANCE_ID")

    RABBITMQ_URL = os.getenv('RABBITMQ_URL')

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    TRACE_TTL = int(os.getenv("TRACE_TTL", "3600"))

    # Span size thresholds (in bytes)
    # If COMBINED input_data + output_data exceed this, store in Redis
    LARGE_FIELD_THRESHOLD = int(os.getenv("LARGE_FIELD_THRESHOLD", "10000"))  # 10KB

    # Future: Bloombox URL for advanced analysis
    BLOOMBOX_URL = os.getenv("BLOOMBOX_URL", "http://bloombox:8080")