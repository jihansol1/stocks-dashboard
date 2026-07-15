import pytest
from fastapi.testclient import TestClient

from app import config, finnhub_client, main
from app.finnhub_client import FinnhubError

FAKE_RESULTS = [
    {"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock"},
    {"symbol": "AAPL.MX", "description": "APPLE INC", "type": "Common Stock"},
    {"symbol": "", "description": "junk row without symbol"},
] + [{"symbol": f"AAP{i}", "description": f"Company {i}"} for i in range(10)]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    main._symbol_suggestions.cache_clear()
    with TestClient(main.app) as client:
        yield client
    main._symbol_suggestions.cache_clear()


def test_suggestions_returned_and_capped(client, monkeypatch):
    monkeypatch.setattr(finnhub_client, "search_symbol", lambda q: FAKE_RESULTS)

    results = client.get("/symbols", params={"q": "aap"}).json()

    assert results[0] == {"ticker": "AAPL", "name": "APPLE INC"}
    assert len(results) == main.MAX_SYMBOL_SUGGESTIONS
    assert all(r["ticker"] for r in results)  # symbol-less rows dropped


def test_blank_query_returns_empty_without_calling_finnhub(client, monkeypatch):
    def explode(q):
        raise AssertionError("should not call Finnhub for a blank query")

    monkeypatch.setattr(finnhub_client, "search_symbol", explode)
    assert client.get("/symbols", params={"q": "   "}).json() == []


def test_repeat_query_is_served_from_cache(client, monkeypatch):
    calls = []

    def counting(q):
        calls.append(q)
        return FAKE_RESULTS

    monkeypatch.setattr(finnhub_client, "search_symbol", counting)
    client.get("/symbols", params={"q": "aap"})
    client.get("/symbols", params={"q": "AAP"})  # same query, different case

    assert calls == ["AAP"]


def test_finnhub_down_returns_502(client, monkeypatch):
    def boom(q):
        raise FinnhubError("finnhub down")

    monkeypatch.setattr(finnhub_client, "search_symbol", boom)
    assert client.get("/symbols", params={"q": "XYZ"}).status_code == 502
