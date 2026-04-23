"""Tests for MockDialog — register a flow as a mock rule."""

import json
import time

import pytest

from troxy.core.db import init_db
from troxy.core.mock import add_mock_rule, list_mock_rules
from troxy.core.store import insert_flow
from troxy.tui.mock_dialog import MockDialog


def _make_flow(db: str, *, path: str = "/api/users/12345/ratings",
               status: int = 401, method: str = "GET",
               host: str = "api.example.com") -> dict:
    """Insert a sample flow and return its dict."""
    from troxy.core.query import get_flow
    fid = insert_flow(
        db, timestamp=time.time(), method=method, scheme="https",
        host=host, port=443, path=path, query=None,
        request_headers={"Accept": "application/json"},
        request_body=None, request_content_type=None,
        status_code=status,
        response_headers={"Content-Type": "application/json"},
        response_body='{"error": "unauthorized"}',
        response_content_type="application/json",
        duration_ms=30.0,
    )
    return get_flow(db, fid)


# -- MockDialog unit tests --


@pytest.mark.asyncio
async def test_mock_dialog_cancel_pops(tmp_db):
    """Esc closes MockDialog without saving."""
    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db)

    from textual.app import App
    from troxy.tui.mock_dialog import MockDialog

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        assert isinstance(pilot.app.screen, MockDialog)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, MockDialog)
        # No rule was saved
        assert list_mock_rules(db) == []


@pytest.mark.asyncio
async def test_mock_dialog_save_creates_rule(tmp_db):
    """Ctrl+S saves a mock rule with prefilled fields."""
    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, path="/api/users/12345/ratings", status=401)

    from textual.app import App
    from troxy.tui.mock_dialog import MockDialog

    saved_events: list = []

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

        def on_mock_dialog_saved(self, event: MockDialog.Saved):
            saved_events.append(event)

    async with TestApp().run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()

    rules = list_mock_rules(db)
    assert len(rules) == 1
    rule = rules[0]
    assert rule["domain"] == "api.example.com"
    # Glob suggestion toggled ON by default when path has dynamic segments
    assert rule["path_pattern"] == "/api/users/*/ratings"
    assert rule["method"] == "GET"
    assert rule["status_code"] == 401
    # Body is prettified on dialog open (Bug #10) and saved as edited.
    assert rule["response_body"] == '{\n  "error": "unauthorized"\n}'
    # Saved message was posted
    assert len(saved_events) == 1
    assert saved_events[0].rule_id == rule["id"]


@pytest.mark.asyncio
async def test_mock_dialog_preserves_headers_as_json(tmp_db):
    """Response headers (dict) should be persisted as JSON string."""
    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db)

    from textual.app import App
    from troxy.tui.mock_dialog import MockDialog

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()

    rules = list_mock_rules(db)
    headers_json = rules[0]["response_headers"]
    assert isinstance(headers_json, str)
    parsed = json.loads(headers_json)
    assert parsed.get("Content-Type") == "application/json"


@pytest.mark.asyncio
async def test_mock_dialog_duplicate_name_emits_error(tmp_db):
    """Attempting to save with a duplicate name should post an Error message."""
    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, path="/api/users/12345/ratings", status=401)
    # Pre-populate: auto name will be 'ratings-401'
    add_mock_rule(db, domain="x.com", path_pattern="/", status_code=200, name="ratings-401")

    from textual.app import App
    from troxy.tui.mock_dialog import MockDialog

    errors: list = []

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

        def on_mock_dialog_error(self, event: MockDialog.Error):
            errors.append(event)

    async with TestApp().run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        # Dialog must still be open after a duplicate-name error.
        assert isinstance(pilot.app.screen, MockDialog)

    # No new rule was persisted and an Error message was posted.
    rules = list_mock_rules(db)
    assert len(rules) == 1  # only the pre-existing one
    assert len(errors) == 1
    assert "ratings-401" in errors[0].message


def test_mock_dialog_auto_name_uses_last_alpha_segment():
    """Auto-name pulls last non-numeric segment + status."""
    from troxy.tui.mock_dialog import MockDialog
    assert MockDialog._auto_name(
        {"path": "/api/users/12345/ratings", "status_code": 401}
    ) == "ratings-401"


def test_mock_dialog_auto_name_skips_numeric_last_segment():
    """If last segment is digits, use previous one."""
    from troxy.tui.mock_dialog import MockDialog
    assert MockDialog._auto_name(
        {"path": "/api/users/12345", "status_code": 404}
    ) == "users-404"


def test_mock_dialog_auto_name_fallback():
    """Empty-ish path uses 'mock' fallback."""
    from troxy.tui.mock_dialog import MockDialog
    assert MockDialog._auto_name({"path": "/", "status_code": 500}) == "mock-500"


# -- Integration: ListScreen m key -> MockDialog --


@pytest.mark.asyncio
async def test_list_screen_m_key_opens_mock_dialog(tmp_db):
    """Pressing m on a selected flow in ListScreen pushes MockDialog."""
    db = str(tmp_db)
    init_db(db)
    insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/items/42", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=200, response_headers={}, response_body="ok",
        response_content_type="text/plain", duration_ms=10.0,
    )

    from textual.app import App
    from troxy.tui.list_screen import ListScreen
    from troxy.tui.mock_dialog import MockDialog

    class TestApp(App):
        def on_mount(self):
            self.push_screen(ListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MockDialog)
        await pilot.press("escape")


# -- Integration: DetailScreen m key -> MockDialog --


@pytest.mark.asyncio
async def test_detail_screen_m_key_opens_mock_dialog(tmp_db):
    """Pressing m in DetailScreen pushes MockDialog."""
    db = str(tmp_db)
    init_db(db)
    fid = insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/items/42", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=200, response_headers={}, response_body="ok",
        response_content_type="text/plain", duration_ms=10.0,
    )

    from textual.app import App
    from troxy.tui.detail_screen import DetailScreen
    from troxy.tui.mock_dialog import MockDialog

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MockDialog)
        await pilot.press("escape")


# -- Bug #10: body pretty-JSON regression guards --


def test_prettify_body_indents_json_with_2_spaces():
    """JSON content_type → indent=2, ensure_ascii=False."""
    out = MockDialog._prettify_body('{"a":1,"b":"\ud55c"}', "application/json")
    assert out == '{\n  "a": 1,\n  "b": "\ud55c"\n}'


def test_prettify_body_preserves_invalid_json():
    """Invalid JSON with json content_type → verbatim, never silently corrupts."""
    raw = "{not valid json"
    assert MockDialog._prettify_body(raw, "application/json") == raw


def test_prettify_body_preserves_plain_text():
    """Non-JSON content_type → raw body passthrough."""
    assert (
        MockDialog._prettify_body("hello world", "text/plain")
        == "hello world"
    )


def test_prettify_body_handles_none_content_type():
    """No content_type → don't attempt JSON parsing."""
    assert MockDialog._prettify_body('{"a":1}', None) == '{"a":1}'


def test_prettify_body_empty_body_returns_empty():
    """Empty body short-circuits to empty string."""
    assert MockDialog._prettify_body("", "application/json") == ""
    assert MockDialog._prettify_body(None, "application/json") == ""


def test_prettify_body_json_charset_variant():
    """application/json; charset=utf-8 still triggers pretty path (substring match)."""
    out = MockDialog._prettify_body('{"k":1}', "application/json; charset=utf-8")
    assert out == '{\n  "k": 1\n}'


@pytest.mark.asyncio
async def test_mock_dialog_body_field_is_pretty_on_open(tmp_db):
    """Opening MockDialog on a JSON flow shows indented body in the TextArea."""
    from textual.widgets import TextArea

    db = str(tmp_db)
    init_db(db)
    fid = insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/items/42", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"id":42,"name":"foo"}',
        response_content_type="application/json", duration_ms=10.0,
    )

    from textual.app import App
    from troxy.tui.detail_screen import DetailScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(DetailScreen(db, fid))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        body = pilot.app.screen.query_one("#mock-body", TextArea)
        assert body.text == '{\n  "id": 42,\n  "name": "foo"\n}'
        await pilot.press("escape")


# -- Bug #16: host/path/method editable -----------------------------------
#
# Each test below names the mutation it catches so a reviewer can confirm
# 1:1 coverage — pair each compose/save line with exactly one probe.


@pytest.mark.asyncio
async def test_mock_dialog_host_path_method_prefilled(tmp_db):
    """Mutation probe: delete the ``#mock-host`` yield in compose →
    query_one raises NoMatches and this test FAILs."""
    from textual.app import App
    from textual.widgets import Input, Select

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, host="api.example.com", method="POST",
                      path="/api/users/12345/ratings")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        dialog = pilot.app.screen
        assert dialog.query_one("#mock-host", Input).value == "api.example.com"
        # Glob toggle is ON by default → path Input shows suggested glob.
        assert (
            dialog.query_one("#mock-path", Input).value
            == "/api/users/*/ratings"
        )
        assert dialog.query_one("#mock-method", Select).value == "POST"


@pytest.mark.asyncio
async def test_mock_dialog_save_persists_edited_url(tmp_db):
    """Mutation probe: flip ``domain=host`` back to ``domain=f['host']``
    in action_save → the saved rule keeps the flow's original host and
    this assertion FAILs."""
    from textual.app import App
    from textual.widgets import Input, Select

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, host="api.example.com", method="GET",
                      path="/api/users/12345/ratings")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        dialog = pilot.app.screen
        dialog.query_one("#mock-host", Input).value = "staging.example.com"
        dialog.query_one("#mock-path", Input).value = "/api/v2/*"
        dialog.query_one("#mock-method", Select).value = "DELETE"
        dialog.query_one("#mock-name", Input).value = "custom-edit"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    rules = list_mock_rules(db)
    assert len(rules) == 1
    rule = rules[0]
    assert rule["domain"] == "staging.example.com"
    assert rule["path_pattern"] == "/api/v2/*"
    assert rule["method"] == "DELETE"


@pytest.mark.asyncio
async def test_mock_dialog_exotic_method_is_preserved(tmp_db):
    """Mutation probe: drop the fallback-append branch in
    ``_method_options_with`` → flow.method='TRACE' no longer appears in
    the Select options; Select.value='TRACE' would raise InvalidValue on
    mount. The assertion below confirms the option is present."""
    from textual.app import App
    from textual.widgets import Select

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, method="TRACE")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        select = pilot.app.screen.query_one("#mock-method", Select)
        assert select.value == "TRACE"


@pytest.mark.asyncio
async def test_mock_dialog_glob_toggle_rewrites_path_input(tmp_db):
    """Mutation probe: remove ``on_switch_changed`` → toggling the glob
    Switch no longer rewrites the path Input; the assertion after toggle
    OFF FAILs because the field still holds the suggested glob."""
    from textual.app import App
    from textual.widgets import Input, Switch

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, path="/api/users/12345/ratings")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        dialog = pilot.app.screen
        path_input = dialog.query_one("#mock-path", Input)
        # Default: toggle ON, path Input shows suggested glob.
        assert path_input.value == "/api/users/*/ratings"
        dialog.query_one("#use-glob", Switch).value = False
        await pilot.pause()
        assert path_input.value == "/api/users/12345/ratings"
        dialog.query_one("#use-glob", Switch).value = True
        await pilot.pause()
        assert path_input.value == "/api/users/*/ratings"


# -- Bug #17: Ctrl+L clears body TextArea --------------------------------


@pytest.mark.asyncio
async def test_mock_dialog_ctrl_l_clears_body_only(tmp_db):
    """Mutation probe pair:
      (A) delete ``action_clear_body`` → body TextArea keeps its text,
          the ``body.text == ""`` assertion FAILs.
      (B) broaden ``action_clear_body`` to wipe every Input (host/path/
          name) → the three 'still populated' assertions FAIL.
    Together they pin the scope: Ctrl+L touches body and nothing else.
    """
    from textual.app import App
    from textual.widgets import Input, TextArea

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, path="/api/users/12345/ratings")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        dialog = pilot.app.screen
        body = dialog.query_one("#mock-body", TextArea)
        # Prettified body from the JSON flow fixture — non-empty.
        assert body.text != ""
        host_before = dialog.query_one("#mock-host", Input).value
        path_before = dialog.query_one("#mock-path", Input).value
        name_before = dialog.query_one("#mock-name", Input).value
        await pilot.press("ctrl+l")
        await pilot.pause()
        assert body.text == ""
        # Scope guard: other fields must stay intact.
        assert dialog.query_one("#mock-host", Input).value == host_before
        assert dialog.query_one("#mock-path", Input).value == path_before
        assert dialog.query_one("#mock-name", Input).value == name_before


@pytest.mark.asyncio
async def test_mock_dialog_empty_host_falls_back_to_flow_value(tmp_db):
    """Probe R guard: action_save의 ``host = Input.value.strip() or f["host"]``
    fallback이 제거되어도 (``or f["host"]`` 절 drop) CI green이던 게 Round 6의
    9224611 probe R 발견 지점. 이 테스트는 빈 host Input → flow.host 로
    폴백하는지 직접 pin."""
    from textual.app import App
    from textual.widgets import Input

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, host="api.example.com", method="GET",
                      path="/api/users")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        dialog = pilot.app.screen
        # 사용자가 실수로 Host Input을 비워도 flow의 원본 값이 persist되어야 함.
        dialog.query_one("#mock-host", Input).value = ""
        dialog.query_one("#mock-name", Input).value = "empty-host-test"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    rules = list_mock_rules(db)
    assert len(rules) == 1
    assert rules[0]["domain"] == "api.example.com"


@pytest.mark.asyncio
async def test_mock_dialog_empty_path_falls_back_to_flow_value(tmp_db):
    """Probe R guard: path에 대한 동일 fallback — ``or f["path"]`` 제거 시
    빈 path로 persist되면 mock rule이 절대 매칭 안 됨."""
    from textual.app import App
    from textual.widgets import Input

    db = str(tmp_db)
    init_db(db)
    flow = _make_flow(db, host="api.example.com", method="POST",
                      path="/api/v2/payments")

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockDialog(db, flow))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        dialog = pilot.app.screen
        dialog.query_one("#mock-path", Input).value = ""
        dialog.query_one("#mock-name", Input).value = "empty-path-test"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    rules = list_mock_rules(db)
    assert len(rules) == 1
    assert rules[0]["path_pattern"] == "/api/v2/payments"


# Note: method Select는 allow_blank=False라 runtime에 value가 절대 None이
# 될 수 없음. action_save의 ``else f["method"]`` 분기는 dead code이며
# 테스트로 pin 불가. 다음 refactor 사이클(Task #25.4 Guard/Sync audit)에서
# dead fallback 제거 대상.
