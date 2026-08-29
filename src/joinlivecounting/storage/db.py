import sqlite3

from .. import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS joins (
    id INTEGER PRIMARY KEY,
    thread_id TEXT NOT NULL,
    username TEXT NOT NULL,
    joined_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS joins_thread_time ON joins (thread_id, joined_at);

CREATE TABLE IF NOT EXISTS blocked (
    thread_id TEXT NOT NULL,
    username TEXT NOT NULL,
    seen_at REAL NOT NULL,
    PRIMARY KEY (thread_id, username)
);

CREATE TABLE IF NOT EXISTS contributor_counts (
    thread_id TEXT PRIMARY KEY,
    count INTEGER,
    scanned_at REAL NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_FILE, timeout=15, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
