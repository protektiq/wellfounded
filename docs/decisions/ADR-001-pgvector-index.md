# ADR-001: pgvector index for `source_passages.embedding`

## Status

Accepted (2026-05-14)

## Context

The source library stores OpenAI `text-embedding-3-large` vectors as `vector(3072)` in PostgreSQL 16 with the `pgvector` extension. Similarity search uses a cosine-distance operator on a cast to `halfvec(3072)` because plain `vector(3072)` exceeds pgvector's per-index dimension limit for HNSW in this deployment.

The MVP target scale is on the order of **150,000 passages** with a product SLO of **top-20 retrieval p95 under 800 ms** (build plan). End-to-end `retrieval.passage_search.search` also performs query embedding and optional Redis caching plus reranking (`retrieval_rerank_backend`), so wall-clock latency is not identical to the ANN index alone.

## Decision

Keep the **HNSW** expression index created in Alembic revision `i1j2k3l4m5n6`:

- Index name: `ix_source_passages_embedding_hnsw`
- Definition: `USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)`
- Query pattern: `ORDER BY embedding::halfvec(3072) <=> (:query_vector)::halfvec`

**Rationale:** HNSW offers strong recall/latency tradeoffs for high-dimensional embeddings and avoids the IVFFlat training and `lists` tuning cycle that must be revisited whenever row counts move materially.

## Benchmarks (operator procedure)

1. Run `make up` and `make db-migrate`, then populate the library (`make ingest-all` or selective `make ingest`).
2. Run from `apps/api`:

   ```bash
   poetry run python -m scripts.benchmark_retrieval --iterations 50 --top-k 20 --disable-cache
   ```

3. Record hardware (CPU/RAM/disk), Postgres version, row counts in `source_passages`, `retrieval_vector_max_candidates`, `retrieval_vector_candidate_multiplier`, and `retrieval_rerank_backend`.
4. For **ANN-only** isolation, compare an `EXPLAIN (ANALYZE, BUFFERS)` statement that matches the `ORDER BY ... <=> ... LIMIT N` clause against wall-clock for full `search()`.

## Alternatives considered

- **IVFFlat** on the same `halfvec` expression: lower build cost and predictable scan cost at very large N, but requires `ANALYZE`/training after bulk load and careful `lists` selection; revisit if HNSW build time or memory becomes the limiting factor.
- **Lower-dimensional embeddings**: rejected unless the product changes embedding model policy.

## Follow-up

If step (4) shows HNSW query latency dominating total `search()` time above SLO while reranking is cheap, add a migration to switch the expression index to IVFFlat with measured `lists` and document before/after p95 in this ADR.
