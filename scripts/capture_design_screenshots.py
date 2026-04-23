"""Capture SVG screenshots of each TUI screen for design review.

Run via:
    uv run python scripts/capture_design_screenshots.py

Outputs:
    docs/qa-screenshots/list-5.svg          — list screen with 5 flows
    docs/qa-screenshots/list-20.svg         — list screen with 20 flows
    docs/qa-screenshots/list-filter.svg     — list screen with filter active
    docs/qa-screenshots/detail-200.svg      — detail screen (2xx)
    docs/qa-screenshots/detail-500.svg      — detail screen (5xx)
    docs/qa-screenshots/mock-dialog.svg     — mock dialog open
    docs/qa-screenshots/mock-list.svg       — mock list screen
    docs/qa-screenshots/copy-modal.svg      — copy modal open
"""

import asyncio
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from troxy.core.db import init_db  # noqa: E402
from troxy.core.mock import add_mock_rule  # noqa: E402
from troxy.core.store import insert_flow  # noqa: E402
from troxy.tui.app import TroxyStartApp  # noqa: E402


import os

OUT_DIR = Path(
    os.environ.get(
        "TROXY_SS_DIR",
        str(Path(__file__).resolve().parent.parent / "docs" / "qa-screenshots"),
    )
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

HOSTS = [
    "api.example.com",
    "api.example.com",
    "cdn.example.com",
    "auth.example.com",
    "graphql.example.com",
]
PATHS = [
    "/api/v2/users/12345/ratings",
    "/api/v2/movies/99/reviews",
    "/api/v1/search",
    "/api/v2/auth/token",
    "/health",
    "/api/v2/contents/abc123/episodes",
    "/api/v1/config",
    "/api/v2/notifications",
    "/api/v2/users/12345/watchlist",
    "/api/v2/movies/99/similar",
]
METHODS = ["GET", "GET", "GET", "POST", "PUT", "DELETE", "PATCH", "GET", "POST", "GET"]
STATUSES = [200, 200, 200, 201, 200, 204, 302, 401, 404, 500]


def seed(db: str, n: int) -> None:
    init_db(db)
    base = time.time() - n
    for i in range(n):
        insert_flow(
            db,
            timestamp=base + i,
            method=METHODS[i % len(METHODS)],
            scheme="https",
            host=HOSTS[i % len(HOSTS)],
            port=443,
            path=PATHS[i % len(PATHS)],
            query=f"page={i}" if i % 3 == 0 else None,
            request_headers={"Accept": "application/json", "Authorization": "Bearer tok"},
            request_body=None if METHODS[i % len(METHODS)] == "GET" else f'{{"idx": {i}}}',
            request_content_type=None if METHODS[i % len(METHODS)] == "GET" else "application/json",
            status_code=STATUSES[i % len(STATUSES)],
            response_headers={"Content-Type": "application/json"},
            response_body=f'{{"ok": true, "index": {i}, "timestamp": "{time.strftime("%Y-%m-%dT%H:%M:%SZ")}"}}',
            response_content_type="application/json",
            duration_ms=10.0 + (i % 100),
        )


async def shoot(app: TroxyStartApp, out: Path, pre_key_seq: list[str] | None = None) -> None:
    async with app.run_test(size=(120, 36)) as pilot:
        if pre_key_seq:
            for k in pre_key_seq:
                if k.startswith("wait:"):
                    await pilot.pause(float(k.split(":", 1)[1]))
                else:
                    await pilot.press(k)
        await pilot.pause(0.1)
        svg = app.export_screenshot(title=out.stem)
        out.write_text(svg)
        print(f"  ✓ {out.relative_to(OUT_DIR.parent.parent)}")


async def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        # List screens
        db5 = f"{td}/list5.db"
        seed(db5, 5)
        await shoot(TroxyStartApp(db_path=db5), OUT_DIR / "list-5.svg")

        db20 = f"{td}/list20.db"
        seed(db20, 20)
        await shoot(TroxyStartApp(db_path=db20), OUT_DIR / "list-20.svg")

        await shoot(
            TroxyStartApp(db_path=db20),
            OUT_DIR / "list-filter.svg",
            pre_key_seq=["f", "wait:0.1", "s", "t", "a", "t", "u", "s", ":", "4", "x", "x", "enter"],
        )

        # Detail screens (use db20 — 20 flows ensures varied status codes)
        # Press enter on first row (index 0 = id 20, status from idx 19 = 404)
        await shoot(
            TroxyStartApp(db_path=db20),
            OUT_DIR / "detail-404.svg",
            pre_key_seq=["enter"],
        )
        # Navigate down to find a 200 flow — index 9 from bottom is status idx 10 = 200
        await shoot(
            TroxyStartApp(db_path=db20),
            OUT_DIR / "detail-200.svg",
            pre_key_seq=["down", "down", "down", "down", "down", "enter"],
        )

        # Mock dialog
        await shoot(
            TroxyStartApp(db_path=db20),
            OUT_DIR / "mock-dialog.svg",
            pre_key_seq=["m"],
        )

        # Copy modal
        await shoot(
            TroxyStartApp(db_path=db20),
            OUT_DIR / "copy-modal.svg",
            pre_key_seq=["enter", "y"],
        )

        # Mock list (populate with a rule first)
        dbm = f"{td}/mocks.db"
        seed(dbm, 10)
        for i in range(4):
            add_mock_rule(
                dbm,
                domain=HOSTS[i],
                path_pattern=PATHS[i].replace("12345", "*").replace("99", "*").replace("abc123", "*"),
                method=METHODS[i],
                status_code=STATUSES[i],
                response_headers='{"Content-Type": "application/json"}',
                response_body='{"ok": true}',
                name=f"mock-{i}",
            )
        await shoot(
            TroxyStartApp(db_path=dbm),
            OUT_DIR / "mock-list.svg",
            pre_key_seq=["shift+m"],
        )


if __name__ == "__main__":
    print(f"Writing screenshots to {OUT_DIR}")
    asyncio.run(main())
    print("Done.")
