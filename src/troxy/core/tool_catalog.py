"""Tool catalog — static metadata describing MCP tools.

Lives in core so both cli (discovery: `troxy mcp-tools`) and mcp (server schemas)
can import it without violating layer dependency rules.
"""

TOOL_SCHEMAS = {
    "troxy_list_flows": {
        "description": "List captured HTTP flows. IMPORTANT: Always set limit (default 10). Use domain/status/method/path/since filters to narrow results.",
        "schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Filter by domain (partial match, e.g. 'example.com')"},
                "status": {"type": "integer", "description": "Filter by HTTP status code (e.g. 401)"},
                "method": {"type": "string", "description": "Filter by HTTP method (e.g. POST)"},
                "path": {"type": "string", "description": "Filter by path (partial match)"},
                "since": {"type": "string", "description": "Relative time filter like '5m', '1h', '30s', '2d'"},
                "limit": {"type": "integer", "description": "Max results to return. Default 10. Use small values.", "default": 10},
            },
        },
    },
    "troxy_get_flow": {
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
        "description": "Get database status: flow count, DB size, path",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_mock_add": {
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
        "description": "List all mock rules",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_mock_remove": {
        "description": "Remove a mock rule by ID",
        "schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    "troxy_mock_toggle": {
        "description": "Enable or disable a mock rule",
        "schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "enabled": {"type": "boolean"}},
            "required": ["id"],
        },
    },
    "troxy_mock_from_flow": {
        "description": "Create a mock rule from an existing flow's response",
        "schema": {
            "type": "object",
            "properties": {"flow_id": {"type": "integer"}, "status_code": {"type": "integer"}},
            "required": ["flow_id"],
        },
    },
    "troxy_intercept_add": {
        "description": "Add an intercept rule to hold matching requests",
        "schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}, "path_pattern": {"type": "string"}, "method": {"type": "string"}},
        },
    },
    "troxy_intercept_list": {
        "description": "List intercept rules",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_intercept_remove": {
        "description": "Remove an intercept rule",
        "schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    "troxy_pending_list": {
        "description": "List intercepted pending flows waiting for release",
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_modify": {
        "description": "Modify a pending flow's headers or body before releasing",
        "schema": {
            "type": "object",
            "properties": {"pending_id": {"type": "integer"}, "headers": {"type": "string"}, "body": {"type": "string"}},
            "required": ["pending_id"],
        },
    },
    "troxy_release": {
        "description": "Release a pending flow to continue to server",
        "schema": {"type": "object", "properties": {"pending_id": {"type": "integer"}}, "required": ["pending_id"]},
    },
    "troxy_drop": {
        "description": "Drop a pending flow (cancel request)",
        "schema": {"type": "object", "properties": {"pending_id": {"type": "integer"}}, "required": ["pending_id"]},
    },
}
