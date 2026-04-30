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
    """명령 별칭을 관리합니다 (하위 명령 없이 실행 시 목록 출력)."""
    if ctx.invoked_subcommand is None:
        data = _load()
        if not data:
            click.echo("등록된 별칭이 없습니다. 사용 예: troxy alias add auth \"flows -s 401\"")
            return
        for name, cmd in sorted(data.items()):
            click.echo(f"  {name} → troxy {cmd}")


@alias_group.command("add")
@click.argument("name")
@click.argument("command")
def alias_add_cmd(name: str, command: str):
    """별칭을 추가하거나 교체합니다.

    NAME은 별칭 단축명, COMMAND는 troxy 하위 명령 + 인자를 하나의 문자열로 지정합니다.
    예: troxy alias add auth "flows -s 401 --no-color"
    """
    if name in _RESERVED_NAMES:
        click.echo(
            f"'{name}'은 내장 명령 이름입니다. 다른 별칭을 사용하세요.",
            err=True,
        )
        sys.exit(1)
    if not name.replace("-", "").replace("_", "").isalnum():
        click.echo("별칭 이름은 영숫자 (- 또는 _ 포함)여야 합니다.", err=True)
        sys.exit(1)
    data = _load()
    data[name] = command
    _save(data)
    click.echo(f"Alias '{name}' → troxy {command}")


@alias_group.command("remove")
@click.argument("name")
def alias_remove_cmd(name: str):
    """별칭을 삭제합니다."""
    data = _load()
    if name not in data:
        click.echo(f"별칭 '{name}'을 찾을 수 없습니다.", err=True)
        sys.exit(1)
    del data[name]
    _save(data)
    click.echo(f"별칭 '{name}' 삭제됨.")


@alias_group.command("run")
@click.argument("name")
@click.argument("extra", nargs=-1)
def alias_run_cmd(name: str, extra: tuple):
    """이름으로 별칭을 실행합니다 (추가 인자 선택)."""
    data = _load()
    if name not in data:
        click.echo(f"별칭 '{name}'을 찾을 수 없습니다. `troxy alias` 실행하여 목록 확인", err=True)
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
