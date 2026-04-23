"""TroxyStartApp — main Textual application."""

from typing import Callable

from textual.app import App
from textual.binding import Binding

from troxy.tui.list_screen import ListScreen


class TroxyStartApp(App):
    """troxy start TUI application."""

    TITLE = "troxy"
    CSS_PATH = None

    BINDINGS = [
        # Textual 8.x binds ctrl+c to `help_quit` (notify-only) by default.
        # Re-declaring it on our App replaces that default so Ctrl+C quits.
        Binding("ctrl+c", "quit", "quit", show=False),
    ]

    def __init__(
        self,
        db_path: str | None = None,
        *,
        port: int = 8080,
        mcp_registered: bool = False,
        proxy_running_fn: Callable[[], bool] | None = None,
        proxy_pause_fn: Callable[[], None] | None = None,
        proxy_resume_fn: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._port = port
        self._mcp_registered = mcp_registered
        self._proxy_running_fn = proxy_running_fn
        self._proxy_pause_fn = proxy_pause_fn
        self._proxy_resume_fn = proxy_resume_fn

    def on_mount(self) -> None:
        self.push_screen(
            ListScreen(
                self._db_path,
                port=self._port,
                mcp_registered=self._mcp_registered,
                proxy_running_fn=self._proxy_running_fn,
                proxy_pause_fn=self._proxy_pause_fn,
                proxy_resume_fn=self._proxy_resume_fn,
            )
        )
