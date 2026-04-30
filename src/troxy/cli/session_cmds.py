"""troxy session — project-scoped DB management.

Stores named DB paths in ~/.troxy/sessions.json (permissions 0600).
Switching sessions sets TROXY_DB via a small shell eval pattern.

Usage:
  troxy session save api-debug /tmp/api.db
  troxy session list
  troxy session use api-debug          # prints export command
  eval "$(troxy session use api-debug)"  # activates in current shell
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
    """이름 있는 troxy 세션(DB 별칭)을 관리합니다."""


@session_group.command("save")
@click.argument("name")
@click.argument("db_path", required=False)
def session_save_cmd(name: str, db_path: str | None):
    """현재 또는 지정한 DB 경로를 NAME으로 저장합니다.

    DB_PATH를 생략하면 현재 활성 DB(TROXY_DB 또는 기본값)를 저장합니다.
    """
    if not name.replace("-", "").replace("_", "").isalnum():
        click.echo("세션 이름은 영숫자 (- 또는 _ 포함)여야 합니다.", err=True)
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
    """저장된 세션 목록을 출력합니다."""
    data = _load()
    if not data:
        click.echo("저장된 세션이 없습니다. 사용: troxy session save <이름> <경로>")
        return
    active = os.environ.get("TROXY_DB") or default_db_path()
    for name, path in sorted(data.items()):
        marker = " ← 활성" if os.path.expanduser(path) == active else ""
        click.echo(f"  {name:20} {path}{marker}")


@session_group.command("use")
@click.argument("name")
def session_use_cmd(name: str):
    """세션 활성화 셸 명령을 출력합니다.

    사용: eval "$(troxy session use my-project)"
    """
    data = _load()
    if name not in data:
        click.echo(f"세션 {name!r}을 찾을 수 없습니다. `troxy session list` 실행", err=True)
        sys.exit(1)
    # Emit shell command — caller must eval it
    click.echo(f'export TROXY_DB="{data[name]}"')


@session_group.command("remove")
@click.argument("name")
def session_remove_cmd(name: str):
    """저장된 세션을 삭제합니다."""
    data = _load()
    if name not in data:
        click.echo(f"세션 {name!r}을 찾을 수 없습니다.", err=True)
        sys.exit(1)
    del data[name]
    _save(data)
    click.echo(f"세션 {name!r} 삭제됨.")
