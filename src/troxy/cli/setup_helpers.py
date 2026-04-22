"""Helpers for onboard/doctor commands — kept out of setup_cmds.py to stay under the 300-line file-size cap."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import click


def generate_ca_cert(ca_path: Path, timeout: float = 8.0) -> tuple[bool, str]:
    """Boot mitmdump briefly so mitmproxy writes its CA cert, then stop it.

    Returns (success, stderr_tail). stderr is captured so the caller can
    surface bind errors (e.g. port 19481 already in use) to the user.
    """
    mitmdump = shutil.which("mitmdump")
    venv_mitmdump = os.path.join(os.path.dirname(sys.executable), "mitmdump")
    if os.path.exists(venv_mitmdump):
        mitmdump = venv_mitmdump
    if not mitmdump:
        return False, "mitmdump not found on PATH"

    ca_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [mitmdump, "--listen-port", "19481", "-q"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if ca_path.exists():
                return True, ""
            if proc.poll() is not None:
                break
            time.sleep(0.2)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    stderr = ""
    if proc.stderr is not None:
        try:
            stderr = proc.stderr.read().decode(errors="replace").strip()
        except Exception:
            stderr = ""
    return ca_path.exists(), stderr


_IOS_HINT = (
    "  iOS Simulator (macOS):\n"
    "    xcrun simctl boot 'iPhone 17'  # if not running\n"
    "    open -a Simulator\n"
    "    Settings → Wi-Fi → (i) → Configure Proxy → Manual\n"
    "        Server: 127.0.0.1   Port: 8080\n"
    "\n"
    "  Install CA on the Simulator (required for HTTPS interception):\n"
    "    1. Run `troxy start` in another terminal (keep it running)\n"
    "    2. Simulator → Safari → http://mitm.it → tap iOS → Allow download\n"
    "    3. Settings → General → VPN & Device Management → Install mitmproxy profile\n"
    "    4. Settings → General → About → Certificate Trust Settings → toggle mitmproxy ON\n"
)

_ANDROID_HINT = (
    "  Android Emulator:\n"
    "    emulator -avd <name> -http-proxy http://127.0.0.1:8080\n"
    "    Or in running emulator: Settings → Network → APN → Proxy\n"
    "\n"
    "  Install CA:\n"
    "    1. Visit http://mitm.it → download .cer file\n"
    "    2. Settings → Security → Install from storage\n"
    "  Android 7+ : app must trust user CAs via network_security_config.xml\n"
    '               (<trust-anchors><certificates src="user"/></trust-anchors>)\n'
    "  Android 14+: user CAs restricted for production-signed apps — debug build only\n"
)

_GENERIC_HINT = (
    "  Physical device:\n"
    "    Wi-Fi settings → HTTP proxy → Manual → 127.0.0.1 / 8080\n"
    "    Install CA from http://mitm.it while proxied\n"
)


def print_device_hints(platform: str | None) -> None:
    if platform == "ios-sim":
        click.echo(_IOS_HINT)
    elif platform == "android-emu":
        click.echo(_ANDROID_HINT)
    elif platform == "manual":
        click.echo(_GENERIC_HINT)
    else:
        click.echo(_IOS_HINT + "\n" + _ANDROID_HINT + "\n" + _GENERIC_HINT)
