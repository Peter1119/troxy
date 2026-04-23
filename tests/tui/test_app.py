import pytest
from troxy.tui.app import TroxyStartApp


@pytest.mark.asyncio
async def test_app_launches(tmp_db):
    db = str(tmp_db)
    from troxy.core.db import init_db
    init_db(db)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        assert app.title == "troxy"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_ctrl_c_quits_app(tmp_db):
    """Regression: Textual 8.x binds ctrl+c to `action_help_quit` (display
    only) by default. TroxyStartApp overrides it to `action_quit` at the
    App level so real users can interrupt the TUI with Ctrl+C.
    """
    db = str(tmp_db)
    from troxy.core.db import init_db
    init_db(db)

    app = TroxyStartApp(db_path=db)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert not app.is_running
        assert app.return_code == 0
