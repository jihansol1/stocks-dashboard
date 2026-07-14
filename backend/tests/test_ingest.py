import pytest

from app import ingest
from app.ai import AIError

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
def fake_ai(monkeypatch):
    calls = []

    def fake_enrich(ticker, headline, snippet):
        calls.append(headline)
        return {"summary": f"AI summary of: {headline}", "sentiment": "bullish"}

    monkeypatch.setattr(ingest.ai, "enrich_article", fake_enrich)
    return calls


def test_ingest_stores_and_enriches_articles(conn, fake_finnhub, fake_ai):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    stats = ingest.ingest_news(conn, "AAPL")

    assert stats == {"fetched": 3, "inserted": 2, "enriched": 2}
    rows = conn.execute("SELECT * FROM articles ORDER BY url").fetchall()
    assert len(rows) == 2
    assert rows[0]["headline"] == "Apple ships new chip"
    assert rows[0]["published_at"] == "2025-07-07T14:53:20Z"
    assert rows[0]["summary"] == "AI summary of: Apple ships new chip"
    assert rows[0]["sentiment"] == "bullish"


def test_ingest_is_idempotent_and_enriches_once(conn, fake_finnhub, fake_ai):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    first = ingest.ingest_news(conn, "AAPL")
    second = ingest.ingest_news(conn, "AAPL")

    assert first == {"fetched": 3, "inserted": 2, "enriched": 2}
    assert second == {"fetched": 3, "inserted": 0, "enriched": 0}
    count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    assert count == 2
    assert len(fake_ai) == 2  # AI ran only for the first-run inserts


def test_ai_failure_degrades_to_null_fields(conn, fake_finnhub, monkeypatch):
    def broken_ai(ticker, headline, snippet):
        raise AIError("anthropic down")

    monkeypatch.setattr(ingest.ai, "enrich_article", broken_ai)
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    stats = ingest.ingest_news(conn, "AAPL")

    assert stats == {"fetched": 3, "inserted": 2, "enriched": 0}
    rows = conn.execute("SELECT summary, sentiment FROM articles").fetchall()
    assert all(r["summary"] is None and r["sentiment"] is None for r in rows)


def test_ingested_articles_are_searchable_by_ai_summary(conn, fake_finnhub, fake_ai):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")

    ingest.ingest_news(conn, "AAPL")

    def hits(q):
        return conn.execute(
            "SELECT COUNT(*) AS c FROM articles_fts WHERE articles_fts MATCH ?", (q,)
        ).fetchone()["c"]

    assert hits("chip") == 1  # headline match
    assert hits("summary") == 2  # AI summary text, synced by the update trigger
