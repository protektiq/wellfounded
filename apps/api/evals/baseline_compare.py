"""Compare two citation_faithfulness RunManifest JSON files by mean fixture score.

Used in CI to guard against regressions vs. a committed baseline manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _mean_score(manifest: dict[str, object]) -> float:
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("manifest.fixtures must be a list")
    scores: list[float] = []
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
        if not isinstance(score, int | float):
            raise TypeError("score must be a number")
        scores.append(float(score))
    if not scores:
        raise ValueError("no fixtures in manifest")
    return sum(scores) / len(scores)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if current mean score drops vs baseline by more than delta.",
    )
    parser.add_argument("baseline", type=Path, help="Path to baseline RunManifest JSON")
    parser.add_argument("current", type=Path, help="Path to current RunManifest JSON")
    parser.add_argument(
        "--max-drop",
        type=float,
        default=0.02,
        help="Maximum allowed drop in mean score (default 0.02 = 2 percentage points).",
    )
    args = parser.parse_args(argv)

    baseline_payload = json.loads(args.baseline.read_text(encoding="utf-8"))
    current_payload = json.loads(args.current.read_text(encoding="utf-8"))

    baseline_mean = _mean_score(baseline_payload)
    current_mean = _mean_score(current_payload)

    print(
        f"baseline_mean={baseline_mean:.6f} current_mean={current_mean:.6f} "
        f"max_drop={args.max_drop}",
    )

    if current_mean < baseline_mean - args.max_drop:
        print(
            f"error: score regressed by more than {args.max_drop} "
            f"(baseline {baseline_mean:.6f}, current {current_mean:.6f})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
