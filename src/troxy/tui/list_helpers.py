"""Pure helpers for ListScreen: row construction, cursor marker, path truncation.

Extracted from ``list_screen.py`` so that screen module stays under the
300-line file-size cap. These functions have no ListScreen-specific state —
they take a DataTable and a flow dict and mutate the table.
"""

import time

from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from troxy.tui.theme import (
    SELECTION_MARKER,
    method_color,
    status_color,
    status_icon,
)


def truncate_path(path: str, max_len: int) -> str:
    """Shorten path with an ellipsis if it exceeds ``max_len``."""
    if len(path) <= max_len:
        return path
    return path[: max_len - 1] + "\u2026"


def time_header_label(newest_first: bool) -> Text:
    """TIME column header with sort-direction arrow.

    ``\u25bc`` = newest-first (descending by time); ``\u25b2`` = oldest-first.
    """
    arrow = "\u25bc" if newest_first else "\u25b2"
    return Text(f"TIME {arrow}")


def add_flow_row(
    table: DataTable, flow: dict, *, path_max_len: int = 40
) -> None:
    """Append one flow row to ``table`` with themed method/status cells.

    Re-renders the cursor marker so the visual cue stays on the current row
    after the insertion.
    """
    status = flow["status_code"]
    ts = time.strftime("%H:%M:%S", time.localtime(flow["timestamp"]))
    method = flow["method"]
    method_cell = Text(method, style=f"bold {method_color(method)}")
    status_cell = Text(
        f"{status} {status_icon(status)}",
        style=f"bold {status_color(status)}",
        justify="right",
    )
    id_cell = Text(str(flow["id"]), justify="right")
    table.add_row(
        "",  # marker column — filled in by update_cursor_marker
        id_cell,
        ts,
        method_cell,
        flow["host"],
        truncate_path(flow["path"], path_max_len),
        status_cell,
        key=str(flow["id"]),
    )
    update_cursor_marker(table)


def update_cursor_marker(table: DataTable) -> None:
    """Render ``SELECTION_MARKER`` in column 0 for the current cursor row only."""
    if table.row_count == 0:
        return
    cursor = table.cursor_row if table.cursor_row is not None else 0
    marker = Text(SELECTION_MARKER, style=f"bold {status_color(200)}")
    blank = Text(" ")
    for i in range(table.row_count):
        try:
            table.update_cell_at(
                Coordinate(i, 0),
                marker if i == cursor else blank,
                update_width=False,
            )
        except Exception:
            pass
