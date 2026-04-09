"""mitmproxy addon — records flows to SQLite.

Usage: mitmproxy -s path/to/addon.py
Set TROXY_DB env var to control database path.
"""

import json
import os
import sys
import time

# Ensure src/ is on path when running as mitmproxy script
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from troxy.core.db import default_db_path, init_db, get_connection
from troxy.core.store import insert_flow


class TroxyAddon:
    """mitmproxy addon that records flows to SQLite."""

    def __init__(self):
        self.db_path = default_db_path()
        init_db(self.db_path)

    def response(self, flow):
        """Called when a response is received."""
        try:
            request = flow.request
            response = flow.response

            content_type_req = request.headers.get("content-type", "")
            content_type_resp = response.headers.get("content-type", "")

            duration = None
            if flow.response.timestamp_end and flow.request.timestamp_start:
                duration = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000

            insert_flow(
                self.db_path,
                timestamp=flow.request.timestamp_start or time.time(),
                method=request.method,
                scheme=request.scheme,
                host=request.host,
                port=request.port,
                path=request.path,
                query=request.query if request.query else None,
                request_headers=dict(request.headers),
                request_body=request.content,
                request_content_type=content_type_req or None,
                status_code=response.status_code,
                response_headers=dict(response.headers),
                response_body=response.content,
                response_content_type=content_type_resp or None,
                duration_ms=duration,
            )
        except Exception as e:
            # Log but don't crash mitmproxy
            print(f"[troxy] Error recording flow: {e}", file=sys.stderr)


addons = [TroxyAddon()]
