from app import ingest

FAKE_NEWS = [
    {
        "headline": "Apple ships new chip",
        "source": "Reuters",
        "url": "http://news/1",
        "datetime": 1751900000,
        "summary": "ignored at ingest, AI fills this in Phase 5",
    },
    {
        "headline": "Apple opens new store",
        "source": "AP",
        "url": "http://news/2",
        "datetime": 1751990000,
    },
    {"headline": "No url, should be skipped", "source": "X", "datetime": 1751990001},
]


def _fake_company_news(items):
    return lambda symbol, from_date, to_date: items


def test_ingest_stores_articles(conn, monkeypatch):
    monkeypatch.setattr(ingest.finnhub_client, "company_news", _fake_company_news(FAKE_NEWS))
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    stats = ingest.ingest_news(conn, "AAPL")

    assert stats == {"fetched": 3, "inserted": 2}
    rows = conn.execute("SELECT * FROM articles ORDER BY url").fetchall()
    assert len(rows) == 2
    assert rows[0]["headline"] == "Apple ships new chip"
    assert rows[0]["published_at"] == "2025-07-07T14:53:20Z"
    assert rows[0]["summary"] is None
    assert rows[0]["sentiment"] is None


def test_ingest_is_idempotent_on_url(conn, monkeypatch):
    monkeypatch.setattr(ingest.finnhub_client, "company_news", _fake_company_news(FAKE_NEWS))
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    first = ingest.ingest_news(conn, "AAPL")
    second = ingest.ingest_news(conn, "AAPL")

    assert first["inserted"] == 2
    assert second["inserted"] == 0
    count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    assert count == 2


def test_ingested_articles_are_searchable(conn, monkeypatch):
    monkeypatch.setattr(ingest.finnhub_client, "company_news", _fake_company_news(FAKE_NEWS))
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    ingest.ingest_news(conn, "AAPL")

    hits = conn.execute(
        "SELECT COUNT(*) AS c FROM articles_fts WHERE articles_fts MATCH 'chip'"
    ).fetchone()["c"]
    assert hits == 1
