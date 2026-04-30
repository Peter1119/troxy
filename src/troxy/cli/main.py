"""troxy CLI — click commands."""

import json
import os
import sys

import click

from troxy.core.db import init_db, get_connection
from troxy.core.query import list_flows, get_flow, search_flows
from troxy.core.export import export_curl, export_httpie
from troxy.cli.utils import _parse_since, _common_options, _resolve_db, _apply_no_color


@click.group()
def cli():
    """troxy — 터미널 프록시 인스펙터."""


@cli.command("flows")
@_common_options
@click.option("-d", "--domain", default=None, help="도메인 필터 (부분 일치)")
@click.option("-s", "--status", default=None, type=int, help="상태 코드 필터")
@click.option("-m", "--method", default=None, help="HTTP 메서드 필터")
@click.option("-p", "--path", "path_filter", default=None, help="경로 필터 (부분 일치)")
@click.option("-n", "--limit", default=50, type=int, help="최대 결과 수")
@click.option("--since", default=None, help="시간 필터 (예: 5m, 1h)")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
def flows_cmd(db, no_color, domain, status, method, path_filter, limit, since, as_json):
    """캡처된 flow 목록을 출력합니다."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    since_seconds = _parse_since(since)
    results = list_flows(db_path, domain=domain, status=status, method=method,
                         path=path_filter, limit=limit, since_seconds=since_seconds)
    if as_json:
        click.echo(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        return
    if not results:
        click.echo("flow가 없습니다.")
        return
    from troxy.cli.formatting import print_flows_table
    print_flows_table(results)


@cli.command("flow")
@_common_options
@click.argument("flow_id", type=int)
@click.option("--request", "request_only", is_flag=True, help="요청만 출력")
@click.option("--response", "response_only", is_flag=True, help="응답만 출력")
@click.option("--headers", "headers_only", is_flag=True, help="헤더만 출력")
@click.option("--body", "body_only", is_flag=True, help="body만 출력")
@click.option("--raw", is_flag=True, help="포맷 없이 원시 출력")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
@click.option("--export", "export_format", type=click.Choice(["curl", "httpie"]),
              default=None, help="내보내기 형식")
@click.option("--no-hint", is_flag=True, help="하단 Claude MCP 힌트 숨기기")
def flow_cmd(db, no_color, flow_id, request_only, response_only, headers_only, body_only,
             raw, as_json, export_format, no_hint):
    """flow 상세 정보를 출력합니다."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_flow(db_path, flow_id)
    if not flow:
        click.echo(f"flow {flow_id}를 찾을 수 없습니다.", err=True)
        sys.exit(1)

    if export_format == "curl":
        click.echo(export_curl(flow))
        return
    if export_format == "httpie":
        click.echo(export_httpie(flow))
        return
    if as_json:
        click.echo(json.dumps(flow, indent=2, ensure_ascii=False, default=str))
        return
    if raw:
        if body_only:
            click.echo(flow.get("response_body", ""))
        else:
            click.echo(json.dumps(flow, indent=2, ensure_ascii=False, default=str))
        return

    from troxy.cli.formatting import print_flow_detail
    from troxy.cli.hints import hints_enabled, flow_hint
    print_flow_detail(flow, request_only=request_only, response_only=response_only,
                      headers_only=headers_only, body_only=body_only)
    if hints_enabled(cli_no_hint=no_hint) and not body_only and not headers_only:
        click.echo(flow_hint(flow_id).format(status=flow["status_code"]))


@cli.command("search")
@_common_options
@click.argument("query")
@click.option("-d", "--domain", default=None, help="도메인 필터")
@click.option("--in", "scope", type=click.Choice(["request", "response", "all"]),
              default="all", help="검색 범위")
@click.option("-n", "--limit", default=50, type=int, help="최대 결과 수")
@click.option("--json", "as_json", is_flag=True, help="JSON 형식으로 출력")
def search_cmd(db, no_color, query, domain, scope, limit, as_json):
    """flow body에서 텍스트를 검색합니다."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    results = search_flows(db_path, query, domain=domain, scope=scope, limit=limit)
    if as_json:
        click.echo(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        return
    if not results:
        click.echo("일치하는 flow가 없습니다.")
        return
    from troxy.cli.formatting import print_flows_table
    print_flows_table(results)


@cli.command("status")
@_common_options
def status_cmd(db, no_color):
    """데이터베이스 상태를 출력합니다."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    conn = get_connection(db_path)
    count = conn.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
    conn.close()
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    from troxy.cli.formatting import print_status
    print_status(db_path, count, db_size)


@cli.command("clear")
@_common_options
@click.option("--before", default=None, help="이전 flow 삭제 (예: 1h)")
@click.option("--yes", is_flag=True, help="확인 단계 건너뛰기")
def clear_cmd(db, no_color, before, yes):
    """전체 flow를 삭제합니다."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    if not yes:
        click.confirm("전체 flow를 삭제할까요?", abort=True)
    conn = get_connection(db_path)
    if before:
        seconds = _parse_since(before)
        if seconds:
            import time
            conn.execute("DELETE FROM flows WHERE timestamp < ?", (time.time() - seconds,))
    else:
        conn.execute("DELETE FROM flows")
    conn.commit()
    conn.close()
    click.echo("flow 초기화 완료.")


@cli.command("start")
@click.option("-p", "--port", default=8080, type=int, help="프록시 포트")
@click.option("--mode", default=None, help="프록시 모드 (예: regular, transparent)")
@_common_options
def start_cmd(port, mode, db, no_color):
    """mitmproxy(헤드리스) + troxy TUI 실행."""
    _apply_no_color(no_color)
    from troxy.tui.app import TroxyStartApp
    from troxy.tui.proxy import ProxyManager, ProxyBootError

    db_path = _resolve_db(db)
    init_db(db_path)

    proxy = ProxyManager(port=port, mode=mode, db_path=db_path)
    try:
        proxy.start()
    except ProxyBootError as e:
        click.echo(f"troxy start 실패:\n{e}", err=True)
        sys.exit(2)
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    # Convert SIGTERM into SystemExit so the finally block below (and
    # atexit hook) run. Default SIGTERM would skip cleanup and orphan mitmdump.
    import atexit
    import signal
    atexit.register(proxy.stop)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    from troxy.cli.hints import hints_enabled

    try:
        app = TroxyStartApp(
            db_path=db_path,
            port=port,
            mcp_registered=hints_enabled(),
            proxy_running_fn=lambda: proxy.running,
            proxy_pause_fn=proxy.pause,
            proxy_resume_fn=proxy.resume,
        )
        app.run()
    finally:
        proxy.stop()


def _register_subgroups() -> None:
    from troxy.cli.mock_cmds import mock_group
    from troxy.cli.intercept_cmds import intercept_group
    from troxy.cli.scenario_cmds import scenario_group
    from troxy.cli.flow_cmds import (
        pending_cmd, modify_cmd, release_cmd, drop_cmd, replay_cmd, tail_cmd,
    )
    from troxy.cli.setup_cmds import (
        version_cmd, doctor_cmd, init_cmd, onboard_cmd, mcp_tools_cmd,
    )
    from troxy.cli.explain_cmds import quick_cmd, explain_cmd
    from troxy.cli.alias_cmds import alias_group
    from troxy.cli.session_cmds import session_group
    from troxy.cli.pick_cmds import pick_cmd
    cli.add_command(mock_group)
    cli.add_command(intercept_group)
    cli.add_command(scenario_group)
    cli.add_command(pending_cmd)
    cli.add_command(modify_cmd)
    cli.add_command(release_cmd)
    cli.add_command(drop_cmd)
    cli.add_command(replay_cmd)
    cli.add_command(tail_cmd)
    cli.add_command(version_cmd)
    cli.add_command(doctor_cmd)
    cli.add_command(init_cmd)
    cli.add_command(onboard_cmd)
    cli.add_command(mcp_tools_cmd)
    cli.add_command(quick_cmd)
    cli.add_command(explain_cmd)
    cli.add_command(alias_group)
    cli.add_command(session_group)
    cli.add_command(pick_cmd)


_register_subgroups()


def _main():
    """Entry point with alias expansion before click parses."""
    from troxy.cli.alias_cmds import resolve_alias_invocation
    argv = sys.argv[1:]
    expanded = resolve_alias_invocation(argv)
    if expanded is not None:
        sys.argv = [sys.argv[0]] + expanded
    cli()


if __name__ == "__main__":
    _main()
