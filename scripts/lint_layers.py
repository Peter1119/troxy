#!/usr/bin/env python3
"""Verify layer dependency rules.

core/ must not import mitmproxy.
cli/ and mcp/ must not import each other.
"""

import re
import sys
from pathlib import Path

VIOLATIONS = []

def check_file(path: Path, forbidden_imports: list[str]):
    content = path.read_text()
    for line_num, line in enumerate(content.splitlines(), 1):
        for forbidden in forbidden_imports:
            if re.search(rf"^\s*(from|import)\s+{forbidden}", line):
                VIOLATIONS.append(f"{path}:{line_num}: forbidden import '{forbidden}'")

def main():
    src = Path("src/troxy")
    for f in (src / "core").rglob("*.py"):
        check_file(f, ["mitmproxy"])
    for f in (src / "cli").rglob("*.py"):
        check_file(f, ["troxy.mcp", "mitmproxy"])
    for f in (src / "mcp").rglob("*.py"):
        check_file(f, ["troxy.cli", "mitmproxy"])

    if (src / "tui").exists():
        for f in (src / "tui").rglob("*.py"):
            check_file(f, ["mitmproxy", "troxy.cli", "troxy.mcp"])

    if VIOLATIONS:
        print("Layer dependency violations:")
        for v in VIOLATIONS:
            print(f"  {v}")
        sys.exit(1)
    print("Layer dependencies OK.")

if __name__ == "__main__":
    main()
