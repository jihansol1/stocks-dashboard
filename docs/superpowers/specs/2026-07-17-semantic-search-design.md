# Phase 7: Hybrid Semantic Search — Design

Date: 2026-07-17
Status: Approved

## Goal

Add semantic search behind the existing search bar. Conceptual queries like
"supply chain problems" should match relevant articles even when the exact words
never appear, while exact-token queries (tickers, CEO names) keep their current
FTS5 precision. The frontend and the `GET /search` response shape do not change.

## Decisions

- **Embedding provider: Voyage AI**, model `voyage-3-lite` (512 dimensions).
  Generous free tier; keeps the backend thin per the existing client
  conventions. Key in `VOYAGE_API_KEY` (env / `backend/.env`, never committed).
- **Search mode: hybrid.** FTS5 and vector KNN both run; results merge via
  reciprocal rank fusion (RRF).
- **Vector store: sqlite-vec.** Vectors live in a `vec0` virtual table inside
  the existing SQLite database, next to the FTS5 table.
- **Retention: 90-day prune** added to the morning refresh. 90 days is safely
  beyond the 7-day fetch window, so pruned articles are never re-fetched and
  re-paid (dedupe-by-url only protects rows that still exist).

## Components

### 1. Embedding client — `backend/app/embeddings.py` (new)

Thin module mirroring `ai.py` / `finnhub_client.py`:

- `embed_documents(texts: list[str]) -> list[list[float]]` — batched, up to 128
  texts per Voyage call, `input_type="document"`.
- `embed_query(text: str) -> list[float]` — `input_type="query"` (Voyage
  optimizes retrieval when document/query types are distinguished).
- Raises a module-level `EmbeddingError` on failure; never crashes callers.
- `VOYAGE_API_KEY` read in `config.py`. It is **not** added to
  `missing_keys()`: the app boots and runs FTS-only without it. Report its
  absence separately (log at startup) so it is discoverable.

### 2. Storage — `backend/app/db.py`

- Load the `sqlite-vec` extension in `get_connection()`.
- New virtual table:
  `CREATE VIRTUAL TABLE IF NOT EXISTS article_vectors USING vec0(article_id INTEGER PRIMARY KEY, embedding float[512])`.
- `vec0` tables do not fire triggers; any code path that deletes from
  `articles` must delete matching `article_vectors` rows explicitly
  (stock removal via cascade, and the new prune).

### 3. Ingestion — extend `backend/app/enrich.py`

- After `enrich_batch` completes a batch, make one batched
  `embed_documents` call for the batch's articles and insert vectors.
- Embedding text per article: `headline + " " + summary`; headline alone if AI
  enrichment failed for that article.
- Guarded by "no vector row exists for this article id" so nothing is
  double-paid — same idempotence convention as `summary IS NULL`.
- A Voyage failure is logged and skipped; the articles stay searchable via
  FTS and are picked up by the next backfill pass.

### 4. Backfill — startup pass

On startup (same place the morning refresh check runs), find articles with no
`article_vectors` row and embed them in batches of 128. Idempotent by
construction; covers the pre-existing corpus and any past embedding failures.
Runs in the background like enrichment; never blocks the first request. Skips
silently if `VOYAGE_API_KEY` is unset.

### 5. Search — `GET /search` in `backend/app/main.py`

1. Run the existing FTS5 query, top 50.
2. `embed_query(q)`, KNN top 50 from `article_vectors` by cosine distance.
3. Merge with reciprocal rank fusion: `score(article) = Σ 1/(60 + rank_i)`
   across the two lists; sort descending, return top `limit`.
4. If the query embedding call fails (no key, network, quota), return plain
   FTS results — the search bar never breaks.

Response shape is unchanged (same columns as today), so no frontend changes.

### 6. Retention — `backend/app/refresh.py`

During the morning refresh, before fetching: delete articles whose
`published_at` (falling back to `fetched_at` when `published_at` is null) is
older than 90 days, plus explicit cleanup of orphaned `article_vectors` rows.
Existing FTS triggers handle the FTS index.

## Error handling summary

| Failure | Behavior |
| --- | --- |
| `VOYAGE_API_KEY` unset | App fully functional, FTS-only search; backfill skipped; logged at startup |
| Voyage call fails at ingestion | Logged, skipped; article searchable via FTS; retried by next backfill |
| Voyage call fails at query time | Plain FTS results returned |
| sqlite-vec extension fails to load | Startup error (hard dependency once shipped) |

## Testing

Unit tests with a fake embedding client (no network):

- RRF merge: known FTS + vector rank lists produce expected order.
- Fallback: query-embedding failure returns FTS-only results.
- Backfill: only articles missing vectors get embedded; second run is a no-op.
- Prune: articles older than 90 days deleted; matching vector rows and FTS
  entries removed; newer articles untouched.
- Ingestion: batch embedding inserts one vector per newly enriched article;
  failure leaves no vector row and does not affect summary/sentiment.

## Out of scope

- No frontend changes (same endpoint, same shape).
- No re-embedding of articles when summaries change (they don't change today).
- No ANN index tuning; brute-force KNN inside sqlite-vec is fine at this scale.
