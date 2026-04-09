"""E2E tests for intercept CLI commands."""

import json
import subprocess
import sys

from troxy.core.db import init_db
from troxy.core.intercept import add_pending_flow


def _run_troxy(*args, db_path=None):
    cmd = [sys.executable, "-m", "troxy.cli.main"] + list(args)
    if db_path:
        cmd.extend(["--db", db_path])
    return subprocess.run(cmd, capture_output=True, text=True)


def test_intercept_add_and_list(tmp_db):
    init_db(tmp_db)
    result = _run_troxy("intercept", "add", "-d", "api.example.com", "-m", "POST", "--db", tmp_db)
    assert result.returncode == 0
    result = _run_troxy("intercept", "list", "--no-color", "--db", tmp_db)
    assert "api.example.com" in result.stdout


def test_intercept_remove(tmp_db):
    init_db(tmp_db)
    _run_troxy("intercept", "add", "-d", "a.com", "--db", tmp_db)
    result = _run_troxy("intercept", "remove", "1", "--db", tmp_db)
    assert result.returncode == 0


def test_pending_list(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="abc", method="POST", host="api.example.com",
                     path="/users", request_headers='{"Auth": "tok"}', request_body='{"a":1}')
    result = _run_troxy("pending", "--no-color", "--db", tmp_db)
    assert "api.example.com" in result.stdout


def test_modify_and_release(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="abc", method="POST", host="a.com",
                     path="/", request_headers='{"Auth": "old"}', request_body=None)
    result = _run_troxy("modify", "1", "--header", "Auth: new_token", "--db", tmp_db)
    assert result.returncode == 0
    result = _run_troxy("release", "1", "--db", tmp_db)
    assert result.returncode == 0


def test_drop(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="abc", method="GET", host="a.com",
                     path="/", request_headers="{}", request_body=None)
    result = _run_troxy("drop", "1", "--db", tmp_db)
    assert result.returncode == 0
