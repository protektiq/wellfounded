"""Single gateway for Anthropic and OpenAI model calls."""

from __future__ import annotations

import time
import uuid
from typing import Any, TypeVar

import httpx
import structlog
from anthropic import AsyncAnthropic
from anthropic.types import Message, ToolChoiceToolParam, ToolParam
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from llm.hashing import completion_input_hash, embedding_input_hash, text_sha256
from llm.models import LLMCallRecord
from llm.prompts import EMBEDDING_PROMPT_ID, Prompt
from llm.retry import async_retry_llm_call
from llm.types import LLMResponse, TokenUsage

log = structlog.get_logger()

S = TypeVar("S", bound=BaseModel)

_EMBED_MODEL = "text-embedding-3-large"
_EMBED_DIMENSIONS = 3072
_EMBED_BATCH_SIZE = 64
_MAX_INPUT_CHARS = 25_000
_MAX_TEXTS = 2048
_STRUCTURED_TOOL_NAME = "structured_output"
_MAX_ERROR_MSG = 10_000


def _request_id_from_context() -> str | None:
    merged = structlog.contextvars.get_merged_contextvars(structlog.get_logger())
    rid = merged.get("request_id")
    return str(rid) if rid is not None else None


def _require_anthropic_key() -> str:
    key = get_settings().anthropic_api_key
    if not key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")
    return key


def _require_openai_key() -> str:
    key = get_settings().openai_api_key
    if not key:
        raise ValueError("OPENAI_API_KEY is not configured")
    return key


def _serialize_raw(model: object) -> dict[str, Any]:
    md = getattr(model, "model_dump", None)
    if callable(md):
        return md(mode="json")  # type: ignore[no-any-return]
    return {"type": type(model).__name__}


def _truncate_error(msg: str) -> str:
    if len(msg) <= _MAX_ERROR_MSG:
        return msg
    return msg[: _MAX_ERROR_MSG - 3] + "..."


def _validate_embed_texts(texts: list[str]) -> list[str]:
    if not texts:
        raise ValueError("texts must be non-empty")
    if len(texts) > _MAX_TEXTS:
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


class LLMClient:
    """Async LLM gateway; persists ``LLMCallRecord`` rows (hashed inputs only)."""

    def __init__(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        *,
        anthropic_client: AsyncAnthropic | None = None,
        openai_client: AsyncOpenAI | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._session = session
        self._organization_id = organization_id
        self._user_id = user_id
        self._anthropic_override = anthropic_client
        self._openai_override = openai_client
        self._http = http_client
        self._anthropic_lazy: AsyncAnthropic | None = None
        self._openai_lazy: AsyncOpenAI | None = None

    def _anthropic(self) -> AsyncAnthropic:
        if self._anthropic_override is not None:
            return self._anthropic_override
        if self._anthropic_lazy is None:
            self._anthropic_lazy = AsyncAnthropic(
                api_key=_require_anthropic_key(),
                max_retries=0,
                http_client=self._http,
            )
        return self._anthropic_lazy

    def _openai(self) -> AsyncOpenAI:
        if self._openai_override is not None:
            return self._openai_override
        if self._openai_lazy is None:
            self._openai_lazy = AsyncOpenAI(
                api_key=_require_openai_key(),
                max_retries=0,
                http_client=self._http,
            )
        return self._openai_lazy

    async def _persist(
        self,
        *,
        prompt_id: str,
        model_id: str,
        usage: dict[str, Any],
        latency_ms: int,
        input_sha256: str,
        success: bool,
        error_message: str | None,
    ) -> None:
        row = LLMCallRecord(
            id=uuid.uuid4(),
            organization_id=self._organization_id,
            user_id=self._user_id,
            prompt_id=prompt_id,
            model_id=model_id,
            usage=usage,
            latency_ms=latency_ms,
            input_sha256=input_sha256,
            success=success,
            error_message=error_message,
        )
        self._session.add(row)
        await self._session.flush()

    async def complete(
        self,
        prompt: Prompt,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        system, user = prompt.rendered()
        mt = prompt.default_max_tokens if max_tokens is None else max_tokens
        temp = prompt.default_temperature if temperature is None else temperature
        if mt < 1 or mt > 200_000:
            raise ValueError("max_tokens out of allowed range")
        if not 0.0 <= temp <= 2.0:
            raise ValueError("temperature must be between 0 and 2")

        input_hash = completion_input_hash(
            prompt_id=prompt.id,
            system=system,
            user=user,
            model_id=prompt.model_id,
            provider=prompt.provider,
        )
        started = time.perf_counter()
        extra_log = {
            "prompt_id": prompt.id,
            "model_id": prompt.model_id,
            "provider": prompt.provider,
        }
        try:
            if prompt.provider == "anthropic":
                msg = await async_retry_llm_call(
                    op_name="anthropic.messages.create",
                    factory=lambda: self._anthropic().messages.create(
                        model=prompt.model_id,
                        max_tokens=mt,
                        temperature=temp,
                        system=system,
                        messages=[{"role": "user", "content": user}],
                    ),
                    log=log,
                    extra=extra_log,
                )
                text = _anthropic_text(msg)
                usage = TokenUsage(
                    prompt_tokens=msg.usage.input_tokens,
                    completion_tokens=msg.usage.output_tokens,
                )
                raw = _serialize_raw(msg)
                rid = _request_id_from_context()
                latency_ms = int((time.perf_counter() - started) * 1000)
                resp = LLMResponse(
                    text=text,
                    model_id=msg.model,
                    usage=usage,
                    latency_ms=latency_ms,
                    request_id=rid,
                    raw_response=raw,
                )
                await self._persist(
                    prompt_id=prompt.id,
                    model_id=msg.model,
                    usage=usage.model_dump(mode="json"),
                    latency_ms=latency_ms,
                    input_sha256=input_hash,
                    success=True,
                    error_message=None,
                )
                return resp

            completion = await async_retry_llm_call(
                op_name="openai.chat.completions.create",
                factory=lambda: self._openai().chat.completions.create(
                    model=prompt.model_id,
                    max_tokens=mt,
                    temperature=temp,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                ),
                log=log,
                extra=extra_log,
            )
            choice0 = completion.choices[0]
            msg_body = choice0.message
            text = msg_body.content or ""
            u = completion.usage
            usage = TokenUsage(
                prompt_tokens=u.prompt_tokens if u else None,
                completion_tokens=u.completion_tokens if u else None,
            )
            raw = _serialize_raw(completion)
            rid = _request_id_from_context()
            latency_ms = int((time.perf_counter() - started) * 1000)
            resp = LLMResponse(
                text=text,
                model_id=completion.model,
                usage=usage,
                latency_ms=latency_ms,
                request_id=rid,
                raw_response=raw,
            )
            await self._persist(
                prompt_id=prompt.id,
                model_id=completion.model,
                usage=usage.model_dump(mode="json"),
                latency_ms=latency_ms,
                input_sha256=input_hash,
                success=True,
                error_message=None,
            )
            return resp
        except BaseException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._persist(
                prompt_id=prompt.id,
                model_id=prompt.model_id,
                usage={},
                latency_ms=latency_ms,
                input_sha256=input_hash,
                success=False,
                error_message=_truncate_error(str(exc)),
            )
            raise

    async def complete_structured(
        self,
        prompt: Prompt,
        schema: type[S],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> S:
        system, user = prompt.rendered()
        mt = prompt.default_max_tokens if max_tokens is None else max_tokens
        temp = prompt.default_temperature if temperature is None else temperature
        if mt < 1 or mt > 200_000:
            raise ValueError("max_tokens out of allowed range")
        if not 0.0 <= temp <= 2.0:
            raise ValueError("temperature must be between 0 and 2")

        input_hash = completion_input_hash(
            prompt_id=prompt.id,
            system=system,
            user=user,
            model_id=prompt.model_id,
            provider=prompt.provider,
            schema_name=schema.__name__,
        )
        started = time.perf_counter()
        extra_log = {
            "prompt_id": prompt.id,
            "model_id": prompt.model_id,
            "provider": prompt.provider,
            "schema": schema.__name__,
        }
        try:
            if prompt.provider == "anthropic":
                tool: ToolParam = {
                    "name": _STRUCTURED_TOOL_NAME,
                    "description": (
                        "Emit structured output matching the requested schema."
                    ),
                    "input_schema": schema.model_json_schema(),
                }
                tool_choice: ToolChoiceToolParam = {
                    "type": "tool",
                    "name": _STRUCTURED_TOOL_NAME,
                }
                msg = await async_retry_llm_call(
                    op_name="anthropic.messages.create_structured",
                    factory=lambda: self._anthropic().messages.create(
                        model=prompt.model_id,
                        max_tokens=mt,
                        temperature=temp,
                        system=system,
                        messages=[{"role": "user", "content": user}],
                        tools=[tool],
                        tool_choice=tool_choice,
                    ),
                    log=log,
                    extra=extra_log,
                )
                parsed = _anthropic_tool_json(msg, _STRUCTURED_TOOL_NAME)
                model_out = schema.model_validate(parsed)
                usage = TokenUsage(
                    prompt_tokens=msg.usage.input_tokens,
                    completion_tokens=msg.usage.output_tokens,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                await self._persist(
                    prompt_id=prompt.id,
                    model_id=msg.model,
                    usage=usage.model_dump(mode="json"),
                    latency_ms=latency_ms,
                    input_sha256=input_hash,
                    success=True,
                    error_message=None,
                )
                return model_out

            completion = await async_retry_llm_call(
                op_name="openai.beta.chat.completions.parse",
                factory=lambda: self._openai().beta.chat.completions.parse(
                    model=prompt.model_id,
                    max_tokens=mt,
                    temperature=temp,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=schema,
                ),
                log=log,
                extra=extra_log,
            )
            parsed_msg = completion.choices[0].message
            parsed_obj = parsed_msg.parsed
            if parsed_obj is None:
                raise RuntimeError(
                    "OpenAI structured completion returned no parsed object"
                )
            u = completion.usage
            usage = TokenUsage(
                prompt_tokens=u.prompt_tokens if u else None,
                completion_tokens=u.completion_tokens if u else None,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._persist(
                prompt_id=prompt.id,
                model_id=completion.model,
                usage=usage.model_dump(mode="json"),
                latency_ms=latency_ms,
                input_sha256=input_hash,
                success=True,
                error_message=None,
            )
            return parsed_obj
        except BaseException as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._persist(
                prompt_id=prompt.id,
                model_id=prompt.model_id,
                usage={},
                latency_ms=latency_ms,
                input_sha256=input_hash,
                success=False,
                error_message=_truncate_error(str(exc)),
            )
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        cleaned = _validate_embed_texts(texts)
        digests = [text_sha256(t) for t in cleaned]
        extra_log = {
            "prompt_id": EMBEDDING_PROMPT_ID,
            "model_id": _EMBED_MODEL,
            "provider": "openai",
        }
        results: list[list[float]] = []
        for start in range(0, len(cleaned), _EMBED_BATCH_SIZE):
            batch = cleaned[start : start + _EMBED_BATCH_SIZE]
            batch_digests = digests[start : start + _EMBED_BATCH_SIZE]
            input_hash = embedding_input_hash(
                model_id=_EMBED_MODEL,
                text_digests=batch_digests,
            )
            batch_started = time.perf_counter()

            async def _run_batch(b: list[str] = batch) -> Any:
                return await self._openai().embeddings.create(
                    model=_EMBED_MODEL,
                    input=b,
                    dimensions=_EMBED_DIMENSIONS,
                )

            try:
                response = await async_retry_llm_call(
                    op_name="openai.embeddings.create",
                    factory=_run_batch,
                    log=log,
                    extra=extra_log,
                )
                vectors = [list(d.embedding) for d in response.data]
                if len(vectors) != len(batch):
                    raise RuntimeError("OpenAI embeddings response length mismatch")
                for v in vectors:
                    if len(v) != _EMBED_DIMENSIONS:
                        raise RuntimeError(
                            "expected embedding dimension "
                            f"{_EMBED_DIMENSIONS}, got {len(v)}",
                        )
                results.extend(vectors)
                u = response.usage
                usage_dict: dict[str, Any] = {}
                if u is not None:
                    usage_dict = {
                        "prompt_tokens": u.prompt_tokens,
                        "total_tokens": u.total_tokens,
                    }
                latency_ms = int((time.perf_counter() - batch_started) * 1000)
                await self._persist(
                    prompt_id=EMBEDDING_PROMPT_ID,
                    model_id=_EMBED_MODEL,
                    usage=usage_dict,
                    latency_ms=latency_ms,
                    input_sha256=input_hash,
                    success=True,
                    error_message=None,
                )
            except BaseException as exc:
                latency_ms = int((time.perf_counter() - batch_started) * 1000)
                await self._persist(
                    prompt_id=EMBEDDING_PROMPT_ID,
                    model_id=_EMBED_MODEL,
                    usage={},
                    latency_ms=latency_ms,
                    input_sha256=input_hash,
                    success=False,
                    error_message=_truncate_error(str(exc)),
                )
                raise
        return results


def _anthropic_text(msg: Message) -> str:
    parts: list[str] = []
    for block in msg.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts)


def _anthropic_tool_json(msg: Message, tool_name: str) -> dict[str, Any]:
    for block in msg.content:
        if block.type == "tool_use" and block.name == tool_name:
            data = block.input
            if isinstance(data, dict):
                return data
            raise TypeError("tool_use input is not a JSON object")
    raise RuntimeError(f"no tool_use block named {tool_name!r} in assistant message")
