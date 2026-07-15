import pytest

from app import config, db


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch):
    """Tests must never reach Finnhub or Anthropic, even if real keys are set."""
    monkeypatch.setattr(config, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")


@pytest.fixture
def db_file(tmp_path):
    """Path to a fresh, fully initialized temp database."""
    path = str(tmp_path / "test.db")
    db.init_db(path)
    return path


@pytest.fixture
def conn(db_file):
    """A connection to the temp database."""
    conn = db.get_connection(db_file)
    yield conn
    conn.close()
