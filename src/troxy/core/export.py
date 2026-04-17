"""Export flows to curl/httpie format."""

import json
import shlex


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


def _decode_body_for_export(body) -> str | None:
    """Return text body suitable for shell export. Skips b64 binary bodies."""
    if body is None:
        return None
    if isinstance(body, str) and body.startswith("b64:"):
        return None
    return body if isinstance(body, str) else str(body)


def export_curl(flow: dict) -> str:
    """Export flow as a curl command with safe shell quoting."""
    url = _build_url(flow)
    method = flow["method"]
    headers = _parse_headers(flow)
    body = _decode_body_for_export(flow.get("request_body"))

    parts = ["curl"]
    if method != "GET":
        parts.extend(["-X", method])

    for key, value in headers.items():
        parts.extend(["-H", shlex.quote(f"{key}: {value}")])

    if body is not None:
        parts.extend(["--data-raw", shlex.quote(body)])

    parts.append(shlex.quote(url))
    return " ".join(parts)


def export_httpie(flow: dict) -> str:
    """Export flow as an httpie command with safe shell quoting."""
    url = _build_url(flow)
    method = flow["method"]
    headers = _parse_headers(flow)
    body = _decode_body_for_export(flow.get("request_body"))

    parts = ["http", method, shlex.quote(url)]

    for key, value in headers.items():
        parts.append(shlex.quote(f"{key}:{value}"))

    if body is not None:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                parts = ["http", "--json", method, shlex.quote(url)]
                for key, value in headers.items():
                    if key.lower() != "content-type":
                        parts.append(shlex.quote(f"{key}:{value}"))
                for k, v in parsed.items():
                    parts.append(shlex.quote(f"{k}={json.dumps(v, ensure_ascii=False)}"))
            else:
                parts.extend(["--raw", shlex.quote(body)])
        except (json.JSONDecodeError, TypeError):
            parts.extend(["--raw", shlex.quote(body)])

    return " ".join(parts)
