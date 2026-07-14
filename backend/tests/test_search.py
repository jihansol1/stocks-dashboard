import pytest
from fastapi.testclient import TestClient

from app import config, db, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Client over a seeded cache. No Finnhub mocks: search is read-path only
    and must never reach an external API."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(main.app) as client:
        conn = db.get_connection()
        conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL'), ('MSFT')")
        conn.executemany(
            """
            INSERT INTO articles (ticker, headline, url, summary, published_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "AAPL",
                    "Apple ships new M5 chip",
                    "http://news/1",
                    "Strong datacenter demand for the new chip line.",
                    "2026-07-10T12:00:00Z",
                ),
                (
                    "MSFT",
                    "Microsoft announces datacenter expansion",
                    "http://news/2",
                    None,
                    "2026-07-11T09:00:00Z",
                ),
            ],
        )
        conn.commit()
        conn.close()
        yield client


def test_search_matches_headline(client):
    results = client.get("/search", params={"q": "chip"}).json()
    assert len(results) == 1
    assert results[0]["ticker"] == "AAPL"
    assert results[0]["headline"] == "Apple ships new M5 chip"


def test_search_matches_summary_and_spans_tickers(client):
    results = client.get("/search", params={"q": "datacenter"}).json()
    assert {r["ticker"] for r in results} == {"AAPL", "MSFT"}


def test_search_is_case_insensitive(client):
    results = client.get("/search", params={"q": "CHIP"}).json()
    assert len(results) == 1


def test_multiple_terms_are_anded(client):
    results = client.get("/search", params={"q": "datacenter expansion"}).json()
    assert len(results) == 1
    assert results[0]["ticker"] == "MSFT"


def test_no_hits_returns_empty_list(client):
    assert client.get("/search", params={"q": "tesla"}).json() == []


def test_blank_query_rejected(client):
    assert client.get("/search", params={"q": "   "}).status_code == 400
    assert client.get("/search").status_code == 422  # q is required


def test_fts_operators_are_treated_as_plain_text(client):
    # None of these may 500; they are matched literally, not parsed as syntax.
    for q in ['"chip" AND (', "chip OR", "NOT chip", '(("', "chip*"]:
        resp = client.get("/search", params={"q": q})
        assert resp.status_code == 200, q
