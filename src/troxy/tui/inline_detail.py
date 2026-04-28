"""InlineDetailPanel — collapsible side-view of the highlighted flow's detail.

Lives next to the flow table inside ListScreen so the user can preview
headers / body without losing the list context. Pushing the dedicated
DetailScreen via Enter is still available for full-screen interaction.
"""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from troxy.core.query import get_flow
from troxy.tui.detail_helpers import (
    body_renderable,
    parse_body_as_json,
    parse_headers,
    render_headers,
)
from troxy.tui.theme import method_color, status_color


class InlineDetailPanel(Widget):
    """Right-hand panel rendering a single flow's detail. Hidden until toggled."""

    DEFAULT_CSS = """
    InlineDetailPanel {
        display: none;
        width: 60;
        background: $surface;
        border-left: solid $primary-darken-1;
        padding: 0 1;
    }
    InlineDetailPanel.visible {
        display: block;
    }
    InlineDetailPanel #side-detail-pane {
        overflow-y: scroll;
    }
    """

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static(id="side-detail-pane"),
            id="side-detail-scroll",
        )

    def show(self) -> None:
        self.add_class("visible")

    def hide(self) -> None:
        self.remove_class("visible")

    def is_visible(self) -> bool:
        return self.has_class("visible")

    def update_for_flow(self, db_path: str, flow_id: int | None) -> None:
        pane = self.query_one("#side-detail-pane", Static)
        if flow_id is None:
            pane.update(Text("(no row selected)", style="dim italic"))
            return
        flow = get_flow(db_path, flow_id)
        if not flow:
            pane.update(Text(f"(flow {flow_id} not found)", style="dim italic"))
            return
        pane.update(_compose_summary(flow))


def _compose_summary(flow: dict) -> Group:
    method = flow["method"]
    status = int(flow["status_code"])
    head = Text()
    head.append(f"#{flow['id']}  ", style="bold")
    head.append(method, style=f"bold {method_color(method)}")
    head.append("  ")
    head.append(str(status), style=f"bold {status_color(status)}")
    head.append(f"  {flow.get('duration_ms') or 0:.0f}ms", style="dim")
    head.append("\n")
    head.append(f"{flow['scheme']}://{flow['host']}{flow['path']}", style="")

    req_headers = render_headers(parse_headers(flow["request_headers"]))
    req_body = _summarize_body(flow.get("request_body"), flow.get("request_content_type"))
    req_panel = Panel(
        Group(req_headers, req_body),
        title="REQUEST",
        title_align="left",
        border_style=method_color(method),
        padding=(0, 1),
    )

    res_headers = render_headers(parse_headers(flow["response_headers"]))
    res_body = _summarize_body(flow.get("response_body"), flow.get("response_content_type"))
    res_panel = Panel(
        Group(res_headers, res_body),
        title="RESPONSE",
        title_align="left",
        border_style=status_color(status),
        padding=(0, 1),
    )

    return Group(head, Text(""), req_panel, res_panel)


def _summarize_body(body, content_type):
    if not body:
        return Text("(no body)", style="dim italic")
    json_data = parse_body_as_json(body, content_type)
    if json_data is not None:
        # Show top-level keys only — full tree lives in DetailScreen.
        if isinstance(json_data, dict):
            keys = list(json_data.keys())
            preview = ", ".join(keys[:6])
            extra = f" +{len(keys) - 6} more" if len(keys) > 6 else ""
            return Text(f"(JSON: {preview}{extra})", style="dim italic")
        if isinstance(json_data, list):
            return Text(f"(JSON array, {len(json_data)} items)", style="dim italic")
    rendered = body_renderable(body, content_type)
    return rendered if rendered is not None else Text("(empty)", style="dim italic")
