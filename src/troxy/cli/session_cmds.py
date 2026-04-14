"""troxy session — project-scoped DB management.

Stores named DB paths in ~/.troxy/sessions.json (permissions 0600).
Switching sessions sets TROXY_DB via a small shell eval pattern.

Usage:
  troxy session save watcha-debug /tmp/watcha.db
  troxy session list
  troxy session use watcha-debug          # prints export command
  eval "$(troxy session use watcha-debug)"  # activates in current shell
"""

import json
import os
import stat
import sys
from pathlib import Path

import click

from troxy.core.db import default_db_path


def _sessions_file() -> Path:
    override = os.environ.get("TROXY_SESSIONS_FILE")
    if override:
        return Path(os.path.expanduser(override))
    return Path.home() / ".troxy" / "sessions.json"


def _load() -> dict:
    p = _sessions_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    p = _sessions_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    # Restrict to 0600 — may contain flow DB paths that hint at projects
    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)


@click.group("session")
def session_group():
    """Manage named troxy sessions (DB aliases)."""


@session_group.command("save")
@click.argument("name")
@click.argument("db_path", required=False)
def session_save_cmd(name: str, db_path: str | None):
    """Save current or explicit DB path under NAME.

    If DB_PATH is omitted, saves the currently-active DB (TROXY_DB or default).
    """
    if not name.replace("-", "").replace("_", "").isalnum():
        click.echo("Session name must be alphanumeric (with - or _).", err=True)
        sys.exit(1)
    if db_path is None:
        db_path = default_db_path()
    db_path = os.path.expanduser(db_path)
    data = _load()
    data[name] = db_path
    _save(data)
    click.echo(f"Session {name!r} → {db_path}")


@session_group.command("list")
def session_list_cmd():
    """List saved sessions."""
    data = _load()
    if not data:
        click.echo("No sessions saved. Try: troxy session save <name> <path>")
        return
    active = os.environ.get("TROXY_DB") or default_db_path()
    for name, path in sorted(data.items()):
        marker = " ← active" if os.path.expanduser(path) == active else ""
        click.echo(f"  {name:20} {path}{marker}")


@session_group.command("use")
@click.argument("name")
def session_use_cmd(name: str):
    """Print a shell command to activate a session.

    Usage: eval "$(troxy session use my-project)"
    """
    data = _load()
    if name not in data:
        click.echo(f"Session {name!r} not found. Run `troxy session list`.", err=True)
        sys.exit(1)
    # Emit shell command — caller must eval it
    click.echo(f'export TROXY_DB="{data[name]}"')


@session_group.command("remove")
@click.argument("name")
def session_remove_cmd(name: str):
    """Remove a saved session."""
    data = _load()
    if name not in data:
        click.echo(f"Session {name!r} not found.", err=True)
        sys.exit(1)
    del data[name]
    _save(data)
    click.echo(f"Session {name!r} removed.")
