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
    """troxy — terminal proxy inspector."""


@cli.command("flows")
@_common_options
@click.option("-d", "--domain", default=None, help="Filter by domain (partial match)")
@click.option("-s", "--status", default=None, type=int, help="Filter by status code")
@click.option("-m", "--method", default=None, help="Filter by HTTP method")
@click.option("-p", "--path", "path_filter", default=None, help="Filter by path (partial match)")
@click.option("-n", "--limit", default=50, type=int, help="Max results")
@click.option("--since", default=None, help="Time filter (e.g. 5m, 1h)")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def flows_cmd(db, no_color, domain, status, method, path_filter, limit, since, as_json):
    """List captured flows."""
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
        click.echo("No flows found.")
        return
    from troxy.cli.formatting import print_flows_table
    print_flows_table(results)


@cli.command("flow")
@_common_options
@click.argument("flow_id", type=int)
@click.option("--request", "request_only", is_flag=True, help="Show request only")
@click.option("--response", "response_only", is_flag=True, help="Show response only")
@click.option("--headers", "headers_only", is_flag=True, help="Show headers only")
@click.option("--body", "body_only", is_flag=True, help="Show body only")
@click.option("--raw", is_flag=True, help="Raw output without formatting")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.option("--export", "export_format", type=click.Choice(["curl", "httpie"]),
              default=None, help="Export format")
@click.option("--no-hint", is_flag=True, help="Suppress Claude MCP hint at the bottom")
def flow_cmd(db, no_color, flow_id, request_only, response_only, headers_only, body_only,
             raw, as_json, export_format, no_hint):
    """Show flow details."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_flow(db_path, flow_id)
    if not flow:
        click.echo(f"Flow {flow_id} not found.", err=True)
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
@click.option("-d", "--domain", default=None, help="Filter by domain")
@click.option("--in", "scope", type=click.Choice(["request", "response", "all"]),
              default="all", help="Search scope")
@click.option("-n", "--limit", default=50, type=int, help="Max results")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def search_cmd(db, no_color, query, domain, scope, limit, as_json):
    """Search flow bodies for text."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    results = search_flows(db_path, query, domain=domain, scope=scope, limit=limit)
    if as_json:
        click.echo(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        return
    if not results:
        click.echo("No matching flows.")
        return
    from troxy.cli.formatting import print_flows_table
    print_flows_table(results)


@cli.command("status")
@_common_options
def status_cmd(db, no_color):
    """Show database status."""
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
@click.option("--before", default=None, help="Clear flows older than (e.g. 1h)")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def clear_cmd(db, no_color, before, yes):
    """Clear all flows."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    if not yes:
        click.confirm("Delete all flows?", abort=True)
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
    click.echo("Flows cleared.")


@cli.command("start")
@click.option("-p", "--port", default=8080, type=int, help="Proxy port")
@click.option("--mode", default=None, help="Proxy mode (e.g. regular, transparent)")
def start_cmd(port, mode):
    """Start mitmproxy with troxy addon."""
    import shutil
    import subprocess

    addon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "addon.py")

    # Find mitmproxy in venv first, then PATH
    venv_bin = os.path.join(os.path.dirname(sys.executable), "mitmproxy")
    if os.path.exists(venv_bin):
        mitmproxy_bin = venv_bin
    else:
        mitmproxy_bin = shutil.which("mitmproxy")
    if not mitmproxy_bin:
        click.echo("mitmproxy not found. Install: uv add mitmproxy", err=True)
        sys.exit(1)

    cmd = [mitmproxy_bin, "-s", addon_path, "-p", str(port)]
    if mode:
        cmd.extend(["--mode", mode])

    click.echo(f"Starting mitmproxy on :{port} with troxy addon...")
    click.echo(f"  DB: {os.environ.get('TROXY_DB', '~/.troxy/flows.db')}")
    click.echo(f"  Addon: {addon_path}")
    click.echo()
    os.execvp(mitmproxy_bin, cmd)


def _register_subgroups() -> None:
    from troxy.cli.mock_cmds import mock_group
    from troxy.cli.intercept_cmds import intercept_group
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
