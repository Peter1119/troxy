# troxy

> terminal + proxy = troxy

mitmproxy addon that records HTTP flows to SQLite, with a CLI and Claude MCP server for easy querying.

**Problem:** mitmproxy's TUI is hard to script and impossible for AI agents to navigate. Searching, filtering, and extracting request/response bodies requires manual interaction.

**Solution:** A mitmproxy addon silently records all flows to SQLite. Query them with a CLI or let Claude do it via MCP.

## Install

```bash
# From PyPI
pipx install troxy

# From source
git clone https://github.com/Peter1119/troxy.git
cd troxy
uv sync --all-extras
```

## Quick Start

```bash
# 1. Start mitmproxy with troxy addon
troxy start

# 2. Use your app through the proxy (port 8080)
# Flows are automatically recorded to ~/.troxy/flows.db

# 3. Query flows
troxy flows                              # list all flows
troxy flows -d api.example.com           # filter by domain
troxy flows -s 401                       # filter by status code
troxy flow 42 --body                     # view request/response body
troxy flow 42 --export curl              # export as curl command
troxy search "access_token"              # search across all bodies
troxy tail                               # stream new flows in real-time
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `troxy start` | Start mitmproxy with troxy addon |
| `troxy flows` | List captured flows (with filters) |
| `troxy flow ID` | Show flow details (headers, body) |
| `troxy search QUERY` | Search flow bodies for text |
| `troxy tail` | Stream new flows in real-time |
| `troxy status` | Show DB stats |
| `troxy clear` | Delete flows |
| `troxy mock add` | Add mock response rule |
| `troxy mock list` | List mock rules |
| `troxy mock from-flow ID` | Create mock from captured flow |
| `troxy intercept add` | Add request intercept rule |
| `troxy pending` | List intercepted flows |
| `troxy modify ID` | Modify intercepted request |
| `troxy release ID` | Release intercepted request |
| `troxy drop ID` | Drop intercepted request |
| `troxy replay ID` | Replay a captured request |
| `troxy flow ID --export curl` | Export as curl command |
| `troxy flow ID --export httpie` | Export as httpie command |

## Filtering

```bash
troxy flows -d watcha              # domain contains "watcha"
troxy flows -s 401                 # status code = 401
troxy flows -m POST                # method = POST
troxy flows -p /api/users          # path contains "/api/users"
troxy flows -n 5                   # limit to 5 results
troxy flows --since 5m             # last 5 minutes
troxy flows --json                 # JSON output
```

## Mock Responses

Inject fake responses without hitting the real server:

```bash
# Add a mock rule
troxy mock add -d api.example.com -p "/api/users/*" -s 200 \
  --body '{"id": 1, "name": "mock user"}'

# Create mock from a captured flow
troxy mock from-flow 42

# Manage rules
troxy mock list
troxy mock disable 1
troxy mock enable 1
troxy mock remove 1
```

## Request Interception

Intercept, modify, and release requests:

```bash
# Set up intercept rule
troxy intercept add -d api.example.com -m POST

# View intercepted requests
troxy pending

# Modify and release
troxy modify 1 --header "Authorization: Bearer new_token"
troxy release 1

# Or drop it
troxy drop 1
```

## Claude MCP Integration

Register troxy as an MCP server so Claude can query mitmproxy flows directly:

```bash
claude mcp add -e TROXY_DB=~/.troxy/flows.db -s user troxy -- \
  uv --directory /path/to/troxy run python -m troxy.mcp.server
```

Then ask Claude naturally:

- "Show me the 401 errors from watcha API"
- "What's in the response body of flow 233?"
- "Search for requests containing 'access_token'"
- "Export flow 42 as a curl command"

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `troxy_status` | DB stats |
| `troxy_list_flows` | List/filter flows |
| `troxy_get_flow` | Get flow detail |
| `troxy_search` | Search bodies |
| `troxy_export` | Export as curl/httpie |
| `troxy_mock_add` | Add mock rule |
| `troxy_mock_list` | List mock rules |
| `troxy_mock_remove` | Remove mock rule |
| `troxy_mock_toggle` | Enable/disable mock |
| `troxy_mock_from_flow` | Mock from flow |
| `troxy_intercept_add` | Add intercept rule |
| `troxy_intercept_list` | List intercept rules |
| `troxy_intercept_remove` | Remove intercept rule |
| `troxy_pending_list` | List pending flows |
| `troxy_modify` | Modify pending flow |
| `troxy_release` | Release pending flow |
| `troxy_drop` | Drop pending flow |

## Architecture

```
mitmproxy -s troxy/addon.py
         |
    troxy addon (request/response hooks)
         | writes
         v
    SQLite (~/.troxy/flows.db)
         | reads
    +----+----+
    v         v
  troxy     troxy
  CLI       MCP Server
```

- **addon** — runs inside mitmproxy, records flows, serves mocks, intercepts requests
- **core** — pure SQLite logic (no mitmproxy dependency)
- **cli** — click + rich terminal commands
- **mcp** — MCP server for Claude integration

## Configuration

| Priority | Source |
|----------|--------|
| 1 | `--db` CLI flag |
| 2 | `TROXY_DB` environment variable |
| 3 | `~/.troxy/flows.db` (default) |

## License

MIT
