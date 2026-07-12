from app import finnhub_client


def test_resolve_ticker_exact_match(monkeypatch):
    monkeypatch.setattr(
        finnhub_client,
        "search_symbol",
        lambda q: [
            {"symbol": "AAPL", "description": "Apple Inc", "type": "Common Stock"},
            {"symbol": "AAPL.MX", "description": "Apple Inc", "type": "Common Stock"},
        ],
    )
    assert finnhub_client.resolve_ticker("aapl") == {
        "ticker": "AAPL",
        "company_name": "Apple Inc",
    }


def test_resolve_ticker_no_exact_match_returns_none(monkeypatch):
    monkeypatch.setattr(
        finnhub_client,
        "search_symbol",
        lambda q: [{"symbol": "AAPL.MX", "description": "Apple Inc"}],
    )
    assert finnhub_client.resolve_ticker("AAPL") is None


def test_resolve_ticker_blank_input(monkeypatch):
    monkeypatch.setattr(finnhub_client, "search_symbol", lambda q: [])
    assert finnhub_client.resolve_ticker("   ") is None


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(finnhub_client.config, "FINNHUB_API_KEY", "")
    try:
        finnhub_client._get("/search", {"q": "AAPL"})
        assert False, "expected FinnhubError"
    except finnhub_client.FinnhubError:
        pass
