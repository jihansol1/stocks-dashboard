import sqlite3

import pytest


def test_schema_has_all_tables(conn):
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"meta", "watchlist", "articles", "articles_fts"} <= names


def test_articles_url_is_unique(conn):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")
    conn.execute(
        "INSERT INTO articles (ticker, headline, url) VALUES ('AAPL', 'h', 'http://x')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO articles (ticker, headline, url) VALUES ('AAPL', 'h2', 'http://x')"
        )


def test_deleting_watchlist_row_cascades_to_articles(conn):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")
    conn.execute(
        "INSERT INTO articles (ticker, headline, url) VALUES ('AAPL', 'h', 'http://x')"
    )
    conn.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
    count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    assert count == 0


def test_fts_stays_in_sync_through_insert_update_delete(conn):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")
    conn.execute(
        "INSERT INTO articles (ticker, headline, url) VALUES ('AAPL', 'Apple ships new chip', 'http://x')"
    )

    def hits(query):
        return conn.execute(
            "SELECT COUNT(*) AS c FROM articles_fts WHERE articles_fts MATCH ?", (query,)
        ).fetchone()["c"]

    assert hits("chip") == 1

    conn.execute("UPDATE articles SET summary = 'record quarterly revenue' WHERE url = 'http://x'")
    assert hits("revenue") == 1

    conn.execute("DELETE FROM articles WHERE url = 'http://x'")
    assert hits("chip") == 0
