"""DetailScreen — flow detail view (Request/Response tab view)."""

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static, Tree

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
    parse_body_as_json,
    parse_headers,
    populate_json_tree,
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
        request_tree = Tree("body", id="request-tree", classes="json-tree hidden")
        request_tree.show_root = False
        request_tree.guide_depth = 3
        yield VerticalScroll(
            Static(id="request-pane", classes="pane"),
            request_tree,
            id="request-container",
            classes="hidden",
        )
        response_tree = Tree("body", id="response-tree", classes="json-tree hidden")
        response_tree.show_root = False
        response_tree.guide_depth = 3
        yield VerticalScroll(
            Static(id="response-pane", classes="pane"),
            response_tree,
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
        self._render_pane(
            pane_id="request-pane",
            tree_id="request-tree",
            headers_raw=f["request_headers"],
            body=f.get("request_body"),
            content_type=f.get("request_content_type"),
        )

    def _render_response(self) -> None:
        f = self._flow
        self._render_pane(
            pane_id="response-pane",
            tree_id="response-tree",
            headers_raw=f["response_headers"],
            body=f.get("response_body"),
            content_type=f.get("response_content_type"),
        )

    def _render_pane(
        self,
        *,
        pane_id: str,
        tree_id: str,
        headers_raw,
        body,
        content_type,
    ) -> None:
        is_request = pane_id == "request-pane"
        label = "요청" if is_request else "응답"
        if is_request:
            accent = method_color(self._flow["method"])
        else:
            accent = status_color(int(self._flow["status_code"]))

        header_text = render_headers(parse_headers(headers_raw))
        headers_panel = Panel(
            header_text,
            title=f"{label} · 헤더",
            title_align="left",
            border_style=accent,
            padding=(0, 1),
        )

        json_data = parse_body_as_json(body, content_type)
        tree = self.query_one(f"#{tree_id}", Tree)
        if json_data is not None:
            tree.remove_class("hidden")
            populate_json_tree(tree, json_data)
            body_panel = Panel(
                Text("(body — Tree 아래에서 ⏎ 펼치기/접기)", style="dim italic"),
                title=f"{label} · body (JSON)",
                title_align="left",
                border_style=accent,
                padding=(0, 1),
            )
            self.query_one(f"#{pane_id}", Static).update(Group(headers_panel, body_panel))
            return
        tree.add_class("hidden")
        body_render = body_renderable(body, content_type)
        body_content = body_render if body_render is not None else Text("(body 없음)", style="dim italic")
        body_panel = Panel(
            body_content,
            title=f"{label} · body",
            title_align="left",
            border_style=accent,
            padding=(0, 1),
        )
        self.query_one(f"#{pane_id}", Static).update(Group(headers_panel, body_panel))

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
            label = "요청" if name == "request" else "응답"
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
