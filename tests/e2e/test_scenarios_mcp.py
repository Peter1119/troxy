"""E2E tests for scenario-related MCP server tool handlers.

Engineer implementation notes (2026-04-27):
- troxy_mock_add: 'sequence' OR 'script' param creates a scenario rule
- troxy_mock_list returns 'sequence_steps' (not 'script_steps') for scenario rules
- troxy_mock_reset: resolves scenario by ID or name
- troxy_mock_update: supports 'sequence'/'script' param + 'new_name' rename
- troxy_mock_from_flow: body/headers/name/enabled overrides
"""

import json
import time

from troxy.core.db import init_db
from troxy.core.store import insert_flow

from troxy.mcp.server import (
    handle_mock_add,
    handle_mock_list,
    handle_mock_reset,
    handle_mock_update,
    handle_mock_from_flow,
)


# ---------------------------------------------------------------------------
# troxy_mock_add — sequence parameter (creates scenario rule)
# ---------------------------------------------------------------------------

def test_mock_add_with_sequence_returns_scenario_type(tmp_db):
    init_db(tmp_db)
    result = handle_mock_add(tmp_db, {
        "domain": "api.example.com",
        "path_pattern": "/v1/payments",
        "method": "POST",
        "sequence": [
            {"status_code": 500, "body": '{"error": "payment_failed"}'},
            {"status_code": 200, "body": '{"ok": true}'},
        ],
    })
    data = json.loads(result)
    assert "rule_id" in data
    assert data["rule_id"] == 1
    assert data.get("type") == "scenario"


def test_mock_add_sequence_with_name(tmp_db):
    init_db(tmp_db)
    result = handle_mock_add(tmp_db, {
        "name": "auth-retry",
        "path_pattern": "/api/me",
        "sequence": [
            {"status_code": 401},
            {"status_code": 200},
        ],
    })
    data = json.loads(result)
    assert data.get("type") == "scenario"


def test_mock_add_sequence_with_loop(tmp_db):
    init_db(tmp_db)
    result = handle_mock_add(tmp_db, {
        "path_pattern": "/api/data",
        "sequence": [{"status_code": 200}, {"status_code": 500}],
        "loop": True,
    })
    data = json.loads(result)
    assert "rule_id" in data


def test_mock_add_single_response_still_works(tmp_db):
    """기존 단일 응답 mock 동작 유지 — 하위 호환."""
    init_db(tmp_db)
    result = handle_mock_add(tmp_db, {
        "domain": "api.example.com",
        "path_pattern": "/users",
        "status_code": 200,
        "body": '{"mock": true}',
    })
    data = json.loads(result)
    assert "rule_id" in data
    assert data.get("type") != "scenario"


def test_mock_add_sequence_takes_priority_over_status_code(tmp_db):
    """sequence + status_code 동시 전달 시 sequence 우선."""
    init_db(tmp_db)
    result = handle_mock_add(tmp_db, {
        "path_pattern": "/api/data",
        "status_code": 200,  # should be ignored
        "sequence": [{"status_code": 500}, {"status_code": 200}],
    })
    data = json.loads(result)
    assert data.get("type") == "scenario"


# ---------------------------------------------------------------------------
# troxy_mock_list — extended response for scenario rules
# ---------------------------------------------------------------------------

def test_mock_list_shows_sequence_steps_for_scenario(tmp_db):
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "path_pattern": "/api/data",
        "sequence": [{"status_code": 200}, {"status_code": 500}],
    })
    result = handle_mock_list(tmp_db, {})
    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["sequence_steps"] == 2
    assert data[0]["current_step"] == 0


def test_mock_list_single_rule_has_null_sequence_fields(tmp_db):
    """단일 응답 rule은 sequence_steps=null, current_step=null."""
    init_db(tmp_db)
    handle_mock_add(tmp_db, {"path_pattern": "/a", "status_code": 200})
    result = handle_mock_list(tmp_db, {})
    data = json.loads(result)
    assert data[0].get("sequence_steps") is None
    assert data[0].get("current_step") is None


def test_mock_list_shows_updated_current_step_after_advance(tmp_db):
    """step advance 후 list에서 current_step 증가 확인."""
    init_db(tmp_db)
    from troxy.core.scenarios import get_and_advance_step
    handle_mock_add(tmp_db, {
        "path_pattern": "/api/data",
        "sequence": [{"status_code": 200}, {"status_code": 500}],
    })
    get_and_advance_step(tmp_db, 1)  # scenario_id=1, advance to step 1
    result = handle_mock_list(tmp_db, {})
    data = json.loads(result)
    scenario_entry = next(d for d in data if d.get("sequence_steps") is not None)
    assert scenario_entry["current_step"] == 1


def test_mock_list_combined_shows_both_types(tmp_db):
    """mock_rules와 시나리오 rule이 모두 표시된다."""
    init_db(tmp_db)
    handle_mock_add(tmp_db, {"path_pattern": "/a", "status_code": 200})
    handle_mock_add(tmp_db, {
        "path_pattern": "/b",
        "sequence": [{"status_code": 200}, {"status_code": 500}],
    })
    result = handle_mock_list(tmp_db, {})
    data = json.loads(result)
    assert len(data) == 2
    types = {d.get("sequence_steps") is not None for d in data}
    assert True in types  # at least one scenario
    assert False in types  # at least one mock_rule (None)


# ---------------------------------------------------------------------------
# troxy_mock_reset — new tool (works on scenario rules only)
# ---------------------------------------------------------------------------

def test_mock_reset_scenario_by_id(tmp_db):
    init_db(tmp_db)
    from troxy.core.scenarios import get_and_advance_step
    handle_mock_add(tmp_db, {
        "path_pattern": "/v1/pay",
        "sequence": [{"status_code": 500}, {"status_code": 200}],
    })
    # scenario_id = 1 in mock_scenarios table
    get_and_advance_step(tmp_db, 1)
    result = handle_mock_reset(tmp_db, {"id": 1})
    data = json.loads(result)
    assert "reset" in data
    assert data["reset"] == 1
    list_data = json.loads(handle_mock_list(tmp_db, {}))
    scenario_entry = next(d for d in list_data if d.get("sequence_steps") is not None)
    assert scenario_entry["current_step"] == 0


def test_mock_reset_scenario_by_name(tmp_db):
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "name": "payment",
        "path_pattern": "/v1/pay",
        "sequence": [{"status_code": 500}, {"status_code": 200}],
    })
    result = handle_mock_reset(tmp_db, {"name": "payment"})
    data = json.loads(result)
    assert "reset" in data


def test_mock_reset_missing_returns_error(tmp_db):
    """없는 시나리오 ID는 error 반환."""
    init_db(tmp_db)
    result = handle_mock_reset(tmp_db, {"id": 999})
    data = json.loads(result)
    assert "error" in data


def test_mock_reset_no_ref_returns_error(tmp_db):
    """id/name 없이 호출 시 error."""
    init_db(tmp_db)
    result = handle_mock_reset(tmp_db, {})
    data = json.loads(result)
    assert "error" in data


# ---------------------------------------------------------------------------
# troxy_mock_update — new tool
# ---------------------------------------------------------------------------

def test_mock_update_body_by_id(tmp_db):
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "path_pattern": "/a",
        "status_code": 200,
        "body": '{"old": true}',
    })
    result = handle_mock_update(tmp_db, {"id": 1, "body": '{"new": true}'})
    data = json.loads(result)
    assert "updated" in data
    rules = json.loads(handle_mock_list(tmp_db, {}))
    mock_rule = next(r for r in rules if r.get("sequence_steps") is None)
    assert mock_rule["response_body"] == '{"new": true}'


def test_mock_update_status_code(tmp_db):
    init_db(tmp_db)
    handle_mock_add(tmp_db, {"path_pattern": "/a", "status_code": 200})
    handle_mock_update(tmp_db, {"id": 1, "status_code": 404})
    rules = json.loads(handle_mock_list(tmp_db, {}))
    assert rules[0]["status_code"] == 404


def test_mock_update_by_name(tmp_db):
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "name": "my-rule",
        "path_pattern": "/a",
        "status_code": 200,
    })
    result = handle_mock_update(tmp_db, {"name": "my-rule", "status_code": 503})
    data = json.loads(result)
    assert "updated" in data


def test_mock_update_rename_scenario(tmp_db):
    """시나리오 rule의 new_name으로 이름 변경."""
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "name": "old-name",
        "path_pattern": "/a",
        "sequence": [{"status_code": 200}],
    })
    result = handle_mock_update(tmp_db, {"name": "old-name", "new_name": "new-name"})
    data = json.loads(result)
    assert "updated" in data
    list_data = json.loads(handle_mock_list(tmp_db, {}))
    scenario_entry = next(d for d in list_data if d.get("sequence_steps") is not None)
    assert scenario_entry["name"] == "new-name"


def test_mock_update_scenario_sequence(tmp_db):
    """시나리오 rule의 sequence 교체."""
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "path_pattern": "/a",
        "sequence": [{"status_code": 200}],
    })
    result = handle_mock_update(tmp_db, {
        "id": 1,
        "sequence": [{"status_code": 503}, {"status_code": 200}],
    })
    data = json.loads(result)
    assert "updated" in data
    list_data = json.loads(handle_mock_list(tmp_db, {}))
    scenario_entry = next(d for d in list_data if d.get("sequence_steps") is not None)
    assert scenario_entry["sequence_steps"] == 2


def test_mock_update_sequence_resets_current_step(tmp_db):
    """sequence 교체 시 current_step이 0으로 리셋된다."""
    init_db(tmp_db)
    from troxy.core.scenarios import get_and_advance_step
    handle_mock_add(tmp_db, {
        "path_pattern": "/a",
        "sequence": [{"status_code": 200}, {"status_code": 500}],
    })
    get_and_advance_step(tmp_db, 1)  # advance to step 1
    handle_mock_update(tmp_db, {
        "id": 1,
        "sequence": [{"status_code": 503}, {"status_code": 200}, {"status_code": 204}],
    })
    list_data = json.loads(handle_mock_list(tmp_db, {}))
    scenario_entry = next(d for d in list_data if d.get("sequence_steps") is not None)
    assert scenario_entry["current_step"] == 0


# ---------------------------------------------------------------------------
# troxy_mock_from_flow — extended params
# ---------------------------------------------------------------------------

def _seed_flow(db_path, *, status_code=200, body='{"id": 1}'):
    return insert_flow(
        db_path, timestamp=time.time(), method="GET", scheme="https",
        host="api.example.com", port=443, path="/api/me", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=status_code,
        response_headers={"Content-Type": "application/json"},
        response_body=body,
        response_content_type="application/json", duration_ms=10.0,
    )


def test_mock_from_flow_default_enabled(tmp_db):
    """enabled 파라미터 없으면 기본 활성화."""
    init_db(tmp_db)
    flow_id = _seed_flow(tmp_db)
    result = handle_mock_from_flow(tmp_db, {"flow_id": flow_id})
    data = json.loads(result)
    assert "rule_id" in data
    rules = json.loads(handle_mock_list(tmp_db, {}))
    mock_rule = next(r for r in rules if r.get("sequence_steps") is None)
    assert mock_rule["enabled"] == 1


def test_mock_from_flow_with_enabled_false(tmp_db):
    """enabled=False로 즉시 비활성화."""
    init_db(tmp_db)
    flow_id = _seed_flow(tmp_db)
    result = handle_mock_from_flow(tmp_db, {"flow_id": flow_id, "enabled": False})
    data = json.loads(result)
    assert "rule_id" in data
    rules = json.loads(handle_mock_list(tmp_db, {}))
    mock_rule = next(r for r in rules if r.get("sequence_steps") is None)
    assert mock_rule["enabled"] == 0


def test_mock_from_flow_with_body_override(tmp_db):
    """body 오버라이드 파라미터."""
    init_db(tmp_db)
    flow_id = _seed_flow(tmp_db, body='{"original": true}')
    result = handle_mock_from_flow(tmp_db, {
        "flow_id": flow_id,
        "body": '{"overridden": true}',
    })
    data = json.loads(result)
    assert "rule_id" in data
    rules = json.loads(handle_mock_list(tmp_db, {}))
    mock_rule = next(r for r in rules if r.get("sequence_steps") is None)
    assert mock_rule["response_body"] == '{"overridden": true}'
