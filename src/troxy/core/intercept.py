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
    conn = get_connection(db_path)
    sql = "SELECT * FROM intercept_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def remove_intercept_rule(db_path: str, rule_id: int) -> None:
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
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM pending_flows WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_flow(db_path: str, pending_id: int) -> dict | None:
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
