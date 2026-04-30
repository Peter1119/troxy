"""troxy CLI — scenario (scripted mock) subcommands."""

import json
import sys

import click

from troxy.core.db import init_db
from troxy.cli.utils import _resolve_db, _apply_no_color


def _parse_steps(steps_str: str) -> list[dict]:
    """Parse steps from JSON array or inline comma-separated status codes.

    Inline: "200,500,503" → [{"status_code": 200}, {"status_code": 500}, ...]
    JSON:   '[{"status_code": 200}, ...]'
    """
    if not steps_str or not steps_str.strip():
        raise ValueError("--steps cannot be empty")
    s = steps_str.strip()
    if s.startswith("["):
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in --steps: {e}") from e
    # Inline comma-separated status codes
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        raise ValueError("--steps cannot be empty")
    try:
        return [{"status_code": int(p)} for p in parts]
    except ValueError:
        raise ValueError(f"Inline --steps must be comma-separated status codes (e.g. '200,500'), got: {s!r}")


@click.group("scenario")
def scenario_group():
    """시나리오 mock 규칙을 관리합니다."""


@scenario_group.command("add")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("-d", "--domain", default=None, help="매칭할 도메인")
@click.option("-p", "--path", "path_pattern", default=None, help="경로 glob 패턴")
@click.option("-m", "--method", default=None, help="매칭할 HTTP 메서드")
@click.option(
    "-s", "--steps", "steps_json", required=True,
    help="단계 객체 JSON 배열, 예: '[{\"status_code\":200},{\"status_code\":500}]'",
)
@click.option("--loop", is_flag=True, default=False,
              help="마지막 단계 후 1단계로 순환 (기본: 마지막 단계 반복)")
@click.option("--name", default=None, help="편리한 참조를 위한 이름")
def scenario_add_cmd(db, domain, path_pattern, method, steps_json, loop, name):
    """순차 응답 시나리오 mock 규칙을 추가합니다."""
    from troxy.core.scenarios import add_scenario
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        steps = _parse_steps(steps_json)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    try:
        sid = add_scenario(
            db_path,
            domain=domain,
            path_pattern=path_pattern,
            method=method,
            name=name,
            steps=steps,
            loop=loop,
        )
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    label = f"{sid} ({name!r})" if name else str(sid)
    click.echo(f"시나리오 규칙 {label} 추가됨.")


@scenario_group.command("list")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("--no-color", is_flag=True, help="색상 출력 비활성화")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
def scenario_list_cmd(db, no_color, as_json):
    """시나리오 mock 규칙 목록을 출력합니다."""
    from troxy.core.scenarios import list_scenarios
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    scenarios = list_scenarios(db_path)
    if as_json:
        click.echo(json.dumps(scenarios, indent=2, ensure_ascii=False, default=str))
        return
    if not scenarios:
        click.echo("시나리오 규칙이 없습니다.")
        return
    for s in scenarios:
        name_label = f" '{s['name']}'" if s.get("name") else ""
        status_label = "enabled" if s["enabled"] else "disabled"
        loop_label = "loop=on" if s.get("loop") else "loop=off"
        step_label = f"step {s['current_step'] + 1}/{s['total_steps']}"
        match_parts = [x for x in [s.get("domain"), s.get("path_pattern"), s.get("method")] if x]
        match_label = " ".join(match_parts) if match_parts else "*"
        click.echo(
            f"[{s['id']}]{name_label} {match_label}  {step_label}  {loop_label}  {status_label}"
        )


@scenario_group.command("remove")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def scenario_remove_cmd(db, rule_ref):
    """ID 또는 이름으로 시나리오 규칙을 삭제합니다."""
    from troxy.core.scenarios import remove_scenario, resolve_scenario_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        sid = resolve_scenario_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    remove_scenario(db_path, sid)
    click.echo(f"시나리오 규칙 {sid} 삭제됨.")


@scenario_group.command("disable")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def scenario_disable_cmd(db, rule_ref):
    """ID 또는 이름으로 시나리오 규칙을 비활성화합니다."""
    from troxy.core.scenarios import toggle_scenario, resolve_scenario_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        sid = resolve_scenario_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    toggle_scenario(db_path, sid, enabled=False)
    click.echo(f"시나리오 규칙 {sid} 비활성화됨.")


@scenario_group.command("enable")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def scenario_enable_cmd(db, rule_ref):
    """ID 또는 이름으로 시나리오 규칙을 활성화합니다."""
    from troxy.core.scenarios import toggle_scenario, resolve_scenario_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        sid = resolve_scenario_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    toggle_scenario(db_path, sid, enabled=True)
    click.echo(f"시나리오 규칙 {sid} 활성화됨.")


@scenario_group.command("reset")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def scenario_reset_cmd(db, rule_ref):
    """시나리오 단계 카운터를 초기화합니다."""
    from troxy.core.scenarios import reset_scenario, resolve_scenario_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        sid = resolve_scenario_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    reset_scenario(db_path, sid)
    click.echo(f"시나리오 규칙 {sid} 1단계로 초기화됨.")


@scenario_group.command("from-flows")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("flow_ids", nargs=-1, type=int, required=True)
@click.option("--name", default=None, help="시나리오 이름 (선택)")
@click.option("--loop", is_flag=True, default=False, help="마지막 단계 후 1단계로 순환")
def scenario_from_flows_cmd(db, flow_ids, name, loop):
    """여러 flow 응답으로 순서대로 시나리오를 생성합니다."""
    from troxy.core.scenarios import scenario_from_flows
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        sid = scenario_from_flows(db_path, list(flow_ids), name=name, loop=loop)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    label = f"{sid} ({name!r})" if name else str(sid)
    click.echo(f"{len(flow_ids)}개 flow에서 시나리오 규칙 {label} 생성됨.")
