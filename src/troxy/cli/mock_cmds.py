"""troxy CLI — mock subcommands."""

import json as _json
import sys

import click

from troxy.core.db import init_db
from troxy.cli.utils import _resolve_db, _apply_no_color


@click.group("mock")
def mock_group():
    """mock 규칙을 관리합니다."""


@mock_group.command("add")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("-d", "--domain", default=None, help="매칭할 도메인")
@click.option("-p", "--path", "path_pattern", default=None, help="매칭할 경로 패턴")
@click.option("-m", "--method", default=None, help="매칭할 HTTP 메서드")
@click.option("-s", "--status", "status_code", default=200, type=int, help="응답 상태 코드")
@click.option("--header", "headers", multiple=True, help="응답 헤더 (Key: Value)")
@click.option("--body", "response_body", default=None, help="응답 body")
@click.option("--name", default=None, help="편리한 참조를 위한 이름 (예: 'user-500')")
def mock_add_cmd(db, domain, path_pattern, method, status_code, headers, response_body, name):
    """mock 규칙을 추가합니다."""
    import sys
    from troxy.core.mock import add_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    response_headers = None
    if headers:
        hdict = {}
        for h in headers:
            if ":" in h:
                k, v = h.split(":", 1)
                hdict[k.strip()] = v.strip()
        response_headers = _json.dumps(hdict)
    try:
        rule_id = add_mock_rule(
            db_path,
            domain=domain,
            path_pattern=path_pattern,
            method=method,
            status_code=status_code,
            response_headers=response_headers,
            response_body=response_body,
            name=name,
        )
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    label = f"{rule_id} ({name!r})" if name else str(rule_id)
    click.echo(f"mock 규칙 {label} 추가됨.")


@mock_group.command("list")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("--no-color", is_flag=True, help="색상 출력 비활성화")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
def mock_list_cmd(db, no_color, as_json):
    """mock 규칙 목록을 출력합니다."""
    from troxy.core.mock import list_mock_rules
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    rules = list_mock_rules(db_path)
    if as_json:
        click.echo(_json.dumps(rules, indent=2, ensure_ascii=False, default=str))
        return
    if not rules:
        click.echo("mock 규칙이 없습니다.")
        return
    for r in rules:
        status_label = "활성화" if r["enabled"] else "비활성화"
        name_label = f" {r['name']!r}" if r.get("name") else ""
        click.echo(f"[{r['id']}]{name_label} {r['domain']} {r['path_pattern']} "
                   f"-> {r['status_code']} ({status_label})")


@mock_group.command("remove")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def mock_remove_cmd(db, rule_ref):
    """ID 또는 이름으로 mock 규칙을 삭제합니다."""
    import sys
    from troxy.core.mock import remove_mock_rule, resolve_mock_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = resolve_mock_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    remove_mock_rule(db_path, rule_id)
    click.echo(f"mock 규칙 {rule_id} 삭제됨.")


@mock_group.command("disable")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def mock_disable_cmd(db, rule_ref):
    """ID 또는 이름으로 mock 규칙을 비활성화합니다."""
    import sys
    from troxy.core.mock import toggle_mock_rule, resolve_mock_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = resolve_mock_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    toggle_mock_rule(db_path, rule_id, enabled=False)
    click.echo(f"mock 규칙 {rule_id} 비활성화됨.")


@mock_group.command("enable")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def mock_enable_cmd(db, rule_ref):
    """ID 또는 이름으로 mock 규칙을 활성화합니다."""
    import sys
    from troxy.core.mock import toggle_mock_rule, resolve_mock_ref
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = resolve_mock_ref(db_path, rule_ref)
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    toggle_mock_rule(db_path, rule_id, enabled=True)
    click.echo(f"mock 규칙 {rule_id} 활성화됨.")


@mock_group.command("from-flow")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("flow_id", type=int)
@click.option("-s", "--status", "status_code", default=None, type=int,
              help="응답 상태 코드 재정의")
def mock_from_flow_cmd(db, flow_id, status_code):
    """기존 flow에서 mock 규칙을 생성합니다."""
    from troxy.core.mock import mock_from_flow
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = mock_from_flow(db_path, flow_id, status_code=status_code)
        click.echo(f"flow {flow_id}에서 mock 규칙 {rule_id} 생성됨.")
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@mock_group.command("reset")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_ref")
def mock_reset_cmd(db, rule_ref):
    """시나리오 mock 규칙의 단계 카운터를 초기화합니다."""
    import sys
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


@mock_group.command("from-status")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("status", type=int)
@click.option("-d", "--domain", default=None, help="도메인 내 검색 범위 제한")
def mock_from_status_cmd(db, status, domain):
    """지정한 상태 코드의 최근 flow에서 mock 규칙을 생성합니다.

    예시: `troxy mock from-status 401 -d api.example.com`
    """
    from troxy.core.mock import mock_from_status
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = mock_from_status(db_path, status, domain=domain)
        click.echo(f"{status} 응답의 최근 flow에서 mock 규칙 {rule_id} 생성됨.")
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
