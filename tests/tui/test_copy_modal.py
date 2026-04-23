import time
from unittest.mock import patch

import pytest

from textual.app import App, ComposeResult

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.detail_screen import DetailScreen
from troxy.tui.widgets import CopyModal, Toast


def _insert_flow(db: str) -> int:
    return insert_flow(
        db, timestamp=time.time(), method="POST", scheme="https",
        host="api.example.com", port=443, path="/api/users", query=None,
        request_headers={"Content-Type": "application/json"},
        request_body='{"name":"tester"}',
        request_content_type="application/json",
        status_code=201,
        response_headers={"Content-Type": "application/json"},
        response_body='{"id":1}',
        response_content_type="application/json", duration_ms=42.0,
    )


class _ModalHost(App):
    def __init__(self) -> None:
        super().__init__()
        self.selected: list[str] = []

    def compose(self) -> ComposeResult:
        yield CopyModal(id="cm")

    def on_copy_modal_selected(self, event: CopyModal.Selected) -> None:
        self.selected.append(event.option)


@pytest.mark.asyncio
async def test_copy_modal_select_url():
    app = _ModalHost()
    async with app.run_test() as pilot:
        cm = app.query_one(CopyModal)
        cm.show()
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        assert app.selected == ["url"]
        assert "visible" not in cm.classes


@pytest.mark.asyncio
async def test_copy_modal_escape_cancels():
    app = _ModalHost()
    async with app.run_test() as pilot:
        cm = app.query_one(CopyModal)
        cm.show()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.selected == []
        assert "visible" not in cm.classes


@pytest.mark.asyncio
async def test_detail_screen_y_opens_copy_modal(tmp_db):
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        app = pilot.app
        await pilot.press("y")
        await pilot.pause()
        cm = app.screen.query_one("#copy-modal", CopyModal)
        assert "visible" in cm.classes
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_detail_screen_u_copies_url_and_shows_toast(tmp_db):
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
        async with TestApp().run_test() as pilot:
            app = pilot.app
            await pilot.press("u")
            await pilot.pause()
            toast = app.screen.query_one("#toast", Toast)
            assert "visible" in toast.classes
            mock_copy.assert_called_once()
            assert "api.example.com" in mock_copy.call_args[0][0]


@pytest.mark.asyncio
async def test_detail_screen_c_copies_curl(tmp_db):
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
        async with TestApp().run_test() as pilot:
            await pilot.press("c")
            await pilot.pause()
            mock_copy.assert_called_once()
            assert mock_copy.call_args[0][0].startswith("curl")


@pytest.mark.asyncio
@pytest.mark.parametrize("key,expected_option", [
    ("1", "url"),
    ("2", "request"),
    ("3", "response"),
    ("4", "response_body"),
    ("5", "curl"),
    ("6", "httpie"),
])
async def test_copy_modal_all_number_keys_dispatch(key, expected_option):
    """All numeric keys 1-6 dispatch the expected option string."""
    app = _ModalHost()
    async with app.run_test() as pilot:
        cm = app.query_one(CopyModal)
        cm.show()
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert app.selected == [expected_option]
        assert "visible" not in cm.classes


@pytest.mark.asyncio
@pytest.mark.parametrize("option,must_contain", [
    ("request", "POST "),
    ("response", "HTTP 201"),
    ("response_body", '"id":1'),
    ("httpie", "http "),
])
async def test_detail_screen_modal_copies_option(tmp_db, option, must_contain):
    """DetailScreen consumes CopyModal.Selected and clipboard-copies the right payload."""
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
        async with TestApp().run_test() as pilot:
            app = pilot.app
            app.screen.on_copy_modal_selected(CopyModal.Selected(option))
            await pilot.pause()
            mock_copy.assert_called_once()
            payload = mock_copy.call_args[0][0]
            assert must_contain in payload


@pytest.mark.asyncio
async def test_detail_screen_Y_copies_focused_response_pane(tmp_db):
    """Shift+Y (action_copy_focused) copies the currently focused pane = response by default."""
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
        async with TestApp().run_test() as pilot:
            app = pilot.app
            # default focus is "response"
            app.screen.action_copy_focused()
            await pilot.pause()
            payload = mock_copy.call_args[0][0]
            assert payload.startswith("HTTP 201")


@pytest.mark.asyncio
async def test_detail_screen_Y_copies_focused_request_pane_after_tab(tmp_db):
    """After Tab, focus → request; Y copies the Request text."""
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
        async with TestApp().run_test() as pilot:
            app = pilot.app
            await pilot.press("tab")
            await pilot.pause()
            assert app.screen._active_tab == "request"
            app.screen.action_copy_focused()
            await pilot.pause()
            payload = mock_copy.call_args[0][0]
            assert payload.startswith("POST ")


@pytest.mark.asyncio
async def test_detail_screen_clipboard_failure_still_shows_toast(tmp_db):
    """If copy_to_clipboard returns False, toast still appears (non-blocking UX)."""
    db = str(tmp_db)
    init_db(db)
    fid = _insert_flow(db)

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=False):
        async with TestApp().run_test() as pilot:
            app = pilot.app
            await pilot.press("u")
            await pilot.pause()
            toast = app.screen.query_one("#toast", Toast)
            assert "visible" in toast.classes
