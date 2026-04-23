"""mitmproxy addon — records flows to SQLite.

Usage: mitmproxy -s path/to/addon.py
Set TROXY_DB env var to control database path.
"""

import fnmatch
import json
import os
import sys
import threading
import time as time_mod

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
        self._intercepted_flows = {}  # flow.id -> flow
        self._poll_thread = threading.Thread(target=self._poll_pending, daemon=True)
        self._poll_thread.start()

    def request(self, flow):
        """Check mock rules, then intercept rules."""
        try:
            self._check_mock(flow)
            if not flow.response:  # not mocked
                self._check_intercept(flow)
        except Exception as e:
            print(f"[troxy] Error in request hook: {e}", file=sys.stderr)

    @staticmethod
    def _safe_query(request) -> str | None:
        """Extract raw query string from request URL."""
        url = request.pretty_url or request.url or ""
        if "?" in url:
            return url.split("?", 1)[1]
        return None

    @staticmethod
    def _safe_headers(headers) -> dict:
        """Convert any header type to plain dict."""
        try:
            return {str(k): str(v) for k, v in headers.items()}
        except Exception:
            return {}

    @staticmethod
    def _safe_body(content) -> bytes | None:
        """Ensure body is bytes or None."""
        if content is None:
            return None
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode("utf-8")
        return str(content).encode("utf-8")

    def response(self, flow):
        """Called when a response is received."""
        try:
            request = flow.request
            response = flow.response

            content_type_req = str(request.headers.get("content-type", ""))
            content_type_resp = str(response.headers.get("content-type", ""))

            duration = None
            if flow.response.timestamp_end and flow.request.timestamp_start:
                duration = (flow.response.timestamp_end - flow.request.timestamp_start) * 1000

            insert_flow(
                self.db_path,
                timestamp=flow.request.timestamp_start or time_mod.time(),
                method=str(request.method),
                scheme=str(request.scheme),
                host=str(request.host),
                port=int(request.port),
                path=str(request.path),
                query=self._safe_query(request),
                request_headers=self._safe_headers(request.headers),
                request_body=self._safe_body(request.content),
                request_content_type=content_type_req or None,
                status_code=int(response.status_code),
                response_headers=self._safe_headers(response.headers),
                response_body=self._safe_body(response.content),
                response_content_type=content_type_resp or None,
                duration_ms=duration,
            )
        except Exception as e:
            print(f"[troxy] Error recording flow: {e}", file=sys.stderr)

    def _check_mock(self, flow):
        from troxy.core.mock import list_mock_rules
        from mitmproxy import http
        rules = list_mock_rules(self.db_path, enabled_only=True)
        for rule in rules:
            if rule["domain"] and rule["domain"] not in flow.request.host:
                continue
            if rule["method"] and rule["method"].upper() != flow.request.method:
                continue
            if rule["path_pattern"] and not fnmatch.fnmatch(flow.request.path, rule["path_pattern"]):
                continue
            headers = {}
            if rule["response_headers"]:
                headers = json.loads(rule["response_headers"])
            body = (rule["response_body"] or "").encode("utf-8")
            flow.response = http.Response.make(rule["status_code"], body, headers)
            conn = get_connection(self.db_path)
            conn.execute(
                "UPDATE mock_rules SET hit_count = hit_count + 1, last_hit_at = ? WHERE id = ?",
                (time_mod.time(), rule["id"]),
            )
            conn.commit()
            conn.close()
            return

    def _check_intercept(self, flow):
        from troxy.core.intercept import list_intercept_rules, add_pending_flow
        rules = list_intercept_rules(self.db_path, enabled_only=True)
        for rule in rules:
            if rule["domain"] and rule["domain"] not in flow.request.host:
                continue
            if rule["method"] and rule["method"].upper() != flow.request.method:
                continue
            if rule["path_pattern"] and not fnmatch.fnmatch(flow.request.path, rule["path_pattern"]):
                continue
            flow.intercept()
            add_pending_flow(
                self.db_path,
                flow_id=flow.id,
                method=flow.request.method,
                host=flow.request.host,
                path=flow.request.path,
                request_headers=json.dumps({k: v for k, v in flow.request.headers.items()}),
                request_body=flow.request.content.decode("utf-8", errors="replace") if flow.request.content else None,
            )
            self._intercepted_flows[flow.id] = flow
            return

    def _poll_pending(self):
        from troxy.core.intercept import get_pending_flow
        while True:
            try:
                conn = get_connection(self.db_path)
                rows = conn.execute(
                    "SELECT * FROM pending_flows WHERE status IN ('released', 'modified', 'dropped')"
                ).fetchall()
                conn.close()
                for row in rows:
                    row = dict(row)
                    flow = self._intercepted_flows.pop(row["flow_id"], None)
                    if flow and row["status"] == "dropped":
                        flow.kill()
                    elif flow and row["status"] in ("released", "modified"):
                        if row["status"] == "modified":
                            if row.get("request_headers"):
                                headers = json.loads(row["request_headers"])
                                for k, v in headers.items():
                                    flow.request.headers[k] = v
                            if row.get("request_body"):
                                flow.request.content = row["request_body"].encode("utf-8")
                        flow.resume()
                    conn2 = get_connection(self.db_path)
                    conn2.execute("DELETE FROM pending_flows WHERE id = ?", (row["id"],))
                    conn2.commit()
                    conn2.close()
            except Exception as e:
                print(f"[troxy] Poll error: {e}", file=sys.stderr)
            time_mod.sleep(0.3)


addons = [TroxyAddon()]
