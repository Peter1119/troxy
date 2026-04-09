"""Tests for flow export to curl/httpie."""

import json

from troxy.core.export import export_curl, export_httpie


def _make_flow_row(**overrides):
    base = {
        "method": "GET",
        "scheme": "https",
        "host": "api.example.com",
        "port": 443,
        "path": "/api/users",
        "query": "page=1",
        "request_headers": json.dumps({"Accept": "application/json", "Authorization": "Bearer tok"}),
        "request_body": None,
    }
    base.update(overrides)
    return base


def test_export_curl_get(tmp_db):
    flow = _make_flow_row()
    result = export_curl(flow)
    assert result.startswith("curl")
    assert "https://api.example.com/api/users?page=1" in result
    assert "-H 'Accept: application/json'" in result
    assert "-H 'Authorization: Bearer tok'" in result


def test_export_curl_post_with_body():
    flow = _make_flow_row(
        method="POST",
        request_body='{"name": "test"}',
    )
    result = export_curl(flow)
    assert "-X POST" in result
    assert "-d '{\"name\": \"test\"}'" in result


def test_export_curl_custom_port():
    flow = _make_flow_row(port=8080)
    result = export_curl(flow)
    assert "api.example.com:8080" in result


def test_export_curl_no_query():
    flow = _make_flow_row(query=None)
    result = export_curl(flow)
    assert "https://api.example.com/api/users'" in result or \
           "https://api.example.com/api/users" in result


def test_export_httpie_get():
    flow = _make_flow_row()
    result = export_httpie(flow)
    assert result.startswith("http")
    assert "https://api.example.com/api/users" in result
    assert "Accept:application/json" in result


def test_export_httpie_post_with_body():
    flow = _make_flow_row(
        method="POST",
        request_body='{"name": "test"}',
        request_headers=json.dumps({"Content-Type": "application/json"}),
    )
    result = export_httpie(flow)
    assert "POST" in result
