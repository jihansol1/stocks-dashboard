"""SQLite connection and schema init.

Schema per CLAUDE.md: watchlist, articles (deduped by unique url), articles_fts
(FTS5 over headline + summary, kept in sync by triggers), meta.
"""

import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    ticker       TEXT PRIMARY KEY,
    company_name TEXT,
    added_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL REFERENCES watchlist(ticker) ON DELETE CASCADE,
    headline     TEXT NOT NULL,
    source       TEXT,
    url          TEXT NOT NULL UNIQUE,
    published_at TEXT,
    fetched_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    summary      TEXT,
    sentiment    TEXT CHECK (sentiment IN ('bullish', 'bearish', 'neutral'))
);

CREATE INDEX IF NOT EXISTS idx_articles_ticker_published
    ON articles(ticker, published_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    headline,
    summary,
    content='articles',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS articles_fts_insert AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, headline, summary)
    VALUES (new.id, new.headline, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS articles_fts_delete AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, headline, summary)
    VALUES ('delete', old.id, old.headline, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS articles_fts_update AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, headline, summary)
    VALUES ('delete', old.id, old.headline, old.summary);
    INSERT INTO articles_fts(rowid, headline, summary)
    VALUES (new.id, new.headline, new.summary);
END;
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may open and close a request's
    # connection on different threadpool threads. Each connection is still
    # used by one request (or one enrichment worker) at a time.
    conn = sqlite3.connect(db_path or config.DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Background enrichment writes from worker threads while requests read.
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(db_path: str | None = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
