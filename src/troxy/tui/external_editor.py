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
