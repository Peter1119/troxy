"""ListScreen — flow list main screen."""

from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import DataTable, Static

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.mock import list_mock_rules
from troxy.core.query import delete_all_flows, get_flow, list_flows, list_flows_filtered
from troxy.tui import copy
from troxy.tui.inline_filter import InlineFilter
from troxy.tui.list_helpers import add_flow_row, time_header_label, update_cursor_marker
from troxy.tui.network import get_local_ip
from troxy.tui.styles import LIST_SCREEN_CSS
from troxy.tui.widgets import ConfirmDialog, Toast


class ListScreen(Screen):
    DEFAULT_CSS = LIST_SCREEN_CSS

    BINDINGS = [
        ("enter", "view_detail", "detail"),
        ("f", "show_filter", "filter"),
        ("escape", "clear_filter", "clear filter"),
        ("m", "mock_flow", "mock"),
        ("shift+m", "mock_list", "mocks"),
        ("M", "mock_list", "mocks"),
        ("i", "intercept_placeholder", "intercept"),
        ("p", "toggle_pause", "pause"),
        ("s", "toggle_sort", "sort"),
        ("x", "clear_all", "clear"),
        ("q", "app.quit", "quit"),
    ]

    def __init__(
        self,
        db_path: str | None = None,
        *,
        port: int = 8080,
        mcp_registered: bool = False,
        proxy_running_fn: Callable[[], bool] | None = None,
        proxy_pause_fn: Callable[[], None] | None = None,
        proxy_resume_fn: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._db_path = db_path or default_db_path()
        self._last_id = 0
        self._flow_count = 0
        self._local_ip = get_local_ip()
        self._active_filter = ""
        self._newest_first = False
        self._port = port
        self._mcp_registered = mcp_registered
        self._proxy_running_fn = proxy_running_fn or (lambda: True)
        self._proxy_pause_fn = proxy_pause_fn
        self._proxy_resume_fn = proxy_resume_fn

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield InlineFilter(id="inline-filter")
        table = DataTable(id="flow-table", zebra_stripes=True)
        table.cursor_type = "row"
        table.add_column(Text("", justify="center"), width=2, key="marker")
        table.add_column(Text("#", justify="right"), key="id")
        table.add_column(time_header_label(self._newest_first), key="time")
        table.add_column("METHOD", key="method")
        table.add_column("HOST", key="host")
        table.add_column("PATH", key="path")
        table.add_column(Text("STATUS", justify="right"), key="status")
        yield table
        yield Static(id="filter-status")
        yield Static(copy.LIST_HINT, id="hint-bar")
        yield Static(id="proxy-bar")
        yield Static(id="info-bar")
        yield ConfirmDialog(id="confirm")
        yield Toast(id="toast")

    def on_mount(self) -> None:
        init_db(self._db_path)
        self._refresh_table_with_filter()
        self._refresh_proxy_bar()
        self._refresh_status_bar()
        self.set_interval(0.5, self._poll_new_flows)
        self.set_interval(30, self._refresh_ip)
        self.set_interval(5, self._refresh_status_bar)
        # Pin focus to DataTable so Screen bindings don't leak into InlineFilter Input.
        self.query_one("#flow-table", DataTable).focus()

    def _poll_new_flows(self) -> None:
        if self._active_filter:
            return
        conn = get_connection(self._db_path)
        rows = conn.execute(
            "SELECT * FROM flows WHERE id > ? ORDER BY id ASC",
            (self._last_id,),
        ).fetchall()
        conn.close()
        if not rows:
            return
        if self._newest_first:
            return self._refresh_table_with_filter()
        table = self.query_one("#flow-table", DataTable)
        for row in rows:
            flow = dict(row)
            add_flow_row(table, flow)
            self._last_id = flow["id"]
            self._flow_count += 1
        self._update_header()

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        table = self.query_one("#flow-table", DataTable)
        update_cursor_marker(table)

    def _update_header(self) -> None:
        header = self.query_one("#header", Static)
        header.update(copy.header_text(self._db_path, self._flow_count))

    def _refresh_ip(self) -> None:
        self._local_ip = get_local_ip()
        self._refresh_proxy_bar()

    def _refresh_proxy_bar(self) -> None:
        self.query_one("#proxy-bar", Static).update(
            copy.proxy_info_line(self._local_ip, self._port)
        )

    def _refresh_status_bar(self) -> None:
        try:
            enabled_mocks = list_mock_rules(self._db_path, enabled_only=True)
        except Exception:
            enabled_mocks = []
        self.query_one("#info-bar", Static).update(
            copy.status_summary_line(
                recording=self._proxy_running_fn(),
                flow_count=self._flow_count,
                mock_count=len(enabled_mocks),
                mcp_enabled=self._mcp_registered,
            )
        )

    def _get_selected_flow_id(self) -> int | None:
        table = self.query_one("#flow-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(
                Coordinate(table.cursor_row, 0)
            )
        except Exception:
            return None
        if row_key.value is None:
            return None
        try:
            return int(row_key.value)
        except (TypeError, ValueError):
            return None

    def action_view_detail(self) -> None:
        from troxy.tui.detail_screen import DetailScreen

        flow_id = self._get_selected_flow_id()
        if flow_id is not None:
            self.app.push_screen(DetailScreen(self._db_path, flow_id))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        from troxy.tui.detail_screen import DetailScreen

        if event.row_key.value is None:
            return
        flow_id = int(event.row_key.value)
        self.app.push_screen(DetailScreen(self._db_path, flow_id))

    def action_show_filter(self) -> None:
        self.query_one("#inline-filter", InlineFilter).show()

    def action_clear_filter(self) -> None:
        # Esc hides the bar only; filter state clears via empty-submit or ``x``.
        inline = self.query_one("#inline-filter", InlineFilter)
        if inline.has_class("visible"):
            inline.hide()
            self.query_one("#flow-table", DataTable).focus()

    def action_mock_flow(self) -> None:
        from troxy.tui.mock_dialog import MockDialog

        flow_id = self._get_selected_flow_id()
        if flow_id is None:
            return
        flow = get_flow(self._db_path, flow_id)
        if flow:
            self.app.push_screen(MockDialog(self._db_path, flow))

    def action_mock_list(self) -> None:
        from troxy.tui.mock_list import MockListScreen

        self.app.push_screen(MockListScreen(self._db_path))

    def on_mock_dialog_saved(self, event) -> None:
        self.query_one("#toast", Toast).show_message(
            copy.toast_mock_saved(event.name)
        )

    def on_mock_dialog_error(self, event) -> None:
        self.query_one("#toast", Toast).show_message(f"\u2715 {event.message}")

    def action_intercept_placeholder(self) -> None:
        self.query_one("#toast", Toast).show_message(
            copy.toast_intercept_placeholder()
        )

    def action_toggle_pause(self) -> None:
        # Refresh status bar immediately — the 5 s poll would otherwise lag the keypress.
        if self._proxy_running_fn():
            if self._proxy_pause_fn is not None:
                self._proxy_pause_fn()
        else:
            if self._proxy_resume_fn is not None:
                self._proxy_resume_fn()
        self._refresh_status_bar()

    def action_toggle_sort(self) -> None:
        self._newest_first = not self._newest_first
        table = self.query_one("#flow-table", DataTable)
        table.columns["time"].label = time_header_label(self._newest_first)
        self._refresh_table_with_filter()

    def action_clear_all(self) -> None:
        self.query_one("#confirm", ConfirmDialog).show(
            copy.confirm_clear(self._flow_count), "clear"
        )

    def on_inline_filter_submitted(
        self, event: InlineFilter.Submitted
    ) -> None:
        self._active_filter = event.filter_text
        self._refresh_table_with_filter()
        self._refresh_filter_status()
        self.query_one("#inline-filter", InlineFilter).hide()
        self.query_one("#flow-table", DataTable).focus()

    def _refresh_filter_status(self) -> None:
        status = self.query_one("#filter-status", Static)
        if self._active_filter:
            status.update(copy.filter_status_text(self._active_filter))
            status.add_class("active")
        else:
            status.update("")
            status.remove_class("active")

    def on_confirm_dialog_confirmed(self, event: ConfirmDialog.Confirmed) -> None:
        if event.action == "clear":
            count = delete_all_flows(self._db_path)
            self._clear_table()
            self.query_one("#toast", Toast).show_message(copy.toast_cleared(count))

    def on_confirm_dialog_cancelled(self, event: ConfirmDialog.Cancelled) -> None:
        pass

    def _refresh_table_with_filter(self) -> None:
        table = self.query_one("#flow-table", DataTable)
        table.clear()
        if self._active_filter:
            flows = list_flows_filtered(self._db_path, self._active_filter)
        else:
            flows = list_flows(self._db_path, limit=500)
        if not self._newest_first:
            flows.reverse()
        self._last_id = 0
        self._flow_count = 0
        for flow in flows:
            add_flow_row(table, flow)
            self._last_id = max(self._last_id, flow["id"])
            self._flow_count += 1
        self._update_header()

    def _clear_table(self) -> None:
        # ``x`` clear-all resets filter values + status bar in lockstep with the table.
        table = self.query_one("#flow-table", DataTable)
        table.clear()
        self.query_one("#inline-filter", InlineFilter).clear_values()
        self._active_filter = ""
        self._refresh_filter_status()
        self._last_id = 0
        self._flow_count = 0
        self._update_header()
