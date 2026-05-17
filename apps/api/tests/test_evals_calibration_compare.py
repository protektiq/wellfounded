"""Tests for practitioner calibration correlation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.calibration_compare import compare_calibration
from evals.paths import default_fixtures_root


def _write_calibration_fixture(directory: Path, fixture_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{fixture_id}.json").write_text(
        json.dumps(
            {
                "id": fixture_id,
                "category": "declaration_quality",
                "scorer": "declaration_quality_live",
                "tags": ["calibration"],
                "input": {},
                "expected": {},
            }
        ),
        encoding="utf-8",
    )


def test_calibration_compare_passes_with_perfect_correlation(
    tmp_path: Path,
) -> None:
    fixtures_root = tmp_path / "fixtures"
    category_dir = fixtures_root / "declaration_quality"
    _write_calibration_fixture(category_dir, "fixture-cal-01")
    _write_calibration_fixture(category_dir, "fixture-cal-02")

    criteria_a = {
        "faithfulness_to_source": 5,
        "structural_completeness": 4,
        "voice_authenticity": 4,
        "flag_accuracy": 4,
        "legal_element_coverage": 4,
    }
    criteria_b = {
        "faithfulness_to_source": 4,
        "structural_completeness": 3,
        "voice_authenticity": 3,
        "flag_accuracy": 3,
        "legal_element_coverage": 3,
    }
    manifest = {
        "fixtures": [
            {
                "fixture_id": "fixture-cal-01",
                "result": {"score": 4.0, "details": {"criteria": criteria_a}},
            },
            {
                "fixture_id": "fixture-cal-02",
                "result": {"score": 3.0, "details": {"criteria": criteria_b}},
            },
        ],
    }
    practitioner = {
        "fixture_scores": {
            "fixture-cal-01": dict(criteria_a),
            "fixture-cal-02": dict(criteria_b),
        },
    }
    ok, _messages = compare_calibration(
        manifest=manifest,
        practitioner=practitioner,
        fixtures_root=fixtures_root,
        category="declaration_quality",
        min_r=0.7,
    )
    assert ok is True


def test_calibration_compare_fails_when_judge_low() -> None:
    manifest = {
        "fixtures": [
            {
                "fixture_id": "ti-er-journalist-01",
                "result": {
                    "score": 2.0,
                    "details": {
                        "criteria": {
                            "faithfulness_to_source": 2,
                            "structural_completeness": 2,
                            "voice_authenticity": 2,
                            "flag_accuracy": 2,
                            "legal_element_coverage": 2,
                        },
                    },
                },
            },
        ],
    }
    practitioner = {
        "fixture_scores": {
            "ti-er-journalist-01": {
                "faithfulness_to_source": 5,
                "structural_completeness": 5,
                "voice_authenticity": 5,
                "flag_accuracy": 5,
                "legal_element_coverage": 5,
            },
        },
    }
    ok, messages = compare_calibration(
        manifest=manifest,
        practitioner=practitioner,
        fixtures_root=default_fixtures_root(),
        category="declaration_quality",
        min_r=0.7,
    )
    assert ok is False
    assert any("faithfulness_to_source" in m for m in messages)
