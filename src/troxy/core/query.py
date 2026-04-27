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


def delete_all_flows(db_path: str) -> int:
    """Delete all flows and return the count deleted."""
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM flows")
    count = cursor.fetchone()[0]
    conn.execute("DELETE FROM flows")
    conn.commit()
    conn.close()
    return count


def list_flows_filtered(db_path: str, filter_text: str, *, limit: int = 500) -> list[dict]:
    """List flows using filter expression syntax (host:X status:4xx method:POST)."""
    from troxy.core.filter_parser import parse_filter

    parsed = parse_filter(filter_text)
    if not parsed:
        return list_flows(db_path, limit=limit)

    conn = get_connection(db_path)
    conditions = []
    params = []

    if "domain" in parsed:
        conditions.append("host LIKE ?")
        params.append(f"%{parsed['domain']}%")
    if "status" in parsed:
        conditions.append("status_code = ?")
        params.append(parsed["status"])
    if "status_range" in parsed:
        lo, hi = parsed["status_range"]
        conditions.append("status_code BETWEEN ? AND ?")
        params.extend([lo, hi])
    if "method" in parsed:
        conditions.append("UPPER(method) = ?")
        params.append(parsed["method"])
    if "path" in parsed:
        conditions.append("path LIKE ?")
        params.append(parsed["path"].replace("*", "%"))

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT * FROM flows WHERE {where} ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]

    if "query" in parsed:
        q = parsed["query"].lower()
        results = [
            r for r in results
            if q in (r.get("request_body") or "").lower()
            or q in (r.get("response_body") or "").lower()
            or q in (r.get("request_headers") or "").lower()
            or q in (r.get("response_headers") or "").lower()
            or q in (r.get("path") or "").lower()
        ]

    return results


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
