"""Strict QA: render every reachable screen and save SVG proof.

These tests exist because "unit tests pass" was the sign-off bar last round
and real `uv run troxy start` sessions were still broken (q didn't quit,
bottom bar was shoved off-screen, the local IP was wrong).

Each test here:

* drives a real ``TroxyStartApp`` through ``run_test``,
* navigates to a target screen (list / detail / copy modal / mock dialog /
  mock list / confirm dialog / toast),
* captures an SVG via ``qa_capture.capture_screen`` into
  ``docs/qa-screenshots/``.

A reviewer can open the SVG in any browser and see exactly what the terminal
would have rendered at size 120x40. When the design changes, the SVGs change
and the diff is part of the PR.

**These are not golden-file tests.** They do not fail on pixel drift -- the
design is still stabilising. They fail only if the capture blows up (missing
widget, layout overflow crash, etc), and they always write the SVG so the QA
engineer can eyeball it after each fix.
"""

from __future__ import annotations

import time

import pytest

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.app import TroxyStartApp

from tests.tui.qa_capture import capture_screen


TERMINAL_SIZE = (120, 40)


def _seed_variety(db: str) -> None:
    """Insert a handful of flows that exercise every status-code icon."""
    base = time.time() - 60
    rows = [
        ("GET", "api.example.com", "/api/v2/users/12345/ratings", 200, 45.0),
        ("GET", "api.example.com", "/api/v2/movies/99/reviews", 200, 120.0),
        ("POST", "auth.example.com", "/api/v2/auth/token", 201, 80.0),
        ("GET", "cdn.example.com", "/static/banner.jpg", 304, 12.0),
        ("GET", "graphql.example.com", "/graphql", 401, 15.0),
        ("DELETE", "api.example.com", "/api/v2/users/12345/session", 403, 20.0),
        ("GET", "api.example.com", "/api/v2/notifications", 500, 999.0),
    ]
    for i, (method, host, path, status, duration) in enumerate(rows):
        insert_flow(
            db,
            timestamp=base + i,
            method=method,
            scheme="https",
            host=host,
            port=443,
            path=path,
            query="page=1" if i == 0 else None,
            request_headers={"Accept": "application/json"},
            request_body=None if method == "GET" else '{"email":"a@b.com"}',
            request_content_type=None if method == "GET" else "application/json",
            status_code=status,
            response_headers={"Content-Type": "application/json"},
            response_body='{"ok": true, "index": %d}' % i,
            response_content_type="application/json",
            duration_ms=duration,
        )


@pytest.mark.asyncio
async def test_qa_snapshot_list_empty(tmp_db):
    """Empty DB: header should still show path · 0 flows, layout intact."""
    db = str(tmp_db)
    init_db(db)
    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        capture_screen(app, "list_empty")


@pytest.mark.asyncio
async def test_qa_snapshot_list_with_flows(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)
    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        capture_screen(app, "list_with_flows")


@pytest.mark.asyncio
async def test_qa_snapshot_list_filter_active(tmp_db):
    """Filter applied via the always-visible InlineFilter — rows narrow
    to the 4xx subset; the filter values stay visible in the top bar."""
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)

    from textual.widgets import Input
    from troxy.tui.inline_filter import InlineFilter

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        inline = app.screen.query_one(InlineFilter)
        inline.query_one("#inline-filter-status", Input).value = "4xx"
        await pilot.press("enter")
        await pilot.pause()
        capture_screen(app, "list_filter_4xx")


@pytest.mark.asyncio
async def test_qa_snapshot_detail_screen(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)

    from troxy.tui.detail_screen import DetailScreen
    from troxy.core.query import list_flows

    flows = list_flows(db)
    assert flows, "fixture must seed at least one flow"
    target_id = flows[0]["id"]

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(DetailScreen(db, target_id))
        await pilot.pause()
        capture_screen(app, "detail_response_focus")

        # Tab to request pane, capture the other focus style.
        await pilot.press("tab")
        await pilot.pause()
        capture_screen(app, "detail_request_focus")


@pytest.mark.asyncio
async def test_qa_snapshot_copy_modal(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)

    from troxy.tui.detail_screen import DetailScreen
    from troxy.core.query import list_flows

    flows = list_flows(db)
    target_id = flows[0]["id"]

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(DetailScreen(db, target_id))
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        capture_screen(app, "detail_copy_modal")


@pytest.mark.asyncio
async def test_qa_snapshot_mock_dialog(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)

    from troxy.core.query import list_flows, get_flow
    from troxy.tui.mock_dialog import MockDialog

    flows = list_flows(db)
    flow = get_flow(db, flows[0]["id"])

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(MockDialog(db, flow))
        await pilot.pause()
        capture_screen(app, "mock_dialog")


@pytest.mark.asyncio
async def test_qa_snapshot_mock_list(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)
    # Seed a couple of mock rules so the list isn't empty.
    from troxy.core.mock import add_mock_rule

    add_mock_rule(
        db,
        domain="api.example.com",
        path_pattern="/api/v2/users/*",
        method="GET",
        status_code=200,
        response_headers=None,
        response_body='{"ok": true}',
        name="users-200",
    )
    add_mock_rule(
        db,
        domain="auth.example.com",
        path_pattern="/api/v2/auth/token",
        method="POST",
        status_code=401,
        response_headers=None,
        response_body='{"error": "unauthorized"}',
        name="auth-401",
    )

    from troxy.tui.mock_list import MockListScreen

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        app.push_screen(MockListScreen(db))
        await pilot.pause()
        capture_screen(app, "mock_list")


@pytest.mark.asyncio
async def test_qa_snapshot_confirm_dialog(tmp_db):
    """Bug #2 regression guard — confirm dialog must not push bottom bar away."""
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)

    from troxy.tui.widgets import ConfirmDialog

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        app.screen.action_clear_all()
        await pilot.pause()
        dialog = app.screen.query_one("#confirm", ConfirmDialog)
        assert "visible" in dialog.classes
        capture_screen(app, "list_confirm_clear")


@pytest.mark.asyncio
async def test_qa_snapshot_toast(tmp_db):
    db = str(tmp_db)
    init_db(db)
    _seed_variety(db)

    from troxy.tui.widgets import Toast

    app = TroxyStartApp(db_path=db)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        app.screen.action_intercept_placeholder()
        await pilot.pause()
        toast = app.screen.query_one("#toast", Toast)
        assert "visible" in toast.classes
        capture_screen(app, "list_toast_intercept")
