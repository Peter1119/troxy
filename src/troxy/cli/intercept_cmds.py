"""troxy CLI — intercept subcommands."""

import json as _json
import sys

import click

from troxy.core.db import init_db
from troxy.cli.utils import _resolve_db, _apply_no_color


@click.group("intercept")
def intercept_group():
    """인터셉트 규칙을 관리합니다."""


@intercept_group.command("add")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("-d", "--domain", default=None, help="매칭할 도메인")
@click.option("-p", "--path", "path_pattern", default=None, help="매칭할 경로 패턴")
@click.option("-m", "--method", default=None, help="매칭할 HTTP 메서드")
def intercept_add_cmd(db, domain, path_pattern, method):
    """인터셉트 규칙을 추가합니다."""
    from troxy.core.intercept import add_intercept_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    rule_id = add_intercept_rule(db_path, domain=domain, path_pattern=path_pattern, method=method)
    click.echo(f"인터셉트 규칙 {rule_id} 추가됨.")


@intercept_group.command("list")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("--no-color", is_flag=True, help="색상 출력 비활성화")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
def intercept_list_cmd(db, no_color, as_json):
    """인터셉트 규칙 목록을 출력합니다."""
    from troxy.core.intercept import list_intercept_rules
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    rules = list_intercept_rules(db_path)
    if as_json:
        click.echo(_json.dumps(rules, indent=2, ensure_ascii=False, default=str))
        return
    if not rules:
        click.echo("인터셉트 규칙이 없습니다.")
        return
    for r in rules:
        status_label = "활성화" if r["enabled"] else "비활성화"
        method_label = r["method"] or "*"
        click.echo(f"[{r['id']}] {r['domain']} {r['path_pattern']} "
                   f"method={method_label} ({status_label})")


@intercept_group.command("remove")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.argument("rule_id", type=int)
def intercept_remove_cmd(db, rule_id):
    """인터셉트 규칙을 삭제합니다."""
    from troxy.core.intercept import remove_intercept_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    remove_intercept_rule(db_path, rule_id)
    click.echo(f"인터셉트 규칙 {rule_id} 삭제됨.")
