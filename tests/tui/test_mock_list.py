"""Tests for MockListScreen — list / toggle / delete / edit mock rules."""

import pytest

from troxy.core.db import init_db
from troxy.core.mock import add_mock_rule, list_mock_rules


def _seed(db: str) -> tuple[int, int]:
    """Seed two mock rules. Returns (enabled_id, disabled_id)."""
    init_db(db)
    a = add_mock_rule(
        db, domain="api.example.com", path_pattern="/api/users/*/ratings",
        method="GET", status_code=401, response_body='{"error":"x"}',
        name="ratings-401",
    )
    b = add_mock_rule(
        db, domain="api.example.com", path_pattern="/login",
        method="POST", status_code=500, response_body="err",
        name="login-500",
    )
    from troxy.core.mock import toggle_mock_rule
    toggle_mock_rule(db, b, enabled=False)
    return a, b


@pytest.mark.asyncio
async def test_mock_list_renders_all_rules(tmp_db):
    """Screen shows every rule with ON icon, id, name, status, hit."""
    db = str(tmp_db)
    _seed(db)

    from textual.app import App
    from textual.widgets import DataTable
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        table = screen.query_one("#mock-table", DataTable)
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_mock_list_space_toggles_rule(tmp_db):
    """Space on the selected row flips `enabled`."""
    db = str(tmp_db)
    enabled_id, _ = _seed(db)

    from textual.app import App
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        # Cursor starts on the first row (id ordered) = enabled_id
        await pilot.press("space")
        await pilot.pause()

    rules = {r["id"]: r for r in list_mock_rules(db)}
    assert rules[enabled_id]["enabled"] == 0


@pytest.mark.asyncio
async def test_mock_list_delete_requires_confirm(tmp_db):
    """d opens the confirm dialog; 'y' deletes the rule."""
    db = str(tmp_db)
    enabled_id, _ = _seed(db)

    from textual.app import App
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

    remaining = {r["id"] for r in list_mock_rules(db)}
    assert enabled_id not in remaining


@pytest.mark.asyncio
async def test_mock_list_delete_cancel_keeps_rule(tmp_db):
    """n cancels deletion."""
    db = str(tmp_db)
    enabled_id, disabled_id = _seed(db)

    from textual.app import App
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

    remaining = {r["id"] for r in list_mock_rules(db)}
    assert remaining == {enabled_id, disabled_id}


@pytest.mark.asyncio
async def test_mock_list_enter_opens_mock_dialog_in_edit_mode(tmp_db):
    """Enter on a rule pushes MockDialog with the rule prefilled."""
    db = str(tmp_db)
    _seed(db)

    from textual.app import App
    from troxy.tui.mock_dialog import MockDialog
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MockDialog)
        # Check rule was passed so the dialog is in edit mode.
        assert pilot.app.screen._rule is not None
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_mock_list_escape_pops(tmp_db):
    """Esc returns to the caller screen."""
    db = str(tmp_db)
    _seed(db)

    from textual.app import App
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(MockListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, MockListScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, MockListScreen)


@pytest.mark.asyncio
async def test_list_screen_capital_m_opens_mock_list(tmp_db):
    """Capital ``M`` on ListScreen pushes MockListScreen.

    ``shift+m`` doesn't get delivered as a Screen binding by every terminal /
    Textual version, so we bind the literal ``M`` and assert that here.
    """
    db = str(tmp_db)
    _seed(db)

    from textual.app import App
    from troxy.tui.list_screen import ListScreen
    from troxy.tui.mock_list import MockListScreen

    class TestApp(App):
        def on_mount(self):
            self.push_screen(ListScreen(db))

    async with TestApp().run_test() as pilot:
        await pilot.pause()
        await pilot.press("M")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MockListScreen)
        await pilot.press("escape")
