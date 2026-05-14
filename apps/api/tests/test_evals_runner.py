"""Tests for the eval harness runner and the deterministic scorers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evals.runner import UnknownScorerError, main, run_category


def _make_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    fixtures = tmp_path / "fixtures"
    results = tmp_path / "results"
    rubrics = tmp_path / "rubrics"
    for d in (fixtures, results, rubrics):
        d.mkdir()
    return fixtures, results, rubrics


def _write_fixture(category_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    category_dir.mkdir(parents=True, exist_ok=True)
    path = category_dir / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.asyncio(loop_scope="session")
async def test_empty_category_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "deadbeef")
    fixtures, _results, rubrics = _make_dirs(tmp_path)

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    assert manifest.git_sha == "deadbeef"
    assert manifest.category == "citation_faithfulness"
    assert manifest.fixtures == []
    assert manifest.runner_version == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_citation_match_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "citation_faithfulness",
        "all_in_context",
        {
            "id": "all-in-context",
            "category": "citation_faithfulness",
            "scorer": "exact_citation_match",
            "input": {
                "retrieval_context_ids": ["src.a", "src.b", "src.c"],
                "cited_source_ids": ["src.a", "src.b"],
            },
            "expected": {},
        },
    )

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    assert len(manifest.fixtures) == 1
    run = manifest.fixtures[0]
    assert run.result.score == 1.0
    assert run.result.passed is True
    assert run.result.details["orphans"] == []
    assert run.result.details["citation_score"] == 1.0
    assert run.result.error is None


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_citation_match_verification_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    claims = [
        {"claim_text": "Alpha.", "support": "supported"},
        {"claim_text": "Beta.", "support": "partially_supported"},
    ]
    _write_fixture(
        fixtures / "citation_faithfulness",
        "verify_ok",
        {
            "id": "verify-ok",
            "category": "citation_faithfulness",
            "scorer": "exact_citation_match",
            "input": {
                "retrieval_context_ids": ["p1"],
                "cited_source_ids": ["p1"],
                "verification_claims": list(claims),
            },
            "expected": {"verification_claims": list(claims)},
        },
    )

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    run = manifest.fixtures[0]
    assert run.result.score == 1.0
    assert run.result.passed is True
    assert run.result.details["citation_score"] == 1.0
    assert run.result.details["verification_score"] == 1.0
    assert run.result.details["verification_mismatches"] == []
    assert run.result.error is None


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_citation_match_verification_fail_on_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "citation_faithfulness",
        "verify_bad_support",
        {
            "id": "verify-bad-support",
            "category": "citation_faithfulness",
            "scorer": "exact_citation_match",
            "input": {
                "retrieval_context_ids": ["p1"],
                "cited_source_ids": ["p1"],
                "verification_claims": [
                    {"claim_text": "Same claim.", "support": "unsupported"},
                ],
            },
            "expected": {
                "verification_claims": [
                    {"claim_text": "Same claim.", "support": "supported"},
                ],
            },
        },
    )

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    run = manifest.fixtures[0]
    assert run.result.score == 0.0
    assert run.result.passed is False
    assert run.result.details["verification_score"] == 0.0
    assert run.result.details["verification_mismatches"]
    assert run.result.error is None


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_citation_match_verification_requires_input_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "citation_faithfulness",
        "verify_missing_input",
        {
            "id": "verify-missing-input",
            "category": "citation_faithfulness",
            "scorer": "exact_citation_match",
            "input": {
                "retrieval_context_ids": ["p1"],
                "cited_source_ids": ["p1"],
            },
            "expected": {
                "verification_claims": [
                    {"claim_text": "Only expected.", "support": "supported"},
                ],
            },
        },
    )

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    run = manifest.fixtures[0]
    assert run.result.error is not None
    assert "input.verification_claims" in (run.result.error or "")
    assert run.result.score is None


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_citation_match_fail_on_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "citation_faithfulness",
        "orphan_cite",
        {
            "id": "orphan-cite",
            "category": "citation_faithfulness",
            "scorer": "exact_citation_match",
            "input": {
                "retrieval_context_ids": ["src.a"],
                "cited_source_ids": ["src.a", "src.hallucinated"],
            },
            "expected": {},
        },
    )

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    run = manifest.fixtures[0]
    assert run.result.score == 0.5
    assert run.result.passed is False
    assert "src.hallucinated" in run.result.details["orphans"]


@pytest.mark.asyncio(loop_scope="session")
async def test_wer_known_corpus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "transcription_wer",
        "fox",
        {
            "id": "fox",
            "category": "transcription_wer",
            "scorer": "wer",
            "input": {
                "reference": "the quick brown fox",
                "hypothesis": "the quick brown dog",
            },
            "expected": {"max_wer": 0.5},
        },
    )

    manifest = await run_category(
        category="transcription_wer",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    run = manifest.fixtures[0]
    assert run.result.score == pytest.approx(0.75)
    assert run.result.passed is True
    assert run.result.details["wer"] == pytest.approx(0.25)


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_rejects_unknown_scorer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "citation_faithfulness",
        "typo",
        {
            "id": "typo",
            "category": "citation_faithfulness",
            "scorer": "exact_citation_mach",
            "input": {"retrieval_context_ids": [], "cited_source_ids": []},
            "expected": {},
        },
    )

    with pytest.raises(UnknownScorerError):
        await run_category(
            category="citation_faithfulness",
            fixtures_root=fixtures,
            rubrics_root=rubrics,
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_records_malformed_fixture_as_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, _results, rubrics = _make_dirs(tmp_path)
    cat = fixtures / "citation_faithfulness"
    cat.mkdir(parents=True)
    (cat / "malformed.json").write_text("{ not valid json", encoding="utf-8")
    (cat / "missing_scorer.json").write_text(
        json.dumps({"id": "missing-scorer", "category": "citation_faithfulness"}),
        encoding="utf-8",
    )

    manifest = await run_category(
        category="citation_faithfulness",
        fixtures_root=fixtures,
        rubrics_root=rubrics,
    )

    assert len(manifest.fixtures) == 2
    for run in manifest.fixtures:
        assert run.scorer == "<invalid>"
        assert run.result.error is not None
        assert run.result.score is None
    error_text = " ".join(r.result.error or "" for r in manifest.fixtures)
    assert "invalid JSON" in error_text
    assert "scorer" in error_text


def test_main_writes_manifest_for_empty_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, results, rubrics = _make_dirs(tmp_path)
    output = results / "out.json"

    rc = main(
        [
            "--category",
            "citation_faithfulness",
            "--fixtures-root",
            str(fixtures),
            "--results-root",
            str(results),
            "--rubrics-root",
            str(rubrics),
            "--output",
            str(output),
        ],
    )

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["category"] == "citation_faithfulness"
    assert payload["fixtures"] == []
    assert payload["git_sha"] == "abc1234"


def test_main_returns_nonzero_on_unknown_scorer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, results, rubrics = _make_dirs(tmp_path)
    _write_fixture(
        fixtures / "citation_faithfulness",
        "bad",
        {
            "id": "bad",
            "category": "citation_faithfulness",
            "scorer": "made_up",
            "input": {"retrieval_context_ids": [], "cited_source_ids": []},
            "expected": {},
        },
    )

    rc = main(
        [
            "--category",
            "citation_faithfulness",
            "--fixtures-root",
            str(fixtures),
            "--results-root",
            str(results),
            "--rubrics-root",
            str(rubrics),
        ],
    )

    assert rc == 2
    captured = capsys.readouterr()
    assert "unknown scorer" in captured.err.lower()


def test_main_rejects_unknown_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    fixtures, results, rubrics = _make_dirs(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--category",
                "bogus_category",
                "--fixtures-root",
                str(fixtures),
                "--results-root",
                str(results),
                "--rubrics-root",
                str(rubrics),
            ],
        )
    assert excinfo.value.code == 2
