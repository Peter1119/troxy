"""MockListScreen — list / toggle / delete / edit mock rules."""

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Static

from troxy.core.mock import list_mock_rules, remove_mock_rule, toggle_mock_rule
from troxy.tui import copy
from troxy.tui.theme import (
    MOCK_DISABLED_ICON,
    MOCK_ENABLED_ICON,
    method_color,
    status_color,
)
from troxy.tui.widgets import ConfirmDialog, Toast


_DELETE_ACTION_PREFIX = "mock-delete-"


class MockListScreen(Screen):
    """List / manage mock rules registered in the DB.

    Navigation:
      - Space — toggle enabled/disabled on the selected row
      - d     — delete the selected row (confirm required)
      - Enter — edit the selected row (opens MockDialog)
      - Esc   — back to the previous screen
    """

    BINDINGS = [
        ("escape", "go_back", "back"),
        ("space", "toggle_mock", "toggle"),
        ("d", "delete_mock", "delete"),
    ]

    DEFAULT_CSS = """
    #mock-header {
        height: 1;
        background: $panel;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    #mock-table {
        height: 1fr;
        background: $surface;
    }
    #mock-table > .datatable--header {
        background: $panel;
        color: $text;
        text-style: bold;
    }
    #mock-table > .datatable--cursor {
        background: $accent 35%;
        color: $text;
        text-style: bold;
    }
    #hint-bar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path

    # ---------- composition / lifecycle ----------

    def compose(self) -> ComposeResult:
        yield Static("\u2500\u2500 Mocks \u2500\u2500", id="mock-header")
        table = DataTable(id="mock-table", zebra_stripes=True)
        table.cursor_type = "row"
        table.add_columns("ON", "#", "NAME", "MATCH", "STATUS", "HIT")
        yield table
        yield Static(copy.MOCK_LIST_HINT, id="hint-bar")
        yield ConfirmDialog(id="confirm")
        yield Toast(id="toast")

    def on_mount(self) -> None:
        self._refresh()

    # ---------- rendering ----------

    def _refresh(self) -> None:
        table = self.query_one("#mock-table", DataTable)
        table.clear()
        rules = list_mock_rules(self._db_path)
        for rule in rules:
            enabled = bool(rule["enabled"])
            on_cell = Text(
                MOCK_ENABLED_ICON if enabled else MOCK_DISABLED_ICON,
                style="bold green" if enabled else "dim",
            )
            method = rule.get("method") or "*"
            match_str = self._format_match(rule)
            match_cell = self._render_match(method, match_str)
            status_code = int(rule["status_code"])
            status_cell = Text(str(status_code), style=f"bold {status_color(status_code)}")
            hit = int(rule.get("hit_count", 0))
            hit_cell = Text(str(hit), style="bold" if hit > 0 else "dim")
            table.add_row(
                on_cell,
                str(rule["id"]),
                rule.get("name") or f"rule-{rule['id']}",
                match_cell,
                status_cell,
                hit_cell,
                key=str(rule["id"]),
            )

    @staticmethod
    def _render_match(method: str, match_str: str) -> Text:
        """Color the method prefix inside the MATCH cell."""
        text = Text()
        if match_str.startswith(method + " "):
            text.append(method, style=f"bold {method_color(method)}")
            text.append(match_str[len(method):])
        else:
            text.append(match_str)
        return text

    @staticmethod
    def _format_match(rule: dict) -> str:
        method = rule.get("method") or "*"
        host = rule.get("domain") or "*"
        path = rule.get("path_pattern") or "/*"
        match = f"{method} {host}{path}"
        if len(match) > 40:
            match = match[:39] + "\u2026"
        return match

    def _selected_rule_id(self) -> int | None:
        table = self.query_one("#mock-table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        try:
            row = table.get_row_at(table.cursor_row)
        except Exception:
            return None
        try:
            return int(row[1]) if row else None
        except (TypeError, ValueError):
            return None

    def _get_rule(self, rule_id: int) -> dict | None:
        for rule in list_mock_rules(self._db_path):
            if rule["id"] == rule_id:
                return rule
        return None

    # ---------- actions ----------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_toggle_mock(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            return
        rule = self._get_rule(rule_id)
        if not rule:
            return
        toggle_mock_rule(self._db_path, rule_id, enabled=not rule["enabled"])
        self._refresh()

    def action_delete_mock(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            return
        rule = self._get_rule(rule_id)
        if not rule:
            return
        name = rule.get("name") or f"rule-{rule_id}"
        self.query_one("#confirm", ConfirmDialog).show(
            copy.confirm_mock_delete(name),
            f"{_DELETE_ACTION_PREFIX}{rule_id}",
        )

    def action_edit_mock(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            return
        rule = self._get_rule(rule_id)
        if not rule:
            return
        # Build a synthetic flow so MockDialog can prefill from the rule.
        flow = {
            "id": 0,
            "method": rule.get("method") or "GET",
            "host": rule.get("domain") or "*",
            "path": rule.get("path_pattern") or "/*",
            "scheme": "https",
            "status_code": rule["status_code"],
            "response_headers": rule.get("response_headers") or "{}",
            "response_body": rule.get("response_body") or "",
        }
        from troxy.tui.mock_dialog import MockDialog

        self.app.push_screen(MockDialog(self._db_path, flow, rule=rule))

    # ---------- messages ----------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row opens MockDialog in edit mode."""
        self.action_edit_mock()

    def on_confirm_dialog_confirmed(self, event: ConfirmDialog.Confirmed) -> None:
        if not event.action.startswith(_DELETE_ACTION_PREFIX):
            return
        try:
            rule_id = int(event.action[len(_DELETE_ACTION_PREFIX):])
        except ValueError:
            return
        rule = self._get_rule(rule_id)
        name = (rule.get("name") if rule else None) or f"rule-{rule_id}"
        remove_mock_rule(self._db_path, rule_id)
        self._refresh()
        self.query_one("#toast", Toast).show_message(
            copy.toast_mock_deleted(name)
        )

    def on_confirm_dialog_cancelled(self, event: ConfirmDialog.Cancelled) -> None:
        pass

    def on_mock_dialog_saved(self, event) -> None:
        # After editing, refresh and notify.
        self._refresh()
        self.query_one("#toast", Toast).show_message(
            copy.toast_mock_saved(event.name)
        )

    def on_mock_dialog_error(self, event) -> None:
        self.query_one("#toast", Toast).show_message(f"\u2715 {event.message}")
