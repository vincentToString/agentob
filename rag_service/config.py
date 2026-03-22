import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_user: str = os.getenv("POSTGRES_USER", "prowl_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "prowl_password")
    postgres_db: str = os.getenv("POSTGRES_DB", "prowl_db")

    # RabbitMQ
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://admin:password@localhost:5672/")

    # OpenRouter API
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base: str = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # Service
    service_host: str = os.getenv("SERVICE_HOST", "0.0.0.0")
    service_port: int = int(os.getenv("SERVICE_PORT", "8002"))

    # Knowledge Graph Settings
    kg_chunk_size: int = int(os.getenv("KG_CHUNK_SIZE", "512"))
    kg_chunk_overlap: int = int(os.getenv("KG_CHUNK_OVERLAP", "50"))
    kg_max_entities_per_chunk: int = int(os.getenv("KG_MAX_ENTITIES_PER_CHUNK", "10"))

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def async_database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


settings = Settings()
