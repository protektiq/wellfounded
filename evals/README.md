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
- `rubrics/*.md` — markdown rubrics consumed by the `rubric_llm_judge` scorer.
- `results/` — git-ignored manifests written by the runner.

Adding a new eval case is one step: drop a new JSON file under the relevant
category folder. No registration is required.
