import json
from types import SimpleNamespace

import pytest

from app import ai
from app.ai import AIError


def _fake_response(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(ai.config, "ANTHROPIC_API_KEY", "test-key")


def _client_returning(response):
    return SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: response)
    )


def test_enrich_article_happy_path(with_key, monkeypatch):
    resp = _fake_response({"summary": "Apple shipped a new chip.", "sentiment": "bullish"})
    monkeypatch.setattr(ai, "_get_client", lambda: _client_returning(resp))

    result = ai.enrich_article("AAPL", "Apple ships new chip", "Some snippet")

    assert result == {"summary": "Apple shipped a new chip.", "sentiment": "bullish"}


def test_unknown_sentiment_kept_as_null(with_key, monkeypatch):
    resp = _fake_response({"summary": "Something happened.", "sentiment": "mixed"})
    monkeypatch.setattr(ai, "_get_client", lambda: _client_returning(resp))

    result = ai.enrich_article("AAPL", "h", None)

    assert result["summary"] == "Something happened."
    assert result["sentiment"] is None


def test_invalid_json_raises(with_key, monkeypatch):
    resp = _fake_response("not json at all")
    monkeypatch.setattr(ai, "_get_client", lambda: _client_returning(resp))

    with pytest.raises(AIError):
        ai.enrich_article("AAPL", "h", None)


def test_empty_summary_raises(with_key, monkeypatch):
    resp = _fake_response({"summary": "   ", "sentiment": "neutral"})
    monkeypatch.setattr(ai, "_get_client", lambda: _client_returning(resp))

    with pytest.raises(AIError):
        ai.enrich_article("AAPL", "h", None)


def test_refusal_raises(with_key, monkeypatch):
    resp = _fake_response({"summary": "x", "sentiment": "neutral"}, stop_reason="refusal")
    monkeypatch.setattr(ai, "_get_client", lambda: _client_returning(resp))

    with pytest.raises(AIError):
        ai.enrich_article("AAPL", "h", None)


def test_missing_api_key_raises():
    with pytest.raises(AIError):
        ai.enrich_article("AAPL", "h", None)
