# Textual TUI 테스트 스타일 가이드

**작성**: 2026-04-16 · tui-lead
**근거**: v0.3 `troxy start` TUI 구현 중 정착한 패턴들

Textual의 `pilot.press()` / `app.run_test()` 는 강력하지만, 잘못 쓰면 깜빡이는(flake) 테스트가 되기 쉽습니다. 아래는 이번 이터레이션에서 검증된 패턴들입니다.

## 1. 테스트 레벨 3단

계층별로 호스트를 달리 씁니다.

### 1a. Widget 단위 — 최소 App 호스트

**언제**: `FilterInput`, `CopyModal`, `ConfirmDialog`, `Toast` 같은 조합 가능한 Widget 자체를 검증할 때.

```python
class _ModalHost(App):
    def __init__(self) -> None:
        super().__init__()
        self.selected: list[str] = []

    def compose(self) -> ComposeResult:
        yield CopyModal(id="cm")

    def on_copy_modal_selected(self, event: CopyModal.Selected) -> None:
        self.selected.append(event.option)
```

메시지(`Selected`, `Cancelled`)가 제대로 버블링되는지 호스트의 상태로 확인 — Widget 내부를 찌르지 말 것.

### 1b. Screen 단위 — App.on_mount에서 push_screen

**언제**: `DetailScreen`, `MockDialog` 등 독립 Screen의 동작.

```python
class TestApp(App):
    def on_mount(self):
        self.push_screen(DetailScreen(db, flow_id))

async with TestApp().run_test() as pilot:
    assert isinstance(pilot.app.screen, DetailScreen)
    await pilot.press("y")
```

`app.query_one(DetailScreen)` 은 안 됨 — Screen은 App의 child DOM이 아닙니다. **반드시 `pilot.app.screen` 또는 `app.screen`으로 접근.**

### 1c. End-to-end — 실제 App 기동

**언제**: ListScreen → DetailScreen → 복귀 같은 시나리오 체인.

```python
app = TroxyStartApp(db_path=db_with_flows)
async with app.run_test() as pilot:
    await pilot.pause()
    app.screen.action_view_detail()
    await pilot.pause()
    assert isinstance(app.screen, DetailScreen)
```

## 2. 키 입력: `pilot.press()` vs 직접 `action_*()`

| 사용 | 예시 |
|---|---|
| **실제 키 바인딩을 검증하고 싶을 때** | `await pilot.press("y")` |
| **상태 전이만 결정론적으로 찍고 싶을 때** | `app.screen.action_view_detail()` |

둘 다 유효합니다. 같은 테스트에서 섞어 써도 됨 — 키 바인딩 + 빠른 상태 셋업을 조합하면 플레이크가 줄어듭니다.

**주의**: `pilot.press()` 전에 항상 `await pilot.pause()` 한 번. 위젯이 mount되기 전에 입력을 쏘면 경쟁 상태가 납니다.

## 3. 타이머/폴링은 private 메서드 직접 호출

**문제**: `set_timer`나 `set_interval`로 도는 폴링을 `asyncio.sleep`으로 기다리면 0.5s 단위로 플레이크.

**해법**: 내부 메서드를 직접 불러 실제 분기를 검증.

```python
# ListScreen._poll_new_flows()는 0.5s 마다 타이머로 돌지만,
# 테스트에서는 조건을 만든 뒤 직접 호출해 결정론적으로 검증.
app.screen._poll_new_flows()
await pilot.pause()
assert table.row_count == after_filter, "filter view mutated by polling"
```

Private 호출이 내부 구현에 결합하는 비용 < 플레이크 비용 + 계약 명시성. 회귀 방지용 테스트에 특히 적합.

## 4. 시스템 경계는 patch

Clipboard, subprocess 같은 OS 경계는 반드시 mock.

```python
with patch("troxy.tui.detail_screen.copy_to_clipboard", return_value=True) as mock_copy:
    await pilot.press("u")
    await pilot.pause()
    mock_copy.assert_called_once()
    assert "api.example.com" in mock_copy.call_args[0][0]
```

**주의**: `patch("troxy.tui.widgets.copy_to_clipboard")`가 아니라 **import 된 자리**(`detail_screen`)에 패치해야 효과가 있음.

## 5. DB 픽스처 3단

`conftest.py`에 미리 정의됨:

| 픽스처 | 크기 | 용도 |
|---|---|---|
| `tmp_db` | 빈 DB | 로직 단위 테스트 |
| `db_with_flows` | 50 flows | 기능 테스트 (필터/detail/copy) |
| `db_10k` | 10,000 flows | 스케일 스모크 (batch insert, ~2초) |

필요 이상 큰 걸 쓰지 말 것 — `db_with_flows` 50건으로 모든 UX 계약은 검증 가능.

## 6. 포커스 함정 주의

### 6a. 숨겨진 Widget이 Input을 들고 있으면 키가 먹힘

`FilterInput`이 `display: none`이라도 내부 `Input`이 `can_focus=True`면 DOM 포커스를 채갑니다. 그러면 부모 Screen의 BINDINGS에 걸어둔 `x`, `m` 같은 단일 키가 작동 안 함.

**패턴**: 숨김 상태에서 `Input.disabled=True`로 두고 `show()`에서만 `disabled=False`로 전환.

```python
def compose(self) -> ComposeResult:
    yield Input(placeholder="...", disabled=True)

def show(self) -> None:
    inp = self.query_one(Input)
    inp.disabled = False
    self.add_class("visible")
    inp.focus()
```

### 6b. TextArea는 Tab을 삼킴

`MockDialog`처럼 여러 필드 사이를 Tab으로 돌려면, `TextArea` 안에 들어간 순간 Tab은 탭 문자를 넣고 포커스가 빠지지 않습니다. Shift+Tab으로는 탈출 가능. UX 수용 가능 여부를 리뷰 시 확인.

## 7. Message 계약을 테스트하라

Widget이 post_message로 이벤트를 쏘면, **호스트의 `on_<widget>_<message>` 핸들러가 호출되는지**를 검증 — 메시지 페이로드(`event.option`, `event.value`)까지 확인.

```python
class _Host(App):
    def on_copy_modal_selected(self, event: CopyModal.Selected) -> None:
        self.selected.append(event.option)
```

이 계약이 깨지면 CopyModal을 재사용하는 모든 화면이 조용히 고장납니다.

## 8. 파일 크기와 구조

- `tests/tui/test_<screen>.py` — 해당 화면의 단위 + screen-level 테스트
- `tests/tui/test_<widget>.py` — 위젯 단위 테스트 (widgets.py용)
- `tests/tui/test_integration.py` — End-to-end 시나리오 (여러 화면 걸쳐)

규모 커지면 쪼갤 것 — CLAUDE.md의 300줄 룰 적용.
