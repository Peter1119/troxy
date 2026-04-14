"""Mock rules CRUD operations."""

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
    name: str | None = None,
) -> int:
    """Add a mock rule and return its ID. Raises ValueError if name already exists."""
    conn = get_connection(db_path)
    if name:
        existing = conn.execute(
            "SELECT id FROM mock_rules WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.close()
            raise ValueError(f"Mock rule with name {name!r} already exists (id={existing[0]})")
    cursor = conn.execute(
        """INSERT INTO mock_rules (domain, path_pattern, method, status_code,
           response_headers, response_body, created_at, name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (domain, path_pattern, method, status_code,
         response_headers, response_body, time.time(), name),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def resolve_mock_ref(db_path: str, ref: str | int) -> int:
    """Resolve a rule reference (ID int or string name) to rule ID. Raises ValueError if not found."""
    conn = get_connection(db_path)
    try:
        rule_id = int(ref)
        row = conn.execute("SELECT id FROM mock_rules WHERE id = ?", (rule_id,)).fetchone()
    except (ValueError, TypeError):
        row = conn.execute("SELECT id FROM mock_rules WHERE name = ?", (str(ref),)).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Mock rule {ref!r} not found (pass ID or --name)")
    return row[0]


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


def mock_from_status(db_path: str, status: int, *, domain: str | None = None) -> int:
    """Create a mock rule from the most recent flow with the given status code.

    Useful for 'the last 401' style shortcuts — no need to look up a flow ID.
    """
    conn = get_connection(db_path)
    sql = "SELECT id FROM flows WHERE status_code = ?"
    params: list = [status]
    if domain:
        sql += " AND host LIKE ?"
        params.append(f"%{domain}%")
    sql += " ORDER BY timestamp DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    conn.close()
    if not row:
        raise ValueError(
            f"No flow found with status {status}"
            + (f" for domain containing {domain!r}" if domain else "")
        )
    return mock_from_flow(db_path, row[0])
