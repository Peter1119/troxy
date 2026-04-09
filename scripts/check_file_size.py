#!/usr/bin/env python3
"""Check that no Python source file exceeds 300 lines."""

import sys
from pathlib import Path

MAX_LINES = 300
VIOLATIONS = []

def main():
    for f in Path("src").rglob("*.py"):
        lines = len(f.read_text().splitlines())
        if lines > MAX_LINES:
            VIOLATIONS.append(f"{f}: {lines} lines (max {MAX_LINES})")

    if VIOLATIONS:
        print("File size violations:")
        for v in VIOLATIONS:
            print(f"  {v}")
        sys.exit(1)
    print("File sizes OK.")

if __name__ == "__main__":
    main()
