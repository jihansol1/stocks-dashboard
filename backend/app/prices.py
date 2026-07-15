"""Thin price-history client for sidebar sparklines and the chart panel.

Finnhub's free tier gates historical candles, so this uses Yahoo's public
chart endpoint (no key). It is unofficial: kept in this one swappable module,
cached with a short TTL so the UI never hammers it. If it breaks, swap this
module for another provider.
"""

import time

import httpx

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TIMEOUT = 10.0
CACHE_TTL_SECONDS = 300

# range key -> (yahoo range, yahoo interval)
RANGES = {
    "1d": ("1d", "5m"),
    "5d": ("5d", "15m"),
    "1mo": ("1mo", "1d"),
    "6mo": ("6mo", "1d"),
    "1y": ("1y", "1d"),
}

_cache: dict[tuple[str, str], tuple[float, dict]] = {}


class PriceError(Exception):
    pass


def get_prices(symbol: str, range_key: str) -> dict:
    """Price series for a symbol. range_key must be one of RANGES."""
    if range_key not in RANGES:
        raise PriceError(f"Unknown range: {range_key}")

    cache_key = (symbol, range_key)
    cached = _cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    data = _fetch(symbol, range_key)
    _cache[cache_key] = (time.monotonic() + CACHE_TTL_SECONDS, data)
    return data


def _fetch(symbol: str, range_key: str) -> dict:
    yahoo_range, interval = RANGES[range_key]
    try:
        resp = httpx.get(
            BASE_URL.format(symbol=symbol),
            params={"range": yahoo_range, "interval": interval, "includePrePost": "false"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise PriceError(f"Price fetch failed for {symbol}: {exc}") from exc

    return _parse(symbol, range_key, payload)


def _parse(symbol: str, range_key: str, payload: dict) -> dict:
    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        timestamps = result.get("timestamp") or []
        closes = result["indicators"]["quote"][0].get("close") or []
    except (KeyError, IndexError, TypeError) as exc:
        raise PriceError(f"Unexpected price payload for {symbol}") from exc

    points = [
        {"t": t, "c": round(c, 4)}
        for t, c in zip(timestamps, closes)
        if c is not None
    ]
    if not points:
        raise PriceError(f"No price points returned for {symbol}")

    price = meta.get("regularMarketPrice")
    prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
    change = round(price - prev_close, 4) if price is not None and prev_close else None
    change_percent = (
        round(change / prev_close * 100, 4) if change is not None and prev_close else None
    )

    return {
        "ticker": symbol,
        "range": range_key,
        "currency": meta.get("currency"),
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_percent": change_percent,
        "points": points,
    }
