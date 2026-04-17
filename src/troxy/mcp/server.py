"""troxy MCP server — exposes flow data as MCP tools."""

import json
import os
import sys

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.query import list_flows, get_flow, search_flows
from troxy.core.export import export_curl, export_httpie
from troxy.core.mock import add_mock_rule, list_mock_rules, remove_mock_rule, toggle_mock_rule, mock_from_flow
from troxy.core.intercept import (
    add_intercept_rule, list_intercept_rules, remove_intercept_rule,
    list_pending_flows, update_pending_flow, get_pending_flow,
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
    if part == "request":
        return json.dumps({k: v for k, v in flow.items() if k.startswith("request") or k in ("method", "scheme", "host", "port", "path", "query")}, indent=2, default=str)
    if part == "response":
        return json.dumps({k: v for k, v in flow.items() if k.startswith("response") or k == "status_code"}, indent=2, default=str)
    return json.dumps(flow, indent=2, default=str)


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


def handle_mock_add(db_path: str, args: dict) -> str:
    rule_id = add_mock_rule(
        db_path,
        domain=args.get("domain"),
        path_pattern=args.get("path_pattern"),
        method=args.get("method"),
        status_code=args.get("status_code", 200),
        response_headers=args.get("headers"),
        response_body=args.get("body"),
    )
    return json.dumps({"rule_id": rule_id})


def handle_mock_list(db_path: str, args: dict) -> str:
    rules = list_mock_rules(db_path)
    return json.dumps(rules, indent=2, default=str)


def handle_mock_remove(db_path: str, args: dict) -> str:
    remove_mock_rule(db_path, args["id"])
    return json.dumps({"removed": args["id"]})


def handle_mock_toggle(db_path: str, args: dict) -> str:
    toggle_mock_rule(db_path, args["id"], enabled=args.get("enabled", True))
    return json.dumps({"toggled": args["id"]})


def handle_mock_from_flow(db_path: str, args: dict) -> str:
    rule_id = mock_from_flow(db_path, args["flow_id"], status_code=args.get("status_code"))
    return json.dumps({"rule_id": rule_id})


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


from troxy.mcp.tools import TOOL_SCHEMAS

_HANDLERS = {
    "troxy_list_flows": handle_list_flows,
    "troxy_get_flow": handle_get_flow,
    "troxy_search": handle_search,
    "troxy_export": handle_export,
    "troxy_status": handle_status,
    "troxy_mock_add": handle_mock_add,
    "troxy_mock_list": handle_mock_list,
    "troxy_mock_remove": handle_mock_remove,
    "troxy_mock_toggle": handle_mock_toggle,
    "troxy_mock_from_flow": handle_mock_from_flow,
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
