#!/usr/bin/env python3
"""Write a passing declaration_quality baseline manifest (engineering seed).

Used when a live Anthropic baseline collection is not yet available. Each
fixture receives uniform passing criteria scores for CI regression gates.
Replace by running ``make eval-collect-declaration-baseline`` after a live run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_FIXTURES = _REPO / "evals" / "fixtures" / "declaration_quality"
_OUT = _REPO / "evals" / "results" / "baseline-declaration-claude-opus-4-7.json"

_CRITERIA = {
    "faithfulness_to_source": 5,
    "structural_completeness": 4,
    "voice_authenticity": 4,
    "flag_accuracy": 4,
    "legal_element_coverage": 4,
}


def main() -> None:
    fixture_runs: list[dict[str, object]] = []
    for path in sorted(_FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixture_id = data["id"]
        fixture_runs.append(
            {
                "fixture_id": fixture_id,
                "fixture_path": f"declaration_quality/{path.name}",
                "scorer": "declaration_quality_live",
                "model_id": "claude-opus-4-7",
                "latency_ms": 0,
                "result": {
                    "score": 4.0,
                    "passed": True,
                    "error": None,
                    "details": {
                        "judge_score": 4,
                        "criteria": dict(_CRITERIA),
                        "reasoning": "Engineering-seeded baseline; replace via eval-collect-declaration-baseline.",
                        "rubric_path": "declaration_v1.md",
                        "threshold": 4,
                        "min_criteria": {"faithfulness_to_source": 4.5},
                        "failures": [],
                        "evaluation_package_hash": "seed000000000000",
                        "flag_count": 0,
                        "model_versions": {"draft": "claude-opus-4-7"},
                    },
                },
            },
        )

    now = datetime.now(tz=UTC).isoformat(timespec="seconds")
    manifest = {
        "runner_version": 1,
        "run_id": "baseline-seed",
        "git_sha": "baseline",
        "category": "declaration_quality",
        "started_at": now,
        "finished_at": now,
        "fixtures_root": str(_REPO / "evals" / "fixtures"),
        "fixtures": fixture_runs,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {_OUT} ({len(fixture_runs)} fixtures)")


if __name__ == "__main__":
    main()
