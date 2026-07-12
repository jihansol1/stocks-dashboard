"""Ingestion pipeline: fetch a recent news window, dedupe by url, store.

AI enrichment (summary + sentiment) is added at this point in Phase 5; until
then rows are cached with null summary/sentiment.
"""

import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from . import finnhub_client

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
    """Fetch recent news for one ticker and store new articles.

    Inserts are idempotent on url (INSERT OR IGNORE against the UNIQUE
    constraint). A bad individual item is logged and skipped, never fatal.
    Returns {"fetched": n, "inserted": n}.
    """
    today = datetime.now(tz=UTC).date()
    from_date = (today - timedelta(days=window_days)).isoformat()
    to_date = today.isoformat()

    items = finnhub_client.company_news(ticker, from_date, to_date)

    inserted = 0
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
            inserted += cur.rowcount
        except sqlite3.Error:
            logger.exception("Failed to store article for %s: %s", ticker, item.get("url"))
    conn.commit()

    return {"fetched": len(items), "inserted": inserted}
