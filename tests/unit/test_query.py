"""Tests for flow querying and filtering."""

import time

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.core.query import list_flows, get_flow, search_flows


def _seed_flows(db_path):
    """Insert test flows and return their IDs."""
    init_db(db_path)
    now = time.time()
    ids = []
    flows = [
        {"method": "GET", "host": "api.example.com", "path": "/users", "status_code": 200,
         "response_body": '{"users": []}', "timestamp": now - 300},
        {"method": "POST", "host": "api.example.com", "path": "/users", "status_code": 201,
         "request_body": '{"name": "test"}', "response_body": '{"id": 1}', "timestamp": now - 200},
        {"method": "GET", "host": "api.internal.com", "path": "/api/ratings", "status_code": 401,
         "response_body": '{"error": "unauthorized", "token": "expired"}', "timestamp": now - 100},
        {"method": "GET", "host": "cdn.example.com", "path": "/image.png", "status_code": 200,
         "response_body": "b64:iVBORw0KGgo=", "response_content_type": "image/png", "timestamp": now},
    ]
    for f in flows:
        base = {
            "timestamp": f.get("timestamp", now),
            "method": f["method"], "scheme": "https", "host": f["host"],
            "port": 443, "path": f["path"], "query": None,
            "request_headers": {"Accept": "*/*"},
            "request_body": f.get("request_body"),
            "request_content_type": "application/json",
            "status_code": f["status_code"],
            "response_headers": {"Content-Type": "application/json"},
            "response_body": f.get("response_body"),
            "response_content_type": f.get("response_content_type", "application/json"),
            "duration_ms": 50.0,
        }
        ids.append(insert_flow(db_path, **base))
    return ids


def test_list_flows_returns_all(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db)
    assert len(flows) == 4


def test_list_flows_ordered_by_timestamp_desc(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db)
    assert flows[0]["host"] == "cdn.example.com"
    assert flows[-1]["host"] == "api.example.com"


def test_list_flows_filter_by_domain(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db, domain="internal")
    assert len(flows) == 1
    assert flows[0]["host"] == "api.internal.com"


def test_list_flows_filter_by_status(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db, status=401)
    assert len(flows) == 1
    assert flows[0]["status_code"] == 401


def test_list_flows_filter_by_method(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db, method="POST")
    assert len(flows) == 1
    assert flows[0]["method"] == "POST"


def test_list_flows_filter_by_path(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db, path="ratings")
    assert len(flows) == 1


def test_list_flows_with_limit(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db, limit=2)
    assert len(flows) == 2


def test_list_flows_filter_by_since(tmp_db):
    _seed_flows(tmp_db)
    flows = list_flows(tmp_db, since_seconds=150)
    assert len(flows) == 2


def test_get_flow_by_id(tmp_db):
    ids = _seed_flows(tmp_db)
    flow = get_flow(tmp_db, ids[2])
    assert flow["host"] == "api.internal.com"
    assert flow["status_code"] == 401
    assert "unauthorized" in flow["response_body"]


def test_get_flow_not_found(tmp_db):
    _seed_flows(tmp_db)
    flow = get_flow(tmp_db, 999)
    assert flow is None


def test_search_flows_in_body(tmp_db):
    _seed_flows(tmp_db)
    results = search_flows(tmp_db, "unauthorized")
    assert len(results) == 1
    assert results[0]["host"] == "api.internal.com"


def test_search_flows_in_request_body(tmp_db):
    _seed_flows(tmp_db)
    results = search_flows(tmp_db, "test", scope="request")
    assert len(results) == 1
    assert results[0]["method"] == "POST"


def test_search_flows_with_domain_filter(tmp_db):
    _seed_flows(tmp_db)
    results = search_flows(tmp_db, "token", domain="internal")
    assert len(results) == 1


def test_search_flows_no_results(tmp_db):
    _seed_flows(tmp_db)
    results = search_flows(tmp_db, "nonexistent_string_xyz")
    assert len(results) == 0
