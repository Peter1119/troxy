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
