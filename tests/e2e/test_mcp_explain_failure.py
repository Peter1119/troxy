"""E2E tests for troxy_explain_failure MCP tool."""

import json
import time

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.mcp.server import handle_explain_failure


def _insert(db_path, *, method="GET", host="api.example.com", path="/users",
            status=200, body=None, ts=None, duration_ms=50.0):
    init_db(db_path)
    insert_flow(
        db_path,
        timestamp=ts or time.time(),
        method=method,
        scheme="https",
        host=host,
        port=443,
        path=path,
        query=None,
        request_headers={"Accept": "application/json"},
        request_body=None,
        request_content_type=None,
        status_code=status,
        response_headers={"Content-Type": "application/json"},
        response_body=body,
        response_content_type="application/json",
        duration_ms=duration_ms,
    )


def _seed_mixed(db_path):
    """Seed a realistic session: 1 success + 3 failures across different patterns."""
    _insert(db_path, status=200, path="/healthz")
    _insert(db_path, status=401, path="/api/me", body='{"error":"token_expired"}')
    _insert(db_path, status=401, path="/api/profile", body='{"error":"token_expired"}')
    _insert(db_path, status=500, path="/api/upload", body='{"error":"internal error"}')
    _insert(db_path, status=429, path="/api/search", body='{"error":"rate limit exceeded"}')


class TestHandleExplainFailureNoFailures:
    def test_returns_empty_summary_when_no_failures(self, tmp_db):
        _insert(tmp_db, status=200)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["total_failures"] == 0
        assert data["failure_groups"] == []
        assert "No failures" in data["summary"]


class TestHandleExplainFailureClassification:
    def test_401_classified_as_token_expired_when_body_says_so(self, tmp_db):
        _insert(tmp_db, status=401, path="/api/me", body='{"error":"token_expired"}')
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        patterns = {g["pattern"] for g in data["failure_groups"]}
        assert "token_expired" in patterns

    def test_401_classified_as_auth_failure_generic(self, tmp_db):
        _insert(tmp_db, status=401, path="/api/me", body='{"error":"unauthorized"}')
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        patterns = {g["pattern"] for g in data["failure_groups"]}
        assert "auth_failure" in patterns

    def test_403_classified_as_permission_denied(self, tmp_db):
        _insert(tmp_db, status=403, path="/admin")
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["failure_groups"][0]["pattern"] == "permission_denied"

    def test_404_classified_as_not_found(self, tmp_db):
        _insert(tmp_db, status=404, path="/api/missing")
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["failure_groups"][0]["pattern"] == "not_found"

    def test_429_classified_as_rate_limit(self, tmp_db):
        _insert(tmp_db, status=429, path="/api/search")
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["failure_groups"][0]["pattern"] == "rate_limit"

    def test_500_classified_as_server_error(self, tmp_db):
        _insert(tmp_db, status=500, path="/api/upload")
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["failure_groups"][0]["pattern"] == "server_error"


class TestHandleExplainFailureGrouping:
    def test_groups_multiple_failures_of_same_pattern(self, tmp_db):
        _insert(tmp_db, status=401, path="/a")
        _insert(tmp_db, status=401, path="/b")
        _insert(tmp_db, status=401, path="/c")
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        auth_group = next(g for g in data["failure_groups"] if g["pattern"] in ("auth_failure", "token_expired"))
        assert auth_group["count"] == 3

    def test_sorted_by_count_descending(self, tmp_db):
        _seed_mixed(tmp_db)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        counts = [g["count"] for g in data["failure_groups"]]
        assert counts == sorted(counts, reverse=True)

    def test_total_failures_excludes_2xx(self, tmp_db):
        _seed_mixed(tmp_db)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["total_failures"] == 4  # 401×2 + 500 + 429

    def test_examples_capped_at_3_per_group(self, tmp_db):
        for i in range(10):
            _insert(tmp_db, status=500, path=f"/api/{i}")
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        server_group = data["failure_groups"][0]
        assert len(server_group["examples"]) <= 3


class TestHandleExplainFailureFilters:
    def test_domain_filter_excludes_other_hosts(self, tmp_db):
        _insert(tmp_db, host="api.example.com", status=500)
        _insert(tmp_db, host="other.service.com", status=500)
        result = handle_explain_failure(tmp_db, {"domain": "example.com"})
        data = json.loads(result)
        assert data["total_failures"] == 1
        assert data["failure_groups"][0]["examples"][0]["host"] == "api.example.com"

    def test_since_filter_excludes_old_flows(self, tmp_db):
        old_ts = time.time() - 7200  # 2 hours ago
        _insert(tmp_db, status=500, ts=old_ts)
        _insert(tmp_db, status=500, ts=time.time())
        result = handle_explain_failure(tmp_db, {"since": "30m"})
        data = json.loads(result)
        assert data["total_failures"] == 1

    def test_no_args_defaults_to_30m_window(self, tmp_db):
        _insert(tmp_db, status=401)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert data["total_failures"] == 1


class TestHandleExplainFailureOutput:
    def test_each_group_has_required_keys(self, tmp_db):
        _insert(tmp_db, status=404)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        group = data["failure_groups"][0]
        for key in ("pattern", "label", "hypothesis", "count", "examples"):
            assert key in group

    def test_example_has_required_keys(self, tmp_db):
        _insert(tmp_db, status=403)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        example = data["failure_groups"][0]["examples"][0]
        for key in ("id", "method", "host", "path", "status"):
            assert key in example

    def test_summary_string_present(self, tmp_db):
        _insert(tmp_db, status=500)
        result = handle_explain_failure(tmp_db, {})
        data = json.loads(result)
        assert isinstance(data["summary"], str)
        assert len(data["summary"]) > 0
