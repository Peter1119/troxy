#!/bin/bash
# Setup troxy: install dependencies and show usage

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing dependencies..."
cd "$PROJECT_DIR"
uv sync --all-extras

echo ""
echo "=== Setup complete ==="
echo ""
echo "Usage:"
echo "  # Start mitmproxy with troxy addon:"
echo "  mitmproxy -s $PROJECT_DIR/src/troxy/addon.py"
echo ""
echo "  # Or add alias to your shell:"
echo "  alias mitmproxy-troxy='mitmproxy -s $PROJECT_DIR/src/troxy/addon.py'"
echo ""
echo "  # CLI:"
echo "  uv run troxy flows"
echo "  uv run troxy flow 1 --body"
echo "  uv run troxy search 'token'"
echo "  uv run troxy mock add -d api.example.com -p '/users' -s 200 --body '{\"mock\": true}'"
echo "  uv run troxy tail"
echo ""
echo "  # MCP server (add to Claude Code settings.json):"
echo "  {\"mcpServers\": {\"troxy\": {\"command\": \"uv\", \"args\": [\"--directory\", \"$PROJECT_DIR\", \"run\", \"python\", \"-m\", \"troxy.mcp.server\"]}}}"
