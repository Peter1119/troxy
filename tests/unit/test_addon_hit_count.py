"""Tests for addon hit_count increment on mock match."""

import time

import pytest

from troxy.core.db import init_db, get_connection
from troxy.core.mock import add_mock_rule, list_mock_rules, toggle_mock_rule


def test_hit_count_increment_sql(tmp_db):
    """Verify the SQL update that addon uses to bump hit_count."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="example.com", path_pattern="/api/*",
        status_code=200, response_body='{"ok": true}',
    )

    # Simulate what addon._check_mock does after a match
    conn = get_connection(db)
    conn.execute(
        "UPDATE mock_rules SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
        (time.time(), rule_id),
    )
    conn.commit()
    conn.close()

    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 1
    assert rule["last_hit_at"] is not None


def test_hit_count_increments_multiple_times(tmp_db):
    """Verify hit_count accumulates across multiple matches."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="example.com", path_pattern="/api/*",
        status_code=200, response_body='{"ok": true}',
    )

    for _ in range(5):
        conn = get_connection(db)
        conn.execute(
            "UPDATE mock_rules SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
            (time.time(), rule_id),
        )
        conn.commit()
        conn.close()

    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 5


def test_hit_count_default_zero(tmp_db):
    """New mock rules start with hit_count=0."""
    db = str(tmp_db)
    init_db(db)
    add_mock_rule(
        db, domain="example.com", path_pattern="/api/*",
        status_code=200, response_body='{"ok": true}',
    )
    rules = list_mock_rules(db)
    assert rules[0]["hit_count"] == 0
    assert rules[0]["last_hit_at"] is None


# -- integration tests: drive TroxyAddon._check_mock with real mitmproxy flows --

_mitmproxy_test = pytest.importorskip("mitmproxy.test")


def _make_addon(db_path: str):
    """Build a TroxyAddon bound to a test DB without touching the global default."""
    from troxy.addon import TroxyAddon

    addon = TroxyAddon.__new__(TroxyAddon)
    addon.db_path = db_path
    addon._intercepted_flows = {}
    return addon


def _make_flow(host: str, path: str, method: str = "GET"):
    from mitmproxy.test import tflow, tutils

    return tflow.tflow(
        req=tutils.treq(host=host, path=path, method=method.encode("ascii"))
    )


def test_addon_mock_match_increments_hit_count(tmp_db):
    """End-to-end: addon._check_mock matches a rule → hit_count bumps + response injected."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/*",
        status_code=201, response_body='{"mocked": true}',
    )
    addon = _make_addon(db)
    flow = _make_flow("api.example.com", "/api/users/42")

    addon._check_mock(flow)

    assert flow.response is not None
    assert flow.response.status_code == 201
    assert flow.response.content == b'{"mocked": true}'
    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 1
    assert rule["last_hit_at"] is not None


def test_addon_mock_no_match_does_not_bump(tmp_db):
    """Path pattern miss → no hit_count change, no response injected."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/*",
        status_code=200, response_body="ok",
    )
    addon = _make_addon(db)
    flow = _make_flow("api.example.com", "/public/home")

    addon._check_mock(flow)

    assert flow.response is None
    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 0
    assert rule["last_hit_at"] is None


def test_addon_mock_repeated_requests_accumulate(tmp_db):
    """Three matching requests → hit_count = 3."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/*",
        status_code=200, response_body="ok",
    )
    addon = _make_addon(db)

    for i in range(3):
        flow = _make_flow("api.example.com", f"/api/items/{i}")
        addon._check_mock(flow)
        assert flow.response is not None

    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 3


def test_addon_disabled_rule_not_counted(tmp_db):
    """Disabled rule → _check_mock skips it, no hit_count change."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/*",
        status_code=200, response_body="ok",
    )
    toggle_mock_rule(db, rule_id, enabled=False)
    addon = _make_addon(db)
    flow = _make_flow("api.example.com", "/api/users/1")

    addon._check_mock(flow)

    assert flow.response is None
    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 0


def test_addon_first_matching_rule_wins(tmp_db):
    """Multiple matching rules → only the first one bumps hit_count."""
    db = str(tmp_db)
    init_db(db)
    rule_a = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/*",
        status_code=200, response_body="A",
    )
    rule_b = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/users/*",
        status_code=200, response_body="B",
    )
    addon = _make_addon(db)
    flow = _make_flow("api.example.com", "/api/users/1")

    addon._check_mock(flow)

    assert flow.response.content == b"A"
    rules = {r["id"]: r for r in list_mock_rules(db)}
    assert rules[rule_a]["hit_count"] == 1
    assert rules[rule_b]["hit_count"] == 0


def test_addon_method_mismatch_skips_rule(tmp_db):
    """Rule scoped to POST should not match a GET request."""
    db = str(tmp_db)
    init_db(db)
    rule_id = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/*",
        method="POST", status_code=200, response_body="ok",
    )
    addon = _make_addon(db)
    flow = _make_flow("api.example.com", "/api/users", method="GET")

    addon._check_mock(flow)

    assert flow.response is None
    rules = list_mock_rules(db)
    rule = next(r for r in rules if r["id"] == rule_id)
    assert rule["hit_count"] == 0
