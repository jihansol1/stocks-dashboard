"""Refresh logic: on-demand per-ticker refresh with a TTL guard.

Phase 3 adds the morning (new market day) refresh that fans out over the
watchlist using the same per-ticker fetch.
"""

import sqlite3
from datetime import UTC, datetime

from . import ingest

# Skip the external call if this ticker was fetched more recently than this,
# so repeated update-button clicks don't drain Finnhub quota.
REFRESH_TTL_SECONDS = 180

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _last_fetch_key(ticker: str) -> str:
    return f"last_fetch:{ticker}"


def _seconds_since_last_fetch(conn: sqlite3.Connection, ticker: str) -> float | None:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (_last_fetch_key(ticker),)
    ).fetchone()
    if row is None:
        return None
    try:
        last = datetime.strptime(row["value"], _TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None
    return (datetime.now(UTC) - last).total_seconds()


def _stamp_last_fetch(conn: sqlite3.Connection, ticker: str) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (_last_fetch_key(ticker), datetime.now(UTC).strftime(_TIME_FORMAT)),
    )
    conn.commit()


def refresh_ticker(
    conn: sqlite3.Connection,
    ticker: str,
    ttl_seconds: float | None = None,
) -> dict:
    """Fetch and store recent news for one ticker unless fetched within the TTL.

    Returns {"refreshed": bool, "fetched": n, "inserted": n}; refreshed=False
    means the TTL guard served the existing cache instead of calling Finnhub.
    """
    if ttl_seconds is None:
        ttl_seconds = REFRESH_TTL_SECONDS
    elapsed = _seconds_since_last_fetch(conn, ticker)
    if elapsed is not None and elapsed < ttl_seconds:
        return {"refreshed": False, "fetched": 0, "inserted": 0}

    stats = ingest.ingest_news(conn, ticker)
    _stamp_last_fetch(conn, ticker)
    return {"refreshed": True, **stats}
