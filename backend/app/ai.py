"""Article enrichment: short summary + sentiment tag via the Anthropic API.

One call per new article at ingestion (decision 5). Thin and swappable per
CLAUDE.md conventions. Raises AIError on any failure; callers degrade to
null summary/sentiment and never abort the refresh.
"""

import json
import logging

import anthropic

from . import config

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"

SENTIMENTS = {"bullish", "bearish", "neutral"}

# Structured output schema: the API guarantees the response parses against
# this, but we still validate defensively below.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "sentiment": {"type": "string", "enum": sorted(SENTIMENTS)},
    },
    "required": ["summary", "sentiment"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You summarize financial news headlines for a personal stock dashboard. "
    "Write one or two plain, factual sentences using only information present "
    "in the provided headline and snippet. Do not invent details, numbers, or "
    "causes that are not stated. No marketing or hype language. No em dashes. "
    "Tag the sentiment for the given ticker as bullish, bearish, or neutral; "
    "use neutral when the news has no clear direction for the stock."
)

_client = None


class AIError(Exception):
    pass


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def enrich_article(ticker: str, headline: str, snippet: str | None) -> dict:
    """Summarize and tag one article. Returns {"summary": str, "sentiment": str|None}."""
    if not config.ANTHROPIC_API_KEY:
        raise AIError("ANTHROPIC_API_KEY is not set")

    user_content = f"Ticker: {ticker}\nHeadline: {headline}"
    if snippet:
        user_content += f"\nSnippet: {snippet}"

    try:
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        )
    except anthropic.APIError as exc:
        raise AIError(f"Anthropic request failed: {exc}") from exc

    return _parse_response(response)


def _parse_response(response) -> dict:
    if response.stop_reason == "refusal":
        raise AIError("Model declined the request")
    text = next(
        (block.text for block in response.content if block.type == "text"), ""
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIError(f"Model returned invalid JSON: {text[:100]!r}") from exc

    summary = str(data.get("summary") or "").strip()
    if not summary:
        raise AIError("Model returned an empty summary")

    sentiment = data.get("sentiment")
    if sentiment not in SENTIMENTS:
        sentiment = None  # cache the summary anyway; sentiment stays untagged

    return {"summary": summary, "sentiment": sentiment}
