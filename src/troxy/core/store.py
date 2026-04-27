"""Flow storage — insert flows into SQLite."""

import base64
import json
import os

from troxy.core.db import get_connection


def _max_body_bytes() -> int | None:
    """Parse TROXY_MAX_BODY env (e.g. '1MB', '500KB', '0' for unlimited).

    Default: 1MB. Only applied to new writes — historical flows are never retroactively truncated.
    """
    raw = os.environ.get("TROXY_MAX_BODY", "1MB").strip().upper()
    if raw in ("0", "OFF", "NONE", "UNLIMITED"):
        return None
    units = {"B": 1, "KB": 1024, "MB": 1024 * 1024, "GB": 1024 * 1024 * 1024}
    for suffix, mult in units.items():
        if raw.endswith(suffix):
            try:
                return int(float(raw[:-len(suffix)]) * mult)
            except ValueError:
                return 1024 * 1024
    try:
        return int(raw)
    except ValueError:
        return 1024 * 1024


def _encode_body(body, content_type: str | None) -> str | None:
    """Encode body for storage. Text as-is, binary as b64:..., truncated per TROXY_MAX_BODY."""
    if body is None:
        return None
    max_bytes = _max_body_bytes()
    if isinstance(body, bytes):
        truncated = False
        if max_bytes is not None and len(body) > max_bytes:
            body = body[:max_bytes]
            truncated = True
        if content_type and (
            content_type.startswith("text/")
            or "json" in content_type
            or "xml" in content_type
            or "javascript" in content_type
            or "html" in content_type
            or "x-www-form-urlencoded" in content_type
        ):
            try:
                text = body.decode("utf-8", errors="replace")
                return text + f"\n[truncated at {max_bytes}B]" if truncated else text
            except UnicodeDecodeError:
                pass
        encoded = "b64:" + base64.b64encode(body).decode("ascii")
        return encoded + f"\n[truncated at {max_bytes}B]" if truncated else encoded
    s = str(body)
    if max_bytes is not None and len(s.encode("utf-8", errors="replace")) > max_bytes:
        return s.encode("utf-8", errors="replace")[:max_bytes].decode("utf-8", errors="replace") \
            + f"\n[truncated at {max_bytes}B]"
    return s


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
