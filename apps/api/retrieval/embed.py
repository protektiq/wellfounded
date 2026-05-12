"""Batch embeddings for retrieval (OpenAI text-embedding-3-large).

Model calls are centralized here; a future ``llm/client.py`` may delegate to
this module to avoid duplicating SDK wiring.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from config import get_settings

# Batches sized for throughput while staying under per-request token limits.
_EMBED_BATCH_SIZE = 64
_MAX_INPUT_CHARS = 25_000
_EMBED_MODEL = "text-embedding-3-large"
_EMBED_DIMENSIONS = 3072
_MAX_RETRIES = 8
_BASE_DELAY_SEC = 0.5


def _validate_texts(texts: Sequence[str]) -> list[str]:
    if not texts:
        raise ValueError("texts must be non-empty")
    if len(texts) > 2048:
        raise ValueError("texts batch exceeds maximum length")
    out: list[str] = []
    for i, t in enumerate(texts):
        if not isinstance(t, str):
            raise TypeError(f"texts[{i}] must be str")
        stripped = t.strip()
        if not stripped:
            raise ValueError(f"texts[{i}] is empty or whitespace-only")
        if len(stripped) > _MAX_INPUT_CHARS:
            raise ValueError(f"texts[{i}] exceeds {_MAX_INPUT_CHARS} characters")
        out.append(stripped)
    return out


async def _embed_batch_with_retry(
    client: AsyncOpenAI,
    batch: list[str],
) -> list[list[float]]:
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.embeddings.create(
                model=_EMBED_MODEL,
                input=batch,
                dimensions=_EMBED_DIMENSIONS,
            )
            return [list(d.embedding) for d in response.data]
        except RateLimitError as exc:
            last_exc = exc
        except (APIConnectionError, APITimeoutError) as exc:
            last_exc = exc
        if attempt >= _MAX_RETRIES - 1:
            assert last_exc is not None
            raise last_exc
        delay = _BASE_DELAY_SEC * (2**attempt)
        delay += random.uniform(0, 0.25 * delay)
        await asyncio.sleep(delay)
    assert last_exc is not None
    msg = "OpenAI embedding exhausted retries without success"
    raise RuntimeError(msg) from last_exc


async def embed_texts(
    texts: Sequence[str],
    *,
    api_key: str | None = None,
) -> list[list[float]]:
    """Return one embedding vector per input string, preserving order."""
    cleaned = _validate_texts(texts)
    key = api_key if api_key is not None else get_settings().openai_api_key
    if not key:
        raise ValueError("OPENAI_API_KEY is not configured")
    client = AsyncOpenAI(api_key=key)
    results: list[list[float]] = []
    for start in range(0, len(cleaned), _EMBED_BATCH_SIZE):
        batch = cleaned[start : start + _EMBED_BATCH_SIZE]
        vectors = await _embed_batch_with_retry(client, batch)
        if len(vectors) != len(batch):
            raise RuntimeError("OpenAI embeddings response length mismatch")
        for v in vectors:
            if len(v) != _EMBED_DIMENSIONS:
                raise RuntimeError(
                    f"expected embedding dimension {_EMBED_DIMENSIONS}, got {len(v)}",
                )
        results.extend(vectors)
    return results
