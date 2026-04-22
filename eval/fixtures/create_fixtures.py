#!/usr/bin/env python3
"""Generate evaluation fixture databases."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from troxy.core.db import init_db
from troxy.core.store import insert_flow


def create_auth_failure(path: str):
    init_db(path)
    now = time.time()
    insert_flow(path, timestamp=now - 10, method="GET", scheme="https",
                host="api.internal.com", port=443, path="/api/home", query=None,
                request_headers={"Authorization": "Bearer valid_token"},
                request_body=None, request_content_type=None,
                status_code=200, response_headers={"Content-Type": "application/json"},
                response_body='{"sections": []}', response_content_type="application/json",
                duration_ms=120)
    insert_flow(path, timestamp=now - 5, method="GET", scheme="https",
                host="api.internal.com", port=443, path="/api/users/17ov/ratings", query=None,
                request_headers={"Authorization": "Bearer expired_token"},
                request_body=None, request_content_type=None,
                status_code=401, response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized", "message": "Token has expired"}',
                response_content_type="application/json", duration_ms=30)
    insert_flow(path, timestamp=now, method="GET", scheme="https",
                host="api.internal.com", port=443, path="/api/users/17ov/report", query=None,
                request_headers={"Authorization": "Bearer expired_token"},
                request_body=None, request_content_type=None,
                status_code=401, response_headers={"Content-Type": "application/json"},
                response_body='{"error": "unauthorized", "message": "Token has expired"}',
                response_content_type="application/json", duration_ms=25)


def create_redirect_chain(path: str):
    init_db(path)
    now = time.time()
    insert_flow(path, timestamp=now - 2, method="GET", scheme="https",
                host="mandrillapp.com", port=443, path="/track/click/abc", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=302, response_headers={"Location": "https://staging-api.internal.com/confirm"},
                response_body=None, response_content_type=None, duration_ms=50)
    insert_flow(path, timestamp=now - 1, method="GET", scheme="https",
                host="staging-api.internal.com", port=443, path="/confirm", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=302, response_headers={"Location": "https://accounts.google.com/oauth"},
                response_body=None, response_content_type=None, duration_ms=40)
    insert_flow(path, timestamp=now, method="GET", scheme="https",
                host="accounts.google.com", port=443, path="/oauth", query=None,
                request_headers={}, request_body=None, request_content_type=None,
                status_code=200, response_headers={"Content-Type": "text/html"},
                response_body="<html>Access Denied</html>", response_content_type="text/html",
                duration_ms=200)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ("auth_failure.db", "redirect_chain.db"):
        path = os.path.join(script_dir, name)
        if os.path.exists(path):
            os.remove(path)
    create_auth_failure(os.path.join(script_dir, "auth_failure.db"))
    create_redirect_chain(os.path.join(script_dir, "redirect_chain.db"))
    print("Fixtures created.")
