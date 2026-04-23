"""Round 3 DetailScreen before/after capture with realistic payload.

Mirrors the user's real-world scenario that triggered the "detail 안이뻐"
feedback: long query-string URL, cookie header with URL-encoded session,
x-frograms-* proprietary headers, user-agent, auth bearer. Saves to
``docs/qa-screenshots/round3/before/`` (or ``after/`` when ``--after``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from troxy.core.db import init_db
from troxy.core.store import insert_flow
from troxy.tui.app import TroxyStartApp


REQUEST_HEADERS = {
    "host": "staging-api.example.com",
    "user-agent": "Example/10.4.2 (iPhone16,1; iOS 18.3; Scale/3.00)",
    "accept": "application/json",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "cookie": (
        "_guinness_session=UnZQY29EZ0tj%2FWYrOEVJd1BUS3pGV3M0Z2s%3D"
        "--Ny5Q1lOi9q%2FxH8c%3D;"
        " example_device_id=abc123-def456-ghi789;"
        " _ga=GA1.2.1234567890.1712345678"
    ),
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMyIsImV4cCI6MTcxMjUwMDAwMH0.signature",
    "x-frograms-app-version": "10.4.2",
    "x-frograms-device-type": "ios",
    "x-frograms-locale": "ko_KR",
}

RESPONSE_HEADERS = {
    "content-type": "application/json; charset=utf-8",
    "content-length": "45",
    "x-request-id": "req_a1b2c3d4e5f6",
    "cache-control": "no-store, max-age=0",
}


def seed(db: str) -> None:
    init_db(db)
    insert_flow(
        db,
        timestamp=time.time() - 12,
        method="GET",
        scheme="https",
        host="staging-api.example.com",
        port=443,
        path="/api/confirmations/status",
        query=(
            "registration_token="
            "d312f00acfd378634e955abfcfe8f78cb4983949f165cff7aa5cae765c2905da"
        ),
        request_headers=REQUEST_HEADERS,
        request_body=None,
        request_content_type=None,
        status_code=200,
        response_headers=RESPONSE_HEADERS,
        response_body='{"status":"confirmed","user_id":12345}',
        response_content_type="application/json",
        duration_ms=45.0,
    )


async def capture(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        db = f"{td}/round3.db"
        seed(db)
        app = TroxyStartApp(db_path=db)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("enter")
            await pilot.pause(0.1)
            svg = app.export_screenshot(title=out.stem)
            out.write_text(svg)
            print(f"  ✓ {out}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--after",
        action="store_true",
        help="Save to docs/qa-screenshots/round3/after/ (default: before/)",
    )
    args = parser.parse_args()
    tag = "after" if args.after else "before"
    out = REPO / "docs" / "qa-screenshots" / "round3" / tag / "detail.svg"
    await capture(out)


if __name__ == "__main__":
    asyncio.run(main())
