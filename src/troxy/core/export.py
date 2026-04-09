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
