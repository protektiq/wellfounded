"""Tests for declaration baseline regression compare."""

from __future__ import annotations

import json
from pathlib import Path

from evals.declaration_baseline_compare import _criteria_means, main


def _manifest(criteria_score: int) -> dict[str, object]:
    criteria = {
        "faithfulness_to_source": criteria_score,
        "structural_completeness": criteria_score,
        "voice_authenticity": criteria_score,
        "flag_accuracy": criteria_score,
        "legal_element_coverage": criteria_score,
    }
    return {
        "fixtures": [
            {
                "fixture_id": "a",
                "result": {
                    "score": float(criteria_score),
                    "details": {"criteria": criteria},
                },
            },
            {
                "fixture_id": "b",
                "result": {
                    "score": float(criteria_score),
                    "details": {"criteria": criteria},
                },
            },
        ],
    }


def test_criteria_means() -> None:
    means = _criteria_means(_manifest(4))
    assert means["faithfulness_to_source"] == 4.0
    assert means["_overall_judge_score"] == 4.0


def test_baseline_compare_passes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    baseline.write_text(json.dumps(_manifest(5)), encoding="utf-8")
    current.write_text(json.dumps(_manifest(5)), encoding="utf-8")
    assert main([str(baseline), str(current)]) == 0


def test_baseline_compare_fails_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    baseline.write_text(json.dumps(_manifest(5)), encoding="utf-8")
    current.write_text(json.dumps(_manifest(3)), encoding="utf-8")
    assert main([str(baseline), str(current)]) == 1
