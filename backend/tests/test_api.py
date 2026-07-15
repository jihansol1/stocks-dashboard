import pytest
from fastapi.testclient import TestClient

from app import ai, config, db, enrich, finnhub_client, main
from app.finnhub_client import FinnhubError

FAKE_NEWS = [
    {
        "headline": "Apple ships new chip",
        "source": "Reuters",
        "url": "http://news/1",
        "datetime": 1751900000,
    },
    {
        "headline": "Apple opens new store",
        "source": "AP",
        "url": "http://news/2",
        "datetime": 1751990000,
    },
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(
        finnhub_client,
        "resolve_ticker",
        lambda t: {"ticker": t.strip().upper(), "company_name": "Apple Inc"}
        if t.strip().upper() == "AAPL"
        else None,
    )
    monkeypatch.setattr(
        finnhub_client, "company_news", lambda symbol, from_date, to_date: FAKE_NEWS
    )
    monkeypatch.setattr(
        ai,
        "enrich_article",
        lambda ticker, headline, snippet: {"summary": "AI summary.", "sentiment": "neutral"},
    )
    # Run queued enrichment synchronously so tests are deterministic.
    monkeypatch.setattr(
        enrich, "schedule", lambda ticker, items: enrich.enrich_batch(ticker, items)
    )
    with TestClient(main.app) as client:
        yield client


def test_add_stock_validates_inserts_and_fetches(client):
    resp = client.post("/stocks", json={"ticker": "aapl"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["company_name"] == "Apple Inc"
    assert body["news"] == {"refreshed": True, "fetched": 2, "inserted": 2, "queued": 2}


def test_add_unknown_ticker_rejected(client):
    resp = client.post("/stocks", json={"ticker": "ZZZZZ"})
    assert resp.status_code == 400


def test_add_duplicate_rejected(client):
    client.post("/stocks", json={"ticker": "AAPL"})
    resp = client.post("/stocks", json={"ticker": "AAPL"})
    assert resp.status_code == 409


def test_add_stock_survives_news_fetch_failure(client, monkeypatch):
    def boom(symbol, from_date, to_date):
        raise FinnhubError("news down")

    monkeypatch.setattr(finnhub_client, "company_news", boom)
    resp = client.post("/stocks", json={"ticker": "AAPL"})
    assert resp.status_code == 201
    assert resp.json()["news"]["refreshed"] is False
    assert client.get("/stocks").json()[0]["ticker"] == "AAPL"


def test_finnhub_down_on_validation_returns_502(client, monkeypatch):
    def boom(ticker):
        raise FinnhubError("finnhub down")

    monkeypatch.setattr(finnhub_client, "resolve_ticker", boom)
    resp = client.post("/stocks", json={"ticker": "AAPL"})
    assert resp.status_code == 502


def test_list_stocks(client):
    client.post("/stocks", json={"ticker": "AAPL"})
    resp = client.get("/stocks")
    assert resp.status_code == 200
    [row] = resp.json()
    assert row["ticker"] == "AAPL"
    assert row["company_name"] == "Apple Inc"
    assert row["article_count"] == 2
    assert row["latest_published_at"] == "2025-07-08T15:53:20Z"
    assert row["neutral_count"] == 2  # fixture AI tags everything neutral
    assert row["bullish_count"] == 0


def test_stock_news_reads_from_cache(client):
    client.post("/stocks", json={"ticker": "AAPL"})
    resp = client.get("/stocks/aapl/news")
    assert resp.status_code == 200
    articles = resp.json()
    assert len(articles) == 2
    assert articles[0]["headline"] == "Apple opens new store"  # newest first
    assert articles[0]["summary"] == "AI summary."
    assert articles[0]["sentiment"] == "neutral"


def test_stock_news_unknown_ticker_404(client):
    assert client.get("/stocks/MSFT/news").status_code == 404


def test_delete_stock_removes_articles(client):
    client.post("/stocks", json={"ticker": "AAPL"})
    assert client.delete("/stocks/AAPL").status_code == 204
    assert client.get("/stocks").json() == []
    assert client.get("/stocks/AAPL/news").status_code == 404
    assert client.delete("/stocks/AAPL").status_code == 404


def test_refresh_respects_ttl(client):
    client.post("/stocks", json={"ticker": "AAPL"})  # stamps last_fetch
    resp = client.post("/stocks/AAPL/refresh")
    assert resp.status_code == 200
    assert resp.json() == {"refreshed": False, "fetched": 0, "inserted": 0, "queued": 0}


def test_refresh_fetches_after_ttl_expiry(client, monkeypatch):
    client.post("/stocks", json={"ticker": "AAPL"})
    monkeypatch.setattr(main.refresh, "REFRESH_TTL_SECONDS", 0)
    resp = client.post("/stocks/AAPL/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["refreshed"] is True
    assert body["inserted"] == 0  # same urls, dedupe holds


def test_refresh_unknown_ticker_404(client):
    assert client.post("/stocks/MSFT/refresh").status_code == 404


def test_new_market_day_refresh_on_dashboard_load(client):
    # Seed the watchlist directly, bypassing POST /stocks and its initial fetch.
    conn = db.get_connection()
    conn.execute("INSERT INTO watchlist (ticker, company_name) VALUES ('AAPL', 'Apple Inc')")
    conn.commit()
    conn.close()

    # No last_refreshed_date in meta means this load counts as a new market day,
    # so GET /stocks fans out over the watchlist before rendering.
    [row] = client.get("/stocks").json()
    assert row["article_count"] == 2
