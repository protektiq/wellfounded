"""Registry-style prompt definitions (module-level constants only)."""

from __future__ import annotations

import string
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

_MAX_SYSTEM_CHARS = 100_000
_MAX_USER_TEMPLATE_CHARS = 100_000
_MAX_VAR_KEY_LEN = 64
_MAX_VAR_VALUE_CHARS = 100_000

Provider = Literal["anthropic", "openai"]

DEFAULT_CLAUDE_MODEL = "claude-opus-4-7"

# Stable id for embedding calls (no Prompt template; used only for audit rows).
EMBEDDING_PROMPT_ID = "platform.embed.text_embedding_3_large"


@dataclass(frozen=True)
class Prompt:
    """Immutable prompt template; variables are bound at construction time."""

    id: str
    system: str
    user_template: str
    variables: tuple[tuple[str, str], ...] = ()
    provider: Provider = "anthropic"
    model_id: str = DEFAULT_CLAUDE_MODEL
    default_max_tokens: int = 4096
    default_temperature: float = 0.0

    def __post_init__(self) -> None:
        if not self.id or len(self.id) > 256:
            raise ValueError("prompt id must be non-empty and at most 256 characters")
        if len(self.system) > _MAX_SYSTEM_CHARS:
            raise ValueError("system prompt exceeds maximum length")
        if len(self.user_template) > _MAX_USER_TEMPLATE_CHARS:
            raise ValueError("user_template exceeds maximum length")
        if self.default_max_tokens < 1 or self.default_max_tokens > 200_000:
            raise ValueError("default_max_tokens out of allowed range")
        if not 0.0 <= self.default_temperature <= 2.0:
            raise ValueError("default_temperature must be between 0 and 2")
        for k, v in self.variables:
            if len(k) > _MAX_VAR_KEY_LEN:
                raise ValueError("variable key exceeds maximum length")
            if len(v) > _MAX_VAR_VALUE_CHARS:
                raise ValueError("variable value exceeds maximum length")
        _validate_template_fields(self.user_template, self.variables)

    def rendered(self) -> tuple[str, str]:
        """Return (system, user) message bodies."""
        vars_dict = dict(self.variables)
        user = self.user_template.format(**vars_dict)
        if len(user) > _MAX_USER_TEMPLATE_CHARS * 2:
            raise ValueError("rendered user message exceeds maximum length")
        return self.system, user


def with_variables(prompt: Prompt, variables: Mapping[str, str]) -> Prompt:
    """Return a copy of ``prompt`` with variables replaced (sorted for stability)."""
    pairs = tuple(sorted(variables.items()))
    return Prompt(
        id=prompt.id,
        system=prompt.system,
        user_template=prompt.user_template,
        variables=pairs,
        provider=prompt.provider,
        model_id=prompt.model_id,
        default_max_tokens=prompt.default_max_tokens,
        default_temperature=prompt.default_temperature,
    )


def _validate_template_fields(
    template: str,
    variables: tuple[tuple[str, str], ...],
) -> None:
    fields: set[str] = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is not None:
            fields.add(field_name)
    keys = {k for k, _ in variables}
    if fields != keys:
        raise ValueError(
            "user_template fields "
            f"{sorted(fields)} do not match variables keys {sorted(keys)}",
        )


# Example prompt for tests and smoke checks (not used in production flows yet).
EXAMPLE_PING_PROMPT = Prompt(
    id="internal.example.ping",
    system="You are a concise assistant.",
    user_template="Reply with the single word: pong.",
    variables=(),
    default_max_tokens=64,
    default_temperature=0.0,
)

# Reranks retrieval passages by relevance to the user query (structured tool output).
TRANSLATION_REVIEW_PROMPT = Prompt(
    id="translation.review.segment_batch",
    system=(
        "You review machine translations of asylum interview segments for US "
        "immigration practice. Preserve legal terminology, proper nouns, place "
        "names, organization names, and dates exactly when correct. Fix only "
        "clear errors or awkward phrasing. Respond with JSON only: "
        '{"english_segments": ["...", ...]} with one string per input segment '
        "in the same order."
    ),
    user_template=(
        "Source language code: {source_language}\n\n"
        "Segments (JSON array of objects with source_text and nllb_english):\n"
        "{segments_json}\n"
    ),
    variables=(("source_language", ""), ("segments_json", "")),
    default_max_tokens=8192,
    default_temperature=0.0,
)

RETRIEVAL_RERANK_PROMPT = Prompt(
    id="retrieval.rerank.order_passages",
    system=(
        "You rank source passages for a legal country-conditions research query. "
        "Given the query and a list of passages (each with passage_id and short "
        "text), emit ordered_passage_ids: every passage_id exactly once, "
        "most relevant first. Use only the provided passage_id values; do not "
        "invent ids."
    ),
    user_template=(
        "Query:\n{query}\n\n"
        "Passages (JSON array of objects with passage_id and text_snippet):\n"
        "{passages_json}\n"
    ),
    variables=(("query", ""), ("passages_json", "")),
    default_max_tokens=4096,
    default_temperature=0.0,
)
