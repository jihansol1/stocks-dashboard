import pytest

from app import enrich, ingest

FAKE_NEWS = [
    {
        "headline": "Apple ships new chip",
        "source": "Reuters",
        "url": "http://news/1",
        "datetime": 1751900000,
        "summary": "Finnhub snippet used as AI input",
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


@pytest.fixture
def fake_finnhub(monkeypatch):
    monkeypatch.setattr(ingest.finnhub_client, "company_news", _fake_company_news(FAKE_NEWS))


@pytest.fixture
def scheduled(monkeypatch):
    """Capture enrichment scheduling instead of spawning background threads."""
    calls = []
    monkeypatch.setattr(ingest.enrich, "schedule", lambda ticker, items: calls.append((ticker, items)))
    return calls


def test_ingest_stores_articles_and_queues_enrichment(conn, fake_finnhub, scheduled):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    stats = ingest.ingest_news(conn, "AAPL")

    assert stats == {"fetched": 3, "inserted": 2, "queued": 2}
    rows = conn.execute("SELECT * FROM articles ORDER BY url").fetchall()
    assert len(rows) == 2
    assert rows[0]["headline"] == "Apple ships new chip"
    assert rows[0]["published_at"] == "2025-07-07T14:53:20Z"
    assert rows[0]["summary"] is None  # fills in from the background worker

    [(ticker, items)] = scheduled
    assert ticker == "AAPL"
    assert items[0] == {
        "url": "http://news/1",
        "headline": "Apple ships new chip",
        "snippet": "Finnhub snippet used as AI input",
    }
    assert items[1]["snippet"] is None


def test_ingest_is_idempotent_and_queues_once(conn, fake_finnhub, scheduled):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    first = ingest.ingest_news(conn, "AAPL")
    second = ingest.ingest_news(conn, "AAPL")

    assert first == {"fetched": 3, "inserted": 2, "queued": 2}
    assert second == {"fetched": 3, "inserted": 0, "queued": 0}
    count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    assert count == 2
    # Only the first run queued anything.
    assert [len(items) for _, items in scheduled] == [2, 0]


def test_full_pipeline_makes_ai_summaries_searchable(conn, db_file, fake_finnhub, scheduled, monkeypatch):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")
    monkeypatch.setattr(
        enrich.ai,
        "enrich_article",
        lambda ticker, headline, snippet: {
            "summary": f"AI summary of: {headline}",
            "sentiment": "bullish",
        },
    )

    ingest.ingest_news(conn, "AAPL")
    [(ticker, items)] = scheduled
    enrich.enrich_batch(ticker, items, db_path=db_file)  # run the queued work now

    def hits(q):
        return conn.execute(
            "SELECT COUNT(*) AS c FROM articles_fts WHERE articles_fts MATCH ?", (q,)
        ).fetchone()["c"]

    assert hits("chip") == 1  # headline match
    assert hits("summary") == 2  # AI summary text, synced by the update trigger
