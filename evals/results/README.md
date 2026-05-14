# evals/results

This directory holds per-run manifests written by `python -m evals.runner`.
Result files are intentionally git-ignored: they are produced on demand by
local runs and by the CI workflow `.github/workflows/evals.yml`, where each
run uploads its manifest as a build artifact. The exception is
`baseline-claude-opus-4-7.json`, a committed mean-score reference used by that
workflow for regression detection.

Use `python -m evals.view <a.json> <b.json>` to render a side-by-side diff
of two manifests on `http://127.0.0.1:8765/`.
