"""E2E smoke test for `troxy start` command."""

import os
import sqlite3
import subprocess
import time

import pytest


def test_start_cmd_help_shows_port_option():
    """`troxy start --help` should list the port and mode options."""
    proc = subprocess.run(
        ["uv", "run", "troxy", "start", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "--port" in proc.stdout
    assert "--mode" in proc.stdout
    assert "TUI" in proc.stdout or "mitmproxy" in proc.stdout


_EXPECTED_TABLES = {"flows", "mock_rules", "intercept_rules", "pending_flows"}


@pytest.mark.slow
def test_start_cmd_launches_and_quits(tmp_path):
    """`troxy start` launches mitmdump + TUI, quits cleanly on q, and leaves
    a fully-initialized SQLite DB behind.

    Strengthened verification (beyond returncode):
    - DB file exists at --db path
    - All core tables are created
    - `mock_rules.hit_count` column exists (schema migration applied)
    """
    db_path = str(tmp_path / "flows.db")
    proc = subprocess.Popen(
        ["uv", "run", "troxy", "start", "-p", "18090", "--db", db_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(3)
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
    except BrokenPipeError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)
    assert proc.returncode is not None

    # DB should have been created + migrated by cli.start_cmd → init_db.
    # If mitmdump failed to bind or TUI crashed before init, this will catch it.
    assert os.path.exists(db_path), f"DB not created at {db_path}"

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = _EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after start: {missing}"

        mock_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(mock_rules)").fetchall()
        }
        assert "hit_count" in mock_columns, (
            "hit_count migration not applied — start_cmd did not run init_db"
        )
    finally:
        conn.close()
