"""Ingestion pipeline: fetch a recent news window, dedupe by url, store,
then queue the new articles for background AI enrichment.

Caching never waits on the AI layer: the response returns as soon as rows are
stored, and summaries/sentiment fill in as the background workers finish. An
AI failure just leaves null fields for a later pass.
"""

import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from . import enrich, finnhub_client

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 7


def _to_iso(unix_seconds) -> str | None:
    try:
        return datetime.fromtimestamp(int(unix_seconds), tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (TypeError, ValueError, OSError):
        return None


def ingest_news(
    conn: sqlite3.Connection,
    ticker: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    """Fetch recent news for one ticker; store new articles and queue enrichment.

    Inserts are idempotent on url (INSERT OR IGNORE against the UNIQUE
    constraint), so enrichment is queued only for articles not already cached.
    A bad individual item is logged and skipped, never fatal.
    Returns {"fetched": n, "inserted": n, "queued": n}.
    """
    today = datetime.now(tz=UTC).date()
    from_date = (today - timedelta(days=window_days)).isoformat()
    to_date = today.isoformat()

    items = finnhub_client.company_news(ticker, from_date, to_date)

    pending: list[dict] = []
    for item in items:
        try:
            url = item.get("url")
            headline = item.get("headline")
            if not url or not headline:
                logger.warning("Skipping article without url/headline for %s", ticker)
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO articles
                    (ticker, headline, source, url, published_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticker, headline, item.get("source"), url, _to_iso(item.get("datetime"))),
            )
            if cur.rowcount:
                pending.append(
                    {"url": url, "headline": headline, "snippet": item.get("summary")}
                )
        except sqlite3.Error:
            logger.exception("Failed to store article for %s: %s", ticker, item.get("url"))
    conn.commit()  # rows must be visible before the background workers start

    enrich.schedule(ticker, pending)

    return {"fetched": len(items), "inserted": len(pending), "queued": len(pending)}
