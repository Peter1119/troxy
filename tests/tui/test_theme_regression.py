"""Regression guards: ``theme.METHOD_COLORS`` / ``STATUS_COLORS`` must be
*applied* to rendered cells, not merely defined.

v0.3 round-1 shipped with the palette defined in ``troxy.tui.theme`` but
``_add_flow_row`` never called ``method_color()`` / ``status_color()`` — so
every method and status cell rendered with no style. Visually the list
looked flat and the status-code semantics (2xx green / 4xx yellow / 5xx
red) were invisible.

design-review caught it during Round-2 visual audit. These tests pin the
fix down so the same regression can't sneak back by refactoring the row
builder into a plain ``table.add_row(str, str, ...)`` form.

We deliberately assert on the *presence* of a non-empty Rich ``Text.style``
rather than the exact colour value. Exact colours still churn (design may
swap green→#22c55e); call-site invocation is the invariant we care about.
"""

from __future__ import annotations

import time

import pytest
from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.app import TroxyStartApp


def _insert_flow(db: str, method: str, status: int, path: str = "/x") -> None:
    insert_flow(
        db,
        timestamp=time.time(),
        method=method,
        scheme="https",
        host="api.example.com",
        port=443,
        path=path,
        query=None,
        request_headers={},
        request_body=None,
        request_content_type=None,
        status_code=status,
        response_headers={},
        response_body=None,
        response_content_type=None,
        duration_ms=10.0,
    )


def _find_cell_containing(table: DataTable, needle: str) -> Text | None:
    """Scan row 0 for the first ``rich.Text`` cell whose plain text contains
    ``needle``. Returns the cell (so callers can assert on ``.style``) or
    ``None`` if nothing matches.

    We scan by content rather than by column index because the table layout
    has shifted across design rounds (marker column was added, id column
    moved). Asserting by semantic needle — "GET", "403" — keeps the test
    resilient to column reorders while still pinning the invariant we care
    about: *this specific cell is a styled Text, not a bare string*.
    """
    for col in range(len(table.ordered_columns)):
        cell = table.get_cell_at(Coordinate(0, col))
        if isinstance(cell, Text) and needle in cell.plain:
            return cell
    return None


@pytest.mark.asyncio
async def test_method_cell_is_styled_text(tmp_db):
    """METHOD column must be a ``rich.Text`` with a non-empty style.

    Regression: ``_add_flow_row`` used to emit ``flow["method"]`` directly
    (a bare ``str``). That path bypasses ``method_color()`` entirely and
    renders in the default DataTable colour.
    """
    db = str(tmp_db)
    init_db(db)
    _insert_flow(db, method="POST", status=200)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 1

        method_cell = _find_cell_containing(table, "POST")
        assert method_cell is not None, (
            "METHOD cell with 'POST' not found — row layout may have changed"
        )
        assert str(method_cell.style), (
            "METHOD cell style is empty — theme.METHOD_COLORS not applied. "
            "Did _add_flow_row lose its method_color() call?"
        )


@pytest.mark.asyncio
async def test_status_cell_is_styled_text(tmp_db):
    """STATUS column must be a styled ``rich.Text`` including the icon.

    Regression: plain-string status (``"403"``) meant the user could not
    tell a 4xx error from a 2xx success at a glance — the whole point of
    the flow list.
    """
    db = str(tmp_db)
    init_db(db)
    _insert_flow(db, method="DELETE", status=403)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 1

        status_cell = _find_cell_containing(table, "403")
        assert status_cell is not None, (
            "STATUS cell with '403' not found — row layout may have changed"
        )
        assert str(status_cell.style), (
            "STATUS cell style is empty — theme.STATUS_COLORS not applied. "
            "Did _add_flow_row lose its status_color() call?"
        )


@pytest.mark.asyncio
async def test_status_cell_carries_icon_from_theme(tmp_db):
    """STATUS column must include the status-class icon next to the code.

    This pins the second half of the Round-2 design spec: not only the
    colour but also the icon (2xx ✓, 3xx —, 4xx ⚠, 5xx 🔥) comes from
    ``theme.STATUS_ICONS``. If someone refactors ``status_icon()`` away
    this guard catches it even if the colour still applies.
    """
    db = str(tmp_db)
    init_db(db)
    _insert_flow(db, method="GET", status=500)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        status_cell = _find_cell_containing(table, "500")
        assert status_cell is not None
        # Icon for 5xx is 🔥 (U+1F525). We assert *some* non-digit glyph
        # follows the code rather than pinning U+1F525 exactly, so a future
        # icon swap in theme.py doesn't break the test.
        plain = status_cell.plain.strip()
        assert plain.startswith("500"), f"expected '500 <icon>', got {plain!r}"
        assert len(plain) > len("500"), (
            f"STATUS cell is just the code — theme.STATUS_ICONS not applied: {plain!r}"
        )
