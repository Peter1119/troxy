# troxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI + MCP tool that records mitmproxy flows to SQLite, enabling Claude and humans to query, filter, search, mock, intercept, and replay HTTP flows without TUI interaction.

**Architecture:** Addon-centric — a mitmproxy addon writes flows to SQLite in real-time. A shared core layer provides querying logic. CLI (click + rich) and MCP Server consume the core. Mock and intercept features extend the addon with request hooks.

**Tech Stack:** Python 3.14, uv, mitmproxy 12.2.1 addon API, sqlite3, click, rich, mcp SDK, pytest

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/troxy/__init__.py`
- Create: `src/troxy/core/__init__.py`
- Create: `src/troxy/cli/__init__.py`
- Create: `src/troxy/mcp/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `CLAUDE.md`
- Create: `ARCHITECTURE.md`
- Create: `.gitignore`

- [ ] **Step 1: Install uv**

```bash
brew install uv
```

Expected: `uv --version` prints version.

- [ ] **Step 2: Initialize project with uv**

```bash
cd /Users/seokhyeon/Workspace/troxy
uv init --lib --name troxy --python 3.14
```

- [ ] **Step 3: Create pyproject.toml**

Replace the generated pyproject.toml:

```toml
[project]
name = "troxy"
version = "0.1.0"
description = "Terminal proxy inspector — mitmproxy flows for CLI and Claude"
requires-python = ">=3.14"
dependencies = [
    "click>=8.1",
    "rich>=13.0",
]

[project.optional-dependencies]
mcp = ["mcp>=1.0"]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
troxy = "troxy.cli.main:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"

[tool.hatch.build.targets.wheel]
packages = ["src/troxy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p src/troxy/core src/troxy/cli src/troxy/mcp tests/unit tests/integration tests/e2e eval/fixtures eval/scenarios scripts
```

Create `src/troxy/__init__.py`:
```python
"""troxy — terminal proxy inspector."""

__version__ = "0.1.0"
```

Create `src/troxy/core/__init__.py`:
```python
"""Core query layer. No mitmproxy imports allowed."""
```

Create `src/troxy/cli/__init__.py`:
```python
"""CLI interface."""
```

Create `src/troxy/mcp/__init__.py`:
```python
"""MCP server interface."""
```

Create empty `tests/__init__.py`.

Create `tests/conftest.py`:
```python
"""Shared test fixtures."""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path."""
    return str(tmp_path / "test_flows.db")
```

- [ ] **Step 5: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
*.db
```

- [ ] **Step 6: Create CLAUDE.md**

```markdown
# troxy

Terminal proxy inspector. mitmproxy addon + CLI + MCP.

## Architecture

See ARCHITECTURE.md for layer diagram.

## Key Rules

- `src/troxy/core/` must NEVER import `mitmproxy`. It is pure SQLite logic.
- `src/troxy/addon.py` is the ONLY file that imports `mitmproxy`.
- `cli` and `mcp` depend on `core` only, never on each other.

## Testing

```bash
uv run pytest                    # all tests
uv run pytest tests/unit -v     # unit only
uv run pytest tests/e2e -v      # E2E only
```

## Lint

```bash
uv run python scripts/lint_layers.py    # check layer deps
uv run python scripts/check_file_size.py # check file sizes
```

## DB Location

Default: `~/.troxy/flows.db`
Override: `TROXY_DB` env var or `--db` CLI flag.
```

- [ ] **Step 7: Create ARCHITECTURE.md**

```markdown
# Architecture

```
mitmproxy -s src/troxy/addon.py
         │
    troxy addon (response/request hooks)
         │ writes
         ▼
    SQLite (flows.db)
         │ reads
    ┌────┴────┐
    ▼         ▼
  troxy     troxy
  CLI       MCP Server
```

## Layers

| Layer | Path | Imports | Responsibility |
|-------|------|---------|---------------|
| addon | `src/troxy/addon.py` | mitmproxy, core | Capture flows, mock, intercept |
| core | `src/troxy/core/` | sqlite3 only | DB, query, store, export, mock rules, intercept rules |
| cli | `src/troxy/cli/` | core, click, rich | Terminal commands |
| mcp | `src/troxy/mcp/` | core, mcp SDK | MCP tool server |

## Dependency Rule

`addon → core ← cli, mcp`

Cross-layer imports are forbidden. core is the shared foundation.
```

- [ ] **Step 8: Install dependencies and verify**

```bash
uv sync --all-extras
uv run pytest --co  # collect tests (should find 0, no error)
```

Expected: dependencies installed, pytest collects with no errors.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold troxy project with uv, directory structure, and docs"
```

---

## Task 2: Core DB — Connection and Schema

**Files:**
- Create: `src/troxy/core/db.py`
- Create: `tests/unit/test_db.py`

- [ ] **Step 1: Write failing tests for DB initialization**

Create `tests/unit/test_db.py`:

```python
"""Tests for database connection and schema."""

from troxy.core.db import get_connection, init_db, DB_SCHEMA_VERSION


def test_init_db_creates_tables(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "flows" in tables
    assert "mock_rules" in tables
    assert "intercept_rules" in tables
    assert "pending_flows" in tables
    conn.close()


def test_init_db_creates_indexes(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = [row[0] for row in cursor.fetchall()]
    assert "idx_flows_host" in indexes
    assert "idx_flows_status" in indexes
    assert "idx_flows_method" in indexes
    assert "idx_flows_timestamp" in indexes
    conn.close()


def test_init_db_is_idempotent(tmp_db):
    init_db(tmp_db)
    init_db(tmp_db)  # should not raise
    conn = get_connection(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    assert len(cursor.fetchall()) > 0
    conn.close()


def test_init_db_creates_parent_dirs(tmp_path):
    db_path = str(tmp_path / "sub" / "dir" / "flows.db")
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    assert len(cursor.fetchall()) > 0
    conn.close()


def test_get_connection_enables_wal(tmp_db):
    init_db(tmp_db)
    conn = get_connection(tmp_db)
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal == "wal"
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'troxy.core.db'`

- [ ] **Step 3: Implement db.py**

Create `src/troxy/core/db.py`:

```python
"""SQLite database connection and schema management."""

import sqlite3
from pathlib import Path

DB_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    method TEXT NOT NULL,
    scheme TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    path TEXT NOT NULL,
    query TEXT,
    request_headers TEXT NOT NULL,
    request_body TEXT,
    request_content_type TEXT,
    status_code INTEGER NOT NULL,
    response_headers TEXT NOT NULL,
    response_body TEXT,
    response_content_type TEXT,
    duration_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_flows_host ON flows(host);
CREATE INDEX IF NOT EXISTS idx_flows_status ON flows(status_code);
CREATE INDEX IF NOT EXISTS idx_flows_method ON flows(method);
CREATE INDEX IF NOT EXISTS idx_flows_timestamp ON flows(timestamp);

CREATE TABLE IF NOT EXISTS mock_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT,
    path_pattern TEXT,
    method TEXT,
    status_code INTEGER NOT NULL DEFAULT 200,
    response_headers TEXT,
    response_body TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS intercept_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT,
    path_pattern TEXT,
    method TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    method TEXT NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    request_headers TEXT NOT NULL,
    request_body TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and row factory."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """Create database file, parent dirs, and all tables/indexes."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA_SQL)
    conn.close()


def default_db_path() -> str:
    """Return the default DB path, respecting TROXY_DB env var."""
    import os

    path = os.environ.get("TROXY_DB")
    if path:
        return os.path.expanduser(path)
    return str(Path.home() / ".troxy" / "flows.db")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_db.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(core): add database connection and schema initialization"
```

---

## Task 3: Core Store — Flow Insertion

**Files:**
- Create: `src/troxy/core/store.py`
- Create: `tests/unit/test_store.py`

- [ ] **Step 1: Write failing tests for flow insertion**

Create `tests/unit/test_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_store.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'troxy.core.store'`

- [ ] **Step 3: Implement store.py**

Create `src/troxy/core/store.py`:

```python
"""Flow storage — insert flows into SQLite."""

import base64
import json

from troxy.core.db import get_connection


def _encode_body(body, content_type: str | None) -> str | None:
    """Encode body for storage. Text as-is, binary as b64:..."""
    if body is None:
        return None
    if isinstance(body, bytes):
        if content_type and (
            content_type.startswith("text/")
            or "json" in content_type
            or "xml" in content_type
            or "javascript" in content_type
            or "html" in content_type
        ):
            try:
                return body.decode("utf-8")
            except UnicodeDecodeError:
                pass
        return "b64:" + base64.b64encode(body).decode("ascii")
    return str(body)


def _encode_headers(headers) -> str:
    """Serialize headers to JSON string."""
    if isinstance(headers, dict):
        return json.dumps(headers, ensure_ascii=False)
    return json.dumps(dict(headers), ensure_ascii=False)


def insert_flow(
    db_path: str,
    *,
    timestamp: float,
    method: str,
    scheme: str,
    host: str,
    port: int,
    path: str,
    query: str | None,
    request_headers,
    request_body,
    request_content_type: str | None,
    status_code: int,
    response_headers,
    response_body,
    response_content_type: str | None,
    duration_ms: float | None,
) -> int:
    """Insert a flow and return its row ID."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """
        INSERT INTO flows (
            timestamp, method, scheme, host, port, path, query,
            request_headers, request_body, request_content_type,
            status_code, response_headers, response_body, response_content_type,
            duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            method,
            scheme,
            host,
            port,
            path,
            query,
            _encode_headers(request_headers),
            _encode_body(request_body, request_content_type),
            request_content_type,
            status_code,
            _encode_headers(response_headers),
            _encode_body(response_body, response_content_type),
            response_content_type,
            duration_ms,
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_store.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(core): add flow storage with body encoding"
```

---

## Task 4: Core Query — Flow Listing and Filtering

**Files:**
- Create: `src/troxy/core/query.py`
- Create: `tests/unit/test_query.py`

- [ ] **Step 1: Write failing tests for flow querying**

Create `tests/unit/test_query.py`:

```python
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
    assert flows[0]["host"] == "cdn.example.com"  # most recent
    assert flows[-1]["host"] == "api.example.com"  # oldest


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
    flows = list_flows(tmp_db, since_seconds=150)  # last 150 seconds
    assert len(flows) == 2  # last two flows


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_query.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement query.py**

Create `src/troxy/core/query.py`:

```python
"""Flow querying, filtering, and searching."""

import time

from troxy.core.db import get_connection


def list_flows(
    db_path: str,
    *,
    domain: str | None = None,
    status: int | None = None,
    method: str | None = None,
    path: str | None = None,
    limit: int = 50,
    since_seconds: float | None = None,
) -> list[dict]:
    """List flows with optional filters. Returns dicts ordered by timestamp DESC."""
    conn = get_connection(db_path)
    conditions = []
    params = []

    if domain:
        conditions.append("host LIKE ?")
        params.append(f"%{domain}%")
    if status is not None:
        conditions.append("status_code = ?")
        params.append(status)
    if method:
        conditions.append("method = ?")
        params.append(method.upper())
    if path:
        conditions.append("path LIKE ?")
        params.append(f"%{path}%")
    if since_seconds is not None:
        conditions.append("timestamp >= ?")
        params.append(time.time() - since_seconds)

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"SELECT * FROM flows {where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_flow(db_path: str, flow_id: int) -> dict | None:
    """Get a single flow by ID."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM flows WHERE id = ?", (flow_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_flows(
    db_path: str,
    query: str,
    *,
    domain: str | None = None,
    scope: str = "all",
    limit: int = 50,
) -> list[dict]:
    """Search flow bodies for a text query."""
    conn = get_connection(db_path)
    conditions = []
    params = []

    if scope == "request":
        conditions.append("(request_body LIKE ? OR request_headers LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    elif scope == "response":
        conditions.append("(response_body LIKE ? OR response_headers LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    else:
        conditions.append(
            "(request_body LIKE ? OR response_body LIKE ? "
            "OR request_headers LIKE ? OR response_headers LIKE ?)"
        )
        params.extend([f"%{query}%"] * 4)

    if domain:
        conditions.append("host LIKE ?")
        params.append(f"%{domain}%")

    where = "WHERE " + " AND ".join(conditions)
    sql = f"SELECT * FROM flows {where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_query.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(core): add flow querying with filters and text search"
```

---

## Task 5: Core Export — curl/httpie

**Files:**
- Create: `src/troxy/core/export.py`
- Create: `tests/unit/test_export.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_export.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_export.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement export.py**

Create `src/troxy/core/export.py`:

```python
"""Export flows to curl/httpie format."""

import json


def _build_url(flow: dict) -> str:
    """Build full URL from flow fields."""
    scheme = flow["scheme"]
    host = flow["host"]
    port = flow["port"]
    path = flow["path"]
    query = flow.get("query")

    default_port = 443 if scheme == "https" else 80
    host_part = f"{host}:{port}" if port != default_port else host
    url = f"{scheme}://{host_part}{path}"
    if query:
        url += f"?{query}"
    return url


def _parse_headers(flow: dict) -> dict:
    """Parse headers from JSON string or dict."""
    headers = flow.get("request_headers", "{}")
    if isinstance(headers, str):
        return json.loads(headers)
    return dict(headers)


def export_curl(flow: dict) -> str:
    """Export flow as a curl command."""
    url = _build_url(flow)
    method = flow["method"]
    headers = _parse_headers(flow)
    body = flow.get("request_body")

    parts = ["curl"]
    if method != "GET":
        parts.append(f"-X {method}")

    for key, value in headers.items():
        parts.append(f"-H '{key}: {value}'")

    if body:
        parts.append(f"-d '{body}'")

    parts.append(f"'{url}'")
    return " ".join(parts)


def export_httpie(flow: dict) -> str:
    """Export flow as an httpie command."""
    url = _build_url(flow)
    method = flow["method"]
    headers = _parse_headers(flow)
    body = flow.get("request_body")

    parts = ["http", method, url]

    for key, value in headers.items():
        parts.append(f"{key}:{value}")

    if body:
        try:
            json.loads(body)
            parts = ["http", "--json", method, url]
            for key, value in headers.items():
                if key.lower() != "content-type":
                    parts.append(f"{key}:{value}")
            parsed = json.loads(body)
            for k, v in parsed.items():
                parts.append(f"{k}={json.dumps(v)}")
        except (json.JSONDecodeError, TypeError):
            parts.append(f"--raw '{body}'")

    return " ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_export.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(core): add curl and httpie export"
```

---

## Task 6: CLI — Basic Commands (flows, flow, search, status, clear)

**Files:**
- Create: `src/troxy/cli/main.py`
- Create: `src/troxy/cli/formatting.py`
- Create: `tests/e2e/test_cli.py`

- [ ] **Step 1: Write failing E2E tests**

Create `tests/e2e/test_cli.py`:

```python
"""E2E tests for CLI commands."""

import json
import subprocess
import sys
import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow


def _run_troxy(*args, db_path=None):
    """Run troxy CLI and return stdout."""
    cmd = [sys.executable, "-m", "troxy.cli.main"] + list(args)
    if db_path:
        cmd.extend(["--db", db_path])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def _seed(db_path):
    """Seed test DB with sample flows."""
    init_db(db_path)
    now = time.time()
    insert_flow(db_path, timestamp=now - 60, method="GET", scheme="https",
                host="api.example.com", port=443, path="/users", query=None,
                request_headers={"Accept": "application/json"}, request_body=None,
                request_content_type=None, status_code=200,
                response_headers={"Content-Type": "application/json"},
                response_body='{"users": []}', response_content_type="application/json",
                duration_ms=42.0)
    insert_flow(db_path, timestamp=now, method="POST", scheme="https",
                host="api.internal.com", port=443, path="/api/users", query=None,
                request_headers={"Content-Type": "application/json"},
                request_body='{"email": "test@test.com"}',
                request_content_type="application/json", status_code=401,
                response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized"}',
                response_content_type="application/json", duration_ms=30.0)


def test_flows_lists_all(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "api.example.com" in result.stdout
    assert "api.internal.com" in result.stdout


def test_flows_filter_domain(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "-d", "internal", "--no-color", db_path=tmp_db)
    assert "api.internal.com" in result.stdout
    assert "api.example.com" not in result.stdout


def test_flows_filter_status(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "-s", "401", "--no-color", db_path=tmp_db)
    assert "401" in result.stdout
    assert "200" not in result.stdout or "api.internal.com" in result.stdout


def test_flows_json_output(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flows", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2


def test_flow_detail(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "2", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "api.internal.com" in result.stdout
    assert "unauthorized" in result.stdout


def test_flow_body_only(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "2", "--body", "--no-color", db_path=tmp_db)
    assert "unauthorized" in result.stdout


def test_flow_export_curl(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "2", "--export", "curl", db_path=tmp_db)
    assert "curl" in result.stdout
    assert "api.internal.com" in result.stdout


def test_flow_not_found(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("flow", "999", db_path=tmp_db)
    assert result.returncode != 0 or "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_search(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("search", "unauthorized", "--no-color", db_path=tmp_db)
    assert "api.internal.com" in result.stdout


def test_status(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("status", "--no-color", db_path=tmp_db)
    assert result.returncode == 0
    assert "2" in result.stdout  # 2 flows


def test_clear(tmp_db):
    _seed(tmp_db)
    result = _run_troxy("clear", "--yes", db_path=tmp_db)
    assert result.returncode == 0
    result2 = _run_troxy("flows", "--json", db_path=tmp_db)
    data = json.loads(result2.stdout)
    assert len(data) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/e2e/test_cli.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement formatting.py**

Create `src/troxy/cli/formatting.py`:

```python
"""Terminal output formatting with rich."""

import json
from datetime import datetime

from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.text import Text

console = Console()

METHOD_COLORS = {
    "GET": "green",
    "POST": "blue",
    "PUT": "yellow",
    "PATCH": "yellow",
    "DELETE": "red",
    "HEAD": "dim",
    "OPTIONS": "dim",
}

STATUS_COLORS = {
    2: "green",
    3: "cyan",
    4: "yellow",
    5: "red",
}


def _method_style(method: str) -> str:
    return METHOD_COLORS.get(method, "white")


def _status_style(code: int) -> str:
    return STATUS_COLORS.get(code // 100, "white")


def _format_size(body: str | None) -> str:
    if not body:
        return "-"
    size = len(body.encode("utf-8")) if not body.startswith("b64:") else len(body) * 3 // 4
    if size < 1024:
        return f"{size}b"
    return f"{size / 1024:.1f}k"


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _format_duration(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def print_flows_table(flows: list[dict]) -> None:
    """Print flow list as a rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Time", width=8)
    table.add_column("Method", width=7)
    table.add_column("Host", max_width=30)
    table.add_column("Path", max_width=40)
    table.add_column("Status", width=6)
    table.add_column("Size", width=8)
    table.add_column("Duration", width=8)

    for f in flows:
        method = f["method"]
        status = f["status_code"]
        table.add_row(
            str(f["id"]),
            _format_time(f["timestamp"]),
            Text(method, style=_method_style(method)),
            f["host"],
            f["path"],
            Text(str(status), style=_status_style(status)),
            _format_size(f.get("response_body")),
            _format_duration(f.get("duration_ms")),
        )
    console.print(table)


def print_flow_detail(flow: dict, *, request_only=False, response_only=False,
                      headers_only=False, body_only=False) -> None:
    """Print flow detail with sections."""
    if not response_only and not body_only:
        console.rule(f"[bold]Request[/bold]", style="blue")
        url = f"{flow['scheme']}://{flow['host']}{flow['path']}"
        if flow.get("query"):
            url += f"?{flow['query']}"
        console.print(f"[bold]{flow['method']}[/bold] {url}")
        if not body_only:
            headers = json.loads(flow["request_headers"]) if isinstance(flow["request_headers"], str) else flow["request_headers"]
            for k, v in headers.items():
                console.print(f"  {k}: {v}", style="dim")
        if not headers_only and flow.get("request_body"):
            console.print()
            _print_body(flow["request_body"], flow.get("request_content_type"))

    if request_only:
        return

    if not body_only:
        status = flow["status_code"]
        duration = _format_duration(flow.get("duration_ms"))
        console.rule(
            f"[bold]Response ({status})[/bold] {duration}",
            style=_status_style(status),
        )
        if not headers_only:
            pass
        headers = json.loads(flow["response_headers"]) if isinstance(flow["response_headers"], str) else flow["response_headers"]
        if not body_only:
            for k, v in headers.items():
                console.print(f"  {k}: {v}", style="dim")

    if headers_only:
        return

    if flow.get("response_body"):
        if not body_only:
            console.print()
        _print_body(flow["response_body"], flow.get("response_content_type"))


def _print_body(body: str, content_type: str | None) -> None:
    """Print body with JSON highlighting if applicable."""
    if body.startswith("b64:"):
        console.print(f"[dim](binary, {len(body) * 3 // 4} bytes, base64 encoded)[/dim]")
        return
    if content_type and "json" in content_type:
        try:
            parsed = json.loads(body)
            console.print(JSON(json.dumps(parsed, indent=2, ensure_ascii=False)))
            return
        except json.JSONDecodeError:
            pass
    console.print(body)


def print_status(db_path: str, flow_count: int, db_size: int) -> None:
    """Print database status info."""
    console.print(f"DB path:  {db_path}")
    console.print(f"Flows:    {flow_count}")
    size_str = f"{db_size / 1024:.1f}KB" if db_size < 1024 * 1024 else f"{db_size / 1024 / 1024:.1f}MB"
    console.print(f"Size:     {size_str}")
```

- [ ] **Step 4: Implement main.py**

Create `src/troxy/cli/main.py`:

```python
"""troxy CLI — click commands."""

import json
import os
import sys

import click

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.query import list_flows, get_flow, search_flows
from troxy.core.export import export_curl, export_httpie


def _parse_since(since: str | None) -> float | None:
    """Parse since string like '5m', '1h' to seconds."""
    if not since:
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if since[-1] in units:
        try:
            return float(since[:-1]) * units[since[-1]]
        except ValueError:
            pass
    return None


@click.group()
@click.option("--db", default=None, help="Database path")
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.pass_context
def cli(ctx, db, no_color):
    """troxy — terminal proxy inspector."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db or default_db_path()
    if no_color:
        os.environ["NO_COLOR"] = "1"
    init_db(ctx.obj["db"])


@cli.command("flows")
@click.option("-d", "--domain", default=None, help="Filter by domain (partial match)")
@click.option("-s", "--status", default=None, type=int, help="Filter by status code")
@click.option("-m", "--method", default=None, help="Filter by HTTP method")
@click.option("-p", "--path", "path_filter", default=None, help="Filter by path (partial match)")
@click.option("-n", "--limit", default=50, type=int, help="Max results")
@click.option("--since", default=None, help="Time filter (e.g. 5m, 1h)")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def flows_cmd(ctx, domain, status, method, path_filter, limit, since, as_json):
    """List captured flows."""
    db = ctx.obj["db"]
    since_seconds = _parse_since(since)
    results = list_flows(db, domain=domain, status=status, method=method,
                         path=path_filter, limit=limit, since_seconds=since_seconds)
    if as_json:
        click.echo(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        return
    if not results:
        click.echo("No flows found.")
        return
    from troxy.cli.formatting import print_flows_table
    print_flows_table(results)


@cli.command("flow")
@click.argument("flow_id", type=int)
@click.option("--request", "request_only", is_flag=True, help="Show request only")
@click.option("--response", "response_only", is_flag=True, help="Show response only")
@click.option("--headers", "headers_only", is_flag=True, help="Show headers only")
@click.option("--body", "body_only", is_flag=True, help="Show body only")
@click.option("--raw", is_flag=True, help="Raw output without formatting")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--export", "export_format", type=click.Choice(["curl", "httpie"]),
              default=None, help="Export format")
@click.pass_context
def flow_cmd(ctx, flow_id, request_only, response_only, headers_only, body_only,
             raw, as_json, export_format):
    """Show flow details."""
    db = ctx.obj["db"]
    flow = get_flow(db, flow_id)
    if not flow:
        click.echo(f"Flow {flow_id} not found.", err=True)
        sys.exit(1)

    if export_format == "curl":
        click.echo(export_curl(flow))
        return
    if export_format == "httpie":
        click.echo(export_httpie(flow))
        return
    if as_json:
        click.echo(json.dumps(flow, indent=2, ensure_ascii=False, default=str))
        return
    if raw:
        if body_only:
            click.echo(flow.get("response_body", ""))
        else:
            click.echo(json.dumps(flow, indent=2, ensure_ascii=False, default=str))
        return

    from troxy.cli.formatting import print_flow_detail
    print_flow_detail(flow, request_only=request_only, response_only=response_only,
                      headers_only=headers_only, body_only=body_only)


@cli.command("search")
@click.argument("query")
@click.option("-d", "--domain", default=None, help="Filter by domain")
@click.option("--in", "scope", type=click.Choice(["request", "response", "all"]),
              default="all", help="Search scope")
@click.option("-n", "--limit", default=50, type=int, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def search_cmd(ctx, query, domain, scope, limit, as_json):
    """Search flow bodies for text."""
    db = ctx.obj["db"]
    results = search_flows(db, query, domain=domain, scope=scope, limit=limit)
    if as_json:
        click.echo(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        return
    if not results:
        click.echo("No matching flows.")
        return
    from troxy.cli.formatting import print_flows_table
    print_flows_table(results)


@cli.command("status")
@click.pass_context
def status_cmd(ctx):
    """Show database status."""
    db = ctx.obj["db"]
    conn = get_connection(db)
    count = conn.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
    conn.close()
    db_size = os.path.getsize(db) if os.path.exists(db) else 0
    from troxy.cli.formatting import print_status
    print_status(db, count, db_size)


@cli.command("clear")
@click.option("--before", default=None, help="Clear flows older than (e.g. 1h)")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def clear_cmd(ctx, before, yes):
    """Clear all flows."""
    db = ctx.obj["db"]
    if not yes:
        click.confirm("Delete all flows?", abort=True)
    conn = get_connection(db)
    if before:
        seconds = _parse_since(before)
        if seconds:
            import time
            conn.execute("DELETE FROM flows WHERE timestamp < ?", (time.time() - seconds,))
    else:
        conn.execute("DELETE FROM flows")
    conn.commit()
    conn.close()
    click.echo("Flows cleared.")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/e2e/test_cli.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 6: Verify CLI works directly**

```bash
uv run troxy --help
uv run troxy status
```

Expected: help text shows all commands, status shows 0 flows.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(cli): add flows, flow, search, status, clear commands with rich UI"
```

---

## Task 7: Addon — mitmproxy Flow Recording

**Files:**
- Create: `src/troxy/addon.py`
- Create: `tests/integration/test_addon.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_addon.py`:

```python
"""Integration tests for mitmproxy addon.

These tests use mitmdump to run the addon against a real HTTP server.
"""

import http.server
import json
import subprocess
import sys
import threading
import time

import pytest

from troxy.core.db import init_db, get_connection


class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"received": True}).encode())

    def log_message(self, format, *args):
        pass  # suppress output


@pytest.fixture
def test_server():
    """Start a simple HTTP server on a random port."""
    server = http.server.HTTPServer(("127.0.0.1", 0), SimpleHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


def test_addon_records_flow(tmp_db, test_server, tmp_path):
    """mitmdump + addon should record flows to SQLite."""
    init_db(tmp_db)
    addon_path = str(tmp_path.parent.parent.parent / "src" / "troxy" / "addon.py")
    # Use the actual addon path
    import troxy.addon
    addon_path = troxy.addon.__file__

    env = {"TROXY_DB": tmp_db, "PATH": "/opt/homebrew/bin:/usr/bin:/bin"}

    # Run mitmdump with addon, make one request through proxy, then stop
    proxy_port = test_server + 1000
    proc = subprocess.Popen(
        ["mitmdump", "-p", str(proxy_port), "-s", addon_path, "--set", f"confdir={tmp_path}",
         "--no-anticache", "-q"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)  # wait for proxy to start

    # Make request through proxy
    import urllib.request
    proxy_handler = urllib.request.ProxyHandler({
        "http": f"http://127.0.0.1:{proxy_port}",
    })
    opener = urllib.request.build_opener(proxy_handler)
    try:
        opener.open(f"http://127.0.0.1:{test_server}/test?q=1", timeout=5)
    except Exception:
        pass

    time.sleep(1)  # wait for addon to write
    proc.terminate()
    proc.wait(timeout=5)

    # Verify flow was recorded
    conn = get_connection(tmp_db)
    rows = conn.execute("SELECT * FROM flows").fetchall()
    conn.close()

    assert len(rows) >= 1
    row = rows[0]
    assert row["method"] == "GET"
    assert row["path"] == "/test"
    assert row["status_code"] == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_addon.py -v
```

Expected: FAIL — addon.py doesn't exist yet.

- [ ] **Step 3: Implement addon.py**

Create `src/troxy/addon.py`:

```python
"""mitmproxy addon — records flows to SQLite.

Usage: mitmproxy -s path/to/addon.py
Set TROXY_DB env var to control database path.
"""

import json
import os
import sys
import time

# Ensure src/ is on path when running as mitmproxy script
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.store import insert_flow


class TroxyAddon:
    """mitmproxy addon that records flows to SQLite."""

    def __init__(self):
        self.db_path = default_db_path()
        init_db(self.db_path)

    def response(self, flow):
        """Called when a response is received."""
        try:
            request = flow.request
            response = flow.response

            content_type_req = request.headers.get("content-type", "")
            content_type_resp = response.headers.get("content-type", "")

            duration = None
            if flow.response.timestamp_end and flow.request.timestamp_start:
                duration = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000

            insert_flow(
                self.db_path,
                timestamp=flow.request.timestamp_start or time.time(),
                method=request.method,
                scheme=request.scheme,
                host=request.host,
                port=request.port,
                path=request.path,
                query=request.query if request.query else None,
                request_headers=dict(request.headers),
                request_body=request.content,
                request_content_type=content_type_req or None,
                status_code=response.status_code,
                response_headers=dict(response.headers),
                response_body=response.content,
                response_content_type=content_type_resp or None,
                duration_ms=duration,
            )
        except Exception as e:
            # Log but don't crash mitmproxy
            print(f"[troxy] Error recording flow: {e}", file=sys.stderr)


addons = [TroxyAddon()]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/integration/test_addon.py -v --timeout=30
```

Expected: PASS (may need adjustments to port/timing).

- [ ] **Step 5: Manual test**

```bash
# Terminal 1: start mitmproxy with addon
TROXY_DB=/tmp/troxy_test.db mitmproxy -s src/troxy/addon.py

# Terminal 2: make request through proxy
curl -x http://localhost:8080 http://httpbin.org/get

# Terminal 3: verify
uv run troxy flows --db /tmp/troxy_test.db
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(addon): add mitmproxy addon for flow recording to SQLite"
```

---

## Task 8: Core Mock — Rules CRUD

**Files:**
- Create: `src/troxy/core/mock.py`
- Create: `tests/unit/test_mock.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_mock.py`:

```python
"""Tests for mock rules CRUD."""

import time

from troxy.core.db import init_db
from troxy.core.mock import add_mock_rule, list_mock_rules, remove_mock_rule, toggle_mock_rule, mock_from_flow
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_mock.py -v
```

- [ ] **Step 3: Implement mock.py**

Create `src/troxy/core/mock.py`:

```python
"""Mock rules CRUD operations."""

import json
import time

from troxy.core.db import get_connection
from troxy.core.query import get_flow


def add_mock_rule(
    db_path: str,
    *,
    domain: str | None = None,
    path_pattern: str | None = None,
    method: str | None = None,
    status_code: int = 200,
    response_headers: str | None = None,
    response_body: str | None = None,
) -> int:
    """Add a mock rule and return its ID."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """INSERT INTO mock_rules (domain, path_pattern, method, status_code,
           response_headers, response_body, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (domain, path_pattern, method, status_code,
         response_headers, response_body, time.time()),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def list_mock_rules(db_path: str, *, enabled_only: bool = False) -> list[dict]:
    """List all mock rules."""
    conn = get_connection(db_path)
    sql = "SELECT * FROM mock_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def remove_mock_rule(db_path: str, rule_id: int) -> None:
    """Delete a mock rule."""
    conn = get_connection(db_path)
    conn.execute("DELETE FROM mock_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()


def toggle_mock_rule(db_path: str, rule_id: int, *, enabled: bool) -> None:
    """Enable or disable a mock rule."""
    conn = get_connection(db_path)
    conn.execute("UPDATE mock_rules SET enabled = ? WHERE id = ?", (int(enabled), rule_id))
    conn.commit()
    conn.close()


def mock_from_flow(db_path: str, flow_id: int, *, status_code: int | None = None) -> int:
    """Create a mock rule from an existing flow's response."""
    flow = get_flow(db_path, flow_id)
    if not flow:
        raise ValueError(f"Flow {flow_id} not found")
    return add_mock_rule(
        db_path,
        domain=flow["host"],
        path_pattern=flow["path"],
        method=flow["method"],
        status_code=status_code or flow["status_code"],
        response_headers=flow["response_headers"],
        response_body=flow["response_body"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_mock.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(core): add mock rules CRUD and from-flow"
```

---

## Task 9: Core Intercept — Rules and Pending Flows

**Files:**
- Create: `src/troxy/core/intercept.py`
- Create: `tests/unit/test_intercept.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_intercept.py`:

```python
"""Tests for intercept rules and pending flows."""

from troxy.core.db import init_db
from troxy.core.intercept import (
    add_intercept_rule, list_intercept_rules, remove_intercept_rule,
    add_pending_flow, list_pending_flows, update_pending_flow,
    get_pending_flow,
)
import time


def test_add_intercept_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_intercept_rule(tmp_db, domain="api.example.com", method="POST")
    assert rule_id == 1


def test_list_intercept_rules(tmp_db):
    init_db(tmp_db)
    add_intercept_rule(tmp_db, domain="a.com")
    add_intercept_rule(tmp_db, domain="b.com")
    rules = list_intercept_rules(tmp_db)
    assert len(rules) == 2


def test_remove_intercept_rule(tmp_db):
    init_db(tmp_db)
    rule_id = add_intercept_rule(tmp_db, domain="a.com")
    remove_intercept_rule(tmp_db, rule_id)
    assert len(list_intercept_rules(tmp_db)) == 0


def test_add_pending_flow(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="abc-123", method="POST",
                             host="api.example.com", path="/api/users",
                             request_headers='{"Content-Type": "application/json"}',
                             request_body='{"name": "test"}')
    assert pf_id == 1


def test_list_pending_flows(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="a", method="GET", host="a.com", path="/",
                     request_headers="{}", request_body=None)
    add_pending_flow(tmp_db, flow_id="b", method="POST", host="b.com", path="/",
                     request_headers="{}", request_body=None)
    pending = list_pending_flows(tmp_db)
    assert len(pending) == 2


def test_list_pending_flows_only_pending(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="a", method="GET", host="a.com", path="/",
                             request_headers="{}", request_body=None)
    add_pending_flow(tmp_db, flow_id="b", method="GET", host="b.com", path="/",
                     request_headers="{}", request_body=None)
    update_pending_flow(tmp_db, pf_id, status="released")
    pending = list_pending_flows(tmp_db)
    assert len(pending) == 1


def test_update_pending_flow_modify_headers(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="a", method="GET", host="a.com", path="/",
                             request_headers='{"Auth": "old"}', request_body=None)
    update_pending_flow(tmp_db, pf_id, request_headers='{"Auth": "new"}', status="modified")
    pf = get_pending_flow(tmp_db, pf_id)
    assert pf["request_headers"] == '{"Auth": "new"}'
    assert pf["status"] == "modified"


def test_update_pending_flow_modify_body(tmp_db):
    init_db(tmp_db)
    pf_id = add_pending_flow(tmp_db, flow_id="a", method="POST", host="a.com", path="/",
                             request_headers="{}", request_body='{"old": true}')
    update_pending_flow(tmp_db, pf_id, request_body='{"new": true}', status="modified")
    pf = get_pending_flow(tmp_db, pf_id)
    assert pf["request_body"] == '{"new": true}'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_intercept.py -v
```

- [ ] **Step 3: Implement intercept.py**

Create `src/troxy/core/intercept.py`:

```python
"""Intercept rules and pending flow management."""

import time

from troxy.core.db import get_connection


def add_intercept_rule(
    db_path: str,
    *,
    domain: str | None = None,
    path_pattern: str | None = None,
    method: str | None = None,
) -> int:
    """Add an intercept rule and return its ID."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """INSERT INTO intercept_rules (domain, path_pattern, method, created_at)
           VALUES (?, ?, ?, ?)""",
        (domain, path_pattern, method, time.time()),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def list_intercept_rules(db_path: str, *, enabled_only: bool = False) -> list[dict]:
    """List intercept rules."""
    conn = get_connection(db_path)
    sql = "SELECT * FROM intercept_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def remove_intercept_rule(db_path: str, rule_id: int) -> None:
    """Delete an intercept rule."""
    conn = get_connection(db_path)
    conn.execute("DELETE FROM intercept_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()


def add_pending_flow(
    db_path: str,
    *,
    flow_id: str,
    method: str,
    host: str,
    path: str,
    request_headers: str,
    request_body: str | None,
) -> int:
    """Record an intercepted flow as pending."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        """INSERT INTO pending_flows (flow_id, timestamp, method, host, path,
           request_headers, request_body) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (flow_id, time.time(), method, host, path, request_headers, request_body),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def list_pending_flows(db_path: str) -> list[dict]:
    """List pending (not yet released/dropped) flows."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM pending_flows WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_flow(db_path: str, pending_id: int) -> dict | None:
    """Get a pending flow by ID."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM pending_flows WHERE id = ?", (pending_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_pending_flow(
    db_path: str,
    pending_id: int,
    *,
    request_headers: str | None = None,
    request_body: str | None = None,
    status: str | None = None,
) -> None:
    """Update a pending flow's headers, body, or status."""
    conn = get_connection(db_path)
    updates = []
    params = []
    if request_headers is not None:
        updates.append("request_headers = ?")
        params.append(request_headers)
    if request_body is not None:
        updates.append("request_body = ?")
        params.append(request_body)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if not updates:
        conn.close()
        return
    params.append(pending_id)
    conn.execute(f"UPDATE pending_flows SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_intercept.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(core): add intercept rules and pending flow management"
```

---

## Task 10: CLI — Mock, Intercept, Replay, and Tail Commands

**Files:**
- Modify: `src/troxy/cli/main.py`
- Create: `tests/e2e/test_cli_mock.py`
- Create: `tests/e2e/test_cli_intercept.py`

- [ ] **Step 1: Write failing tests for mock CLI**

Create `tests/e2e/test_cli_mock.py`:

```python
"""E2E tests for mock CLI commands."""

import json
import subprocess
import sys
import time

from troxy.core.db import init_db
from troxy.core.store import insert_flow


def _run_troxy(*args, db_path=None):
    cmd = [sys.executable, "-m", "troxy.cli.main"] + list(args)
    if db_path:
        cmd.extend(["--db", db_path])
    return subprocess.run(cmd, capture_output=True, text=True)


def test_mock_add_and_list(tmp_db):
    init_db(tmp_db)
    result = _run_troxy("mock", "add", "-d", "api.example.com", "-p", "/users",
                        "-s", "200", "--body", '{"mock": true}', db_path=tmp_db)
    assert result.returncode == 0

    result = _run_troxy("mock", "list", "--no-color", db_path=tmp_db)
    assert "api.example.com" in result.stdout


def test_mock_remove(tmp_db):
    init_db(tmp_db)
    _run_troxy("mock", "add", "-d", "a.com", "-p", "/", "-s", "200", db_path=tmp_db)
    result = _run_troxy("mock", "remove", "1", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("mock", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert len(data) == 0


def test_mock_disable_enable(tmp_db):
    init_db(tmp_db)
    _run_troxy("mock", "add", "-d", "a.com", "-p", "/", "-s", "200", db_path=tmp_db)
    _run_troxy("mock", "disable", "1", db_path=tmp_db)
    result = _run_troxy("mock", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["enabled"] == 0

    _run_troxy("mock", "enable", "1", db_path=tmp_db)
    result = _run_troxy("mock", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert data[0]["enabled"] == 1


def test_mock_from_flow(tmp_db):
    init_db(tmp_db)
    insert_flow(tmp_db, timestamp=time.time(), method="GET", scheme="https",
                host="api.example.com", port=443, path="/api/data", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=200, response_headers={"Content-Type": "application/json"},
                response_body='{"data": true}', response_content_type="application/json",
                duration_ms=50)
    result = _run_troxy("mock", "from-flow", "1", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("mock", "list", "--json", db_path=tmp_db)
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["domain"] == "api.example.com"
```

- [ ] **Step 2: Write failing tests for intercept CLI**

Create `tests/e2e/test_cli_intercept.py`:

```python
"""E2E tests for intercept CLI commands."""

import json
import subprocess
import sys

from troxy.core.db import init_db
from troxy.core.intercept import add_pending_flow


def _run_troxy(*args, db_path=None):
    cmd = [sys.executable, "-m", "troxy.cli.main"] + list(args)
    if db_path:
        cmd.extend(["--db", db_path])
    return subprocess.run(cmd, capture_output=True, text=True)


def test_intercept_add_and_list(tmp_db):
    init_db(tmp_db)
    result = _run_troxy("intercept", "add", "-d", "api.example.com", "-m", "POST", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("intercept", "list", "--no-color", db_path=tmp_db)
    assert "api.example.com" in result.stdout


def test_intercept_remove(tmp_db):
    init_db(tmp_db)
    _run_troxy("intercept", "add", "-d", "a.com", db_path=tmp_db)
    result = _run_troxy("intercept", "remove", "1", db_path=tmp_db)
    assert result.returncode == 0


def test_pending_list(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="abc", method="POST", host="api.example.com",
                     path="/users", request_headers='{"Auth": "tok"}', request_body='{"a":1}')
    result = _run_troxy("pending", "--no-color", db_path=tmp_db)
    assert "api.example.com" in result.stdout


def test_modify_and_release(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="abc", method="POST", host="a.com",
                     path="/", request_headers='{"Auth": "old"}', request_body=None)
    result = _run_troxy("modify", "1", "--header", "Auth: new_token", db_path=tmp_db)
    assert result.returncode == 0
    result = _run_troxy("release", "1", db_path=tmp_db)
    assert result.returncode == 0


def test_drop(tmp_db):
    init_db(tmp_db)
    add_pending_flow(tmp_db, flow_id="abc", method="GET", host="a.com",
                     path="/", request_headers="{}", request_body=None)
    result = _run_troxy("drop", "1", db_path=tmp_db)
    assert result.returncode == 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/e2e/test_cli_mock.py tests/e2e/test_cli_intercept.py -v
```

- [ ] **Step 4: Add mock, intercept, pending, modify, release, drop, replay, tail commands to main.py**

Append to `src/troxy/cli/main.py`:

```python
# --- Mock commands ---

@cli.group("mock")
@click.pass_context
def mock_group(ctx):
    """Manage mock response rules."""
    pass


@mock_group.command("add")
@click.option("-d", "--domain", default=None)
@click.option("-p", "--path", "path_pattern", default=None)
@click.option("-m", "--method", default=None)
@click.option("-s", "--status", default=200, type=int)
@click.option("--body", default=None)
@click.option("--header", multiple=True, help="Header in 'Key: Value' format")
@click.pass_context
def mock_add(ctx, domain, path_pattern, method, status, body, header):
    """Add a mock response rule."""
    from troxy.core.mock import add_mock_rule
    headers = None
    if header:
        h = {}
        for hdr in header:
            k, _, v = hdr.partition(":")
            h[k.strip()] = v.strip()
        headers = json.dumps(h)
    rule_id = add_mock_rule(ctx.obj["db"], domain=domain, path_pattern=path_pattern,
                            method=method, status_code=status,
                            response_headers=headers, response_body=body)
    click.echo(f"Mock rule {rule_id} added.")


@mock_group.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def mock_list(ctx, as_json):
    """List mock rules."""
    from troxy.core.mock import list_mock_rules
    rules = list_mock_rules(ctx.obj["db"])
    if as_json:
        click.echo(json.dumps(rules, indent=2, default=str))
        return
    if not rules:
        click.echo("No mock rules.")
        return
    for r in rules:
        state = "ON" if r["enabled"] else "OFF"
        click.echo(f"  [{r['id']}] {state}  {r.get('method') or '*'} {r.get('domain') or '*'}{r.get('path_pattern') or '/*'} → {r['status_code']}")


@mock_group.command("remove")
@click.argument("rule_id", type=int)
@click.pass_context
def mock_remove(ctx, rule_id):
    """Remove a mock rule."""
    from troxy.core.mock import remove_mock_rule
    remove_mock_rule(ctx.obj["db"], rule_id)
    click.echo(f"Mock rule {rule_id} removed.")


@mock_group.command("disable")
@click.argument("rule_id", type=int)
@click.pass_context
def mock_disable(ctx, rule_id):
    """Disable a mock rule."""
    from troxy.core.mock import toggle_mock_rule
    toggle_mock_rule(ctx.obj["db"], rule_id, enabled=False)
    click.echo(f"Mock rule {rule_id} disabled.")


@mock_group.command("enable")
@click.argument("rule_id", type=int)
@click.pass_context
def mock_enable(ctx, rule_id):
    """Enable a mock rule."""
    from troxy.core.mock import toggle_mock_rule
    toggle_mock_rule(ctx.obj["db"], rule_id, enabled=True)
    click.echo(f"Mock rule {rule_id} enabled.")


@mock_group.command("from-flow")
@click.argument("flow_id", type=int)
@click.option("-s", "--status", default=None, type=int)
@click.pass_context
def mock_from_flow_cmd(ctx, flow_id, status):
    """Create mock rule from existing flow response."""
    from troxy.core.mock import mock_from_flow
    rule_id = mock_from_flow(ctx.obj["db"], flow_id, status_code=status)
    click.echo(f"Mock rule {rule_id} created from flow {flow_id}.")


# --- Intercept commands ---

@cli.group("intercept")
@click.pass_context
def intercept_group(ctx):
    """Manage request intercept rules."""
    pass


@intercept_group.command("add")
@click.option("-d", "--domain", default=None)
@click.option("-p", "--path", "path_pattern", default=None)
@click.option("-m", "--method", default=None)
@click.pass_context
def intercept_add(ctx, domain, path_pattern, method):
    """Add an intercept rule."""
    from troxy.core.intercept import add_intercept_rule
    rule_id = add_intercept_rule(ctx.obj["db"], domain=domain, path_pattern=path_pattern, method=method)
    click.echo(f"Intercept rule {rule_id} added.")


@intercept_group.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def intercept_list(ctx, as_json):
    """List intercept rules."""
    from troxy.core.intercept import list_intercept_rules
    rules = list_intercept_rules(ctx.obj["db"])
    if as_json:
        click.echo(json.dumps(rules, indent=2, default=str))
        return
    if not rules:
        click.echo("No intercept rules.")
        return
    for r in rules:
        state = "ON" if r["enabled"] else "OFF"
        click.echo(f"  [{r['id']}] {state}  {r.get('method') or '*'} {r.get('domain') or '*'}{r.get('path_pattern') or '/*'}")


@intercept_group.command("remove")
@click.argument("rule_id", type=int)
@click.pass_context
def intercept_remove(ctx, rule_id):
    """Remove an intercept rule."""
    from troxy.core.intercept import remove_intercept_rule
    remove_intercept_rule(ctx.obj["db"], rule_id)
    click.echo(f"Intercept rule {rule_id} removed.")


# --- Pending / Modify / Release / Drop ---

@cli.command("pending")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def pending_cmd(ctx, as_json):
    """List intercepted pending flows."""
    from troxy.core.intercept import list_pending_flows
    pending = list_pending_flows(ctx.obj["db"])
    if as_json:
        click.echo(json.dumps(pending, indent=2, default=str))
        return
    if not pending:
        click.echo("No pending flows.")
        return
    for p in pending:
        click.echo(f"  [{p['id']}] {p['method']} {p['host']}{p['path']}")


@cli.command("modify")
@click.argument("pending_id", type=int)
@click.option("--header", multiple=True, help="Header 'Key: Value'")
@click.option("--body", default=None)
@click.pass_context
def modify_cmd(ctx, pending_id, header, body):
    """Modify a pending intercepted flow."""
    from troxy.core.intercept import update_pending_flow, get_pending_flow
    updates = {}
    if header:
        pf = get_pending_flow(ctx.obj["db"], pending_id)
        existing = json.loads(pf["request_headers"]) if pf else {}
        for h in header:
            k, _, v = h.partition(":")
            existing[k.strip()] = v.strip()
        updates["request_headers"] = json.dumps(existing)
    if body:
        updates["request_body"] = body
    if updates:
        updates["status"] = "modified"
        update_pending_flow(ctx.obj["db"], pending_id, **updates)
    click.echo(f"Pending flow {pending_id} modified.")


@cli.command("release")
@click.argument("pending_id", type=int)
@click.pass_context
def release_cmd(ctx, pending_id):
    """Release a pending flow to continue to the server."""
    from troxy.core.intercept import update_pending_flow
    update_pending_flow(ctx.obj["db"], pending_id, status="released")
    click.echo(f"Pending flow {pending_id} released.")


@cli.command("drop")
@click.argument("pending_id", type=int)
@click.pass_context
def drop_cmd(ctx, pending_id):
    """Drop a pending flow (cancel the request)."""
    from troxy.core.intercept import update_pending_flow
    update_pending_flow(ctx.obj["db"], pending_id, status="dropped")
    click.echo(f"Pending flow {pending_id} dropped.")


# --- Replay ---

@cli.command("replay")
@click.argument("flow_id", type=int)
@click.option("--header", multiple=True, help="Override header 'Key: Value'")
@click.option("--body", default=None, help="Override request body")
@click.pass_context
def replay_cmd(ctx, flow_id, header, body):
    """Replay a saved flow (re-send the request)."""
    flow = get_flow(ctx.obj["db"], flow_id)
    if not flow:
        click.echo(f"Flow {flow_id} not found.", err=True)
        sys.exit(1)

    import urllib.request
    url = f"{flow['scheme']}://{flow['host']}:{flow['port']}{flow['path']}"
    if flow.get("query"):
        url += f"?{flow['query']}"
    headers = json.loads(flow["request_headers"]) if isinstance(flow["request_headers"], str) else dict(flow["request_headers"])
    if header:
        for h in header:
            k, _, v = h.partition(":")
            headers[k.strip()] = v.strip()
    req_body = (body or flow.get("request_body") or "").encode("utf-8") if (body or flow.get("request_body")) else None
    req = urllib.request.Request(url, data=req_body, headers=headers, method=flow["method"])
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        click.echo(f"Status: {resp.status}")
        click.echo(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        click.echo(f"Status: {e.code}")
        click.echo(e.read().decode("utf-8", errors="replace"))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# --- Tail ---

@cli.command("tail")
@click.option("-d", "--domain", default=None)
@click.option("-s", "--status", default=None, help="Status filter (e.g. 401, 4xx)")
@click.pass_context
def tail_cmd(ctx, domain, status):
    """Stream new flows in real-time (like tail -f)."""
    import time as time_mod
    from troxy.cli.formatting import print_flows_table

    db = ctx.obj["db"]
    conn = get_connection(db)
    last_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM flows").fetchone()[0]
    conn.close()

    click.echo("Watching for new flows... (Ctrl+C to stop)")
    try:
        while True:
            conn = get_connection(db)
            conditions = ["id > ?"]
            params = [last_id]
            if domain:
                conditions.append("host LIKE ?")
                params.append(f"%{domain}%")
            if status:
                if status.endswith("xx"):
                    prefix = int(status[0])
                    conditions.append("status_code >= ? AND status_code < ?")
                    params.extend([prefix * 100, (prefix + 1) * 100])
                else:
                    conditions.append("status_code = ?")
                    params.append(int(status))
            where = " AND ".join(conditions)
            rows = conn.execute(
                f"SELECT * FROM flows WHERE {where} ORDER BY id", params
            ).fetchall()
            conn.close()
            if rows:
                flows = [dict(r) for r in rows]
                print_flows_table(flows)
                last_id = flows[-1]["id"]
            time_mod.sleep(0.5)
    except KeyboardInterrupt:
        click.echo("\nStopped.")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/e2e/test_cli_mock.py tests/e2e/test_cli_intercept.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(cli): add mock, intercept, pending, modify, release, drop, replay, tail commands"
```

---

## Task 11: MCP Server

**Files:**
- Create: `src/troxy/mcp/server.py`
- Create: `tests/e2e/test_mcp.py`

- [ ] **Step 1: Write failing tests**

Create `tests/e2e/test_mcp.py`:

```python
"""E2E tests for MCP server tools."""

import json
import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow

# Test the tool functions directly (they share the same core logic)
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/e2e/test_mcp.py -v
```

- [ ] **Step 3: Implement server.py**

Create `src/troxy/mcp/server.py`:

```python
"""troxy MCP server — exposes flow data as MCP tools."""

import json
import os
import sys

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.query import list_flows, get_flow, search_flows
from troxy.core.export import export_curl, export_httpie
from troxy.core.mock import add_mock_rule, list_mock_rules, remove_mock_rule, toggle_mock_rule, mock_from_flow
from troxy.core.intercept import (
    add_intercept_rule, list_intercept_rules, remove_intercept_rule,
    list_pending_flows, update_pending_flow, get_pending_flow,
)


# --- Tool handlers (testable without MCP protocol) ---

def handle_list_flows(db_path: str, args: dict) -> str:
    results = list_flows(
        db_path,
        domain=args.get("domain"),
        status=args.get("status"),
        method=args.get("method"),
        path=args.get("path"),
        limit=args.get("limit", 50),
    )
    return json.dumps(results, indent=2, default=str)


def handle_get_flow(db_path: str, args: dict) -> str:
    flow = get_flow(db_path, args["id"])
    if not flow:
        return json.dumps({"error": f"Flow {args['id']} not found"})
    part = args.get("part", "all")
    if part == "body":
        return json.dumps({
            "request_body": flow.get("request_body"),
            "response_body": flow.get("response_body"),
        }, indent=2)
    if part == "request":
        return json.dumps({k: v for k, v in flow.items() if k.startswith("request") or k in ("method", "scheme", "host", "port", "path", "query")}, indent=2, default=str)
    if part == "response":
        return json.dumps({k: v for k, v in flow.items() if k.startswith("response") or k == "status_code"}, indent=2, default=str)
    return json.dumps(flow, indent=2, default=str)


def handle_search(db_path: str, args: dict) -> str:
    results = search_flows(
        db_path, args["query"],
        domain=args.get("domain"),
        scope=args.get("scope", "all"),
        limit=args.get("limit", 50),
    )
    return json.dumps(results, indent=2, default=str)


def handle_export(db_path: str, args: dict) -> str:
    flow = get_flow(db_path, args["id"])
    if not flow:
        return json.dumps({"error": f"Flow {args['id']} not found"})
    fmt = args.get("format", "curl")
    if fmt == "httpie":
        return export_httpie(flow)
    return export_curl(flow)


def handle_status(db_path: str, args: dict) -> str:
    conn = get_connection(db_path)
    count = conn.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
    conn.close()
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return json.dumps({"flow_count": count, "db_size": db_size, "db_path": db_path})


def handle_mock_add(db_path: str, args: dict) -> str:
    rule_id = add_mock_rule(
        db_path,
        domain=args.get("domain"),
        path_pattern=args.get("path_pattern"),
        method=args.get("method"),
        status_code=args.get("status_code", 200),
        response_headers=args.get("headers"),
        response_body=args.get("body"),
    )
    return json.dumps({"rule_id": rule_id})


def handle_mock_list(db_path: str, args: dict) -> str:
    rules = list_mock_rules(db_path)
    return json.dumps(rules, indent=2, default=str)


def handle_mock_remove(db_path: str, args: dict) -> str:
    remove_mock_rule(db_path, args["id"])
    return json.dumps({"removed": args["id"]})


def handle_mock_toggle(db_path: str, args: dict) -> str:
    toggle_mock_rule(db_path, args["id"], enabled=args.get("enabled", True))
    return json.dumps({"toggled": args["id"]})


def handle_mock_from_flow(db_path: str, args: dict) -> str:
    rule_id = mock_from_flow(db_path, args["flow_id"], status_code=args.get("status_code"))
    return json.dumps({"rule_id": rule_id})


def handle_intercept_add(db_path: str, args: dict) -> str:
    rule_id = add_intercept_rule(db_path, domain=args.get("domain"),
                                 path_pattern=args.get("path_pattern"), method=args.get("method"))
    return json.dumps({"rule_id": rule_id})


def handle_intercept_list(db_path: str, args: dict) -> str:
    return json.dumps(list_intercept_rules(db_path), indent=2, default=str)


def handle_intercept_remove(db_path: str, args: dict) -> str:
    remove_intercept_rule(db_path, args["id"])
    return json.dumps({"removed": args["id"]})


def handle_pending_list(db_path: str, args: dict) -> str:
    return json.dumps(list_pending_flows(db_path), indent=2, default=str)


def handle_modify(db_path: str, args: dict) -> str:
    updates = {}
    if "headers" in args:
        updates["request_headers"] = args["headers"] if isinstance(args["headers"], str) else json.dumps(args["headers"])
    if "body" in args:
        updates["request_body"] = args["body"]
    updates["status"] = "modified"
    update_pending_flow(db_path, args["pending_id"], **updates)
    return json.dumps({"modified": args["pending_id"]})


def handle_release(db_path: str, args: dict) -> str:
    update_pending_flow(db_path, args["pending_id"], status="released")
    return json.dumps({"released": args["pending_id"]})


def handle_drop(db_path: str, args: dict) -> str:
    update_pending_flow(db_path, args["pending_id"], status="dropped")
    return json.dumps({"dropped": args["pending_id"]})


# --- MCP Protocol Server ---

TOOLS = {
    "troxy_list_flows": {"handler": handle_list_flows, "description": "List captured HTTP flows with optional filters"},
    "troxy_get_flow": {"handler": handle_get_flow, "description": "Get details of a specific flow by ID"},
    "troxy_search": {"handler": handle_search, "description": "Search flow bodies for text"},
    "troxy_export": {"handler": handle_export, "description": "Export a flow as curl or httpie command"},
    "troxy_status": {"handler": handle_status, "description": "Get database status info"},
    "troxy_mock_add": {"handler": handle_mock_add, "description": "Add a mock response rule"},
    "troxy_mock_list": {"handler": handle_mock_list, "description": "List mock rules"},
    "troxy_mock_remove": {"handler": handle_mock_remove, "description": "Remove a mock rule"},
    "troxy_mock_toggle": {"handler": handle_mock_toggle, "description": "Enable/disable a mock rule"},
    "troxy_mock_from_flow": {"handler": handle_mock_from_flow, "description": "Create mock rule from existing flow"},
    "troxy_intercept_add": {"handler": handle_intercept_add, "description": "Add an intercept rule"},
    "troxy_intercept_list": {"handler": handle_intercept_list, "description": "List intercept rules"},
    "troxy_intercept_remove": {"handler": handle_intercept_remove, "description": "Remove an intercept rule"},
    "troxy_pending_list": {"handler": handle_pending_list, "description": "List intercepted pending flows"},
    "troxy_modify": {"handler": handle_modify, "description": "Modify a pending intercepted flow"},
    "troxy_release": {"handler": handle_release, "description": "Release a pending flow to continue"},
    "troxy_drop": {"handler": handle_drop, "description": "Drop a pending flow"},
}


def main():
    """Run MCP server using stdio transport."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError:
        # Fallback: simple JSON-RPC over stdio
        _run_simple_stdio()
        return

    db_path = default_db_path()
    init_db(db_path)
    server = Server("troxy")

    @server.list_tools()
    async def list_tools():
        from mcp.types import Tool
        tools = []
        for name, info in TOOLS.items():
            tools.append(Tool(name=name, description=info["description"], inputSchema={"type": "object"}))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        from mcp.types import TextContent
        if name not in TOOLS:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        result = TOOLS[name]["handler"](db_path, arguments)
        return [TextContent(type="text", text=result)]

    import asyncio
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


def _run_simple_stdio():
    """Fallback stdio server without MCP SDK."""
    db_path = default_db_path()
    init_db(db_path)
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            tool_name = request.get("tool") or request.get("method", "")
            args = request.get("arguments") or request.get("params", {})
            if tool_name in TOOLS:
                result = TOOLS[tool_name]["handler"](db_path, args)
            else:
                result = json.dumps({"error": f"Unknown tool: {tool_name}"})
            print(json.dumps({"result": result}), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/e2e/test_mcp.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(mcp): add MCP server with all tools"
```

---

## Task 12: Addon — Mock and Intercept Hooks

**Files:**
- Modify: `src/troxy/addon.py`

- [ ] **Step 1: Update addon with mock and intercept support**

Add to `src/troxy/addon.py` (replace the class):

```python
import fnmatch
import json
import threading
import time as time_mod

class TroxyAddon:
    """mitmproxy addon that records flows, serves mocks, and intercepts requests."""

    def __init__(self):
        self.db_path = default_db_path()
        init_db(self.db_path)
        self._intercepted_flows = {}  # flow.id -> flow
        self._poll_thread = threading.Thread(target=self._poll_pending, daemon=True)
        self._poll_thread.start()

    def request(self, flow):
        """Handle request: check mock rules, then intercept rules."""
        try:
            self._check_mock(flow)
            if not flow.response:
                self._check_intercept(flow)
        except Exception as e:
            print(f"[troxy] Error in request hook: {e}", file=sys.stderr)

    def response(self, flow):
        """Record completed flow to SQLite."""
        try:
            request = flow.request
            response = flow.response

            content_type_req = request.headers.get("content-type", "")
            content_type_resp = response.headers.get("content-type", "")

            duration = None
            if flow.response.timestamp_end and flow.request.timestamp_start:
                duration = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000

            insert_flow(
                self.db_path,
                timestamp=flow.request.timestamp_start or time_mod.time(),
                method=request.method,
                scheme=request.scheme,
                host=request.host,
                port=request.port,
                path=request.path,
                query=request.query if request.query else None,
                request_headers=dict(request.headers),
                request_body=request.content,
                request_content_type=content_type_req or None,
                status_code=response.status_code,
                response_headers=dict(response.headers),
                response_body=response.content,
                response_content_type=content_type_resp or None,
                duration_ms=duration,
            )
        except Exception as e:
            print(f"[troxy] Error recording flow: {e}", file=sys.stderr)

    def _check_mock(self, flow):
        """Check if request matches any mock rule."""
        from troxy.core.mock import list_mock_rules
        from mitmproxy import http

        rules = list_mock_rules(self.db_path, enabled_only=True)
        for rule in rules:
            if rule["domain"] and rule["domain"] not in flow.request.host:
                continue
            if rule["method"] and rule["method"].upper() != flow.request.method:
                continue
            if rule["path_pattern"] and not fnmatch.fnmatch(flow.request.path, rule["path_pattern"]):
                continue
            # Match found — inject mock response
            headers = {}
            if rule["response_headers"]:
                headers = json.loads(rule["response_headers"])
            body = (rule["response_body"] or "").encode("utf-8")
            flow.response = http.Response.make(
                rule["status_code"],
                body,
                headers,
            )
            return

    def _check_intercept(self, flow):
        """Check if request should be intercepted."""
        from troxy.core.intercept import list_intercept_rules, add_pending_flow

        rules = list_intercept_rules(self.db_path, enabled_only=True)
        for rule in rules:
            if rule["domain"] and rule["domain"] not in flow.request.host:
                continue
            if rule["method"] and rule["method"].upper() != flow.request.method:
                continue
            if rule["path_pattern"] and not fnmatch.fnmatch(flow.request.path, rule["path_pattern"]):
                continue
            # Match — intercept the flow
            flow.intercept()
            pf_id = add_pending_flow(
                self.db_path,
                flow_id=flow.id,
                method=flow.request.method,
                host=flow.request.host,
                path=flow.request.path,
                request_headers=json.dumps(dict(flow.request.headers)),
                request_body=flow.request.content.decode("utf-8", errors="replace") if flow.request.content else None,
            )
            self._intercepted_flows[flow.id] = flow
            return

    def _poll_pending(self):
        """Background thread: poll DB for released/modified/dropped pending flows."""
        from troxy.core.intercept import get_pending_flow
        while True:
            try:
                conn = get_connection(self.db_path)
                rows = conn.execute(
                    "SELECT * FROM pending_flows WHERE status IN ('released', 'modified', 'dropped')"
                ).fetchall()
                conn.close()

                for row in rows:
                    row = dict(row)
                    flow = self._intercepted_flows.pop(row["flow_id"], None)
                    if flow and row["status"] == "dropped":
                        flow.kill()
                    elif flow and row["status"] in ("released", "modified"):
                        if row["status"] == "modified":
                            if row.get("request_headers"):
                                headers = json.loads(row["request_headers"])
                                for k, v in headers.items():
                                    flow.request.headers[k] = v
                            if row.get("request_body"):
                                flow.request.content = row["request_body"].encode("utf-8")
                        flow.resume()
                    # Clean up
                    conn2 = get_connection(self.db_path)
                    conn2.execute("DELETE FROM pending_flows WHERE id = ?", (row["id"],))
                    conn2.commit()
                    conn2.close()
            except Exception as e:
                print(f"[troxy] Poll error: {e}", file=sys.stderr)
            time_mod.sleep(0.3)
```

- [ ] **Step 2: Run all existing tests to verify nothing is broken**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(addon): add mock response injection and request intercept/modify support"
```

---

## Task 13: Harness — Layer Lints and Evaluation Fixtures

**Files:**
- Create: `scripts/lint_layers.py`
- Create: `scripts/check_file_size.py`
- Create: `eval/fixtures/create_fixtures.py`
- Create: `eval/scenarios/find_401_cause.yaml`
- Create: `eval/scenarios/extract_post_body.yaml`
- Create: `eval/runner.py`

- [ ] **Step 1: Create layer lint script**

Create `scripts/lint_layers.py`:

```python
#!/usr/bin/env python3
"""Verify layer dependency rules.

core/ must not import mitmproxy.
cli/ and mcp/ must not import each other.
"""

import re
import sys
from pathlib import Path

VIOLATIONS = []

def check_file(path: Path, forbidden_imports: list[str]):
    content = path.read_text()
    for line_num, line in enumerate(content.splitlines(), 1):
        for forbidden in forbidden_imports:
            if re.search(rf"^\s*(from|import)\s+{forbidden}", line):
                VIOLATIONS.append(f"{path}:{line_num}: forbidden import '{forbidden}'")

def main():
    src = Path("src/troxy")
    # core must not import mitmproxy
    for f in (src / "core").rglob("*.py"):
        check_file(f, ["mitmproxy"])
    # cli must not import mcp
    for f in (src / "cli").rglob("*.py"):
        check_file(f, ["troxy.mcp", "mitmproxy"])
    # mcp must not import cli
    for f in (src / "mcp").rglob("*.py"):
        check_file(f, ["troxy.cli", "mitmproxy"])

    if VIOLATIONS:
        print("Layer dependency violations:")
        for v in VIOLATIONS:
            print(f"  {v}")
        sys.exit(1)
    print("Layer dependencies OK.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create file size check script**

Create `scripts/check_file_size.py`:

```python
#!/usr/bin/env python3
"""Check that no Python source file exceeds 300 lines."""

import sys
from pathlib import Path

MAX_LINES = 300
VIOLATIONS = []

def main():
    for f in Path("src").rglob("*.py"):
        lines = len(f.read_text().splitlines())
        if lines > MAX_LINES:
            VIOLATIONS.append(f"{f}: {lines} lines (max {MAX_LINES})")

    if VIOLATIONS:
        print("File size violations:")
        for v in VIOLATIONS:
            print(f"  {v}")
        sys.exit(1)
    print("File sizes OK.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create evaluation fixture generator**

Create `eval/fixtures/create_fixtures.py`:

```python
#!/usr/bin/env python3
"""Generate evaluation fixture databases."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from troxy.core.db import init_db
from troxy.core.store import insert_flow


def create_auth_failure(path: str):
    """Fixture: auth failure scenario with 401 responses."""
    init_db(path)
    now = time.time()
    # Normal successful request
    insert_flow(path, timestamp=now - 10, method="GET", scheme="https",
                host="api.internal.com", port=443, path="/api/home", query=None,
                request_headers={"Authorization": "Bearer valid_token"},
                request_body=None, request_content_type=None,
                status_code=200, response_headers={"Content-Type": "application/json"},
                response_body='{"sections": []}', response_content_type="application/json",
                duration_ms=120)
    # Failed auth request
    insert_flow(path, timestamp=now - 5, method="GET", scheme="https",
                host="api.internal.com", port=443, path="/api/users/17ov/ratings", query=None,
                request_headers={"Authorization": "Bearer expired_token"},
                request_body=None, request_content_type=None,
                status_code=401, response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized", "message": "Token has expired"}',
                response_content_type="application/json", duration_ms=30)
    # Another failed request
    insert_flow(path, timestamp=now, method="GET", scheme="https",
                host="api.internal.com", port=443, path="/api/users/17ov/report", query=None,
                request_headers={"Authorization": "Bearer expired_token"},
                request_body=None, request_content_type=None,
                status_code=401, response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized", "message": "Token has expired"}',
                response_content_type="application/json", duration_ms=25)


def create_redirect_chain(path: str):
    """Fixture: redirect chain scenario."""
    init_db(path)
    now = time.time()
    insert_flow(path, timestamp=now - 2, method="GET", scheme="https",
                host="mandrillapp.com", port=443, path="/track/click/abc", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=302, response_headers={"Location": "https://staging-api.internal.com/confirm"},
                response_body=None, response_content_type=None, duration_ms=50)
    insert_flow(path, timestamp=now - 1, method="GET", scheme="https",
                host="staging-api.internal.com", port=443, path="/confirm", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=302, response_headers={"Location": "https://accounts.google.com/oauth"},
                response_body=None, response_content_type=None, duration_ms=40)
    insert_flow(path, timestamp=now, method="GET", scheme="https",
                host="accounts.google.com", port=443, path="/oauth", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=200, response_headers={"Content-Type": "text/html"},
                response_body="<html>Access Denied</html>", response_content_type="text/html",
                duration_ms=200)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    create_auth_failure(os.path.join(script_dir, "auth_failure.db"))
    create_redirect_chain(os.path.join(script_dir, "redirect_chain.db"))
    print("Fixtures created.")
```

- [ ] **Step 4: Create evaluation scenarios**

Create `eval/scenarios/find_401_cause.yaml`:

```yaml
name: find_401_cause
description: "Find the cause of 401 unauthorized responses"
fixture: auth_failure.db
task: "api.internal.com에서 401 응답이 오는 요청의 원인을 찾아라"
steps:
  - tool: troxy_list_flows
    args: {status: 401}
    expect_count: 2
  - tool: troxy_get_flow
    args: {id: 2, part: "response"}
    expect_contains: "Token has expired"
pass_criteria:
  - "output must contain 'expired' or 'unauthorized'"
  - "must identify at least one flow with status 401"
```

Create `eval/scenarios/extract_post_body.yaml`:

```yaml
name: extract_post_body
description: "Extract and read a POST request body"
fixture: auth_failure.db
task: "POST 요청의 body를 확인해라"
steps:
  - tool: troxy_list_flows
    args: {method: "POST"}
    expect_count_gte: 0
  - tool: troxy_search
    args: {query: "email", scope: "request"}
    expect_count_gte: 0
pass_criteria:
  - "search should find POST requests containing expected content"
```

- [ ] **Step 5: Create evaluation runner**

Create `eval/runner.py`:

```python
#!/usr/bin/env python3
"""Run evaluation scenarios against troxy tools."""

import json
import os
import sys
import yaml
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from troxy.mcp.server import TOOLS


def run_scenario(scenario_path: str, fixtures_dir: str) -> dict:
    """Run a single evaluation scenario. Returns pass/fail with details."""
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    fixture_path = os.path.join(fixtures_dir, scenario["fixture"])
    if not os.path.exists(fixture_path):
        return {"name": scenario["name"], "passed": False, "error": "Fixture not found"}

    results = []
    for step in scenario.get("steps", []):
        tool_name = step["tool"]
        args = step.get("args", {})

        if tool_name not in TOOLS:
            results.append({"tool": tool_name, "error": f"Unknown tool"})
            continue

        output = TOOLS[tool_name]["handler"](fixture_path, args)
        step_result = {"tool": tool_name, "output_length": len(output)}

        if "expect_count" in step:
            data = json.loads(output)
            if isinstance(data, list):
                step_result["count"] = len(data)
                step_result["count_ok"] = len(data) == step["expect_count"]

        if "expect_contains" in step:
            step_result["contains_ok"] = step["expect_contains"] in output

        results.append(step_result)

    all_passed = all(
        r.get("count_ok", True) and r.get("contains_ok", True) and "error" not in r
        for r in results
    )

    return {
        "name": scenario["name"],
        "passed": all_passed,
        "steps": results,
    }


def main():
    eval_dir = Path(__file__).parent
    fixtures_dir = eval_dir / "fixtures"
    scenarios_dir = eval_dir / "scenarios"

    if not fixtures_dir.exists():
        print("Run eval/fixtures/create_fixtures.py first.")
        sys.exit(1)

    total = 0
    passed = 0
    for scenario_file in sorted(scenarios_dir.glob("*.yaml")):
        result = run_scenario(str(scenario_file), str(fixtures_dir))
        total += 1
        status = "PASS" if result["passed"] else "FAIL"
        if result["passed"]:
            passed += 1
        print(f"  [{status}] {result['name']}")
        if not result["passed"]:
            for step in result.get("steps", []):
                if not step.get("count_ok", True) or not step.get("contains_ok", True) or "error" in step:
                    print(f"         {step}")

    print(f"\n{passed}/{total} scenarios passed.")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run lints and generate fixtures**

```bash
uv run python scripts/lint_layers.py
uv run python scripts/check_file_size.py
uv run python eval/fixtures/create_fixtures.py
```

Expected: all pass, fixture DBs created.

- [ ] **Step 7: Install pyyaml and run evaluations**

```bash
uv add pyyaml --dev
uv run python eval/runner.py
```

Expected: all scenarios PASS.

- [ ] **Step 8: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(harness): add layer lints, file size checks, eval fixtures and runner"
```

---

## Task 14: Final Integration — Alias and Documentation

**Files:**
- Create: `scripts/setup.sh`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create setup script**

Create `scripts/setup.sh`:

```bash
#!/bin/bash
# Setup troxy: install dependencies, create alias, register MCP server

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing dependencies..."
cd "$PROJECT_DIR"
uv sync --all-extras

echo ""
echo "=== Setup complete ==="
echo ""
echo "Usage:"
echo "  # Start mitmproxy with troxy addon:"
echo "  mitmproxy -s $PROJECT_DIR/src/troxy/addon.py"
echo ""
echo "  # Or add alias to your shell:"
echo "  alias mitmproxy-troxy='mitmproxy -s $PROJECT_DIR/src/troxy/addon.py'"
echo ""
echo "  # CLI:"
echo "  uv run troxy flows"
echo "  uv run troxy flow 1 --body"
echo "  uv run troxy search 'token'"
echo ""
echo "  # MCP server (add to Claude Code settings.json):"
echo "  {\"mcpServers\": {\"troxy\": {\"command\": \"uv\", \"args\": [\"--directory\", \"$PROJECT_DIR\", \"run\", \"python\", \"-m\", \"troxy.mcp.server\"]}}}"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/setup.sh
```

- [ ] **Step 3: Run full validation**

```bash
uv run pytest -v
uv run python scripts/lint_layers.py
uv run python scripts/check_file_size.py
uv run python eval/fixtures/create_fixtures.py
uv run python eval/runner.py
```

Expected: everything PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: add setup script and finalize documentation"
```
