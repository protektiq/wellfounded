"""Pydantic types for LLM responses (in-memory audit payloads)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    model_id: str
    usage: TokenUsage
    latency_ms: int = Field(ge=0)
    request_id: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
