import pytest

from app import config, db


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch):
    """Tests must never reach Finnhub or Anthropic, even if real keys are set."""
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")


@pytest.fixture
def conn(tmp_path):
    """A connection to a fresh, fully initialized temp database."""
    db_file = str(tmp_path / "test.db")
    db.init_db(db_file)
    conn = db.get_connection(db_file)
    yield conn
    conn.close()
