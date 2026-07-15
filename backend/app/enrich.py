"""Background AI enrichment for cached articles.

Ingestion caches articles immediately and hands the new ones here; enrichment
runs concurrently on a background thread so the API never blocks on the AI
layer. Each worker writes through its own connection, guarded by
`summary IS NULL` so nothing is ever overwritten or double-paid.
"""

import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from . import ai, db

logger = logging.getLogger(__name__)

MAX_WORKERS = 8


def schedule(ticker: str, items: list[dict]) -> None:
    """Fire-and-forget: enrich in a daemon thread and return immediately."""
    if not items:
        return
    threading.Thread(
        target=enrich_batch,
        args=(ticker, items),
        name=f"enrich-{ticker}",
        daemon=True,
    ).start()


def enrich_batch(ticker: str, items: list[dict], db_path: str | None = None) -> int:
    """Enrich items ({url, headline, snippet}) concurrently; blocks until done.

    Returns the number of articles successfully enriched. Failures are logged
    and skipped; those rows keep null summary/sentiment.
    """
    if not items:
        return 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(lambda item: _enrich_one(ticker, item, db_path), items))
    enriched = sum(results)
    logger.info("Enriched %d/%d articles for %s", enriched, len(items), ticker)
    return enriched


def _enrich_one(ticker: str, item: dict, db_path: str | None) -> bool:
    try:
        result = ai.enrich_article(ticker, item["headline"], item.get("snippet"))
    except ai.AIError as exc:
        logger.warning("AI enrichment failed for %s (%s); leaving nulls", item["url"], exc)
        return False

    conn = db.get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE articles SET summary = ?, sentiment = ?
            WHERE url = ? AND summary IS NULL
            """,
            (result["summary"], result["sentiment"], item["url"]),
        )
        conn.commit()
        return True
    except sqlite3.Error:
        logger.exception("Failed to store enrichment for %s", item["url"])
        return False
    finally:
        conn.close()
