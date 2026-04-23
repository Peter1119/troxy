import time

import pytest

from rich.syntax import Syntax
from rich.text import Text

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.detail_helpers import body_renderable, get_url
from troxy.tui.detail_screen import DetailScreen


@pytest.mark.asyncio
async def test_detail_screen_shows_flow(tmp_db):
    db = str(tmp_db)
    init_db(db)
    fid = insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/test", query="q=1",
        request_headers={"Accept": "application/json"},
        request_body=None, request_content_type=None,
        status_code=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"ok": true}',
        response_content_type="application/json", duration_ms=42.0,
    )

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        app = pilot.app
        assert isinstance(app.screen, DetailScreen)
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_detail_screen_pops_on_missing_flow(tmp_db):
    db = str(tmp_db)
    init_db(db)

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, 99999))

    async with TestApp().run_test() as pilot:
        app = pilot.app
        assert not isinstance(app.screen, DetailScreen)


@pytest.mark.asyncio
async def test_detail_screen_tab_switches_active_tab(tmp_db):
    """Tab/Shift+Tab must still toggle active tab for legacy keyboard users."""
    db = str(tmp_db)
    init_db(db)
    fid = insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/test", query=None,
        request_headers={"Accept": "application/json"},
        request_body=None, request_content_type=None,
        status_code=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"ok": true}',
        response_content_type="application/json", duration_ms=10.0,
    )

    from textual.app import App

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        app = pilot.app
        screen: DetailScreen = app.screen
        assert screen._active_tab == "response"
        await pilot.press("tab")
        assert screen._active_tab == "request"
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_escape_pops_detail_back_to_list(tmp_db):
    """Bug #7 regression: Textual's Screen._key_escape calls clear_selection()
    and masks the ``escape → go_back`` binding. DetailScreen.key_escape
    override must route escape back to pop_screen.

    Note: Textual pilot drives bindings through the DOM tree, not the real
    TTY keypath. See tests/tui/test_real_tty.py for the pexpect gate.
    """
    from troxy.tui.app import TroxyStartApp
    from troxy.tui.list_screen import ListScreen

    db = str(tmp_db)
    init_db(db)
    insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/test", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=200, response_headers={}, response_body="ok",
        response_content_type="text/plain", duration_ms=10.0,
    )

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ListScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ListScreen)
        await pilot.press("q")


def test_body_renderable_binary_returns_placeholder():
    """Bodies prefixed with 'b64:' are rendered as a size placeholder, not decoded."""
    out = body_renderable("b64:ZGVhZGJlZWY=", "application/octet-stream")
    assert isinstance(out, Text)
    assert out.plain.startswith("(binary,")
    assert "bytes base64" in out.plain


def test_body_renderable_invalid_json_falls_through_to_raw():
    """content_type says json but body is not valid → returns raw Text unchanged."""
    out = body_renderable("{not valid json", "application/json")
    assert isinstance(out, Text)
    assert out.plain == "{not valid json"


def test_body_renderable_valid_json_pretty_prints():
    """Valid JSON returns a Syntax renderable with 2-space indentation."""
    out = body_renderable('{"a":1,"b":2}', "application/json")
    assert isinstance(out, Syntax)
    assert "\n" in out.code
    assert '"a": 1' in out.code


def test_body_renderable_none_returns_none():
    """Empty body returns None (caller decides how to render the gap)."""
    assert body_renderable(None, None) is None


def test_get_url_includes_custom_port():
    """Non-standard ports (not 80/443) are rendered in URL."""
    flow = {
        "scheme": "http", "host": "localhost", "port": 8080,
        "path": "/api/x", "query": None,
    }
    assert get_url(flow) == "http://localhost:8080/api/x"


def test_get_url_omits_standard_ports():
    """Ports 80 (http) and 443 (https) are not rendered."""
    flow = {
        "scheme": "https", "host": "example.com", "port": 443,
        "path": "/a", "query": "q=1",
    }
    assert get_url(flow) == "https://example.com/a?q=1"


# ---------- Bug #9 tab view regression guards ----------

def _seed_tab_flow(db: str) -> int:
    return insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/x", query=None,
        request_headers={"accept": "application/json"},
        request_body=None, request_content_type=None,
        status_code=200,
        response_headers={"content-type": "application/json"},
        response_body='{"ok": true}',
        response_content_type="application/json", duration_ms=10.0,
    )


@pytest.mark.asyncio
async def test_initial_active_tab_is_response(tmp_db):
    """On mount the Response tab is active; request container is hidden."""
    from textual.app import App
    from textual.containers import VerticalScroll

    db = str(tmp_db)
    init_db(db)
    fid = _seed_tab_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        screen: DetailScreen = pilot.app.screen
        assert screen._active_tab == "response"
        req = screen.query_one("#request-container", VerticalScroll)
        res = screen.query_one("#response-container", VerticalScroll)
        assert "hidden" in req.classes
        assert "hidden" not in res.classes
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_left_arrow_switches_to_request(tmp_db):
    """← arrow activates the Request tab and hides the Response container."""
    from textual.app import App
    from textual.containers import VerticalScroll

    db = str(tmp_db)
    init_db(db)
    fid = _seed_tab_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        screen: DetailScreen = pilot.app.screen
        await pilot.press("left")
        assert screen._active_tab == "request"
        req = screen.query_one("#request-container", VerticalScroll)
        res = screen.query_one("#response-container", VerticalScroll)
        assert "hidden" not in req.classes
        assert "hidden" in res.classes
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_right_arrow_switches_to_response(tmp_db):
    """→ arrow brings Response tab back after navigating away."""
    from textual.app import App
    from textual.containers import VerticalScroll

    db = str(tmp_db)
    init_db(db)
    fid = _seed_tab_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        screen: DetailScreen = pilot.app.screen
        await pilot.press("left")
        assert screen._active_tab == "request"
        await pilot.press("right")
        assert screen._active_tab == "response"
        req = screen.query_one("#request-container", VerticalScroll)
        res = screen.query_one("#response-container", VerticalScroll)
        assert "hidden" in req.classes
        assert "hidden" not in res.classes
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_non_active_tab_container_has_hidden_class(tmp_db):
    """Spec pin: non-active tab's container must carry ``.hidden`` class.

    Guards against someone removing ``_update_tab_visibility`` or replacing
    the `.hidden` toggle with e.g. tint/opacity — both panes showing again
    would revert Bug #9.
    """
    from textual.app import App
    from textual.containers import VerticalScroll

    db = str(tmp_db)
    init_db(db)
    fid = _seed_tab_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        screen: DetailScreen = pilot.app.screen
        # Exactly one container must be hidden at any given time.
        for _ in range(3):  # toggle a few times
            req = screen.query_one("#request-container", VerticalScroll)
            res = screen.query_one("#response-container", VerticalScroll)
            hidden_count = int("hidden" in req.classes) + int("hidden" in res.classes)
            assert hidden_count == 1
            await pilot.press("left")
        await pilot.press("escape")


def test_arrow_bindings_are_declared():
    """BINDINGS must include left→show_request and right→show_response.

    Spec pin for mutation probe: removing either binding must FAIL this test.
    """
    keys = {b[0]: b[1] for b in DetailScreen.BINDINGS}
    assert keys.get("left") == "show_request"
    assert keys.get("right") == "show_response"


# ---------- Bug #12: Response pane scroll regression guards ----------


def _seed_long_flow(db: str, line_count: int = 400) -> int:
    """Flow with a response body guaranteed to overflow the default viewport."""
    body = "\n".join(f'"line-{i}": {i}' for i in range(line_count))
    return insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/long", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=200, response_headers={}, response_body=body,
        response_content_type="text/plain", duration_ms=10.0,
    )


@pytest.mark.asyncio
async def test_response_container_is_vertical_scroll(tmp_db):
    """Spec pin: response-container must be VerticalScroll (not plain Vertical).

    Mutation probe: swap VerticalScroll→Vertical and this test FAILs.
    """
    from textual.app import App
    from textual.containers import VerticalScroll

    db = str(tmp_db)
    init_db(db)
    fid = _seed_long_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        screen: DetailScreen = pilot.app.screen
        res = screen.query_one("#response-container", VerticalScroll)
        req = screen.query_one("#request-container", VerticalScroll)
        assert isinstance(res, VerticalScroll)
        assert isinstance(req, VerticalScroll)
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_response_pane_scrolls_on_down_key(tmp_db):
    """Long body + down arrow advances scroll_y.

    The scroll offset must actually move — this pins the UX promise: users
    can read overflowing response bodies from the keyboard.
    """
    from textual.app import App
    from textual.containers import VerticalScroll

    db = str(tmp_db)
    init_db(db)
    fid = _seed_long_flow(db)

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        screen: DetailScreen = pilot.app.screen
        res = screen.query_one("#response-container", VerticalScroll)
        res.focus()
        await pilot.pause()
        start_y = res.scroll_y
        for _ in range(5):
            await pilot.press("down")
        await pilot.pause()
        assert res.scroll_y > start_y, (
            f"response-container did not scroll: start={start_y}, "
            f"after={res.scroll_y}"
        )
        await pilot.press("escape")
