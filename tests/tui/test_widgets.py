"""Tests for reusable TUI widgets — FilterInput, ConfirmDialog, Toast."""

import pytest

from textual.app import App, ComposeResult

from troxy.tui.widgets import ConfirmDialog, FilterInput, Toast


class _FilterHost(App):
    def __init__(self) -> None:
        super().__init__()
        self.submitted: list[str] = []
        self.cancelled = 0

    def compose(self) -> ComposeResult:
        yield FilterInput(id="fi")

    def on_filter_input_submitted(self, event: FilterInput.Submitted) -> None:
        self.submitted.append(event.value)

    def on_filter_input_cancelled(self, event: FilterInput.Cancelled) -> None:
        self.cancelled += 1


@pytest.mark.asyncio
async def test_filter_input_hidden_by_default():
    app = _FilterHost()
    async with app.run_test() as pilot:
        fi = app.query_one(FilterInput)
        assert "visible" not in fi.classes
        await pilot.press("q")


@pytest.mark.asyncio
async def test_filter_input_emits_on_submit():
    app = _FilterHost()
    async with app.run_test() as pilot:
        fi = app.query_one(FilterInput)
        fi.show()
        await pilot.pause()
        from textual.widgets import Input
        fi.query_one(Input).value = "host:example.com"
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["host:example.com"]
        assert "visible" not in fi.classes


@pytest.mark.asyncio
async def test_filter_input_escape_cancels():
    app = _FilterHost()
    async with app.run_test() as pilot:
        fi = app.query_one(FilterInput)
        fi.show()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.cancelled == 1
        assert "visible" not in fi.classes


class _ConfirmHost(App):
    def __init__(self) -> None:
        super().__init__()
        self.confirmed_actions: list[str] = []
        self.cancelled = 0

    def compose(self) -> ComposeResult:
        yield ConfirmDialog(id="cd")

    def on_confirm_dialog_confirmed(self, event: ConfirmDialog.Confirmed) -> None:
        self.confirmed_actions.append(event.action)

    def on_confirm_dialog_cancelled(self, event: ConfirmDialog.Cancelled) -> None:
        self.cancelled += 1


@pytest.mark.asyncio
async def test_confirm_dialog_y_confirms_with_action():
    app = _ConfirmHost()
    async with app.run_test() as pilot:
        cd = app.query_one(ConfirmDialog)
        cd.show("delete all?", "clear")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert app.confirmed_actions == ["clear"]
        assert "visible" not in cd.classes


@pytest.mark.asyncio
async def test_confirm_dialog_n_cancels():
    app = _ConfirmHost()
    async with app.run_test() as pilot:
        cd = app.query_one(ConfirmDialog)
        cd.show("delete all?", "clear")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.cancelled == 1
        assert app.confirmed_actions == []


@pytest.mark.asyncio
async def test_confirm_dialog_escape_cancels():
    app = _ConfirmHost()
    async with app.run_test() as pilot:
        cd = app.query_one(ConfirmDialog)
        cd.show("delete all?", "clear")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.cancelled == 1


class _ToastHost(App):
    def compose(self) -> ComposeResult:
        yield Toast(id="toast")


@pytest.mark.asyncio
async def test_toast_show_message_adds_visible_class():
    app = _ToastHost()
    async with app.run_test() as pilot:
        toast = app.query_one(Toast)
        toast.show_message("hello")
        await pilot.pause()
        assert "visible" in toast.classes


@pytest.mark.asyncio
async def test_toast_auto_dismisses():
    # visible-after-show is covered by test_toast_show_message_adds_visible_class;
    # this test only verifies dismissal after the timer fires. A larger duration and
    # proportionally larger pause avoid flakes under full-suite CPU contention.
    app = _ToastHost()
    async with app.run_test() as pilot:
        toast = app.query_one(Toast)
        toast.show_message("hello", duration=0.2)
        await pilot.pause(0.5)
        assert "visible" not in toast.classes
