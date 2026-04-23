"""Manage mitmdump subprocess lifecycle."""

import os
import shutil
import signal
import subprocess
import sys
import time


# Wait for mitmdump to bind/fail after spawn so callers learn of port
# conflicts immediately instead of seeing a silent "paused" state.
_BOOT_WAIT_SECONDS = 1.5


class ProxyBootError(RuntimeError):
    """Raised when mitmdump exits during the boot window (e.g. port conflict)."""


class ProxyManager:
    def __init__(
        self,
        port: int = 8080,
        mode: str | None = None,
        db_path: str | None = None,
    ):
        self._port = port
        self._mode = mode
        self._db_path = db_path
        self._process: subprocess.Popen | None = None

    def _find_mitmdump(self) -> str | None:
        venv_bin = os.path.join(os.path.dirname(sys.executable), "mitmdump")
        if os.path.exists(venv_bin):
            return venv_bin
        return shutil.which("mitmdump")

    def _addon_path(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "addon.py",
        )

    def start(self) -> None:
        mitmdump = self._find_mitmdump()
        if not mitmdump:
            raise RuntimeError("mitmdump not found. Install: uv add mitmproxy")

        cmd = [mitmdump, "-s", self._addon_path(), "-p", str(self._port), "-q"]
        if self._mode:
            cmd.extend(["--mode", self._mode])

        env = os.environ.copy()
        if self._db_path:
            env["TROXY_DB"] = self._db_path

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        # Verify mitmdump actually bound the port — without this the TUI
        # launches in a silent "paused" state when port 8080 is already
        # taken by a stale mitmdump from a previous session.
        time.sleep(_BOOT_WAIT_SECONDS)
        if self._process.poll() is not None:
            stderr = b""
            if self._process.stderr is not None:
                try:
                    stderr = self._process.stderr.read() or b""
                except Exception:
                    pass
            msg = stderr.decode("utf-8", errors="replace").strip()
            detail = msg or f"mitmdump exited with code {self._process.returncode}"
            self._process = None
            raise ProxyBootError(
                f"Port {self._port} may be in use or mitmdump failed to start.\n"
                f"  detail: {detail}\n"
                f"  hint: `pgrep -lf mitmdump` 로 기존 프로세스 확인 후 kill"
            )

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def pause(self) -> None:
        """Stop the subprocess while keeping the port free for a later resume.

        Semantically distinct from ``stop()`` only from the UI's POV — the
        user can press ``p`` again to bring recording back without re-running
        ``troxy start``. Implementation re-uses ``stop()`` verbatim so the
        SIGTERM → wait → kill ladder stays in one place.
        """
        self.stop()

    def resume(self) -> None:
        """Re-spawn mitmdump on the same port. Idempotent when already running."""
        if self.running:
            return
        self.start()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None
