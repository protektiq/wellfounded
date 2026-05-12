"""Exponential backoff for retryable HTTP failures (429, 5xx)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from anthropic import APIStatusError as AnthropicAPIStatusError
from openai import APIStatusError as OpenAIAPIStatusError

T = TypeVar("T")

_MAX_RETRIES = 3
_BASE_DELAY_SEC = 0.35


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, AnthropicAPIStatusError):
        code = exc.status_code
        return code == 429 or code >= 500
    if isinstance(exc, OpenAIAPIStatusError):
        code = exc.status_code
        return code == 429 or code >= 500
    return False


async def async_retry_llm_call(
    *,
    op_name: str,
    factory: Callable[[], Awaitable[T]],
    log: Any,
    extra: dict[str, Any],
) -> T:
    """Run ``factory`` with up to three retries (four attempts total)."""
    last: BaseException | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await factory()
        except BaseException as exc:
            last = exc
            if attempt >= _MAX_RETRIES or not _is_retryable(exc):
                raise
            delay = _BASE_DELAY_SEC * (2**attempt)
            delay += random.uniform(0, 0.25 * delay)
            status_code: int | None = None
            if isinstance(exc, AnthropicAPIStatusError | OpenAIAPIStatusError):
                status_code = exc.status_code
            log.warning(
                "llm_retry",
                op=op_name,
                attempt=attempt + 1,
                max_attempts=_MAX_RETRIES + 1,
                status_code=status_code,
                error_type=type(exc).__name__,
                **extra,
            )
            await asyncio.sleep(delay)
    assert last is not None
    raise last
