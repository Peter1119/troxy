"""E2E tests for mock CLI commands."""

import json
import subprocess
import sys
import time

from troxy.core.db import init_db
from troxy.core.store import insert_flow


def _run_troxy(*args, db_path=None):
    cmd = [sys.executable, "-m", "troxy.cli.main"] + list(args)
    if db_path:
        cmd.extend(["--db", db_path])
    return subprocess.run(cmd, capture_output=True, text=True)


def test_mock_add_and_list(tmp_db):
    init_db(tmp_db)
    result = _run_troxy("mock", "add", "-d", "api.example.com", "-p", "/users",
                        "-s", "200", "--body", '{"mock": true}', "--db", tmp_db)
    assert result.returncode == 0

    result = _run_troxy("mock", "list", "--no-color", "--db", tmp_db)
    assert "api.example.com" in result.stdout


def test_mock_remove(tmp_db):
    init_db(tmp_db)
    _run_troxy("mock", "add", "-d", "a.com", "-p", "/", "-s", "200", "--db", tmp_db)
    result = _run_troxy("mock", "remove", "1", "--db", tmp_db)
    assert result.returncode == 0
    result = _run_troxy("mock", "list", "--json", "--db", tmp_db)
    data = json.loads(result.stdout)
    assert len(data) == 0


def test_mock_disable_enable(tmp_db):
    init_db(tmp_db)
    _run_troxy("mock", "add", "-d", "a.com", "-p", "/", "-s", "200", "--db", tmp_db)
    _run_troxy("mock", "disable", "1", "--db", tmp_db)
    result = _run_troxy("mock", "list", "--json", "--db", tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["enabled"] == 0

    _run_troxy("mock", "enable", "1", "--db", tmp_db)
    result = _run_troxy("mock", "list", "--json", "--db", tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["enabled"] == 1


def test_mock_from_flow(tmp_db):
    init_db(tmp_db)
    insert_flow(tmp_db, timestamp=time.time(), method="GET", scheme="https",
                host="api.example.com", port=443, path="/api/data", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=200, response_headers={"Content-Type": "application/json"},
                response_body='{"data": true}', response_content_type="application/json",
                duration_ms=50)
    result = _run_troxy("mock", "from-flow", "1", "--db", tmp_db)
    assert result.returncode == 0
    result = _run_troxy("mock", "list", "--json", "--db", tmp_db)
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["domain"] == "api.example.com"
