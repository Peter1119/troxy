"""MockDialog — modal to register a flow as a mock rule."""

import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Select, Static, Switch, TextArea

from troxy.core.mock import add_mock_rule, suggest_glob
from troxy.tui.external_editor import (
    EditorCancelledError, EditorIOError, EditorNotFoundError,
    open_in_editor, prettify_body, validate_json_body,
)


STATUS_OPTIONS: list[tuple[str, str]] = [
    ("200", "200"),
    ("201", "201"),
    ("204", "204"),
    ("400", "400"),
    ("401", "401"),
    ("403", "403"),
    ("404", "404"),
    ("500", "500"),
    ("502", "502"),
    ("503", "503"),
]

METHOD_OPTIONS: list[tuple[str, str]] = [
    ("GET", "GET"),
    ("POST", "POST"),
    ("PUT", "PUT"),
    ("PATCH", "PATCH"),
    ("DELETE", "DELETE"),
    ("HEAD", "HEAD"),
    ("OPTIONS", "OPTIONS"),
]


def _method_options_with(current: str) -> list[tuple[str, str]]:
    """Ensure the flow's method appears in the Select even if it's exotic
    (e.g. ``TRACE``). Preserves canonical order; appends unknowns so the
    Select.value prefill never fires InvalidValue."""
    base = list(METHOD_OPTIONS)
    if current and not any(v == current for _, v in base):
        base.append((current, current))
    return base


class MockDialog(ModalScreen):
    """Modal dialog to create (or edit) a mock rule from a flow.

    Prefills all fields from the given flow. ``suggest_glob`` proposes
    replacing dynamic path segments with ``*``; the user can toggle the
    suggestion off to keep the exact path.
    """

    class Saved(Message):
        def __init__(self, rule_id: int, name: str) -> None:
            self.rule_id = rule_id
            self.name = name
            super().__init__()

    class Error(Message):
        def __init__(self, message: str) -> None:
            self.message = message
            super().__init__()

    BINDINGS = [
        ("escape", "cancel", "cancel"),
        ("ctrl+s", "save", "save"),
        ("ctrl+e", "open_editor", "external editor"),
        ("ctrl+l", "clear_body", "clear body"),
    ]

    DEFAULT_CSS = """
    MockDialog {
        align: center middle;
        background: $background 70%;
    }
    #mock-dialog-container {
        width: 72;
        height: auto;
        max-height: 32;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    #mock-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
        border-bottom: solid $primary-darken-1;
        margin-bottom: 1;
    }
    #mock-dialog-container .field-label {
        margin-top: 1;
        color: $text-muted;
    }
    #mock-dialog-container .dialog-hint {
        margin-top: 1;
        color: $text-muted;
        text-style: italic;
    }
    #mock-body {
        height: 8;
    }
    #mock-glob-row {
        height: 3;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        db_path: str,
        flow: dict,
        rule: dict | None = None,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._flow = flow
        self._rule = rule

    # ---------- composition ----------

    def compose(self) -> ComposeResult:
        f = self._flow
        suggested = suggest_glob(f["path"])
        has_glob = suggested != f["path"]

        if self._rule:
            title = f"Edit Mock #{self._rule['id']}"
            initial_name = self._rule.get("name") or self._auto_name(f)
            initial_status = str(self._rule.get("status_code") or f["status_code"])
            raw_body = (
                self._rule.get("response_body")
                or f.get("response_body")
                or ""
            )
        else:
            title = f"Mock from Flow #{f.get('id', '?')}"
            initial_name = self._auto_name(f)
            initial_status = str(f["status_code"])
            raw_body = f.get("response_body") or ""
        initial_body = prettify_body(raw_body, f.get("response_content_type"))

        path_shown = suggested if has_glob else f["path"]

        with Vertical(id="mock-dialog-container"):
            yield Static(title, id="mock-title")
            yield Label("Name:", classes="field-label")
            yield Input(value=initial_name, id="mock-name")
            yield Label("Host:", classes="field-label")
            yield Input(value=f["host"], id="mock-host")
            yield Label("Method:", classes="field-label")
            yield Select(
                _method_options_with(f["method"]),
                value=f["method"],
                id="mock-method",
                allow_blank=False,
            )
            yield Label("Path:", classes="field-label")
            yield Input(value=path_shown, id="mock-path")
            if has_glob:
                with Horizontal(id="mock-glob-row"):
                    yield Switch(value=True, id="use-glob")
                    yield Static("  glob 제안 사용")
            yield Label("Status:", classes="field-label")
            yield Select(
                STATUS_OPTIONS,
                value=initial_status,
                id="mock-status",
                allow_blank=False,
            )
            yield Label("Body:", classes="field-label")
            yield TextArea(initial_body, id="mock-body", language="json")
            yield Static(
                "Ctrl+S \uc800\uc7a5 \u00b7 Ctrl+E \uc5d0\ub514\ud130 \u00b7 Ctrl+L body \ucd08\uae30\ud654 \u00b7 Esc \ucde8\uc18c",
                classes="dialog-hint",
            )

    # ---------- helpers ----------

    @staticmethod
    def _auto_name(flow: dict) -> str:
        """Suggest ``{last-alpha-segment}-{status}`` as a rule name."""
        path_parts = [p for p in flow["path"].strip("/").split("/") if p]
        if not path_parts:
            return f"mock-{flow['status_code']}"
        last = path_parts[-1]
        # If the last segment looks like an ID (pure digits or very long),
        # fall back to the previous segment so names stay readable.
        if last.isdigit() or len(last) > 10:
            last = path_parts[-2] if len(path_parts) > 1 else "mock"
        return f"{last}-{flow['status_code']}"

    def _serialize_headers(self, headers) -> str | None:
        """Return a JSON string for storage; accept dict or pre-serialized str."""
        if headers is None:
            return None
        if isinstance(headers, str):
            return headers
        try:
            return json.dumps(headers)
        except (TypeError, ValueError):
            return None

    # ---------- actions ----------

    def action_save(self) -> None:
        f = self._flow
        name = self.query_one("#mock-name", Input).value.strip() or None

        # Read edited URL fields (Bug #16). Empty falls back to the flow's
        # value so an accidentally-cleared Input doesn't persist a blank
        # domain/path into the DB.
        host = (
            self.query_one("#mock-host", Input).value.strip() or f["host"]
        )
        path_pattern = (
            self.query_one("#mock-path", Input).value.strip() or f["path"]
        )
        method_select = self.query_one("#mock-method", Select)
        method = (
            str(method_select.value) if method_select.value else f["method"]
        )

        select = self.query_one("#mock-status", Select)
        try:
            status_code = int(select.value)
        except (TypeError, ValueError):
            status_code = int(f["status_code"])

        body = self.query_one("#mock-body", TextArea).text
        ct = f.get("response_content_type") or ""
        if "json" in ct.lower():
            ok, err_msg = validate_json_body(body)
            if not ok:
                self.notify(err_msg, severity="error")
                return
        headers_json = self._serialize_headers(f.get("response_headers"))

        try:
            rule_id = add_mock_rule(
                self._db_path,
                domain=host,
                path_pattern=path_pattern,
                method=method,
                status_code=status_code,
                response_headers=headers_json,
                response_body=body,
                name=name,
            )
        except ValueError as exc:
            # Keep the dialog open so the user can fix the name.
            self.post_message(self.Error(str(exc)))
            return

        final_name = name or f"rule-{rule_id}"
        self.post_message(self.Saved(rule_id, final_name))
        self.app.pop_screen()

    async def action_open_editor(self) -> None:
        body = self.query_one("#mock-body", TextArea).text
        ct = self._flow.get("response_content_type")
        try:
            self.query_one("#mock-body", TextArea).load_text(
                await open_in_editor(body, ct, self.app)
            )
        except EditorNotFoundError:
            self.notify("에디터를 찾을 수 없습니다. $EDITOR 환경변수를 설정하세요.", severity="error")
        except EditorCancelledError:
            self.notify("편집이 취소되었습니다", severity="warning")
        except EditorIOError as e:
            self.notify(str(e), severity="error")

    def action_clear_body(self) -> None:
        # Ctrl+L wipes the body TextArea only (Bug #17) — readline-style
        # clear, scoped so that Host/Path Inputs are left intact.
        self.query_one("#mock-body", TextArea).text = ""

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        # Glob toggle is a path-prefill helper (Bug #16): flipping it
        # rewrites the path Input so the user can use the suggestion as a
        # starting point without losing the ability to hand-edit.
        if event.switch.id != "use-glob":
            return
        path_input = self.query_one("#mock-path", Input)
        raw_path = self._flow["path"]
        path_input.value = (
            suggest_glob(raw_path) if event.value else raw_path
        )
