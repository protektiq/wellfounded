"""Shared criterion keys for declaration quality evals."""

from __future__ import annotations

DECLARATION_CRITERION_KEYS: tuple[str, ...] = (
    "faithfulness_to_source",
    "structural_completeness",
    "voice_authenticity",
    "flag_accuracy",
    "legal_element_coverage",
)

DEFAULT_MIN_SCORE = 4
DEFAULT_FAITHFULNESS_MIN = 4.5
