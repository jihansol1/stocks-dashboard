"""Thin Finnhub client: symbol search and company news.

Kept minimal and swappable per CLAUDE.md conventions. All functions raise
FinnhubError on transport or API failures; callers decide how to degrade.
"""

import httpx

from . import config

BASE_URL = "https://finnhub.io/api/v1"
TIMEOUT = 10.0


class FinnhubError(Exception):
    pass


def _get(path: str, params: dict) -> dict | list:
    if not config.FINNHUB_API_KEY:
        raise FinnhubError("FINNHUB_API_KEY is not set")
    try:
        resp = httpx.get(
            f"{BASE_URL}{path}",
            params={**params, "token": config.FINNHUB_API_KEY},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise FinnhubError(f"Finnhub request failed: {path}: {exc}") from exc


def search_symbol(query: str) -> list[dict]:
    """Symbol lookup. Returns the raw result list (symbol, description, type, ...)."""
    data = _get("/search", {"q": query})
    result = data.get("result") if isinstance(data, dict) else None
    return result if isinstance(result, list) else []


def resolve_ticker(ticker: str) -> dict | None:
    """Validate a ticker via symbol search.

    Returns {"ticker": ..., "company_name": ...} on an exact symbol match,
    else None.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        return None
    for item in search_symbol(ticker):
        if item.get("symbol", "").upper() == ticker:
            return {"ticker": ticker, "company_name": item.get("description", "")}
    return None


def company_news(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """Company news for a symbol between from_date and to_date (YYYY-MM-DD).

    Items carry: headline, source, url, summary, datetime (unix seconds), ...
    """
    data = _get("/company-news", {"symbol": symbol, "from": from_date, "to": to_date})
    return data if isinstance(data, list) else []
