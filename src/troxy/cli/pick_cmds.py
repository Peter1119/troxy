"""troxy pick — interactive flow picker (curses-based).

Requires a TTY. Falls back to a helpful error message in non-TTY / CI / piped contexts.
"""

import curses
import sys

import click

from troxy.core.db import init_db
from troxy.core.query import list_flows, get_flow
from troxy.cli.utils import _resolve_db, _apply_no_color, _common_options


@click.command("pick")
@_common_options
@click.option("-d", "--domain", default=None, help="Pre-filter by domain")
@click.option("-s", "--status", default=None, type=int, help="Pre-filter by status code")
@click.option("-n", "--limit", default=100, type=int,
              help="Max flows to load (default 100; large values hurt responsiveness)")
@click.option("--last", default=None, type=int,
              help="Non-TTY fallback: print the last N flow IDs instead of opening picker")
def pick_cmd(db, no_color, domain, status, limit, last):
    """Interactive flow picker — arrow keys to browse, Enter to see detail."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)

    flows = list_flows(db_path, domain=domain, status=status, limit=limit)
    if not flows:
        click.echo("No flows to pick.")
        return

    if not sys.stdout.isatty() or not sys.stdin.isatty():
        if last is not None:
            for f in flows[:last]:
                click.echo(
                    f"{f['id']}\t{f['method']}\t{f['host']}{f['path']}\t{f['status_code']}"
                )
            return
        click.echo(
            "troxy pick requires an interactive terminal. "
            "Use `troxy flows` (table) or `troxy pick --last 10` (tab-separated list) instead.",
            err=True,
        )
        sys.exit(1)

    chosen_id = curses.wrapper(_pick_loop, flows)
    if chosen_id is None:
        return

    flow = get_flow(db_path, chosen_id)
    if not flow:
        click.echo(f"Flow {chosen_id} not found.", err=True)
        sys.exit(1)

    from troxy.cli.formatting import print_flow_detail
    print_flow_detail(flow)


def _pick_loop(stdscr, flows):
    """Curses main loop. Returns chosen flow id, or None on cancel."""
    curses.curs_set(0)
    stdscr.keypad(True)
    cursor = 0
    top = 0

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.addnstr(
            0, 0,
            "troxy pick — ↑/↓ move, Enter=detail, q=quit",
            w - 1, curses.A_BOLD,
        )
        body_rows = max(h - 2, 1)

        if cursor < top:
            top = cursor
        elif cursor >= top + body_rows:
            top = cursor - body_rows + 1

        for i, f in enumerate(flows[top: top + body_rows]):
            idx = top + i
            line = _format_flow_line(f, w - 1)
            if idx == cursor:
                stdscr.addnstr(i + 1, 0, line, w - 1, curses.A_REVERSE)
            else:
                stdscr.addnstr(i + 1, 0, line, w - 1)

        stdscr.addnstr(
            h - 1, 0,
            f"[{cursor + 1}/{len(flows)}]  (Enter to inspect, q to cancel)",
            w - 1, curses.A_DIM,
        )
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q"), 27):  # q or ESC
            return None
        if ch in (curses.KEY_UP, ord("k")) and cursor > 0:
            cursor -= 1
        elif ch in (curses.KEY_DOWN, ord("j")) and cursor < len(flows) - 1:
            cursor += 1
        elif ch == curses.KEY_PPAGE:
            cursor = max(0, cursor - body_rows)
        elif ch == curses.KEY_NPAGE:
            cursor = min(len(flows) - 1, cursor + body_rows)
        elif ch == curses.KEY_HOME:
            cursor = 0
        elif ch == curses.KEY_END:
            cursor = len(flows) - 1
        elif ch in (curses.KEY_ENTER, 10, 13):
            return flows[cursor]["id"]


def _format_flow_line(f, width):
    prefix = f"[{f['id']:>5}] {f['method']:<6} {f['status_code']} "
    rest = f"{f['host']}{f['path']}"
    line = prefix + rest
    if len(line) > width:
        line = line[: width - 1] + "…"
    return line
