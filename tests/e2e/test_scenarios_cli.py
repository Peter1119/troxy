"""E2E tests for 'troxy scenario' CLI subcommands.

Engineer implementation: --steps / -s accepts JSON array
e.g. -s '[{"status_code":200},{"status_code":500}]'
"""

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


def _seed_flow(db_path, *, status_code=200, path="/api/data"):
    return insert_flow(
        db_path,
        timestamp=time.time(),
        method="GET",
        scheme="https",
        host="api.example.com",
        port=443,
        path=path,
        query=None,
        request_headers={},
        request_body=None,
        request_content_type=None,
        status_code=status_code,
        response_headers={"Content-Type": "application/json"},
        response_body=f'{{"status": {status_code}}}',
        response_content_type="application/json",
        duration_ms=10.0,
    )


_TWO_STEP_JSON = json.dumps([
    {"status_code": 500, "response_body": '{"error": "payment_failed"}'},
    {"status_code": 200, "response_body": '{"ok": true}'},
])

_SIMPLE_TWO_STEP = json.dumps([{"status_code": 500}, {"status_code": 200}])


# ---------------------------------------------------------------------------
# troxy scenario add
# ---------------------------------------------------------------------------

def test_scenario_add_and_list(tmp_db):
    init_db(tmp_db)
    result = _run_troxy(
        "scenario", "add",
        "-d", "api.example.com",
        "-p", "/v1/payments",
        "-m", "POST",
        "-s", _SIMPLE_TWO_STEP,
        db_path=tmp_db,
    )
    assert result.returncode == 0

    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["domain"] == "api.example.com"
    assert data[0]["path_pattern"] == "/v1/payments"
    assert data[0]["method"] == "POST"


def test_scenario_add_with_name(tmp_db):
    init_db(tmp_db)
    result = _run_troxy(
        "scenario", "add",
        "--name", "auth-retry",
        "-p", "/api/me",
        "-s", json.dumps([{"status_code": 401}, {"status_code": 200}]),
        db_path=tmp_db,
    )
    assert result.returncode == 0

    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["name"] == "auth-retry"


def test_scenario_add_with_loop_flag(tmp_db):
    init_db(tmp_db)
    result = _run_troxy(
        "scenario", "add",
        "-p", "/api/data",
        "-s", _SIMPLE_TWO_STEP,
        "--loop",
        db_path=tmp_db,
    )
    assert result.returncode == 0

    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["loop"] in (1, True)


def test_scenario_add_four_step_sequence(tmp_db):
    """4-step 시나리오: [200, 500, 503, 200]."""
    init_db(tmp_db)
    four_steps = json.dumps([
        {"status_code": 200},
        {"status_code": 500},
        {"status_code": 503},
        {"status_code": 200},
    ])
    result = _run_troxy(
        "scenario", "add",
        "-d", "api.example.com",
        "-p", "/api/refresh",
        "-s", four_steps,
        "--name", "pay-flicker",
        db_path=tmp_db,
    )
    assert result.returncode == 0
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["total_steps"] == 4


# ---------------------------------------------------------------------------
# troxy scenario list
# ---------------------------------------------------------------------------

def test_scenario_list_shows_current_step_and_total(tmp_db):
    init_db(tmp_db)
    three_steps = json.dumps([{"status_code": 200}, {"status_code": 500}, {"status_code": 503}])
    _run_troxy(
        "scenario", "add",
        "-p", "/api/data",
        "-s", three_steps,
        db_path=tmp_db,
    )
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["current_step"] == 0
    assert data[0]["total_steps"] == 3


def test_scenario_list_no_color(tmp_db):
    init_db(tmp_db)
    _run_troxy(
        "scenario", "add",
        "-p", "/api/data",
        "-s", _SIMPLE_TWO_STEP,
        db_path=tmp_db,
    )
    result = _run_troxy("scenario", "list", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "/api/data" in result.stdout


# ---------------------------------------------------------------------------
# troxy scenario reset
# ---------------------------------------------------------------------------

def test_scenario_reset_by_id(tmp_db):
    init_db(tmp_db)
    _run_troxy(
        "scenario", "add",
        "-p", "/api/me",
        "-s", json.dumps([{"status_code": 401}, {"status_code": 200}]),
        db_path=tmp_db,
    )
    result = _run_troxy("scenario", "reset", "1", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["current_step"] == 0


def test_scenario_reset_by_name(tmp_db):
    init_db(tmp_db)
    _run_troxy(
        "scenario", "add",
        "--name", "auth-retry",
        "-p", "/api/me",
        "-s", json.dumps([{"status_code": 401}, {"status_code": 200}]),
        db_path=tmp_db,
    )
    result = _run_troxy("scenario", "reset", "auth-retry", db_path=tmp_db)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# troxy scenario remove
# ---------------------------------------------------------------------------

def test_scenario_remove_by_id(tmp_db):
    init_db(tmp_db)
    _run_troxy("scenario", "add", "-p", "/api/data", "-s", _SIMPLE_TWO_STEP, db_path=tmp_db)
    result = _run_troxy("scenario", "remove", "1", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert len(data) == 0


def test_scenario_remove_by_name(tmp_db):
    init_db(tmp_db)
    _run_troxy(
        "scenario", "add",
        "--name", "to-remove",
        "-p", "/api/data",
        "-s", _SIMPLE_TWO_STEP,
        db_path=tmp_db,
    )
    result = _run_troxy("scenario", "remove", "to-remove", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert len(data) == 0


# ---------------------------------------------------------------------------
# troxy scenario disable / enable
# ---------------------------------------------------------------------------

def test_scenario_disable_enable(tmp_db):
    init_db(tmp_db)
    _run_troxy("scenario", "add", "-p", "/api/data", "-s", _SIMPLE_TWO_STEP, db_path=tmp_db)
    _run_troxy("scenario", "disable", "1", db_path=tmp_db)
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["enabled"] in (0, False)

    _run_troxy("scenario", "enable", "1", db_path=tmp_db)
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["enabled"] in (1, True)


# ---------------------------------------------------------------------------
# troxy scenario from-flows
# ---------------------------------------------------------------------------

def test_scenario_from_flows_with_explicit_ids(tmp_db):
    init_db(tmp_db)
    fid1 = _seed_flow(tmp_db, status_code=200)
    fid2 = _seed_flow(tmp_db, status_code=401)
    result = _run_troxy(
        "scenario", "from-flows",
        str(fid1), str(fid2),
        "--name", "login-seq",
        db_path=tmp_db,
    )
    assert result.returncode == 0
    result = _run_troxy("scenario", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["name"] == "login-seq"
    assert data[0]["total_steps"] == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_scenario_add_invalid_json_steps_errors(tmp_db):
    """잘못된 JSON steps 에러."""
    init_db(tmp_db)
    result = _run_troxy(
        "scenario", "add",
        "-p", "/api/data",
        "-s", "not-json",
        db_path=tmp_db,
    )
    assert result.returncode != 0


def test_scenario_add_empty_steps_errors(tmp_db):
    """빈 steps 배열 에러."""
    init_db(tmp_db)
    result = _run_troxy(
        "scenario", "add",
        "-p", "/api/data",
        "-s", "[]",
        db_path=tmp_db,
    )
    assert result.returncode != 0
