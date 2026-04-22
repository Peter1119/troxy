"""troxy TUI — interactive flow inspector built on textual."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Label, RichLog, Static

from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from troxy.core.db import init_db, get_connection
from troxy.core.query import list_flows, get_flow


METHOD_COLORS = {
    "GET": "green", "POST": "blue", "PUT": "yellow",
    "PATCH": "yellow", "DELETE": "red", "HEAD": "dim", "OPTIONS": "dim",
}
STATUS_COLORS = {2: "green", 3: "cyan", 4: "yellow", 5: "red"}


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _fmt_dur(ms: float | None) -> str:
    if ms is None:
        return "-"
    return f"{ms:.0f}ms" if ms < 1000 else f"{ms / 1000:.1f}s"


def _fmt_size(body: str | None) -> str:
    if not body:
        return "-"
    size = len(body.encode("utf-8")) if not body.startswith("b64:") else len(body) * 3 // 4
    if size < 1024:
        return f"{size}b"
    return f"{size / 1024:.1f}k"


def _short_method(m: str) -> str:
    return {"DELETE": "DEL", "OPTIONS": "OPT", "PATCH": "PAT"}.get(m, m)


def _body_text(body: str | None, content_type: str | None) -> str:
    if not body:
        return ""
    if body.startswith("b64:"):
        return "(binary)"
    if content_type and "json" in content_type:
        try:
            return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return body


def _headers_text(raw: str | dict | None) -> str:
    if not raw:
        return ""
    headers = json.loads(raw) if isinstance(raw, str) else raw
    return "\n".join(f"{k}: {v}" for k, v in headers.items())


def _write_body(log: RichLog, body: str, content_type: str | None) -> None:
    if body.startswith("b64:"):
        log.write("[dim](binary, base64 encoded)[/dim]")
        return
    if content_type and "json" in content_type:
        try:
            parsed = json.loads(body)
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            log.write(Syntax(formatted, "json", theme="monokai"))
            return
        except json.JSONDecodeError:
            pass
    if len(body) > 10000:
        log.write(body[:10000])
        log.write(f"\n[dim]... ({len(body)} chars total)[/dim]")
    else:
        log.write(body)


# ── CSS ──

APP_CSS = """\
#flow-table {
    height: 1fr;
}
#flow-table.hidden {
    display: none;
}

#filter-bar {
    dock: top;
    height: 3;
    display: none;
    background: $surface;
    padding: 0 1;
}
#filter-bar.visible {
    display: block;
}

.filter-label {
    width: auto;
    padding: 0 1 0 0;
    content-align: center middle;
}
.filter-input {
    width: 1fr;
    margin: 0 1 0 0;
}

#detail-header {
    dock: top;
    height: 1;
    display: none;
    background: $accent;
    color: $text;
    padding: 0 1;
}
#detail-header.visible {
    display: block;
}

#detail-tabs {
    dock: top;
    height: 1;
    display: none;
    padding: 0 1;
    background: $surface;
}
#detail-tabs.visible {
    display: block;
}

#detail-log {
    height: 1fr;
    display: none;
}
#detail-log.visible {
    display: block;
}

#cmd-bar {
    dock: bottom;
    height: 1;
    display: none;
    background: $surface;
}
#cmd-bar.visible {
    display: block;
}

#status-bar {
    dock: bottom;
    height: 1;
    background: $surface;
    color: $text;
    padding: 0 1;
}
"""


class TroxyApp(App):
    TITLE = "troxy"
    CSS = APP_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("enter", "open_detail", "Detail", show=True),
        Binding("escape", "go_back", "Back", show=True, priority=True),
        Binding("f", "toggle_filter", "Filter", show=True, priority=True),
        Binding("x", "clear_flows", "Clear", show=True, priority=True),
        Binding("1", "tab_overview", "Overview", show=False, priority=True),
        Binding("2", "tab_request", "Request", show=False, priority=True),
        Binding("3", "tab_response", "Response", show=False, priority=True),
        Binding("left", "tab_prev", "← Prev tab", show=False, priority=True),
        Binding("right", "tab_next", "→ Next tab", show=False, priority=True),
        Binding("s", "toggle_sort", "Sort", show=True, priority=True),
        Binding("c", "copy_tab", "Copy", show=True, priority=True),
        Binding("colon", "open_cmd", ":", show=False, priority=True),
    ]

    flow_count: reactive[int] = reactive(0)

    def __init__(
        self,
        db_path: str,
        port: int = 0,
        domain: str | None = None,
        proxy_proc: subprocess.Popen | None = None,
    ):
        super().__init__()
        self.db_path = db_path
        self.port = port
        self.domain = domain
        self.proxy_proc = proxy_proc
        self._last_id = 0
        self._flow_ids: list[int] = []
        self._all_flows: list[dict] = []
        self._filter_domain: str = domain or ""
        self._filter_path: str = ""
        self._filter_method: str = ""
        self._filter_status: str = ""
        self._proxy_exited = False
        self._sort_desc = True  # True = newest first (default)
        self._local_ip = self._get_local_ip()
        self._in_detail = False
        self._detail_flow: dict | None = None
        self._detail_tab = "response"  # default to response
        self._focus_on_tabs = False  # True = tab bar focused, False = content focused

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label("Host:", classes="filter-label"),
            Input(placeholder="e.g. api.example.com", value=self._filter_domain,
                  id="filter-domain", classes="filter-input"),
            Label("Path:", classes="filter-label"),
            Input(placeholder="e.g. /api", id="filter-path", classes="filter-input"),
            Label("Mtd:", classes="filter-label"),
            Input(placeholder="GET", id="filter-method", classes="filter-input"),
            Label("St:", classes="filter-label"),
            Input(placeholder="200", id="filter-status", classes="filter-input"),
            id="filter-bar",
        )
        yield Static(id="detail-header")
        yield Static(id="detail-tabs")
        yield DataTable(id="flow-table")
        yield RichLog(id="detail-log", wrap=True, highlight=True, markup=True)
        yield Input(placeholder="command (c=copy cURL, j=copy JSON)", id="cmd-bar")
        yield Static(id="status-bar")

    def on_mount(self) -> None:
        try:
            table = self.query_one("#flow-table", DataTable)
            table.cursor_type = "row"
            table.zebra_stripes = True
            table.add_columns("Time", "Mtd", "St", "Host", "Path", "Size", "Dur")

            init_db(self.db_path)
            conn = get_connection(self.db_path)
            row = conn.execute("SELECT MAX(id) FROM flows").fetchone()
            conn.close()
            self._last_id = (row[0] or 0) if row else 0

            self._update_status()
            self.set_interval(1.0, self._poll_once)
        except Exception as e:
            self.notify(f"Mount error: {e}", severity="error")

    # ── Polling ──

    def _poll_once(self) -> None:
        if self.proxy_proc and not self._proxy_exited and self.proxy_proc.poll() is not None:
            self._proxy_exited = True
            self.notify("Proxy exited", severity="error")
            self._update_status()
        try:
            conn = get_connection(self.db_path)
            new_rows = conn.execute(
                "SELECT * FROM flows WHERE id > ? ORDER BY id", [self._last_id]
            ).fetchall()
            conn.close()
        except Exception:
            return
        if new_rows:
            for row in new_rows:
                f = dict(row)
                self._all_flows.append(f)
                if f["id"] > self._last_id:
                    self._last_id = f["id"]
            if not self._in_detail:
                self._apply_filter()

    # ── Table ──

    def _add_flow_row(self, table: DataTable, f: dict) -> None:
        method = f["method"]
        status = f["status_code"]
        host = f.get("host", "")
        host_style = (
            "bold" if self._filter_domain and self._filter_domain.lower() in host.lower() else ""
        )
        table.add_row(
            Text(_fmt_time(f["timestamp"]), style="dim"),
            Text(_short_method(method), style=METHOD_COLORS.get(method, "white")),
            Text(str(status), style=STATUS_COLORS.get(status // 100, "white")),
            Text(f["host"], style=host_style),
            f["path"],
            _fmt_size(f.get("response_body")),
            _fmt_dur(f.get("duration_ms")),
        )
        self._flow_ids.append(f["id"])
        self.flow_count = len(self._flow_ids)

    # ── Filter ──

    def _matches_filter(self, f: dict) -> bool:
        if self._filter_domain and self._filter_domain.lower() not in f.get("host", "").lower():
            return False
        if self._filter_path and self._filter_path.lower() not in f.get("path", "").lower():
            return False
        if self._filter_method and self._filter_method.upper() != f.get("method", "").upper():
            return False
        if self._filter_status:
            try:
                if int(self._filter_status) != f.get("status_code"):
                    return False
            except ValueError:
                pass
        return True

    def _apply_filter(self) -> None:
        table = self.query_one("#flow-table", DataTable)
        table.clear()
        self._flow_ids.clear()
        filtered = [f for f in self._all_flows if self._matches_filter(f)]
        filtered.sort(key=lambda f: f.get("timestamp", 0), reverse=self._sort_desc)
        for f in filtered:
            self._add_flow_row(table, f)
        self._update_status()

    def _read_filter_inputs(self) -> None:
        self._filter_domain = self.query_one("#filter-domain", Input).value.strip()
        self._filter_path = self.query_one("#filter-path", Input).value.strip()
        self._filter_method = self.query_one("#filter-method", Input).value.strip()
        self._filter_status = self.query_one("#filter-status", Input).value.strip()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("filter-"):
            self._read_filter_inputs()
            self._apply_filter()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cmd-bar":
            cmd = event.input.value.strip()
            event.input.value = ""
            self.query_one("#cmd-bar").remove_class("visible")
            self._handle_cmd(cmd)
            # Re-focus detail log
            self.query_one("#detail-log", RichLog).focus()

    def _handle_cmd(self, cmd: str) -> None:
        flow = self._detail_flow
        if not flow:
            return
        if cmd == "c":
            from troxy.core.export import export_curl
            self.copy_to_clipboard(export_curl(flow))
            self.notify("Copied as cURL")
        elif cmd == "j":
            self.copy_to_clipboard(json.dumps(flow, indent=2, ensure_ascii=False, default=str))
            self.notify("Copied as JSON")
        elif cmd == "u":
            self.copy_to_clipboard(self._flow_url(flow))
            self.notify("Copied URL")
        else:
            self.notify(f"Unknown: {cmd}  (c=cURL j=JSON u=URL)", severity="warning")

    def action_toggle_filter(self) -> None:
        if self._in_detail:
            return
        bar = self.query_one("#filter-bar")
        if bar.has_class("visible"):
            bar.remove_class("visible")
            self.query_one("#flow-table", DataTable).focus()
        else:
            bar.add_class("visible")
            self.query_one("#filter-domain", Input).focus()

    def action_toggle_sort(self) -> None:
        if self._in_detail:
            return
        self._sort_desc = not self._sort_desc
        order = "newest first" if self._sort_desc else "oldest first"
        self.notify(f"Sort: {order}")
        self._apply_filter()

    def action_clear_flows(self) -> None:
        if self._in_detail:
            return
        self._all_flows.clear()
        self._flow_ids.clear()
        self.query_one("#flow-table", DataTable).clear()
        self.flow_count = 0
        self._update_status()
        self.notify("Cleared")

    # ── Detail ──

    def _flow_url(self, flow: dict) -> str:
        url = f"{flow['scheme']}://{flow['host']}{flow['path']}"
        if flow.get("query"):
            url += f"?{flow['query']}"
        return url

    def action_open_detail(self) -> None:
        if self._in_detail:
            # If on tab bar, go into content
            if self._focus_on_tabs:
                self._focus_on_tabs = False
                self._render_tab()
                self.query_one("#detail-log", RichLog).focus()
            return
        table = self.query_one("#flow-table", DataTable)
        row = table.cursor_row
        if row is not None and row < len(self._flow_ids):
            flow_id = self._flow_ids[row]
            flow = get_flow(self.db_path, flow_id)
            if flow:
                self._enter_detail(flow)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._in_detail:
            return
        if event.cursor_row < len(self._flow_ids):
            flow_id = self._flow_ids[event.cursor_row]
            flow = get_flow(self.db_path, flow_id)
            if flow:
                self._enter_detail(flow)

    def _enter_detail(self, flow: dict) -> None:
        self._in_detail = True
        self._detail_flow = flow
        self._detail_tab = "response"
        self._focus_on_tabs = False

        self.query_one("#flow-table").add_class("hidden")
        self.query_one("#filter-bar").remove_class("visible")

        # Header: summary line
        method = flow["method"]
        status = flow["status_code"]
        url = self._flow_url(flow)
        dur = _fmt_dur(flow.get("duration_ms"))
        s_color = STATUS_COLORS.get(status // 100, "white")
        m_color = METHOD_COLORS.get(method, "white")
        header = self.query_one("#detail-header", Static)
        header.update(
            f" [bold {m_color}]{method}[/bold {m_color}] "
            f"[{s_color}]{status}[/{s_color}] {url}  [dim]{dur}[/dim]"
        )
        header.add_class("visible")

        # Tabs + content
        self.query_one("#detail-tabs").add_class("visible")
        log = self.query_one("#detail-log", RichLog)
        log.add_class("visible")
        log.focus()

        self._render_tab()
        self._update_status()

    def _exit_detail(self) -> None:
        self._in_detail = False
        self._detail_flow = None

        self.query_one("#detail-header").remove_class("visible")
        self.query_one("#detail-tabs").remove_class("visible")
        self.query_one("#cmd-bar").remove_class("visible")
        log = self.query_one("#detail-log", RichLog)
        log.remove_class("visible")
        log.clear()

        self.query_one("#flow-table").remove_class("hidden")
        self.query_one("#flow-table", DataTable).focus()
        self._update_status()

    def _render_tab(self) -> None:
        flow = self._detail_flow
        if not flow:
            return

        # Update tab bar
        tabs = self.query_one("#detail-tabs", Static)
        tab_names = {"overview": "1 Overview", "request": "2 Request", "response": "3 Response"}
        parts = []
        for key, label in tab_names.items():
            if key == self._detail_tab:
                if self._focus_on_tabs:
                    parts.append(f"[bold reverse] ▸ {label} [/bold reverse]")
                else:
                    parts.append(f"[bold underline] {label} [/bold underline]")
            else:
                parts.append(f"[dim] {label} [/dim]")
        hint = "←→ Switch  ⏎ Enter" if self._focus_on_tabs else "c Copy  :c cURL"
        tabs.update("  ".join(parts) + f"  [dim]{hint}[/dim]")

        # Render content
        log = self.query_one("#detail-log", RichLog)
        log.clear()

        if self._detail_tab == "overview":
            self._render_overview(log, flow)
        elif self._detail_tab == "request":
            self._render_request(log, flow)
        elif self._detail_tab == "response":
            self._render_response(log, flow)

        # Scroll to top
        log.scroll_home(animate=False)

    def _render_overview(self, log: RichLog, flow: dict) -> None:
        method = flow["method"]
        status = flow["status_code"]
        url = self._flow_url(flow)
        dur = _fmt_dur(flow.get("duration_ms"))
        s_color = STATUS_COLORS.get(status // 100, "white")
        m_color = METHOD_COLORS.get(method, "white")

        # Parse headers for key info
        req_h = json.loads(flow["request_headers"]) if isinstance(
            flow.get("request_headers"), str) else (flow.get("request_headers") or {})
        resp_h = json.loads(flow["response_headers"]) if isinstance(
            flow.get("response_headers"), str) else (flow.get("response_headers") or {})

        # General
        general = Table(show_header=False, box=None, padding=(0, 1, 0, 0), expand=True,
                        title="[bold]General[/bold]", title_style="", title_justify="left")
        general.add_column("Key", style="dim", no_wrap=True, width=20)
        general.add_column("Value", ratio=1)
        general.add_row("Method", Text(method, style=f"bold {m_color}"))
        general.add_row("Status", Text(str(status), style=s_color))
        general.add_row("URL", url)
        general.add_row("Duration", dur)
        general.add_row("Host", flow["host"])
        if flow.get("port") and flow["port"] not in (80, 443):
            general.add_row("Port", str(flow["port"]))
        log.write(general)
        log.write("")

        # Request summary
        req_table = Table(show_header=False, box=None, padding=(0, 1, 0, 0), expand=True,
                          title="[bold blue]Request[/bold blue]", title_style="", title_justify="left")
        req_table.add_column("Key", style="dim", no_wrap=True, width=20)
        req_table.add_column("Value", ratio=1)
        req_ct = flow.get("request_content_type", "")
        req_table.add_row("Content-Type", req_ct or "-")
        req_table.add_row("Body Size", _fmt_size(flow.get("request_body")))
        # Extract key headers
        auth = req_h.get("authorization") or req_h.get("Authorization", "")
        if auth:
            display = auth[:60] + "..." if len(auth) > 60 else auth
            req_table.add_row("Authorization", display)
        user_agent = req_h.get("user-agent") or req_h.get("User-Agent", "")
        if user_agent:
            display = user_agent[:80] + "..." if len(user_agent) > 80 else user_agent
            req_table.add_row("User-Agent", display)
        cookie = req_h.get("cookie") or req_h.get("Cookie", "")
        if cookie:
            req_table.add_row("Cookie", f"{len(cookie)} chars")
        log.write(req_table)

        # Request body preview
        if flow.get("request_body"):
            body = _body_text(flow["request_body"], flow.get("request_content_type"))
            preview = body[:300] + "..." if len(body) > 300 else body
            log.write(f"  [dim]{preview}[/dim]")
        log.write("")

        # Response summary
        resp_table = Table(show_header=False, box=None, padding=(0, 1, 0, 0), expand=True,
                           title=f"[bold {s_color}]Response[/bold {s_color}]",
                           title_style="", title_justify="left")
        resp_table.add_column("Key", style="dim", no_wrap=True, width=20)
        resp_table.add_column("Value", ratio=1)
        resp_ct = flow.get("response_content_type", "")
        resp_table.add_row("Content-Type", resp_ct or "-")
        resp_table.add_row("Body Size", _fmt_size(flow.get("response_body")))
        cache = resp_h.get("cache-control") or resp_h.get("Cache-Control", "")
        if cache:
            resp_table.add_row("Cache-Control", cache)
        set_cookie = resp_h.get("set-cookie") or resp_h.get("Set-Cookie", "")
        if set_cookie:
            resp_table.add_row("Set-Cookie", f"{len(set_cookie)} chars")
        log.write(resp_table)

        # Response body preview
        if flow.get("response_body"):
            body = _body_text(flow["response_body"], flow.get("response_content_type"))
            preview = body[:300] + "..." if len(body) > 300 else body
            log.write(f"  [dim]{preview}[/dim]")

    def _render_headers_table(self, log: RichLog, raw: str | dict | None,
                              title: str, style: str = "blue") -> None:
        if not raw:
            return
        headers = json.loads(raw) if isinstance(raw, str) else raw
        table = Table(show_header=False, box=None, padding=(0, 1, 0, 0), expand=True)
        table.add_column("Key", style="dim", no_wrap=True, max_width=35)
        table.add_column("Value", ratio=1)
        for k, v in headers.items():
            table.add_row(k, str(v))
        log.write(f"[bold {style}]{title}[/bold {style}]")
        log.write(table)

    def _render_request(self, log: RichLog, flow: dict) -> None:
        url = self._flow_url(flow)
        log.write(f"[bold]{flow['method']}[/bold] {url}")
        log.write("")

        self._render_headers_table(log, flow.get("request_headers"), "Headers", "blue")

        if flow.get("request_body"):
            ct = flow.get("request_content_type", "")
            log.write("")
            log.write(f"[bold blue]Body[/bold blue]  [dim]{ct}  {_fmt_size(flow.get('request_body'))}[/dim]")
            log.write("")
            _write_body(log, flow["request_body"], flow.get("request_content_type"))
        else:
            log.write("")
            log.write("[dim]No request body[/dim]")

    def _render_response(self, log: RichLog, flow: dict) -> None:
        status = flow["status_code"]
        dur = _fmt_dur(flow.get("duration_ms"))
        s_color = STATUS_COLORS.get(status // 100, "white")

        log.write(f"[{s_color}]{status}[/{s_color}]  {dur}  {_fmt_size(flow.get('response_body'))}")
        log.write("")

        self._render_headers_table(log, flow.get("response_headers"), "Headers", s_color)

        if flow.get("response_body"):
            ct = flow.get("response_content_type", "")
            log.write("")
            log.write(f"[bold {s_color}]Body[/bold {s_color}]  [dim]{ct}[/dim]")
            log.write("")
            _write_body(log, flow["response_body"], flow.get("response_content_type"))
        else:
            log.write("")
            log.write("[dim]No response body[/dim]")

    # ── Tab switching ──

    def action_tab_overview(self) -> None:
        if self._in_detail:
            self._detail_tab = "overview"
            self._render_tab()

    def action_tab_request(self) -> None:
        if self._in_detail:
            self._detail_tab = "request"
            self._render_tab()

    def action_tab_response(self) -> None:
        if self._in_detail:
            self._detail_tab = "response"
            self._render_tab()

    _TAB_ORDER = ["overview", "request", "response"]

    def action_tab_prev(self) -> None:
        if not self._in_detail:
            return
        idx = self._TAB_ORDER.index(self._detail_tab)
        self._detail_tab = self._TAB_ORDER[(idx - 1) % len(self._TAB_ORDER)]
        self._render_tab()

    def action_tab_next(self) -> None:
        if not self._in_detail:
            return
        idx = self._TAB_ORDER.index(self._detail_tab)
        self._detail_tab = self._TAB_ORDER[(idx + 1) % len(self._TAB_ORDER)]
        self._render_tab()

    # ── Copy ──

    def action_copy_tab(self) -> None:
        flow = self._detail_flow
        if not flow or not self._in_detail:
            return

        if self._detail_tab == "overview":
            text = f"{flow['method']} {self._flow_url(flow)}"
            self.copy_to_clipboard(text)
            self.notify("Copied URL")
        elif self._detail_tab == "request":
            body = _body_text(flow.get("request_body"), flow.get("request_content_type"))
            if body:
                self.copy_to_clipboard(body)
                self.notify("Copied request body")
            else:
                # Fallback: copy URL
                self.copy_to_clipboard(f"{flow['method']} {self._flow_url(flow)}")
                self.notify("Copied URL (no request body)")
        elif self._detail_tab == "response":
            body = _body_text(flow.get("response_body"), flow.get("response_content_type"))
            if body:
                self.copy_to_clipboard(body)
                self.notify("Copied response body")
            else:
                self.notify("No response body", severity="warning")

    # ── Command bar ──

    def action_open_cmd(self) -> None:
        if not self._in_detail:
            return
        cmd_bar = self.query_one("#cmd-bar", Input)
        cmd_bar.add_class("visible")
        cmd_bar.value = ""
        cmd_bar.focus()

    def action_go_back(self) -> None:
        cmd_bar = self.query_one("#cmd-bar")
        if cmd_bar.has_class("visible"):
            cmd_bar.remove_class("visible")
            self.query_one("#detail-log", RichLog).focus()
            self._focus_on_tabs = False
            return
        if self._in_detail:
            if not self._focus_on_tabs:
                # Content → tab bar
                self._focus_on_tabs = True
                self._render_tab()  # re-render to show tab bar highlight
            else:
                # Tab bar → exit detail
                self._exit_detail()
        else:
            bar = self.query_one("#filter-bar")
            if bar.has_class("visible"):
                bar.remove_class("visible")
                self.query_one("#flow-table", DataTable).focus()

    # ── Network info ──

    @staticmethod
    def _get_local_ip() -> str:
        try:
            out = subprocess.check_output(
                ["ipconfig", "getifaddr", "en0"], stderr=subprocess.DEVNULL, timeout=2
            ).decode().strip()
            return out
        except Exception:
            return ""

    # ── Status ──

    def _update_status(self) -> None:
        bar = self.query_one("#status-bar", Static)
        if self._proxy_exited:
            proxy_text = "[red]● stopped[/red]"
        elif self.proxy_proc:
            proxy_text = f"[green]● :{self.port}[/green]"
        else:
            proxy_text = "[dim]no proxy[/dim]"
        total = len(self._all_flows)
        shown = len(self._flow_ids)
        filter_active = any([self._filter_domain, self._filter_path,
                             self._filter_method, self._filter_status])
        count_text = f"{shown}/{total}" if filter_active else str(total)
        ip = f"  [dim bold]{self._local_ip}[/dim bold]" if self._local_ip else ""
        sort_icon = "↓" if self._sort_desc else "↑"
        if self._in_detail:
            if self._focus_on_tabs:
                bar.update(f" {proxy_text}  [dim]←→ Tab  ⏎ Enter  esc Exit[/dim]{ip}")
            else:
                bar.update(f" {proxy_text}  [dim]1/2/3 Tab  c Copy  :c cURL  esc Back  q Quit[/dim]{ip}")
        else:
            bar.update(f" {proxy_text}  {count_text} flows {sort_icon}  [dim]⏎ Detail  f Filter  s Sort  x Clear  q Quit[/dim]{ip}")

    def watch_flow_count(self, count: int) -> None:
        if not self._in_detail:
            self._update_status()

    def action_quit(self) -> None:
        if self.proxy_proc:
            self.proxy_proc.terminate()
            try:
                self.proxy_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proxy_proc.kill()
        self.exit()


def run_tui(port: int, mode: str | None, domain: str | None, db_path: str) -> None:
    """Launch mitmdump as background process + textual TUI."""
    init_db(db_path)

    addon_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "addon.py"
    )
    venv_bin = os.path.join(os.path.dirname(sys.executable), "mitmdump")
    bin_path = venv_bin if os.path.exists(venv_bin) else shutil.which("mitmdump")
    if not bin_path:
        print("mitmdump not found. Install: uv add mitmproxy", file=sys.stderr)
        sys.exit(1)

    dump_cmd = [bin_path, "-s", addon_path, "-p", str(port), "-q"]
    if mode:
        dump_cmd.extend(["--mode", mode])

    proc = subprocess.Popen(dump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    try:
        app = TroxyApp(db_path=db_path, port=port, domain=domain, proxy_proc=proc)
        app.run()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
