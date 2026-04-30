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
@click.option("-d", "--domain", default=None, help="도메인으로 사전 필터")
@click.option("-s", "--status", default=None, type=int, help="상태 코드로 사전 필터")
@click.option("-n", "--limit", default=100, type=int,
              help="최대 로드 flow 수 (기본 100; 클수록 반응 저하)")
@click.option("--last", default=None, type=int,
              help="비TTY 폴백: picker 대신 마지막 N개 flow ID 출력")
def pick_cmd(db, no_color, domain, status, limit, last):
    """대화형 flow 선택기 — 화살표로 이동, Enter로 상세 보기."""
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)

    flows = list_flows(db_path, domain=domain, status=status, limit=limit)
    if not flows:
        click.echo("선택할 flow가 없습니다.")
        return

    if not sys.stdout.isatty() or not sys.stdin.isatty():
        if last is not None:
            for f in flows[:last]:
                click.echo(
                    f"{f['id']}\t{f['method']}\t{f['host']}{f['path']}\t{f['status_code']}"
                )
            return
        click.echo(
            "troxy pick은 인터랙티브 터미널이 필요합니다. "
            "`troxy flows`(표) 또는 `troxy pick --last 10`(탭 구분 목록)을 사용하세요.",
            err=True,
        )
        sys.exit(1)

    chosen_id = curses.wrapper(_pick_loop, flows)
    if chosen_id is None:
        return

    flow = get_flow(db_path, chosen_id)
    if not flow:
        click.echo(f"flow {chosen_id}를 찾을 수 없습니다.", err=True)
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
            "troxy pick — ↑/↓ 이동, Enter=상세, q=종료",
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
            f"[{cursor + 1}/{len(flows)}]  (Enter=상세, q=취소)",
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
