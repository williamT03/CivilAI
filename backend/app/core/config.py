from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _csv_env(name: str, default: str = "") -> list[str]:
    raw_value = os.getenv(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CivilAISettings:
    """Environment-driven settings for the SaaS backend.

    The current app still supports local SQLite/Chroma development, but these
    settings provide the production shape for PostgreSQL, Qdrant, Redis, R2/S3,
    and multi-provider AI routing.
    """

    backend_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite:///{(Path(__file__).resolve().parents[2] / 'Data' / 'civilai_auth.db').as_posix()}",
        )
    )
    structured_database_url: str = field(
        default_factory=lambda: os.getenv(
            "STRUCTURED_DATABASE_URL",
            f"sqlite:///{(Path(__file__).resolve().parents[2] / 'Data' / 'civilai_structured.db').as_posix()}",
        )
    )

    cors_allow_origins: list[str] = field(
        default_factory=lambda: _csv_env(
            "CORS_ALLOW_ORIGINS",
            (
                "http://localhost:3000,"
                "http://127.0.0.1:3000,"
                "http://localhost:3001,"
                "http://127.0.0.1:3001,"
                "https://civilai.willcloudlab.com"
            ),
        )
    )
    cors_allow_origin_regex: str | None = field(
        default_factory=lambda: os.getenv(
            "CORS_ALLOW_ORIGIN_REGEX",
            r"https://([a-z0-9-]+\.)?willcloudlab\.com",
        )
    )
    cors_allow_credentials: bool = field(default_factory=lambda: _bool_env("CORS_ALLOW_CREDENTIALS", True))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))))
    max_request_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_REQUEST_BYTES", str(60 * 1024 * 1024))))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")))
    free_monthly_token_limit: int = field(default_factory=lambda: int(os.getenv("FREE_MONTHLY_TOKEN_LIMIT", "0")))
    standard_monthly_token_limit: int = field(default_factory=lambda: int(os.getenv("STANDARD_MONTHLY_TOKEN_LIMIT", "0")))
    pro_monthly_token_limit: int = field(default_factory=lambda: int(os.getenv("PRO_MONTHLY_TOKEN_LIMIT", "0")))
    free_monthly_message_limit: int = field(default_factory=lambda: int(os.getenv("FREE_MONTHLY_MESSAGE_LIMIT", "0")))
    pro_monthly_message_limit: int = field(default_factory=lambda: int(os.getenv("PRO_MONTHLY_MESSAGE_LIMIT", "0")))

    ai_default_provider: str = field(default_factory=lambda: os.getenv("AI_DEFAULT_PROVIDER", "openai"))
    ai_fallback_provider: str = field(default_factory=lambda: os.getenv("AI_FALLBACK_PROVIDER", "deepseek"))
    ai_local_provider: str = field(default_factory=lambda: os.getenv("AI_LOCAL_PROVIDER", "ollama"))
    ai_embedding_provider: str = field(default_factory=lambda: os.getenv("AI_EMBEDDING_PROVIDER", "openai"))
    ai_background_provider: str = field(default_factory=lambda: os.getenv("AI_BACKGROUND_PROVIDER", "deepseek"))
    ai_request_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60")))
    ai_max_retries: int = field(default_factory=lambda: int(os.getenv("AI_MAX_RETRIES", "2")))
    ai_enable_ollama_fallback: bool = field(default_factory=lambda: _bool_env("AI_ENABLE_OLLAMA_FALLBACK", True))

    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_chat_model: str = field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"))
    openai_embedding_model: str = field(default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))

    deepseek_api_key: str | None = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
    deepseek_base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_chat_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat"))
    deepseek_reasoner_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"))

    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3"))

    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    async_ingestion_enabled: bool = field(default_factory=lambda: _bool_env("ASYNC_INGESTION_ENABLED", False))
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str | None = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    qdrant_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("QDRANT_TIMEOUT_SECONDS", "300")))
    qdrant_upsert_batch_size: int = field(default_factory=lambda: int(os.getenv("QDRANT_UPSERT_BATCH_SIZE", "64")))
    vector_store_backend: str = field(default_factory=lambda: os.getenv("VECTOR_STORE_BACKEND", "chroma"))
    chroma_persist_directory: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIRECTORY", "backend/Data/chroma_db"))

    s3_endpoint_url: str | None = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL") or os.getenv("R2_ENDPOINT_URL"))
    s3_bucket_name: str | None = field(default_factory=lambda: os.getenv("S3_BUCKET_NAME") or os.getenv("R2_BUCKET_NAME"))
    s3_access_key_id: str | None = field(default_factory=lambda: os.getenv("S3_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY_ID"))
    s3_secret_access_key: str | None = field(default_factory=lambda: os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("R2_SECRET_ACCESS_KEY"))
    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    local_upload_directory: str = field(default_factory=lambda: os.getenv("LOCAL_UPLOAD_DIRECTORY", "backend/Data/PDF"))

    def provider_order(self, purpose: str = "answer") -> list[str]:
        if purpose == "embedding":
            primary = self.ai_embedding_provider
        elif purpose in {"background", "summary", "classification", "cleanup"}:
            primary = self.ai_background_provider
        elif self.environment.lower() in {"local", "dev-local"}:
            primary = self.ai_local_provider
        else:
            primary = self.ai_default_provider

        ordered = [primary, self.ai_fallback_provider]
        if self.ai_enable_ollama_fallback:
            ordered.append(self.ai_local_provider)

        deduped: list[str] = []
        for provider in ordered:
            normalized = provider.strip().lower()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped


@lru_cache(maxsize=1)
def get_settings() -> CivilAISettings:
    return CivilAISettings()
