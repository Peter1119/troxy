"""troxy CLI — pending flow and tail subcommands."""

import json
import sys

import click

from troxy.core.db import init_db, get_connection
from troxy.core.query import list_flows, get_flow
from troxy.cli.utils import _resolve_db, _apply_no_color, _common_options


@click.command("pending")
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


@click.command("modify")
@_common_options
@click.argument("pending_id", type=int)
@click.option("--header", "headers", multiple=True, help="Header to set (Key: Value)")
@click.option("--body", "request_body", default=None, help="New request body")
def modify_cmd(db, no_color, pending_id, headers, request_body):
    """Modify a pending flow's request headers or body."""
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
            existing = json.loads(flow["request_headers"])
        except Exception:
            existing = {}
        for h in headers:
            if ":" in h:
                k, v = h.split(":", 1)
                existing[k.strip()] = v.strip()
        new_headers = json.dumps(existing)
    update_pending_flow(db_path, pending_id,
                        request_headers=new_headers,
                        request_body=request_body)
    click.echo(f"Pending flow {pending_id} modified.")


@click.command("release")
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


@click.command("drop")
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


@click.command("replay")
@_common_options
@click.argument("flow_id", type=int)
def replay_cmd(db, no_color, flow_id):
    """Replay a captured flow by resending its request."""
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
        headers = json.loads(flow["request_headers"]) if flow["request_headers"] else {}
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


@click.command("tail")
@_common_options
@click.option("-d", "--domain", default=None, help="Filter by domain")
@click.option("-n", "--count", default=10, type=int, help="Initial lines to show")
def tail_cmd(db, no_color, domain, count):
    """Tail new flows in real time (polls DB every 0.5s)."""
    import time as _time
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)

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
                click.echo(
                    f"[{f['id']}] {f['method']} {f['host']}{f['path']} -> {f['status_code']}"
                )
                if f["id"] > last_id:
                    last_id = f["id"]
    except KeyboardInterrupt:
        pass
