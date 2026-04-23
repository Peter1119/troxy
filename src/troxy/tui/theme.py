"""Color palette and style constants for troxy TUI."""

STATUS_COLORS = {
    2: "green",
    3: "blue",
    4: "yellow",
    5: "red",
}

STATUS_ICONS = {
    2: "\u2713",
    3: "\u2014",
    4: "\u26a0",
    5: "\U0001f525",
}

METHOD_COLORS = {
    "GET": "green",
    "POST": "blue",
    "PUT": "#ff8800",
    "DELETE": "red",
    "PATCH": "cyan",
    "HEAD": "dim",
    "OPTIONS": "dim",
}

MOCK_ENABLED_ICON = "\u25cf"
MOCK_DISABLED_ICON = "\u25cb"

FOCUS_ACCENT = "\u2588"
SELECTION_MARKER = "\u25b6"


def status_color(code: int) -> str:
    """Return color name for HTTP status code."""
    return STATUS_COLORS.get(code // 100, "white")


def status_icon(code: int) -> str:
    """Return icon for HTTP status code."""
    return STATUS_ICONS.get(code // 100, "")


def method_color(method: str) -> str:
    """Return color name for HTTP method."""
    return METHOD_COLORS.get(method.upper(), "white")
