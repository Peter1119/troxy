"""SVG screenshot capture helpers for strict QA.

The previous v0.3 team marked features "done" based on unit-test PASS, but real
runs exposed q-key breakage, broken layout, wrong IP, and a bare list design.
This module gives the QA engineer a way to ship PROOF with every verdict:

* every screen that a user can reach is captured as an SVG
* screenshots land in ``docs/qa-screenshots/`` (tracked in git) so reviewers
  can diff the before / after without installing anything

Typical usage inside a pytest test::

    from tests.tui.qa_capture import capture_screen, QA_SCREENSHOT_DIR

    @pytest.mark.asyncio
    async def test_list_screen_snapshot(tmp_db):
        app = TroxyStartApp(db_path=str(tmp_db))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            capture_screen(app, "list_empty")

The file ends up at ``docs/qa-screenshots/list_empty.svg``.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App


QA_SCREENSHOT_DIR: Path = Path(__file__).resolve().parents[2] / "docs" / "qa-screenshots"


def capture_screen(app: App, name: str) -> Path:
    """Save ``app``'s current screen to ``docs/qa-screenshots/{name}.svg``.

    Args:
        app: A Textual ``App`` instance that is currently running (inside
            ``async with app.run_test()``). ``save_screenshot`` only works while
            the app is mounted; calling this outside ``run_test`` will raise.
        name: File stem (no extension). Use snake_case so directory listings
            stay readable: ``list_empty``, ``detail_response``, ``mock_dialog``.

    Returns:
        Absolute path to the saved SVG. The parent directory is created if
        missing so CI and fresh clones both Just Work.
    """
    QA_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{name}.svg"
    # save_screenshot wants path + filename separately and returns a string.
    saved = app.save_screenshot(filename=filename, path=str(QA_SCREENSHOT_DIR))
    return Path(saved)


def list_captured() -> list[Path]:
    """Return every SVG currently in the QA screenshot directory (sorted)."""
    if not QA_SCREENSHOT_DIR.exists():
        return []
    return sorted(QA_SCREENSHOT_DIR.glob("*.svg"))
