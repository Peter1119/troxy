"""Tests for Bug #13 bottom-bar 3-line expansion.

Each unit test pins one piece of the contract. Mutation probe: change
the corresponding constant/branch in ``copy.py`` or ``list_screen.py``
and the matching test must FAIL.
"""

import pytest
from textual.app import App
from textual.widgets import Static

from troxy.core.db import init_db
from troxy.core.mock import add_mock_rule, toggle_mock_rule
from troxy.tui import copy
from troxy.tui.app import TroxyStartApp
from troxy.tui.list_screen import ListScreen


# ---------- Pure copy.py unit tests ----------


def test_ca_trust_url_constant():
    """Mutation probe: change CA_TRUST_URL → this test FAILs."""
    assert copy.CA_TRUST_URL == "http://mitm.it"


def test_proxy_info_line_contains_ip_port_and_ca_url():
    line = copy.proxy_info_line("192.168.0.56", 8080)
    assert "192.168.0.56:8080" in line
    assert "http://mitm.it" in line


def test_proxy_info_line_port_rendered_verbatim():
    """Non-default ports must render — pinning the `:port` template."""
    line = copy.proxy_info_line("10.0.0.1", 9999)
    assert ":9999" in line


def test_status_summary_line_recording_active():
    line = copy.status_summary_line(
        recording=True, flow_count=12, mock_count=3, mcp_enabled=False
    )
    assert "캡처 중" in line
    assert "12개 flow" in line
    assert "3개 mock" in line
    assert "MCP" not in line


def test_status_summary_line_paused_when_proxy_dead():
    """When the ProxyManager process is gone we must not lie to the user."""
    line = copy.status_summary_line(
        recording=False, flow_count=0, mock_count=0, mcp_enabled=False
    )
    assert "일시정지" in line
    assert "캡처 중" not in line


def test_status_summary_line_mcp_hint_appended():
    line = copy.status_summary_line(
        recording=True, flow_count=1, mock_count=0, mcp_enabled=True
    )
    assert "Claude" in line or "MCP" in line


def test_status_summary_line_mocks_uses_puzzle_icon(ark=None):
    """Bug #22 mutation probe: flip 🧩 back to 🎭 (or 🐎) and this FAILs.

    The 🎭 drama-masks glyph rendered as 🐎 (horse) in the user's
    terminal font; 🧩 is wider-covered across terminal fonts and
    stays visually tied to the mocks concept.
    """
    line = copy.status_summary_line(
        recording=True, flow_count=0, mock_count=2, mcp_enabled=False
    )
    assert "\U0001f9e9" in line, "mocks label must use 🧩 puzzle glyph"
    assert "\U0001f3ad" not in line, "stale 🎭 glyph must be gone"
    assert "\U0001f434" not in line, "stale 🐎 glyph must be gone"


# ---------- ListScreen integration tests ----------


def _make_app(db: str, **kw) -> TroxyStartApp:
    return TroxyStartApp(db_path=db, **kw)


@pytest.mark.asyncio
async def test_bottom_bar_proxy_line_contains_injected_port(tmp_db):
    """Port flows App → ListScreen and lands verbatim in #proxy-bar.

    Mutation probe: drop the port arg on the ListScreen constructor and
    this test FAILs — user would see the default 8080 regardless of
    --port.
    """
    db = str(tmp_db)
    init_db(db)
    app = _make_app(db, port=9999)
    async with app.run_test() as pilot:
        await pilot.pause()
        bar = app.screen.query_one("#proxy-bar", Static)
        assert "9999" in str(bar.render())
        assert "mitm.it" in str(bar.render())
        await pilot.press("q")


@pytest.mark.asyncio
async def test_bottom_bar_status_line_counts_only_enabled_mocks(tmp_db):
    """Disabled rules must not inflate the count.

    Mutation probe: pass ``enabled_only=False`` and the "1 mocks" assertion
    breaks (count becomes 2).
    """
    db = str(tmp_db)
    init_db(db)
    rid_a = add_mock_rule(
        db, domain="a.com", path_pattern="/", status_code=200, name="a"
    )
    rid_b = add_mock_rule(
        db, domain="b.com", path_pattern="/", status_code=200, name="b"
    )
    toggle_mock_rule(db, rid_b, enabled=False)
    # Sanity — one enabled, one disabled.
    _ = rid_a  # kept for readability

    app = _make_app(db)
    async with app.run_test() as pilot:
        await pilot.pause()
        info = app.screen.query_one("#info-bar", Static)
        text = str(info.render())
        assert "1개 mock" in text
        await pilot.press("q")


@pytest.mark.asyncio
async def test_bottom_bar_status_line_shows_recording_by_default(tmp_db):
    """proxy_running_fn defaults to ``True`` so tests that don't inject it
    still see a live recording state (matches the common case)."""
    db = str(tmp_db)
    init_db(db)
    app = _make_app(db)
    async with app.run_test() as pilot:
        await pilot.pause()
        info = app.screen.query_one("#info-bar", Static)
        assert "캡처 중" in str(info.render())
        await pilot.press("q")


@pytest.mark.asyncio
async def test_bottom_bar_status_line_shows_paused_when_proxy_fn_false(tmp_db):
    """Injected ProxyManager.running=False → bar shows paused."""
    db = str(tmp_db)
    init_db(db)
    app = _make_app(db, proxy_running_fn=lambda: False)
    async with app.run_test() as pilot:
        await pilot.pause()
        info = app.screen.query_one("#info-bar", Static)
        assert "일시정지" in str(info.render())
        await pilot.press("q")


@pytest.mark.asyncio
async def test_bottom_bar_has_three_distinct_widgets(tmp_db):
    """Spec pin: compose yields #hint-bar, #proxy-bar, #info-bar all present.

    Mutation probe: delete any of the three Static yields and this FAILs.
    """
    db = str(tmp_db)
    init_db(db)
    app = _make_app(db)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ListScreen)
        for wid in ("#hint-bar", "#proxy-bar", "#info-bar"):
            app.screen.query_one(wid, Static)  # raises if missing
        await pilot.press("q")
