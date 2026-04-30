"""Tests for Bug #18 — ``s`` key toggles list sort (time asc / desc).

User ask (verbatim): "추가적으로 sort 기능 빠져있다. s 누르면 time 순으로
순서 바뀌도록 해줘. 쌓이는 것도 그렇고."

Mutation probes (each test catches its match):
  - Drop the ``_newest_first = not _newest_first`` flip in
    ``action_toggle_sort`` → toggle tests FAIL (state stuck).
  - Drop the ``if self._newest_first: return self._refresh_table_with_filter()``
    branch in ``_poll_new_flows`` → polling tests in newest-first mode FAIL
    (new flow lands at bottom instead of top).
  - Drop the ``table.columns["time"].label = time_header_label(...)``
    update in ``action_toggle_sort`` → header indicator test FAILs.
"""

import time

import pytest
from textual.widgets import DataTable, Static

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.app import TroxyStartApp


def _seed(db: str, count: int) -> None:
    for i in range(count):
        insert_flow(
            db,
            timestamp=1000.0 + i,  # stable ordering; newest = largest
            method="GET", scheme="https",
            host=f"host{i}.example.com", port=443, path=f"/p{i}", query=None,
            request_headers={}, request_body=None, request_content_type=None,
            status_code=200, response_headers={}, response_body="ok",
            response_content_type="text/plain", duration_ms=1.0,
        )


def _row_host(table: DataTable, row_index: int) -> str:
    """Pull the HOST cell (column index 4: marker/#/TIME/METHOD/HOST)."""
    row_key = table.ordered_rows[row_index].key
    return str(table.get_row(row_key)[4])


@pytest.mark.asyncio
async def test_s_key_toggles_newest_first_state(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed(db, 2)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen._newest_first is False
        await pilot.press("s")
        await pilot.pause()
        assert app.screen._newest_first is True
        await pilot.press("s")
        await pilot.pause()
        assert app.screen._newest_first is False
        await pilot.press("q")


@pytest.mark.asyncio
async def test_default_sort_oldest_at_top(tmp_db):
    """Default (``_newest_first=False``) matches pre-Bug-#18 behavior:
    id=1 (host0) at row 0, id=3 (host2) at bottom. Protects existing tests
    and user's "쌓이는 것도 그렇고" = current behavior stays default.
    """
    db = str(tmp_db)
    init_db(db)
    _seed(db, 3)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 3
        assert _row_host(table, 0) == "host0.example.com"
        assert _row_host(table, 2) == "host2.example.com"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_s_toggle_flips_row_order(tmp_db):
    """After ``s``, row 0 becomes the newest (host2), row 2 the oldest."""
    db = str(tmp_db)
    init_db(db)
    _seed(db, 3)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert _row_host(table, 0) == "host2.example.com"
        assert _row_host(table, 2) == "host0.example.com"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_polling_newest_first_inserts_at_top(tmp_db):
    """In newest-first mode, a late arrival must appear at row 0.

    Mutation probe: remove the ``if self._newest_first:`` early-rebuild
    branch from ``_poll_new_flows`` → new flow appended at bottom,
    ``row 0`` stays ``host2`` (the previous newest) instead of the new one.
    """
    db = str(tmp_db)
    init_db(db)
    _seed(db, 3)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        insert_flow(
            db,
            timestamp=2000.0, method="POST", scheme="https",
            host="latecomer.example.com", port=443, path="/new", query=None,
            request_headers={}, request_body=None, request_content_type=None,
            status_code=201, response_headers={}, response_body="",
            response_content_type=None, duration_ms=1.0,
        )
        # Two 0.5-s polls; one is enough but pause() is cheap.
        await pilot.pause()
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        # Wait up to ~1.5 s for the poll interval (set_interval 0.5 s).
        for _ in range(30):
            if table.row_count == 4:
                break
            await pilot.pause()
        assert table.row_count == 4
        assert _row_host(table, 0) == "latecomer.example.com"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_polling_default_appends_at_bottom(tmp_db):
    """In default (oldest-first) mode, polling appends to the bottom.

    Guards against a regression where ``_poll_new_flows`` unconditionally
    calls ``_refresh_table_with_filter`` — that would still produce the
    right order here but drop cursor state and waste cycles. This test
    asserts the cheap append path is retained.
    """
    db = str(tmp_db)
    init_db(db)
    _seed(db, 3)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        insert_flow(
            db,
            timestamp=2000.0, method="POST", scheme="https",
            host="latecomer.example.com", port=443, path="/new", query=None,
            request_headers={}, request_body=None, request_content_type=None,
            status_code=201, response_headers={}, response_body="",
            response_content_type=None, duration_ms=1.0,
        )
        table = app.screen.query_one("#flow-table", DataTable)
        for _ in range(30):
            if table.row_count == 4:
                break
            await pilot.pause()
        assert table.row_count == 4
        assert _row_host(table, 3) == "latecomer.example.com"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_time_header_indicator_reflects_sort(tmp_db):
    """Header arrow: ``\u25b2`` (oldest-first default) \u2194 ``\u25bc`` (newest-first).

    Mutation probe: drop the ``table.columns["time"].label = ...`` update
    in ``action_toggle_sort`` → arrow never changes, this FAILs.
    """
    db = str(tmp_db)
    init_db(db)
    _seed(db, 1)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        initial_label = str(table.columns["time"].label)
        assert "\u25b2" in initial_label, f"default arrow missing: {initial_label!r}"
        await pilot.press("s")
        await pilot.pause()
        toggled_label = str(table.columns["time"].label)
        assert "\u25bc" in toggled_label, f"toggled arrow missing: {toggled_label!r}"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_hint_advertises_s_sort(tmp_db):
    """Discoverability: bottom hint bar must mention ``s sort``."""
    db = str(tmp_db)
    init_db(db)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        hint = app.screen.query_one("#hint-bar", Static)
        assert "s 정렬" in str(hint.render())
        await pilot.press("q")
