"""troxy CLI — quick / explain commands for low-AI-literacy users.

`quick`: one-liner flow summary (replaces `mitmproxy TUI + Enter` for read-only devs)
`explain`: heuristic interpretation of what likely went wrong (no AI call)
"""

import base64
import json
import sys
from datetime import datetime

import click

from troxy.core.db import init_db
from troxy.core.query import get_flow
from troxy.cli.utils import _resolve_db, _apply_no_color, _common_options


# --- Heuristic knowledge base ----------------------------------------------

_STATUS_NAMES = {
    200: "OK", 201: "Created", 204: "No Content",
    301: "Moved Permanently", 302: "Found", 304: "Not Modified",
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 405: "Method Not Allowed", 408: "Request Timeout",
    409: "Conflict", 413: "Payload Too Large", 415: "Unsupported Media Type",
    422: "Unprocessable Entity", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway",
    503: "Service Unavailable", 504: "Gateway Timeout",
}


def _status_label(code: int) -> str:
    return _STATUS_NAMES.get(code, f"HTTP {code}")


def _human_size(body) -> str:
    if not body:
        return "0b"
    if isinstance(body, str) and body.startswith("b64:"):
        size = len(body) * 3 // 4
    else:
        size = len(body.encode("utf-8")) if isinstance(body, str) else len(body)
    if size < 1024:
        return f"{size}b"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}kb"
    return f"{size / 1024 / 1024:.1f}mb"


# --- `troxy quick` ----------------------------------------------------------

@click.command("quick")
@_common_options
@click.argument("flow_id", type=int)
def quick_cmd(db, no_color, flow_id):
    """읽기 전용 검사용 한 줄 요약."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_flow(db_path, flow_id)
    if not flow:
        click.echo(f"flow {flow_id}를 찾을 수 없습니다.", err=True)
        sys.exit(1)

    status = flow["status_code"]
    duration = flow.get("duration_ms")
    dur_str = f"{duration:.0f}ms" if duration else "-"
    resp_size = _human_size(flow.get("response_body"))
    req_size = _human_size(flow.get("request_body"))
    ct = (flow.get("response_content_type") or "").split(";")[0].strip() or "-"

    ts = flow.get("timestamp")
    when = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "-"

    click.echo(
        f"[{flow_id}] {when} {flow['method']} {flow['host']}{flow['path']} "
        f"→ {status} {_status_label(status)} "
        f"({dur_str}, req {req_size}, resp {resp_size}, {ct})"
    )


# --- `troxy explain` --------------------------------------------------------

@click.command("explain")
@_common_options
@click.argument("flow_id", type=int)
def explain_cmd(db, no_color, flow_id):
    """flow에 대한 휴리스틱 분석 (로컬 실행, AI 불필요)."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    flow = get_flow(db_path, flow_id)
    if not flow:
        click.echo(f"flow {flow_id}를 찾을 수 없습니다.", err=True)
        sys.exit(1)

    status = flow["status_code"]
    method = flow["method"]
    url = f"{flow['scheme']}://{flow['host']}{flow['path']}"
    if flow.get("query"):
        url += f"?{flow['query']}"

    click.echo(f"Flow #{flow_id}: {method} {url}")
    click.echo(f"  → {status} {_status_label(status)}")

    try:
        req_h = json.loads(flow.get("request_headers") or "{}")
    except Exception:
        req_h = {}
    try:
        resp_h = json.loads(flow.get("response_headers") or "{}")
    except Exception:
        resp_h = {}

    findings = _diagnose(flow, method, status, req_h, resp_h)

    if not findings:
        click.echo("  ✓ 특이사항 없음.")
        return

    click.echo("\n진단:")
    for f in findings:
        click.echo(f"  • {f}")

    click.echo(
        "\n다음으로 해볼 수 있는 것:\n"
        f"  troxy flow {flow_id} --body       # 전체 body 보기\n"
        f"  troxy flow {flow_id} --export curl  # 같은 요청 재현\n"
        f"  troxy replay {flow_id}             # 저장된 요청 재전송\n"
    )


def _diagnose(flow, method, status, req_h, resp_h) -> list[str]:
    findings = []
    lower_req = {k.lower(): v for k, v in req_h.items()}
    lower_resp = {k.lower(): v for k, v in resp_h.items()}

    # Status-based
    if status == 401:
        auth = lower_req.get("authorization", "")
        findings.append(
            "401 Unauthorized — Authorization 헤더를 서버가 거부함."
        )
        if not auth:
            findings.append("  Authorization 헤더가 비어있음. 로그인 토큰이 붙지 않았을 가능성.")
        elif auth.lower().startswith("bearer "):
            findings.extend(_jwt_findings(auth.split(" ", 1)[1]))
        body = flow.get("response_body") or ""
        if isinstance(body, str) and body and not body.startswith("b64:"):
            snippet = body[:120].replace("\n", " ")
            findings.append(f"  응답 메시지: {snippet}")

    elif status == 403:
        findings.append("403 Forbidden — 토큰은 유효해도 권한이 없음. 서버 role/scope 확인.")

    elif status == 404:
        findings.append(f"404 Not Found — 경로 {flow['path']} 가 서버에 없거나 오타일 수 있음.")
        if flow.get("query"):
            findings.append("  query parameter 포함되어 있는데 서버가 path로 인식했을 가능성도 체크.")

    elif status == 429:
        ra = lower_resp.get("retry-after")
        if ra:
            secs = _parse_retry_after(ra)
            human = f"{secs}s ({secs // 60}m {secs % 60}s)" if secs is not None else ra
            findings.append(
                f"429 Too Many Requests — 레이트 리밋. Retry-After: {human}. "
                f"다음 호출 전 최소 그만큼 대기 필요."
            )
        else:
            findings.append(
                "429 Too Many Requests — 레이트 리밋. Retry-After 헤더가 없어 백오프 간격을 서버가 명시 안 함."
            )

    elif 500 <= status < 600:
        findings.append(f"{status} — 서버 에러. 클라이언트가 아니라 백엔드 문제일 가능성 높음.")
        body = flow.get("response_body") or ""
        if isinstance(body, str) and body and not body.startswith("b64:"):
            snippet = body[:200].replace("\n", " ")
            findings.append(f"  서버 응답: {snippet}")

    elif 300 <= status < 400:
        loc = lower_resp.get("location")
        findings.append(f"{status} Redirect{' → ' + loc if loc else ''}")

    # Header/body sanity
    if method in ("POST", "PUT", "PATCH"):
        ct = lower_req.get("content-type", "")
        body = flow.get("request_body")
        if body and not ct:
            findings.append("request body는 있는데 Content-Type 헤더 없음. 서버가 파싱 못할 수 있음.")
        if "application/json" in ct and body and isinstance(body, str) and not body.startswith("b64:"):
            try:
                json.loads(body)
            except Exception:
                findings.append("Content-Type은 JSON인데 body가 JSON 형식이 아님.")
        # Content-type mismatch: JSON body sent with form content-type
        if "x-www-form-urlencoded" in ct and body and isinstance(body, str):
            stripped = body.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                findings.append(
                    "Content-Type은 form-urlencoded인데 body가 JSON 형식. "
                    "Content-Type을 application/json으로 바꾸거나 body를 key=value 포맷으로."
                )

    # Cache header diagnostics (new in v0.2)
    if 200 <= status < 300 or status == 304:
        cc = lower_resp.get("cache-control", "")
        if status == 304:
            findings.append("304 Not Modified — 클라이언트 캐시 재사용. 서버가 body 다시 안 내려줌.")
        elif "no-store" in cc:
            findings.append("Cache-Control: no-store — 이 응답은 캐시되지 않음 (민감 데이터 가능성).")
        elif "no-cache" in cc:
            findings.append("Cache-Control: no-cache — 매 요청마다 서버 validate 필요.")

    # CORS preflight
    if method == "OPTIONS" and "access-control-request-method" in lower_req:
        ac = lower_resp.get("access-control-allow-origin")
        if not ac:
            findings.append("CORS preflight인데 Access-Control-Allow-Origin 응답이 없음.")

    # Slow response
    dur = flow.get("duration_ms") or 0
    if dur > 3000:
        findings.append(f"응답 지연 {dur:.0f}ms — 3초 초과. 백엔드/네트워크 성능 확인.")

    # Large response
    resp_body = flow.get("response_body")
    if resp_body and isinstance(resp_body, str):
        size = len(resp_body.encode("utf-8")) if not resp_body.startswith("b64:") else len(resp_body) * 3 // 4
        if size > 1024 * 1024:
            findings.append(f"응답 크기 {size / 1024 / 1024:.1f}MB — 큼. 페이징/압축 고려.")

    return findings


def _parse_retry_after(value: str) -> int | None:
    """Parse Retry-After header. Supports seconds ('120') or HTTP-date."""
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime
    try:
        return max(0, int(value.strip()))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (dt - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(delta))
    except Exception:
        return None


def _jwt_findings(token: str) -> list[str]:
    """Best-effort JWT claim extraction. Returns empty list if not a JWT."""
    parts = token.split(".")
    if len(parts) != 3:
        return []
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return []
    out = []
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        now = datetime.now().timestamp()
        if exp < now:
            out.append(f"  JWT 토큰 만료됨 (exp={datetime.fromtimestamp(exp)}).")
        else:
            remaining = int(exp - now)
            out.append(f"  JWT 토큰 유효 (남은 시간 {remaining // 60}분).")
    sub = payload.get("sub")
    if sub:
        out.append(f"  JWT subject: {sub}")
    return out
