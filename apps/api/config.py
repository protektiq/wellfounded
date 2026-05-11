from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
        description="Redis URL for future queue work",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
