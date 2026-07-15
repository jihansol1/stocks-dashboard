"""FastAPI app entry point and routes."""

import logging
import sqlite3
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from . import config, db, refresh
from . import finnhub_client
from .finnhub_client import FinnhubError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Stock News Dashboard", lifespan=lifespan)


def get_db():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


class StockCreate(BaseModel):
    ticker: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "missing_keys": config.missing_keys(),
    }


MAX_SYMBOL_SUGGESTIONS = 8


@lru_cache(maxsize=256)
def _symbol_suggestions(query: str) -> tuple[dict, ...]:
    # Cached per query text so typeahead keystrokes don't drain Finnhub quota.
    suggestions = []
    for item in finnhub_client.search_symbol(query):
        symbol = item.get("symbol")
        if not symbol:
            continue
        suggestions.append({"ticker": symbol, "name": item.get("description", "")})
        if len(suggestions) >= MAX_SYMBOL_SUGGESTIONS:
            break
    return tuple(suggestions)


@app.get("/symbols")
def symbol_suggestions(q: str = ""):
    """Typeahead for the add-stock input: symbol matches for a partial query."""
    q = q.strip().upper()
    if not q:
        return []
    try:
        return list(_symbol_suggestions(q))
    except FinnhubError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/stocks", status_code=201)
def add_stock(body: StockCreate, conn: sqlite3.Connection = Depends(get_db)):
    try:
        resolved = finnhub_client.resolve_ticker(body.ticker)
    except FinnhubError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if resolved is None:
        raise HTTPException(status_code=400, detail="Ticker not recognized")

    ticker = resolved["ticker"]
    exists = conn.execute(
        "SELECT 1 FROM watchlist WHERE ticker = ?", (ticker,)
    ).fetchone()
    if exists:
        raise HTTPException(status_code=409, detail="Ticker already on watchlist")

    conn.execute(
        "INSERT INTO watchlist (ticker, company_name) VALUES (?, ?)",
        (ticker, resolved["company_name"]),
    )
    conn.commit()

    # Initial news fetch. A Finnhub failure here must not undo the add; the
    # cache fills on a later refresh instead.
    try:
        news = refresh.refresh_ticker(conn, ticker)
    except FinnhubError:
        logger.exception("Initial news fetch failed for %s", ticker)
        news = {"refreshed": False, "fetched": 0, "inserted": 0, "queued": 0}

    return {"ticker": ticker, "company_name": resolved["company_name"], "news": news}


@app.get("/stocks")
def list_stocks(conn: sqlite3.Connection = Depends(get_db)):
    # First dashboard load of a new market day refreshes the whole watchlist
    # before rendering (decision 4: refresh-on-first-load, not a cron).
    refresh.refresh_all_if_new_day(conn)
    rows = conn.execute(
        """
        SELECT w.ticker, w.company_name, w.added_at,
               COUNT(a.id)          AS article_count,
               MAX(a.published_at)  AS latest_published_at
        FROM watchlist w
        LEFT JOIN articles a ON a.ticker = w.ticker
        GROUP BY w.ticker
        ORDER BY w.ticker
        """
    ).fetchall()
    return [dict(row) for row in rows]


@app.delete("/stocks/{ticker}", status_code=204)
def delete_stock(ticker: str, conn: sqlite3.Connection = Depends(get_db)):
    cur = conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticker not on watchlist")


@app.get("/stocks/{ticker}/news")
def stock_news(
    ticker: str,
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_db),
):
    ticker = ticker.upper()
    if conn.execute("SELECT 1 FROM watchlist WHERE ticker = ?", (ticker,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Ticker not on watchlist")
    rows = conn.execute(
        """
        SELECT id, ticker, headline, source, url, published_at, fetched_at,
               summary, sentiment
        FROM articles
        WHERE ticker = ?
        ORDER BY published_at DESC
        LIMIT ?
        """,
        (ticker, limit),
    ).fetchall()
    return [dict(row) for row in rows]


@app.post("/stocks/{ticker}/refresh")
def refresh_stock(ticker: str, conn: sqlite3.Connection = Depends(get_db)):
    ticker = ticker.upper()
    if conn.execute("SELECT 1 FROM watchlist WHERE ticker = ?", (ticker,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Ticker not on watchlist")
    try:
        return refresh.refresh_ticker(conn, ticker)
    except FinnhubError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _fts_match_query(user_query: str) -> str:
    # Quote each token so FTS5 operators and punctuation in user input
    # (AND, OR, quotes, parens) are matched as plain text. Tokens are
    # implicitly ANDed.
    tokens = user_query.replace('"', " ").split()
    return " ".join(f'"{token}"' for token in tokens)


@app.get("/search")
def search(q: str, limit: int = 50, conn: sqlite3.Connection = Depends(get_db)):
    match = _fts_match_query(q)
    if not match:
        raise HTTPException(status_code=400, detail="Search query is empty")
    rows = conn.execute(
        """
        SELECT a.id, a.ticker, a.headline, a.source, a.url, a.published_at,
               a.fetched_at, a.summary, a.sentiment
        FROM articles_fts
        JOIN articles a ON a.id = articles_fts.rowid
        WHERE articles_fts MATCH ?
        ORDER BY articles_fts.rank
        LIMIT ?
        """,
        (match, limit),
    ).fetchall()
    return [dict(row) for row in rows]
