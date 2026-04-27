"""Parse filter expressions like 'host:X status:4xx method:POST'."""

import re


def parse_filter(text: str) -> dict:
    if not text or not text.strip():
        return {}

    result = {}
    freetext_parts = []
    tokens = text.strip().split()

    for token in tokens:
        if ":" in token:
            key, value = token.split(":", 1)
            key = key.lower()

            if key == "host":
                result["domain"] = value
            elif key == "status":
                match = re.match(r"^(\d)xx$", value, re.IGNORECASE)
                if match:
                    base = int(match.group(1)) * 100
                    result["status_range"] = (base, base + 99)
                else:
                    try:
                        result["status"] = int(value)
                    except ValueError:
                        # Non-numeric status (e.g. user typed text) → treat as freetext
                        # so the filter UI doesn't crash, just no status match.
                        freetext_parts.append(token)
            elif key == "method":
                result["method"] = value.upper()
            elif key == "path":
                result["path"] = value
            else:
                freetext_parts.append(token)
        else:
            freetext_parts.append(token)

    if freetext_parts:
        result["query"] = " ".join(freetext_parts)

    return result
