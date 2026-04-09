# troxy

Terminal proxy inspector. mitmproxy addon + CLI + MCP.

## Architecture

See ARCHITECTURE.md for layer diagram.

## Key Rules

- `src/troxy/core/` must NEVER import `mitmproxy`. It is pure SQLite logic.
- `src/troxy/addon.py` is the ONLY file that imports `mitmproxy`.
- `cli` and `mcp` depend on `core` only, never on each other.

## Testing

```bash
uv run pytest                    # all tests
uv run pytest tests/unit -v     # unit only
uv run pytest tests/e2e -v      # E2E only
```

## Lint

```bash
uv run python scripts/lint_layers.py    # check layer deps
uv run python scripts/check_file_size.py # check file sizes
```

## DB Location

Default: `~/.troxy/flows.db`
Override: `TROXY_DB` env var or `--db` CLI flag.
