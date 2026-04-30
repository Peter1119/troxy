"""Strict QA: real-TTY key handling with pexpect.

The Textual ``run_test`` harness dispatches key events directly against the
App state machine. That is great for logic tests, but it does NOT prove that
a user typing ``q`` in iTerm/tmux actually exits the app -- that path runs
through the real terminal driver, which was the breakage that shipped last
round ("q doesn't quit").

These tests spawn the real app in a PTY (via ``pexpect``) and verify:

* the TUI mounts and becomes interactive
* keyboard shortcuts documented in ``docs/v0.3-manual-verification.md`` cause
  the process to exit when expected (``q``, ``Ctrl+C``)
* no orphan process is left behind

We launch ``TroxyStartApp`` *without* the mitmdump subprocess on purpose --
these tests are about the TUI keypath, not the proxy. Proxy subprocess
lifecycle is covered by ``tests/e2e``.

Tests are marked ``slow`` because spawning a PTY-backed Python subprocess
takes ~1s each; they are skipped automatically if pexpect is unavailable (as
on Windows CI).
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

import pytest

pexpect = pytest.importorskip("pexpect")


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"


# Tiny launcher that boots the TUI without the proxy subprocess. We use -c so
# we don't have to ship a dedicated fixture script in the package tree.
_LAUNCHER = (
    "import os, sys; "
    "sys.path.insert(0, {src!r}); "
    "from troxy.core.db import init_db; "
    "from troxy.tui.app import TroxyStartApp; "
    "db = os.environ['TROXY_TEST_DB']; "
    "init_db(db); "
    "TroxyStartApp(db_path=db).run()"
).format(src=str(SRC_DIR))


# Variant launcher that seeds a single flow so Enter has something to open.
_LAUNCHER_WITH_FLOW = (
    "import os, sys, time; "
    "sys.path.insert(0, {src!r}); "
    "from troxy.core.db import init_db; "
    "from troxy.core.store import insert_flow; "
    "from troxy.tui.app import TroxyStartApp; "
    "db = os.environ['TROXY_TEST_DB']; "
    "init_db(db); "
    "insert_flow(db, timestamp=time.time(), method='GET', scheme='https', "
    "host='example.com', port=443, path='/ttymarker', query=None, "
    "request_headers={{}}, request_body=None, request_content_type=None, "
    "status_code=200, response_headers={{}}, response_body='ok', "
    "response_content_type='text/plain', duration_ms=10.0); "
    "TroxyStartApp(db_path=db).run()"
).format(src=str(SRC_DIR))


def _spawn_tui_with_flow(db_path: str, cols: int = 150, rows: int = 40) -> "pexpect.spawn":
    """Spawn variant that seeds a single flow row before mounting the TUI.

    Required for Bug #5 (Enter → detail): an empty DataTable has no row to
    select, so RowSelected never fires and the detail screen can't prove it
    was reached.
    """
    env = os.environ.copy()
    env["TROXY_TEST_DB"] = db_path
    env["TERM"] = "xterm-256color"
    env.pop("NO_COLOR", None)

    child = pexpect.spawn(
        sys.executable,
        ["-c", _LAUNCHER_WITH_FLOW],
        env=env,
        encoding="utf-8",
        timeout=10,
        dimensions=(rows, cols),
    )
    child.expect(r"\x1b\[\?1049h", timeout=10)
    time.sleep(1.0)
    return child


def _spawn_tui(db_path: str, cols: int = 120, rows: int = 40) -> "pexpect.spawn":
    """Spawn the TUI in a PTY and wait until it is interactive.

    Textual interleaves every visible character with VT escape sequences,
    which makes a plain regex search for ``"troxy"`` unreliable (you end up
    matching against the alt-screen enter sequence rather than the title).

    We instead wait for the alternate-screen enter sequence (``\\x1b[?1049h``)
    which Textual emits as the *first* action on startup — that's a rock
    solid signal that the app has mounted and is ready for input.
    """
    env = os.environ.copy()
    env["TROXY_TEST_DB"] = db_path
    env["TERM"] = "xterm-256color"
    # Disable color / fancy features that confuse pexpect's matcher.
    env.pop("NO_COLOR", None)

    python = sys.executable
    child = pexpect.spawn(
        python,
        ["-c", _LAUNCHER],
        env=env,
        encoding="utf-8",
        timeout=10,
        dimensions=(rows, cols),
    )
    # Alt-screen enter: definitive "TUI is up" marker.
    child.expect(r"\x1b\[\?1049h", timeout=10)
    # Let a few frames paint so bindings + focus are registered.
    time.sleep(1.0)
    return child


def _terminate(child: "pexpect.spawn") -> None:
    """Best-effort cleanup so a hanging TUI doesn't wedge the suite."""
    if child.isalive():
        try:
            child.kill(9)
        except Exception:
            pass
    child.close(force=True)


@pytest.mark.slow
def test_real_tty_q_key_exits(tmp_path):
    """Bug #1 regression: pressing ``q`` in a real PTY must exit the app."""
    db = str(tmp_path / "qa.db")
    child = _spawn_tui(db)
    try:
        child.send("q")
        # Allow up to 5s for Textual to unmount and the process to exit.
        child.expect(pexpect.EOF, timeout=5)
        child.wait()
        assert child.exitstatus == 0, (
            f"q should exit cleanly, got exitstatus={child.exitstatus} "
            f"signalstatus={child.signalstatus}"
        )
    finally:
        _terminate(child)


@pytest.mark.slow
def test_real_tty_ctrl_c_exits(tmp_path):
    """Ctrl+C must terminate the TUI — covers the SIGINT path too."""
    db = str(tmp_path / "qa.db")
    child = _spawn_tui(db)
    try:
        child.sendcontrol("c")
        child.expect(pexpect.EOF, timeout=5)
        child.wait()
        # Textual converts Ctrl+C into a clean app.exit(); both 0 and being
        # signalled count as "gone", but we prefer the clean exit.
        assert not child.isalive()
    finally:
        _terminate(child)


@pytest.mark.slow
def test_real_tty_does_not_exit_on_unbound_key(tmp_path):
    """Sanity: a random letter must NOT close the app.

    If this test fails it usually means a default binding is swallowing
    keys that should be no-ops (e.g. ``z`` being bound to quit by accident).
    """
    db = str(tmp_path / "qa.db")
    child = _spawn_tui(db)
    try:
        child.send("z")
        time.sleep(1.0)
        assert child.isalive(), "unbound key 'z' caused the TUI to exit"
    finally:
        child.send("q")
        try:
            child.expect(pexpect.EOF, timeout=5)
        except pexpect.TIMEOUT:
            pass
        _terminate(child)


@pytest.mark.slow
def test_real_tty_filter_then_escape_then_quit(tmp_path):
    """End-to-end keypath: f → filter text → Enter → Esc → q.

    This is the exact sequence a user followed when they reported ``q`` not
    quitting: after opening and dismissing the filter, focus used to linger
    on the Input widget and swallow ``q``. Covering it in a real PTY prevents
    the regression from sneaking back.
    """
    db = str(tmp_path / "qa.db")
    child = _spawn_tui(db)
    try:
        child.send("f")
        time.sleep(0.3)
        child.send("status:2xx")
        child.send("\r")  # Enter
        time.sleep(0.3)
        child.send("\x1b")  # Escape
        time.sleep(0.3)
        child.send("q")
        child.expect(pexpect.EOF, timeout=5)
        child.wait()
        assert child.exitstatus == 0, (
            "q after filter/esc must still exit — "
            f"exitstatus={child.exitstatus}"
        )
    finally:
        _terminate(child)


@pytest.mark.slow
def test_real_tty_enter_opens_detail_screen(tmp_path):
    """Bug #5 regression: in a real PTY, Enter on a focused DataTable must
    route to DetailScreen (via RowSelected handler), not be swallowed.

    Proof: after Enter we should see DetailScreen-only rendering — the
    ``── Request ──`` pane header. If the handler is missing, Enter does
    nothing on ListScreen and this expect() times out.

    Note: we don't attempt Esc→q cleanup here because DetailScreen's focus
    model swallows single-byte ESC in pexpect-driven TTY (terminal waits
    for a CSI sequence completion). Exit path is covered by other tests.
    """
    db = str(tmp_path / "qa.db")
    child = _spawn_tui_with_flow(db)
    try:
        child.send("\r")  # Enter
        # DetailScreen renders "── 요청 ──" in the request pane.
        # pexpect can match across VT escape bytes for contiguous characters.
        child.expect("요청", timeout=5)
    finally:
        _terminate(child)


@pytest.mark.slow
def test_real_tty_detail_escape_returns_to_list(tmp_path):
    """Bug #7 regression: Esc on a focused DetailScreen must pop back to
    ListScreen in a real PTY. Previously Textual's ``Screen._key_escape``
    ran ``clear_selection()`` and masked the ``escape → go_back`` binding;
    ``DetailScreen.key_escape`` now re-routes escape to ``action_go_back``.

    We send ``\\x1b\\x1b`` (double-Escape) to defeat the terminal's CSI
    completion timeout on a bare Esc byte — a single ESC sits in the input
    queue waiting for a potential CSI continuation and never reaches the
    app. Double-Esc forces the first byte to resolve as a completed key.

    Signal: after go_back the ListScreen renders ``LIST_HINT`` which
    contains the word ``필터``. If the fix is removed, DetailScreen
    stays mounted and ``필터`` never appears → this expect() times out.
    """
    db = str(tmp_path / "qa.db")
    child = _spawn_tui_with_flow(db)
    try:
        child.send("\r")  # Enter → DetailScreen
        child.expect("요청", timeout=5)
        child.send("\x1b\x1b")  # Double ESC → forces key resolution
        child.expect("필터", timeout=5)
    finally:
        _terminate(child)


@pytest.mark.slow
def test_real_tty_detail_escape_back_then_quit(tmp_path):
    """Enter → Esc → q must succeed even with an empty list (no-op Enter)."""
    if shutil.which(sys.executable) is None:
        pytest.skip("python executable not discoverable")
    db = str(tmp_path / "qa.db")
    child = _spawn_tui(db)
    try:
        child.send("\r")  # Enter — with no rows, this is a no-op.
        time.sleep(0.3)
        child.send("\x1b")  # Esc
        time.sleep(0.3)
        child.send("q")
        child.expect(pexpect.EOF, timeout=5)
        child.wait()
        assert child.exitstatus == 0
    finally:
        _terminate(child)
