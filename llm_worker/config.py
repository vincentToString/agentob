import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # RabbitMQ
    RABBITMQ_URL = os.getenv(
        "RABBITMQ_URL", "amqp://admin:password@localhost:5672/"
    )
    
    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # PostgreSQL
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.getenv("POSTGRES_USER", "agentob_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "agentob_password")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "agentob_db")
    
    # LLM (OpenRouter)
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE = os.getenv(
        "OPENROUTER_BASE", "https://openrouter.ai/api/v1/chat/completions"
    )
    MODEL = os.getenv("MODEL", "qwen/qwen3.6-plus:free")
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "20"))
    
    # Analysis settings
    MAX_FILES = int(os.getenv("MAX_FILES_FOR_SNIPPETS", "3"))
    MAX_LINES = int(os.getenv("MAX_LINES_PER_FILE", "120"))

    # RAG service settings
    RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8001")
    RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
    RAG_TIMEOUT = int(os.getenv("RAG_TIMEOUT", "5"))
