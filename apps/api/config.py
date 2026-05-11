from __future__ import annotations

from functools import lru_cache

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
