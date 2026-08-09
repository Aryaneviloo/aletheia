"""
aletheia_core.config
=====================

Centralized, validated configuration for every Aletheia service.

Why this exists
----------------

Every service in this architecture imports `get_settings()` from here
instead of touching `os.environ` directly. Pydantic validates types and
required fields at import time, so a missing DATABASE_URL fails on startup 

Usage
-----
    from aletheia_core.config import get_settings

    settings = get_settings()
    engine = create_engine(str(settings.database_url))
"""
from pathlib import Path
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
class Settings(BaseSettings):
    """
    Single source of truth for runtime configuration.

    Every field here maps to an environment variable of the same name
    (case-insensitive), read from the process environment first, falling
    back to a `.env` file if present 
    """

    # --- Identity -----------------------------------------------------
    app_name: str = Field(default="aletheia-service")
    environment: Literal["local", "staging", "production"] = Field(default="local")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")


    # --- Postgres  -------
    database_url: PostgresDsn = Field(
        ...,
        description="postgresql+psycopg://user:pass@host:5432/dbname",
    )
    database_pool_size: int = Field(default=10, ge=1)
    database_pool_max_overflow: int = Field(default=20, ge=0)


    # --- Qdrant --------
    qdrant_url: str = Field(default="http://qdrant:6333")
    qdrant_api_key: str | None = Field(default=None)
    qdrant_collection_prefix: str = Field(default="aletheia")


    # --- Redis / Celery broker + result backend ------------------------
    redis_url: RedisDsn = Field(default="redis://redis:6379/0")


    # --- Inference service (embedder / reranker / Ollama proxy) --------
    inference_service_url: str = Field(default="http://inference-service:8100")
    ollama_url: str = Field(default="http://ollama:11434")
    ollama_model: str = Field(default="llama3.2:1b")


    # --- Embedding / retrieval -----------------------------------
    embedding_model_name: str = Field(default="BAAI/bge-small-en-v1.5")
    embedding_dim: int = Field(default=384, gt=0)
    reranker_model_name: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    chunk_size_tokens: int = Field(default=400, gt=0)
    chunk_overlap_tokens: int = Field(default=60, ge=0)
    max_upload_mb: int = Field(default=25, gt=0)


    # --- Auth ------------------------------------------------------------
    jwt_secret_key: str = Field(
        default="dev-only-insecure-secret-change-me",
        description="MUST be overridden via env in staging/production.",
    )
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30, gt=0)
    refresh_token_expire_days: int = Field(default=14, gt=0)


    # --- CORS --------------------------------------------------------------
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",          # unrelated env vars (e.g. POSTGRES_USER, used only by the db image) don't break parsing
        case_sensitive=False,
    )

    # --- LLM provider selection ------------------------------------------
    llm_provider: Literal["ollama", "groq"] = Field(default="ollama")
    groq_api_key: str | None = Field(default=None)
    groq_model: str = Field(default="llama-3.1-8b-instant")


    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_secret_key(cls, v: str, info) -> str:
        """
        Refuse to boot in production with the placeholder dev secret.
        """

        if info.data.get("environment") == "production" and v == "dev-only-insecure-secret-change-me":
            raise ValueError(
                "JWT_SECRET_KEY must be set explicitly when ENVIRONMENT=production."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    """
    Returns a process-wide singleton Settings instance.
    """
    return Settings()