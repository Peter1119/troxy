"""E2E tests for MCP server tools."""

import json
import time

from troxy.core.db import init_db
from troxy.core.store import insert_flow

from troxy.mcp.server import (
    handle_list_flows, handle_get_flow, handle_search, handle_export,
    handle_status, handle_mock_add, handle_mock_list,
)


def _seed(db_path):
    init_db(db_path)
    insert_flow(db_path, timestamp=time.time(), method="GET", scheme="https",
                host="api.example.com", port=443, path="/users", query="page=1",
                request_headers={"Accept": "application/json"}, request_body=None,
                request_content_type=None, status_code=200,
                response_headers={"Content-Type": "application/json"},
                response_body='{"users": []}', response_content_type="application/json",
                duration_ms=42.0)
    insert_flow(db_path, timestamp=time.time(), method="POST", scheme="https",
                host="pedia.watcha.com", port=443, path="/api/users", query=None,
                request_headers={"Content-Type": "application/json"},
                request_body='{"email": "test@test.com"}',
                request_content_type="application/json", status_code=401,
                response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized"}',
                response_content_type="application/json", duration_ms=30.0)


def test_handle_list_flows(tmp_db):
    _seed(tmp_db)
    result = handle_list_flows(tmp_db, {})
    data = json.loads(result)
    assert len(data) == 2


def test_handle_list_flows_with_filter(tmp_db):
    _seed(tmp_db)
    result = handle_list_flows(tmp_db, {"domain": "watcha"})
    data = json.loads(result)
    assert len(data) == 1


def test_handle_get_flow(tmp_db):
    _seed(tmp_db)
    result = handle_get_flow(tmp_db, {"id": 2})
    data = json.loads(result)
    assert data["host"] == "pedia.watcha.com"
    assert "unauthorized" in data["response_body"]


def test_handle_get_flow_body_only(tmp_db):
    _seed(tmp_db)
    result = handle_get_flow(tmp_db, {"id": 2, "part": "body"})
    data = json.loads(result)
    assert "request_body" in data
    assert "response_body" in data


def test_handle_search(tmp_db):
    _seed(tmp_db)
    result = handle_search(tmp_db, {"query": "unauthorized"})
    data = json.loads(result)
    assert len(data) == 1


def test_handle_export_curl(tmp_db):
    _seed(tmp_db)
    result = handle_export(tmp_db, {"id": 1, "format": "curl"})
    assert "curl" in result
    assert "api.example.com" in result


def test_handle_status(tmp_db):
    _seed(tmp_db)
    result = handle_status(tmp_db, {})
    data = json.loads(result)
    assert data["flow_count"] == 2


def test_handle_mock_add(tmp_db):
    init_db(tmp_db)
    result = handle_mock_add(tmp_db, {
        "domain": "api.example.com",
        "path_pattern": "/users",
        "status_code": 200,
        "body": '{"mock": true}',
    })
    data = json.loads(result)
    assert data["rule_id"] == 1


def test_handle_mock_list(tmp_db):
    init_db(tmp_db)
    handle_mock_add(tmp_db, {"path_pattern": "/a", "status_code": 200})
    result = handle_mock_list(tmp_db, {})
    data = json.loads(result)
    assert len(data) == 1
