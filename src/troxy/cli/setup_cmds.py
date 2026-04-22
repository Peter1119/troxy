"""troxy CLI — adoption commands: version, doctor, init."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.cli.setup_helpers import generate_ca_cert, print_device_hints


_EXAMPLE_PROMPTS = {
    "troxy_list_flows": '"방금 앱에서 난 401 요청 보여줘"',
    "troxy_get_flow": '"flow 42 response body 보여줘"',
    "troxy_search": '"access_token 들어간 요청 전부 찾아줘"',
    "troxy_export": '"이 요청 curl로 뽑아줘"',
    "troxy_mock_add": '"/api/users 엔드포인트에 mock 응답 걸어줘"',
    "troxy_mock_from_flow": '"아까 본 flow를 mock으로 만들어줘"',
    "troxy_intercept_add": '"POST 요청 가로채줘"',
}


@click.command("mcp-tools")
def mcp_tools_cmd():
    """List MCP tools with example prompts (useful before `troxy init`)."""
    from troxy.core.tool_catalog import TOOL_SCHEMAS
    click.echo(
        "troxy MCP exposes 17 tools to Claude Code. Register with `troxy init`, "
        "then ask Claude things like:\n"
    )
    for name, info in TOOL_SCHEMAS.items():
        example = _EXAMPLE_PROMPTS.get(name)
        click.echo(f"  {name}")
        click.echo(f"    {info['description']}")
        if example:
            click.echo(f"    예) {example}")
        click.echo()


@click.command("version")
def version_cmd():
    """Show troxy version and environment info."""
    try:
        from importlib.metadata import version as _pkg_version
        pkg_version = _pkg_version("troxy")
    except Exception:
        pkg_version = "unknown (dev)"

    click.echo(f"troxy {pkg_version}")
    click.echo(f"  Python: {sys.version.split()[0]} ({sys.executable})")
    click.echo(f"  DB:     {default_db_path()}")

    mitm = shutil.which("mitmproxy")
    click.echo(f"  mitmproxy: {mitm or 'not found'}")


@click.command("doctor")
def doctor_cmd():
    """Diagnose troxy setup. Checks mitmproxy, DB, cert, MCP."""
    ok = True

    def check(label, condition, hint=None):
        nonlocal ok
        if condition:
            click.echo(f"  ✓ {label}")
        else:
            click.echo(f"  ✗ {label}")
            if hint:
                click.echo(f"      → {hint}")
            ok = False

    click.echo("Checking troxy environment...\n")

    # 1. mitmproxy installed
    mitm = shutil.which("mitmproxy")
    venv_mitm = os.path.join(os.path.dirname(sys.executable), "mitmproxy")
    if os.path.exists(venv_mitm):
        mitm = venv_mitm
    check(
        f"mitmproxy installed ({mitm or 'missing'})",
        mitm is not None,
        "Install: `brew install mitmproxy` or `uv add mitmproxy`",
    )

    # 2. DB accessible
    db_path = default_db_path()
    try:
        init_db(db_path)
        conn = get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
        conn.close()
        check(f"DB ready at {db_path} ({count} flows)", True)
    except Exception as e:
        check(f"DB at {db_path}", False, f"Error: {e}")

    # 3. mitmproxy CA cert installed
    cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    check(
        f"mitmproxy CA cert at {cert_path}",
        cert_path.exists(),
        "Run `troxy onboard` to auto-generate the CA and (on macOS) trust it in the system keychain.",
    )

    # 4. troxy-mcp command available
    troxy_mcp = shutil.which("troxy-mcp")
    check(
        f"troxy-mcp command ({troxy_mcp or 'not on PATH'})",
        troxy_mcp is not None,
        "Reinstall via brew, or run `uv pip install -e .` in the project dir",
    )

    # 5. Claude CLI (optional but needed for `init`)
    claude = shutil.which("claude")
    if claude:
        click.echo(f"  ✓ Claude Code CLI ({claude})")
    else:
        click.echo("  ⚠ Claude Code CLI not found (optional — needed for `troxy init`)")

    click.echo()
    if ok:
        click.echo("All checks passed. Ready to capture flows.")
    else:
        click.echo("Some checks failed. Fix the ✗ items above.")
        sys.exit(1)


@click.command("onboard")
@click.option("--skip-trust", is_flag=True, help="Skip keychain trust step")
@click.option("--platform", default=None,
              type=click.Choice(["ios-sim", "android-emu", "manual"]),
              help="Target device platform for proxy config hints")
def onboard_cmd(skip_trust, platform):
    """Guided first-run setup: generate CA, trust it, print device proxy instructions.

    Folds what was previously three manual steps into one command.
    """
    click.echo("troxy onboard — guided setup\n")

    # Step 1: Ensure CA cert exists — generate automatically if missing
    ca = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    if not ca.exists():
        click.echo("Step 1/3: mitmproxy CA cert not found — generating now...")
        success, stderr = generate_ca_cert(ca)
        if not success:
            click.echo(f"  ✗ Failed to auto-generate CA at {ca}")
            lower = stderr.lower()
            if "address already in use" in lower or "bind" in lower:
                click.echo("      Port 19481 is in use. Check with `lsof -i :19481`, kill the blocker, retry.")
            elif stderr:
                click.echo(f"      mitmdump stderr: {stderr[:200]}")
            click.echo("      Fallback: run `troxy start` once, Ctrl+C, then rerun `troxy onboard`.")
            sys.exit(1)
        click.echo(f"  ✓ Step 1/3: CA cert generated at {ca}")
    else:
        click.echo(f"  ✓ Step 1/3: CA cert present at {ca}")

    # Step 2: Trust in macOS keychain
    if skip_trust:
        click.echo("  ⚠ Step 2/3: skipped (--skip-trust)")
    elif sys.platform != "darwin":
        click.echo(f"  ⚠ Step 2/3: auto-trust skipped (not macOS — {sys.platform})")
        click.echo(f"      Trust manually: open http://mitm.it from a proxied device")
    else:
        click.echo("  → Step 2/3: adding CA to macOS keychain (sudo required)")
        result = subprocess.run(
            ["sudo", "security", "add-trusted-cert", "-d",
             "-p", "ssl", "-p", "basic",
             "-k", "/Library/Keychains/System.keychain", str(ca)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            click.echo(f"  ✗ Trust failed: {result.stderr.strip()}")
            click.echo("      Fix manually: open http://mitm.it from a proxied device")
        else:
            click.echo("  ✓ Step 2/3: CA trusted in system keychain")

    # Step 3: Device proxy configuration
    click.echo("\nStep 3/3: configure your device/simulator proxy to 127.0.0.1:8080")
    print_device_hints(platform)

    click.echo(
        "\nDone. Run `troxy start` to capture flows, "
        "then `troxy flows` / `troxy explain <id>`.\n"
        "Bonus: run `troxy init` to let Claude Code query your flows via MCP.\n"
    )


@click.command("init")
@click.option("--scope", default="user",
              type=click.Choice(["user", "project", "local"]),
              help="Claude MCP scope (default: user)")
@click.option("--force", is_flag=True, help="Overwrite existing registration")
def init_cmd(scope, force):
    """Register troxy as a Claude Code MCP server (one-shot setup)."""
    claude = shutil.which("claude")
    if not claude:
        click.echo(
            "Claude Code CLI not found. Install from https://claude.com/claude-code",
            err=True,
        )
        sys.exit(1)

    db_env = f"TROXY_DB={default_db_path()}"
    args = [claude, "mcp", "add", "-e", db_env, "-s", scope, "troxy", "--", "troxy-mcp"]
    if force:
        # Remove first, ignore failure
        subprocess.run([claude, "mcp", "remove", "troxy", "-s", scope],
                       capture_output=True)

    click.echo(f"Registering troxy MCP server (scope={scope})...")
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(result.stderr or result.stdout, err=True)
        click.echo(
            "\nIf troxy is already registered, rerun with --force.",
            err=True,
        )
        sys.exit(1)

    click.echo(result.stdout.strip() or "Registered.")
    click.echo(
        "\nNext steps:\n"
        "  1. Run `troxy start` to launch mitmproxy with the troxy addon\n"
        "  2. Configure your app/device proxy to 127.0.0.1:8080\n"
        "  3. Ask Claude: \"troxy_status\" to confirm MCP works\n"
    )
