from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="local", description="Deployment environment name")
    log_level: str = Field(default="INFO")

    database_url: str = Field(
        default="postgresql+asyncpg://wellfounded:wellfounded@127.0.0.1:15432/wellfounded",
        description="Async SQLAlchemy database URL",
    )

    checkpoint_database_url: str | None = Field(
        default=None,
        max_length=1024,
        description=(
            "Optional psycopg connection URI for LangGraph checkpoints; "
            "defaults to database_url with asyncpg driver stripped"
        ),
    )

    s3_endpoint_url: str = Field(
        default="http://127.0.0.1:9000",
        description="S3-compatible endpoint (MinIO locally)",
    )
    s3_region: str = Field(default="us-east-1")
    s3_bucket: str = Field(default="wellfounded-dev")
    aws_access_key_id: str = Field(default="minioadmin")
    aws_secret_access_key: str = Field(default="minioadmin")

    redis_url: str = Field(
        default="redis://127.0.0.1:16379/0",
        description="Redis URL for retrieval cache and future queue work",
    )

    retrieval_cache_enabled: bool = Field(
        default=True,
        description="When false, skip Redis for retrieval vector candidate cache",
    )

    retrieval_rerank_backend: Literal["llm", "cross_encoder"] = Field(
        default="llm",
        description="Reranker: LLM structured (default) or local cross-encoder",
    )

    retrieval_cross_encoder_model: str = Field(
        default="BAAI/bge-reranker-large",
        max_length=256,
        description="HuggingFace id when retrieval_rerank_backend is cross_encoder",
    )

    retrieval_vector_candidate_multiplier: int = Field(
        default=8,
        ge=1,
        le=50,
        description="ANN candidate pool size is min(max, top_k * multiplier)",
    )

    retrieval_vector_max_candidates: int = Field(
        default=200,
        ge=20,
        le=500,
        description="Upper cap on ANN candidates before reranking",
    )

    git_sha: str | None = Field(
        default=None,
        description="Override application version (GIT_SHA in environment)",
    )

    anthropic_api_key: str | None = Field(default=None)
    openai_api_key: str | None = Field(default=None)

    public_app_url: str = Field(
        default="http://127.0.0.1:3000",
        max_length=512,
        description="Browser app base URL for post-login redirect",
    )
    api_public_url: str = Field(
        default="http://127.0.0.1:8000",
        max_length=512,
        description="Public base URL of this API (magic-link callback host)",
    )
    magic_link_ttl_seconds: int = Field(
        default=900,
        ge=60,
        le=86400,
        description="Magic-link token lifetime in seconds",
    )
    email_backend: Literal["console", "ses"] = Field(
        default="console",
        description="Email transport: console (dev) or ses (stub)",
    )

    e2e_magic_link_reveal_enabled: bool = Field(
        default=False,
        description=(
            "When true (local only), magic-link POST may return the callback URL"
        ),
    )
    e2e_magic_link_secret: str | None = Field(
        default=None,
        max_length=256,
        description="Shared secret for X-E2E-Secret header when reveal is enabled",
    )

    country_conditions_e2e_stub: bool = Field(
        default=False,
        description=(
            "When true (local only), country conditions generation uses a fixture memo"
        ),
    )

    webauthn_rp_id: str = Field(
        default="",
        max_length=253,
        description="WebAuthn RP ID; empty uses hostname of public_app_url",
    )
    webauthn_rp_name: str = Field(
        default="Wellfounded",
        min_length=1,
        max_length=64,
        description="Human-readable relying party name shown by authenticators",
    )

    @field_validator("public_app_url", "api_public_url")
    @classmethod
    def http_base_url(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if len(stripped) > 512:
            raise ValueError("URL exceeds maximum length")
        return stripped

    @field_validator("log_level")
    @classmethod
    def log_level_upper(cls, value: str) -> str:
        upper = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    def resolved_webauthn_rp_id(self) -> str:
        stripped = self.webauthn_rp_id.strip()
        if stripped:
            if len(stripped) > 253:
                raise ValueError("webauthn_rp_id exceeds maximum length")
            return stripped
        parsed = urlparse(self.public_app_url)
        host = parsed.hostname
        if host is None or host == "":
            raise ValueError(
                "public_app_url must include a hostname for WebAuthn RP ID",
            )
        if len(host) > 253:
            raise ValueError("derived WebAuthn RP ID exceeds maximum length")
        return host

    def resolved_webauthn_expected_origins(self) -> list[str]:
        parsed = urlparse(self.public_app_url)
        netloc = parsed.netloc
        if not netloc:
            raise ValueError("public_app_url must include a host for WebAuthn origins")
        origin = f"{parsed.scheme}://{netloc}"
        return [origin]

    def resolved_checkpoint_database_url(self) -> str:
        """URI for psycopg (LangGraph AsyncPostgresSaver); not asyncpg."""
        if self.checkpoint_database_url is not None:
            raw = self.checkpoint_database_url.strip()
            if not raw:
                raise ValueError("checkpoint_database_url must be non-empty when set")
            if len(raw) > 1024:
                raise ValueError("checkpoint_database_url exceeds maximum length")
            return raw
        url = self.database_url.strip()
        for prefix in (
            "postgresql+asyncpg://",
            "postgres+asyncpg://",
        ):
            if url.startswith(prefix):
                return "postgresql://" + url[len(prefix) :]
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            return url
        raise ValueError("database_url must be a recognized PostgreSQL URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
