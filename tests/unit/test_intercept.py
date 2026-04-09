"""Tests for intercept rules and pending flows."""

from troxy.core.db import init_db
from troxy.core.intercept import (
    add_intercept_rule, list_intercept_rules, remove_intercept_rule,
    add_pending_flow, list_pending_flows, update_pending_flow,
    get_pending_flow,
)
import time


def test_add_intercept_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_intercept_rule(tmp_db, domain="api.example.com", method="POST")
    assert rule_id == 1


def test_list_intercept_rules(tmp_db):
    init_db(tmp_db)
    add_intercept_rule(tmp_db, domain="a.com")
    add_intercept_rule(tmp_db, domain="b.com")
    rules = list_intercept_rules(tmp_db)
    assert len(rules) == 2


def test_remove_intercept_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_intercept_rule(tmp_db, domain="a.com")
    remove_intercept_rule(tmp_db, rule_id)
    assert len(list_intercept_rules(tmp_db)) == 0


def test_add_pending_flow(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="abc-123", method="POST",
                             host="api.example.com", path="/api/users",
                             request_headers='{"Content-Type": "application/json"}',
                             request_body='{"name": "test"}')
    assert pf_id == 1


def test_list_pending_flows(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="a", method="GET", host="a.com", path="/",
                     request_headers="{}", request_body=None)
    add_pending_flow(tmp_db, flow_id="b", method="POST", host="b.com", path="/",
                     request_headers="{}", request_body=None)
    pending = list_pending_flows(tmp_db)
    assert len(pending) == 2


def test_list_pending_flows_only_pending(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="a", method="GET", host="a.com", path="/",
                             request_headers="{}", request_body=None)
    add_pending_flow(tmp_db, flow_id="b", method="GET", host="b.com", path="/",
                     request_headers="{}", request_body=None)
    update_pending_flow(tmp_db, pf_id, status="released")
    pending = list_pending_flows(tmp_db)
    assert len(pending) == 1


def test_update_pending_flow_modify_headers(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="a", method="GET", host="a.com", path="/",
                             request_headers='{"Auth": "old"}', request_body=None)
    update_pending_flow(tmp_db, pf_id, request_headers='{"Auth": "new"}', status="modified")
    pf = get_pending_flow(tmp_db, pf_id)
    assert pf["request_headers"] == '{"Auth": "new"}'
    assert pf["status"] == "modified"


def test_update_pending_flow_modify_body(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="a", method="POST", host="a.com", path="/",
                             request_headers="{}", request_body='{"old": true}')
    update_pending_flow(tmp_db, pf_id, request_body='{"new": true}', status="modified")
    pf = get_pending_flow(tmp_db, pf_id)
    assert pf["request_body"] == '{"new": true}'
