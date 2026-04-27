"""All user-facing text -- hints, toasts, labels. Single source of truth."""

# -- List View hints --
LIST_HINT = (
    "\u2191\u2193 browse \u00b7 \u23ce detail \u00b7 f filter"
    " \u00b7 m mock \u00b7 M mocks \u00b7 s sort \u00b7 p pause"
    " \u00b7 x clear \u00b7 q quit"
)

# -- Detail View hints --
DETAIL_HINT = (
    "\u2190\u2192 switch tab \u00b7 \u2191\u2193 scroll \u00b7 y copy"
    " \u00b7 u copy url \u00b7 m mock \u00b7 c curl \u00b7 Esc"
)

# -- Mock List hints --
MOCK_LIST_HINT = (
    "\u2191\u2193 browse \u00b7 Space toggle"
    " \u00b7 \u23ce edit \u00b7 a add \u00b7 d delete \u00b7 Esc back"
)

# -- Copy modal options --
COPY_OPTIONS = [
    ("1", "URL"),
    ("2", "Request (full)"),
    ("3", "Response (full)"),
    ("4", "Response body only"),
    ("5", "as curl"),
    ("6", "as HTTPie"),
]


# -- Filter status --
def filter_status_text(summary: str) -> str:
    """Compact status line shown in ``#filter-status`` when a filter is
    applied but the edit bar is hidden (Round 7).

    Prefixed with 🔍 so the active state is unambiguous; the trailing
    ``f to edit`` hint directs the user back to the edit bar. Under
    Round 7 semantics, Esc only HIDES the bar and does NOT reset the
    filter, so the old ``Esc to reset`` copy was removed to avoid
    contradicting the new keybinding.
    """
    return f"\U0001f50d filter: {summary}  \u00b7  f to edit"


# -- Toast messages --
def toast_copied(what: str, size_bytes: int) -> str:
    """Toast after copying content to clipboard."""
    if size_bytes < 1024:
        size = f"{size_bytes}b"
    else:
        size = f"{size_bytes / 1024:.1f}KB"
    return f"\u2713 copied: {what} ({size})"


def toast_mock_saved(name: str) -> str:
    """Toast after saving a mock rule."""
    return f"\u2713 mock saved: {name} (enabled)"


def toast_mock_deleted(name: str) -> str:
    """Toast after deleting a mock rule."""
    return f"\u2713 mock deleted: {name}"


def toast_cleared(count: int) -> str:
    """Toast after clearing all flows."""
    return f"\u2713 {count} flows cleared"


def toast_intercept_placeholder() -> str:
    """Toast for intercept feature placeholder."""
    return "intercept live edit \u2014 coming in v0.4"


# -- Confirm messages --
def confirm_clear(count: int) -> str:
    """Confirm dialog text for clearing all flows."""
    return f"\uc804\uccb4 {count}\uac1c flow\ub97c \uc0ad\uc81c\ud569\ub2c8\ub2e4. \ud655\uc778? [y/N]"


def confirm_mock_delete(name: str) -> str:
    """Confirm dialog text for deleting a mock rule."""
    return f"mock '{name}' \uc0ad\uc81c\ud560\uae4c\uc694? [y/N]"


# -- Info bar --
def info_bar(ip: str, mcp_registered: bool) -> str:
    """Bottom info bar with local IP and optional MCP hint.

    Kept for callers that want the compact single-line fallback; the
    primary list screen now uses the 3-line layout
    (``proxy_info_line`` + ``status_summary_line``).
    """
    parts = [f"\U0001f4e1 {ip}"]
    if mcp_registered:
        parts.append("\U0001f4a1 ask Claude via MCP")
    return "  \u00b7  ".join(parts)


# -- Bottom-bar line 2: proxy info --
CA_TRUST_URL = "http://mitm.it"


def proxy_info_line(ip: str, port: int) -> str:
    """Line 2 of the bottom bar: proxy endpoint + CA trust URL.

    The port is the one the local mitmdump is listening on; pairing it
    with ``mitm.it`` keeps the two pieces a user needs for device setup
    in one glance.
    """
    return (
        f"\U0001f4e1 Proxy: {ip}:{port}"
        f"  \u00b7  \U0001f510 CA: {CA_TRUST_URL}"
    )


# -- Bottom-bar line 3: live status summary --
def status_summary_line(
    recording: bool,
    flow_count: int,
    mock_count: int,
    mcp_enabled: bool,
) -> str:
    """Line 3 of the bottom bar: recording state, live counters, optional MCP hint.

    Parts are joined with ``  \u00b7  `` and only populated parts are shown, so the
    line stays compact when MCP is off.
    """
    state = "\U0001f534 recording" if recording else "\u23f8 paused"
    parts = [
        f"{state} ({flow_count} flows)",
        f"\U0001f9e9 {mock_count} mocks",
    ]
    if mcp_enabled:
        parts.append("\U0001f4a1 ask Claude via MCP")
    return "  \u00b7  ".join(parts)


# -- Header --
def _shorten_db_path(db_path: str, max_len: int = 48) -> str:
    """Shorten a filesystem path for display in the header.

    Rules (applied in order):
      1. Replace the user's home directory prefix with ``~``.
      2. If still longer than ``max_len``, keep the first segment and the
         last two segments, eliding the middle with ``\u2026``.
    """
    import os

    home = os.path.expanduser("~")
    shown = db_path
    if shown.startswith(home):
        shown = "~" + shown[len(home):]

    if len(shown) <= max_len:
        return shown

    parts = shown.split("/")
    if len(parts) <= 3:
        return shown[: max_len - 1] + "\u2026"

    # Preserve whether the path was absolute so we don't double the leading "/".
    head = parts[0] if parts[0] else ""
    tail = "/".join(parts[-2:])
    prefix = head if head else "/"
    candidate = f"{prefix}/\u2026/{tail}" if head else f"/\u2026/{tail}"
    if len(candidate) <= max_len:
        return candidate
    # Last resort — keep the filename only.
    return "\u2026/" + parts[-1][: max_len - 2]


def header_text(db_path: str, flow_count: int) -> str:
    """Header text with DB path and flow count."""
    return f"{_shorten_db_path(db_path)} \u00b7 {flow_count:,} flows"
