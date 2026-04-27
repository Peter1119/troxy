"""Pure helpers for DetailScreen — extracted to keep detail_screen.py
under the 300-line file-size cap. No textual/app state here: only
input → rendered output transformations."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qsl

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


_BINARY_CONTENT_HINTS = (
    "octet-stream",
    "image/",
    "audio/",
    "video/",
    "application/pdf",
    "application/zip",
    "application/x-protobuf",
    "application/grpc",
)


def unfold_b64_text(body, content_type=None):
    """If body was stored with a ``b64:`` prefix (binary fallback in store.py)
    but is actually utf-8 text, return the decoded string. Otherwise return body
    unchanged (or None for genuinely binary payloads).

    Skips unfolding when content_type advertises a binary payload — that's a
    capture-time signal we should respect even if the bytes happen to be
    utf-8-decodable.
    """
    if not isinstance(body, str) or not body.startswith("b64:"):
        return body
    ct = (content_type or "").lower()
    if any(hint in ct for hint in _BINARY_CONTENT_HINTS):
        return body
    try:
        return base64.b64decode(body[4:], validate=False).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return body


def parse_body_as_json(body, content_type):
    """Return parsed Python obj if body is JSON-like, else None.

    Used by DetailScreen to decide whether to render a collapsible Tree
    view (interactive) or fall back to a Syntax block (static).
    """
    if not isinstance(body, str):
        return None
    body = unfold_b64_text(body, content_type)
    if not isinstance(body, str) or body.startswith("b64:"):
        return None
    stripped = body.lstrip().lstrip("﻿")  # tolerate BOM-prefixed payloads
    if not stripped:
        return None
    ct = (content_type or "").lower()
    looks_json = stripped[:1] in ("{", "[")
    ct_is_json = "json" in ct or "+json" in ct
    if not (looks_json or ct_is_json):
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None


def populate_json_tree(tree, data) -> None:
    """Wipe the tree and reseed with `data`. Root expands so the first level
    of keys is visible; deeper nodes stay collapsed (user opens on demand)."""
    tree.clear()
    _populate_node(tree.root, data)
    tree.root.expand()


def _populate_node(node, value) -> None:
    if isinstance(value, dict):
        if not value:
            node.add_leaf(Text("{}", style="dim"))
            return
        for k, v in value.items():
            _add_kv_node(node, str(k), v)
    elif isinstance(value, list):
        if not value:
            node.add_leaf(Text("[]", style="dim"))
            return
        for i, v in enumerate(value):
            _add_kv_node(node, f"[{i}]", v)
    else:
        node.add_leaf(_format_primitive(value))


def _add_kv_node(parent, key: str, value) -> None:
    if isinstance(value, (dict, list)):
        size = len(value)
        kind = "{}" if isinstance(value, dict) else "[]"
        label = Text()
        label.append(key, style="bold cyan")
        label.append(": ", style="dim")
        label.append(f"{kind[0]} {size} item{'s' if size != 1 else ''} {kind[1]}", style="dim")
        child = parent.add(label)
        _populate_node(child, value)
    else:
        label = Text()
        label.append(key, style="bold cyan")
        label.append(": ", style="dim")
        label.append_text(_format_primitive(value))
        parent.add_leaf(label)


def _format_primitive(value) -> Text:
    if value is None:
        return Text("null", style="italic dim")
    if isinstance(value, bool):
        return Text(str(value).lower(), style="bold magenta")
    if isinstance(value, (int, float)):
        return Text(str(value), style="bold yellow")
    if isinstance(value, str):
        v = value if len(value) <= HEADER_VALUE_FOLD else value[:HEADER_VALUE_FOLD - 3] + "..."
        return Text(f'"{v}"', style="green")
    return Text(repr(value))


def body_renderable(body, content_type) -> RenderableType | None:
    """Return a rich renderable for the body, or None if empty."""
    if not body:
        return None
    body = unfold_b64_text(body, content_type)
    if isinstance(body, str) and body.startswith("b64:"):
        return Text(f"(binary, {len(body)} bytes base64)", style="dim italic")
    looks_json = isinstance(body, str) and body.lstrip()[:1] in ("{", "[")
    if (content_type and "json" in content_type) or looks_json:
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
    if isinstance(body, str) and _looks_form_urlencoded(body, content_type):
        rendered = _render_form_body(body)
        if rendered is not None:
            return rendered
    return Text(body)


def _looks_form_urlencoded(body: str, content_type) -> bool:
    if content_type and "x-www-form-urlencoded" in content_type:
        return True
    if "=" in body and "\n" not in body and "<" not in body[:1]:
        # Heuristic: body has key=value pairs and is single-line / no HTML.
        return all("=" in pair for pair in body.split("&") if pair)
    return False


def _render_form_body(body: str) -> Text | None:
    """Pretty-print form-urlencoded body — one ``key: value`` per line, URL-decoded."""
    try:
        pairs = parse_qsl(body, keep_blank_values=True, strict_parsing=False)
    except ValueError:
        return None
    if not pairs:
        return None
    t = Text()
    for i, (k, v) in enumerate(pairs):
        if i > 0:
            t.append("\n")
        key_padded = str(k)[:HEADER_KEY_WIDTH].ljust(HEADER_KEY_WIDTH)
        t.append(f"  {key_padded}  ", style="dim")
        t.append_text(fold_value(v))
    return t


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
