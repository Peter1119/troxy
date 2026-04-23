"""Widget-level tests for InlineFilter (Round 5 Bug #14, Round 7 Bug #19).

These pin the widget's public contract in isolation plus the ListScreen
integration points (f/Enter/Esc/x wiring).

Mutation probes (verify each test catches the matching regression):
  - Reorder FIELD_IDS → test_field_order FAILs
  - Rename a placeholder → test_placeholders_match_field_names FAILs
  - Clear Input.value on submit → test_values_persist_after_submit FAILs
  - Drop ``display: none`` from DEFAULT_CSS → test_hidden_by_default FAILs
  - Drop ``add_class('visible')`` in show() → test_f_press_reveals_bar FAILs
  - Drop ``inline.hide()`` on submit → test_enter_hides_bar FAILs
  - Make Esc call clear_values() → test_esc_preserves_filter_state FAILs
"""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from troxy.tui.inline_filter import FIELD_IDS, InlineFilter


class _Harness(App):
    """Minimal host so InlineFilter mounts inside a real Textual app.

    The widget messages bubble up to this App, which we intercept via
    ``on_inline_filter_submitted`` to inspect the payload.
    """

    def __init__(self) -> None:
        super().__init__()
        self.submitted: list[str] = []

    def compose(self) -> ComposeResult:
        yield InlineFilter(id="inline-filter")

    def on_inline_filter_submitted(
        self, event: InlineFilter.Submitted
    ) -> None:
        self.submitted.append(event.filter_text)


@pytest.mark.asyncio
async def test_four_inputs_mounted():
    """Mutation probe: remove a field from FIELD_IDS → count drops to 3."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        inputs = list(widget.query(Input))
        assert len(inputs) == 4


@pytest.mark.asyncio
async def test_hidden_by_default():
    """Bug #19: widget mounts without the ``visible`` class.

    Mutation probe: add ``self.add_class('visible')`` in compose — this
    test FAILs (the bar would eat 3 vertical rows on mount).
    """
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        assert "visible" not in widget.classes


@pytest.mark.asyncio
async def test_show_adds_visible_class_and_hide_removes_it():
    """Mutation probe: drop ``add_class('visible')`` from show() — this FAILs.

    Also pins that hide() is the inverse: removes the class without
    touching Input values.
    """
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        widget.show()
        await pilot.pause()
        assert "visible" in widget.classes
        widget.hide()
        await pilot.pause()
        assert "visible" not in widget.classes


@pytest.mark.asyncio
async def test_hide_preserves_input_values():
    """Round 7 semantic: hide() must NOT clear values.

    Mutation probe: change hide() to call clear_values() — this FAILs.
    """
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        widget.query_one("#inline-filter-host", Input).value = "keep.me"
        widget.show()
        await pilot.pause()
        widget.hide()
        await pilot.pause()
        assert (
            widget.query_one("#inline-filter-host", Input).value == "keep.me"
        )


@pytest.mark.asyncio
async def test_field_order_host_status_method_path():
    """Stable order matters for Tab navigation — pin it here."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        ids = [inp.id for inp in widget.query(Input)]
        assert ids == [
            "inline-filter-host",
            "inline-filter-status",
            "inline-filter-method",
            "inline-filter-path",
        ]


@pytest.mark.asyncio
async def test_placeholders_match_field_names():
    """Placeholders act as the visible labels — any drift is a UX regression."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        placeholders = {inp.id: inp.placeholder for inp in widget.query(Input)}
        assert placeholders == {
            "inline-filter-host": "host",
            "inline-filter-status": "status",
            "inline-filter-method": "method",
            "inline-filter-path": "path",
        }


@pytest.mark.asyncio
async def test_build_filter_text_drops_empty_fields():
    """Empty fields must NOT emit ``host: status:`` noise."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        widget.query_one("#inline-filter-host", Input).value = "example.com"
        widget.query_one("#inline-filter-status", Input).value = "4xx"
        assert widget.build_filter_text() == "host:example.com status:4xx"


@pytest.mark.asyncio
async def test_build_filter_text_all_four_fields():
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        widget.query_one("#inline-filter-host", Input).value = "a.com"
        widget.query_one("#inline-filter-status", Input).value = "200"
        widget.query_one("#inline-filter-method", Input).value = "POST"
        widget.query_one("#inline-filter-path", Input).value = "/api/*"
        assert (
            widget.build_filter_text()
            == "host:a.com status:200 method:POST path:/api/*"
        )


@pytest.mark.asyncio
async def test_build_filter_text_empty_returns_empty_string():
    """No fields filled → empty string (parser treats as 'no filter')."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        assert widget.build_filter_text() == ""


@pytest.mark.asyncio
async def test_enter_in_any_field_submits_current_values():
    """Enter in ``status`` field still submits the whole form."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        widget.query_one("#inline-filter-host", Input).value = "a.com"
        status_input = widget.query_one("#inline-filter-status", Input)
        status_input.value = "401"
        status_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.submitted == ["host:a.com status:401"]


@pytest.mark.asyncio
async def test_values_persist_after_submit():
    """Unlike FilterForm.hide(), InlineFilter must NOT clear values on submit.

    Mutation probe: add ``self.clear_values()`` after post_message and this
    assertion FAILs — the user-visible 'what am I filtered on' cue disappears.
    """
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        host_input = widget.query_one("#inline-filter-host", Input)
        host_input.value = "a.com"
        host_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # The field still shows the filter the user applied.
        assert host_input.value == "a.com"


@pytest.mark.asyncio
async def test_clear_values_wipes_all_four():
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        for fid in FIELD_IDS:
            widget.query_one(f"#inline-filter-{fid}", Input).value = "x"
        widget.clear_values()
        for fid in FIELD_IDS:
            assert (
                widget.query_one(f"#inline-filter-{fid}", Input).value == ""
            )


@pytest.mark.asyncio
async def test_focus_first_points_to_host():
    """Parent screen's ``f`` binding calls focus_first() — it must land on
    the leftmost (host) field, not whichever was focused last."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#inline-filter", InlineFilter)
        # Land somewhere else first.
        widget.query_one("#inline-filter-path", Input).focus()
        await pilot.pause()
        widget.focus_first()
        await pilot.pause()
        assert app.focused is widget.query_one(
            "#inline-filter-host", Input
        )


# ---------- ListScreen integration (Round 5 final, Bug #14) ----------
#
# The 4 tests below verify the pipeline: InlineFilter widget → ListScreen
# compose → ``f`` / Enter / ``x`` key wiring → table refresh. Each test
# names a mutation probe so a reviewer can confirm the regression catch.


@pytest.mark.asyncio
async def test_inline_filter_in_list_screen_compose(tmp_db):
    """Mutation probe: delete ``yield InlineFilter(...)`` from ListScreen
    compose → this test FAILs (widget missing).

    Also pins Round 7 composition: InlineFilter present but hidden by
    default, #filter-status Static present but inactive.
    """
    from textual.widgets import Static
    from troxy.core.db import init_db
    from troxy.tui.app import TroxyStartApp

    db = str(tmp_db)
    init_db(db)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        matches = list(app.screen.query(InlineFilter))
        assert len(matches) == 1
        inline = matches[0]
        for fid in FIELD_IDS:
            inline.query_one(f"#inline-filter-{fid}", Input)
        # Round 7: bar hidden on mount (no ``visible`` class).
        assert "visible" not in inline.classes
        # Round 7: filter-status Static is back but inactive (no filter yet).
        status = app.screen.query_one("#filter-status", Static)
        assert "active" not in status.classes
        # Old FilterForm infrastructure must stay gone.
        assert not list(app.screen.query("#filter-form"))
        await pilot.press("q")


@pytest.mark.asyncio
async def test_f_key_reveals_and_focuses_host_input(tmp_db):
    """Bug #19 mutation probe: replace ``show()`` with ``focus_first()`` in
    action_show_filter → widget stays hidden, ``visible`` class missing,
    and this test FAILs.
    """
    from textual.widgets import Input
    from troxy.core.db import init_db
    from troxy.tui.app import TroxyStartApp

    db = str(tmp_db)
    init_db(db)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        assert "visible" not in inline.classes
        await pilot.press("f")
        await pilot.pause()
        # f must BOTH reveal AND land focus on host.
        assert "visible" in inline.classes
        assert app.focused is inline.query_one(
            "#inline-filter-host", Input
        )
        await pilot.press("q")


@pytest.mark.asyncio
async def test_inline_filter_enter_applies_filter_to_table(tmp_db):
    """Mutation probe: drop ``on_inline_filter_submitted`` from
    ListScreen → this test FAILs because the table stays at row_count=2
    after Enter.

    This also exercises the full pipeline:
      press f → focus host → type → focus status → type → Enter →
      InlineFilter.Submitted bubbles → ListScreen applies filter →
      _refresh_table_with_filter narrows the DataTable.
    """
    import time as _time
    from textual.widgets import DataTable, Input
    from troxy.core.db import init_db
    from troxy.core.store import insert_flow
    from troxy.tui.app import TroxyStartApp

    db = str(tmp_db)
    init_db(db)
    # Two flows differing only in status, so status-filter narrows to 1.
    for status in (200, 401):
        insert_flow(
            db, timestamp=_time.time(), method="GET", scheme="https",
            host="example.com", port=443, path="/a", query=None,
            request_headers={}, request_body=None,
            request_content_type=None, status_code=status,
            response_headers={}, response_body="x",
            response_content_type="text/plain", duration_ms=1.0,
        )
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#flow-table", DataTable)
        assert table.row_count == 2
        # Round 7: press f first to reveal the bar before typing.
        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        status_input = inline.query_one("#inline-filter-status", Input)
        status_input.value = "4xx"
        status_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert table.row_count == 1, (
            "Enter in a focused InlineFilter Input must narrow the table"
        )
        # Round 7 regression: Enter must also hide the editing bar.
        assert "visible" not in inline.classes, (
            "Enter must collapse the editing bar after applying the filter"
        )
        await pilot.press("q")


@pytest.mark.asyncio
async def test_x_clear_also_resets_inline_filter_values(tmp_db):
    """Mutation probe: remove the ``clear_values()`` call from
    ``_clear_table`` → this test FAILs; stale "4xx" would still sit in
    the status Input and silently filter the next recording session.
    """
    import time as _time
    from textual.widgets import Input
    from troxy.core.db import init_db
    from troxy.core.store import insert_flow
    from troxy.tui.app import TroxyStartApp
    from troxy.tui.widgets import ConfirmDialog

    db = str(tmp_db)
    init_db(db)
    insert_flow(
        db, timestamp=_time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/a", query=None,
        request_headers={}, request_body=None,
        request_content_type=None, status_code=401,
        response_headers={}, response_body="x",
        response_content_type="text/plain", duration_ms=1.0,
    )
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        inline.query_one("#inline-filter-status", Input).value = "4xx"
        # x → confirm dialog → confirm → _clear_table fires
        app.screen.action_clear_all()
        await pilot.pause()
        dialog = app.screen.query_one("#confirm", ConfirmDialog)
        assert "visible" in dialog.classes
        dialog.action_confirm()
        await pilot.pause()
        # Post-clear: InlineFilter values must be wiped.
        for fid in FIELD_IDS:
            val = inline.query_one(f"#inline-filter-{fid}", Input).value
            assert val == "", (
                f"'x' clear-all must also wipe InlineFilter field "
                f"{fid!r}, got {val!r}"
            )
        await pilot.press("q")


def test_default_css_has_focus_accent_border():
    """Bug #21 mutation probe: delete the ``Input:focus`` block from
    InlineFilter.DEFAULT_CSS → this test FAILs.

    Visual contract: the focused Input must get an accent-coloured
    border so the user knows which field is active. Snapshot tests in
    ``test_qa_snapshots.py`` cover the rendered glyphs; this test pins
    the CSS rule string against accidental deletion during refactors.
    """
    css = InlineFilter.DEFAULT_CSS
    assert "Input:focus" in css
    assert "$accent" in css.split("Input:focus")[1].split("}")[0]


def test_default_css_has_placeholder_contrast_rule():
    """Bug #20 mutation probe: remove the ``.input--placeholder`` rule
    from DEFAULT_CSS → this test FAILs.

    The default Textual placeholder colour is low-contrast against the
    ``$panel`` background; the 70%-opacity override lifts it enough to
    be legible without competing with typed values.
    """
    css = InlineFilter.DEFAULT_CSS
    assert ".input--placeholder" in css
    assert "$text 70%" in css


# ---------- Round 7 / Bug #19 regression tests ----------


@pytest.mark.asyncio
async def test_esc_hides_bar_without_clearing_filter(tmp_db):
    """Bug #19 Round 7 semantic: Esc is 'dismiss editing UI', NOT 'clear filter'.

    Mutation probe: restore the old semantic by making action_clear_filter
    also reset ``self._active_filter = ""`` + call ``inline.clear_values()``
    → this test FAILs (table widens back and host value wipes).
    """
    import time as _time
    from textual.widgets import DataTable, Input
    from troxy.core.db import init_db
    from troxy.core.store import insert_flow
    from troxy.tui.app import TroxyStartApp

    db = str(tmp_db)
    init_db(db)
    for status in (200, 401):
        insert_flow(
            db, timestamp=_time.time(), method="GET", scheme="https",
            host="example.com", port=443, path="/a", query=None,
            request_headers={}, request_body=None,
            request_content_type=None, status_code=status,
            response_headers={}, response_body="x",
            response_content_type="text/plain", duration_ms=1.0,
        )

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
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

        # Re-show the bar, then invoke Esc-action.
        await pilot.press("f")
        await pilot.pause()
        assert "visible" in inline.classes
        app.screen.action_clear_filter()
        await pilot.pause()

        assert "visible" not in inline.classes, "Esc must hide the bar"
        assert table.row_count == 1, (
            "Round 7: Esc does NOT clear the filter — table must stay narrowed"
        )
        assert status_input.value == "4xx", (
            "Round 7: Esc must preserve Input values; user clears by "
            "emptying + Enter or pressing x"
        )
        await pilot.press("q")


@pytest.mark.asyncio
async def test_empty_submit_clears_filter(tmp_db):
    """Round 7: 'how to clear' — user empties all 4 Inputs and presses Enter.

    Mutation probe: break this path (e.g., ignore empty submits) and the
    user has no way to clear short of ``x`` (which also nukes flows).
    """
    import time as _time
    from textual.widgets import DataTable, Input
    from troxy.core.db import init_db
    from troxy.core.store import insert_flow
    from troxy.tui.app import TroxyStartApp

    db = str(tmp_db)
    init_db(db)
    for status in (200, 401):
        insert_flow(
            db, timestamp=_time.time(), method="GET", scheme="https",
            host="example.com", port=443, path="/a", query=None,
            request_headers={}, request_body=None,
            request_content_type=None, status_code=status,
            response_headers={}, response_body="x",
            response_content_type="text/plain", duration_ms=1.0,
        )

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
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

        # Now clear: reveal, empty the Input, press Enter.
        await pilot.press("f")
        await pilot.pause()
        status_input.value = ""
        status_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert table.row_count == 2, (
            "Empty-submit must reset the filter and restore all rows"
        )
        await pilot.press("q")


@pytest.mark.asyncio
async def test_filter_status_bar_activates_on_submit_and_clears_on_empty(tmp_db):
    """Bug #19 filter-summary: ``#filter-status`` Static gets the
    ``active`` class + summary text when a filter is applied, and loses
    both when the filter is cleared.

    Mutation probe: drop ``self._refresh_filter_status()`` from
    ``on_inline_filter_submitted`` → summary never appears (FAIL).
    Mutation probe: drop the ``remove_class('active')`` branch → stale
    summary sticks around after the user clears the filter (FAIL).
    """
    import time as _time
    from textual.widgets import Input, Static
    from troxy.core.db import init_db
    from troxy.core.store import insert_flow
    from troxy.tui.app import TroxyStartApp

    db = str(tmp_db)
    init_db(db)
    insert_flow(
        db, timestamp=_time.time(), method="GET", scheme="https",
        host="example.com", port=443, path="/a", query=None,
        request_headers={}, request_body=None,
        request_content_type=None, status_code=401,
        response_headers={}, response_body="x",
        response_content_type="text/plain", duration_ms=1.0,
    )

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        status_static = app.screen.query_one("#filter-status", Static)
        assert "active" not in status_static.classes

        # Apply filter.
        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        host_input = inline.query_one("#inline-filter-host", Input)
        host_input.value = "example.com"
        host_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert "active" in status_static.classes
        rendered = str(status_static.render())
        assert "host:example.com" in rendered
        assert "f to edit" in rendered

        # Clear via empty-submit.
        await pilot.press("f")
        await pilot.pause()
        host_input.value = ""
        host_input.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert "active" not in status_static.classes, (
            "filter-status must lose .active when the filter is cleared"
        )
        await pilot.press("q")
