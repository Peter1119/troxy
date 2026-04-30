"""External editor integration for MockDialog body editing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App


class EditorNotFoundError(Exception):
    """No usable editor binary found on PATH."""


class EditorIOError(Exception):
    """Temporary file read/write failure."""


class EditorCancelledError(Exception):
    """User closed editor without saving (returncode != 0)."""


def resolve_editor() -> str | None:
    """Return the first usable editor command via fallback chain.

    Chain: $VISUAL → $EDITOR → nano → vi → None
    Uses shutil.which() to verify the binary exists on PATH.
    """
    for env_var in ("VISUAL", "EDITOR"):
        cmd = os.environ.get(env_var)
        if cmd and shutil.which(cmd):
            return cmd
    for fallback in ("nano", "vi"):
        if shutil.which(fallback):
            return fallback
    return None


def ext_for_content_type(content_type: str | None) -> str:
    """Return a file extension for the given MIME type.

    Used to give the temp file a meaningful extension so editors can
    apply syntax highlighting.
    """
    if not content_type:
        return ".txt"
    ct = content_type.lower()
    if "json" in ct:
        return ".json"
    if "xml" in ct:
        return ".xml"
    if "html" in ct:
        return ".html"
    return ".txt"


def prettify_body(body: str, content_type: str | None) -> str:
    """Pretty-print body when content_type is JSON; return verbatim otherwise.

    Invalid JSON falls through to the raw string — editing a mock should
    never silently corrupt the user's payload.
    """
    if not body:
        return ""
    if content_type and "json" in content_type.lower():
        try:
            return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass
    return body


def validate_json_body(body: str) -> tuple[bool, str]:
    """Validate body as JSON.

    Returns (True, "") on success or empty body.
    Returns (False, "<human message>") on parse error with line/col.
    """
    if not body.strip():
        return True, ""
    try:
        json.loads(body)
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"JSON 오류: {e.lineno}행 {e.colno}열 — {e.msg}"
