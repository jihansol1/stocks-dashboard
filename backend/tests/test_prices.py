import pytest
from fastapi.testclient import TestClient

from app import config, db, main, prices
from app.prices import PriceError

FAKE_PAYLOAD = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "regularMarketPrice": 327.5,
                    "chartPreviousClose": 314.86,
                },
                "timestamp": [1000, 2000, 3000],
                "indicators": {"quote": [{"close": [318.87, None, 327.5]}]},
            }
        ]
    }
}


@pytest.fixture(autouse=True)
def clear_price_cache():
    prices._cache.clear()
    yield
    prices._cache.clear()


def test_parse_extracts_series_and_change():
    data = prices._parse("AAPL", "1d", FAKE_PAYLOAD)

    assert data["price"] == 327.5
    assert data["change"] == pytest.approx(12.64)
    assert data["change_percent"] == pytest.approx(4.0145, abs=0.001)
    assert data["points"] == [{"t": 1000, "c": 318.87}, {"t": 3000, "c": 327.5}]  # null dropped


def test_unknown_range_rejected():
    with pytest.raises(PriceError):
        prices.get_prices("AAPL", "3y")


def test_empty_series_raises():
    empty = {"chart": {"result": [{"meta": {}, "timestamp": [], "indicators": {"quote": [{"close": []}]}}]}}
    with pytest.raises(PriceError):
        prices._parse("AAPL", "1d", empty)


def test_cache_prevents_second_fetch(monkeypatch):
    calls = []

    def fake_fetch(symbol, range_key):
        calls.append(symbol)
        return {"ticker": symbol, "points": [{"t": 1, "c": 2.0}]}

    monkeypatch.setattr(prices, "_fetch", fake_fetch)

    prices.get_prices("AAPL", "1d")
    prices.get_prices("AAPL", "1d")
    prices.get_prices("AAPL", "1mo")  # different range is a different cache entry

    assert calls == ["AAPL", "AAPL"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(main.app) as client:
        conn = db.get_connection()
        conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")
        conn.commit()
        conn.close()
        yield client


def test_prices_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        prices, "get_prices", lambda symbol, range_key: {"ticker": symbol, "range": range_key}
    )
    resp = client.get("/stocks/aapl/prices?range=1mo")
    assert resp.status_code == 200
    assert resp.json() == {"ticker": "AAPL", "range": "1mo"}


def test_prices_endpoint_validations(client, monkeypatch):
    assert client.get("/stocks/MSFT/prices").status_code == 404  # not on watchlist
    assert client.get("/stocks/AAPL/prices?range=3y").status_code == 400

    def boom(symbol, range_key):
        raise PriceError("provider down")

    monkeypatch.setattr(prices, "get_prices", boom)
    assert client.get("/stocks/AAPL/prices").status_code == 502