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
    results = list_flows(
        db_path,
        domain=args.get("domain"),
        status=args.get("status"),
        method=args.get("method"),
        path=args.get("path"),
        limit=args.get("limit", 10),
    )
    return json.dumps(results, indent=2, default=str)


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


TOOLS = {
    "troxy_list_flows": {
        "handler": handle_list_flows,
        "description": "List captured HTTP flows. IMPORTANT: Always set limit (default 10). Use domain/status/method/path filters to narrow results.",
        "schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Filter by domain (partial match, e.g. 'watcha')"},
                "status": {"type": "integer", "description": "Filter by HTTP status code (e.g. 401)"},
                "method": {"type": "string", "description": "Filter by HTTP method (e.g. POST)"},
                "path": {"type": "string", "description": "Filter by path (partial match)"},
                "limit": {"type": "integer", "description": "Max results to return. Default 10. Use small values.", "default": 10},
            },
        },
    },
    "troxy_get_flow": {
        "handler": handle_get_flow,
        "description": "Get details of a specific flow by ID. Use part='body' to get only request/response bodies.",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Flow ID"},
                "part": {"type": "string", "enum": ["all", "request", "response", "body"], "description": "Which part to return. 'body' returns only bodies (smallest)."},
            },
            "required": ["id"],
        },
    },
    "troxy_search": {
        "handler": handle_search,
        "description": "Search flow headers and bodies for text. Returns matching flows.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for"},
                "domain": {"type": "string", "description": "Limit search to domain"},
                "scope": {"type": "string", "enum": ["all", "request", "response"], "default": "all"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    "troxy_export": {
        "handler": handle_export,
        "description": "Export a flow as a curl or httpie command string",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Flow ID"},
                "format": {"type": "string", "enum": ["curl", "httpie"], "default": "curl"},
            },
            "required": ["id"],
        },
    },
    "troxy_status": {
        "handler": handle_status,
        "description": "Get database status: flow count, DB size, path",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_mock_add": {
        "handler": handle_mock_add,
        "description": "Add a mock response rule. Matching requests get fake response instead of hitting server.",
        "schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "path_pattern": {"type": "string", "description": "Glob pattern for path"},
                "method": {"type": "string"},
                "status_code": {"type": "integer", "default": 200},
                "headers": {"type": "string", "description": "JSON string of response headers"},
                "body": {"type": "string", "description": "Response body string"},
            },
        },
    },
    "troxy_mock_list": {
        "handler": handle_mock_list,
        "description": "List all mock rules",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_mock_remove": {
        "handler": handle_mock_remove,
        "description": "Remove a mock rule by ID",
        "schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    "troxy_mock_toggle": {
        "handler": handle_mock_toggle,
        "description": "Enable or disable a mock rule",
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "enabled": {"type": "boolean"}},
            "required": ["id"],
        },
    },
    "troxy_mock_from_flow": {
        "handler": handle_mock_from_flow,
        "description": "Create a mock rule from an existing flow's response",
        "schema": {
            "type": "object",
            "properties": {"flow_id": {"type": "integer"}, "status_code": {"type": "integer"}},
            "required": ["flow_id"],
        },
    },
    "troxy_intercept_add": {
        "handler": handle_intercept_add,
        "description": "Add an intercept rule to hold matching requests",
        "schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}, "path_pattern": {"type": "string"}, "method": {"type": "string"}},
        },
    },
    "troxy_intercept_list": {
        "handler": handle_intercept_list,
        "description": "List intercept rules",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_intercept_remove": {
        "handler": handle_intercept_remove,
        "description": "Remove an intercept rule",
        "schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    "troxy_pending_list": {
        "handler": handle_pending_list,
        "description": "List intercepted pending flows waiting for release",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_modify": {
        "handler": handle_modify,
        "description": "Modify a pending flow's headers or body before releasing",
        "schema": {
            "type": "object",
            "properties": {"pending_id": {"type": "integer"}, "headers": {"type": "string"}, "body": {"type": "string"}},
            "required": ["pending_id"],
        },
    },
    "troxy_release": {
        "handler": handle_release,
        "description": "Release a pending flow to continue to server",
        "schema": {"type": "object", "properties": {"pending_id": {"type": "integer"}}, "required": ["pending_id"]},
    },
    "troxy_drop": {
        "handler": handle_drop,
        "description": "Drop a pending flow (cancel request)",
        "schema": {"type": "object", "properties": {"pending_id": {"type": "integer"}}, "required": ["pending_id"]},
    },
}


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
