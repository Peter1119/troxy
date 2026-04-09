"""SQLite database connection and schema management."""

import sqlite3
from pathlib import Path

DB_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    method TEXT NOT NULL,
    scheme TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    path TEXT NOT NULL,
    query TEXT,
    request_headers TEXT NOT NULL,
    request_body TEXT,
    request_content_type TEXT,
    status_code INTEGER NOT NULL,
    response_headers TEXT NOT NULL,
    response_body TEXT,
    response_content_type TEXT,
    duration_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_flows_host ON flows(host);
CREATE INDEX IF NOT EXISTS idx_flows_status ON flows(status_code);
CREATE INDEX IF NOT EXISTS idx_flows_method ON flows(method);
CREATE INDEX IF NOT EXISTS idx_flows_timestamp ON flows(timestamp);

CREATE TABLE IF NOT EXISTS mock_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT,
    path_pattern TEXT,
    method TEXT,
    status_code INTEGER NOT NULL DEFAULT 200,
    response_headers TEXT,
    response_body TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS intercept_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT,
    path_pattern TEXT,
    method TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    method TEXT NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    request_headers TEXT NOT NULL,
    request_body TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and row factory."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """Create database file, parent dirs, and all tables/indexes."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA_SQL)
    conn.close()


def default_db_path() -> str:
    """Return the default DB path, respecting TROXY_DB env var."""
    import os

    path = os.environ.get("TROXY_DB")
    if path:
        return os.path.expanduser(path)
    return str(Path.home() / ".troxy" / "flows.db")
