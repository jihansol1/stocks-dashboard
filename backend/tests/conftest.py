import pytest

from app import db


@pytest.fixture
def conn(tmp_path):
    """A connection to a fresh, fully initialized temp database."""
    db_file = str(tmp_path / "test.db")
    db.init_db(db_file)
    conn = db.get_connection(db_file)
    yield conn
    conn.close()
