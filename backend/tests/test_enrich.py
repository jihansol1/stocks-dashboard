import threading

from app import enrich
from app.ai import AIError

ITEMS = [
    {"url": "http://news/1", "headline": "Apple ships new chip", "snippet": "snippet one"},
    {"url": "http://news/2", "headline": "Apple opens new store", "snippet": None},
]


def _seed_articles(conn):
    conn.execute("INSERT INTO watchlist (ticker) VALUES ('AAPL')")
    for item in ITEMS:
        conn.execute(
            "INSERT INTO articles (ticker, headline, url) VALUES ('AAPL', ?, ?)",
            (item["headline"], item["url"]),
        )
    conn.commit()


def test_enrich_batch_fills_summary_and_sentiment(conn, db_file, monkeypatch):
    _seed_articles(conn)
    monkeypatch.setattr(
        enrich.ai,
        "enrich_article",
        lambda ticker, headline, snippet: {
            "summary": f"AI summary of: {headline}",
            "sentiment": "bullish",
        },
    )

    count = enrich.enrich_batch("AAPL", ITEMS, db_path=db_file)

    assert count == 2
    rows = conn.execute("SELECT headline, summary, sentiment FROM articles").fetchall()
    assert all(r["summary"] == f"AI summary of: {r['headline']}" for r in rows)
    assert all(r["sentiment"] == "bullish" for r in rows)


def test_enrich_batch_failures_leave_nulls(conn, db_file, monkeypatch):
    _seed_articles(conn)

    def flaky(ticker, headline, snippet):
        if headline == "Apple ships new chip":
            raise AIError("anthropic down")
        return {"summary": "ok", "sentiment": "neutral"}

    monkeypatch.setattr(enrich.ai, "enrich_article", flaky)

    count = enrich.enrich_batch("AAPL", ITEMS, db_path=db_file)

    assert count == 1
    row = conn.execute(
        "SELECT summary FROM articles WHERE url = 'http://news/1'"
    ).fetchone()
    assert row["summary"] is None


def test_enrich_batch_never_overwrites_existing_summary(conn, db_file, monkeypatch):
    _seed_articles(conn)
    conn.execute(
        "UPDATE articles SET summary = 'original', sentiment = 'bearish' WHERE url = 'http://news/1'"
    )
    conn.commit()
    monkeypatch.setattr(
        enrich.ai,
        "enrich_article",
        lambda ticker, headline, snippet: {"summary": "overwritten", "sentiment": "bullish"},
    )

    enrich.enrich_batch("AAPL", ITEMS, db_path=db_file)

    row = conn.execute(
        "SELECT summary, sentiment FROM articles WHERE url = 'http://news/1'"
    ).fetchone()
    assert row["summary"] == "original"
    assert row["sentiment"] == "bearish"


def test_enrich_batch_empty_is_noop(db_file):
    assert enrich.enrich_batch("AAPL", [], db_path=db_file) == 0


def test_schedule_runs_in_background(conn, db_file, monkeypatch):
    _seed_articles(conn)
    monkeypatch.setattr(
        enrich.ai,
        "enrich_article",
        lambda ticker, headline, snippet: {"summary": "done", "sentiment": "neutral"},
    )
    # schedule() defaults db_path to the configured DB; point it at the temp one.
    original_get_connection = enrich.db.get_connection
    monkeypatch.setattr(
        enrich.db, "get_connection", lambda p=None: original_get_connection(p or db_file)
    )

    enrich.schedule("AAPL", ITEMS)
    for thread in threading.enumerate():
        if thread.name.startswith("enrich-"):
            thread.join(timeout=10)

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM articles WHERE summary = 'done'"
    ).fetchone()["c"]
    assert count == 2
