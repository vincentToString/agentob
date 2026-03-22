import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    DIFF_TTL = int(os.getenv("DIFF_TTL", "3600"))

    # Legacy OpenRouter settings
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
    MODEL = os.getenv("MODEL", "deepseek/deepseek-chat-v3.1:free")

    # Bedrock settings
    AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
    BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "")

    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "20"))
    MAX_FILES = int(os.getenv("MAX_FILES_FOR_SNIPPETS", "3"))
    MAX_LINES = int(os.getenv("MAX_LINES_PER_FILE", "120"))

    # RAG service settings
    RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8001")
    RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
    RAG_TIMEOUT = int(os.getenv("RAG_TIMEOUT", "5"))
