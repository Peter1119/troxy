# troxy v0.3 — Strict QA Protocol

The previous round shipped with four separate breakages (`q` did not quit,
the bottom bar was pushed off-screen, the displayed IP was wrong, the flow
list looked unfinished) *after* unit tests passed. This document is the
bar we use now before any TUI-touching PR can be marked **completed**.

No step is optional. Each step produces an artifact (PASS log, SVG, or
exit code) that ships with the PR.

---

## Gate 0 — Preconditions

Before you even start reviewing a fix:

```bash
uv sync                               # refresh deps, incl. pexpect
uv run python scripts/lint_layers.py  # layer hygiene
uv run python scripts/check_file_size.py
```

If any lint step fails, reject the fix immediately. No TUI issue justifies
breaking the layer rules in `CLAUDE.md`.

---

## Gate 1 — Unit + widget tests

```bash
uv run pytest tests/unit tests/tui -v
```

Every test must pass. Tests passing here are **necessary but not
sufficient** — they do not catch real-TTY bugs.

---

## Gate 2 — SVG snapshot capture

```bash
uv run pytest tests/tui/test_qa_snapshots.py -v
```

Produces:

- `docs/qa-screenshots/list_empty.svg`
- `docs/qa-screenshots/list_with_flows.svg`
- `docs/qa-screenshots/list_filter_4xx.svg`
- `docs/qa-screenshots/list_confirm_clear.svg`
- `docs/qa-screenshots/list_toast_intercept.svg`
- `docs/qa-screenshots/detail_request_focus.svg`
- `docs/qa-screenshots/detail_response_focus.svg`
- `docs/qa-screenshots/detail_copy_modal.svg`
- `docs/qa-screenshots/mock_dialog.svg`
- `docs/qa-screenshots/mock_list.svg`

**QA engineer must open each SVG in a browser and inspect it.** Reject if:

- the bottom hint/info bar is clipped or missing (Bug #2 regression),
- a panel has collapsed to height 0,
- any text overflows past the 120-col width,
- the flow list lacks any of: id, time, method, host, path, status+icon.

Attach the rendered screenshots (or a diff against the previous commit) to
the PR review comment.

---

## Gate 3 — Real TTY keybinding tests

```bash
uv run pytest tests/tui/test_real_tty.py -v -m slow
```

These spawn the real app in a PTY via `pexpect` and send actual keystrokes.
They catch the class of bug where `run_test` pilots pass but a terminal
session hangs.

At minimum, these five tests must pass before `q` / keybinding work is
considered "done":

1. `test_real_tty_q_key_exits` — the Bug #1 regression guard.
2. `test_real_tty_ctrl_c_exits` — user's panic key must always work.
3. `test_real_tty_filter_then_escape_then_quit` — the exact sequence that
   broke last round (focus lingering on the filter input).
4. `test_real_tty_enter_opens_detail_screen` — **Bug #5** guard: Enter on
   the focused DataTable must reach `ListScreen.action_view_detail` and
   push `DetailScreen` (proven by matching "Request" in the rendered
   frame). Round-trip also verified via Esc → q.
5. `test_real_tty_detail_escape_back_then_quit` — Enter → Esc → q still
   works with an empty list (no-op Enter path).

Expected output: **6 passed** (five above + the `unbound key` sanity test).

---

## Gate 4 — Manual live run

Machine tests cannot observe visual drift, flicker, cursor flashes, or the
30-second IP refresh. A human must run the app end-to-end.

```bash
export TROXY_DB=/tmp/troxy-verify.db
rm -f "$TROXY_DB"
uv run troxy start -p 18090
```

Walk the checklist in `docs/v0.3-manual-verification.md` top to bottom. For
this strict round we add:

### Bug-specific live checks

**Bug #1 — `q` exits.**
  - [ ] Press `q` in the list view → app exits, shell prompt returns.
  - [ ] Press `q` after `f` (filter) → Enter → Esc → app exits.
  - [ ] Press `q` after Enter (detail) → Esc → app exits.
  - [ ] Press `Ctrl+C` in the list view → app exits.
  - [ ] `lsof -i :18090` empty after exit (no orphan mitmdump).

**Bug #2 — bottom bar not pushed.**
  - [ ] Open filter (`f`) → the hint bar stays on the last row, does not
        jump above the confirm dialog or get clipped.
  - [ ] Open clear-confirm (`x`) → confirm dialog renders above the hint
        bar, hint bar still visible.
  - [ ] Resize terminal to 80 cols → layout reflows, bottom bar still
        anchored at the last row.

**Bug #3 — IP correct.**
  - [ ] The `📡 {my-ip}` line matches `ifconfig | grep 'inet '` private IP
        (192.168.* / 10.* / 172.16-31.*).
  - [ ] On a laptop with VPN active, the LAN IP is preferred over the VPN
        tunnel IP.
  - [ ] Phone on the same Wi-Fi actually proxies through
        `{displayed-ip}:18090` and flows appear.

**Bug #4 — list design.**
  - [ ] Columns are aligned (not ragged).
  - [ ] Status column shows both code and icon (e.g. `200 ✓`).
  - [ ] 4xx/5xx rows are visually distinct from 2xx.
  - [ ] Long hostnames / paths truncate with an ellipsis rather than
        wrapping.

**Bug #5 — Enter opens detail.**
  - [ ] In the list, highlight a row with ↑↓ and press Enter → detail
        view appears (URL line, Request pane, Response pane visible).
  - [ ] Esc from the detail view returns to the list with the cursor on
        the same row.
  - [ ] Enter → Esc → Enter (same row) works twice in a row (no stale
        screen on the stack).
  - [ ] With the filter active (`f status:2xx` Enter), pressing Enter on
        a filtered row still opens detail for the correct flow.

---

## Gate 5 — Sign-off

A bug can be moved to **completed** only if the QA engineer submits, in the
task comment thread:

1. Git SHA of the fix.
2. `Gate 1` pytest output (PASS count).
3. `Gate 2` SVG filenames touched and a one-line visual verdict for each.
4. `Gate 3` pytest output (PASS count; any test that did not pass
   **blocks** completion).
5. `Gate 4` checklist, each box filled with ✅ / ❌ and a short note.

If any box is ❌, the task goes back to `in_progress` with a comment
explaining the failure mode. **No exceptions** — that is the whole reason
this protocol exists.

---

## When to add a new gate

Whenever a bug slips through all five gates in production, add a new
automated check here and link it to the incident. The protocol should
only ever grow; never delete a gate as a shortcut.
