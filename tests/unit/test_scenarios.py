"""Tests for core/scenarios.py — CRUD + step advance logic."""

import threading
import time
from collections import Counter

import pytest

from troxy.core.db import init_db, get_connection
from troxy.core.scenarios import (
    add_scenario,
    list_scenarios,
    remove_scenario,
    toggle_scenario,
    reset_scenario,
    resolve_scenario_ref,
    scenario_from_flows,
    get_and_advance_step,
)
from troxy.core.store import insert_flow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_steps(statuses: list[int]) -> list[dict]:
    return [{"status_code": s, "response_body": f"body-{s}"} for s in statuses]


def _make_flow_id(db_path: str, *, status_code: int = 200, path: str = "/api/data") -> int:
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


# ---------------------------------------------------------------------------
# add_scenario
# ---------------------------------------------------------------------------

def test_add_scenario_returns_id(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]))
    assert sid == 1


def test_add_scenario_multiple_returns_incrementing_ids(tmp_db):
    init_db(tmp_db)
    sid1 = add_scenario(tmp_db, steps=_make_steps([200]))
    sid2 = add_scenario(tmp_db, steps=_make_steps([404]))
    assert sid1 == 1
    assert sid2 == 2


def test_add_scenario_with_name(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, name="auth-retry", steps=_make_steps([401, 200]))
    scenarios = list_scenarios(tmp_db)
    assert scenarios[0]["name"] == "auth-retry"
    assert scenarios[0]["id"] == sid


def test_add_scenario_name_conflict_raises(tmp_db):
    init_db(tmp_db)
    add_scenario(tmp_db, name="dup", steps=_make_steps([200]))
    with pytest.raises(ValueError, match="dup"):
        add_scenario(tmp_db, name="dup", steps=_make_steps([500]))


def test_add_scenario_empty_steps_raises(tmp_db):
    init_db(tmp_db)
    with pytest.raises(ValueError):
        add_scenario(tmp_db, steps=[])


def test_add_scenario_stores_domain_and_path(tmp_db):
    init_db(tmp_db)
    add_scenario(
        tmp_db,
        domain="api.example.com",
        path_pattern="/v1/payments",
        method="POST",
        steps=_make_steps([500, 200]),
    )
    scenarios = list_scenarios(tmp_db)
    assert scenarios[0]["domain"] == "api.example.com"
    assert scenarios[0]["path_pattern"] == "/v1/payments"
    assert scenarios[0]["method"] == "POST"


def test_add_scenario_default_loop_is_false(tmp_db):
    init_db(tmp_db)
    add_scenario(tmp_db, steps=_make_steps([200]))
    scenarios = list_scenarios(tmp_db)
    assert scenarios[0]["loop"] == 0


def test_add_scenario_loop_true_stored(tmp_db):
    init_db(tmp_db)
    add_scenario(tmp_db, steps=_make_steps([200, 500]), loop=True)
    scenarios = list_scenarios(tmp_db)
    assert scenarios[0]["loop"] == 1


# ---------------------------------------------------------------------------
# list_scenarios
# ---------------------------------------------------------------------------

def test_list_scenarios_all(tmp_db):
    init_db(tmp_db)
    add_scenario(tmp_db, steps=_make_steps([200]))
    add_scenario(tmp_db, steps=_make_steps([500]))
    result = list_scenarios(tmp_db)
    assert len(result) == 2


def test_list_scenarios_enabled_only(tmp_db):
    init_db(tmp_db)
    sid1 = add_scenario(tmp_db, steps=_make_steps([200]))
    sid2 = add_scenario(tmp_db, steps=_make_steps([500]))
    toggle_scenario(tmp_db, sid2, enabled=False)
    result = list_scenarios(tmp_db, enabled_only=True)
    assert len(result) == 1
    assert result[0]["id"] == sid1


def test_list_scenarios_shows_total_steps(tmp_db):
    init_db(tmp_db)
    add_scenario(tmp_db, steps=_make_steps([200, 500, 503]))
    result = list_scenarios(tmp_db)
    assert result[0]["total_steps"] == 3


def test_list_scenarios_shows_current_step(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]))
    get_and_advance_step(tmp_db, sid)
    result = list_scenarios(tmp_db)
    assert result[0]["current_step"] == 1


# ---------------------------------------------------------------------------
# remove_scenario
# ---------------------------------------------------------------------------

def test_remove_scenario(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]))
    remove_scenario(tmp_db, sid)
    assert list_scenarios(tmp_db) == []


# ---------------------------------------------------------------------------
# toggle_scenario
# ---------------------------------------------------------------------------

def test_toggle_scenario_disable(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]))
    toggle_scenario(tmp_db, sid, enabled=False)
    result = list_scenarios(tmp_db)
    assert result[0]["enabled"] == 0


def test_toggle_scenario_reenable(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]))
    toggle_scenario(tmp_db, sid, enabled=False)
    toggle_scenario(tmp_db, sid, enabled=True)
    result = list_scenarios(tmp_db)
    assert result[0]["enabled"] == 1


# ---------------------------------------------------------------------------
# reset_scenario
# ---------------------------------------------------------------------------

def test_reset_scenario_rewinds_to_zero(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]))
    get_and_advance_step(tmp_db, sid)  # advance to step 1
    reset_scenario(tmp_db, sid)
    step = get_and_advance_step(tmp_db, sid)
    assert step["status_code"] == 200  # back to step 0


def test_reset_scenario_after_exhaustion(tmp_db):
    """loop=False 소진 후 reset → 처음부터."""
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]), loop=False)
    get_and_advance_step(tmp_db, sid)
    get_and_advance_step(tmp_db, sid)
    get_and_advance_step(tmp_db, sid)  # sticky last (500)
    reset_scenario(tmp_db, sid)
    step = get_and_advance_step(tmp_db, sid)
    assert step["status_code"] == 200


# ---------------------------------------------------------------------------
# resolve_scenario_ref
# ---------------------------------------------------------------------------

def test_resolve_scenario_ref_by_id(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]))
    assert resolve_scenario_ref(tmp_db, sid) == sid


def test_resolve_scenario_ref_by_name(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, name="my-scenario", steps=_make_steps([200]))
    assert resolve_scenario_ref(tmp_db, "my-scenario") == sid


def test_resolve_scenario_ref_not_found_raises(tmp_db):
    init_db(tmp_db)
    with pytest.raises(ValueError):
        resolve_scenario_ref(tmp_db, 999)


def test_resolve_scenario_ref_name_not_found_raises(tmp_db):
    init_db(tmp_db)
    with pytest.raises(ValueError):
        resolve_scenario_ref(tmp_db, "no-such-name")


# ---------------------------------------------------------------------------
# get_and_advance_step — happy path
# ---------------------------------------------------------------------------

def test_get_and_advance_step_two_step_sequence(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]))
    step1 = get_and_advance_step(tmp_db, sid)
    step2 = get_and_advance_step(tmp_db, sid)
    assert step1["status_code"] == 200
    assert step2["status_code"] == 500


def test_get_and_advance_step_returns_response_body(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=[
        {"status_code": 200, "response_body": '{"ok": true}'},
        {"status_code": 500, "response_body": '{"error": "oops"}'},
    ])
    step = get_and_advance_step(tmp_db, sid)
    assert step["response_body"] == '{"ok": true}'


def test_get_and_advance_step_returns_response_headers(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=[
        {"status_code": 200, "response_headers": {"X-Step": "1"}, "response_body": "a"},
        {"status_code": 200, "response_headers": {"X-Step": "2"}, "response_body": "b"},
    ])
    step1 = get_and_advance_step(tmp_db, sid)
    step2 = get_and_advance_step(tmp_db, sid)
    assert step1.get("response_headers", {}).get("X-Step") == "1"
    assert step2.get("response_headers", {}).get("X-Step") == "2"


def test_get_and_advance_step_missing_scenario_returns_none(tmp_db):
    init_db(tmp_db)
    result = get_and_advance_step(tmp_db, 999)
    assert result is None


def test_get_and_advance_step_disabled_returns_none(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]))
    toggle_scenario(tmp_db, sid, enabled=False)
    result = get_and_advance_step(tmp_db, sid)
    assert result is None


# ---------------------------------------------------------------------------
# get_and_advance_step — loop=False (sticky last)
# ---------------------------------------------------------------------------

def test_loop_false_sticky_last_two_steps(tmp_db):
    """마지막 step에서 멈춤 (소진 후 반복)."""
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]), loop=False)
    results = [get_and_advance_step(tmp_db, sid)["status_code"] for _ in range(4)]
    assert results == [200, 500, 500, 500]


def test_loop_false_single_step_always_same(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]), loop=False)
    results = [get_and_advance_step(tmp_db, sid)["status_code"] for _ in range(3)]
    assert results == [200, 200, 200]


def test_loop_false_four_steps(tmp_db):
    """4-step [200, 500, 503, 200] 소진 후 sticky last."""
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500, 503, 200]), loop=False)
    results = [get_and_advance_step(tmp_db, sid)["status_code"] for _ in range(5)]
    assert results == [200, 500, 503, 200, 200]


# ---------------------------------------------------------------------------
# get_and_advance_step — loop=True (cyclic)
# ---------------------------------------------------------------------------

def test_loop_true_two_steps_cycles(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]), loop=True)
    results = [get_and_advance_step(tmp_db, sid)["status_code"] for _ in range(4)]
    assert results == [200, 500, 200, 500]


def test_loop_true_single_step_always_same(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200]), loop=True)
    results = [get_and_advance_step(tmp_db, sid)["status_code"] for _ in range(3)]
    assert results == [200, 200, 200]


def test_loop_true_three_steps_seven_advances(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500, 503]), loop=True)
    results = [get_and_advance_step(tmp_db, sid)["status_code"] for _ in range(7)]
    assert results == [200, 500, 503, 200, 500, 503, 200]


# ---------------------------------------------------------------------------
# get_and_advance_step — step label is preserved but not required
# ---------------------------------------------------------------------------

def test_step_label_preserved(tmp_db):
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=[
        {"status_code": 200, "response_body": "ok", "label": "정상"},
    ])
    step = get_and_advance_step(tmp_db, sid)
    assert step.get("label") == "정상"


# ---------------------------------------------------------------------------
# Concurrency — atomic step advance
# ---------------------------------------------------------------------------

def test_get_and_advance_step_concurrent_no_duplicates(tmp_db):
    """10개 thread가 동시에 advance해도 각 step이 정확히 1번씩 할당되어야 한다."""
    init_db(tmp_db)
    n = 10
    steps = _make_steps(list(range(n)))
    sid = add_scenario(tmp_db, steps=steps, loop=False)

    results = []
    errors = []

    def worker():
        try:
            step = get_and_advance_step(tmp_db, sid)
            if step is not None:
                results.append(step["status_code"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    # loop=False: 처음 n번의 advance는 각 step을 한 번씩 반환해야 한다
    # (sticky last로 인해 일부 중복이 생길 수 있지만, status 0~n-1은 최소 1번씩)
    counts = Counter(results)
    # 첫 n개 unique step이 각 1번 이상 등장 확인
    for status in range(n):
        assert counts[status] >= 1, f"status {status} not returned"


def test_get_and_advance_step_two_threads_two_steps_no_lost_update(tmp_db):
    """2 thread, 2-step — lost update 없으면 각 step이 정확히 1번씩."""
    init_db(tmp_db)
    sid = add_scenario(tmp_db, steps=_make_steps([200, 500]), loop=False)

    results = []

    def worker():
        step = get_and_advance_step(tmp_db, sid)
        if step:
            results.append(step["status_code"])

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 두 번의 advance: 200 한 번, 500 한 번 (순서는 임의)
    assert sorted(results) == [200, 500]


# ---------------------------------------------------------------------------
# scenario_from_flows
# ---------------------------------------------------------------------------

def test_scenario_from_flows_creates_steps_in_order(tmp_db):
    init_db(tmp_db)
    fid1 = _make_flow_id(tmp_db, status_code=200)
    fid2 = _make_flow_id(tmp_db, status_code=401)
    fid3 = _make_flow_id(tmp_db, status_code=200)

    sid = scenario_from_flows(tmp_db, [fid1, fid2, fid3])
    step1 = get_and_advance_step(tmp_db, sid)
    step2 = get_and_advance_step(tmp_db, sid)
    step3 = get_and_advance_step(tmp_db, sid)

    assert step1["status_code"] == 200
    assert step2["status_code"] == 401
    assert step3["status_code"] == 200


def test_scenario_from_flows_preserves_response_body(tmp_db):
    init_db(tmp_db)
    fid = _make_flow_id(tmp_db, status_code=200)
    sid = scenario_from_flows(tmp_db, [fid])
    step = get_and_advance_step(tmp_db, sid)
    assert step["response_body"] == '{"status": 200}'


def test_scenario_from_flows_with_name(tmp_db):
    init_db(tmp_db)
    fid = _make_flow_id(tmp_db, status_code=200)
    sid = scenario_from_flows(tmp_db, [fid], name="login-seq")
    scenarios = list_scenarios(tmp_db)
    assert scenarios[0]["name"] == "login-seq"


def test_scenario_from_flows_missing_flow_raises(tmp_db):
    init_db(tmp_db)
    with pytest.raises(ValueError):
        scenario_from_flows(tmp_db, [9999])


# ---------------------------------------------------------------------------
# DB schema — mock_scenarios table created by init_db
# ---------------------------------------------------------------------------

def test_db_has_mock_scenarios_table_after_init(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "mock_scenarios" in tables


def test_existing_db_reinit_does_not_error(tmp_db):
    """기존 DB에 init_db 재실행 시 에러 없음 (CREATE TABLE IF NOT EXISTS)."""
    init_db(tmp_db)
    add_scenario(tmp_db, steps=_make_steps([200]))
    init_db(tmp_db)  # 재실행 — 기존 row 유지
    assert len(list_scenarios(tmp_db)) == 1
