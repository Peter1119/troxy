"""E2E integration scenarios across ListScreen → DetailScreen → mutate → back.

These exercise real key bindings (not direct action_* calls) wherever possible,
and use the 10k fixture to ensure rendering/querying doesn't collapse at volume.
"""

from unittest.mock import patch

import pytest

from textual.widgets import DataTable, Input

from troxy.core.query import list_flows
from troxy.tui.app import TroxyStartApp
from troxy.tui.detail_screen import DetailScreen
from troxy.tui.list_screen import ListScreen
from troxy.tui.inline_filter import InlineFilter
from troxy.tui.widgets import ConfirmDialog, CopyModal, Toast


@pytest.mark.asyncio
async def test_e2e_10k_load_filter_detail_copy_back_clear(db_10k):
    """Full golden-path flow: load 10k → filter → open detail → copy → back → clear."""
    app = TroxyStartApp(db_path=db_10k)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ListScreen)

        table = app.screen.query_one("#flow-table", DataTable)
        # initial load caps at 500 rows
        initial_rows = table.row_count
        assert initial_rows == 500

        # filter narrows — SAMPLE_STATUSES includes 401/403/500 (3 of 10) → ~3000 rows
        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        inline.query_one("#inline-filter-status", Input).value = "5xx"
        await pilot.press("enter")
        await pilot.pause()
        filtered = table.row_count
        assert filtered > 0
        assert filtered <= initial_rows  # narrowed or equal (not an explosion)

        # open detail on current row
        app.screen.action_view_detail()
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)

        # copy URL via shortcut — verifies toast + clipboard call
        with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
            await pilot.press("u")
            await pilot.pause()
            mock_copy.assert_called_once()
            toast = app.screen.query_one("#toast", Toast)
            assert "visible" in toast.classes

        # back to list
        app.screen.action_go_back()
        await pilot.pause()
        assert isinstance(app.screen, ListScreen)

        # clear filter so clear_all targets the full DB, not the filtered view
        app.screen.action_clear_filter()
        await pilot.pause()
        assert table.row_count == 500

        # clear all — show dialog then confirm via action_* (reliable in test env)
        app.screen.action_clear_all()
        await pilot.pause()
        confirm = app.screen.query_one("#confirm", ConfirmDialog)
        assert "visible" in confirm.classes
        confirm.action_confirm()
        await pilot.pause()

        assert table.row_count == 0
        assert list_flows(db_10k) == []

        await pilot.press("q")


@pytest.mark.asyncio
async def test_e2e_filter_then_poll_skips_new_flows(db_with_flows):
    """When a filter is active, _poll_new_flows must not inject new rows.

    This guards the UX contract: the user's filter view is stable while
    new flows stream in; they see them only after clearing the filter.
    """
    app = TroxyStartApp(db_path=db_with_flows)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)

        # apply filter
        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        inline.query_one("#inline-filter-host", Input).value = "auth.example.com"
        await pilot.press("enter")
        await pilot.pause()
        after_filter = table.row_count

        # insert a fresh flow while filter is active — should NOT appear in view
        import time as _time
        from troxy.core.store import insert_flow

        insert_flow(
            db_with_flows, timestamp=_time.time(), method="GET",
            scheme="https", host="other.example.com", port=443, path="/post-filter",
            query=None, request_headers={}, request_body=None, request_content_type=None,
            status_code=200, response_headers={}, response_body="x",
            response_content_type="text/plain", duration_ms=1.0,
        )

        # manually trigger the poll — it must early-return
        app.screen._poll_new_flows()
        await pilot.pause()
        assert table.row_count == after_filter, "filter view mutated by polling — regression"

        await pilot.press("q")


@pytest.mark.asyncio
async def test_e2e_copy_modal_option_via_keypress_end_to_end(db_with_flows):
    """End-to-end: ListScreen Enter → DetailScreen y (modal) → 5 (curl) → toast."""
    app = TroxyStartApp(db_path=db_with_flows)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_view_detail()
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)

        with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
            await pilot.press("y")
            await pilot.pause()
            modal = app.screen.query_one("#copy-modal", CopyModal)
            assert "visible" in modal.classes

            await pilot.press("5")  # curl
            await pilot.pause()
            assert "visible" not in modal.classes
            mock_copy.assert_called_once()
            assert mock_copy.call_args[0][0].startswith("curl")

        await pilot.press("escape")
