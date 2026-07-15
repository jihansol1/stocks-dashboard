# CLAUDE.md

Working title: **Stock News Dashboard** (rename to the real project name once chosen).

A single-user dashboard for tracking company news across a personal watchlist of
stock tickers, with an AI layer that summarizes and tags each article. This file is
the durable context for the project. Keep it lean: record decisions and their
rationale here so they don't get re-litigated or accidentally reversed, and keep the
evolving task detail in the Build Plan section below.

## What we're building

- User adds a stock via an "add" control by typing a ticker. The ticker is validated
  against Finnhub's symbol search; if it doesn't resolve or is already on the
  watchlist, the add is rejected. Valid tickers become a block on the main menu.
- Clicking a block opens a panel showing that stock's recent news (headline, source,
  timestamp, link, plus AI summary and sentiment tag).
- News comes from Finnhub's company-news endpoint. It refreshes automatically on the
  first load of each new market day, and on demand per stock via an "update" button.
- A search bar at the top filters the news already cached for every watchlist ticker.
- Single user. No auth, no accounts, no multi-user fan-out.

## Tech stack

- Backend: FastAPI (Python 3.11+)
- Storage: SQLite, with FTS5 for full-text search
- Frontend: React + Vite, Tailwind, shadcn/ui
- External data: Finnhub (symbol search, company news, quotes)
- AI: Anthropic Messages API (article summary + sentiment)

## Key decisions and their rationale

These are settled. Don't undo them without a reason that's written down here.

1. **News is surfaced and linked, never scraped or republished.** WSJ, Bloomberg, and
   NYT are paywalled and their terms prohibit scraping, and they have no redistribution
   API. Finnhub aggregates many outlets, tags articles by ticker, and gives us a link
   back to the original. We display the headline/source and link out. Do not add a
   scraper for any news outlet.

2. **Read path is separate from the write path.** The write path fills the `articles`
   cache (via the morning refresh and the update button). The read path (opening a
   stock panel, searching) reads only from SQLite and never calls an external API in
   the hot path. This keeps the UI fast and bounds API usage.

3. **Dedupe articles by `url`.** Both refresh triggers query a rolling recent window,
   so the same article will reappear. Inserts must be idempotent on `url`.

4. **Refresh-on-first-load, not a cron.** This is a single-user local app that isn't
   guaranteed to be running at market open, so a scheduled job would silently miss.
   Instead, on startup / first dashboard load, compare today's market date against
   `meta.last_refreshed_date`; if it's a new market day, refresh every watchlist ticker
   before rendering, then stamp the date. The update button reuses the same per-ticker
   fetch. (If this is ever deployed as an always-on service, a cron becomes viable, but
   that's out of scope for now.)

5. **AI runs at ingestion, not on view.** Summarize and tag each article once, when it
   enters the cache, and store the result on the row. Never summarize on render. This
   bounds LLM cost to the number of unique articles rather than article-views.
   Enrichment is **asynchronous**: articles are cached and the API responds
   immediately; a background worker pool (8 concurrent calls, `enrich.py`) fills in
   summary/sentiment, guarded by `summary IS NULL` so nothing is double-paid. A
   synchronous version blocked `POST /stocks` for 6+ minutes on newsy tickers.
   SQLite runs in WAL mode so background writers coexist with request reads.

6. **Search is FTS5 first, embeddings later.** v1 is SQLite FTS5 keyword search over
   cached articles. v2 (Phase 7) swaps in embeddings at ingestion and vector similarity
   behind the same search bar, which is the more defensible version but not required to
   ship.

## Data model (SQLite)

- `watchlist` — `ticker` (PK), `company_name`, `added_at`
- `articles` — `id` (PK), `ticker` (FK), `headline`, `source`, `url` (UNIQUE),
  `published_at`, `fetched_at`, `summary` (nullable), `sentiment` (nullable:
  bullish | bearish | neutral)
- `articles_fts` — FTS5 virtual table over `headline` + `summary`, kept in sync with
  `articles`
- `meta` — `key` (PK), `value`; holds `last_refreshed_date` and any other small state

Phase 7 adds an embedding column or a companion table keyed by `articles.id`.

## API endpoints (FastAPI)

- `POST /stocks` — body `{ ticker }`. Validate via Finnhub symbol search; reject
  unknown or duplicate; insert into `watchlist`; run an initial news fetch for it.
- `GET /stocks` — the main menu (watchlist rows, optionally with latest-article
  metadata for the block preview).
- `DELETE /stocks/{ticker}` — remove a block and its articles.
- `GET /stocks/{ticker}/news` — the panel; reads `articles` from the DB only.
- `POST /stocks/{ticker}/refresh` — the update button; on-demand fetch for one ticker.
  Enforce a short TTL (skip the external call and serve cache if this ticker was
  fetched within the last few minutes) so repeated clicks don't drain quota.
- `GET /search?q=` — FTS5 query across all cached articles.

## External integrations

**Finnhub**
- Symbol search: validate a ticker before adding.
- Company news: takes `symbol` plus a `from`/`to` date range. "Most recent news" =
  query a rolling window (e.g. last 7 days) and keep what's newer than what's cached.
  Both refresh triggers call this same function, just anchored to a recent `from` date.
- Free tier is generous but not unlimited; the refresh TTL above is the main guard.
- Verify exact endpoint paths and parameter names against current Finnhub docs before
  wiring; the shape above is stable but field names may differ.
- Key in `FINNHUB_API_KEY` (env, never committed).

**Anthropic Messages API**
- One call per new article at ingestion. Prompt for a short summary and a
  bullish/bearish/neutral tag; require the model to return strict JSON
  (`{ "summary": "...", "sentiment": "..." }`) with no preamble, and parse defensively.
- Use a fast, low-cost model for this (check the current model list; a Haiku-class
  model suits per-article summarization). Don't hard-code a model string without
  confirming it's current.
- Key in `ANTHROPIC_API_KEY` (env, never committed).

## Conventions

- Ingestion must be resilient: a Finnhub or Anthropic failure for one article must not
  abort the whole refresh. Log it, skip that item, keep going. Articles can be cached
  with a null summary/sentiment and enriched on a later pass.
- No secrets in the repo. All keys via env / `.env` (gitignored).
- User-facing text, including AI-generated summaries, stays plain and factual: no em
  dashes, no marketing or hype language, no invented detail beyond the source article.
- Keep functions small and the Finnhub/Anthropic clients thin and swappable, so a
  provider change touches one module.

## Commands

Adjust to the actual layout once scaffolded.

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload        # dev server
pytest                               # tests

# Frontend
cd frontend
npm install
npm run dev
```

Suggested layout:

```
/backend
  /app
    main.py            # FastAPI app + routes
    db.py              # SQLite connection + schema init
    finnhub_client.py  # symbol search + company news
    ai.py              # summary + sentiment
    ingest.py          # fetch -> dedupe -> enrich -> store
    refresh.py         # morning + on-demand refresh logic
  requirements.txt
/frontend
  /src
    ...
CLAUDE.md
```

## Build plan

Build in order; each phase should end in something runnable.

- **Phase 0 — Scaffolding.** Repo structure, FastAPI skeleton, SQLite init on startup,
  env config for both API keys, health-check route.
- **Phase 1 — Data + Finnhub.** Schema + init. Thin Finnhub client (symbol search +
  company news). Ticker validation. `ingest.py`: fetch a window, dedupe by `url`, store.
- **Phase 2 — Watchlist + news endpoints.** `POST/GET/DELETE /stocks`,
  `GET /stocks/{ticker}/news`, `POST /stocks/{ticker}/refresh` with the TTL guard.
- **Phase 3 — Morning refresh.** `last_refreshed_date` check + refresh-on-first-load
  that fans out over the watchlist.
- **Phase 4 — Search.** FTS5 table kept in sync with `articles`; `GET /search?q=`.
- **Phase 5 — AI layer.** Summary + sentiment at ingestion, stored on the row, surfaced
  in the news panel. Failures degrade gracefully to null fields.
- **Phase 6 — Frontend.** Menu of blocks, add modal, click-to-open news panel, per-stock
  update button, top search bar. Wire to the endpoints above.
- **Phase 7 — Semantic search (stretch).** Embed articles at ingestion; vector query
  behind the same search bar. This is the version worth talking about in interviews.

## Out of scope / non-goals

- No authentication, accounts, or multi-user support.
- No cron/scheduler (see decision 4).
- No buy/sell, price-target, or investment recommendations. The AI is a research and
  summarization assistant only. This is both an accuracy issue (LLMs are unreliable at
  it) and keeps the app clear of anything resembling unlicensed financial advice.
- No trading, brokerage, or portfolio-valuation features.