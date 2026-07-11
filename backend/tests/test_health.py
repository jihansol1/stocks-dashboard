from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["missing_keys"], list)


def test_startup_creates_meta_table(tmp_path):
    from app import db

    db_file = tmp_path / "test.db"
    db.init_db(str(db_file))
    conn = db.get_connection(str(db_file))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
