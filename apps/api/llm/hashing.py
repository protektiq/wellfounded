"""Canonical SHA-256 fingerprints for LLM inputs (no raw text persisted)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from llm.prompts import EMBEDDING_PROMPT_ID

_MAX_SERIALIZED_BYTES = 512_000


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dump_canonical(payload: dict[str, Any]) -> bytes:
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    encoded = text.encode("utf-8")
    if len(encoded) > _MAX_SERIALIZED_BYTES:
        raise ValueError("serialized hash payload exceeds maximum size")
    return encoded


def completion_input_hash(
    *,
    prompt_id: str,
    system: str,
    user: str,
    model_id: str,
    provider: Literal["anthropic", "openai"],
    schema_name: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "kind": "completion",
        "model_id": model_id,
        "prompt_id": prompt_id,
        "provider": provider,
        "system": system,
        "user": user,
    }
    if schema_name is not None:
        payload["schema_name"] = schema_name
    return sha256_hex(_dump_canonical(payload))


def embedding_input_hash(*, model_id: str, text_digests: list[str]) -> str:
    payload: dict[str, Any] = {
        "kind": "embed",
        "model_id": model_id,
        "prompt_id": EMBEDDING_PROMPT_ID,
        "provider": "openai",
        "text_digests": text_digests,
    }
    return sha256_hex(_dump_canonical(payload))


def text_sha256(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))
