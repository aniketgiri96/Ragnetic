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
    llm_timeout_seconds: int = 90
    llm_connect_timeout_seconds: int = 5
    llm_model_check_timeout_seconds: int = 3
    ollama_num_predict: int = 220
    ollama_temperature: float = 0.1
    openai_api_key: Optional[str] = None

    chunk_max_chars: int = 600
    chunk_overlap_chars: int = 80
    chunk_overlap_sentences: int = 1
    chunk_min_chars: int = 180

    chat_context_max_sources: int = 4
    chat_context_max_chars_per_source: int = 420
    chat_unique_sources_per_document: bool = True
    chat_model_context_tokens: int = 8192
    chat_context_budget_ratio: float = 0.75
    chat_context_reserved_tokens: int = 1200
    chat_context_min_tokens_per_source: int = 80
    chat_context_max_tokens_per_source: int = 260
    chat_context_compression_enabled: bool = True
    chat_context_compression_target_ratio: float = 0.60
    chat_low_confidence_threshold: float = 0.45
    chat_enforce_citation_format: bool = True
    chat_enable_faithfulness_scoring: bool = True
    chat_faithfulness_threshold: float = 0.55

    retrieval_top_k: int = 5
    retrieval_dense_limit: int = 20
    retrieval_sparse_pool: int = 240
    retrieval_rerank_top_n: int = 8
    retrieval_enable_cross_encoder: bool = False
    retrieval_enable_query_expansion: bool = True
    retrieval_query_expansion_max_variants: int = 4
    retrieval_enable_hyde: bool = False
    retrieval_hyde_max_chars: int = 700

    analytics_default_window_days: int = 7
    analytics_top_queries_limit: int = 8
    analytics_drift_zero_result_rate_threshold: float = 0.30
    analytics_drift_retrieval_ms_threshold: int = 1400
    analytics_drift_low_faithfulness_rate_threshold: float = 0.30
    analytics_drift_low_confidence_rate_threshold: float = 0.35
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
