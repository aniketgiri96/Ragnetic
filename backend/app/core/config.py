"""Application configuration from environment."""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """KnowAI backend settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://knowai:knowaipassword@localhost:5432/knowai"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    minio_url: str = "http://localhost:9000"
    minio_access_key: str = "admin"
    minio_secret_key: str = "password"
    minio_bucket: str = "knowai"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_api_key: Optional[str] = None

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url.replace("/0", "/1")


settings = Settings()
