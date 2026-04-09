# Architecture

```
mitmproxy -s src/troxy/addon.py
         │
    troxy addon (response/request hooks)
         │ writes
         ▼
    SQLite (flows.db)
         │ reads
    ┌────┴────┐
    ▼         ▼
  troxy     troxy
  CLI       MCP Server
```

## Layers

| Layer | Path | Imports | Responsibility |
|-------|------|---------|---------------|
| addon | `src/troxy/addon.py` | mitmproxy, core | Capture flows, mock, intercept |
| core | `src/troxy/core/` | sqlite3 only | DB, query, store, export, mock rules, intercept rules |
| cli | `src/troxy/cli/` | core, click, rich | Terminal commands |
| mcp | `src/troxy/mcp/` | core, mcp SDK | MCP tool server |

## Dependency Rule

`addon → core ← cli, mcp`

Cross-layer imports are forbidden. core is the shared foundation.
