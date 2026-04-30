"""Claude MCP hint helpers.

Hints are only shown when:
1. User hasn't explicitly disabled via `TROXY_HINTS=0` or `--no-hint`, AND
2. troxy MCP is actually registered with Claude Code (so the suggestion works).

Detection runs once per process and is cached.
"""

import os
import shutil
import subprocess

_cached: bool | None = None


def hints_enabled(cli_no_hint: bool = False) -> bool:
    """Return True if Claude hints should be shown for this invocation."""
    if cli_no_hint:
        return False
    env = os.environ.get("TROXY_HINTS", "").lower()
    if env in ("0", "off", "false", "no"):
        return False
    if env in ("1", "on", "true", "yes"):
        return True
    return _mcp_registered()


def _mcp_registered() -> bool:
    """Best-effort check whether troxy MCP is registered with Claude Code.

    Cached. Never raises — if claude CLI is missing or times out, returns False.
    """
    global _cached
    if _cached is not None:
        return _cached
    if not shutil.which("claude"):
        _cached = False
        return False
    try:
        result = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True, text=True, timeout=2,
        )
        _cached = result.returncode == 0 and "troxy" in result.stdout.lower()
    except Exception:
        _cached = False
    return _cached


def flow_hint(flow_id: int) -> str:
    """Short hint shown after `troxy flow` output."""
    return (
        f"\n💡 Claude에 물어보세요: \"troxy_get_flow({flow_id})\" 또는 "
        f"\"flow {flow_id}이 {{status}}를 반환한 이유는?\""
    )


def explain_hint(flow_id: int) -> str:
    """Hint shown after `troxy explain` when heuristics are exhausted."""
    return (
        f"\n💡 더 자세한 분석이 필요하다면 Claude에: "
        f"\"troxy_get_flow({flow_id}, part='response')\" 후 설명 요청"
    )
