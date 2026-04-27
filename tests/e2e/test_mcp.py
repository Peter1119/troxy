"""E2E tests for MCP server tools."""

import base64
import json
import time

from troxy.core.db import init_db, get_connection
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
                host="api.internal.com", port=443, path="/api/users", query=None,
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
    result = handle_list_flows(tmp_db, {"domain": "internal"})
    data = json.loads(result)
    assert len(data) == 1


def test_handle_get_flow(tmp_db):
    _seed(tmp_db)
    result = handle_get_flow(tmp_db, {"id": 2})
    data = json.loads(result)
    assert data["host"] == "api.internal.com"
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


def _seed_form_flow(db_path, body_bytes, content_type="application/x-www-form-urlencoded"):
    init_db(db_path)
    insert_flow(db_path, timestamp=time.time(), method="POST", scheme="https",
                host="api.example.com", port=443, path="/api/orders", query=None,
                request_headers={"Content-Type": content_type},
                request_body=body_bytes, request_content_type=content_type,
                status_code=200, response_headers={}, response_body="{}",
                response_content_type="application/json", duration_ms=10.0)


def test_handle_get_flow_form_part_parses_form(tmp_db):
    _seed_form_flow(tmp_db, b"a=1&b=Ticket%3A%3ATall")
    result = handle_get_flow(tmp_db, {"id": 1, "part": "form"})
    data = json.loads(result)
    assert data["fields"] == {"a": "1", "b": "Ticket::Tall"}
    assert data["truncated"] is False


def test_handle_get_flow_form_part_decodes_legacy_b64(tmp_db):
    init_db(tmp_db)
    body = b"receipt_data=" + b"A" * 500 + b"&ticket_type=Ticket%3A%3ATall"
    legacy_stored = "b64:" + base64.b64encode(body).decode("ascii")
    insert_flow(tmp_db, timestamp=time.time(), method="POST", scheme="https",
                host="api.example.com", port=443, path="/api/orders", query=None,
                request_headers={"Content-Type": "application/x-www-form-urlencoded"},
                request_body=None, request_content_type="application/x-www-form-urlencoded",
                status_code=200, response_headers={}, response_body=None,
                response_content_type=None, duration_ms=10.0)
    conn = get_connection(tmp_db)
    conn.execute("UPDATE flows SET request_body = ? WHERE id = 1", (legacy_stored,))
    conn.commit()
    conn.close()
    result = handle_get_flow(tmp_db, {"id": 1, "part": "form"})
    data = json.loads(result)
    assert data["fields"]["ticket_type"] == "Ticket::Tall"
    assert isinstance(data["fields"]["receipt_data"], dict)
    assert data["fields"]["receipt_data"]["_kind"] == "binary-base64"


def test_handle_get_flow_form_part_rejects_non_form(tmp_db):
    init_db(tmp_db)
    insert_flow(tmp_db, timestamp=time.time(), method="POST", scheme="https",
                host="api.example.com", port=443, path="/api/users", query=None,
                request_headers={"Content-Type": "application/json"},
                request_body='{"a": 1}', request_content_type="application/json",
                status_code=200, response_headers={}, response_body="{}",
                response_content_type="application/json", duration_ms=10.0)
    result = handle_get_flow(tmp_db, {"id": 1, "part": "form"})
    data = json.loads(result)
    assert data["error"] == "not form-urlencoded"
    assert data["content_type"] == "application/json"


def test_handle_get_flow_form_part_empty_body(tmp_db):
    _seed_form_flow(tmp_db, None)
    result = handle_get_flow(tmp_db, {"id": 1, "part": "form"})
    data = json.loads(result)
    assert data == {"fields": {}, "truncated": False}
