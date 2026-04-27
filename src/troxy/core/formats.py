"""Format-specific body parsers (form-urlencoded, etc.)."""

import hashlib
import re
from urllib.parse import parse_qsl

_TRUNCATION_MARKER_RE = re.compile(r"\n\[truncated at \d+B\]\s*$")
_BASE64_LIKE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def _summarize_value(value: str, summary_threshold: int) -> str | dict:
    """Return value as-is if short, otherwise a summary dict with length / sha / preview."""
    if len(value) <= summary_threshold:
        return value
    sha = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
    preview = value[:64]
    if len(value) >= 100 and _BASE64_LIKE_RE.match(value):
        kind = "binary-base64"
    else:
        kind = "long-text"
    return {"_kind": kind, "len": len(value), "sha256": sha, "preview": preview}


def parse_form_body(body: str, *, summary_threshold: int = 256) -> dict:
    """Parse application/x-www-form-urlencoded body into a field map.

    Long values are summarized (length, sha256 prefix, preview) so the result stays
    small enough to return through MCP without truncating useful metadata. base64-like
    values get _kind="binary-base64" so callers can spot opaque payloads (e.g. PKCS7
    receipts) at a glance.

    Returns: {"fields": {...}, "truncated": bool}
             or {"error": ..., "reason": ...} on parse failure.
    """
    if not body:
        return {"fields": {}, "truncated": False}

    truncated = False
    if _TRUNCATION_MARKER_RE.search(body):
        body = _TRUNCATION_MARKER_RE.sub("", body)
        truncated = True

    try:
        pairs = parse_qsl(body, keep_blank_values=True, strict_parsing=False)
    except ValueError as e:
        return {"error": "form parse failed", "reason": str(e)}

    fields: dict[str, str | dict] = {}
    for key, value in pairs:
        fields[key] = _summarize_value(value, summary_threshold)

    return {"fields": fields, "truncated": truncated}
