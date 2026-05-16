# Week 5 checkpoint — Country conditions (Task 2.8)

**Date (UTC):** 2026-05-16T15:05:15Z  
**Git ref:** `ed3e155` (`ed3e155213702e70f7976034b4126a2a80f3ac8a`) on branch `develop`  
**Environment:** local (WSL2), Postgres 16 + pgvector on `:15432`, model `claude-opus-4-7`  
**Reviewer:** automated eval + integration tests (practitioner-in-residence review deferred)

## Decision

**CONDITIONAL — practitioner review pending**

Quantitative gates for citation faithfulness are met on the golden set. Per [docs/04_mvp_prd.md](../04_mvp_prd.md) section 9.3, a full **GO** into Phase 3 (declarations) also requires a positive practitioner review of five live memos. That review was explicitly deferred for this checkpoint.

| Gate | Result |
|------|--------|
| `citation_faithfulness` mean ≥ structural expectation (1.0) | **PASS** (1.0000, 20/20) |
| `citation_faithfulness_live` mean ≥ 99% | **PASS** (1.0000, 5/5) |
| Practitioner review (5 memos) | **BLOCKED** |
| P0: cross-tenant isolation | **PASS** (automated test) |
| P0: audit trail on generation | **PASS** (automated test) |
| P0: zero hallucinated citations in last 200 internal runs | **N/A** (1 complete memo in DB; see below) |

**Rationale.** Live eval scored 100% with zero orphan citations across adversarial and supported fixtures. Deterministic structural eval scored 100%. Integration tests confirm cross-org case isolation and the full country-conditions audit action sequence. We do not yet have 200 production memo runs to validate the operational hallucination claim; the golden-set live eval plus graph-level `assert_citations_subset` enforcement are the substitute evidence for this checkpoint.

**Recommended next steps before Phase 3:**

1. Schedule practitioner-in-residence review of five end-to-end memos (diverse countries/claim bases; real retrieval, not E2E stub).
2. Commit fixes discovered during this checkpoint (ORM registration in eval/ingest CLIs; omit `temperature` for `claude-opus-4-*` in `LLMClient`).
3. Optionally refresh `evals/results/baseline-live-claude-opus-4-7.json` from the successful live run manifest below.

---

## 1. Citation faithfulness evals

### Deterministic (`citation_faithfulness`)

| Metric | Value |
|--------|-------|
| Mean score | **1.0000** |
| Fixtures passed | **20 / 20** |
| Manifest | `evals/results/ed3e155-citation_faithfulness-20260516T150320Z.json` |

### Live (`citation_faithfulness_live`) — GO/NO-GO signal

| Metric | Value |
|--------|-------|
| Mean score | **1.0000** (threshold ≥ 0.99) |
| Fixtures passed | **5 / 5** |
| Total orphan citations | **0** |
| Manifest | `evals/results/ed3e155-citation_faithfulness_live-20260516T150453Z.json` |
| Wall time | ~31 s |

#### Per-fixture live results

| Fixture | Score | Orphans | Latency (ms) | Section |
|---------|-------|---------|--------------|---------|
| `af-live-adversarial-01` | 1.0 | 0 | 6325 | state_actor_involvement |
| `er-live-adversarial-01` | 1.0 | 0 | 3930 | general_conditions |
| `hn-live-supported-01` | 1.0 | 0 | 6960 | treatment_of_group |
| `ir-live-supported-01` | 1.0 | 0 | 7811 | treatment_of_group |
| `ve-live-adversarial-01` | 1.0 | 0 | 5566 | internal_relocation |

### Baseline comparison

Compared against committed `evals/results/baseline-live-claude-opus-4-7.json`:

```
baseline_mean=1.000000 current_mean=1.000000 max_drop=0.10
```

No regression vs baseline (committed baseline was bootstrap metadata; fresh run is authoritative for this checkpoint).

---

## 2. Source library ingestion

| Metric | Before | After |
|--------|--------|-------|
| `source_documents` | 5 (ER test stubs) | **10** |
| `source_passages` | 5 | **97** |

**Ingested:** US State Dept 2024 Country Reports on Human Rights Practices for **ER, HN, VE, AF, IR** (live HTTP fetch + OpenAI embeddings).

**Note:** `make ingest` with space-separated `--countries ER HN ...` only passes `ER` to argparse; use comma-separated `--countries ER,HN,VE,AF,IR` or the ingest script will skip countries. The ingest CLI also required ORM model registration (same class of bug as eval runner) before embeddings could persist `llm_call_records`.

---

## 3. P0 property checks

### Cross-tenant isolation

```
pytest tests/test_cases_api.py::test_cases_cross_org_isolation  PASSED
```

**Gap:** No dedicated `country_conditions` cross-org API test; case-level isolation is the current automated coverage.

### Audit trail completeness

```
pytest tests/test_country_conditions_api.py  4 passed
```

Confirmed actions on successful generation (mocked LLM, real Postgres):  
`country_conditions.generate.start`, `.plan.complete`, `.retrieve.complete`, `.draft.complete`, `.verify.complete`, `.synthesize.complete`, `.generate.complete`.

Production graph calls `assert_citations_subset` at draft and verify; orphan passage IDs raise before a memo can reach `complete`.

### Last 200 internal memo runs (hallucinated citations)

| Query | Result |
|-------|--------|
| `complete` memos | **1** |
| `failed` memos | **0** |
| Failed with citation-related `error_message` | **0** |

**Conclusion:** Criterion is not statistically meaningful at current volume. Substitute: golden-set live eval (5/5, zero orphans) + structural eval (20/20) + graph citation subset assertions.

---

## 4. Practitioner review

**Status: BLOCKED (deferred)**

Five freshly generated memos were not reviewed against practitioner work product during this checkpoint.

**When unblocked**, generate memos via the workbench for:

| # | Country | Suggested claim basis |
|---|---------|------------------------|
| 1 | ER | political opinion |
| 2 | HN | religion |
| 3 | VE | particular social group |
| 4 | AF | gender |
| 5 | IR | mixed |

Use real retrieval (`COUNTRY_CONDITIONS_E2E_STUB` unset). Rubric: citation accuracy, legal framing, usability as drafting starter, unsupported claims.

---

## 5. Engineering fixes applied during checkpoint

These were required to execute live eval and ingestion locally:

1. **`apps/api/evals/runner.py`** — import ORM models before `LLMClient` persists call records.
2. **`apps/api/scripts/ingest.py`** — same ORM registration for embedding during ingest.
3. **`apps/api/llm/client.py`** — omit `temperature` for `claude-opus-4-*` models (API returns 400 if sent).

---

## 6. If this were NO-GO

Not applicable on eval scores. If practitioner review is negative after it runs, spend an additional week on retrieval/verification before declarations, per build plan Task 2.8.
