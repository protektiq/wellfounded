"""Pydantic v2 models for eval fixtures and result manifests.

All models forbid extra fields and apply length caps; fixtures are user/file
input and must be validated before use. The ``input`` and ``expected``
dictionaries are intentionally opaque so each scorer can define its own
contract; the runner only enforces overall structure.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Categories mirror the four eval areas in PRD section 5.3.
# citation_faithfulness_live calls the model; the others are deterministic.
Category = Literal[
    "citation_faithfulness",
    "citation_faithfulness_live",
    "declaration_quality",
    "transcription_wer",
    "translation_quality",
]

CATEGORIES: tuple[Category, ...] = (
    "citation_faithfulness",
    "citation_faithfulness_live",
    "declaration_quality",
    "transcription_wer",
    "translation_quality",
)

_FIXTURE_ID_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,127}$"
_MAX_SCORER_NAME = 64
_MAX_TAG_COUNT = 16
_MAX_TAG_LEN = 64
_MAX_INPUT_BYTES = 1_000_000


class Fixture(BaseModel):
    """One eval case loaded from a JSON file under ``evals/fixtures/<category>/``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=_FIXTURE_ID_PATTERN)
    category: Category
    scorer: str = Field(min_length=1, max_length=_MAX_SCORER_NAME)
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAG_COUNT)

    def validate_tags(self) -> None:
        for t in self.tags:
            if not isinstance(t, str):
                raise TypeError("fixture tag must be a string")
            if not 1 <= len(t) <= _MAX_TAG_LEN:
                raise ValueError(
                    f"fixture tag length out of range (1..{_MAX_TAG_LEN})",
                )


class ScoreResult(BaseModel):
    """Per-fixture scorer output. ``score`` is None if the scorer errored."""

    model_config = ConfigDict(extra="forbid")

    score: float | None = Field(default=None)
    passed: bool | None = Field(default=None)
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=10_000)


class FixtureRun(BaseModel):
    """One ``Fixture`` evaluated against one scorer in a single run."""

    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(max_length=128)
    fixture_path: str = Field(max_length=1024)
    scorer: str = Field(max_length=_MAX_SCORER_NAME)
    result: ScoreResult
    model_id: str | None = Field(default=None, max_length=128)
    latency_ms: int = Field(ge=0)


class RunManifest(BaseModel):
    """Top-level result file written by the runner; comparable across runs."""

    model_config = ConfigDict(extra="forbid")

    runner_version: Literal[1] = 1
    run_id: str = Field(min_length=1, max_length=64)
    git_sha: str = Field(min_length=1, max_length=64)
    category: Category
    started_at: str = Field(min_length=1, max_length=64)
    finished_at: str = Field(min_length=1, max_length=64)
    fixtures_root: str = Field(max_length=1024)
    fixtures: list[FixtureRun] = Field(default_factory=list)


def fixture_size_ok(raw: bytes) -> bool:
    """Reject suspiciously large fixture files before JSON parsing."""
    return len(raw) <= _MAX_INPUT_BYTES
