import time
from unittest.mock import patch, MagicMock

import pytest

from troxy.tui.proxy import ProxyManager


def test_find_mitmdump():
    pm = ProxyManager(port=8080)
    path = pm._find_mitmdump()
    assert path is not None
    assert "mitmdump" in path


def test_proxy_start_stop():
    pm = ProxyManager(port=18080)
    pm.start()
    # Give mitmdump time to bind (or fail fast on port conflict / missing deps).
    # 2s with settled re-check is more tolerant under CI / full-suite parallel load.
    time.sleep(2)
    assert pm.running, "mitmdump subprocess did not stay alive after 2s"
    pm.stop()
    assert not pm.running


def test_proxy_passes_db_path_via_env():
    """ProxyManager must propagate db_path as TROXY_DB env to mitmdump."""
    pm = ProxyManager(port=18081, db_path="/tmp/custom.db")
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    with patch("troxy.tui.proxy.subprocess.Popen", return_value=fake_proc) as popen:
        pm.start()
    env = popen.call_args.kwargs["env"]
    assert env["TROXY_DB"] == "/tmp/custom.db"


def test_proxy_without_db_path_does_not_set_env():
    """Absent db_path leaves TROXY_DB inherited from parent env (no override)."""
    pm = ProxyManager(port=18082)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    with patch("troxy.tui.proxy.subprocess.Popen", return_value=fake_proc) as popen:
        pm.start()
    env = popen.call_args.kwargs["env"]
    # Child env should be a copy of parent env (not forcing TROXY_DB).
    # If parent had no TROXY_DB, child also shouldn't.
    import os
    if "TROXY_DB" in os.environ:
        assert env["TROXY_DB"] == os.environ["TROXY_DB"]
    else:
        assert "TROXY_DB" not in env


# ---------- Bug #15: pause / resume cycle ----------


def test_proxy_pause_invokes_stop_path():
    """Mutation probe: if ``pause()`` stops delegating to ``stop()`` (e.g. no
    SIGTERM, no process detach) this contract breaks.

    We verify that pause() on a running proxy sends SIGTERM, waits, and
    clears ``_process`` — i.e. the real stop ladder.
    """
    pm = ProxyManager(port=18090)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None  # pretend alive until stop() runs
    with patch("troxy.tui.proxy.subprocess.Popen", return_value=fake_proc):
        pm.start()
    assert pm.running
    pm.pause()
    fake_proc.send_signal.assert_called_once()
    fake_proc.wait.assert_called_once()
    assert pm._process is None
    assert not pm.running


def test_proxy_pause_is_idempotent_when_not_running():
    """Calling ``pause()`` on a never-started manager is a no-op, not a crash.

    Matches the UI's "press p twice" tolerance — user should not observe
    any error if they hit p before the proxy has even spawned.
    """
    pm = ProxyManager(port=18091)
    assert not pm.running
    pm.pause()  # must not raise
    assert not pm.running


def test_proxy_resume_is_idempotent_when_already_running():
    """``resume()`` on a running manager does NOT spawn a second subprocess.

    Mutation probe: remove the ``if self.running: return`` guard and this
    test FAILs — Popen would be called twice → orphan mitmdump process.
    """
    pm = ProxyManager(port=18092)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    with patch("troxy.tui.proxy.subprocess.Popen", return_value=fake_proc) as popen:
        pm.start()
        pm.resume()  # should NOT start a second subprocess
    assert popen.call_count == 1


def test_proxy_resume_after_pause_respawns_on_same_port():
    """pause → resume must reuse the original port (no 'paused port is lost').

    Mutation probe 1: if ``resume()`` drops ``self.start()`` the mock Popen
    is never called the second time → call_count==1 → this FAILs.
    Mutation probe 2: if ``__init__`` forgets to persist ``port`` on the
    instance, the second Popen command string would not contain the port.
    """
    pm = ProxyManager(port=18093)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    with patch("troxy.tui.proxy.subprocess.Popen", return_value=fake_proc) as popen:
        pm.start()
        pm.pause()
        # After pause, fake_proc was wait()ed — reset to simulate a fresh start.
        fake_proc.poll.return_value = None
        pm.resume()
    assert popen.call_count == 2, "resume() must re-invoke Popen exactly once"
    # Both invocations must target the same port via the "-p <port>" CLI args.
    for call in popen.call_args_list:
        cmd = call.args[0]
        assert "-p" in cmd, f"start command missing -p flag: {cmd}"
        assert str(18093) in cmd, f"start command missing port 18093: {cmd}"


@pytest.mark.slow
def test_proxy_real_pause_resume_cycle():
    """End-to-end: start → pause → running=False → resume → running=True.

    Exercises the real SIGTERM path and real mitmdump re-spawn. Slow
    because we need the first process to settle, die, and a fresh one to
    bind the port again. Port 28094 is far from the 180xx range used by
    sibling tests so we don't collide with mitmdump sockets still in
    TIME_WAIT from earlier cases in the same run.
    """
    pm = ProxyManager(port=28094)
    pm.start()
    try:
        time.sleep(3)
        assert pm.running, "mitmdump did not stay alive after initial start"
        pm.pause()
        assert not pm.running, "pause() must stop the subprocess"
        pm.resume()
        time.sleep(3)
        assert pm.running, "resume() must re-spawn mitmdump on the same port"
    finally:
        pm.stop()
    assert not pm.running
