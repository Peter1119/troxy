"""Reusable TUI widgets — FilterInput, ConfirmDialog, Toast, CopyModal."""

import subprocess
import sys

from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static


class FilterInput(Widget):
    """Top-docked single-line input for filter expressions."""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class Cancelled(Message):
        pass

    DEFAULT_CSS = """
    FilterInput {
        display: none;
        height: 3;
        dock: top;
    }
    FilterInput.visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="host:X status:4xx method:POST path:/api/*",
            disabled=True,
        )

    def show(self) -> None:
        inp = self.query_one(Input)
        inp.disabled = False
        self.add_class("visible")
        inp.focus()

    def hide(self) -> None:
        self.remove_class("visible")
        inp = self.query_one(Input)
        inp.value = ""
        inp.disabled = True

    @on(Input.Submitted)
    def _on_submit(self, event: Input.Submitted) -> None:
        event.stop()
        value = event.value
        self.hide()
        self.post_message(self.Submitted(value))

    def key_escape(self) -> None:
        self.hide()
        self.post_message(self.Cancelled())


class ConfirmDialog(Widget):
    """Yes/No confirmation docked at the bottom."""

    class Confirmed(Message):
        def __init__(self, action: str) -> None:
            self.action = action
            super().__init__()

    class Cancelled(Message):
        pass

    DEFAULT_CSS = """
    ConfirmDialog {
        display: none;
        dock: bottom;
        height: 3;
        background: $warning;
        padding: 1;
    }
    ConfirmDialog.visible {
        display: block;
    }
    """

    BINDINGS = [
        ("y", "confirm", "yes"),
        ("n", "cancel", "no"),
        ("escape", "cancel", "cancel"),
    ]

    can_focus = True

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._action = ""

    def compose(self) -> ComposeResult:
        yield Static(id="confirm-text")

    def show(self, message: str, action: str) -> None:
        self._action = action
        self.query_one("#confirm-text", Static).update(message)
        self.add_class("visible")
        self.focus()

    def hide(self) -> None:
        self.remove_class("visible")

    def action_confirm(self) -> None:
        if "visible" not in self.classes:
            return
        action = self._action
        self.hide()
        self.post_message(self.Confirmed(action))

    def action_cancel(self) -> None:
        if "visible" not in self.classes:
            return
        self.hide()
        self.post_message(self.Cancelled())


class Toast(Static):
    """Transient success/info notice that auto-dismisses."""

    DEFAULT_CSS = """
    Toast {
        display: none;
        dock: bottom;
        height: 1;
        background: $success;
    }
    Toast.visible {
        display: block;
    }
    """

    def show_message(self, text: str, duration: float = 2.0) -> None:
        self.update(text)
        self.add_class("visible")
        self.set_timer(duration, self._dismiss)

    def _dismiss(self) -> None:
        self.remove_class("visible")


class CopyModal(Widget):
    """Modal with numbered copy options (1=URL, 2=Request, ...)."""

    class Selected(Message):
        def __init__(self, option: str) -> None:
            self.option = option
            super().__init__()

    class Cancelled(Message):
        pass

    DEFAULT_CSS = """
    CopyModal {
        display: none;
        dock: bottom;
        height: auto;
        max-height: 10;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    CopyModal.visible {
        display: block;
    }
    """

    BINDINGS = [
        ("1", "select('url')", "URL"),
        ("2", "select('request')", "Request"),
        ("3", "select('response')", "Response"),
        ("4", "select('response_body')", "Body"),
        ("5", "select('curl')", "curl"),
        ("6", "select('httpie')", "httpie"),
        ("escape", "cancel", "cancel"),
    ]

    can_focus = True

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        from troxy.tui.copy import COPY_OPTIONS

        lines = ["\u2500\u2500 Copy \u2500\u2500"]
        for key, label in COPY_OPTIONS:
            lines.append(f"  [{key}] {label}")
        yield Static("\n".join(lines))

    def show(self) -> None:
        self.add_class("visible")
        self.focus()

    def hide(self) -> None:
        self.remove_class("visible")

    def action_select(self, option: str) -> None:
        if "visible" not in self.classes:
            return
        self.hide()
        self.post_message(self.Selected(option))

    def action_cancel(self) -> None:
        if "visible" not in self.classes:
            return
        self.hide()
        self.post_message(self.Cancelled())


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return True
        for cmd in (["xclip", "-selection", "clipboard"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True)
                return True
            except FileNotFoundError:
                continue
        return False
    except Exception:
        return False
