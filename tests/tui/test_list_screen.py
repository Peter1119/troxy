import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.app import TroxyStartApp
from troxy.tui.list_screen import ListScreen


@pytest.mark.asyncio
async def test_list_screen_shows_flow_table(tmp_db):
    db = str(tmp_db)
    init_db(db)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        assert isinstance(app.screen, ListScreen)
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_screen_displays_flows(tmp_db):
    db = str(tmp_db)
    init_db(db)
    insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/api/test", query=None,
        request_headers={"Accept": "application/json"},
        request_body=None, request_content_type=None,
        status_code=200,
        response_headers={"Content-Type": "text/plain"},
        response_body="ok",
        response_content_type="text/plain", duration_ms=10.0,
    )

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        from textual.widgets import DataTable
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 1
        await pilot.press("q")


def _seed_two_flows(db: str) -> None:
    insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="api.example.com", port=443, path="/a", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=200, response_headers={}, response_body="ok",
        response_content_type="text/plain", duration_ms=1.0,
    )
    insert_flow(
        db, timestamp=time.time(), method="GET", scheme="https",
        host="api.example.com", port=443, path="/b", query=None,
        request_headers={}, request_body=None, request_content_type=None,
        status_code=401, response_headers={}, response_body="err",
        response_content_type="text/plain", duration_ms=1.0,
    )


@pytest.mark.asyncio
async def test_list_screen_filter_narrows_rows(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    from textual.widgets import DataTable, Input
    from troxy.tui.inline_filter import InlineFilter
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 2

        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        status_input = inline.query_one("#inline-filter-status", Input)
        status_input.value = "4xx"
        status_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert table.row_count == 1
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_screen_escape_only_hides_bar(tmp_db):
    """Round 7 semantic flip: Esc hides the edit bar but MUST NOT clear
    filter state. Complements the broader assertion in
    ``test_inline_filter.py::test_esc_hides_bar_without_clearing_filter``
    by focusing on the ListScreen-level DataTable re-focus.
    """
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    from textual.widgets import DataTable, Input
    from troxy.tui.inline_filter import InlineFilter
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        table = app.screen.query_one("#flow-table", DataTable)

        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        status_input = inline.query_one("#inline-filter-status", Input)
        status_input.value = "4xx"
        status_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert table.row_count == 1

        # Re-show and Esc: bar hides, filter stays.
        await pilot.press("f")
        await pilot.pause()
        assert "visible" in inline.classes
        app.screen.action_clear_filter()
        await pilot.pause()

        assert "visible" not in inline.classes
        assert table.row_count == 1, (
            "Round 7: Esc must NOT widen the table (filter state preserved)"
        )
        assert (
            inline.query_one("#inline-filter-status", Input).value == "4xx"
        ), "Round 7: Esc must NOT wipe InlineFilter fields"
        # Focus snaps back to the DataTable so ``q`` quits cleanly.
        assert isinstance(app.screen.focused, DataTable)
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_screen_clear_all_confirms_and_deletes(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    from textual.widgets import DataTable
    from troxy.core.query import list_flows
    from troxy.tui.widgets import ConfirmDialog
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 2

        app.screen.action_clear_all()
        await pilot.pause()
        dialog = app.screen.query_one("#confirm", ConfirmDialog)
        assert "visible" in dialog.classes
        dialog.action_confirm()
        await pilot.pause()

        assert table.row_count == 0
        assert list_flows(db) == []
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_screen_clear_all_cancel_keeps_flows(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    from textual.widgets import DataTable
    from troxy.core.query import list_flows
    from troxy.tui.widgets import ConfirmDialog
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)

        app.screen.action_clear_all()
        await pilot.pause()
        dialog = app.screen.query_one("#confirm", ConfirmDialog)
        assert "visible" in dialog.classes
        dialog.action_cancel()
        await pilot.pause()

        assert table.row_count == 2
        assert len(list_flows(db)) == 2
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_screen_intercept_placeholder_toast(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    from troxy.tui.widgets import Toast
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_intercept_placeholder()
        await pilot.pause()
        toast = app.screen.query_one("#toast", Toast)
        assert "visible" in toast.classes
        await pilot.press("q")


@pytest.mark.asyncio
async def test_q_quits_app_with_datatable_focused(tmp_db):
    """Regression: DataTable focus used to mask the Screen `q → quit` binding
    because Textual does not auto-bubble bare `quit` action lookups to App.
    Binding now uses `app.quit` explicit namespace.

    Note: Textual pilot drives bindings through the DOM tree, which is not
    identical to the TTY key routing path. See tests/tui/test_real_tty.py
    for the pexpect-based real-TTY assertion.
    """
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import DataTable
        assert isinstance(app.screen.focused, DataTable)
        await pilot.press("q")
        await pilot.pause()
        assert not app.is_running
        assert app.return_code == 0


@pytest.mark.asyncio
async def test_enter_on_datatable_opens_detail(tmp_db):
    """Regression: DataTable consumes Enter into its `RowSelected` message
    rather than letting the Screen `enter → view_detail` binding fire.
    Fix routes DetailScreen push through the RowSelected message handler.
    """
    from troxy.tui.detail_screen import DetailScreen

    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ListScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)


@pytest.mark.asyncio
async def test_x_clear_also_clears_filter_status_bar(tmp_db):
    """Probe R guard: 410030b에서 발견된 x-clear filter-status leak —
    `_clear_table`에서 `_refresh_filter_status()` 호출이 제거되어도 flow
    수 assertion만으론 CI green. 이 테스트는 활성 필터 → x clear 시
    `#filter-status` Static의 content + visibility도 함께 리셋되는지 pin.

    Mutation: `_clear_table()`에서 `self._refresh_filter_status()` 라인
    삭제 → 이 테스트 FAIL (stale filter-status 남음).
    """
    db = str(tmp_db)
    init_db(db)
    _seed_two_flows(db)

    from textual.widgets import Static
    from troxy.tui.widgets import ConfirmDialog

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        # 먼저 필터를 적용해서 #filter-status 를 active 상태로
        app.screen._active_filter = "host:api"
        app.screen._refresh_filter_status()
        await pilot.pause()

        status = app.screen.query_one("#filter-status", Static)
        before_text = str(status.render())
        assert before_text.strip() != "", (
            "테스트 세팅: filter-status에 content가 있어야 함"
        )

        # 이제 x clear 실행
        app.screen.action_clear_all()
        await pilot.pause()
        dialog = app.screen.query_one("#confirm", ConfirmDialog)
        dialog.action_confirm()
        await pilot.pause()

        # clear 후 filter-status 가 빈 상태여야 함
        status_after = app.screen.query_one("#filter-status", Static)
        after_text = str(status_after.render())
        assert after_text.strip() == "", (
            f"x clear 후 filter-status가 stale 상태로 남음: {after_text!r}"
        )
        await pilot.press("q")
