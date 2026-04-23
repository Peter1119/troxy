"""Pure helpers for DetailScreen — extracted to keep detail_screen.py
under the 300-line file-size cap. No textual/app state here: only
input → rendered output transformations."""

from __future__ import annotations

import json

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.text import Text

QUERY_PREVIEW_MAX = 32
HEADER_KEY_WIDTH = 20
HEADER_VALUE_FOLD = 80


def append_field(t: Text, label: str, value: str) -> None:
    t.append(f"{label}: ", style="dim")
    t.append(value)


def preview_query(query: str) -> str:
    """Trim query for display; full value remains available via ``u`` copy."""
    if len(query) <= QUERY_PREVIEW_MAX:
        return query
    byte_count = len(query.encode("utf-8", errors="replace"))
    return f"{query[:16]}...({byte_count}b)"


def fold_value(value) -> Text:
    if value is None:
        return Text("")
    v = str(value)
    if len(v) <= HEADER_VALUE_FOLD:
        return Text(v)
    size = len(v.encode("utf-8", errors="replace"))
    t = Text(v[: HEADER_VALUE_FOLD - 24])
    t.append(f"...({size}b, y to copy)", style="dim italic")
    return t


def render_headers(headers: dict) -> Text:
    """Format headers as dim 20-char keys + value, folding long values."""
    t = Text()
    for i, (k, v) in enumerate(headers.items()):
        if i > 0:
            t.append("\n")
        key_padded = str(k)[:HEADER_KEY_WIDTH].ljust(HEADER_KEY_WIDTH)
        t.append(f"  {key_padded}  ", style="dim")
        t.append_text(fold_value(v))
    return t


def parse_headers(headers) -> dict:
    if isinstance(headers, str):
        try:
            return json.loads(headers)
        except json.JSONDecodeError:
            return {}
    return dict(headers) if headers else {}


def body_renderable(body, content_type) -> RenderableType | None:
    """Return a rich renderable for the body, or None if empty."""
    if not body:
        return None
    if isinstance(body, str) and body.startswith("b64:"):
        return Text(f"(binary, {len(body)} bytes base64)", style="dim italic")
    if content_type and "json" in content_type:
        try:
            pretty = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
            return Syntax(
                pretty,
                "json",
                theme="monokai",
                background_color="default",
                word_wrap=True,
            )
        except (json.JSONDecodeError, TypeError):
            pass
    return Text(body)


def format_size(body: str | None) -> str:
    if not body:
        return "0 bytes"
    size = len(body.encode("utf-8", errors="replace"))
    if size < 1024:
        return f"{size} bytes"
    return f"{size / 1024:.1f} KB"


def get_url(flow: dict) -> str:
    url = f"{flow['scheme']}://{flow['host']}"
    if flow.get("port") and flow["port"] not in (80, 443):
        url += f":{flow['port']}"
    url += flow["path"]
    if flow.get("query"):
        url += f"?{flow['query']}"
    return url


def build_request_text(flow: dict) -> str:
    lines = [f"{flow['method']} {get_url(flow)}"]
    for k, v in parse_headers(flow["request_headers"]).items():
        lines.append(f"{k}: {v}")
    if flow.get("request_body"):
        lines.append("")
        lines.append(flow["request_body"])
    return "\n".join(lines)


def build_response_text(flow: dict) -> str:
    lines = [f"HTTP {flow['status_code']}"]
    for k, v in parse_headers(flow["response_headers"]).items():
        lines.append(f"{k}: {v}")
    if flow.get("response_body"):
        lines.append("")
        lines.append(flow["response_body"])
    return "\n".join(lines)
