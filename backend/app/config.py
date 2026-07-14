"""Environment configuration. All secrets come from env / .env, never the repo."""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env lives at backend/.env; load it once at import time.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "stocks.db"))


def missing_keys() -> list[str]:
    """Names of required API keys that are not set. Empty list means fully configured."""
    missing = []
    if not FINNHUB_API_KEY:
        missing.append("FINNHUB_API_KEY")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    return missing
