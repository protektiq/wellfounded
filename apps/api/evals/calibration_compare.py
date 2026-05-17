"""Compare LLM judge scores to practitioner calibration scores (Pearson r)."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from evals.declaration_criteria import DECLARATION_CRITERION_KEYS
from evals.fixtures import Fixture
from evals.paths import default_fixtures_root


def _pearson_r(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    if xs == ys:
        return 1.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0.0 and den_y == 0.0:
        return 1.0 if xs == ys else 0.0
    if den_x == 0.0 or den_y == 0.0:
        return None
    return num / (den_x * den_y)


def _load_calibration_fixture_ids(
    fixtures_root: Path,
    *,
    category: str,
) -> set[str]:
    category_dir = fixtures_root / category
    ids: set[str] = set()
    if not category_dir.is_dir():
        return ids
    for path in sorted(category_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        fixture = Fixture.model_validate(data)
        if "calibration" in fixture.tags:
            ids.add(fixture.id)
    return ids


def _judge_criteria_from_manifest(
    manifest: dict[str, object],
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("manifest.fixtures must be a list")
    for row in fixtures:
        if not isinstance(row, dict):
            raise ValueError("each fixture run must be an object")
        fixture_id = row.get("fixture_id")
        if not isinstance(fixture_id, str):
            continue
        result = row.get("result")
        if not isinstance(result, dict):
            continue
        err = result.get("error")
        if err is not None:
            raise ValueError(f"fixture {fixture_id!r} has error: {err}")
        details = result.get("details")
        if not isinstance(details, dict):
            continue
        criteria = details.get("criteria")
        if not isinstance(criteria, dict):
            continue
        parsed: dict[str, int] = {}
        for key in DECLARATION_CRITERION_KEYS:
            val = criteria.get(key)
            if isinstance(val, int):
                parsed[key] = val
        out[fixture_id] = parsed
    return out


def compare_calibration(
    *,
    manifest: dict[str, object],
    practitioner: dict[str, object],
    fixtures_root: Path,
    category: str,
    min_r: float,
) -> tuple[bool, list[str]]:
    calibration_ids = _load_calibration_fixture_ids(fixtures_root, category=category)
    if not calibration_ids:
        return False, ["no calibration-tagged fixtures found"]

    scores_raw = practitioner.get("fixture_scores")
    if not isinstance(scores_raw, dict):
        raise ValueError("practitioner.fixture_scores must be an object")

    judge_by_fixture = _judge_criteria_from_manifest(manifest)
    messages: list[str] = []
    all_ok = True

    for criterion in DECLARATION_CRITERION_KEYS:
        xs: list[float] = []
        ys: list[float] = []
        for fixture_id in sorted(calibration_ids):
            pir_row = scores_raw.get(fixture_id)
            if not isinstance(pir_row, dict):
                messages.append(f"missing practitioner scores for {fixture_id}")
                all_ok = False
                continue
            pir_score = pir_row.get(criterion)
            judge_scores = judge_by_fixture.get(fixture_id, {})
            judge_score = judge_scores.get(criterion)
            if not isinstance(pir_score, int | float):
                messages.append(f"{fixture_id}: missing practitioner {criterion}")
                all_ok = False
                continue
            if not isinstance(judge_score, int):
                messages.append(f"{fixture_id}: missing judge {criterion}")
                all_ok = False
                continue
            if judge_score == 0:
                messages.append(f"{fixture_id}: judge {criterion} unscored (0)")
                all_ok = False
                continue
            xs.append(float(judge_score))
            ys.append(float(pir_score))

        r = _pearson_r(xs, ys)
        if r is None:
            messages.append(f"{criterion}: cannot compute r (n={len(xs)})")
            all_ok = False
        elif r < min_r:
            messages.append(f"{criterion}: r={r:.4f} < {min_r}")
            all_ok = False
        else:
            messages.append(f"{criterion}: r={r:.4f}")

    mean_xs: list[float] = []
    mean_ys: list[float] = []
    for fixture_id in sorted(calibration_ids):
        pir_row = scores_raw.get(fixture_id)
        judge_scores = judge_by_fixture.get(fixture_id, {})
        if not isinstance(pir_row, dict):
            continue
        pir_vals = [
            float(pir_row[k])
            for k in DECLARATION_CRITERION_KEYS
            if isinstance(pir_row.get(k), int | float)
        ]
        judge_vals = [
            float(judge_scores[k])
            for k in DECLARATION_CRITERION_KEYS
            if isinstance(judge_scores.get(k), int) and judge_scores[k] != 0
        ]
        if pir_vals and judge_vals and len(pir_vals) == len(judge_vals):
            mean_xs.append(sum(judge_vals) / len(judge_vals))
            mean_ys.append(sum(pir_vals) / len(pir_vals))

    mean_r = _pearson_r(mean_xs, mean_ys)
    if mean_r is None:
        messages.append("mean_across_criteria: cannot compute r")
        all_ok = False
    elif mean_r < min_r:
        messages.append(f"mean_across_criteria: r={mean_r:.4f} < {min_r}")
        all_ok = False
    else:
        messages.append(f"mean_across_criteria: r={mean_r:.4f}")

    return all_ok, messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify judge vs practitioner Pearson correlation on calibration fixtures."
        ),
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="RunManifest JSON from declaration_quality eval",
    )
    parser.add_argument(
        "practitioner",
        type=Path,
        help="Practitioner scores JSON under evals/calibration/",
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=None,
        help="Fixtures root (defaults to repo evals/fixtures).",
    )
    parser.add_argument(
        "--category",
        default="declaration_quality",
        help="Fixture category directory name.",
    )
    parser.add_argument(
        "--min-r",
        type=float,
        default=0.7,
        help="Minimum Pearson r required (default 0.7).",
    )
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    practitioner = json.loads(args.practitioner.read_text(encoding="utf-8"))
    fixtures_root = (args.fixtures_root or default_fixtures_root()).resolve()

    ok, messages = compare_calibration(
        manifest=manifest,
        practitioner=practitioner,
        fixtures_root=fixtures_root,
        category=args.category,
        min_r=args.min_r,
    )
    for line in messages:
        print(line)
    if not ok:
        print("error: calibration correlation below threshold", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
