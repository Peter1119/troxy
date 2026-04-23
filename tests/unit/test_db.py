"""Tests for database connection and schema."""

from troxy.core.db import get_connection, init_db, DB_SCHEMA_VERSION


def test_init_db_creates_tables(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "flows" in tables
    assert "mock_rules" in tables
    assert "intercept_rules" in tables
    assert "pending_flows" in tables
    conn.close()


def test_init_db_creates_indexes(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = [row[0] for row in cursor.fetchall()]
    assert "idx_flows_host" in indexes
    assert "idx_flows_status" in indexes
    assert "idx_flows_method" in indexes
    assert "idx_flows_timestamp" in indexes
    conn.close()


def test_init_db_is_idempotent(tmp_db):
    init_db(tmp_db)
    init_db(tmp_db)  # should not raise
    conn = get_connection(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    assert len(cursor.fetchall()) > 0
    conn.close()


def test_init_db_creates_parent_dirs(tmp_path):
    db_path = str(tmp_path / "sub" / "dir" / "flows.db")
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    assert len(cursor.fetchall()) > 0
    conn.close()


def test_get_connection_enables_wal(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal == "wal"
    conn.close()


def test_migration_adds_hit_count_columns(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(mock_rules)")}
    assert "hit_count" in columns
    assert "last_hit_at" in columns
    conn.close()


def test_migration_hit_count_default_zero(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    import time
    conn.execute(
        "INSERT INTO mock_rules (domain, path_pattern, status_code, enabled, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        ("example.com", "/api/*", 200, 1, time.time()),
    )
    conn.commit()
    row = conn.execute("SELECT hit_count, last_hit_at FROM mock_rules").fetchone()
    assert row[0] == 0
    assert row[1] is None
    conn.close()
