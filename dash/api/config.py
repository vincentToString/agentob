import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Service settings
    SERVICE_HOST = os.getenv("SERVICE_HOST", "0.0.0.0")
    SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8003"))

    # Database (for review history)
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.getenv("POSTGRES_USER", "agentob_user")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "agentob_password")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "agentob_db")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # RabbitMQ (for queue metrics)
    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:password@localhost:5672/")
    RABBITMQ_MANAGEMENT_URL = os.getenv(
        "RABBITMQ_MANAGEMENT_URL",
        "http://admin:password@rabbitmq:15672"
    )

    # Redis (for real-time metrics)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Refresh intervals (seconds)
    METRICS_REFRESH_INTERVAL = int(os.getenv("METRICS_REFRESH_INTERVAL", "5"))
    HISTORY_RETENTION_DAYS = int(os.getenv("HISTORY_RETENTION_DAYS", "30"))


config = Config()
