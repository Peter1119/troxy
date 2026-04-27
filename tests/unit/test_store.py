"""Tests for flow storage."""

import json
import time

from troxy.core.db import init_db, get_connection
from troxy.core.store import insert_flow


def _make_flow(**overrides):
    base = {
        "timestamp": time.time(),
        "method": "GET",
        "scheme": "https",
        "host": "api.example.com",
        "port": 443,
        "path": "/api/users",
        "query": "page=1",
        "request_headers": {"Accept": "application/json"},
        "request_body": None,
        "request_content_type": "application/json",
        "status_code": 200,
        "response_headers": {"Content-Type": "application/json"},
        "response_body": '{"id": 1}',
        "response_content_type": "application/json",
        "duration_ms": 42.5,
    }
    base.update(overrides)
    return base


def test_insert_flow_returns_id(tmp_db):
    init_db(tmp_db)
    flow_id = insert_flow(tmp_db, **_make_flow())
    assert flow_id == 1


def test_insert_flow_stores_all_fields(tmp_db):
    init_db(tmp_db)
    flow_data = _make_flow(
        method="POST",
        host="api.internal.com",
        path="/api/users",
        status_code=401,
        response_body='{"error": "unauthorized"}',
    )
    flow_id = insert_flow(tmp_db, **flow_data)
    conn = get_connection(tmp_db)
    row = conn.execute("SELECT * FROM flows WHERE id = ?", (flow_id,)).fetchone()
    assert row["method"] == "POST"
    assert row["host"] == "api.internal.com"
    assert row["status_code"] == 401
    assert row["response_body"] == '{"error": "unauthorized"}'
    conn.close()


def test_insert_flow_serializes_headers_as_json(tmp_db):
    init_db(tmp_db)
    headers = {"Authorization": "Bearer token", "Accept": "application/json"}
    insert_flow(tmp_db, **_make_flow(request_headers=headers))
    conn = get_connection(tmp_db)
    row = conn.execute("SELECT request_headers FROM flows WHERE id = 1").fetchone()
    parsed = json.loads(row["request_headers"])
    assert parsed["Authorization"] == "Bearer token"
    conn.close()


def test_insert_flow_handles_binary_body(tmp_db):
    init_db(tmp_db)
    binary_body = b"\x89PNG\r\n\x1a\n"
    insert_flow(tmp_db, **_make_flow(
        response_body=binary_body,
        response_content_type="image/png",
    ))
    conn = get_connection(tmp_db)
    row = conn.execute("SELECT response_body FROM flows WHERE id = 1").fetchone()
    assert row["response_body"].startswith("b64:")
    conn.close()


def test_insert_flow_handles_none_body(tmp_db):
    init_db(tmp_db)
    insert_flow(tmp_db, **_make_flow(request_body=None, response_body=None))
    conn = get_connection(tmp_db)
    row = conn.execute("SELECT request_body, response_body FROM flows WHERE id = 1").fetchone()
    assert row["request_body"] is None
    assert row["response_body"] is None
    conn.close()


def test_insert_multiple_flows_increments_id(tmp_db):
    init_db(tmp_db)
    id1 = insert_flow(tmp_db, **_make_flow())
    id2 = insert_flow(tmp_db, **_make_flow())
    assert id1 == 1
    assert id2 == 2


def test_form_urlencoded_body_stored_as_text(tmp_db):
    init_db(tmp_db)
    body = b"a=1&b=Ticket%3A%3ATall"
    insert_flow(tmp_db, **_make_flow(
        method="POST",
        request_body=body,
        request_content_type="application/x-www-form-urlencoded",
    ))
    conn = get_connection(tmp_db)
    row = conn.execute("SELECT request_body FROM flows WHERE id = 1").fetchone()
    assert row["request_body"] == "a=1&b=Ticket%3A%3ATall"
    assert not row["request_body"].startswith("b64:")
    conn.close()


def test_form_urlencoded_with_charset_param_stored_as_text(tmp_db):
    init_db(tmp_db)
    body = b"a=1&b=2"
    insert_flow(tmp_db, **_make_flow(
        method="POST",
        request_body=body,
        request_content_type="application/x-www-form-urlencoded; charset=utf-8",
    ))
    conn = get_connection(tmp_db)
    row = conn.execute("SELECT request_body FROM flows WHERE id = 1").fetchone()
    assert row["request_body"] == "a=1&b=2"
    conn.close()
