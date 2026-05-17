# evals

Practitioner-facing data for the Wellfounded eval harness. The harness code
lives at `apps/api/evals/` (so the rubric LLM judge can use the same
`LLMClient` wrapper as production code); the data lives here so reviewers can
edit fixtures and rubrics without touching the API package.

Layout:

- `fixtures/<category>/*.json` — eval cases, one per file. Categories must be
  one of: `citation_faithfulness`, `declaration_quality`, `transcription_wer`,
  `translation_quality`. Each fixture is validated against
  `apps/api/evals/fixtures.py::Fixture` before scoring.
- `rubrics/*.md` — markdown rubrics consumed by LLM judges (`rubric_llm_judge`,
  `declaration_quality_live`).
- `calibration/*.json` — practitioner reference scores for judge calibration
  (declaration quality uses Pearson r on fixtures tagged `calibration`).
- `results/` — git-ignored manifests written by the runner, except committed
  baseline files listed in `results/.gitignore`.

Adding a new eval case is one step: drop a new JSON file under the relevant
category folder. No registration is required.

## Declaration quality

- Fixtures: `fixtures/declaration_quality/` (15 cases; scorer
  `declaration_quality_live` runs the declaration LangGraph then
  `evals.declaration_judge.v1`).
- Rubric: `rubrics/declaration_v1.md` (five 1–5 criteria).
- Calibration: `calibration/declaration_practitioner_scores.json` — replace
  engineering-seeded scores with practitioner-in-residence scores before launch.
- Baseline: `results/baseline-declaration-claude-opus-4-7.json` (committed).

```bash
make up && make db-migrate
make eval-run category=declaration_quality
make eval-collect-declaration-baseline   # refresh baseline after prompt changes
make eval-calibration-check            # judge vs practitioner r >= 0.7
```
