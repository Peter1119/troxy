"""DetailScreen — flow detail view (Request/Response tab view)."""

from rich.console import Group
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from troxy.core.export import export_curl, export_httpie
from troxy.core.query import get_flow
from troxy.tui import copy
from troxy.tui.detail_helpers import (
    append_field,
    body_renderable,
    build_request_text,
    build_response_text,
    format_size,
    get_url,
    parse_headers,
    preview_query,
    render_headers,
)
from troxy.tui.styles import DETAIL_SCREEN_CSS
from troxy.tui.theme import method_color, status_color
from troxy.tui.widgets import CopyModal, Toast, copy_to_clipboard


class DetailScreen(Screen):
    BINDINGS = [
        ("escape", "go_back", "back"),
        ("left", "show_request", "request"),
        ("right", "show_response", "response"),
        ("tab", "switch_tab", "switch"),
        ("shift+tab", "switch_tab", "switch"),
        ("y", "copy_modal", "copy"),
        ("Y", "copy_focused", "quick copy"),
        ("u", "copy_url", "copy url"),
        ("m", "mock_flow", "mock"),
        ("c", "copy_curl", "curl"),
        ("r", "replay", "replay"),
    ]

    DEFAULT_CSS = DETAIL_SCREEN_CSS

    def __init__(self, db_path: str, flow_id: int) -> None:
        super().__init__()
        self._db_path = db_path
        self._flow_id = flow_id
        self._flow: dict | None = None
        self._active_tab = "response"

    def compose(self) -> ComposeResult:
        yield Static(id="url-bar")
        yield Static(id="tab-bar")
        yield VerticalScroll(
            Static(id="request-pane", classes="pane"),
            id="request-container",
            classes="hidden",
        )
        yield VerticalScroll(
            Static(id="response-pane", classes="pane"),
            id="response-container",
        )
        yield Static(copy.DETAIL_HINT, id="hint-bar")
        yield CopyModal(id="copy-modal")
        yield Toast(id="toast")

    def on_mount(self) -> None:
        self._flow = get_flow(self._db_path, self._flow_id)
        if not self._flow:
            self.app.pop_screen()
            return
        self._render_url()
        self._render_request()
        self._render_response()
        self._render_tab_bar()
        self._update_tab_visibility()

    def _render_url(self) -> None:
        f = self._flow
        method = f["method"]
        status = int(f["status_code"])
        t = Text()
        t.append(f"Flow #{f['id']}", style="bold")
        t.append("  ")
        t.append(method, style=f"bold {method_color(method)}")
        t.append("  ")
        t.append(str(status), style=f"bold {status_color(status)}")
        t.append(f"  {f['duration_ms']:.0f}ms", style="dim")
        t.append("\n")
        append_field(t, "Host ", f"{f['scheme']}://{f['host']}")
        t.append("\n")
        append_field(t, "Path ", f["path"] or "/")
        query = f.get("query") or ""
        if query:
            t.append("\n")
            append_field(t, "Query", preview_query(query))
        self.query_one("#url-bar", Static).update(t)

    def _render_request(self) -> None:
        f = self._flow
        header_text = render_headers(parse_headers(f["request_headers"]))
        body = body_renderable(f.get("request_body"), f.get("request_content_type"))
        if body is None:
            group = Group(header_text, Text("\n(body 없음)", style="dim italic"))
        else:
            group = Group(header_text, Text(""), body)
        self.query_one("#request-pane", Static).update(group)

    def _render_response(self) -> None:
        f = self._flow
        header_text = render_headers(parse_headers(f["response_headers"]))
        body = body_renderable(f.get("response_body"), f.get("response_content_type"))
        if body is None:
            group = Group(header_text)
        else:
            group = Group(header_text, Text(""), body)
        self.query_one("#response-pane", Static).update(group)

    def _render_tab_bar(self) -> None:
        """Render `[ Request ]   ( Response )` with brackets marking the active tab.

        Brackets + parens make the active tab visible even in monochrome terminals;
        color (accent reverse vs dim) reinforces for color terminals.
        """
        f = self._flow
        status = int(f["status_code"])
        t = Text()
        for i, name in enumerate(("request", "response")):
            if i > 0:
                t.append("   ")
            label = "Request" if name == "request" else "Response"
            if self._active_tab == name:
                t.append(f"[ {label} ]", style="bold reverse")
            else:
                t.append(f"( {label} )", style="dim")
        # Right-aligned status/size for Response context.
        if self._active_tab == "response":
            t.append("   ")
            t.append(str(status), style=f"bold {status_color(status)}")
            t.append(f"  ·  {format_size(f.get('response_body'))}", style="dim")
        self.query_one("#tab-bar", Static).update(t)

    def _update_tab_visibility(self) -> None:
        req = self.query_one("#request-container", VerticalScroll)
        res = self.query_one("#response-container", VerticalScroll)
        req.set_class(self._active_tab != "request", "hidden")
        res.set_class(self._active_tab != "response", "hidden")

    def action_show_request(self) -> None:
        self._active_tab = "request"
        self._render_tab_bar()
        self._update_tab_visibility()

    def action_show_response(self) -> None:
        self._active_tab = "response"
        self._render_tab_bar()
        self._update_tab_visibility()

    def action_switch_tab(self) -> None:
        self._active_tab = "request" if self._active_tab == "response" else "response"
        self._render_tab_bar()
        self._update_tab_visibility()

    def key_escape(self) -> None:
        # Textual's Screen._key_escape routes escape to clear_selection() —
        # it runs before our Screen BINDINGS lookup, so the "escape → go_back"
        # binding never fires. Declaring a public key_escape override steals
        # escape back into our action path.
        self.action_go_back()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_copy_modal(self) -> None:
        self.query_one("#copy-modal", CopyModal).show()

    def action_copy_focused(self) -> None:
        if self._active_tab == "request":
            self._copy_and_toast(build_request_text(self._flow), "Request")
        else:
            self._copy_and_toast(build_response_text(self._flow), "Response")

    def action_copy_url(self) -> None:
        self._copy_and_toast(get_url(self._flow), "URL")

    def action_copy_curl(self) -> None:
        if not self._flow:
            return
        self._copy_and_toast(export_curl(self._flow), "curl")

    def action_mock_flow(self) -> None:
        if not self._flow:
            return
        from troxy.tui.mock_dialog import MockDialog

        self.app.push_screen(MockDialog(self._db_path, self._flow))

    def action_replay(self) -> None:
        pass

    def on_mock_dialog_saved(self, event) -> None:
        self.query_one("#toast", Toast).show_message(
            copy.toast_mock_saved(event.name)
        )

    def on_mock_dialog_error(self, event) -> None:
        self.query_one("#toast", Toast).show_message(f"\u2715 {event.message}")

    def on_copy_modal_selected(self, event: CopyModal.Selected) -> None:
        if not self._flow:
            return
        option = event.option
        if option == "url":
            text, label = get_url(self._flow), "URL"
        elif option == "request":
            text, label = build_request_text(self._flow), "Request"
        elif option == "response":
            text, label = build_response_text(self._flow), "Response"
        elif option == "response_body":
            text, label = self._flow.get("response_body") or "", "Response body"
        elif option == "curl":
            text, label = export_curl(self._flow), "curl"
        elif option == "httpie":
            text, label = export_httpie(self._flow), "HTTPie"
        else:
            return
        self._copy_and_toast(text, label)

    def on_copy_modal_cancelled(self, event: CopyModal.Cancelled) -> None:
        pass

    def _copy_and_toast(self, text: str, label: str) -> None:
        copy_to_clipboard(text)
        self.query_one("#toast", Toast).show_message(
            copy.toast_copied(label, len(text.encode("utf-8", errors="replace")))
        )
