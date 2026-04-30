"""troxy MCP server — exposes flow data as MCP tools."""

import base64
import json
import os
import sys

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.query import list_flows, get_flow, search_flows, query_failures
from troxy.core.export import export_curl, export_httpie
from troxy.core.formats import parse_form_body
from troxy.core.intercept import (
    add_intercept_rule, list_intercept_rules, remove_intercept_rule,
    list_pending_flows, update_pending_flow, get_pending_flow,
)
from troxy.mcp.mock_handlers import (
    handle_mock_add, handle_mock_list, handle_mock_remove, handle_mock_toggle,
    handle_mock_from_flow, handle_mock_reset, handle_mock_update,
)


def handle_list_flows(db_path: str, args: dict) -> str:
    since_seconds = _parse_since_arg(args.get("since"))
    results = list_flows(
        db_path,
        domain=args.get("domain"),
        status=args.get("status"),
        method=args.get("method"),
        path=args.get("path"),
        limit=args.get("limit", 10),
        since_seconds=since_seconds,
    )
    return json.dumps(results, indent=2, default=str)


def _parse_since_arg(since):
    """Parse since string like '5m'. Returns None for missing/invalid."""
    if not since or not isinstance(since, str):
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if since and since[-1] in units:
        try:
            value = float(since[:-1])
            if value < 0:
                return None
            return value * units[since[-1]]
        except ValueError:
            return None
    return None


def handle_get_flow(db_path: str, args: dict) -> str:
    flow = get_flow(db_path, args["id"])
    if not flow:
        return json.dumps({"error": f"Flow {args['id']} not found"})
    part = args.get("part", "all")
    if part == "body":
        return json.dumps({
            "request_body": flow.get("request_body"),
            "response_body": flow.get("response_body"),
        }, indent=2)
    if part == "form":
        return json.dumps(_form_view(flow), indent=2, ensure_ascii=False)
    if part == "request":
        return json.dumps({k: v for k, v in flow.items() if k.startswith("request") or k in ("method", "scheme", "host", "port", "path", "query")}, indent=2, default=str)
    if part == "response":
        return json.dumps({k: v for k, v in flow.items() if k.startswith("response") or k == "status_code"}, indent=2, default=str)
    return json.dumps(flow, indent=2, default=str)


def _form_view(flow: dict) -> dict:
    """Return parsed form-urlencoded request body, handling legacy b64-encoded rows."""
    content_type = flow.get("request_content_type") or ""
    if "x-www-form-urlencoded" not in content_type:
        return {"error": "not form-urlencoded", "content_type": content_type}
    body = flow.get("request_body")
    if not body:
        return {"fields": {}, "truncated": False}
    if isinstance(body, str) and body.startswith("b64:"):
        try:
            body = base64.b64decode(body[4:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as e:
            return {"error": "decode failed", "reason": str(e)}
    return parse_form_body(body)


def handle_search(db_path: str, args: dict) -> str:
    results = search_flows(
        db_path, args["query"],
        domain=args.get("domain"),
        scope=args.get("scope", "all"),
        limit=args.get("limit", 50),
    )
    return json.dumps(results, indent=2, default=str)


def handle_export(db_path: str, args: dict) -> str:
    flow = get_flow(db_path, args["id"])
    if not flow:
        return json.dumps({"error": f"Flow {args['id']} not found"})
    fmt = args.get("format", "curl")
    if fmt == "httpie":
        return export_httpie(flow)
    return export_curl(flow)


def handle_status(db_path: str, args: dict) -> str:
    conn = get_connection(db_path)
    count = conn.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
    conn.close()
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return json.dumps({"flow_count": count, "db_size": db_size, "db_path": db_path})


def handle_intercept_add(db_path: str, args: dict) -> str:
    rule_id = add_intercept_rule(db_path, domain=args.get("domain"),
                                 path_pattern=args.get("path_pattern"), method=args.get("method"))
    return json.dumps({"rule_id": rule_id})


def handle_intercept_list(db_path: str, args: dict) -> str:
    return json.dumps(list_intercept_rules(db_path), indent=2, default=str)


def handle_intercept_remove(db_path: str, args: dict) -> str:
    remove_intercept_rule(db_path, args["id"])
    return json.dumps({"removed": args["id"]})


def handle_pending_list(db_path: str, args: dict) -> str:
    return json.dumps(list_pending_flows(db_path), indent=2, default=str)


def handle_modify(db_path: str, args: dict) -> str:
    headers = None
    body = None
    if "headers" in args:
        headers = args["headers"] if isinstance(args["headers"], str) else json.dumps(args["headers"])
    if "body" in args:
        body = args["body"]
    update_pending_flow(
        db_path,
        args["pending_id"],
        request_headers=headers,
        request_body=body,
        status="modified",
    )
    return json.dumps({"modified": args["pending_id"]})


def handle_release(db_path: str, args: dict) -> str:
    update_pending_flow(db_path, args["pending_id"], status="released")
    return json.dumps({"released": args["pending_id"]})


def handle_drop(db_path: str, args: dict) -> str:
    update_pending_flow(db_path, args["pending_id"], status="dropped")
    return json.dumps({"dropped": args["pending_id"]})


def _classify_failure(status: int, path: str, response_body: str | None) -> tuple[str, str, str]:
    """Return (pattern, label, hypothesis) for a failed flow.

    Purely structural — no LLM call. Keeps the tool cheap and cache-friendly.
    Claude Code receives organized fuel and does the reasoning.
    """
    body_lower = (response_body or "").lower()

    if status == 401:
        if any(k in body_lower for k in ("expired", "invalid_token", "token_expired")):
            return "token_expired", "Token expired", "Access token has expired — refresh or re-authenticate."
        return "auth_failure", "Authentication failure", "Request is missing credentials or the token is invalid/expired."

    if status == 403:
        return "permission_denied", "Permission denied", "Credentials are valid but the caller lacks the required permission or scope."

    if status == 404:
        return "not_found", "Resource not found", "The endpoint or resource does not exist — check path and IDs."

    if status == 422 or status == 400:
        return "bad_request", "Bad request / validation error", "The request payload is malformed or fails server-side validation — inspect the request body."

    if status == 429:
        return "rate_limit", "Rate limit hit", "Too many requests — the client is being throttled. Back off and retry with exponential delay."

    if status == 408 or status == 504 or status == 503:
        return "timeout_or_unavailable", "Timeout / service unavailable", "Upstream service is slow or unreachable — check service health and network."

    if 500 <= status <= 599:
        return "server_error", "Server error", f"Unexpected server-side failure (HTTP {status}) — check server logs for stack traces."

    if 400 <= status <= 499:
        return "client_error", "Client error", f"HTTP {status} — client-side error; inspect request headers, path, and body."

    return "unknown_failure", f"HTTP {status}", f"Unexpected status {status}."


def handle_explain_failure(db_path: str, args: dict) -> str:
    """Classify recent failure flows into semantic groups with hypotheses."""
    since_seconds = _parse_since_arg(args.get("since", "30m"))
    domain = args.get("domain")
    limit = args.get("limit", 50)

    flows = query_failures(db_path, domain=domain, since_seconds=since_seconds, limit=limit)

    if not flows:
        scope = f"domain={domain}" if domain else "all domains"
        window = args.get("since", "30m")
        return json.dumps({
            "summary": f"No failures found in the last {window} ({scope}).",
            "failure_groups": [],
            "total_failures": 0,
        })

    import datetime

    groups: dict[str, dict] = {}
    for flow in flows:
        status = flow["status_code"]
        path = flow.get("path", "")
        body = flow.get("response_body") or ""
        pattern, label, hypothesis = _classify_failure(status, path, body)

        if pattern not in groups:
            groups[pattern] = {
                "pattern": pattern,
                "label": label,
                "hypothesis": hypothesis,
                "count": 0,
                "examples": [],
            }
        groups[pattern]["count"] += 1
        if len(groups[pattern]["examples"]) < 3:
            ts = flow.get("timestamp")
            ts_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
            groups[pattern]["examples"].append({
                "id": flow["id"],
                "method": flow.get("method", ""),
                "host": flow.get("host", ""),
                "path": path,
                "status": status,
                "duration_ms": flow.get("duration_ms"),
                "time": ts_str,
            })

    sorted_groups = sorted(groups.values(), key=lambda g: g["count"], reverse=True)
    scope_str = f"on {domain}" if domain else "across all domains"
    window_str = args.get("since", "30m")
    summary = f"{len(flows)} failure(s) in the last {window_str} {scope_str}. {len(groups)} distinct pattern(s)."

    return json.dumps({
        "summary": summary,
        "failure_groups": sorted_groups,
        "total_failures": len(flows),
    }, indent=2)


from troxy.mcp.tools import TOOL_SCHEMAS

_HANDLERS = {
    "troxy_list_flows": handle_list_flows,
    "troxy_get_flow": handle_get_flow,
    "troxy_search": handle_search,
    "troxy_export": handle_export,
    "troxy_status": handle_status,
    "troxy_explain_failure": handle_explain_failure,
    "troxy_mock_add": handle_mock_add,
    "troxy_mock_list": handle_mock_list,
    "troxy_mock_remove": handle_mock_remove,
    "troxy_mock_toggle": handle_mock_toggle,
    "troxy_mock_from_flow": handle_mock_from_flow,
    "troxy_mock_reset": handle_mock_reset,
    "troxy_mock_update": handle_mock_update,
    "troxy_intercept_add": handle_intercept_add,
    "troxy_intercept_list": handle_intercept_list,
    "troxy_intercept_remove": handle_intercept_remove,
    "troxy_pending_list": handle_pending_list,
    "troxy_modify": handle_modify,
    "troxy_release": handle_release,
    "troxy_drop": handle_drop,
}

TOOLS = {name: {**TOOL_SCHEMAS[name], "handler": _HANDLERS[name]} for name in _HANDLERS}


def main():
    """Run MCP server using stdio transport."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError:
        _run_simple_stdio()
        return

    db_path = default_db_path()
    init_db(db_path)
    server = Server("troxy")

    @server.list_tools()
    async def list_tools():
        from mcp.types import Tool
        tools = []
        for name, info in TOOLS.items():
            tools.append(Tool(name=name, description=info["description"], inputSchema=info.get("schema", {"type": "object"})))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        from mcp.types import TextContent
        if name not in TOOLS:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        result = TOOLS[name]["handler"](db_path, arguments)
        return [TextContent(type="text", text=result)]

    import asyncio
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


def _run_simple_stdio():
    """Fallback stdio server without MCP SDK."""
    db_path = default_db_path()
    init_db(db_path)
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            tool_name = request.get("tool") or request.get("method", "")
            args = request.get("arguments") or request.get("params", {})
            if tool_name in TOOLS:
                result = TOOLS[tool_name]["handler"](db_path, args)
            else:
                result = json.dumps({"error": f"Unknown tool: {tool_name}"})
            print(json.dumps({"result": result}), flush=True)
        except Exception as e:
            print(json.dumps({"error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
