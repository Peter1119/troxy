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
    """릴리즈 또는 드롭 대기 중인 인터셉트 flow 목록을 출력합니다."""
    from troxy.core.intercept import list_pending_flows
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flows = list_pending_flows(db_path)
    if not flows:
        click.echo("대기 중인 flow가 없습니다.")
        return
    for f in flows:
        click.echo(f"[{f['id']}] {f['method']} {f['host']}{f['path']} ({f['status']})")


@click.command("modify")
@_common_options
@click.argument("pending_id", type=int)
@click.option("--header", "headers", multiple=True, help="설정할 헤더 (Key: Value)")
@click.option("--body", "request_body", default=None, help="새 요청 body")
def modify_cmd(db, no_color, pending_id, headers, request_body):
    """대기 flow의 요청 헤더 또는 body를 수정합니다."""
    from troxy.core.intercept import get_pending_flow, update_pending_flow
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_pending_flow(db_path, pending_id)
    if not flow:
        click.echo(f"대기 flow {pending_id}를 찾을 수 없습니다.", err=True)
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
    click.echo(f"대기 flow {pending_id} 수정됨.")


@click.command("release")
@_common_options
@click.argument("pending_id", type=int)
def release_cmd(db, no_color, pending_id):
    """대기 flow를 릴리즈합니다."""
    from troxy.core.intercept import get_pending_flow, update_pending_flow
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_pending_flow(db_path, pending_id)
    if not flow:
        click.echo(f"대기 flow {pending_id}를 찾을 수 없습니다.", err=True)
        sys.exit(1)
    update_pending_flow(db_path, pending_id, status="released")
    click.echo(f"대기 flow {pending_id} 릴리즈됨.")


@click.command("drop")
@_common_options
@click.argument("pending_id", type=int)
def drop_cmd(db, no_color, pending_id):
    """대기 flow를 드롭합니다."""
    from troxy.core.intercept import get_pending_flow, update_pending_flow
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_pending_flow(db_path, pending_id)
    if not flow:
        click.echo(f"대기 flow {pending_id}를 찾을 수 없습니다.", err=True)
        sys.exit(1)
    update_pending_flow(db_path, pending_id, status="dropped")
    click.echo(f"대기 flow {pending_id} 드롭됨.")


@click.command("replay")
@_common_options
@click.argument("flow_id", type=int)
@click.option("--header", "headers_override", multiple=True,
              help="헤더 재정의/추가 (Key: Value). 반복 사용 가능.")
@click.option("--body", "body_override", default=None,
              help="요청 body 재정의")
@click.option("--no-body", "hide_body", is_flag=True,
              help="응답 body 출력 안 함 (기본: 출력)")
def replay_cmd(db, no_color, flow_id, headers_override, body_override, hide_body):
    """캡처된 flow를 재전송합니다. base64 body 디코딩 및 응답 body 기본 출력."""
    import base64
    import urllib.request
    import urllib.error
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_flow(db_path, flow_id)
    if not flow:
        click.echo(f"flow {flow_id}를 찾을 수 없습니다.", err=True)
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

    click.echo(f"flow {flow_id} 재전송 중: {method} {url}")
    try:
        with urllib.request.urlopen(req) as resp:
            click.echo(f"응답: {resp.status} {resp.reason}")
            if not hide_body:
                _print_replay_body(resp)
    except urllib.error.HTTPError as e:
        click.echo(f"응답: {e.code} {e.reason}")
        if not hide_body:
            _print_replay_body(e)
    except urllib.error.URLError as e:
        click.echo(f"오류: {e.reason}", err=True)
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
        click.echo(f"(바이너리 응답, {len(data)} bytes)")
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
@click.option("-d", "--domain", default=None, help="도메인 필터")
@click.option("-s", "--status", default=None,
              help="상태 코드 필터 (예: 401, 4xx, 5xx)")
@click.option("-m", "--method", default=None, help="HTTP 메서드 필터")
@click.option("-n", "--count", default=10, type=int, help="초기 출력 라인 수")
def tail_cmd(db, no_color, domain, status, method, count):
    """새 flow를 실시간으로 감시합니다 (0.5초 간격 DB 폴링)."""
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

    click.echo("새 flow 실시간 감시 중... (Ctrl+C 종료)")
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
            f"잘못된 상태 코드 필터: {status!r}. 401 또는 4xx 형식으로 입력하세요."
        )


def _matches_status_class(flow, status_class):
    if status_class is None:
        return True
    return flow["status_code"] // 100 == status_class


def _emit_tail(f):
    click.echo(f"[{f['id']}] {f['method']} {f['host']}{f['path']} -> {f['status_code']}")
