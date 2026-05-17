"""Multi-dimensional regression gate for declaration_quality baselines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evals.declaration_criteria import (
    DECLARATION_CRITERION_KEYS,
    DEFAULT_FAITHFULNESS_MIN,
    DEFAULT_MIN_SCORE,
)


def _criteria_means(manifest: dict[str, object]) -> dict[str, float]:
    sums: dict[str, float] = {k: 0.0 for k in DECLARATION_CRITERION_KEYS}
    counts: dict[str, int] = {k: 0 for k in DECLARATION_CRITERION_KEYS}
    overall_scores: list[float] = []

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("manifest.fixtures must be a list")

    for row in fixtures:
        if not isinstance(row, dict):
            raise ValueError("each fixture run must be an object")
        result = row.get("result")
        if not isinstance(result, dict):
            raise ValueError("fixture run missing result object")
        err = result.get("error")
        if err is not None:
            raise ValueError(f"fixture {row.get('fixture_id')!r} has error: {err}")
        score = result.get("score")
        if score is None:
            raise ValueError(f"fixture {row.get('fixture_id')!r} has null score")
        overall_scores.append(float(score))

        details = result.get("details")
        if not isinstance(details, dict):
            continue
        criteria = details.get("criteria")
        if not isinstance(criteria, dict):
            continue
        for key in DECLARATION_CRITERION_KEYS:
            val = criteria.get(key)
            if isinstance(val, int) and val != 0:
                sums[key] += float(val)
                counts[key] += 1

    means: dict[str, float] = {}
    for key in DECLARATION_CRITERION_KEYS:
        if counts[key] == 0:
            raise ValueError(f"no scored values for criterion {key!r}")
        means[key] = sums[key] / counts[key]
    if not overall_scores:
        raise ValueError("no fixtures in manifest")
    means["_overall_judge_score"] = sum(overall_scores) / len(overall_scores)
    return means


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if declaration_quality dimension means regress vs baseline.",
    )
    parser.add_argument(
        "baseline",
        type=Path,
        help="Committed baseline RunManifest JSON",
    )
    parser.add_argument("current", type=Path, help="Current RunManifest JSON")
    parser.add_argument(
        "--max-drop",
        type=float,
        default=0.2,
        help="Maximum allowed drop per dimension vs baseline (default 0.2).",
    )
    parser.add_argument(
        "--min-dimension",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help="Absolute floor for each dimension mean (default 4.0).",
    )
    parser.add_argument(
        "--min-faithfulness",
        type=float,
        default=DEFAULT_FAITHFULNESS_MIN,
        help="Absolute floor for faithfulness mean (default 4.5).",
    )
    args = parser.parse_args(argv)

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))

    baseline_means = _criteria_means(baseline)
    current_means = _criteria_means(current)

    failed = False
    for key in DECLARATION_CRITERION_KEYS:
        b = baseline_means[key]
        c = current_means[key]
        floor = (
            args.min_faithfulness
            if key == "faithfulness_to_source"
            else args.min_dimension
        )
        print(f"{key}: baseline={b:.4f} current={c:.4f} floor={floor:.2f}")
        if c < floor:
            print(
                f"error: {key} mean {c:.4f} below absolute floor {floor:.2f}",
                file=sys.stderr,
            )
            failed = True
        if c < b - args.max_drop:
            print(
                f"error: {key} regressed by more than {args.max_drop} "
                f"(baseline {b:.4f}, current {c:.4f})",
                file=sys.stderr,
            )
            failed = True

    b_overall = baseline_means["_overall_judge_score"]
    c_overall = current_means["_overall_judge_score"]
    print(
        f"_overall_judge_score: baseline={b_overall:.4f} current={c_overall:.4f}",
    )
    if c_overall < args.min_dimension:
        print(
            f"error: overall judge mean {c_overall:.4f} below {args.min_dimension}",
            file=sys.stderr,
        )
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
