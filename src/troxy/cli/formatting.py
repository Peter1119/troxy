"""Terminal output formatting with rich."""

import json
from datetime import datetime

from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.text import Text

console = Console(width=200)

METHOD_COLORS = {
    "GET": "green",
    "POST": "blue",
    "PUT": "yellow",
    "PATCH": "yellow",
    "DELETE": "red",
    "HEAD": "dim",
    "OPTIONS": "dim",
}

STATUS_COLORS = {
    2: "green",
    3: "cyan",
    4: "yellow",
    5: "red",
}


def _method_style(method: str) -> str:
    return METHOD_COLORS.get(method, "white")


def _status_style(code: int) -> str:
    return STATUS_COLORS.get(code // 100, "white")


def _format_size(body: str | None) -> str:
    if not body:
        return "-"
    size = len(body.encode("utf-8")) if not body.startswith("b64:") else len(body) * 3 // 4
    if size < 1024:
        return f"{size}b"
    return f"{size / 1024:.1f}k"


def _format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _format_duration(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def print_flows_table(flows: list[dict]) -> None:
    """Print flow list as a rich table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="dim", width=6)
    table.add_column("Time", width=8)
    table.add_column("Method", width=7)
    table.add_column("Host", max_width=30)
    table.add_column("Path", max_width=40)
    table.add_column("Status", width=6)
    table.add_column("Size", width=8)
    table.add_column("Duration", width=8)

    for f in flows:
        method = f["method"]
        status = f["status_code"]
        table.add_row(
            str(f["id"]),
            _format_time(f["timestamp"]),
            Text(method, style=_method_style(method)),
            f["host"],
            f["path"],
            Text(str(status), style=_status_style(status)),
            _format_size(f.get("response_body")),
            _format_duration(f.get("duration_ms")),
        )
    console.print(table)


def print_flow_detail(flow: dict, *, request_only=False, response_only=False,
                      headers_only=False, body_only=False) -> None:
    """Print flow detail with sections."""
    if not response_only and not body_only:
        console.rule(f"[bold]Request[/bold]", style="blue")
        url = f"{flow['scheme']}://{flow['host']}{flow['path']}"
        if flow.get("query"):
            url += f"?{flow['query']}"
        console.print(f"[bold]{flow['method']}[/bold] {url}")
        if not body_only:
            headers = json.loads(flow["request_headers"]) if isinstance(flow["request_headers"], str) else flow["request_headers"]
            for k, v in headers.items():
                console.print(f"  {k}: {v}", style="dim")
        if not headers_only and flow.get("request_body"):
            console.print()
            _print_body(flow["request_body"], flow.get("request_content_type"))

    if request_only:
        return

    if not body_only:
        status = flow["status_code"]
        duration = _format_duration(flow.get("duration_ms"))
        console.rule(
            f"[bold]Response ({status})[/bold] {duration}",
            style=_status_style(status),
        )
        headers = json.loads(flow["response_headers"]) if isinstance(flow["response_headers"], str) else flow["response_headers"]
        if not body_only:
            for k, v in headers.items():
                console.print(f"  {k}: {v}", style="dim")

    if headers_only:
        return

    if flow.get("response_body"):
        if not body_only:
            console.print()
        _print_body(flow["response_body"], flow.get("response_content_type"))


def _print_body(body: str, content_type: str | None) -> None:
    """Print body with JSON highlighting if applicable."""
    if body.startswith("b64:"):
        console.print(f"[dim](binary, {len(body) * 3 // 4} bytes, base64 encoded)[/dim]")
        return
    if content_type and "json" in content_type:
        try:
            parsed = json.loads(body)
            console.print(JSON(json.dumps(parsed, indent=2, ensure_ascii=False)))
            return
        except json.JSONDecodeError:
            pass
    console.print(body)


def print_status(db_path: str, flow_count: int, db_size: int) -> None:
    """Print database status info."""
    console.print(f"DB path:  {db_path}")
    console.print(f"Flows:    {flow_count}")
    size_str = f"{db_size / 1024:.1f}KB" if db_size < 1024 * 1024 else f"{db_size / 1024 / 1024:.1f}MB"
    console.print(f"Size:     {size_str}")
