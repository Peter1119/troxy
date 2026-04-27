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
        "description": "Get details of a specific flow by ID. Use part='body' to get only request/response bodies, or part='form' to get the request body parsed as application/x-www-form-urlencoded (URL-decoded key=value map; long base64-like values summarized).",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Flow ID"},
                "part": {"type": "string", "enum": ["all", "request", "response", "body", "form"], "description": "Which part to return. 'body' returns only bodies (smallest). 'form' returns the request body parsed as form-urlencoded — fails if the request content-type is not form-urlencoded."},
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
        "description": (
            "Add a mock response rule. For a single static response, use status_code/body/headers. "
            "For a sequence of responses that rotate on each request (e.g. 200→401→500→200), "
            "use the 'sequence' parameter with an array of step objects — this replaces multiple "
            "troxy_mock_add calls with one. Set loop=true to cycle back to step 1 after the last "
            "step; default is to repeat the last step indefinitely."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to match (e.g. 'api.example.com'). Omit to match all."},
                "path_pattern": {"type": "string", "description": "Glob pattern for path (e.g. '/pay', '/user/*')"},
                "method": {"type": "string", "description": "HTTP method (GET, POST, etc.). Omit to match all."},
                "status_code": {"type": "integer", "default": 200, "description": "Response status code. Used only when 'script' is not provided."},
                "headers": {"type": "string", "description": "JSON string of response headers. Used only when 'script' is not provided."},
                "body": {"type": "string", "description": "Response body string. Used only when 'script' is not provided."},
                "name": {"type": "string", "description": "Optional name for easy reference in reset/remove calls."},
                "sequence": {
                    "type": "array",
                    "description": "Array of response steps for a scripted/sequential mock. Provide instead of status_code/body/headers.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "status_code": {"type": "integer", "description": "HTTP status code for this step (required)"},
                            "body": {"type": "string", "description": "Response body for this step"},
                            "headers": {"type": "string", "description": "JSON string of response headers for this step"},
                        },
                        "required": ["status_code"],
                    },
                },
                "loop": {"type": "boolean", "default": False, "description": "When sequence is provided: if true, cycle back to step 1. If false (default), repeat last step."},
            },
        },
    },
    "troxy_mock_list": {
        "description": "List all mock rules and scripted scenario rules. Scripted rules include script_steps and current_step fields.",
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
        "description": "Create a mock rule from an existing flow's response. Set enabled=true to activate immediately.",
        "schema": {
            "type": "object",
            "properties": {
                "flow_id": {"type": "integer"},
                "status_code": {"type": "integer"},
                "body": {"type": "string", "description": "Override response body"},
                "headers": {"type": "string", "description": "Override response headers as JSON string"},
                "enabled": {"type": "boolean", "default": True, "description": "Enable the rule immediately (default: true)"},
                "name": {"type": "string", "description": "Optional name for the rule"},
            },
            "required": ["flow_id"],
        },
    },
    "troxy_mock_reset": {
        "description": "Reset a scripted mock rule's sequence back to step 1. Use after running through the sequence to replay from the beginning.",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Scenario rule ID (from troxy_mock_list or troxy_mock_add)"},
                "name": {"type": "string", "description": "Scenario rule name (alternative to id)"},
            },
        },
    },
    "troxy_mock_update": {
        "description": "Update an existing mock rule in-place. Only provided fields are updated — others remain unchanged.",
        "schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Mock rule ID to update"},
                "name": {"type": "string", "description": "Mock rule name (alternative to id)"},
                "status_code": {"type": "integer", "description": "New status code (single-response rules only)"},
                "body": {"type": "string", "description": "New response body"},
                "headers": {"type": "string", "description": "New response headers as JSON string"},
                "sequence": {
                    "type": "array",
                    "description": "Replace entire step sequence for scripted rules",
                    "items": {
                        "type": "object",
                        "properties": {
                            "status_code": {"type": "integer"},
                            "body": {"type": "string"},
                            "headers": {"type": "string"},
                        },
                        "required": ["status_code"],
                    },
                },
                "new_name": {"type": "string", "description": "Rename the rule to this new name"},
                "loop": {"type": "boolean", "description": "Change loop behavior for scripted rules"},
                "enabled": {"type": "boolean", "description": "Enable or disable the rule"},
            },
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
