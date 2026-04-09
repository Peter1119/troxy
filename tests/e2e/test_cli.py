"""E2E tests for CLI commands."""

import json
import subprocess
import sys
import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow


def _run_troxy(*args, db_path=None):
    """Run troxy CLI and return stdout."""
    cmd = [sys.executable, "-m", "troxy.cli.main"] + list(args)
    if db_path:
        cmd.extend(["--db", db_path])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def _seed(db_path):
    """Seed test DB with sample flows."""
    init_db(db_path)
    now = time.time()
    insert_flow(db_path, timestamp=now - 60, method="GET", scheme="https",
                host="api.example.com", port=443, path="/users", query=None,
                request_headers={"Accept": "application/json"}, request_body=None,
                request_content_type=None, status_code=200,
                response_headers={"Content-Type": "application/json"},
                response_body='{"users": []}', response_content_type="application/json",
                duration_ms=42.0)
    insert_flow(db_path, timestamp=now, method="POST", scheme="https",
                host="api.example.com", port=443, path="/api/users", query=None,
                request_headers={"Content-Type": "application/json"},
                request_body='{"email": "test@test.com"}',
                request_content_type="application/json", status_code=401,
                response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized"}',
                response_content_type="application/json", duration_ms=30.0)


def test_flows_lists_all(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "api.example.com" in result.stdout
    assert "api.example.com" in result.stdout


def test_flows_filter_domain(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "-d", "example", "--no-color", db_path=tmp_db)
    assert "api.example.com" in result.stdout
    assert "api.example.com" not in result.stdout


def test_flows_filter_status(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "-s", "401", "--no-color", db_path=tmp_db)
    assert "401" in result.stdout


def test_flows_json_output(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2


def test_flow_detail(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "2", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "api.example.com" in result.stdout
    assert "unauthorized" in result.stdout


def test_flow_body_only(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "2", "--body", "--no-color", db_path=tmp_db)
    assert "unauthorized" in result.stdout


def test_flow_export_curl(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "2", "--export", "curl", db_path=tmp_db)
    assert "curl" in result.stdout
    assert "api.example.com" in result.stdout


def test_flow_not_found(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "999", db_path=tmp_db)
    assert result.returncode != 0 or "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_search(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("search", "unauthorized", "--no-color", db_path=tmp_db)
    assert "api.example.com" in result.stdout


def test_status(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("status", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "2" in result.stdout


def test_clear(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("clear", "--yes", db_path=tmp_db)
    assert result.returncode == 0
    result2 = _run_troxy("flows", "--json", db_path=tmp_db)
    data = json.loads(result2.stdout)
    assert len(data) == 0
