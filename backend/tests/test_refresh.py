import pytest

from app import refresh
from app.finnhub_client import FinnhubError


def _add_tickers(conn, *tickers):
    for t in tickers:
        conn.execute("INSERT INTO watchlist (ticker) VALUES (?)", (t,))
    conn.commit()


def _stamped_date(conn):
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (refresh.LAST_REFRESHED_KEY,)
    ).fetchone()
    return row["value"] if row else None


def test_new_day_refreshes_every_ticker(conn, monkeypatch):
    fetched = []

    def fake_ingest(c, ticker, window_days=7):
        fetched.append(ticker)
        return {"fetched": 1, "inserted": 1}

    monkeypatch.setattr(refresh.ingest, "ingest_news", fake_ingest)
    _add_tickers(conn, "AAPL", "MSFT")

    result = refresh.refresh_all_if_new_day(conn)

    assert result == {"is_new_day": True, "refreshed": 2, "failed": 0}
    assert sorted(fetched) == ["AAPL", "MSFT"]
    assert _stamped_date(conn) == refresh.market_today()


def test_same_day_is_a_no_op(conn, monkeypatch):
    def explode(c, ticker, window_days=7):
        raise AssertionError("should not fetch on the same market day")

    monkeypatch.setattr(refresh.ingest, "ingest_news", explode)
    _add_tickers(conn, "AAPL")
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        (refresh.LAST_REFRESHED_KEY, refresh.market_today()),
    )
    conn.commit()

    result = refresh.refresh_all_if_new_day(conn)

    assert result == {"is_new_day": False, "refreshed": 0, "failed": 0}


def test_one_failure_does_not_abort_the_rest(conn, monkeypatch):
    def flaky(c, ticker, window_days=7):
        if ticker == "AAPL":
            raise FinnhubError("boom")
        return {"fetched": 1, "inserted": 1}

    monkeypatch.setattr(refresh.ingest, "ingest_news", flaky)
    _add_tickers(conn, "AAPL", "MSFT")

    result = refresh.refresh_all_if_new_day(conn)

    assert result == {"is_new_day": True, "refreshed": 1, "failed": 1}
    assert _stamped_date(conn) == refresh.market_today()


def test_total_failure_retries_on_next_load(conn, monkeypatch):
    def down(c, ticker, window_days=7):
        raise FinnhubError("finnhub down")

    monkeypatch.setattr(refresh.ingest, "ingest_news", down)
    _add_tickers(conn, "AAPL", "MSFT")

    result = refresh.refresh_all_if_new_day(conn)

    assert result == {"is_new_day": True, "refreshed": 0, "failed": 2}
    assert _stamped_date(conn) is None  # unstamped, so the next load retries


def test_empty_watchlist_still_stamps_the_day(conn, monkeypatch):
    monkeypatch.setattr(
        refresh.ingest,
        "ingest_news",
        lambda c, t, window_days=7: pytest.fail("nothing to fetch"),
    )

    result = refresh.refresh_all_if_new_day(conn)

    assert result == {"is_new_day": True, "refreshed": 0, "failed": 0}
    assert _stamped_date(conn) == refresh.market_today()
