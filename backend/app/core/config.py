"""Application configuration from environment."""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ragnetic backend settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://ragnetic:ragneticpassword@localhost:5432/ragnetic"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    minio_url: str = "http://localhost:9000"
    minio_access_key: str = "admin"
    minio_secret_key: str = "password"
    minio_bucket: str = "ragnetic"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    llm_timeout_seconds: int = 30
    llm_connect_timeout_seconds: int = 5
    llm_model_check_timeout_seconds: int = 3
    ollama_num_predict: int = 220
    ollama_temperature: float = 0.1
    openai_api_key: Optional[str] = None

    chunk_max_chars: int = 600
    chunk_overlap_chars: int = 80
    chunk_min_chars: int = 180

    chat_context_max_sources: int = 4
    chat_context_max_chars_per_source: int = 420

    retrieval_top_k: int = 5
    retrieval_dense_limit: int = 20
    retrieval_sparse_pool: int = 240
    retrieval_rerank_top_n: int = 8
    retrieval_enable_cross_encoder: bool = False
    environment: str = "development"

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url.replace("/0", "/1")


settings = Settings()


def validate_security_settings() -> None:
    env = (settings.environment or "development").strip().lower()
    if env in {"prod", "production"} and settings.jwt_secret == "change-me-in-production":
        raise RuntimeError("JWT_SECRET must be set to a strong secret in production.")
