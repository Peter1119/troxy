# Mock Body Editor — Ctrl+E 외부 에디터 연동

## 배경

`MockDialog`의 `TextArea`는 높이 8줄로 고정돼 있어, JSON 페이로드 같은 긴 body를 보거나 고치기 어렵다.
AI가 body를 채워줘도 사람이 터미널에서 직접 검토·수정하는 시나리오가 불편하다.

## 목표

1. `MockDialog` 안에서 **Ctrl+E** 하나로 외부 에디터(풀스크린)를 열어 body를 자유롭게 편집한다.
2. 에디터 종료 후 변경 내용이 `TextArea`에 반영된다.
3. 저장(`Ctrl+S`) 시 JSON body는 구문 검증을 거쳐, 실패하면 라인/컬럼 정보를 Toast로 표시하고 저장을 차단한다.
4. 임시 파일은 편집 직후 즉시 삭제한다 (응답에 토큰 등 민감 정보가 포함될 수 있음).

## 비목표

- Headers 편집 UI (별도 작업)
- Windows 지원 (mitmproxy + Textual `App.suspend()` 동작 차이 — 명시적 제외)
- 파일 저장·열기 메뉴

---

## 아키텍처

레이어 규칙(`addon → core ← cli, mcp`) 유지. 본 작업은 `tui/`만 변경한다.

| 파일 | 변경 | 비고 |
|------|------|------|
| `src/troxy/tui/external_editor.py` | **신규** | 에디터 탐색·실행·임시파일 IO. `mock_dialog.py`가 이미 291줄이므로 책임 분리 |
| `src/troxy/tui/mock_dialog.py` | 수정 | Ctrl+E 바인딩, JSON 검증 호출, hint 텍스트 갱신 |
| `tests/unit/tui/test_external_editor.py` | **신규** | 단위 테스트 |

`core/`, `addon.py`, `cli/`, `mcp/` 변경 없음.

---

## `external_editor.py` 명세

### `resolve_editor() -> str | None`

폴백 체인 순서로 사용 가능한 에디터 명령을 반환한다.

```
$VISUAL → $EDITOR → nano → vi → None
```

- `os.environ.get("VISUAL")`, `os.environ.get("EDITOR")` 값은 `shutil.which()`로 존재 확인 후 반환.
- `nano`, `vi`는 `shutil.which("nano")`, `shutil.which("vi")`로 탐색.
- 모두 없으면 `None` 반환.

### `ext_for_content_type(content_type: str | None) -> str`

`content_type`에 따라 임시파일 확장자를 결정한다.

| content_type 포함 문자열 | 반환 |
|--------------------------|------|
| `json` | `.json` |
| `xml` | `.xml` |
| `html` | `.html` |
| 그 외 / None | `.txt` |

### `open_in_editor(body: str, content_type: str | None, app: App) -> str`

1. `resolve_editor()`로 에디터 명령 결정. `None`이면 `EditorNotFoundError` 발생.
2. `tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="w", encoding="utf-8")` 로 임시파일 생성 및 현재 body 기록 후 닫는다.
3. `async with app.suspend():` 블록 안에서 `subprocess.run([editor_cmd, tmp_path])` 호출.  
   - 반드시 `App.suspend()` 컨텍스트 매니저 안에서 — 백그라운드 분기 금지.
4. 에디터 프로세스 종료 후 파일 내용 읽기.
5. 임시파일 **즉시 삭제** (`os.unlink(tmp_path)`) — 예외가 발생해도 finally 블록에서 삭제.
6. 읽은 텍스트 반환.

**에러 처리**:

| 상황 | 처리 |
|------|------|
| 에디터 바이너리 없음 | `EditorNotFoundError` 발생 |
| `subprocess.run` 비정상 종료 (returncode ≠ 0) | `EditorCancelledError` 발생 (사용자가 저장 안 하고 종료한 것으로 간주 — 호출자가 Toast 표시) |
| 파일 IO 실패 | `EditorIOError` 발생 |

### `validate_json_body(body: str) -> tuple[bool, str]`

- body가 비어 있으면 `(True, "")`.
- `json.loads(body)` 시도.
- 성공하면 `(True, "")`.
- `json.JSONDecodeError`면 `(False, "JSON 오류: {line}행 {col}열 — {msg}")` 반환.

### 예외 클래스

```python
class EditorNotFoundError(Exception): ...
class EditorIOError(Exception): ...
class EditorCancelledError(Exception): ...
```

---

## `mock_dialog.py` 변경 명세

### BINDINGS 추가

```python
("ctrl+e", "open_editor", "external editor"),
```

### hint 텍스트 갱신

```
Ctrl+S save · Ctrl+E editor · Ctrl+L clear body · Esc cancel
```

### `action_open_editor` (async)

```python
async def action_open_editor(self) -> None:
    body = self.query_one("#mock-body", TextArea).text
    content_type = self._flow.get("response_content_type")
    try:
        new_body = await open_in_editor(body, content_type, self.app)
        self.query_one("#mock-body", TextArea).load_text(new_body)
    except EditorNotFoundError:
        self.notify("에디터를 찾을 수 없습니다. $EDITOR 환경변수를 설정하세요.", severity="error")
    except EditorCancelledError:
        self.notify("편집이 취소되었습니다", severity="warning")
    except EditorIOError as e:
        self.notify(str(e), severity="error")
```

### `action_save` JSON 검증 추가

저장 시 `content_type`이 JSON 계열(`"json" in content_type`)이면 `validate_json_body(body)` 호출.

```python
content_type = self._flow.get("response_content_type") or ""
if "json" in content_type.lower():
    ok, err_msg = validate_json_body(body)
    if not ok:
        self.notify(err_msg, severity="error")
        return  # 저장 차단
```

---

## 테스트 계획

**파일**: `tests/unit/tui/test_external_editor.py`  
**도구**: `pytest` + `monkeypatch` (표준 `subprocess.run` mock)

### `resolve_editor` 테스트

| 케이스 | 설정 | 예상 |
|--------|------|------|
| `$VISUAL` 설정 + which 존재 | `VISUAL=nvim`, `shutil.which`→경로 | `nvim` |
| `$VISUAL` 없음, `$EDITOR` 설정 | `EDITOR=vim` | `vim` |
| 환경변수 없음, nano 존재 | `which`→`/usr/bin/nano` | `nano` |
| 환경변수 없음, nano 없음, vi 존재 | `which nano`→None, `which vi`→존재 | `vi` |
| 모두 없음 | `which`→모두 None | `None` |

### `ext_for_content_type` 테스트

| content_type | 예상 |
|--------------|------|
| `application/json` | `.json` |
| `application/json; charset=utf-8` | `.json` |
| `application/xml` | `.xml` |
| `text/html` | `.html` |
| `text/plain` | `.txt` |
| `None` | `.txt` |

### `open_in_editor` 테스트

| 케이스 | mock | 예상 |
|--------|------|------|
| 정상 편집 후 저장 | `subprocess.run` returncode=0, 파일에 새 내용 | 새 텍스트 반환 |
| 에디터 없음 | `resolve_editor`→None | `EditorNotFoundError` |
| 저장 안 하고 종료 (returncode=1) | returncode=1 | `EditorCancelledError` 발생 |
| 임시파일 항상 삭제 | 어떤 경우든 | `os.path.exists(tmp_path)` == False |

### `validate_json_body` 테스트

| 케이스 | 입력 | 예상 |
|--------|------|------|
| 유효한 JSON | `{"a":1}` | `(True, "")` |
| 빈 문자열 | `""` | `(True, "")` |
| 잘못된 JSON | `{bad}` | `(False, "JSON 오류: 1행 ...")` |
| 줄바꿈 있는 JSON | 여러 줄 잘못된 JSON | 올바른 행 번호 포함 |

---

## 실행 순서

1. `src/troxy/tui/external_editor.py` + `tests/unit/tui/test_external_editor.py` 작성
2. `src/troxy/tui/mock_dialog.py` 수정
3. `uv run python -m pytest tests/unit -v` 통과 확인
4. `uv run python scripts/lint_layers.py` + `uv run python scripts/check_file_size.py` 통과
5. PR 생성 (`Feat: MockDialog Ctrl+E 외부 에디터 연동`, `Refs #4`)
