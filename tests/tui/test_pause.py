"""Tests for Bug #15 — ``p`` key manual pause/resume, ListScreen integration.

ProxyManager.pause() / .resume() lifecycle is covered in ``test_proxy.py``.
This file pins the UI integration: ``p`` binding, toggle direction, and
the immediate status-bar refresh so the user sees the state flip the
same frame (not on the next 5 s tick).

User ask (verbatim): "p로 하고 기본은 recording이야".

Mutation probes (each test catches its match):
  - Flip the ``if running`` branch in ``action_toggle_pause`` → the two
    ``test_p_key_calls_*_when_*`` tests FAIL (wrong callable invoked).
  - Delete the trailing ``_refresh_status_bar()`` call →
    ``test_p_key_refreshes_status_bar_immediately`` FAILs (bar stays
    "recording" until the 5 s interval).
  - Remove ``p pause`` from ``copy.LIST_HINT`` → ``test_list_hint_*`` FAILs
    and the keybind becomes invisible to new users.
"""

from unittest.mock import MagicMock

import pytest
from textual.widgets import Static

from troxy.core.db import init_db
from troxy.tui.app import TroxyStartApp


@pytest.mark.asyncio
async def test_p_key_calls_pause_when_running(tmp_db):
    """Default state = recording (running_fn → True); p must invoke pause_fn."""
    db = str(tmp_db)
    init_db(db)
    running = [True]
    pause_fn = MagicMock(
        side_effect=lambda: running.__setitem__(0, False)
    )
    resume_fn = MagicMock()
    app = TroxyStartApp(
        db_path=db,
        proxy_running_fn=lambda: running[0],
        proxy_pause_fn=pause_fn,
        proxy_resume_fn=resume_fn,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert pause_fn.call_count == 1
        assert resume_fn.call_count == 0
        await pilot.press("q")


@pytest.mark.asyncio
async def test_p_key_calls_resume_when_paused(tmp_db):
    """When proxy is already stopped, p must call resume_fn (not pause_fn)."""
    db = str(tmp_db)
    init_db(db)
    running = [False]
    pause_fn = MagicMock()
    resume_fn = MagicMock(
        side_effect=lambda: running.__setitem__(0, True)
    )
    app = TroxyStartApp(
        db_path=db,
        proxy_running_fn=lambda: running[0],
        proxy_pause_fn=pause_fn,
        proxy_resume_fn=resume_fn,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert resume_fn.call_count == 1
        assert pause_fn.call_count == 0
        await pilot.press("q")


@pytest.mark.asyncio
async def test_p_key_refreshes_status_bar_immediately(tmp_db):
    """After p, the #info-bar must flip to ``paused`` the same frame.

    Mutation probe: remove the trailing ``self._refresh_status_bar()`` from
    ``action_toggle_pause`` → bar stays "recording" until the 5 s interval,
    this assertion FAILs.
    """
    db = str(tmp_db)
    init_db(db)
    running = [True]
    app = TroxyStartApp(
        db_path=db,
        proxy_running_fn=lambda: running[0],
        proxy_pause_fn=lambda: running.__setitem__(0, False),
        proxy_resume_fn=lambda: running.__setitem__(0, True),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        info = app.screen.query_one("#info-bar", Static)
        assert "recording" in str(info.render())
        await pilot.press("p")
        await pilot.pause()
        assert "paused" in str(info.render())
        assert "recording" not in str(info.render())
        await pilot.press("q")


@pytest.mark.asyncio
async def test_p_key_toggle_round_trip(tmp_db):
    """p → paused → p → recording; the bar must track both transitions."""
    db = str(tmp_db)
    init_db(db)
    running = [True]
    app = TroxyStartApp(
        db_path=db,
        proxy_running_fn=lambda: running[0],
        proxy_pause_fn=lambda: running.__setitem__(0, False),
        proxy_resume_fn=lambda: running.__setitem__(0, True),
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        info = app.screen.query_one("#info-bar", Static)
        assert "paused" in str(info.render())
        await pilot.press("p")
        await pilot.pause()
        assert "recording" in str(info.render())
        await pilot.press("q")


@pytest.mark.asyncio
async def test_list_hint_advertises_p_pause(tmp_db):
    """User discoverability: the bottom hint must mention ``p pause``.

    Mutation probe: revert copy.LIST_HINT to pre-Bug-#15 → this test FAILs
    and the keybind becomes invisible to new users.
    """
    db = str(tmp_db)
    init_db(db)
    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        hint = app.screen.query_one("#hint-bar", Static)
        assert "p pause" in str(hint.render())
        await pilot.press("q")
