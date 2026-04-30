# Mock Body Editor (Ctrl+E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `MockDialog`에 `Ctrl+E` 단축키를 추가해 외부 에디터로 body를 풀스크린 편집하고, `Ctrl+S` 시 JSON body를 구문 검증한다.

**Architecture:** `src/troxy/tui/external_editor.py` 신규 모듈이 에디터 탐색·subprocess 실행·임시파일 IO·검증 로직을 담는다. `mock_dialog.py`는 이 모듈을 import해 키 바인딩과 저장 검증만 추가한다. `_prettify_body` 정적 메서드도 `external_editor.py`로 이동해 `mock_dialog.py`를 300줄 이하로 유지한다.

**Tech Stack:** Python stdlib (`subprocess`, `tempfile`, `shutil`, `os`, `json`), Textual (`App.suspend()`), pytest + monkeypatch + pytest-asyncio

---

## File Map

| 작업 | 파일 | 변경 |
|------|------|------|
| 신규 | `src/troxy/tui/external_editor.py` | 예외 3종 + 함수 5개 |
| 신규 | `tests/unit/test_external_editor.py` | 단위 테스트 |
| 수정 | `src/troxy/tui/mock_dialog.py` | `_prettify_body` 제거·이동, Ctrl+E 바인딩, `action_open_editor`, `action_save` JSON 검증, hint 갱신 |

---

## Task 1: 예외 클래스 + `resolve_editor()`

**Files:**
- Create: `tests/unit/test_external_editor.py`
- Create: `src/troxy/tui/external_editor.py`

- [ ] **Step 1-1: failing test 작성**

`tests/unit/test_external_editor.py` 생성:

```python
"""Tests for external_editor helpers."""

import pytest


# ---------- resolve_editor ----------

def test_resolve_editor_visual_env(monkeypatch):
    monkeypatch.setenv("VISUAL", "nvim")
    monkeypatch.setenv("EDITOR", "emacs")
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "nvim" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "nvim"


def test_resolve_editor_falls_back_to_editor_env(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "vim" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "vim"


def test_resolve_editor_falls_back_to_nano(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "nano"


def test_resolve_editor_falls_back_to_vi(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/vi" if cmd == "vi" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "vi"


def test_resolve_editor_returns_none_when_all_missing(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() is None
```

- [ ] **Step 1-2: 테스트 실패 확인**

```bash
uv run python -m pytest tests/unit/test_external_editor.py -v 2>&1 | tail -15
```
예상: `ImportError` 또는 `ModuleNotFoundError` — `external_editor` 모듈 없음

- [ ] **Step 1-3: 최소 구현 작성**

`src/troxy/tui/external_editor.py` 생성:

```python
"""External editor integration for MockDialog body editing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App


class EditorNotFoundError(Exception):
    """No usable editor binary found on PATH."""


class EditorIOError(Exception):
    """Temporary file read/write failure."""


class EditorCancelledError(Exception):
    """User closed editor without saving (returncode != 0)."""


def resolve_editor() -> str | None:
    """Return the first usable editor command via fallback chain.

    Chain: $VISUAL → $EDITOR → nano → vi → None
    Uses shutil.which() to verify the binary exists on PATH.
    """
    for env_var in ("VISUAL", "EDITOR"):
        cmd = os.environ.get(env_var)
        if cmd and shutil.which(cmd):
            return cmd
    for fallback in ("nano", "vi"):
        if shutil.which(fallback):
            return fallback
    return None
```

- [ ] **Step 1-4: 테스트 통과 확인**

```bash
uv run python -m pytest tests/unit/test_external_editor.py -v 2>&1 | tail -15
```
예상: 5 passed

- [ ] **Step 1-5: 커밋** (`committer` 스킬 사용)

---

## Task 2: `ext_for_content_type()` + `prettify_body()` + `validate_json_body()`

**Files:**
- Modify: `tests/unit/test_external_editor.py` (테스트 추가)
- Modify: `src/troxy/tui/external_editor.py` (함수 3개 추가)

- [ ] **Step 2-1: failing tests 추가**

`tests/unit/test_external_editor.py` 끝에 추가:

```python
# ---------- ext_for_content_type ----------

def test_ext_for_json():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("application/json") == ".json"


def test_ext_for_json_with_charset():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("application/json; charset=utf-8") == ".json"


def test_ext_for_xml():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("application/xml") == ".xml"


def test_ext_for_html():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("text/html") == ".html"


def test_ext_for_plain_text():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("text/plain") == ".txt"


def test_ext_for_none():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type(None) == ".txt"


# ---------- prettify_body ----------

def test_prettify_body_json_indents():
    from troxy.tui.external_editor import prettify_body
    result = prettify_body('{"a":1}', "application/json")
    assert result == '{\n  "a": 1\n}'


def test_prettify_body_invalid_json_returns_raw():
    from troxy.tui.external_editor import prettify_body
    raw = "{bad json}"
    assert prettify_body(raw, "application/json") == raw


def test_prettify_body_non_json_returns_raw():
    from troxy.tui.external_editor import prettify_body
    raw = "hello world"
    assert prettify_body(raw, "text/plain") == raw


def test_prettify_body_empty_returns_empty():
    from troxy.tui.external_editor import prettify_body
    assert prettify_body("", "application/json") == ""


def test_prettify_body_none_content_type():
    from troxy.tui.external_editor import prettify_body
    raw = '{"a":1}'
    assert prettify_body(raw, None) == raw


# ---------- validate_json_body ----------

def test_validate_json_valid():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body('{"a": 1}')
    assert ok is True
    assert msg == ""


def test_validate_json_empty_body():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body("")
    assert ok is True
    assert msg == ""


def test_validate_json_whitespace_only():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body("   \n  ")
    assert ok is True


def test_validate_json_invalid_reports_line_col():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body("{bad}")
    assert ok is False
    assert "1행" in msg
    assert "열" in msg


def test_validate_json_multiline_error_line_number():
    from troxy.tui.external_editor import validate_json_body
    body = '{\n  "a": 1,\n  bad\n}'
    ok, msg = validate_json_body(body)
    assert ok is False
    assert "3행" in msg
```

- [ ] **Step 2-2: 테스트 실패 확인**

```bash
uv run python -m pytest tests/unit/test_external_editor.py -v 2>&1 | tail -20
```
예상: 새로 추가한 테스트들 FAIL (`ImportError: cannot import name`)

- [ ] **Step 2-3: 함수 3개 구현**

`src/troxy/tui/external_editor.py`에 `resolve_editor()` 아래에 추가:

```python
def ext_for_content_type(content_type: str | None) -> str:
    """Return a file extension for the given MIME type.

    Used to give the temp file a meaningful extension so editors can
    apply syntax highlighting.
    """
    if not content_type:
        return ".txt"
    ct = content_type.lower()
    if "json" in ct:
        return ".json"
    if "xml" in ct:
        return ".xml"
    if "html" in ct:
        return ".html"
    return ".txt"


def prettify_body(body: str, content_type: str | None) -> str:
    """Pretty-print body when content_type is JSON; return verbatim otherwise.

    Invalid JSON falls through to the raw string — editing a mock should
    never silently corrupt the user's payload.
    """
    if not body:
        return ""
    if content_type and "json" in content_type.lower():
        try:
            return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass
    return body


def validate_json_body(body: str) -> tuple[bool, str]:
    """Validate body as JSON when content_type is JSON.

    Returns (True, "") on success or empty body.
    Returns (False, "<human message>") on parse error.
    """
    if not body.strip():
        return True, ""
    try:
        json.loads(body)
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"JSON 오류: {e.lineno}행 {e.colno}열 — {e.msg}"
```

- [ ] **Step 2-4: 테스트 통과 확인**

```bash
uv run python -m pytest tests/unit/test_external_editor.py -v 2>&1 | tail -20
```
예상: 전체 통과

- [ ] **Step 2-5: 커밋** (`committer` 스킬 사용)

---

## Task 3: `open_in_editor()` async

**Files:**
- Modify: `tests/unit/test_external_editor.py` (async 테스트 추가)
- Modify: `src/troxy/tui/external_editor.py` (`open_in_editor` 추가)

- [ ] **Step 3-1: async fixture + failing tests 추가**

`tests/unit/test_external_editor.py` 끝에 추가:

```python
# ---------- open_in_editor ----------

import os
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_app():
    """Minimal App mock exposing an async suspend() context manager."""
    app = MagicMock()

    @asynccontextmanager
    async def _suspend():
        yield

    app.suspend = _suspend
    return app


@pytest.mark.asyncio
async def test_open_in_editor_returns_edited_content(tmp_path, monkeypatch, mock_app):
    """Editor writes new content → function returns that content."""
    def fake_run(cmd, **kwargs):
        # Simulate editor writing to the temp file
        with open(cmd[1], "w") as f:
            f.write("edited body")
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor
    result = await open_in_editor("original", "application/json", mock_app)
    assert result == "edited body"


@pytest.mark.asyncio
async def test_open_in_editor_raises_when_no_editor(monkeypatch, mock_app):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    from troxy.tui.external_editor import open_in_editor, EditorNotFoundError
    with pytest.raises(EditorNotFoundError):
        await open_in_editor("body", None, mock_app)


@pytest.mark.asyncio
async def test_open_in_editor_raises_cancelled_on_nonzero_exit(monkeypatch, mock_app):
    """returncode != 0 → EditorCancelledError (user quit without saving)."""
    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 1
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor, EditorCancelledError
    with pytest.raises(EditorCancelledError):
        await open_in_editor("body", None, mock_app)


@pytest.mark.asyncio
async def test_open_in_editor_deletes_temp_file(monkeypatch, mock_app):
    """Temp file must be deleted regardless of editor outcome."""
    captured_path: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_path.append(cmd[1])
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor
    await open_in_editor("body", "application/json", mock_app)

    assert captured_path, "subprocess.run was not called"
    assert not os.path.exists(captured_path[0]), "temp file was not deleted"


@pytest.mark.asyncio
async def test_open_in_editor_deletes_temp_file_even_on_cancel(monkeypatch, mock_app):
    """Temp file must be deleted even when editor exits with error."""
    captured_path: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_path.append(cmd[1])
        result = MagicMock()
        result.returncode = 1
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor, EditorCancelledError
    with pytest.raises(EditorCancelledError):
        await open_in_editor("body", None, mock_app)

    assert captured_path
    assert not os.path.exists(captured_path[0]), "temp file leaked on cancel"
```

- [ ] **Step 3-2: 테스트 실패 확인**

```bash
uv run python -m pytest tests/unit/test_external_editor.py -v -k "open_in_editor" 2>&1 | tail -20
```
예상: FAIL (`cannot import name 'open_in_editor'`)

- [ ] **Step 3-3: `open_in_editor` 구현**

`src/troxy/tui/external_editor.py`에 `validate_json_body` 아래에 추가:

```python
async def open_in_editor(
    body: str, content_type: str | None, app: App
) -> str:
    """Open *body* in an external editor and return the edited text.

    Uses ``App.suspend()`` to pause Textual while the editor runs.
    The temporary file is always deleted — even on error — to avoid
    leaking potentially sensitive payload data to disk.

    Raises:
        EditorNotFoundError: No usable editor found on PATH.
        EditorCancelledError: Editor exited with non-zero returncode
            (treat as user cancellation).
        EditorIOError: Temp file could not be written or read.
    """
    editor = resolve_editor()
    if editor is None:
        raise EditorNotFoundError(
            "에디터를 찾을 수 없습니다. $VISUAL 또는 $EDITOR 환경변수를 설정하세요."
        )

    ext = ext_for_content_type(content_type)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(body)
            tmp_path = f.name

        async with app.suspend():
            result = subprocess.run([editor, tmp_path])

        if result.returncode != 0:
            raise EditorCancelledError(
                f"에디터가 비정상 종료되었습니다 (returncode={result.returncode})."
            )

        try:
            with open(tmp_path, encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            raise EditorIOError(f"편집 파일 읽기 실패: {exc}") from exc

    except (EditorNotFoundError, EditorCancelledError, EditorIOError):
        raise
    except OSError as exc:
        raise EditorIOError(f"임시 파일 IO 오류: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
```

- [ ] **Step 3-4: 테스트 통과 확인**

```bash
uv run python -m pytest tests/unit/test_external_editor.py -v 2>&1 | tail -20
```
예상: 전체 통과

- [ ] **Step 3-5: 커밋** (`committer` 스킬 사용)

---

## Task 4: `mock_dialog.py` 통합

> **주의:** `mock_dialog.py`는 현재 291줄. 기능 추가 시 ~312줄로 초과한다. `_prettify_body` 를 `external_editor.prettify_body`로 이동해 순 변경을 제로에 가깝게 유지한다.

**Files:**
- Modify: `src/troxy/tui/mock_dialog.py`

- [ ] **Step 4-1: import 교체 + `_prettify_body` 제거**

`mock_dialog.py` 상단 `import json` 제거, import 블록에 추가:

```python
from troxy.tui.external_editor import (
    EditorCancelledError, EditorIOError, EditorNotFoundError,
    open_in_editor, prettify_body, validate_json_body,
)
```

그리고 `_prettify_body` 정적 메서드(lines 182–198) 전체 삭제.

`compose()` 안의 호출 변경:

```python
# 변경 전
initial_body = self._prettify_body(raw_body, f.get("response_content_type"))

# 변경 후
initial_body = prettify_body(raw_body, f.get("response_content_type"))
```

- [ ] **Step 4-2: 기존 테스트 통과 확인 (리그레션 없음)**

```bash
uv run python -m pytest tests/unit -v 2>&1 | tail -10
```
예상: 153+ passed, 0 failed

- [ ] **Step 4-3: `BINDINGS`에 Ctrl+E 추가**

```python
BINDINGS = [
    ("escape", "cancel", "cancel"),
    ("ctrl+s", "save", "save"),
    ("ctrl+e", "open_editor", "external editor"),
    ("ctrl+l", "clear_body", "clear body"),
]
```

- [ ] **Step 4-4: hint 텍스트 갱신**

```python
# 변경 전
yield Static(
    "Ctrl+S save · Ctrl+L clear body · Esc cancel",
    classes="dialog-hint",
)

# 변경 후
yield Static(
    "Ctrl+S save · Ctrl+E editor · Ctrl+L clear body · Esc cancel",
    classes="dialog-hint",
)
```

- [ ] **Step 4-5: `action_open_editor` 메서드 추가**

`action_clear_body` 바로 앞에 추가:

```python
async def action_open_editor(self) -> None:
    body = self.query_one("#mock-body", TextArea).text
    ct = self._flow.get("response_content_type")
    try:
        self.query_one("#mock-body", TextArea).load_text(
            await open_in_editor(body, ct, self.app)
        )
    except EditorNotFoundError:
        self.notify("에디터를 찾을 수 없습니다. $EDITOR 환경변수를 설정하세요.", severity="error")
    except EditorCancelledError:
        self.notify("편집이 취소되었습니다", severity="warning")
    except EditorIOError as e:
        self.notify(str(e), severity="error")
```

- [ ] **Step 4-6: `action_save`에 JSON 검증 추가**

`body = self.query_one("#mock-body", TextArea).text` 바로 아래에 삽입:

```python
        body = self.query_one("#mock-body", TextArea).text
        ct = self._flow.get("response_content_type") or ""
        if "json" in ct.lower():
            ok, err_msg = validate_json_body(body)
            if not ok:
                self.notify(err_msg, severity="error")
                return
```

- [ ] **Step 4-7: 파일 크기 + lint 확인**

```bash
wc -l src/troxy/tui/mock_dialog.py
uv run python scripts/check_file_size.py
uv run python scripts/lint_layers.py
```

예상: mock_dialog.py ≤ 300줄, `File sizes OK.`, `No layer violations`

만약 300줄 초과 시 `action_open_editor`의 TextArea 호출 분리 또는 주석 압축으로 1-2줄 조정.

- [ ] **Step 4-8: 전체 테스트 통과 확인**

```bash
uv run python -m pytest tests/unit -v 2>&1 | tail -15
```
예상: 전체 통과 (new tests 포함)

- [ ] **Step 4-9: 커밋** (`committer` 스킬 사용)

---

## Task 5: PR 생성

- [ ] **Step 5-1: 브랜치 push**

```bash
git push -u origin feat/mock-body-editor
```

- [ ] **Step 5-2: PR 생성**

```bash
gh pr create \
  --title "Feat: MockDialog Ctrl+E 외부 에디터 연동" \
  --body "$(cat <<'EOF'
## Summary
- `Ctrl+E`로 외부 에디터(`$VISUAL → $EDITOR → nano → vi`) 열기
- `App.suspend()`로 Textual 일시정지 후 subprocess 실행 (터미널 충돌 방지)
- 임시파일 content_type 기반 확장자 + 종료 직후 삭제 (보안)
- `Ctrl+S` 시 JSON body 구문 검증 — 실패 시 라인/컬럼 Toast + 저장 차단
- `_prettify_body` → `external_editor.prettify_body`로 이동 (300줄 제한 준수)

## Test plan
- [ ] `tests/unit/test_external_editor.py` 전체 통과
- [ ] 기존 153 unit tests 리그레션 없음
- [ ] `uv run python scripts/check_file_size.py` OK
- [ ] `uv run python scripts/lint_layers.py` OK

Refs #4
EOF
)"
```

- [ ] **Step 5-3: lead에 PR URL 보고**

```
SendMessage → team-lead: "Task #2 구현 완료 — PR: <URL>"
```
