"""InlineFilter — hidden-by-default 4-field filter (Round 7, Bug #19).

Round 5 landed an always-visible version which turned out to eat 3-4
vertical rows even when idle. User feedback: "항상 보이지 않아도 돼.
f 눌렀을때 보이고 거기에 입력하고 엔터누르면 적용하고 그런식이면 된다고 봐."

So Round 7 reverts the always-visible layout choice while keeping the
4-column editing UX. The widget is now hidden via ``display: none`` and
toggled into view by the ``.visible`` class — same pattern used by
``ConfirmDialog`` / ``Toast`` / ``CopyModal`` in ``widgets.py``.

Contract (pinned by ``tests/tui/test_inline_filter.py``):
  - Hidden by default (no ``.visible`` class on mount).
  - 5 Inputs in order: host, status, method, path, search. The trailing
    ``search`` field is a free-text matcher that hits body / headers / path.
  - Placeholders equal the field name verbatim — no truncation.
  - ``show()`` reveals the bar AND focuses the first (host) field.
  - ``hide()`` conceals the bar WITHOUT touching values — Round 7 Esc
    semantic: Esc is 'dismiss the editing UI', NOT 'clear the filter'.
  - Enter on ANY Input emits ``Submitted(filter_text)``; empty fields drop.
    Values persist across submits (the Inputs ARE the UI state).
  - ``clear_values()`` is used by ``x`` (clear all flows) so the filter
    row resets in lockstep with the table.
  - Focused Input gets an accent-coloured border so the active field is
    visually distinct from the others (Bug #21).
"""

from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input


FIELD_IDS: tuple[str, ...] = ("host", "status", "method", "path", "search")


class InlineFilter(Widget):
    """Horizontal 4-field filter bar toggled in/out by the parent screen.

    Emits ``Submitted(filter_text)`` on Enter in any field. The parent
    screen owns the ``f`` (show) and ``Esc`` (hide) bindings;
    InlineFilter stays a dumb form widget.
    """

    class Submitted(Message):
        def __init__(self, filter_text: str) -> None:
            self.filter_text = filter_text
            super().__init__()

    DEFAULT_CSS = """
    InlineFilter {
        display: none;
        height: 3;
        layout: horizontal;
        background: $panel;
        padding: 0 1;
    }
    InlineFilter.visible {
        display: block;
    }
    InlineFilter Input {
        width: 1fr;
        margin: 0 1 0 0;
    }
    InlineFilter Input:focus {
        border: tall $accent;
    }
    InlineFilter Input > .input--placeholder {
        color: $text 70%;
    }
    """

    def compose(self) -> ComposeResult:
        for fid in FIELD_IDS:
            yield Input(
                placeholder=fid,
                id=f"inline-filter-{fid}",
            )

    def show(self) -> None:
        """Reveal the bar and land focus on the first (host) field so
        the user can start typing without clicking. Called by the parent
        screen's ``f`` binding."""
        self.add_class("visible")
        self.focus_first()

    def hide(self) -> None:
        """Conceal the bar without touching any Input values.

        Round 7 semantic: hiding is NOT clearing. The parent screen
        calls this on Esc (dismiss edit UI) and on ``Submitted`` (apply
        + collapse). To clear the filter, the user empties the Inputs
        and presses Enter."""
        self.remove_class("visible")

    def focus_first(self) -> None:
        """Move focus to the first (host) field."""
        self.query_one(f"#inline-filter-{FIELD_IDS[0]}", Input).focus()

    def clear_values(self) -> None:
        """Wipe all 4 field values without emitting ``Submitted``.

        Called by the parent screen on ``x`` (clear all flows) so the
        filter row resets in lockstep with the table.
        """
        for fid in FIELD_IDS:
            self.query_one(f"#inline-filter-{fid}", Input).value = ""

    def build_filter_text(self) -> str:
        """Compose current values into the tokenised form.

        Example: with host="a.com" and status="4xx", returns
        ``"host:a.com status:4xx"``. Empty fields are dropped so
        ``core.filter_parser.parse_filter`` receives a clean string.
        ``search`` value joins as a free-text token (matches body / headers / path).
        """
        parts = []
        for fid in FIELD_IDS:
            value = self.query_one(
                f"#inline-filter-{fid}", Input
            ).value.strip()
            if not value:
                continue
            if fid == "search":
                parts.append(value)
            else:
                parts.append(f"{fid}:{value}")
        return " ".join(parts)

    @on(Input.Submitted)
    def _on_any_submit(self, event: Input.Submitted) -> None:
        """Enter on any field applies the whole form.

        The parent screen hides the bar after applying — this widget
        just posts the message and stays put.
        """
        event.stop()
        self.post_message(self.Submitted(self.build_filter_text()))
