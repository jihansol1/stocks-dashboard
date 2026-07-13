"""Refresh logic: the morning (new market day) refresh that fans out over the
watchlist, and the on-demand per-ticker refresh with a TTL guard. Both use the
same per-ticker fetch.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from . import ingest

logger = logging.getLogger(__name__)

# Skip the external call if this ticker was fetched more recently than this,
# so repeated update-button clicks don't drain Finnhub quota.
REFRESH_TTL_SECONDS = 180

# "New market day" flips at midnight in the market's timezone, not the user's.
MARKET_TZ = ZoneInfo("America/New_York")

LAST_REFRESHED_KEY = "last_refreshed_date"

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


def market_today() -> str:
    return datetime.now(MARKET_TZ).date().isoformat()


def refresh_all_if_new_day(conn: sqlite3.Connection) -> dict:
    """Refresh every watchlist ticker if this is the first load of a new market day.

    One ticker failing must not abort the others. The date is stamped unless
    every ticker failed, so a total Finnhub outage retries on the next load
    while a partial failure waits for tomorrow (the update button covers the
    stragglers).

    Returns {"is_new_day": bool, "refreshed": n, "failed": n}.
    """
    today = market_today()
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (LAST_REFRESHED_KEY,)
    ).fetchone()
    if row is not None and row["value"] == today:
        return {"is_new_day": False, "refreshed": 0, "failed": 0}

    tickers = [r["ticker"] for r in conn.execute("SELECT ticker FROM watchlist")]
    refreshed = failed = 0
    for ticker in tickers:
        try:
            refresh_ticker(conn, ticker)
            refreshed += 1
        except Exception:
            logger.exception("Morning refresh failed for %s", ticker)
            failed += 1

    if tickers and refreshed == 0:
        return {"is_new_day": True, "refreshed": 0, "failed": failed}

    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (LAST_REFRESHED_KEY, today),
    )
    conn.commit()
    return {"is_new_day": True, "refreshed": refreshed, "failed": failed}
