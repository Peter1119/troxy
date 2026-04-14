"""Tests for mock_from_status shortcut."""

import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.core.mock import mock_from_status, list_mock_rules


def _seed(db_path, status_code, host="api.example.com", ts=None):
    insert_flow(
        db_path,
        timestamp=ts or time.time(),
        method="GET",
        scheme="https",
        host=host,
        port=443,
        path="/v1/thing",
        query=None,
        request_headers={"Authorization": "Bearer x"},
        request_body=None,
        request_content_type=None,
        status_code=status_code,
        response_headers={"Content-Type": "application/json"},
        response_body='{"err":"x"}',
        response_content_type="application/json",
        duration_ms=12.0,
    )


def test_mock_from_status_uses_most_recent(tmp_db):
    init_db(tmp_db)
    now = time.time()
    _seed(tmp_db, 401, ts=now - 100)
    _seed(tmp_db, 401, ts=now - 10)   # most recent 401
    _seed(tmp_db, 200, ts=now - 5)    # newer, but different status

    rule_id = mock_from_status(tmp_db, 401)
    rules = list_mock_rules(tmp_db)
    assert len(rules) == 1
    assert rules[0]["id"] == rule_id
    assert rules[0]["status_code"] == 401


def test_mock_from_status_respects_domain_filter(tmp_db):
    init_db(tmp_db)
    _seed(tmp_db, 401, host="a.example.com")
    _seed(tmp_db, 401, host="b.example.com")

    mock_from_status(tmp_db, 401, domain="b.example")
    rules = list_mock_rules(tmp_db)
    assert rules[0]["domain"] == "b.example.com"


def test_mock_from_status_raises_when_no_match(tmp_db):
    init_db(tmp_db)
    _seed(tmp_db, 200)

    with pytest.raises(ValueError):
        mock_from_status(tmp_db, 401)
