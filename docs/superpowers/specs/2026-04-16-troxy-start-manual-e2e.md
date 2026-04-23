# `troxy start` 수동 E2E 검증 체크리스트

**작성**: 2026-04-16 · tui-lead
**대상 커밋**: `bcbe542` (초기 구현), `a08d1f0` (버그 픽스 2건)

TUI는 TTY가 필요해서 일반 subprocess 테스트로는 실제 렌더/키입력을 확인할 수 없습니다.
릴리스 전에는 아래 시나리오를 실제 터미널에서 한 번씩 수행해주세요.

## 준비

```bash
# 클린 DB로 시작
rm -f /tmp/troxy-manual.db
```

## 시나리오

### 1. mitmdump가 백그라운드로 정상 기동

```bash
uv run troxy start -p 18099 --db /tmp/troxy-manual.db
```

기대:
- TUI 프레임이 즉시 그려짐 (헤더 `<db> · 0 flows` + DataTable 빈 상태)
- 하단에 `📡 <my-ip>` 표시
- 힌트 바: `↑↓ browse · ⏎ detail · f filter · m mock · M mocks · x clear · q quit`

별도 터미널에서 확인:
```bash
pgrep -fl "mitmdump.*18099"
# → 한 줄 출력되어야 함
```

### 2. 프록시 경유 요청이 TUI에 실시간 반영

별도 터미널:
```bash
curl -sS -x http://127.0.0.1:18099 http://httpbin.org/get
```

기대:
- 0.5s 이내에 TUI 테이블에 `GET · httpbin.org · /get · 200` 행 추가
- 헤더 카운트가 `0 flows` → `1 flows`

### 3. 정상 종료 (`q` 키)

TUI에서 `q` 입력.

기대:
- TUI 프로세스 종료, 터미널 복원
- `pgrep -fl mitmdump.*18099` → 없음 (자동 정리됨)

### 4. 비정상 종료 시 cleanup (SIGTERM)

다시 start한 뒤 별도 터미널에서:
```bash
TROXY_PY=$(pgrep -f "\.venv/bin/troxy start -p 18099")
kill -TERM $TROXY_PY
```

기대:
- TUI가 즉시 종료
- mitmdump도 자동 정리됨 — `a08d1f0`의 SIGTERM→SystemExit 핸들러가 `finally`를 강제 실행

### 5. Ctrl+C

TUI 떠 있는 상태에서 터미널에서 Ctrl+C 입력.

기대:
- Textual이 key binding으로 소비하거나 앱 종료
- mitmdump orphan 없음

### 6. 포트 충돌 / mitmdump 미설치

```bash
# 다른 프로세스가 18099 점유 중일 때
uv run troxy start -p 18099
```
→ 현재는 Popen이 실패 메시지를 stderr에 찍고 TUI가 "0 flows"로 뜸.
**개선 여지**: mitmdump 기동 실패 시 TUI 실행 전에 명시적 에러 메시지 + exit(1) 하면 좋음 (다음 이터레이션 후보).

## 알려진 한계

- `SIGKILL`로 부모를 강제로 죽이면 mitmdump는 정리되지 않음 (OS-level signal handler로는 방어 불가).
  → macOS/Linux 모두 공통. 필요하면 별도 `trap` wrapper 스크립트 또는 `PR_SET_PDEATHSIG`(Linux-only) 도입 검토.
- TUI가 TTY 없이 실행되면 Textual이 fallback 모드로 뜨고 키 입력을 받지 못함 (subprocess 자동화에서만 발생).

## 자동화된 커버리지

- `tests/e2e/test_start.py::test_start_cmd_help_shows_port_option` — CLI 옵션 표면 검증
- `tests/e2e/test_start.py::test_start_cmd_launches_and_quits` — subprocess 스모크 (TUI 렌더는 검증 못함)
- `tests/tui/test_proxy.py::test_proxy_passes_db_path_via_env` — TROXY_DB 환경변수 전달 (a08d1f0 회귀 방지)
- `tests/tui/test_proxy.py::test_proxy_start_stop` — Popen/SIGTERM lifecycle

## 검증 로그 (tui-lead 2026-04-16)

- [x] 시나리오 1: mitmdump 기동 확인 (pid 10023)
- [x] 시나리오 2: httpbin.org/get → /tmp/troxy-manual.db 1 flow 기록
- [x] 시나리오 4: SIGTERM 후 orphan 없음 (a08d1f0 적용 후)
- [ ] 시나리오 3/5: 실제 TTY 필요 — 릴리스 담당자 수동 확인 필요
