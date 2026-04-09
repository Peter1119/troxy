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
