# troxy v0.3 Design Review

**Reviewer**: design-review (Design Critic)
**Date**: 2026-04-16
**Screenshots**: `docs/qa-screenshots/list-5.svg`, `list-20.svg`, `list-filter.svg`, `detail-200.svg`, `detail-404.svg`, `mock-dialog.svg`, `mock-list.svg`, `copy-modal.svg`

**사용자 피드백**: *"리스트도 안이뻐 이게 뭐가 이쁜거야"*

---

## 심사 기준

각 화면을 5개 축에서 10점 만점으로 채점:

1. **정보 위계** — 중요한 것(method, status)이 먼저 눈에 들어오는가
2. **컬러 시맨틱** — 2xx green / 3xx blue / 4xx yellow / 5xx red 일관성
3. **여백/패딩** — 컬럼·섹션 간 호흡
4. **선택/포커스** — 현재 선택/포커스 항목이 명확한가
5. **헤더/구분선** — 테이블 헤더·패인 경계 구분

---

## 1. ListScreen — **총점 22/50 ❌ (실패)**

**Evidence**: `docs/qa-screenshots/list-5.svg`, `list-20.svg`

| 축 | 점수 | 근거 |
|---|---:|---|
| 정보 위계 | 4/10 | DB path가 헤더 전체 폭을 먹음. flow count는 오른쪽 끝. METHOD·STATUS 컬러 0 → 눈이 갈 곳을 잃음. |
| 컬러 시맨틱 | **1/10 🔥** | `theme.py`에 `METHOD_COLORS`/`STATUS_COLORS` 정의돼 있으나 `_add_flow_row`에서 **전혀 사용 안 함**. 모든 cell이 `#e0e0e0` 흰색. 200·401·500 구별 불가. |
| 여백/패딩 | 5/10 | 컬럼 사이 1-space padding은 OK. 하지만 table→hint-bar 사이 구분선 없음, 빈 공간이 어두운 회색으로 죽어있음. |
| 선택/포커스 | 4/10 | Textual 기본 `#0178d4` 브라이트 블루. 채도가 너무 강해 데이터 가독성 해침. `SELECTION_MARKER = "▶"` 상수 정의돼 있으나 **미사용**. |
| 헤더/구분선 | 4/10 | 헤더 bg `#2d3740` — 데이터 bg `#272727`과 대비 약함 (ΔL ≈ 6). 헤더 아래 구분선 없음. |

### 치명적 문제 (Critical)

**C-1. 컬러 시맨틱이 전혀 렌더되지 않음**
- `src/troxy/tui/list_screen.py:104-112` — `table.add_row(...)`에 raw `str` 전달
- `theme.method_color()`, `theme.status_color()` 함수는 존재하지만 호출되지 않음
- 사용자 원칙 **"2xx green, 3xx blue, 4xx yellow, 5xx red"** 위반

**C-2. 선택 행 마커 없음**
- `theme.SELECTION_MARKER = "▶"` 정의됐으나 미사용
- 키보드 발견성 원칙("키보드로 조작하는 게 보이게") 위반

**C-3. DB path 오버플로**
- `copy.header_text()`에서 `~/.troxy/flows.db` 풀 경로 노출. 실제 환경에서는 `/Users/xxx/Workspace/.../flows.db` 같이 길어짐 → 헤더 60+ 컬럼 차지 → flow count 가려짐

### 주요 문제 (Major)

**M-1. 데이터 행 zebra striping 없음** → 10+ 행에서 행 경계 모호 (list-20.svg)
**M-2. 헤더 대문자/굵기 처리** — 현재 그냥 `" # "`, `" TIME "` — k9s·lazygit 수준의 헤더 포즈 필요
**M-3. PATH 컬럼 30자 truncation** — 실제 API path는 50+ 자. `/api/v2/...` 접두 무의미하게 반복

---

## 2. DetailScreen — **총점 27/50 ⚠️ (부족)**

**Evidence**: `docs/qa-screenshots/detail-200.svg`, `detail-404.svg`

| 축 | 점수 | 근거 |
|---|---:|---|
| 정보 위계 | 6/10 | URL bar 상단 고정은 OK. 하지만 status code 색상 없음, duration도 plain text. |
| 컬러 시맨틱 | 2/10 | status code(200·404) 컬러 미적용. 헤더 키/값 구분 없음. |
| 여백/패딩 | 5/10 | pane 내부 padding 0 → 텍스트가 경계에 붙음. header 줄과 body 사이 간격 없음. |
| 선택/포커스 | 7/10 | `border-left: thick $accent` 괜찮음. 하지만 어느 pane이 focus인지 색 대비가 약함. |
| 헤더/구분선 | 7/10 | `border-top: solid $primary` 패인 간 구분 OK. URL bar 위/아래 경계 없음. |

### 주요 문제

**D-1. URL bar 밋밋함** — status가 `Flow #1 · GET · 200 · 12ms` plain — method/status 컬러 필요
**D-2. pane padding 없음** — `.pane`에 `padding: 0 1` 필요
**D-3. 섹션 타이틀 `── Request ──` 수준 낮음** — k9s처럼 bold colored header 권장

---

## 3. MockDialog — **총점 30/50 ⚠️**

**Evidence**: `docs/qa-screenshots/mock-dialog.svg`

| 축 | 점수 | 근거 |
|---|---:|---|
| 정보 위계 | 7/10 | 타이틀 굵게, 필드 라벨 간격 OK |
| 컬러 시맨틱 | 4/10 | status Select에 컬러 없음. Save/Cancel 힌트 희미함 |
| 여백/패딩 | 7/10 | `padding: 1 2` 괜찮음 |
| 선택/포커스 | 6/10 | 현재 focus된 필드 하이라이트 약함 (Textual 기본) |
| 헤더/구분선 | 6/10 | 타이틀 아래 구분선 없음 |

### 주요 문제

**K-1. 타이틀 분리 안 됨** — 타이틀/본문 사이 `border-bottom` 필요
**K-2. 푸터 힌트 `Ctrl+S save · Esc cancel`** — class `field-label`로 label과 같은 레벨로 보임 → hint 전용 스타일 필요

---

## 4. MockListScreen — **총점 24/50 ❌**

**Evidence**: `docs/qa-screenshots/mock-list.svg`

ListScreen과 동일한 문제 (컬러 시맨틱 0, zebra 0, 헤더 약함) + 추가로:

- **ON 컬럼**: `●`/`○` 텍스트만. enabled는 green, disabled는 dim gray 필요
- **HIT 컬럼**: 0일 때 dim, 1+ 일 때 primary 필요 (사용량 시각화)

---

## 5. CopyModal — **총점 31/50 ✓**

**Evidence**: `docs/qa-screenshots/copy-modal.svg`

| 축 | 점수 | 근거 |
|---|---:|---|
| 정보 위계 | 8/10 | `[1] URL`, `[2] Request` 키 우선 — 발견성 좋음 |
| 컬러 시맨틱 | 5/10 | 숫자 키 하이라이트 없음 |
| 여백/패딩 | 7/10 | `padding: 1` 적당 |
| 선택/포커스 | 5/10 | focus 상태 표시 없음 (디스플레이만) |
| 헤더/구분선 | 6/10 | `── Copy ──` OK |

**개선**: 숫자 키 `[1]`을 `$accent` 컬러로.

---

## 📋 Action Plan (우선순위)

### P0 — 리스트 컬러 시맨틱 (Task #4 블로커)
1. `list_screen._add_flow_row`에서 `rich.text.Text`로 method/status 컬러 적용
2. `mock_list._refresh`에서도 동일 적용 (ON/STATUS/HIT)
3. 선택 행: `SELECTION_MARKER` 첫 컬럼에 렌더

### P1 — 리스트 CSS 다듬기
4. DataTable header 스타일 강화 (bold + bg + border-bottom)
5. Zebra striping (`.datatable--odd-row` / `--even-row`)
6. 선택 행 bg를 `$primary-darken-2` 수준으로 톤다운

### P2 — 공통 다듬기
7. Header truncation (DB path → `~/…/flows.db` 축약)
8. Hint bar bg 분리 (`$surface`)
9. Detail URL bar 컬러 적용
10. Mock dialog 타이틀 구분선

---

## 📐 CSS Diff Proposal (초안)

### `list_screen.py` DEFAULT_CSS

```diff
 DEFAULT_CSS = """
+#flow-table {
+    height: 1fr;
+    background: $surface;
+}
+#flow-table > .datatable--header {
+    background: $primary-background;
+    color: $text;
+    text-style: bold;
+}
+#flow-table > .datatable--odd-row {
+    background: $surface;
+}
+#flow-table > .datatable--even-row {
+    background: $surface-lighten-1;
+}
+#flow-table > .datatable--cursor {
+    background: $accent 30%;
+    color: $text;
+    text-style: bold;
+}
 #header {
     height: 1;
+    background: $panel;
+    color: $text-muted;
+    padding: 0 1;
 }
 #hint-bar {
     height: 1;
+    background: $panel;
+    color: $text-muted;
+    padding: 0 1;
 }
-#flow-table {
-    height: 1fr;
-}
 """
```

### `list_screen._add_flow_row` — 핵심 패치

```python
from rich.text import Text
from troxy.tui.theme import SELECTION_MARKER, method_color, status_color, status_icon

def _add_flow_row(self, table: DataTable, flow: dict) -> None:
    status = flow["status_code"]
    ts = time.strftime("%H:%M:%S", time.localtime(flow["timestamp"]))
    method_cell = Text(flow["method"], style=f"bold {method_color(flow['method'])}")
    status_cell = Text(
        f"{status} {status_icon(status)}",
        style=f"bold {status_color(status)}",
    )
    table.add_row(
        str(flow["id"]),
        ts,
        method_cell,
        flow["host"],
        self._truncate_path(flow["path"], 40),
        status_cell,
        key=str(flow["id"]),
    )
```

---

## 📊 목표 점수 (개선 후)

| 화면 | 현재 | 목표 |
|---|---:|---:|
| ListScreen | 22/50 | **42+/50** |
| DetailScreen | 27/50 | 40+/50 |
| MockDialog | 30/50 | 40+/50 |
| MockListScreen | 24/50 | 42+/50 |
| CopyModal | 31/50 | 38+/50 |

---

## 🎯 레퍼런스 기준

- **k9s**: 컬러풀한 namespace badge, 선택 행 강한 bg contrast
- **lazygit**: panel border/header 명확, 푸터 힌트 dim 처리
- **Charles/Proxyman**: 2xx green / 4xx yellow / 5xx red 일관 적용

---

## ✅ 구현 결과 (Task #4)

**Commit target**: `src/troxy/tui/list_screen.py`, `mock_list.py`, `detail_screen.py`

### Before → After 비교 파일

| 화면 | Before | After |
|---|---|---|
| List (5 flows) | `docs/qa-screenshots/before/list-5.svg` | `docs/qa-screenshots/after/list-5.svg` |
| List (20 flows) | `docs/qa-screenshots/before/list-20.svg` | `docs/qa-screenshots/after/list-20.svg` |
| List (filter) | `docs/qa-screenshots/before/list-filter.svg` | `docs/qa-screenshots/after/list-filter.svg` |
| Detail (200) | `docs/qa-screenshots/before/detail-200.svg` | `docs/qa-screenshots/after/detail-200.svg` |
| Detail (404) | `docs/qa-screenshots/before/detail-404.svg` | `docs/qa-screenshots/after/detail-404.svg` |
| Mock list | `docs/qa-screenshots/before/mock-list.svg` | `docs/qa-screenshots/after/mock-list.svg` |
| Mock dialog | `docs/qa-screenshots/before/mock-dialog.svg` | `docs/qa-screenshots/after/mock-dialog.svg` |
| Copy modal | `docs/qa-screenshots/before/copy-modal.svg` | `docs/qa-screenshots/after/copy-modal.svg` |

### 팔레트 확인 (after/list-20.svg)

| 역할 | Hex | 용도 |
|---|---|---|
| bright green | `#98e024` | GET, 2xx ✓ |
| orange | `#ff8800` | PUT |
| red | `#f4005f` | DELETE, 5xx 🔥 |
| yellow | `#fd971f` | 4xx ⚠ |
| purple/blue | `#9d65ff` | POST, 3xx |
| cyan | `#58d1eb` | PATCH |

➡️ 컬러 시맨틱 **1/10 → 9/10**. 정보 위계 축도 동반 상승.

### 변경 요약

1. `list_screen.DEFAULT_CSS` — header·hint·info-bar에 `$panel` bg 추가, datatable cursor를 `$accent 35%`로 톤다운 (기존 `#0178d4` 원색 → 반투명 accent)
2. `DataTable(zebra_stripes=True)` — 짝/홀수 행 구분
3. `_add_flow_row` — `method`/`status` 컬럼에 `rich.text.Text(style=bold {color})` 렌더
4. `mock_list._refresh` — ON/MATCH/STATUS/HIT 네 컬럼에 의미 컬러 적용
5. `detail_screen._render_url` — URL bar에 method/status 컬러, duration을 dim 처리

### Round 2 — team-lead 피드백 반영 (2026-04-16)

team-lead가 `/tmp/troxy-screenshots/*.svg.png`을 직접 캡처해 구체 이슈 6건 제기. 전부 반영:

| # | 이슈 | 조치 | 파일 |
|---|---|---|---|
| L-1 | DB 경로 전체 노출 | `_shorten_db_path()` 추가 — `$HOME→~`, 깊은 경로는 `/…/parent/file.db`로 축약 | `copy.py` |
| L-2 | 선택 행이 갈색 (`$accent 35%` 블렌딩) | 고정 hex `#1e4e8f` (deep blue) + `#ffffff` text | `list_screen.DEFAULT_CSS` |
| L-3 | ▶ 마커 없음 | 전용 marker 컬럼(width=2) 추가, `on_data_table_row_highlighted`에서 cursor 행에만 ▶ 찍음 | `list_screen._update_cursor_marker` |
| L-4 | Status/ID 좌측 정렬 | `Text(justify="right")` 적용 (헤더·cell 모두) | `list_screen.compose`, `_add_flow_row` |
| L-5 | 헤더 구분 약함 | `background: $panel-darken-1; color: $accent; text-style: bold` | `.datatable--header` CSS |
| M-1 | MockDialog 오른쪽 밀림 + dimming 없음 | `MockDialog { background: $background 70%; align: center middle; }` 추가 | `mock_dialog.DEFAULT_CSS` |
| M-2 | 모달 border 튐 | `border: solid $primary` → `border: round $accent` | `mock_dialog.DEFAULT_CSS` |
| M-3 | 타이틀 구분선 | `#mock-title { border-bottom: solid $primary-darken-1; color: $accent; text-style: bold; }` | `mock_dialog.DEFAULT_CSS` |
| M-4 | 하단 힌트 동일 스타일 | 전용 `.dialog-hint` 클래스 (italic, dim) | `mock_dialog.compose` |

### Selection cursor 팔레트 비교

| State | Before | After |
|---|---|---|
| cursor bg | `$accent 35%` → 블렌드시 **갈색** | `#1e4e8f` (deep blue, 고정) |
| cursor text | `$text` (default off-white) | `#ffffff` + bold |
| 마커 | 없음 | `▶` (green, 첫 컬럼) |

### DB path 축약 예시

```
before: /var/folders/bs/kdrdq4yj64j60hqbsqscyjbw0000gn/T/tmp2bgtmqd/capture.db
after:  /…/tmp2bgtmqd/capture.db

before: /Users/seokhyeon/.troxy/flows.db
after:  ~/.troxy/flows.db
```

### MockDialog 레이아웃 diff

```diff
 MockDialog {
+    background: $background 70%;   # dimming 뒷배경
     align: center middle;
 }
 #mock-dialog-container {
-    width: 80;
+    width: 72;
-    max-height: 40;
+    max-height: 32;
     background: $surface;
-    border: solid $primary;
+    border: round $accent;
     padding: 1 2;
 }
+#mock-title {
+    text-style: bold;
+    color: $accent;
+    padding-bottom: 1;
+    border-bottom: solid $primary-darken-1;
+    margin-bottom: 1;
+}
+#mock-dialog-container .dialog-hint {
+    color: $text-muted;
+    text-style: italic;
+    margin-top: 1;
+}
```

### 남은 Follow-up

- `DataTable.zebra_stripes` 대비가 여전히 약함 — `$surface` ↔ `$surface-lighten-1` 차이가 약 ΔL 5. 커스텀 컬러 오버라이드 필요 시 Round 3로.
- Switch / Horizontal 라벨 정렬 (M-3 관련) — Textual 기본 Switch 크기 이슈, 위젯 커스텀까지 필요. Round 3.

### 검증 로그

```
$ uv run pytest tests/tui --ignore=tests/tui/test_real_tty.py -q
112 passed in 13.25s

$ TROXY_SS_DIR=docs/qa-screenshots/after uv run python scripts/capture_design_screenshots.py
✓ 8 screenshots
```

*(`test_real_tty.py` 단일 실패는 Bug #1 — q 키 종료 안 됨. 이번 디자인 변경과 무관.)*

---

### Round 3 — DetailScreen 재설계 (2026-04-16, Bug #8)

사용자 피드백: "detail 안이뻐". 실제 시나리오(긴 registration_token 쿼리, Cookie URL-encoded 세션, Bearer JWT, x-frograms-* 헤더)로 캡처한 before/after는 `docs/qa-screenshots/round3/`.

**6가지 시각 이슈 → 해결:**

1. **URL 1줄 오버플로** → Host/Path/Query 3필드 분리, Query는 32자 넘으면 `<first16>...(<bytes>b)` 형식으로 축약 (원본은 `u` 키로 복사 가능)
2. **헤더 key/value 구분 없음** → 20-char dim 패딩 key + 기본색 value
3. **Cookie 값 무한 스크롤** → 80자 초과 시 `...(<bytes>b, y to copy)` 축약
4. **Request/Response 경계 없음** → `double $accent` 가로 구분선 + 각 구역에 `.pane-header` (Response는 status·size 표시)
5. **Focus 불명확** → `tint: $accent 8%` 으로 활성 pane 전체 톤다운
6. **배경 일관성** → Request 컨테이너 `$surface-darken-1`, Response 컨테이너 `$surface`

**JSON body:** `rich.syntax.Syntax(theme="monokai", background_color="default", word_wrap=True)` 로 구문 강조.

**파일 크기 준수:** Round 3 코드 추가로 `detail_screen.py`가 366줄까지 증가 → CSS를 `src/troxy/tui/styles.py#DETAIL_SCREEN_CSS` 로, 순수 렌더/텍스트 헬퍼를 `src/troxy/tui/detail_helpers.py` 로 분리하여 207줄로 축소 (300줄 cap 준수).

**검증:**

```
$ uv run python scripts/check_file_size.py   # File sizes OK.
$ uv run python scripts/lint_layers.py       # Layer dependencies OK.
$ uv run pytest tests/tui -q                 # 160 passed in 31.52s
```

**v0.4 예약:** URL verbose 토글(`v` 키로 축약 해제), Pretty-printed form-urlencoded body, Binary hex-dump 뷰.

