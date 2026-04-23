"""Textual CSS constants for screens. Kept out of screen modules to
keep each screen's Python source under the 300-line file-size cap."""

DETAIL_SCREEN_CSS = """
#url-bar {
    height: auto;
    background: $panel;
    color: $text;
    padding: 0 1;
}
#tab-bar {
    height: 1;
    background: $panel-darken-2;
    padding: 0 1;
}
#request-container, #response-container {
    height: 1fr;
    background: $surface;
}
.hidden {
    display: none;
}
.pane {
    overflow-y: scroll;
    padding: 0 1;
}
#hint-bar {
    height: 1;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
}
"""

LIST_SCREEN_CSS = """
#header {
    height: 1;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
}
#flow-table {
    height: 1fr;
    background: $surface;
}
#flow-table > .datatable--header {
    background: $panel-darken-1;
    color: $accent;
    text-style: bold;
}
#flow-table > .datatable--cursor {
    background: #1e4e8f;
    color: #ffffff;
    text-style: bold;
}
#flow-table > .datatable--hover {
    background: $boost;
}
#filter-status {
    display: none;
    height: 1;
    background: $panel-darken-1;
    color: $accent;
    padding: 0 1;
}
#filter-status.active {
    display: block;
}
#hint-bar {
    height: 1;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
}
#proxy-bar {
    height: 1;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
}
#info-bar {
    height: 1;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
}
"""
