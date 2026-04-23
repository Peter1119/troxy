"""Bug #2 regression guards: bottom bar anchor across flow counts and
dialog states.

The original v0.3 round-1 bug was that ``#flow-table`` had no explicit
``height`` rule, so it grew to its natural content height. With 5 flows
the table was 5 rows tall and the hint/info bars sat right below it
mid-screen. With 50 flows the table shoved the hint/info bars *off the
bottom of the terminal* entirely — the user could not see their local IP
or the keybindings anymore.

Fix (in ``list_screen.py`` DEFAULT_CSS, later extracted to ``styles.py``):
``#flow-table { height: 1fr; }`` — claim all remaining vertical space so
the siblings below it always sit on the last rows.

These tests assert the fix *at the layout level* by reading widget
``.region.y`` coordinates after mount. They catch the regression even if
the CSS is deleted but the existing SVG snapshot tests happen to look OK
on a 40-row terminal with sparse data.
"""

from __future__ import annotations

import time

import pytest
from textual.widgets import DataTable, Static

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.app import TroxyStartApp

# Terminal size matches qa_snapshots so the two test suites diff cleanly.
# 40 rows is enough to show the difference between "info-bar anchored at
# row 39" (correct) and "info-bar at row 7 because table claimed height 5"
# (the original bug).
TERM_W = 120
TERM_H = 40


def _seed_flows(db: str, count: int) -> None:
    """Insert ``count`` varied flows without calling time.time() in a tight
    loop — we pre-compute timestamps so ORDER BY is stable across runs.
    """
    base = time.time() - count
    for i in range(count):
        status = [200, 200, 201, 304, 401, 403, 500][i % 7]
        method = ["GET", "POST", "GET", "DELETE", "PUT", "PATCH", "GET"][i % 7]
        insert_flow(
            db,
            timestamp=base + i,
            method=method,
            scheme="https",
            host=f"host{i % 4}.example.com",
            port=443,
            path=f"/api/v2/resource/{i}",
            query=None,
            request_headers={},
            request_body=None,
            request_content_type=None,
            status_code=status,
            response_headers={},
            response_body="ok",
            response_content_type="text/plain",
            duration_ms=10.0,
        )


async def _assert_bottom_bar_anchored(app: TroxyStartApp) -> None:
    """Core assertion: ``#info-bar`` sits on the terminal's last row, and
    ``#hint-bar`` sits immediately above ``#proxy-bar`` + ``#info-bar``.

    After Round 5 (Bug #14) the old ``#filter-status`` Static is gone —
    the InlineFilter at the TOP of the screen owns the filter display,
    and the bottom three rows are hint → proxy → info.

    Why read ``.region.y`` instead of just diffing SVGs?
    ------------------------------------------------------
    SVG diffs flag *any* pixel change, but layout regressions hide when the
    flow count happens to fit. A targeted y-coordinate assertion isolates
    "is the bottom bar at the bottom" from cosmetic churn elsewhere.
    """
    info = app.screen.query_one("#info-bar", Static)
    proxy_bar = app.screen.query_one("#proxy-bar", Static)
    hint = app.screen.query_one("#hint-bar", Static)

    assert info.region.y == TERM_H - 1, (
        f"#info-bar must be pinned to the last row (y={TERM_H - 1}), "
        f"got y={info.region.y}. Bug #2 regression: flow-table grew past "
        f"its 1fr share and pushed the info bar off-screen."
    )
    assert hint.region.y < proxy_bar.region.y < info.region.y, (
        f"layout order must be hint → proxy → info "
        f"(hint={hint.region.y}, proxy={proxy_bar.region.y}, "
        f"info={info.region.y})"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("flow_count", [0, 5, 20, 50, 100])
async def test_bottom_bar_anchored_across_flow_counts(tmp_db, flow_count):
    """Bug #2 core: info-bar stays on the last row at 0/5/20/50/100 flows.

    100 flows is well over the height of a 40-row terminal, so the table
    WILL scroll — but the hint/info bars must not be scrolled with it.
    """
    db = str(tmp_db)
    init_db(db)
    if flow_count:
        _seed_flows(db, flow_count)

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=(TERM_W, TERM_H)) as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == flow_count
        await _assert_bottom_bar_anchored(app)


@pytest.mark.asyncio
async def test_bottom_bar_anchored_with_active_filter(tmp_db):
    """Filter bar is always visible (Round 5) — applying a filter must
    NOT reshuffle the bottom anchor.

    Exact user flow from the original bug report: open InlineFilter with
    ``f``, type, press Enter. The InlineFilter sits at the TOP of the
    screen and owns its own 3-row height; the bottom hint/proxy/info
    stack must stay pinned to the last 3 rows.
    """
    db = str(tmp_db)
    init_db(db)
    _seed_flows(db, 30)

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=(TERM_W, TERM_H)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from textual.widgets import Input
        from troxy.tui.inline_filter import InlineFilter

        inline = app.screen.query_one(InlineFilter)
        inline.query_one("#inline-filter-status", Input).value = "4xx"
        await pilot.press("enter")
        await pilot.pause()

        await _assert_bottom_bar_anchored(app)

        # InlineFilter must still carry the user-typed value after submit
        # (values persist — no modal hide semantics).
        assert (
            inline.query_one("#inline-filter-status", Input).value == "4xx"
        )


@pytest.mark.asyncio
async def test_hint_and_info_visible_with_confirm_dialog(tmp_db):
    """``x`` opens the confirm dialog. The dialog renders as a sibling in
    the ListScreen compose tree (NOT a modal), so it takes real layout
    space. The spec (qa-protocol.md Bug #2 live checks) is:

      - dialog is visible on screen
      - hint bar is still visible
      - info bar is still visible

    The info bar no longer sits on the last row while the dialog is open —
    that's expected, because the dialog claims the bottom ~3 rows. What
    MUST NOT regress is hint/info getting clipped out of the terminal.
    """
    db = str(tmp_db)
    init_db(db)
    _seed_flows(db, 30)

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=(TERM_W, TERM_H)) as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()

        from troxy.tui.widgets import ConfirmDialog

        dialog = app.screen.query_one("#confirm", ConfirmDialog)
        assert "visible" in dialog.classes, "confirm dialog did not open"

        hint = app.screen.query_one("#hint-bar", Static)
        info = app.screen.query_one("#info-bar", Static)

        # "Still visible" means the widget's y is within the terminal AND
        # does not overlap the dialog's region.
        assert 0 <= hint.region.y < TERM_H, (
            f"hint-bar clipped off-screen: y={hint.region.y}"
        )
        assert 0 <= info.region.y < TERM_H, (
            f"info-bar clipped off-screen: y={info.region.y}"
        )
        dialog_y_start = dialog.region.y
        assert hint.region.y < dialog_y_start, (
            f"hint-bar overlaps dialog (hint.y={hint.region.y}, "
            f"dialog.y={dialog_y_start})"
        )
        assert info.region.y < dialog_y_start, (
            f"info-bar overlaps dialog (info.y={info.region.y}, "
            f"dialog.y={dialog_y_start})"
        )


@pytest.mark.asyncio
async def test_bottom_bar_anchored_on_narrow_terminal(tmp_db):
    """Bug #2 extended: narrow terminal (80 cols) reflows but still anchors.

    Users resize iTerm/tmux panes all the time. A reflow regression would
    look like "works at 120, breaks at 80" — this test nails that down."""
    db = str(tmp_db)
    init_db(db)
    _seed_flows(db, 20)

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=(80, TERM_H)) as pilot:
        await pilot.pause()
        info = app.screen.query_one("#info-bar", Static)
        assert info.region.y == TERM_H - 1, (
            f"narrow reflow broke bottom anchor: info-bar y={info.region.y}"
        )
        assert info.region.width == 80, (
            f"info-bar did not reflow to 80 cols: width={info.region.width}"
        )
