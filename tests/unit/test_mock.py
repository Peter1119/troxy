"""Tests for mock rules CRUD."""

import time

from troxy.core.db import init_db
from troxy.core.mock import (
    add_mock_rule, list_mock_rules, remove_mock_rule, toggle_mock_rule,
    mock_from_flow, suggest_glob,
)
from troxy.core.store import insert_flow


def test_add_mock_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_mock_rule(tmp_db, domain="api.example.com", path_pattern="/api/users/*",
                            method="GET", status_code=200, response_body='{"mock": true}')
    assert rule_id == 1


def test_list_mock_rules(tmp_db):
    init_db(tmp_db)
    add_mock_rule(tmp_db, domain="api.example.com", path_pattern="/users", status_code=200)
    add_mock_rule(tmp_db, domain="cdn.example.com", path_pattern="/img", status_code=404)
    rules = list_mock_rules(tmp_db)
    assert len(rules) == 2


def test_list_mock_rules_enabled_only(tmp_db):
    init_db(tmp_db)
    add_mock_rule(tmp_db, domain="a.com", path_pattern="/", status_code=200)
    rule_id = add_mock_rule(tmp_db, domain="b.com", path_pattern="/", status_code=200)
    toggle_mock_rule(tmp_db, rule_id, enabled=False)
    rules = list_mock_rules(tmp_db, enabled_only=True)
    assert len(rules) == 1
    assert rules[0]["domain"] == "a.com"


def test_remove_mock_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_mock_rule(tmp_db, domain="a.com", path_pattern="/", status_code=200)
    remove_mock_rule(tmp_db, rule_id)
    rules = list_mock_rules(tmp_db)
    assert len(rules) == 0


def test_toggle_mock_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_mock_rule(tmp_db, domain="a.com", path_pattern="/", status_code=200)
    toggle_mock_rule(tmp_db, rule_id, enabled=False)
    rules = list_mock_rules(tmp_db)
    assert rules[0]["enabled"] == 0
    toggle_mock_rule(tmp_db, rule_id, enabled=True)
    rules = list_mock_rules(tmp_db)
    assert rules[0]["enabled"] == 1


def test_mock_from_flow(tmp_db):
    init_db(tmp_db)
    flow_id = insert_flow(tmp_db, timestamp=time.time(), method="GET", scheme="https",
                          host="api.example.com", port=443, path="/api/data", query=None,
                          request_headers={}, request_body=None, request_content_type=None,
                          status_code=200, response_headers={"Content-Type": "application/json"},
                          response_body='{"data": [1,2,3]}', response_content_type="application/json",
                          duration_ms=50)
    rule_id = mock_from_flow(tmp_db, flow_id)
    rules = list_mock_rules(tmp_db)
    assert len(rules) == 1
    assert rules[0]["domain"] == "api.example.com"
    assert rules[0]["path_pattern"] == "/api/data"
    assert rules[0]["response_body"] == '{"data": [1,2,3]}'


def test_mock_from_flow_with_status_override(tmp_db):
    init_db(tmp_db)
    flow_id = insert_flow(tmp_db, timestamp=time.time(), method="GET", scheme="https",
                          host="api.example.com", port=443, path="/api/data", query=None,
                          request_headers={}, request_body=None, request_content_type=None,
                          status_code=200, response_headers={},
                          response_body='{"ok": true}', response_content_type="application/json",
                          duration_ms=50)
    rule_id = mock_from_flow(tmp_db, flow_id, status_code=500)
    rules = list_mock_rules(tmp_db)
    assert rules[0]["status_code"] == 500


# -- suggest_glob tests --


def test_suggest_glob_numeric_segments():
    assert suggest_glob("/api/users/12345/ratings") == "/api/users/*/ratings"


def test_suggest_glob_uuid():
    assert suggest_glob("/api/users/17ovVJlDr1vzy/ratings/2026/4") == "/api/users/*/ratings/*/*"


def test_suggest_glob_no_dynamic():
    assert suggest_glob("/api/users") == "/api/users"


def test_suggest_glob_mixed():
    assert suggest_glob("/api/v2/movies/123/reviews") == "/api/v2/movies/*/reviews"


def test_suggest_glob_uuid_dashed():
    assert suggest_glob("/api/items/550e8400-e29b-41d4-a716-446655440000/detail") == "/api/items/*/detail"


def test_suggest_glob_root():
    assert suggest_glob("/") == "/"


def test_suggest_glob_short_alpha_kept():
    """Short alpha segments like 'v2', 'api' should NOT be replaced."""
    assert suggest_glob("/api/v2/users") == "/api/v2/users"


def test_suggest_glob_trailing_slash_normalized():
    """Trailing slash is dropped (handled by strip)."""
    assert suggest_glob("/api/users/123/") == "/api/users/*"


def test_suggest_glob_single_dynamic_segment():
    """Top-level dynamic segment like /12345 -> /*."""
    assert suggest_glob("/12345") == "/*"


def test_suggest_glob_empty_string():
    """Empty path normalized to '/'."""
    assert suggest_glob("") == "/"


def test_suggest_glob_file_extension_preserved():
    """Segments with a dot (file extensions) are NOT replaced, to avoid
    over-matching resources like /static/logo.png or /files/abc.json."""
    assert suggest_glob("/static/logo.png") == "/static/logo.png"
    assert suggest_glob("/files/abc123.json") == "/files/abc123.json"


def test_suggest_glob_slug_with_dash_preserved():
    """Slugs with dashes (not UUIDs) should NOT be replaced."""
    assert suggest_glob("/movies/my-awesome-movie/reviews") == "/movies/my-awesome-movie/reviews"


def test_suggest_glob_base64_like_token():
    """Long alphanumeric tokens (>= 10 chars) treated as dynamic."""
    assert suggest_glob("/api/tokens/abc123DEF456xyz") == "/api/tokens/*"


def test_suggest_glob_preserves_non_ascii():
    """Non-ASCII segments (e.g. locale codes, paths with hangul) pass through."""
    assert suggest_glob("/api/ko-KR/users") == "/api/ko-KR/users"
