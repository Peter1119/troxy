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
@click.option("--header", "headers_override", multiple=True,
              help="Override/add header (Key: Value). Can be repeated.")
@click.option("--body", "body_override", default=None,
              help="Override request body")
@click.option("--no-body", "hide_body", is_flag=True,
              help="Don't print response body (default: print)")
def replay_cmd(db, no_color, flow_id, headers_override, body_override, hide_body):
    """Replay a captured flow. Decodes base64 bodies, prints response body by default."""
    import base64
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
    port = flow.get("port") or (443 if scheme == "https" else 80)
    default_port = 443 if scheme == "https" else 80
    host_part = f"{host}:{port}" if port != default_port else host
    path = flow["path"]
    query = flow.get("query")
    url = f"{scheme}://{host_part}{path}"
    if query:
        url += f"?{query}"

    method = flow["method"]
    try:
        headers = json.loads(flow["request_headers"]) if flow["request_headers"] else {}
    except Exception:
        headers = {}

    for h in headers_override:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()

    body = body_override if body_override is not None else flow.get("request_body")
    body_bytes = None
    if body is not None:
        if isinstance(body, str) and body.startswith("b64:"):
            body_bytes = base64.b64decode(body[4:])
        elif isinstance(body, str):
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = bytes(body)

    req = urllib.request.Request(url, data=body_bytes, method=method)
    for k, v in headers.items():
        req.add_header(k, v)

    click.echo(f"Replaying flow {flow_id}: {method} {url}")
    try:
        with urllib.request.urlopen(req) as resp:
            click.echo(f"Response: {resp.status} {resp.reason}")
            if not hide_body:
                _print_replay_body(resp)
    except urllib.error.HTTPError as e:
        click.echo(f"Response: {e.code} {e.reason}")
        if not hide_body:
            _print_replay_body(e)
    except urllib.error.URLError as e:
        click.echo(f"Error: {e.reason}", err=True)
        sys.exit(1)


def _print_replay_body(resp):
    try:
        data = resp.read()
    except Exception:
        return
    if not data:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        click.echo(f"(binary response, {len(data)} bytes)")
        return
    ct = resp.headers.get("Content-Type", "") if hasattr(resp, "headers") else ""
    if "json" in ct:
        try:
            click.echo(json.dumps(json.loads(text), indent=2, ensure_ascii=False))
            return
        except Exception:
            pass
    # Truncate very long text
    if len(text) > 8000:
        click.echo(text[:8000])
        click.echo(f"... ({len(text) - 8000} more bytes)")
    else:
        click.echo(text)


@click.command("tail")
@_common_options
@click.option("-d", "--domain", default=None, help="Filter by domain")
@click.option("-s", "--status", default=None,
              help="Filter by status code (exact, e.g. 401) or class (e.g. 4xx, 5xx)")
@click.option("-m", "--method", default=None, help="Filter by HTTP method")
@click.option("-n", "--count", default=10, type=int, help="Initial lines to show")
def tail_cmd(db, no_color, domain, status, method, count):
    """Tail new flows in real time (polls DB every 0.5s)."""
    import time as _time
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)

    status_exact, status_class = _parse_status_filter(status)

    results = list_flows(db_path, domain=domain, status=status_exact, method=method,
                         limit=count)
    results = [f for f in results if _matches_status_class(f, status_class)]
    last_id = 0
    for f in results:
        _emit_tail(f)
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
            if status_exact is not None:
                sql += " AND status_code = ?"
                params.append(status_exact)
            if method:
                sql += " AND method = ?"
                params.append(method.upper())
            sql += " ORDER BY id"
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            for row in rows:
                f = dict(row)
                if not _matches_status_class(f, status_class):
                    continue
                _emit_tail(f)
                if f["id"] > last_id:
                    last_id = f["id"]
    except KeyboardInterrupt:
        pass


def _parse_status_filter(status):
    """Parse '401' → (401, None); '4xx' → (None, 4); None → (None, None)."""
    if not status:
        return None, None
    s = status.lower()
    if len(s) == 3 and s.endswith("xx") and s[0].isdigit():
        return None, int(s[0])
    try:
        return int(status), None
    except ValueError:
        raise click.BadParameter(
            f"Invalid status filter: {status!r}. Use 401 or 4xx."
        )


def _matches_status_class(flow, status_class):
    if status_class is None:
        return True
    return flow["status_code"] // 100 == status_class


def _emit_tail(f):
    click.echo(f"[{f['id']}] {f['method']} {f['host']}{f['path']} -> {f['status_code']}")
