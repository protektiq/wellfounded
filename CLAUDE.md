# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Wellfounded is a vertical AI workbench for US affirmative asylum practice (I-589 filings). MVP scope: **country conditions memo generation**, **declaration drafting from interview audio**, and the **case-file primitive** that holds them. Evidence packet assembly and credibility auditing are out of scope for MVP.

## Commands

All commands run from the repo root unless otherwise noted.

```bash
make up              # Start Postgres (port 15432), MinIO (port 9000), Redis (port 16379) via Docker Compose
make down            # Stop Compose services
make db-migrate      # Run alembic upgrade head
make db-revision msg="your message"  # Create a new Alembic revision
make api             # FastAPI with hot reload on port 8000
make web             # Next.js dev server on port 3000
make test            # Run pytest (API) + vitest (web)
make test-e2e        # Playwright E2E (installs Chromium); see E2E env vars below
make lint            # Run ruff + mypy --strict on apps/api
make ingest ARGS="--source state_dept --year-from 2024 --year-to 2024 --countries ER"  # Ingest sources
make ingest-all      # Full launch-catalog ingestion (sequential)
make refresh-living-sources  # State Dept + USCIRF + Freedom House (cron)
make benchmark-retrieval ARGS="--iterations 30 --disable-cache"  # After library load
make eval-run category=citation_faithfulness   # Run eval harness for a category
make eval-view a=<a.json> b=<b.json>           # Side-by-side eval result diff
```

Run a single API test:
```bash
cd apps/api && poetry run pytest tests/test_auth_magic_link.py -k test_name
```

Run a single web test:
```bash
cd apps/web && npm test -- smoke
```

**Country conditions Playwright E2E** (requires Postgres migrated, API and web running on defaults):

Set on the **API** (for example `.env.local`): `ENVIRONMENT=local`, `E2E_MAGIC_LINK_REVEAL_ENABLED=true`, `E2E_MAGIC_LINK_SECRET=<long random>`, `COUNTRY_CONDITIONS_E2E_STUB=true`.

Set in the shell running Playwright: `export WF_E2E_MAGIC_LINK_SECRET=<same value as E2E_MAGIC_LINK_SECRET>`.

Then in separate terminals: `make api`, `make web`, and `make test-e2e` (or `cd apps/web && npm run test:e2e`). Optional: `PLAYWRIGHT_API_URL`, `PLAYWRIGHT_BASE_URL` if not using `127.0.0.1:8000` / `:3000`.

## Architecture

### Monorepo layout

```
apps/api/      FastAPI backend (Python 3.12, Poetry)
apps/web/      Next.js 15 frontend (TypeScript strict, app router)
packages/      Shared TS types matching backend Pydantic models
infra/local/   Docker Compose: Postgres 16 + pgvector, MinIO, Redis 7
evals/         Eval fixtures (evals/fixtures/) and versioned results (evals/results/)
docs/          PRD and ADRs
```

### Backend module structure (`apps/api/`)

Each feature domain is a Python package with `models.py` (SQLAlchemy ORM), `repository.py` (DB queries), `router.py`/`routes.py` (FastAPI), and `schemas.py` (Pydantic).

- **`auth/`** — Passwordless magic-link auth + WebAuthn second factor. Session cookie: `wf_session`. Key deps: `auth.deps.get_request_auth`, `require_role(*roles)`, `require_mfa`.
- **`orgs/`** — Organization and User models, role system (`UserRole.admin / practitioner`).
- **`audit/`** — Append-only `audit_log_entries` table (Postgres triggers block UPDATE/DELETE). `RequestContextMiddleware` assigns UUIDv7 `request_id` and binds it into structlog context. `AuditWriter` is injected via `get_audit_writer` dependency.
- **`llm/`** — All Anthropic and OpenAI SDK usage is confined here. `LLMClient` exposes `complete`, `complete_structured`, and `embed`; every call persists an `LLMCallRecord` row (hashed inputs, never raw text). Prompt templates are module-level `Prompt` constants in `llm/prompts.py`; use `with_variables(prompt, {...})` to bind values.
- **`retrieval/`** — `source_documents` + `source_passages` with `vector(3072)` embeddings via pgvector HNSW index on `embedding::halfvec(3072)`. Ingestion via `scripts/ingest.py`.
- **`db/`** — `Base` declarative base (all ORM models must inherit it), async session factory, Alembic config at `alembic.ini`.

### Key invariants

- **Multi-tenancy**: every query on a tenant-scoped table must filter by `organization_id`. Cross-tenant access is a P0 bug.
- **Pseudonymity**: no `client_name`, `client_email`, or `client_phone` fields exist or should be added.
- **Audit log**: every state-changing endpoint must call `AuditWriter.record`. The table is append-only.
- **LLM gateway**: never call Anthropic/OpenAI SDKs directly from feature code. Always go through `LLMClient` in `apps/api/llm/client.py`.
- **Citation faithfulness**: every retrieval-grounded output must emit structured citation tokens and pass a verification step before reaching the user. Hallucinated citations are P0.
- **Model default**: `claude-opus-4-7` (defined as `DEFAULT_CLAUDE_MODEL` in `llm/prompts.py`). Do not change without explicit instruction.

### Frontend (`apps/web/`)

Next.js 15 with React 19, TypeScript strict + `noUncheckedIndexedAccess`, Tailwind CSS 4, `@simplewebauthn/browser` for WebAuthn ceremonies. API calls go through `lib/api-base.ts`. Never call model APIs from the frontend.

> **Note**: This uses Next.js 15 which has breaking changes from prior versions. Before writing Next.js code, consult `node_modules/next/dist/docs/` for current API conventions.

### Testing

- Backend tests require Postgres running (`make up`). Fixtures in `tests/conftest.py` run `alembic upgrade head` once per session and truncate tables between tests.
- Tests use the real database (no mocking the DB layer). `api_client` fixture wires the ASGI app with an overridden DB session.
- Every new endpoint needs at least one integration test; every new prompt needs at least one eval case.

### Evals

Eval fixtures live under `evals/fixtures/<category>/*.json`. Categories: `citation_faithfulness`, `declaration_quality`, `transcription_wer`, `translation_quality`. Results are written to `evals/results/` (gitignored). The eval harness at `apps/api/evals/` routes through the same `LLMClient` as production.

### Type strictness

- Python: `mypy --strict` (excludes `db/migrations/versions/`)
- TypeScript: `tsc --strict --noUncheckedIndexedAccess`

New code must pass with zero errors in both.

### Logging

`structlog` with JSON output. Every log line should include `request_id`, `organization_id`, and `user_id` where applicable.

### Migrations

Every schema change ships with both a forward and backward Alembic migration (`make db-revision msg="..."` then edit the generated file to add the `downgrade` body).
