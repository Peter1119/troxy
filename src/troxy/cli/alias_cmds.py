"""troxy alias — save and run frequently-used filter presets.

Example:
  troxy alias add auth "flows -s 401"
  troxy alias add slow "flows --since 5m"
  troxy auth                          # runs `troxy flows -s 401`

Aliases are stored in ~/.troxy/aliases.json (overridable via TROXY_ALIAS_FILE).
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import click


_RESERVED_NAMES = {
    "flows", "flow", "search", "tail", "status", "clear", "start", "version",
    "doctor", "init", "mock", "intercept", "pending", "modify", "release",
    "drop", "replay", "quick", "explain", "alias", "onboard", "mcp-tools",
    "session", "pick",
}


def _alias_file() -> Path:
    override = os.environ.get("TROXY_ALIAS_FILE")
    if override:
        return Path(os.path.expanduser(override))
    return Path.home() / ".troxy" / "aliases.json"


def _load() -> dict:
    p = _alias_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    p = _alias_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


@click.group("alias", invoke_without_command=True)
@click.pass_context
def alias_group(ctx):
    """Manage command aliases (list if no subcommand)."""
    if ctx.invoked_subcommand is None:
        data = _load()
        if not data:
            click.echo("No aliases defined. Try: troxy alias add auth \"flows -s 401\"")
            return
        for name, cmd in sorted(data.items()):
            click.echo(f"  {name} → troxy {cmd}")


@alias_group.command("add")
@click.argument("name")
@click.argument("command")
def alias_add_cmd(name: str, command: str):
    """Add or replace an alias.

    NAME is the alias shortname. COMMAND is the troxy subcommand + args as a single string.
    Example: troxy alias add auth "flows -s 401 --no-color"
    """
    if name in _RESERVED_NAMES:
        click.echo(
            f"'{name}' is a built-in command name. Pick a different alias.",
            err=True,
        )
        sys.exit(1)
    if not name.replace("-", "").replace("_", "").isalnum():
        click.echo("Alias name must be alphanumeric (with - or _).", err=True)
        sys.exit(1)
    data = _load()
    data[name] = command
    _save(data)
    click.echo(f"Alias '{name}' → troxy {command}")


@alias_group.command("remove")
@click.argument("name")
def alias_remove_cmd(name: str):
    """Remove an alias."""
    data = _load()
    if name not in data:
        click.echo(f"Alias '{name}' not found.", err=True)
        sys.exit(1)
    del data[name]
    _save(data)
    click.echo(f"Alias '{name}' removed.")


@alias_group.command("run")
@click.argument("name")
@click.argument("extra", nargs=-1)
def alias_run_cmd(name: str, extra: tuple):
    """Run an alias by name (optional extra args appended)."""
    data = _load()
    if name not in data:
        click.echo(f"Alias '{name}' not found. Run `troxy alias` to list.", err=True)
        sys.exit(1)
    argv = shlex.split(data[name]) + list(extra)
    # Re-invoke the troxy CLI as a subprocess for isolation
    cmd = [sys.executable, "-m", "troxy.cli.main"] + argv
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def resolve_alias_invocation(argv: list[str]) -> list[str] | None:
    """If argv[0] is a known alias, return expanded argv; else None.

    Called from main CLI dispatcher to short-circuit before click parsing.
    """
    if not argv:
        return None
    data = _load()
    first = argv[0]
    if first in data and first not in _RESERVED_NAMES:
        return shlex.split(data[first]) + argv[1:]
    return None
