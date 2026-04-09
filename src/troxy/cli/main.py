"""troxy CLI — click commands."""

import json
import os
import sys

import click

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.query import list_flows, get_flow, search_flows
from troxy.core.export import export_curl, export_httpie


def _parse_since(since: str | None) -> float | None:
    """Parse since string like '5m', '1h' to seconds."""
    if not since:
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if since[-1] in units:
        try:
            return float(since[:-1]) * units[since[-1]]
        except ValueError:
            pass
    return None


def _common_options(f):
    """Shared --db and --no-color options for subcommands."""
    f = click.option("--db", default=None, help="Database path")(f)
    f = click.option("--no-color", is_flag=True, help="Disable color output")(f)
    return f


def _resolve_db(db: str | None) -> str:
    return db or default_db_path()


def _apply_no_color(no_color: bool) -> None:
    if no_color:
        os.environ["NO_COLOR"] = "1"


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
def flow_cmd(db, no_color, flow_id, request_only, response_only, headers_only, body_only,
             raw, as_json, export_format):
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
    print_flow_detail(flow, request_only=request_only, response_only=response_only,
                      headers_only=headers_only, body_only=body_only)


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


# ---------------------------------------------------------------------------
# Mock group
# ---------------------------------------------------------------------------

@cli.group("mock")
def mock_group():
    """Manage mock rules."""


@mock_group.command("add")
@click.option("--db", default=None, help="Database path")
@click.option("-d", "--domain", default=None, help="Domain to match")
@click.option("-p", "--path", "path_pattern", default=None, help="Path pattern to match")
@click.option("-m", "--method", default=None, help="HTTP method to match")
@click.option("-s", "--status", "status_code", default=200, type=int, help="Response status code")
@click.option("--header", "headers", multiple=True, help="Response header (Key: Value)")
@click.option("--body", "response_body", default=None, help="Response body")
def mock_add_cmd(db, domain, path_pattern, method, status_code, headers, response_body):
    """Add a mock rule."""
    import json as _json
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
    rule_id = add_mock_rule(
        db_path,
        domain=domain,
        path_pattern=path_pattern,
        method=method,
        status_code=status_code,
        response_headers=response_headers,
        response_body=response_body,
    )
    click.echo(f"Mock rule {rule_id} added.")


@mock_group.command("list")
@click.option("--db", default=None, help="Database path")
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def mock_list_cmd(db, no_color, as_json):
    """List mock rules."""
    import json as _json
    from troxy.core.mock import list_mock_rules
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    rules = list_mock_rules(db_path)
    if as_json:
        click.echo(_json.dumps(rules, indent=2, ensure_ascii=False, default=str))
        return
    if not rules:
        click.echo("No mock rules.")
        return
    for r in rules:
        status_label = "enabled" if r["enabled"] else "disabled"
        click.echo(f"[{r['id']}] {r['domain']} {r['path_pattern']} "
                   f"-> {r['status_code']} ({status_label})")


@mock_group.command("remove")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def mock_remove_cmd(db, rule_id):
    """Remove a mock rule."""
    from troxy.core.mock import remove_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    remove_mock_rule(db_path, rule_id)
    click.echo(f"Mock rule {rule_id} removed.")


@mock_group.command("disable")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def mock_disable_cmd(db, rule_id):
    """Disable a mock rule."""
    from troxy.core.mock import toggle_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    toggle_mock_rule(db_path, rule_id, enabled=False)
    click.echo(f"Mock rule {rule_id} disabled.")


@mock_group.command("enable")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def mock_enable_cmd(db, rule_id):
    """Enable a mock rule."""
    from troxy.core.mock import toggle_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    toggle_mock_rule(db_path, rule_id, enabled=True)
    click.echo(f"Mock rule {rule_id} enabled.")


@mock_group.command("from-flow")
@click.option("--db", default=None, help="Database path")
@click.argument("flow_id", type=int)
@click.option("-s", "--status", "status_code", default=None, type=int,
              help="Override response status code")
def mock_from_flow_cmd(db, flow_id, status_code):
    """Create a mock rule from an existing flow."""
    from troxy.core.mock import mock_from_flow
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = mock_from_flow(db_path, flow_id, status_code=status_code)
        click.echo(f"Mock rule {rule_id} created from flow {flow_id}.")
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Intercept group
# ---------------------------------------------------------------------------

@cli.group("intercept")
def intercept_group():
    """Manage intercept rules."""


@intercept_group.command("add")
@click.option("--db", default=None, help="Database path")
@click.option("-d", "--domain", default=None, help="Domain to match")
@click.option("-p", "--path", "path_pattern", default=None, help="Path pattern to match")
@click.option("-m", "--method", default=None, help="HTTP method to match")
def intercept_add_cmd(db, domain, path_pattern, method):
    """Add an intercept rule."""
    from troxy.core.intercept import add_intercept_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    rule_id = add_intercept_rule(db_path, domain=domain, path_pattern=path_pattern, method=method)
    click.echo(f"Intercept rule {rule_id} added.")


@intercept_group.command("list")
@click.option("--db", default=None, help="Database path")
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def intercept_list_cmd(db, no_color, as_json):
    """List intercept rules."""
    import json as _json
    from troxy.core.intercept import list_intercept_rules
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    rules = list_intercept_rules(db_path)
    if as_json:
        click.echo(_json.dumps(rules, indent=2, ensure_ascii=False, default=str))
        return
    if not rules:
        click.echo("No intercept rules.")
        return
    for r in rules:
        status_label = "enabled" if r["enabled"] else "disabled"
        method_label = r["method"] or "*"
        click.echo(f"[{r['id']}] {r['domain']} {r['path_pattern']} "
                   f"method={method_label} ({status_label})")


@intercept_group.command("remove")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def intercept_remove_cmd(db, rule_id):
    """Remove an intercept rule."""
    from troxy.core.intercept import remove_intercept_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    remove_intercept_rule(db_path, rule_id)
    click.echo(f"Intercept rule {rule_id} removed.")


# ---------------------------------------------------------------------------
# Pending flows commands
# ---------------------------------------------------------------------------

@cli.command("pending")
@_common_options
def pending_cmd(db, no_color):
    """List pending (intercepted) flows awaiting release or drop."""
    from troxy.core.intercept import list_pending_flows
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flows = list_pending_flows(db_path)
    if not flows:
        click.echo("No pending flows.")
        return
    for f in flows:
        click.echo(f"[{f['id']}] {f['method']} {f['host']}{f['path']} ({f['status']})")


@cli.command("modify")
@_common_options
@click.argument("pending_id", type=int)
@click.option("--header", "headers", multiple=True, help="Header to set (Key: Value)")
@click.option("--body", "request_body", default=None, help="New request body")
def modify_cmd(db, no_color, pending_id, headers, request_body):
    """Modify a pending flow's request headers or body."""
    import json as _json
    from troxy.core.intercept import get_pending_flow, update_pending_flow
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_pending_flow(db_path, pending_id)
    if not flow:
        click.echo(f"Pending flow {pending_id} not found.", err=True)
        sys.exit(1)
    new_headers = None
    if headers:
        try:
            existing = _json.loads(flow["request_headers"])
        except Exception:
            existing = {}
        for h in headers:
            if ":" in h:
                k, v = h.split(":", 1)
                existing[k.strip()] = v.strip()
        new_headers = _json.dumps(existing)
    update_pending_flow(db_path, pending_id,
                        request_headers=new_headers,
                        request_body=request_body)
    click.echo(f"Pending flow {pending_id} modified.")


@cli.command("release")
@_common_options
@click.argument("pending_id", type=int)
def release_cmd(db, no_color, pending_id):
    """Release a pending flow (mark as released)."""
    from troxy.core.intercept import get_pending_flow, update_pending_flow
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_pending_flow(db_path, pending_id)
    if not flow:
        click.echo(f"Pending flow {pending_id} not found.", err=True)
        sys.exit(1)
    update_pending_flow(db_path, pending_id, status="released")
    click.echo(f"Pending flow {pending_id} released.")


@cli.command("drop")
@_common_options
@click.argument("pending_id", type=int)
def drop_cmd(db, no_color, pending_id):
    """Drop a pending flow (mark as dropped)."""
    from troxy.core.intercept import get_pending_flow, update_pending_flow
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_pending_flow(db_path, pending_id)
    if not flow:
        click.echo(f"Pending flow {pending_id} not found.", err=True)
        sys.exit(1)
    update_pending_flow(db_path, pending_id, status="dropped")
    click.echo(f"Pending flow {pending_id} dropped.")


# ---------------------------------------------------------------------------
# Replay command
# ---------------------------------------------------------------------------

@cli.command("replay")
@_common_options
@click.argument("flow_id", type=int)
def replay_cmd(db, no_color, flow_id):
    """Replay a captured flow by resending its request."""
    import json as _json
    import urllib.request
    import urllib.error
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_flow(db_path, flow_id)
    if not flow:
        click.echo(f"Flow {flow_id} not found.", err=True)
        sys.exit(1)

    scheme = flow.get("scheme", "https")
    host = flow["host"]
    port = flow.get("port", 443)
    path = flow["path"]
    query = flow.get("query")
    url = f"{scheme}://{host}:{port}{path}"
    if query:
        url += f"?{query}"

    method = flow["method"]
    try:
        headers = _json.loads(flow["request_headers"]) if flow["request_headers"] else {}
    except Exception:
        headers = {}

    body = flow.get("request_body")
    body_bytes = body.encode("utf-8") if body else None

    req = urllib.request.Request(url, data=body_bytes, method=method)
    for k, v in headers.items():
        req.add_header(k, v)

    click.echo(f"Replaying flow {flow_id}: {method} {url}")
    try:
        with urllib.request.urlopen(req) as resp:
            click.echo(f"Response: {resp.status} {resp.reason}")
    except urllib.error.HTTPError as e:
        click.echo(f"Response: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        click.echo(f"Error: {e.reason}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Tail command
# ---------------------------------------------------------------------------

@cli.command("tail")
@_common_options
@click.option("-d", "--domain", default=None, help="Filter by domain")
@click.option("-n", "--count", default=10, type=int, help="Initial lines to show")
def tail_cmd(db, no_color, domain, count):
    """Tail new flows in real time (polls DB every 0.5s)."""
    import time as _time
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)

    # Show last N flows first
    results = list_flows(db_path, domain=domain, limit=count)
    last_id = 0
    for f in results:
        click.echo(f"[{f['id']}] {f['method']} {f['host']}{f['path']} -> {f['status_code']}")
        if f["id"] > last_id:
            last_id = f["id"]

    click.echo("Tailing new flows... (Ctrl+C to stop)")
    try:
        while True:
            _time.sleep(0.5)
            conn = get_connection(db_path)
            sql = "SELECT * FROM flows WHERE id > ?"
            params = [last_id]
            if domain:
                sql += " AND host LIKE ?"
                params.append(f"%{domain}%")
            sql += " ORDER BY id"
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            for row in rows:
                f = dict(row)
                click.echo(f"[{f['id']}] {f['method']} {f['host']}{f['path']} -> {f['status_code']}")
                if f["id"] > last_id:
                    last_id = f["id"]
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
