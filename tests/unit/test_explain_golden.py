"""Golden-set tests for the explain heuristic engine.

Each case describes a realistic flow and asserts specific diagnostic strings appear.
Adding a new heuristic → add a case here.
"""

import base64
import json
import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.cli.explain_cmds import _diagnose, _parse_retry_after


def _make_flow(
    *,
    method="GET",
    host="api.example.com",
    path="/v1/thing",
    req_headers=None,
    req_body=None,
    req_ct=None,
    status=200,
    resp_headers=None,
    resp_body=None,
    resp_ct="application/json",
    duration_ms=50.0,
):
    return {
        "method": method,
        "scheme": "https",
        "host": host,
        "port": 443,
        "path": path,
        "query": None,
        "request_headers": json.dumps(req_headers or {}),
        "request_body": req_body,
        "request_content_type": req_ct,
        "status_code": status,
        "response_headers": json.dumps(resp_headers or {}),
        "response_body": resp_body,
        "response_content_type": resp_ct,
        "duration_ms": duration_ms,
    }


def _parse(flow):
    req_h = json.loads(flow["request_headers"])
    resp_h = json.loads(flow["response_headers"])
    return _diagnose(flow, flow["method"], flow["status_code"], req_h, resp_h)


def test_401_missing_auth_header():
    flow = _make_flow(status=401)
    findings = _parse(flow)
    assert any("401 Unauthorized" in f for f in findings)
    assert any("Authorization 헤더가 비어있음" in f for f in findings)


def test_401_expired_jwt():
    # JWT with exp far in the past (2001)
    payload = base64.urlsafe_b64encode(b'{"sub":"u","exp":1000000000}').decode().rstrip("=")
    token = f"header.{payload}.sig"
    flow = _make_flow(
        status=401,
        req_headers={"Authorization": f"Bearer {token}"},
    )
    findings = _parse(flow)
    assert any("JWT 토큰 만료" in f for f in findings)


def test_429_retry_after_seconds():
    flow = _make_flow(status=429, resp_headers={"Retry-After": "120"})
    findings = _parse(flow)
    assert any("Retry-After: 120s" in f for f in findings)


def test_429_no_retry_after():
    flow = _make_flow(status=429)
    findings = _parse(flow)
    assert any("백오프 간격을 서버가 명시 안 함" in f for f in findings)


def test_500_slow_response():
    flow = _make_flow(status=500, resp_body='{"err":"oops"}', duration_ms=4500.0)
    findings = _parse(flow)
    assert any("500" in f and "서버 에러" in f for f in findings)
    assert any("응답 지연" in f and "4500ms" in f for f in findings)


def test_content_type_json_body_is_not_json():
    flow = _make_flow(
        method="POST",
        req_headers={"Content-Type": "application/json"},
        req_body="not json",
        req_ct="application/json",
    )
    findings = _parse(flow)
    assert any("body가 JSON 형식이 아님" in f for f in findings)


def test_content_type_form_but_body_is_json():
    flow = _make_flow(
        method="POST",
        req_headers={"Content-Type": "application/x-www-form-urlencoded"},
        req_body='{"a":1}',
        req_ct="application/x-www-form-urlencoded",
    )
    findings = _parse(flow)
    assert any("Content-Type은 form-urlencoded인데 body가 JSON" in f for f in findings)


def test_cache_control_no_store():
    flow = _make_flow(status=200, resp_headers={"Cache-Control": "no-store, max-age=0"})
    findings = _parse(flow)
    assert any("no-store" in f for f in findings)


def test_304_not_modified():
    flow = _make_flow(status=304)
    findings = _parse(flow)
    assert any("304 Not Modified" in f for f in findings)


def test_cors_preflight_no_allow_origin():
    flow = _make_flow(
        method="OPTIONS",
        req_headers={"Access-Control-Request-Method": "POST"},
    )
    findings = _parse(flow)
    assert any("Access-Control-Allow-Origin 응답이 없음" in f for f in findings)


def test_parse_retry_after_seconds():
    assert _parse_retry_after("120") == 120


def test_parse_retry_after_http_date():
    # Any far-past date should return 0 (clamped)
    assert _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0


def test_parse_retry_after_garbage():
    assert _parse_retry_after("soon") is None
