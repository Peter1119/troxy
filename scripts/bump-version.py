#!/usr/bin/env python3
"""
bump-version — semver bump + CHANGELOG management for troxy.

Skips silently if [Unreleased] section is empty (no-op release guard).

Usage:
  python scripts/bump-version.py [patch|minor|major] [--dry-run] [--push]
"""
import os
import re
import sys
import argparse
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "peter1119",
    "GIT_AUTHOR_EMAIL": "peter1119@users.noreply.github.com",
    "GIT_COMMITTER_NAME": "peter1119",
    "GIT_COMMITTER_EMAIL": "peter1119@users.noreply.github.com",
}


def read_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("version not found in pyproject.toml")
    return m.group(1)


def bump(version: str, part: str) -> str:
    major, minor, patch = map(int, version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def unreleased_is_empty() -> bool:
    """Return True if [Unreleased] has no substantive content."""
    text = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"## \[Unreleased\]\n(.*?)(?=^## \[|\Z)", text, re.DOTALL | re.MULTILINE)
    if not m:
        return True
    return not m.group(1).strip()


def update_pyproject(old: str, new: str, dry_run: bool) -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text()
    updated = text.replace(f'version = "{old}"', f'version = "{new}"', 1)
    if updated == text:
        raise RuntimeError("Version string not found in pyproject.toml — nothing replaced.")
    if dry_run:
        print(f"  [dry-run] pyproject.toml: {old} → {new}")
    else:
        path.write_text(updated)


def update_changelog(new_version: str, dry_run: bool) -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text()
    today = date.today().isoformat()
    # Insert versioned header directly after [Unreleased]
    updated = text.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n## [{new_version}] — {today}",
        1,
    )
    if updated == text:
        raise RuntimeError("[Unreleased] header not found in CHANGELOG.md.")
    if dry_run:
        print(f"  [dry-run] CHANGELOG.md: inserted [{new_version}] — {today}")
    else:
        path.write_text(updated)


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True, env=GIT_ENV)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump troxy version and update CHANGELOG.")
    parser.add_argument("part", choices=["patch", "minor", "major"], nargs="?", default="patch")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing files.")
    parser.add_argument("--push", action="store_true", help="Push main branch and tag to origin after commit.")
    args = parser.parse_args()

    if unreleased_is_empty():
        print("⏭  [Unreleased] is empty — skipping release (no-op guard).")
        sys.exit(0)

    old = read_version()
    new = bump(old, args.part)
    print(f"{'[dry-run] ' if args.dry_run else ''}Bumping {old} → {new}  ({args.part})")

    update_pyproject(old, new, args.dry_run)
    update_changelog(new, args.dry_run)

    if args.dry_run:
        print("✓  Dry run complete — no files changed, no commits made.")
        return

    git("add", "pyproject.toml", "CHANGELOG.md")
    git("commit", "-m", f"chore(release): bump to v{new}")
    git("tag", f"v{new}")
    print(f"✓  Committed and tagged v{new}")

    if args.push:
        git("push", "origin", "main")
        git("push", "origin", f"v{new}")
        print(f"✓  Pushed — GitHub Actions will publish v{new} to PyPI and update Homebrew.")
    else:
        print(f"  Run: git push origin main && git push origin v{new}")
        print("  That will trigger the release CI (PyPI publish + Homebrew formula update).")


if __name__ == "__main__":
    main()
