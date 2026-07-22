"""FastAPI app entry point and routes."""

import logging
import sqlite3
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from . import analyst, config, db, prices, refresh
from . import finnhub_client
from .analyst import AnalystError
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


class AskRequest(BaseModel):
    question: str


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
               MAX(a.published_at)  AS latest_published_at,
               SUM(CASE WHEN a.sentiment = 'bullish' THEN 1 ELSE 0 END) AS bullish_count,
               SUM(CASE WHEN a.sentiment = 'bearish' THEN 1 ELSE 0 END) AS bearish_count,
               SUM(CASE WHEN a.sentiment = 'neutral' THEN 1 ELSE 0 END) AS neutral_count
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


MAX_ASK_ARTICLES = 30


def _compile_news_context(rows: list[sqlite3.Row]) -> str:
    lines = []
    for row in rows:
        line = f"[{row['published_at'] or 'unknown date'}"
        if row["source"]:
            line += f", {row['source']}"
        line += f"] {row['headline']}"
        if row["summary"]:
            line += f" Summary: {row['summary']}"
        if row["sentiment"]:
            line += f" (sentiment: {row['sentiment']})"
        lines.append(line)
    return "\n".join(lines)


@app.post("/stocks/{ticker}/ask")
def ask_about_stock(
    ticker: str,
    body: AskRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    ticker = ticker.upper()
    if conn.execute("SELECT 1 FROM watchlist WHERE ticker = ?", (ticker,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Ticker not on watchlist")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")

    # Read path: reuses the cached articles only, never calls Finnhub
    # (decision 2 in CLAUDE.md).
    rows = conn.execute(
        """
        SELECT headline, source, url, published_at, summary, sentiment
        FROM articles
        WHERE ticker = ?
        ORDER BY published_at DESC
        LIMIT ?
        """,
        (ticker, MAX_ASK_ARTICLES),
    ).fetchall()

    if not rows:
        return {
            "ticker": ticker,
            "question": question,
            "answer": "There is no cached news for this stock yet. Try refreshing it first.",
        }

    try:
        result = analyst.analyze(question, ticker, _compile_news_context(rows))
    except AnalystError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ticker": ticker, "question": question, "answer": result["final_response"]}


@app.post("/stocks/{ticker}/refresh")
def refresh_stock(ticker: str, conn: sqlite3.Connection = Depends(get_db)):
    ticker = ticker.upper()
    if conn.execute("SELECT 1 FROM watchlist WHERE ticker = ?", (ticker,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Ticker not on watchlist")
    try:
        return refresh.refresh_ticker(conn, ticker)
    except FinnhubError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/stocks/{ticker}/prices")
def stock_prices(
    ticker: str,
    range: str = "1d",
    conn: sqlite3.Connection = Depends(get_db),
):
    """Price series for the sidebar sparkline and the chart panel."""
    ticker = ticker.upper()
    if conn.execute("SELECT 1 FROM watchlist WHERE ticker = ?", (ticker,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Ticker not on watchlist")
    if range not in prices.RANGES:
        raise HTTPException(status_code=400, detail=f"range must be one of {sorted(prices.RANGES)}")
    try:
        return prices.get_prices(ticker, range)
    except prices.PriceError as exc:
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
