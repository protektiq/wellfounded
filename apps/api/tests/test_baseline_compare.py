"""Tests for evals.baseline_compare mean-score regression guard."""

import json
from pathlib import Path
from typing import Any

import pytest

from evals.baseline_compare import _mean_score, main


def _manifest(
    scores: list[float | None],
    errors: list[str | None] | None = None,
) -> dict[str, Any]:
    errors = errors or [None] * len(scores)
    fixtures = []
    for i, (sc, err) in enumerate(zip(scores, errors, strict=True)):
        row: dict[str, Any] = {
            "fixture_id": f"f{i}",
            "fixture_path": f"{i}.json",
            "scorer": "exact_citation_match",
            "result": {"score": sc, "passed": True, "details": {}, "error": err},
            "latency_ms": 0,
        }
        fixtures.append(row)
    return {"fixtures": fixtures}


def test_mean_score_simple() -> None:
    assert _mean_score(_manifest([1.0, 0.5])) == pytest.approx(0.75)


def test_mean_score_rejects_fixture_error() -> None:
    with pytest.raises(ValueError, match="has error"):
        _mean_score(_manifest([1.0], errors=["bad"]))


def test_mean_score_rejects_null_score() -> None:
    with pytest.raises(ValueError, match="null score"):
        _mean_score(_manifest([None]))


def test_main_passes_when_above_floor(tmp_path: Path) -> None:
    base = tmp_path / "b.json"
    cur = tmp_path / "c.json"
    base.write_text(json.dumps(_manifest([1.0, 1.0])), encoding="utf-8")
    cur.write_text(json.dumps(_manifest([0.99, 0.99])), encoding="utf-8")
    assert main([str(base), str(cur), "--max-drop", "0.02"]) == 0


def test_main_fails_on_regression(tmp_path: Path) -> None:
    base = tmp_path / "b.json"
    cur = tmp_path / "c.json"
    base.write_text(json.dumps(_manifest([1.0, 1.0])), encoding="utf-8")
    cur.write_text(json.dumps(_manifest([0.97, 0.97])), encoding="utf-8")
    assert main([str(base), str(cur), "--max-drop", "0.02"]) == 1


def test_main_accepts_path_objects(tmp_path: Path) -> None:
    base = tmp_path / "b.json"
    cur = tmp_path / "c.json"
    base.write_text(json.dumps(_manifest([1.0])), encoding="utf-8")
    cur.write_text(json.dumps(_manifest([1.0])), encoding="utf-8")
    assert main([str(base), str(cur)]) == 0
