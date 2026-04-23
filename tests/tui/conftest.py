"""TUI test fixtures — shared DB helpers and bulk flow generators."""

import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow


SAMPLE_HOSTS = [
    "api.example.com",
    "api.example.com",
    "cdn.example.com",
    "auth.example.com",
    "graphql.example.com",
]

SAMPLE_PATHS = [
    "/api/v2/users/12345/ratings",
    "/api/v2/movies/99/reviews",
    "/api/v1/search",
    "/api/v2/auth/token",
    "/health",
    "/api/v2/contents/abc123/episodes",
    "/api/v1/config",
    "/api/v2/notifications",
    "/api/v2/users/12345/watchlist",
    "/api/v2/movies/99/similar",
]

SAMPLE_METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE", "PATCH", "GET", "GET", "GET"]
SAMPLE_STATUSES = [200, 200, 200, 201, 200, 204, 200, 401, 403, 500]


def _make_flow_kwargs(index: int, base_time: float) -> dict:
    """Generate deterministic flow kwargs for a given index."""
    host = SAMPLE_HOSTS[index % len(SAMPLE_HOSTS)]
    path = SAMPLE_PATHS[index % len(SAMPLE_PATHS)]
    method = SAMPLE_METHODS[index % len(SAMPLE_METHODS)]
    status = SAMPLE_STATUSES[index % len(SAMPLE_STATUSES)]

    return {
        "timestamp": base_time + index * 0.1,
        "method": method,
        "scheme": "https",
        "host": host,
        "port": 443,
        "path": path,
        "query": f"page={index % 10}" if index % 3 == 0 else None,
        "request_headers": {"Accept": "application/json", "Authorization": "Bearer tok"},
        "request_body": None if method == "GET" else f'{{"idx": {index}}}',
        "request_content_type": None if method == "GET" else "application/json",
        "status_code": status,
        "response_headers": {"Content-Type": "application/json"},
        "response_body": f'{{"ok": true, "index": {index}}}',
        "response_content_type": "application/json",
        "duration_ms": 10.0 + (index % 100),
    }


@pytest.fixture
def db_with_flows(tmp_db):
    """DB with 50 sample flows — fast fixture for functional tests."""
    init_db(tmp_db)
    for i in range(50):
        insert_flow(tmp_db, **_make_flow_kwargs(i, time.time() - 50))
    return tmp_db


@pytest.fixture
def db_10k(tmp_path):
    """DB with 10,000 flows — performance/stress fixture.

    Uses batch insert for speed (~2-3s).
    """
    db_path = str(tmp_path / "stress_flows.db")
    init_db(db_path)

    from troxy.core.db import get_connection

    conn = get_connection(db_path)
    base_time = time.time() - 10000

    rows = []
    for i in range(10_000):
        kw = _make_flow_kwargs(i, base_time)
        rows.append((
            kw["timestamp"],
            kw["method"],
            kw["scheme"],
            kw["host"],
            kw["port"],
            kw["path"],
            kw["query"],
            '{"Accept": "application/json"}',
            kw["request_body"],
            kw["request_content_type"],
            kw["status_code"],
            '{"Content-Type": "application/json"}',
            kw["response_body"],
            kw["response_content_type"],
            kw["duration_ms"],
        ))

    conn.executemany(
        """INSERT INTO flows (
            timestamp, method, scheme, host, port, path, query,
            request_headers, request_body, request_content_type,
            status_code, response_headers, response_body, response_content_type,
            duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path
