# Wellfounded — Cursor Build Plan

**Derived from:** `04_mvp_prd.md`
**Format:** Copy-paste-ready prompts for Cursor's agent mode
**Target outcome:** Closed alpha with 3 design-partner legal aid organizations at week 12

---

## How to use this plan

This document is structured for an engineer driving Cursor's agent mode. Each task block is a complete, self-contained prompt designed to be pasted directly into Cursor with the relevant files open in context. Tasks are sequenced — later tasks depend on earlier ones — but each is scoped tightly enough that the agent can execute it in a single working session without losing the thread.

**The cardinal rules for working with Cursor on this codebase:**

1. **Always have `.cursorrules` and the relevant PRD section open in context** when starting a task. The agent has no memory between sessions; the rules file is what keeps the project coherent.
2. **One task per session.** Resist the temptation to chain tasks. Each task ends with running tests and committing. Then start a fresh session.
3. **Read the task's "before you start" section carefully.** It tells the agent which files to read first. Skipping this produces drift.
4. **Acceptance criteria are not optional.** If the agent says "done" without satisfying every criterion, push back. Do not move to the next task.
5. **Hallucinated APIs are the most common failure.** When the agent imports something that doesn't exist, ask it to verify the import path before continuing.

Every prompt is bounded with `---PROMPT START---` and `---PROMPT END---` markers. Copy everything between the markers, including the formatting.

---

## Phase 0 — Project rules and scaffolding

### Step 0.1 — Initialize the repository

Run this manually before opening Cursor:

```bash
mkdir wellfounded && cd wellfounded
git init
mkdir -p apps/web apps/api packages/shared infra/local docs evals
touch README.md .gitignore
```

Open the empty directory in Cursor.

### Step 0.2 — Create the `.cursorrules` file

Create a file at the repository root named `.cursorrules` with the contents below. This is the persistent context Cursor loads on every session. Do not skip this. The remainder of the build plan assumes these rules are in force.

```markdown
# Wellfounded — Project Rules

## What this is
Wellfounded is a vertical AI workbench for US affirmative asylum practice (I-589 filings).
The MVP scope is exactly three product surfaces: country conditions memo generation,
declaration drafting from interview audio, and the case-file primitive that holds them.
Evidence packet assembly and credibility auditing are explicitly OUT OF SCOPE for the
MVP. Do not implement them. Do not propose them. They ship in v1.1 and v1.2 respectively.

## Stack — non-negotiable
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2.
- Orchestration: LangChain + LangGraph. Use LangGraph for any multi-step flow with
  human-in-the-loop checkpoints (country conditions verification, declaration drafting).
- Database: PostgreSQL 16 with pgvector extension. No other databases.
- Frontend: Next.js 15 (app router), TypeScript strict mode, React Server Components
  where they fit, Tailwind CSS, shadcn/ui for primitives.
- Models:
  - Drafting and reasoning: Anthropic Claude via the official SDK. Default model
    string `claude-opus-4-7`. Do not change without explicit instruction.
  - Embeddings: OpenAI `text-embedding-3-large`.
  - Transcription: Whisper-large-v3 via `faster-whisper` self-hosted in MVP.
  - Translation: per-language NMT (start with NLLB-200) plus an LLM review pass.
- Storage: S3-compatible (MinIO for local dev, S3 in prod). Per-tenant envelope
  encryption with AWS KMS-issued data keys.
- Auth: passwordless magic links + WebAuthn second factor for admin roles. Use
  `lucia-auth` or a hand-rolled equivalent. Do not bring in Auth0 / Clerk.

## Architecture rules
- The system is multi-tenant from day one. Tenancy is the Organization. Cross-tenant
  data access is a P0 bug. Every query that touches a tenant-scoped table MUST filter
  by organization_id. Add this to every repository method without exception.
- The system is pseudonymous by design. No client legal name fields exist. Use a
  pseudonymous identifier ("M.A. — Eritrea"). If you find yourself about to add a
  `client_name` column, STOP and ask.
- Every state-changing API endpoint writes an entry to the audit log table. No
  exceptions. The audit log is append-only.
- Citation faithfulness is a P0 quality property. Every retrieval-grounded model
  output must use structured generation that emits citation tokens inline, and must
  pass a verification step before being returned to the user. Hallucinated citations
  are treated as P0 incidents.
- Model API calls go through a single typed wrapper (`apps/api/llm/client.py`).
  Do not call SDKs directly from feature code.

## Engineering conventions
- Type strictness: `mypy --strict` for Python, `tsc --strict --noUncheckedIndexedAccess`
  for TypeScript. New code must pass with zero errors.
- Tests: pytest for backend, vitest + Playwright for frontend. Every new endpoint
  ships with at least one integration test. Every new prompt ships with at least one
  eval case.
- Migrations: every schema change ships with a forward and backward Alembic migration.
- Secrets: never commit. Use `.env.local` for dev (gitignored), AWS Secrets Manager
  in prod.
- Logging: structured JSON via `structlog`. Every log line includes `request_id`,
  `organization_id`, `user_id` where applicable.
- No emoji in code, comments, commits, or UI text. The product tone is editorial,
  not chatty.

## What NOT to do
- Do not add features that are not in the MVP PRD section 3 (User stories).
- Do not add a `client_name`, `client_email`, or `client_phone` field anywhere.
- Do not store model API keys in the database. Environment only.
- Do not add a chatbot for clients. Out of scope.
- Do not call OpenAI / Anthropic / any model API from the frontend. Backend only.
- Do not introduce a new dependency without justification in a code comment.
- Do not generate or display emoji in any user-facing surface.
- Do not silence flagged content in declaration output. Flags are P0 product behavior.

## File layout (canonical)
```
apps/
  api/                    FastAPI backend
    main.py
    config.py
    db/                   SQLAlchemy models, session, migrations
    auth/                 Magic-link + WebAuthn
    orgs/                 Organization, user, role models
    cases/                Case file, intake, versioning
    country_conditions/   CC memo generation flow
    declarations/         Declaration drafting flow
    llm/                  Model client wrappers and prompt assets
    retrieval/            Source library, embeddings, pgvector
    transcription/        Whisper pipeline
    translation/          NMT + LLM review pipeline
    docx/                 DOCX template rendering
    audit/                Audit log writers and queries
    evals/                Eval harness
  web/                    Next.js frontend
    app/
    components/
    lib/
packages/
  shared/                 TS types matching backend Pydantic models
infra/
  local/                  docker-compose for postgres + minio + worker
docs/
  prd.md                  Copy of the MVP PRD for in-repo reference
  decisions/              ADRs
evals/
  fixtures/               Golden-set inputs
  results/                Versioned eval run outputs
```
```

Commit this file as the first commit on the repository: `chore: initial cursorrules`.

---

## Phase 1 — Foundation (weeks 1–2)

The goal of this phase is a working skeleton: a multi-tenant Postgres-backed FastAPI service with auth, organizations, audit logging, and the source library ingestion pipeline. No product features yet. By the end of week 2 the country conditions vertical can begin.

### Task 1.1 — Local development environment

---PROMPT START---

Read `.cursorrules` first.

**Objective.** Stand up a fully working local development environment for Wellfounded.

**What to build.**

1. `infra/local/docker-compose.yml` running:
   - Postgres 16 with the `pgvector` extension preinstalled (use `pgvector/pgvector:pg16`).
   - MinIO as an S3-compatible blob store with a pre-created bucket named `wellfounded-dev`.
   - A `redis:7` instance for future queue work — start it but do not yet use it.
2. `apps/api/pyproject.toml` with the dependency set committed in this task. Use Poetry. Lock to specific minor versions; do not use floating ranges.
3. `apps/api/main.py` — a minimal FastAPI app exposing `GET /health` returning `{"status": "ok", "version": <git-sha>}`.
4. `apps/api/config.py` — a Pydantic `BaseSettings` class that reads from environment with sensible local defaults. No defaults for secrets.
5. `apps/api/db/session.py` — async SQLAlchemy engine and session factory, configurable from `config.py`.
6. `apps/api/db/migrations/` — Alembic configured for async, with an empty initial migration so subsequent migrations have a baseline.
7. `apps/web/` — a fresh `npx create-next-app@latest` with TypeScript strict, Tailwind, app router, no src dir. Replace the default homepage with a minimal "Wellfounded" wordmark so we can verify the dev loop.
8. `Makefile` at repository root with targets: `up`, `down`, `db-migrate`, `db-revision`, `api`, `web`, `test`, `lint`. Running `make up && make api & make web` should bring the full stack up locally.
9. `README.md` — onboarding instructions assuming a fresh laptop with Docker, Python 3.12, and Node 22 installed.

**Dependencies to include (Python).**
fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic, pydantic-settings, structlog, httpx, anthropic, openai, langchain, langgraph, langchain-anthropic, langchain-openai, langchain-community, langchain-postgres, python-multipart, python-docx, pgvector, boto3, cryptography, pytest, pytest-asyncio, mypy, ruff.

**Acceptance criteria.**
- `make up` brings up Postgres, MinIO, Redis. `psql` into Postgres confirms `pgvector` extension is available.
- `make api` starts FastAPI; `curl localhost:8000/health` returns 200 with status ok and a git SHA.
- `make web` starts Next.js on port 3000; the homepage renders the wordmark.
- `make test` runs pytest (no tests yet, exit 0) and Next.js test runner.
- `make lint` runs `ruff check` and `mypy --strict apps/api`. Both pass.
- README contains the exact commands to clone, install, run.

**Do not yet.** Implement auth, models, or any product feature. This task is purely scaffolding.

---PROMPT END---

### Task 1.2 — Tenancy: Organization and User models

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.3 ("Case file primitive") first.

**Objective.** Implement the multi-tenant foundation: Organization and User models with role-based access.

**What to build.**

1. `apps/api/orgs/models.py` — SQLAlchemy models:
   - `Organization` (id: UUID, name: str, slug: str unique, created_at, deleted_at nullable, kms_data_key_arn nullable for future encryption work)
   - `User` (id: UUID, organization_id: FK, email: str, display_name: str, role: enum, status: enum, created_at, last_login_at nullable, deleted_at nullable). Unique on (organization_id, email).
   - Role enum: `admin`, `attorney`, `paralegal`, `student`.
   - Status enum: `invited`, `active`, `suspended`.
2. Alembic migration creating the two tables with appropriate indexes (organization_id on every tenant-scoped table from now on; index on User.email for lookup by email at login).
3. `apps/api/orgs/repository.py` — async repository class with methods `get_org_by_slug`, `create_org`, `get_user_by_email`, `create_user`, `list_users_in_org`. Every read method that returns a User MUST require an `organization_id` argument and filter by it.
4. `apps/api/orgs/schemas.py` — Pydantic v2 schemas for the API surface (request/response). Mirror in `packages/shared/types/org.ts`.
5. `apps/api/main.py` — register a router stub at `/orgs` but no public endpoints yet.
6. Tests at `apps/api/tests/test_orgs_repository.py`:
   - Create two orgs A and B, create a user in each with the same email. Confirm `get_user_by_email("alice@x.com", organization_id=A.id)` returns A's user, never B's.
   - Confirm soft-delete behavior: deleting a user marks `deleted_at` and excludes them from `list_users_in_org`.

**Acceptance criteria.**
- Migration runs cleanly forward and backward.
- All tests pass.
- `mypy --strict` passes.
- Every repository method that returns tenant-scoped data has `organization_id` in its signature. There are no exceptions to this. Do not add a "helper" that omits the org id.

**Do not yet.** Implement HTTP endpoints, auth, or login. This is the data layer only.

---PROMPT END---

### Task 1.3 — Audit logging primitive

---PROMPT START---

Read `.cursorrules` first.

**Objective.** Implement the append-only audit log that every state-changing operation will write to.

**What to build.**

1. `apps/api/audit/models.py` — `AuditLogEntry` with: id, organization_id (FK indexed), user_id (FK nullable for system events), action (str, e.g. "case.create", "memo.generate.start"), resource_type, resource_id, metadata (JSONB), created_at. The table has no UPDATE or DELETE methods in the repository — append only.
2. Alembic migration.
3. `apps/api/audit/writer.py` — `AuditWriter` class with a single method `record(action, organization_id, user_id, resource_type, resource_id, metadata=None)`. Sync interface to the async db is fine via the current session.
4. FastAPI dependency `get_audit_writer` that yields a writer bound to the current request context.
5. `apps/api/audit/middleware.py` — middleware that ensures every request has a `request_id` (generate UUID v7), attaches it to structlog context, and includes it in audit log metadata.
6. Tests at `apps/api/tests/test_audit.py`:
   - Writing an entry persists with the right org and user.
   - Reads filter by organization_id.
   - The repository has no `update` or `delete` method.

**Acceptance criteria.**
- All tests pass.
- The audit table can be queried for a given (organization_id, time range) efficiently — index on (organization_id, created_at).
- Confirm via a unit test that attempting to update an audit row raises (we will rely on this property for compliance).

---PROMPT END---

### Task 1.4 — Passwordless auth (magic link)

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 6.1 first.

**Objective.** Implement passwordless magic-link authentication for the Wellfounded API. WebAuthn second factor for admins is a follow-up task (1.5); not in scope here.

**What to build.**

1. `apps/api/auth/tokens.py` — single-use, expiring (15 min) signed magic-link tokens. Use a server-side stored token table (`MagicLinkToken`: id, user_id, organization_id, token_hash, expires_at, consumed_at nullable) rather than stateless JWT for revocability. Store only the hash; compare via constant-time comparison.
2. `apps/api/auth/sessions.py` — server-side session table (`Session`: id, user_id, organization_id, created_at, last_seen_at, revoked_at nullable, user_agent, ip_addr). Session cookies are HttpOnly, Secure, SameSite=Lax, named `wf_session`, value is the session id (UUID v7), looked up server-side on each request.
3. `apps/api/auth/email.py` — abstract `EmailSender` interface plus a `ConsoleEmailSender` for local dev that prints the magic link to stdout. The production SES adapter is a stub for now.
4. Endpoints in `apps/api/auth/routes.py`:
   - `POST /auth/magic-link` — body `{email, organization_slug}`. Always returns 204 to avoid email enumeration. Internally: if the user exists and is active, create a token and send. Audit log the request regardless.
   - `GET /auth/callback?token=...` — validates, consumes the token, creates a session, sets the cookie, redirects to the web app.
   - `POST /auth/logout` — revokes the current session.
   - `GET /auth/me` — returns current user and organization.
5. `apps/api/auth/deps.py` — FastAPI dependency `get_current_user` that reads the session cookie, loads the session, and returns the user. Raises 401 if unauthenticated. `require_role(*roles)` factory for role-gated endpoints.
6. Alembic migrations for the two new tables.
7. Tests:
   - Magic link flow end to end: request, consume, session established, /me returns the user.
   - Expired token rejected.
   - Consumed token cannot be reused.
   - Logout invalidates the session.
   - Audit entries are written for `auth.magic_link.request`, `auth.magic_link.consume`, `auth.logout`.

**Acceptance criteria.**
- All tests pass.
- The token table stores hashes, not raw tokens. Manually inspect to confirm.
- The `/auth/magic-link` endpoint always returns 204, regardless of whether the email exists.

**Do not.** Implement signup or self-service org creation. Users are provisioned by an admin in a follow-up task.

---PROMPT END---

### Task 1.5 — WebAuthn second factor for admins

---PROMPT START---

Read `.cursorrules` first. Task 1.4 must be complete.

**Objective.** Add a WebAuthn (passkey) second factor required for users with role=admin. Other roles are not required to enroll.

**What to build.**

1. `WebAuthnCredential` table linked to user (credential_id, public_key, sign_count, transports, friendly_name, created_at, last_used_at).
2. Library choice: `webauthn` Python package (PyPI) for backend verification.
3. Endpoints under `/auth/webauthn/`:
   - `POST /register/begin` — returns registration options.
   - `POST /register/finish` — verifies and stores credential.
   - `POST /authenticate/begin` — returns auth options.
   - `POST /authenticate/finish` — verifies and elevates the session to `mfa_verified=true`.
4. Session model gains `mfa_verified_at` column. Admin-only endpoints require both `get_current_user` AND `require_mfa`.
5. Frontend stubs: registration and authentication pages using `@simplewebauthn/browser`. Polish comes later; just functional.
6. Tests covering registration, authentication, and an admin-only test endpoint that returns 403 without MFA and 200 with.

**Acceptance criteria.**
- An admin user must complete WebAuthn before reaching `/orgs/admin/users`.
- Non-admin users are not prompted for WebAuthn.
- All tests pass.

---PROMPT END---

### Task 1.6 — Source library: ingestion pipeline scaffold

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.1 ("Source library at launch") first.

**Objective.** Build the framework that will ingest the country-conditions source library into pgvector. We will not yet ingest the full library; this task delivers the pipeline plus a single working source (US State Dept Country Reports).

**What to build.**

1. `apps/api/retrieval/models.py`:
   - `SourceDocument` (id, source_family enum, title, publication_date, country_codes ARRAY, url, last_verified_at, content_hash, deleted_at nullable). Source families: `state_dept_human_rights`, `uscirf`, `unhcr`, `hrc_upr`, `hrw`, `amnesty`, `freedom_house`, `cpj`, `euaa_coi`, `academic`.
   - `SourcePassage` (id, source_document_id FK, section_anchor, page_number nullable, text, embedding vector(3072), token_count, created_at). Index the embedding column with `ivfflat` or `hnsw` (use `hnsw` for v1).
2. Migrations.
3. `apps/api/retrieval/ingestion/base.py` — abstract `SourceIngester` with methods `discover()`, `fetch(doc_ref)`, `parse(raw) -> List[Passage]`, `embed(passages)`, `upsert(passages)`. Concrete ingesters subclass this.
4. `apps/api/retrieval/ingestion/state_dept.py` — concrete ingester for the State Dept Country Reports on Human Rights Practices. For MVP, hardcode the 2024 report year and three target countries (Eritrea, Honduras, Venezuela) so we have working data. Source HTML is at `https://www.state.gov/reports/2024-country-reports-on-human-rights-practices/<country>/`. Parse into passages roughly section-anchored (one passage per H2 or H3 block, with section title captured).
5. `apps/api/retrieval/embed.py` — wrapper around `openai.embeddings.create` returning vectors for batches of passages. Honor rate limits with backoff.
6. CLI script `apps/api/scripts/ingest.py` runnable as `python -m apps.api.scripts.ingest --source state_dept --year 2024 --country ER` etc.
7. Tests at `apps/api/tests/test_ingestion_state_dept.py` — use a saved HTML fixture (commit to `apps/api/tests/fixtures/state_dept_eritrea_2024.html`) so the test does not hit the network.

**Acceptance criteria.**
- Running the CLI with the fixture produces SourcePassage rows with non-null embeddings.
- A second run produces zero duplicates (idempotent on content_hash).
- A pgvector similarity query against the embedding column returns results in <100ms on the test dataset.
- Tests pass without network access.

**Do not.** Ingest more than the three test countries yet. The full ingestion pass happens in Task 2.5 once the retrieval flow exists.

---PROMPT END---

### Task 1.7 — LLM client wrapper

---PROMPT START---

Read `.cursorrules` first.

**Objective.** Build the single typed wrapper through which all model calls flow. No feature code calls model SDKs directly.

**What to build.**

1. `apps/api/llm/client.py` exposing:
   - `LLMClient` class with methods:
     - `complete(prompt: Prompt, *, max_tokens, temperature, response_schema=None) -> LLMResponse`
     - `complete_structured(prompt: Prompt, schema: type[BaseModel]) -> BaseModel`
     - `embed(texts: list[str]) -> list[list[float]]`
   - Internally dispatches to Anthropic (default) or OpenAI based on prompt metadata. Embeddings always go to OpenAI.
2. `apps/api/llm/prompts.py` — `Prompt` dataclass containing: system, user_template, variables, model_id, max_tokens default, expected_schema. Prompts are defined as module-level constants, not built ad hoc in feature code.
3. `apps/api/llm/types.py` — `LLMResponse` containing: text, model_id, usage (prompt_tokens, completion_tokens), latency_ms, request_id, raw_response (kept for audit). `LLMCallRecord` SQLAlchemy model to persist the (organization_id, user_id, prompt_id, model_id, usage, latency, redacted_input_hash, success, error). Migration included.
4. The client writes an `LLMCallRecord` for every call. Inputs are stored as a SHA-256 hash, not raw text, for compliance.
5. Retry logic: exponential backoff on 429 and 5xx, max 3 retries, with structured logging of each attempt.
6. Tests at `apps/api/tests/test_llm_client.py` using a fake transport. Cover: success path, structured generation path, retry on 429, embedding batching.

**Acceptance criteria.**
- All feature code in subsequent tasks goes through this wrapper. The agent should refuse to import `anthropic` or `openai` outside `apps/api/llm/`.
- Every model call produces an `LLMCallRecord` row.
- Tests pass without network access.

---PROMPT END---

### Task 1.8 — Eval harness skeleton

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 5.3 first.

**Objective.** Build the eval harness as part of foundation, not as an afterthought. We will accumulate cases as we ship features.

**What to build.**

1. `evals/runner.py` — discoverable eval cases as JSON files under `evals/fixtures/<category>/`. Categories: `citation_faithfulness`, `declaration_quality`, `transcription_wer`, `translation_quality`.
2. Each fixture is a JSON file: `{id, category, input, expected, scorer, tags}`.
3. Scorers are pluggable Python functions under `evals/scorers/`. Initial scorers:
   - `exact_citation_match` — checks every cited source id in output is in the retrieval context.
   - `rubric_llm_judge` — uses an LLM-as-judge with a fixed rubric stored in `evals/rubrics/`.
   - `wer` — word error rate for transcription.
4. CLI: `python -m evals.runner --category citation_faithfulness --output evals/results/<git-sha>.json`.
5. Results are written as versioned JSON: input, output, score, scorer, timestamp, model_id.
6. A simple HTML viewer at `evals/view.py` that serves a static page comparing two result files.
7. CI integration: a GitHub Actions workflow that runs the citation_faithfulness eval on every PR touching `country_conditions/` or `llm/`.

**Acceptance criteria.**
- Adding a new fixture file is the only step required to add a new eval case.
- Running the harness on an empty category exits 0.
- The HTML viewer renders side-by-side diffs of two runs.

**Do not.** Add full fixture libraries yet. Each feature task adds its own.

---PROMPT END---

---

## Phase 2 — Country conditions vertical (weeks 3–5)

By the end of week 5, an attorney in the admin UI can specify country + basis + group + timeframe, click Generate, and receive a structured memo with verified citations downloadable as DOCX.

### Task 2.1 — Case file primitive

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` sections 3 ("User stories") and 4.3 ("Case file primitive") first.

**Objective.** Implement the case-file data model that will hold all downstream artifacts.

**What to build.**

1. `apps/api/cases/models.py`:
   - `Case` (id, organization_id FK indexed, pseudonym str, country_code str, basis enum, group_description text, filing_deadline date nullable, asylum_office enum nullable, intake_notes text, created_by_user_id FK, created_at, archived_at nullable, deleted_at nullable).
   - Basis enum: `political_opinion`, `religion`, `particular_social_group`, `gender_based`, `race`, `nationality`, `mixed`.
   - `CaseAssignment` (case_id, user_id, role_on_case enum: lead_attorney, supporting_attorney, paralegal, supervised_student, created_at).
   - `CaseArtifact` (id, case_id FK, artifact_type enum: country_conditions_memo, declaration_draft, uploaded_file, interview_audio, transcript). Parent class — concrete tables join on this for type-specific fields.
2. Migrations with the constraint that `Case` cannot be created without at least one CaseAssignment of role lead_attorney (enforce in repository, not DB).
3. `apps/api/cases/repository.py` — full CRUD with `organization_id` filtering on every method.
4. `apps/api/cases/routes.py`:
   - `POST /cases` — create
   - `GET /cases` — list within current org, filterable by status
   - `GET /cases/{id}` — detail
   - `PATCH /cases/{id}` — update mutable fields
   - `POST /cases/{id}/archive` — archive
   - `POST /cases/{id}/assignments` — add/remove assignments
5. Audit entries for every state change.
6. Tests covering: creation, cross-org isolation (org A cannot see org B's cases), role permissions (paralegal cannot archive, student cannot create), soft-delete behavior.

**Acceptance criteria.**
- A user in org A querying `/cases` never sees org B's cases. Confirmed by test.
- A student cannot create a case. 403 returned.
- Every endpoint produces audit entries with the right action names.

---PROMPT END---

### Task 2.2 — Retrieval layer

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.1 ("Generation flow") first. Task 1.6 must be complete.

**Objective.** Build the retrieval layer over the source library. Given a query, return top-k passages with metadata, scoped by country and date.

**What to build.**

1. `apps/api/retrieval/search.py`:
   - `search(query: str, *, country_codes: list[str], date_after: date | None, source_families: list[str] | None, top_k: int = 20) -> list[RetrievedPassage]`
   - Implementation: embed query via `LLMClient.embed`, run pgvector cosine similarity query with the filters above. Return passages with full source metadata. **The HNSW index on `source_passages` is built on `(embedding::halfvec(3072))` — queries must use the same cast: `(embedding::halfvec(3072)) <=> ($1::halfvec(3072))`. A plain `vector` operator expression will bypass the index and full-scan the table.**
2. `RetrievedPassage` dataclass: passage_id, document_id, source_family, document_title, publication_date, url, section_anchor, text, similarity_score.
3. A reranking step (`apps/api/retrieval/rerank.py`) using a cross-encoder reranker — `BAAI/bge-reranker-large` self-hosted, or as a stub, an LLM-based rerank for MVP. Configurable via env. Default to LLM rerank in MVP to avoid GPU dependency in early dev.
4. Caching: Redis cache of (query_hash, filters) -> result_ids with 24h TTL. Cache hit must not skip rerank.
5. Tests:
   - Seed three documents from different countries; confirm country filter works.
   - Confirm date filter excludes pre-cutoff documents.
   - Confirm reranking changes the order vs. raw similarity in a constructed case where the rerank model has a clear preference.

**Acceptance criteria.**
- All tests pass.
- Retrieval latency p95 < 600ms on the test dataset.
- Tests verify the cache layer can be disabled via config.

---PROMPT END---

### Task 2.3 — Country conditions LangGraph flow

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.1 ("Generation flow", all 5 steps) first. Tasks 2.1, 2.2, and 1.7 must be complete.

**Objective.** Implement the five-step LangGraph flow that produces a country conditions memo with verified citations.

**What to build.**

1. `apps/api/country_conditions/graph.py` — LangGraph state machine:
   - State: `CountryConditionsState` (TypedDict) holding `inputs`, `outline`, `section_drafts` (dict of section_id -> draft with citations), `verified_sections`, `final_memo`, `errors`.
   - Nodes:
     - `plan` — given inputs, produce a structured outline with retrieval queries per section. Five fixed sections per PRD: general_conditions, treatment_of_group, state_actor_involvement, internal_relocation, recent_trends.
     - `retrieve` — fan out one retrieval call per section query, store results in state.
     - `draft` — for each section, draft prose using structured generation. The output schema requires every factual sentence to carry one or more citation tokens (`<cite passage_id="..."/>`). Use Anthropic's structured output via tool-use.
     - `verify` — a separate LLM pass per section that, given (section draft, retrieved passages), classifies each cited claim as `supported`, `partially_supported`, `unsupported`. Unsupported claims are rewritten or removed.
     - `synthesize` — combine verified sections, build bibliography (dedup citations, assign 1, 2, 3 indices), produce final structured memo.
   - Checkpoints: state is persisted between nodes via LangGraph's built-in checkpointer (Postgres). A flow can resume if interrupted.
2. `apps/api/country_conditions/prompts.py` — the four prompts (plan, draft, verify, synthesize) as module-level `Prompt` instances. Drafting prompt must explicitly enumerate citation rules.
3. `apps/api/country_conditions/service.py` — `CountryConditionsService.generate(case_id, inputs, requested_by_user_id)`:
   - Creates a `CountryConditionsMemo` artifact in `pending` state.
   - Kicks off the graph as a background task (use `asyncio.create_task` for MVP; revisit Celery later).
   - Returns the artifact id.
   - On graph completion, updates the artifact to `complete` with the structured output and audit-logs the operation.
4. `CountryConditionsMemo` model: id, case_id, status enum (pending, generating, complete, failed), inputs JSONB, output JSONB, version int (auto-increment per case), generated_by_user_id, generated_at, model_versions JSONB (records which model versions were used).
5. Endpoints:
   - `POST /cases/{case_id}/country-conditions` — request a generation
   - `GET /cases/{case_id}/country-conditions` — list versions
   - `GET /cases/{case_id}/country-conditions/{memo_id}` — retrieve
6. Tests including a full happy-path integration test that mocks the LLM client to return fixed outputs at each node and verifies the final memo structure.

**Acceptance criteria.**
- Generating a memo end-to-end (with mocked LLM) produces a structured memo with all five sections, each section has citations, every cited passage_id exists in the retrieval results.
- The graph state is checkpointed; killing the worker mid-flow and resuming completes successfully.
- The verify step reliably catches a planted unsupported claim in a test fixture.
- All audit entries written: `country_conditions.generate.start`, `.plan.complete`, `.retrieve.complete`, `.draft.complete`, `.verify.complete`, `.synthesize.complete`, `.generate.complete` (or `.failed`).

---PROMPT END---

### Task 2.4 — Citation faithfulness eval cases

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 5.3 first. Task 2.3 and Task 1.8 must be complete.

**Objective.** Add the first 20 eval fixtures for citation faithfulness. Without these we cannot ship country conditions in good conscience.

**What to build.**

1. 20 fixture files under `evals/fixtures/citation_faithfulness/`:
   - 10 cases where the retrieved passages fully support the expected memo claims. The fixture includes the inputs, a frozen retrieval set, and an expected score of 100% support.
   - 5 adversarial cases where the retrieval set is missing key support and the memo must NOT claim things it cannot cite. Expected: zero unsupported claims in output.
   - 5 multi-source cases where the same claim is supported by multiple passages.
2. The fixtures cover at least Eritrea, Honduras, Venezuela, Afghanistan, and Iran across the five claim bases.
3. The `exact_citation_match` scorer is updated to also check the verification step's classification matches the fixture's expected classification.
4. Running `python -m evals.runner --category citation_faithfulness` against the current `claude-opus-4-7` produces a baseline result file committed at `evals/results/baseline-claude-opus-4-7.json`.
5. CI gate: `.github/workflows/evals.yml` already exists and triggers on `country_conditions/`, `llm/`, `evals/`, and `evals/fixtures/citation_faithfulness/` path changes — do not replace it. Extend it to add a baseline comparison step: download the committed `evals/results/baseline-claude-opus-4-7.json` artifact and fail the workflow if the overall support score drops more than 2 points vs. baseline.

**Acceptance criteria.**
- Baseline eval shows ≥99% citation support on the supportive fixtures.
- Adversarial fixtures show zero hallucinated citations.
- CI gate runs and reports a clean number on the PR opened to add this task.

---PROMPT END---

### Task 2.5 — Full source library ingestion

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.1 ("Source library at launch") first. Tasks 1.6 and 2.3 must be complete.

**Objective.** Implement ingesters for the remaining source families and ingest the full launch library.

**What to build.**

1. Additional concrete ingesters under `apps/api/retrieval/ingestion/`:
   - `uscirf.py` — annual reports, 2020-2025
   - `unhcr.py` — Eligibility Guidelines and country information pages
   - `hrw.py` — country reports
   - `amnesty.py` — country reports
   - `freedom_house.py` — Freedom in the World annual reports
   - `cpj.py` — country pages and topical reports
   - `euaa_coi.py` — EUAA Country of Origin Information reports
2. For each, fixture-based tests confirming parsing extracts intended passages from real saved pages.
3. A `make ingest-all` target added to the **repo-root `Makefile`** (alongside `make api`, `make web`, etc.) that runs all ingesters in dependency order. The existing `make ingest` target accepts a single `--source` flag; `ingest-all` calls it once per source family.
4. The full launch library is sized at ~3,000 documents and ~150,000 passages — confirm the pgvector hnsw index continues to perform within SLO at this scale; if not, switch to ivfflat with appropriate lists parameter and document the decision in `docs/decisions/ADR-001-pgvector-index.md`.
5. A scheduled task (cron or simple async loop) that re-runs ingestion for living-document source families (state dept, USCIRF, freedom house) every 30 days and records the last_verified_at update.

**Acceptance criteria.**
- All ingesters have at least one fixture-based parsing test.
- Full library ingestion runs to completion in under 4 hours on local dev hardware.
- Retrieval against the full library returns top-20 results in p95 < 800ms.
- ADR-001 documents the index choice and benchmarks.

---PROMPT END---

### Task 2.6 — DOCX rendering for country conditions

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.1 ("Output format") first.

**Objective.** Render a country conditions memo as a styled DOCX file ready to attach as evidence.

**What to build.**

1. `apps/api/docx/country_conditions.py` using `python-docx`:
   - Template-driven rendering. Template lives at `apps/api/docx/templates/country_conditions.docx`, edited by hand to set fonts, margins, footer, etc. The Python code fills placeholders.
   - Header: matter caption (case pseudonym), memo title, date.
   - Body: five sections with H2 headings matching PRD structure.
   - Citations: superscript numbers in body text. Bibliography section at end with numbered entries: author/organization, title, publication date, URL, last verified date.
   - Footer on every page: "Generated by Wellfounded. Attorney review required. Not legal advice." with page number.
2. The DOCX template is committed to the repo. The template must use the editorial style language: serif (Source Serif Pro acceptable as it ships free), 11pt body, 1.15 line spacing, 1" margins.
3. Endpoint: `GET /cases/{case_id}/country-conditions/{memo_id}/export.docx` — streams the file. Audit logged.
4. Tests using python-docx to parse the generated file and assert structure (correct number of sections, bibliography has correct number of entries, every superscript has a matching bibliography number).

**Acceptance criteria.**
- A generated DOCX opens in Word and Google Docs without warnings.
- Citations are interactive in Word (footnote-style with hyperlinks back to source URLs).
- Bibliography is alphabetized by source family, then by date descending.
- Tests verify structural integrity.

---PROMPT END---

### Task 2.7 — Country conditions frontend

---PROMPT START---

Read `.cursorrules` and the design notes in `02_landing_page.html` for visual reference (warm cream paper background, Fraunces display, Public Sans body, oxblood accents).

**Before you start.** `shadcn/ui` is not yet installed in `apps/web`. Run `npx shadcn@latest init` from `apps/web` and accept the defaults (TypeScript, Tailwind CSS, app router, no `src/` dir). Do this before writing any component code.

**Objective.** Build the country conditions surface in the Next.js workbench.

**What to build.**

1. `apps/web/app/cases/[caseId]/country-conditions/page.tsx`:
   - Header showing case metadata and the country-conditions tab active.
   - Left: a form to request a new memo (country code, basis, group description, date range).
   - Right: list of versions, each clickable to open a detail view.
2. `apps/web/app/cases/[caseId]/country-conditions/[memoId]/page.tsx`:
   - Renders the memo with its five sections.
   - Inline superscript citations; clicking opens a slide-out drawer showing the cited passage in full with the source's metadata.
   - "Export DOCX" button calls the export endpoint and downloads.
   - "Generate new version" button with the form pre-filled.
3. Server components for data fetching; client components only for the citation drawer and form interaction.
4. Use shadcn/ui primitives. Tailwind. Match the cream/ink/oxblood palette from the landing page. Fraunces for headings, Public Sans for body.
5. Loading states: a real document-stack skeleton, not a generic spinner.
6. Error states: clear messaging when generation fails, with a retry button.
7. Playwright test: log in, navigate to a seeded case, request a generation (with the LLM mocked at the API layer), wait for completion, verify the memo renders with citations.

**Acceptance criteria.**
- Visual match to the brand DNA (a designer would not be embarrassed to show this).
- Clicking any citation opens the source passage in <200ms.
- Playwright test passes.

---PROMPT END---

### Task 2.8 — Country conditions checkpoint review

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 9.3 ("Decision points") first.

**Objective.** Run the week-5 decision-point review. This is not a build task — it is a checkpoint.

**What to do.**

1. Run both citation faithfulness eval categories on the latest `main`:
   - `make eval-collect-baseline` first to refresh `evals/results/baseline-live-claude-opus-4-7.json`
     (requires `make up && make db-migrate` and `ANTHROPIC_API_KEY` set).
   - `make eval-run category=citation_faithfulness` — deterministic structural check; should be 1.0.
   - `make eval-run category=citation_faithfulness_live` — live model check; this is the signal that counts.
   - Compare the live result against the committed baseline using `make eval-view`.
   - The GO/NO-GO threshold applies to `citation_faithfulness_live` mean score only.
2. Have the practitioner-in-residence review 5 freshly generated memos against their own work product. Capture qualitative notes.
3. Check that all P0 properties hold:
   - No memo has been produced with a hallucinated citation in any of the last 200 internal runs.
   - Every memo generation produces a complete audit trail.
   - Cross-tenant isolation tests still pass.
4. Make the go/no-go call on starting Phase 3:
   - GO if `citation_faithfulness_live` mean score ≥99% and practitioner review is positive.
   - NO-GO if `citation_faithfulness_live` mean score <99%; spend an additional week tightening retrieval and verification before starting declarations.

**Output.** A written checkpoint memo at `docs/checkpoints/week-5.md` documenting the decision and the data behind it.

---PROMPT END---

---

## Phase 3 — Declaration drafter (weeks 6–8)

By the end of week 8, an attorney can upload an interview audio file, receive a transcript and a flagged first-draft declaration, iterate via prompts, and export to DOCX in working or clean modes.

### Task 3.1 — Audio upload and transcription pipeline

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.2 ("Transcription") first.

**Objective.** Implement audio upload with envelope encryption and the Whisper transcription pipeline.

**What to build.**

1. `InterviewAudio` model: id, case_id FK, source_filename, source_language enum, duration_seconds, storage_key (S3), encryption_key_id (KMS), content_hash, uploaded_by_user_id, uploaded_at, transcription_status enum.
2. Supported languages enum (six at launch per PRD): `es`, `zh`, `fr`, `ht`, `ti`, `prs` (Dari).
3. Upload endpoint: `POST /cases/{case_id}/interviews` — multipart form with audio file (WAV/MP3/M4A/OGG, max 60 min, max 200 MB). Generate per-tenant data key via KMS, encrypt before storage. Store the encrypted blob in S3.
4. `apps/api/transcription/whisper.py` — wraps `faster-whisper` running on CPU in local dev. Returns segments with timestamps, language confidence, and speaker labels via VAD-based diarization (`pyannote-audio` for diarization in a future iteration; for MVP, speaker labels can be left as a single track if diarization model is unavailable).
5. `Transcript` model: id, interview_audio_id FK, source_language, segments JSONB (list of {start, end, speaker, source_text, english_text}), full_source_text, full_english_text, model_version, completed_at.
6. Translation step: for non-English source, NLLB-200 segment-level translation followed by an LLM review pass that produces the final English text per segment. The translation prompt explicitly preserves legal terminology and proper nouns.
7. Background task processing: upload returns 202 with a transcript id; the transcription runs async; client polls or subscribes to a status endpoint.
8. Tests with short fixture audio files committed to the repo (synthesized TTS samples in each supported language, under 30 seconds each).
9. WER eval fixtures: 5 reference transcriptions per supported language, scored against ground-truth.

**Acceptance criteria.**
- Audio file at rest is encrypted (verify by reading raw S3 bytes and confirming they are not the source file).
- Transcription produces segment-level output for all six supported languages.
- WER eval on the reference set is recorded and committed as baseline.
- An admin can revoke the encryption data key for a tenant, after which existing audio becomes unreadable.

---PROMPT END---

### Task 3.2 — Declaration LangGraph flow

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.2 ("Drafting flow", "Flag taxonomy", and the User stories DEC-01 through DEC-07) first. Tasks 3.1 and 1.7 must be complete.

**Objective.** Implement the four-step LangGraph flow that produces a flagged first-draft client declaration from a transcript.

**What to build.**

1. `apps/api/declarations/graph.py` — LangGraph state machine:
   - State: transcript, prior_statements (optional), case_metadata, extracted_facts, gap_analysis, inconsistency_report, draft, flags.
   - Nodes:
     - `extract` — structured extraction from transcript producing a `ClaimIntermediateRepresentation`: biographical_data, timeline_events[], identified_persecutors[], articulated_harms[], protected_ground_evidence, nexus_evidence, well_founded_fear_evidence, internal_relocation_evidence, one_year_filing_bar_facts.
     - `gap_check` — compares the IR against a checklist of required asylum claim elements (stored in `apps/api/declarations/elements.py`). Produces a list of GAP flags.
     - `inconsistency_check` — if prior statements are present, runs pairwise comparison against the extraction. Produces INCONSISTENCY flags with quoted text from both sources.
     - `draft` — produces a first-person declaration in the client's voice. Structured output requires every paragraph to be tagged with its source segments. Every sentence that goes beyond direct client statement is marked INFERENCE. Required structural sections: identity_background, past_persecution, perpetrator_motivation, well_founded_fear_future, internal_relocation, filing_bar_facts.
2. `DeclarationDraft` model: id, case_id, interview_audio_id, transcript_id, version int, status enum, draft JSONB (structured paragraphs with metadata), flags JSONB (list with type, location, content, resolution_status), prior_statement_ids[], created_by_user_id, created_at, finalized_at nullable.
3. Flag taxonomy implemented exactly per PRD: GAP, INFERENCE, INCONSISTENCY, AMBIGUITY, TRANSLATION_UNCERTAINTY. Each flag has fields: id, type, paragraph_id, span (start, end), description, suggested_resolution, status (open, resolved, deferred), resolved_by_user_id, resolved_at, resolution_note.
4. Iteration endpoint: `POST /cases/{case_id}/declarations/{draft_id}/revise` — takes a natural-language instruction and a target scope (paragraph_id or section_id). Returns a new draft version. Audit logged.
5. Tests with a synthetic transcript fixture covering Eritrean journalist scenario (mirroring the platform page demo case). Confirm:
   - GAP detected when "first incident date" is missing from extraction.
   - INCONSISTENCY detected when prior statement says "3 men" and transcript says "4 men".
   - INFERENCE flagged on any paragraph where extracted facts don't directly support the prose.
   - No flagged content is silently smoothed across revisions.

**Acceptance criteria.**
- Every flag has a suggested resolution.
- A clean-copy export endpoint rejects drafts with unresolved required flags (GAP, INFERENCE, INCONSISTENCY) with a 409 and a list of unresolved flag ids.
- Practitioner-in-residence reviews 5 generated drafts at this stage and signs off on flag quality.

---PROMPT END---

### Task 3.3 — Declaration DOCX rendering (working and clean modes)

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.2 ("Output format") first. Task 3.2 must be complete.

**Objective.** Render a declaration as DOCX in two modes: working copy (with flag annotations and inference highlighting) and clean copy (no annotations, only with all flags resolved).

**What to build.**

1. `apps/api/docx/declaration.py` with two functions:
   - `render_working_copy(draft) -> bytes` — flags rendered as Word comments anchored to spans; INFERENCE spans highlighted with a subtle background color; AMBIGUITY footnotes in margin.
   - `render_clean_copy(draft) -> bytes` — no annotations; pre-condition: all required flags (GAP, INFERENCE, INCONSISTENCY) must be in `resolved` or `deferred` status. Raises a typed error otherwise.
2. Template at `apps/api/docx/templates/declaration.docx` with: matter caption, declaration header, numbered paragraphs, signature block placeholder, footer.
3. Endpoints:
   - `GET /cases/{case_id}/declarations/{draft_id}/export.docx?mode=working`
   - `GET /cases/{case_id}/declarations/{draft_id}/export.docx?mode=clean`
4. Tests verifying:
   - Working copy parses with python-docx and contains comments at every flag location.
   - Clean copy without resolved flags returns 409 with structured error.
   - Clean copy with all flags resolved produces a DOCX with zero comments.
5. A parallel render option `?parallel=true` produces a two-column layout: source language on left, English on right, for client review before signing.

**Acceptance criteria.**
- All tests pass.
- A working-copy DOCX opens in Word with comments displayed in the comment pane.
- A clean-copy DOCX has no review marks of any kind.

---PROMPT END---

### Task 3.4 — Declaration frontend

---PROMPT START---

Read `.cursorrules` first. Task 3.2 and 3.3 must be complete.

**Before you start.** Confirm `shadcn/ui` is installed in `apps/web` (installed during Task 2.7). If for any reason it is absent, run `npx shadcn@latest init` from `apps/web` before writing component code.

**Objective.** Build the declaration surface in the Next.js workbench.

**What to build.**

1. `apps/web/app/cases/[caseId]/declarations/page.tsx` — list of drafts, with status pills (drafting, ready_for_review, flags_unresolved, finalized).
2. `apps/web/app/cases/[caseId]/declarations/new/page.tsx` — guided flow: upload audio or select prior interview, select source language, optionally upload prior statements, request first draft.
3. `apps/web/app/cases/[caseId]/declarations/[draftId]/page.tsx`:
   - Left: editable declaration text with inline flag markers (colored by severity per flag type).
   - Right: flag panel showing open flags, each with description, suggested resolution, and action buttons (Resolve, Defer, Edit, Reject).
   - Top: revision input — natural-language instruction with target-scope selector.
   - Bottom: export buttons (Working, Clean, Parallel).
4. Flag resolution UX is the critical detail: clicking a flag opens a side drawer with the source transcript segment, the prior statement (if applicable), and the suggested resolution text. The attorney can accept the suggestion verbatim, edit it, or reject the flag with a note.
5. Audio playback panel: clicking any timestamp anchor in the transcript plays the audio segment.
6. Use the same brand palette and typography as the country conditions surface.
7. Playwright test: full flow from upload through revision through clean export.

**Acceptance criteria.**
- Flag resolution UX is single-click for accept, two-click for edit.
- Clean export is greyed out when required flags remain unresolved.
- Audio segment playback works.
- Visual cohesion with the platform-page mockup (`03_platform_page.html`).

---PROMPT END---

### Task 3.5 — Declaration quality eval

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 5.3 first.

**Objective.** Establish the declaration quality eval before launch.

**What to build.**

1. Rubric stored at `evals/rubrics/declaration_v1.md`:
   - Faithfulness to source (5-point): does the draft only assert what the source supports?
   - Structural completeness (5-point): all required sections present and substantive?
   - Voice authenticity (5-point): does it read in the client's voice or is it stilted?
   - Flag accuracy (5-point): are flags placed correctly and substantively?
   - Legal element coverage (5-point): are protected ground, nexus, and well-founded fear all addressed?
2. 15 fixture cases under `evals/fixtures/declaration_quality/`:
   - 3 per supported language at MVP (Spanish, Mandarin, French, Haitian Creole, Tigrinya, Dari — but for MVP eval, prioritize Spanish, Mandarin, Tigrinya since Eritrean journalist is the canonical demo case).
   - Each fixture has a synthetic transcript and the practitioner-in-residence's gold-standard declaration for comparison.
3. LLM-as-judge scorer using the rubric, with the practitioner-in-residence's own scoring of a held-out subset as the calibration set.
4. Baseline run recorded at `evals/results/baseline-declaration-claude-opus-4-7.json`.

**Acceptance criteria.**
- Baseline rubric scores average ≥4.0 across all dimensions.
- Faithfulness specifically averages ≥4.5.
- The judge model's scores correlate with the practitioner's scores at r ≥ 0.7 on the calibration set.

---PROMPT END---

### Task 3.6 — Phase 3 checkpoint

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 9.3 ("Decision points") first.

**Objective.** Run the week-8 decision-point review.

**What to do.**

1. Run all evals (citation, declaration, WER) and compare to baselines.
2. Practitioner-in-residence reviews 5 freshly generated declarations end-to-end and reports practitioner revision time.
3. Decision:
   - GO if practitioner revision time is ≤40% of baseline (PRD target).
   - NO-GO if revision time is >40% — slip launch by 2 weeks and revise the drafting prompt and gap-detection logic.
4. Write `docs/checkpoints/week-8.md`.

---PROMPT END---

---

## Phase 4 — Workbench shell and integration (weeks 9–10)

### Task 4.1 — Global workbench shell

---PROMPT START---

Read `.cursorrules` and reference `03_platform_page.html` for the exact visual treatment.

**Before you start.** Confirm `shadcn/ui` is installed in `apps/web` (installed during Task 2.7). If for any reason it is absent, run `npx shadcn@latest init` from `apps/web` before writing component code.

**Objective.** Build the global workbench shell: left rail, case list sidebar, main content area. This replaces the per-feature pages from Phase 2 and 3 with the consolidated workbench.

**What to build.**

1. `apps/web/app/(workbench)/layout.tsx` — three-column layout:
   - Rail (60px): logo, nav icons for Cases, Country Library (read-only browser), Settings, user avatar.
   - Sidebar (280px): case list with search, filter tabs (All / Prep / Review / Filed), grouped by deadline.
   - Main: child route renders here.
2. `apps/web/app/(workbench)/cases/[caseId]/layout.tsx` — case-level shell with breadcrumb, header, tab strip (Country conditions / Declaration / I-589 form / Timeline). Note: I-589 and Timeline tabs render placeholder content; not in MVP. Evidence and Credibility audit tabs do NOT appear (they ship in v1.1 / v1.2).
3. Right rail (340px) on every case route: case spine showing status, file metadata, deadline countdown. Reuses the design from `03_platform_page.html`.
4. Keyboard shortcuts: `Cmd-K` opens case search, `Cmd-1..4` switches tabs.
5. Cohesive palette and typography across every surface. Apply the cream-paper aesthetic consistently.

**Acceptance criteria.**
- Visual cohesion with `03_platform_page.html`.
- All Phase 2 and Phase 3 features remain functional from inside the shell.
- No layout shift between tabs.

---PROMPT END---

### Task 4.2 — Versioning UX and audit trail surfacing

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 4.3 ("Case file primitive") first.

**Objective.** Surface version history and audit trail in the UI. Every artifact must be revertable.

**What to build.**

1. Version history dropdown on every artifact (country conditions memo, declaration draft) showing all versions with author, timestamp, and a short generated summary of changes.
2. Revert button — creates a new version that is a copy of the selected historical version. Audit-logged as `revert`.
3. Case-level audit log view (admin-only): chronological list of all actions on the case, filterable by user and action type.
4. Audit log entries link to the artifact version they affected.

**Acceptance criteria.**
- Reverting an artifact creates a new version (does not destroy history).
- Audit log loads in p95 < 400ms for a case with 1,000 entries.
- An admin querying the audit log via API can paginate efficiently.

---PROMPT END---

### Task 4.3 — Admin: user provisioning and org settings

---PROMPT START---

Read `.cursorrules` first.

**Objective.** Build the admin surface for provisioning users and managing org settings. Required because we have no self-service signup.

**Before you start.** Several stubs already exist from Phase 1 — read them before writing anything new:
- `apps/api/orgs/router.py` — `GET /orgs/admin/users` stub, already gated by `require_role(UserRole.admin)` and `require_mfa`.
- `apps/web/app/orgs/admin/users/page.tsx` — functional admin page stub: role check, MFA redirect, stub user list rendered from the API.
- `apps/web/app/auth/webauthn/register/page.tsx` and `authenticate/page.tsx` — WebAuthn ceremony pages.
Extend these files in-place. Do not create new routes at the same paths.

**What to build.**

1. `/admin/users` — list users in the org with role, status, last login. Admin can invite new users (sends magic link), suspend users, change roles.
2. `/admin/org` — org settings: display name, data residency region (us-east-1 only at launch but show the field), KMS data key rotation button.
3. `/admin/audit` — org-wide audit log view.
4. All admin pages require `mfa_verified` session per Task 1.5 — this gate is already enforced in the existing backend stub and frontend redirect; do not remove or weaken it.

**Acceptance criteria.**
- Inviting a user sends a magic link (verify by intercepting the email send in test).
- Suspending a user immediately invalidates their sessions.
- Non-admins cannot reach `/admin/*` (302 to /cases).

---PROMPT END---

---

## Phase 5 — Hardening and alpha (weeks 11–12)

### Task 5.1 — Security audit prep

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 6 first.

**Objective.** Prepare the system for the third-party security audit and penetration test scheduled for week 11.

**What to do.**

1. `docs/security/README.md` — security overview document covering: data flow, encryption posture, auth and session management, audit log integrity, model API contracts, incident response runbook.
2. Confirm zero-data-retention contracts are in place with Anthropic and OpenAI; document the contract effective dates.
3. Run `bandit` and `pip-audit` on the backend. Fix all findings.
4. Run `npm audit` on the frontend. Fix all findings.
5. Confirm no secrets in git history (use `gitleaks` or `trufflehog`).
6. Implement rate limiting on all auth endpoints (Redis-backed sliding window: 5 magic-link requests per email per hour, 20 callback attempts per IP per hour).
7. Implement CSRF protection on state-changing endpoints (double-submit cookie).
8. Implement strict CSP and security headers via middleware.
9. A red-team exercise prompt: pose as an attacker trying to (a) read another org's cases, (b) read raw audio files, (c) bypass MFA on admin, (d) inject a prompt that gets the model to ignore citation enforcement. For each, document the attempted attack and the system's defense.

**Acceptance criteria.**
- All security tools pass with zero high-severity findings.
- Rate limiting test confirms 6th magic-link request in an hour is 429.
- The red-team exercises produce a `docs/security/red-team-week-11.md` report.

---PROMPT END---

### Task 5.2 — Onboarding and design-partner kit

---PROMPT START---

Read `.cursorrules` first.

**Objective.** Prepare materials for the three design-partner organizations who will onboard at week 12.

**What to build.**

1. `docs/onboarding/getting-started.md` — written for a legal aid director: what is the tool, what is in scope, what is not, how to use safely, where the limits are.
2. `docs/onboarding/attorney-walkthrough.md` — step-by-step for an attorney's first case.
3. In-app onboarding: a 60-second guided tour the first time an attorney logs in (use shadcn/ui drawer + tooltip components).
4. A sandbox case seeded into every new org so attorneys can experiment without using real client data.
5. Feedback channel: an in-app "Send feedback" button that creates a ticket with the current case context attached (with explicit consent each time).

**Acceptance criteria.**
- A new attorney can complete their first generated memo within 15 minutes of receiving the magic link.
- Sandbox case is clearly labeled and isolated from real cases.

---PROMPT END---

### Task 5.3 — Alpha launch

---PROMPT START---

Read `.cursorrules` and `docs/prd.md` section 9.3 first.

**Objective.** Launch the closed alpha to three design-partner legal aid organizations.

**What to do.**

1. Provision a production environment on AWS us-east-1: VPC, RDS Postgres, ElastiCache Redis, S3 buckets, KMS key, Secrets Manager entries, ECS/Fargate for the API, Vercel or self-hosted for the web app.
2. Run the full migration suite against an empty production database.
3. Run a smoke-test playbook: register an admin, invite three attorneys, create a case, generate a country conditions memo, upload an audio file, generate a declaration, export both.
4. Pre-launch checklist:
   - All evals green vs. baseline.
   - Practitioner-in-residence sign-off on the past week's generated outputs.
   - Security audit findings all triaged and high-severity items resolved.
   - Backup and restore drill complete.
   - Incident response runbook current.
5. Onboard the three design partners over the course of week 12, in serial, with practitioner-in-residence shadowing each onboarding session.

**Acceptance criteria.**
- All three orgs have at least one attorney successfully generating memos and declarations by end of week 12.
- Zero security incidents.
- Feedback channel collecting real-world usage notes that feed back into the v1.1 plan.

---PROMPT END---

---

## Appendix A — Working with Cursor on this codebase

**Context budget management.** Cursor's agent works best when its context is dense with relevant material and sparse on irrelevant material. Before starting a task, close every editor tab not related to the task. Pin only: `.cursorrules`, the relevant PRD section, and the 2–4 files the task explicitly touches.

**When the agent hallucinates an import.** Stop. Ask: "verify that the symbol you imported exists in that package by reading the package's `__init__.py` or running `python -c 'from <package> import <symbol>'`." Do not let the agent paper over hallucinated APIs with try/except.

**When the agent wants to add a new dependency.** Push back unless the dependency is in the canonical list in `.cursorrules`. New dependencies are an architectural decision and should be made deliberately, not in the middle of a task.

**When the agent skips writing a test.** Reject the work and ask for tests. The eval harness and test suite are the only things keeping this project from drifting.

**When the agent proposes "improvements" outside scope.** Reject. Out-of-scope work in this codebase is the leading cause of MVP slippage. The PRD non-goals list is the project's most important section.

**When the agent's diff touches more than 3 files for a task that should touch 1.** Reject. Ask it to narrow.

## Appendix B — Recommended Cursor model settings

- Use the strongest available model for tasks 1.4, 1.7, 2.3, and 3.2 (these are architecturally consequential).
- Use a faster model for scaffolding tasks (1.1, 1.2, 1.3).
- Enable "Always include codebase context" for backend tasks.
- Disable auto-run for any command touching `db/migrations/` or `infra/`.

## Appendix C — Cadence

- **Daily.** End every day with a clean working tree, pushed to GitHub. No long-lived branches.
- **Weekly.** Run all evals on `main`. Compare to last week. File regressions as P0.
- **Every Friday.** Practitioner-in-residence reviews the week's outputs. The next week's prompts and prompts-tuning is informed by this review.
- **End of each phase.** Checkpoint review (`docs/checkpoints/`). Go / no-go decision documented and reviewed by the full team.

---

**End of build plan.**
