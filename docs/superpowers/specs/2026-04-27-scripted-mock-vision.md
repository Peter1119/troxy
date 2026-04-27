# Scripted Mock Vision — 제품 성공지표 & 스코프 가이드라인

**작성일**: 2026-04-27  
**작성자**: CEO (troxy-scripted-mock 팀)  
**리뷰어**: CTO

---

## 1. 사용자 페인 포인트 (현재 워크플로 분석)

### 1-A. 단순 mock 생성 — 현재 단계 수

목표: "최근 API 응답을 mock으로 만들어 body를 수정하고 활성화"

| # | MCP 호출 | 설명 |
|---|----------|------|
| 1 | `troxy_list_flows` | 어떤 flow를 쓸지 확인 |
| 2 | `troxy_get_flow` | body/header 내용 확인 |
| 3 | `troxy_mock_from_flow` | flow → mock rule 생성 |
| 4 | `troxy_mock_list` | 생성된 rule ID 확인 |
| 5 | `troxy_mock_remove` + `troxy_mock_add` | body/header 수정 (직접 수정 API 없음) |
| 6 | `troxy_mock_toggle` | 활성화 |

**최소 4–6 MCP 호출**, 수정이 생기면 remove + re-add로 추가 2회.

### 1-B. 시나리오 mock — 현재는 불가능

목표: "refresh #1=200, #2=500, #3=503, #4=200 순서로 응답 변화"

현재 `mock_rules` 테이블 스키마:
- `status_code`, `response_headers`, `response_body` — 단일 정적 값
- 요청 횟수 카운터 없음, 시퀀스 개념 없음

현재 유일한 우회책:
1. 4개의 별도 mock rule 생성 (6×4 = 24회 MCP 호출)
2. 각 refresh 후 수동으로 toggle off/on
3. 또는 intercept hold/release 를 매번 수동 개입 (비현실적)

**결론: 시나리오 mock은 현재 구조상 지원 불가.**

### 1-C. 측정된 마찰 요약

| 지표 | 현재 | 목표 |
|------|------|------|
| 단순 mock 생성 MCP 호출 수 | 4–6회 | **1–2회** |
| body 수정 MCP 호출 수 | 2회 (remove+add) | **1회 (update)** |
| 4-단계 시나리오 mock 생성 | 불가능 | **단일 명령** |
| 시나리오 실행 중 인간 개입 | 매 refresh마다 | **0회** |

---

## 2. 성공지표

### 2-A. 워크플로 단순화

- **S1**: 기존 flow에서 mock 생성 + body 수정 + 활성화를 **2회 이하** MCP 호출로 완료
  - 측정: `troxy_mock_from_flow(flow_id, body=..., status_code=..., enabled=True)` 단일 호출
- **S2**: 기존 mock rule의 body/header/status 수정을 **1회** MCP 호출로 완료
  - 측정: `troxy_mock_update(id, body=..., headers=...)` 신규 tool 추가

### 2-B. 시나리오(Scripted) Mock

- **S3**: N개 응답 시퀀스를 단일 명령으로 정의 가능
  - 측정: `troxy_mock_add(path=..., script=[{status:200, body:...}, {status:500, body:...}])` 1회 호출
- **S4**: 시퀀스가 자동으로 순환됨 — 인간 개입 0회
  - 측정: 4회 refresh 시 정의된 순서대로 4가지 응답 반환 (E2E 테스트 통과)
- **S5**: 시퀀스 소진 후 동작 선택 가능 (마지막 응답 반복 / 첫 응답으로 순환)
  - 측정: `loop: true/false` 옵션

### 2-C. 관찰 가능성

- **S6**: `troxy_mock_list` 에서 시나리오 mock의 현재 스텝 인덱스 노출
  - 측정: `{"current_step": 2, "total_steps": 4}` 형태 응답
- **S7**: mock reset (스텝 인덱스 초기화) 가능
  - 측정: `troxy_mock_reset(id)` tool

---

## 3. 스코프 가이드라인

### 3-A. In-Scope (이번 버전에서 구현)

| 항목 | 근거 |
|------|------|
| HTTP/HTTPS mock 시퀀스 | 핵심 유스케이스 |
| 응답당 `status_code`, `response_body`, `response_headers` 변경 | 사용자 원본 요구 |
| 시퀀스 소진 후 loop/hold 옵션 | 실용적 시나리오 완성도 |
| `troxy_mock_update` tool (부분 수정) | 워크플로 단순화 필수 |
| `troxy_mock_from_flow` 개선 (body/enabled 파라미터 추가) | 단계 수 감소 |
| `troxy_mock_reset` tool (스텝 인덱스 리셋) | 관찰 가능성 |
| DB 스키마 마이그레이션 (기존 mock_rules 호환) | 무중단 업그레이드 |
| unit + e2e 테스트 | 품질 기준 |

### 3-B. Out-of-Scope (이번 버전에서 제외)

| 항목 | 제외 이유 |
|------|-----------|
| gRPC mock | 별도 transport 레이어, mitmproxy addon 대규모 변경 필요 |
| WebSocket mock | 양방향 스트리밍, 모델 완전히 다름 |
| 요청 내용 기반 분기 (request body matching) | 복잡도 급증, 별도 스펙 필요 |
| 응답 딜레이(latency injection) | 유용하나 이번 스코프 외 |
| 시각적 GUI/Web UI | CLI/MCP 우선 |
| 외부 파일 import (fixture 파일 경로 지정) | nice-to-have, 보안 고려 필요 |
| 조건부 시퀀스 (if 헤더 X then step Y) | 복잡도 급증 |

---

## 4. 비기능 요구사항

### 4-A. 아키텍처 레이어 규칙 준수

- `src/troxy/core/`는 `mitmproxy` import **절대 금지**
- 시퀀스 스텝 관리 로직은 `core/mock.py` 또는 `core/mock_sequence.py`에만 위치
- `addon.py`만 mitmproxy 의존; 시퀀스 인덱스 조회/증가는 `core` 함수 호출로 처리
- `cli`와 `mcp`는 서로 import 금지

### 4-B. 새 PyPI 의존성 0

- SQLite의 기본 기능(`json_each`, `CASE WHEN` 등)만 활용
- Python 표준 라이브러리 범위 내에서 구현
- 이미 사용 중인 `mcp`, `click`, `rich` 외 추가 패키지 없음

### 4-C. 기존 mock_rules CRUD 호환성

- 현재 단일 응답 mock rule(= step이 1개인 시나리오)은 그대로 동작
- `list_mock_rules`, `remove_mock_rule`, `toggle_mock_rule` API 시그니처 변경 없음
- DB 마이그레이션: 기존 rows에 `script` 컬럼 `NULL` → 단일 응답으로 fallback

### 4-D. 스레드 안전성

- `addon.py`는 mitmproxy worker thread에서 호출됨
- 시퀀스 인덱스 증가는 SQLite `UPDATE ... RETURNING` 또는 `BEGIN IMMEDIATE` 트랜잭션으로 원자적 처리

### 4-E. 파일 크기 제한

- `scripts/check_file_size.py` 기준 준수 (신규 파일 각각 500줄 이하 목표)
- 필요 시 `core/mock_sequence.py`로 분리

---

## 5. 우선순위 (MUST / SHOULD / COULD)

### MUST (MVP — 없으면 출시 불가)

| ID | 항목 |
|----|------|
| M1 | `mock_rules` 테이블에 `script` 컬럼 추가 (JSON array of steps) |
| M2 | `mock_step_index` 컬럼 추가 — 현재 어느 스텝까지 반환했는지 추적 |
| M3 | addon이 요청 매칭 시 현재 스텝 반환 + 인덱스 원자적 증가 |
| M4 | `troxy_mock_add` — `script` 파라미터 지원 (배열) |
| M5 | `troxy_mock_reset` MCP tool |
| M6 | `troxy_mock_list` — 현재 스텝 인덱스 노출 |
| M7 | 기존 단일 응답 mock rule과 완전 하위 호환 |
| M8 | Unit 테스트: 시퀀스 증가, loop, 소진 동작 |

### SHOULD (1차 릴리즈에 포함 권장)

| ID | 항목 |
|----|------|
| S1 | `troxy_mock_update` MCP tool (부분 수정, remove+add 불필요) |
| S2 | `troxy_mock_from_flow` — `body`, `headers`, `enabled` 파라미터 추가 |
| S3 | `loop` 옵션 — 시퀀스 소진 후 첫 스텝으로 돌아감 (기본 OFF = 마지막 응답 반복) |
| S4 | E2E 테스트: 4-단계 시나리오 mock 전체 흐름 검증 |
| S5 | CLI에 `troxy mock script` 서브커맨드 추가 |

### COULD (2차 릴리즈 이후 고려)

| ID | 항목 |
|----|------|
| C1 | 응답 딜레이(latency) per-step 설정 |
| C2 | 외부 JSON fixture 파일 경로로 script 정의 |
| C3 | `troxy_mock_duplicate` — 기존 rule 복사 (시나리오 분기 용이) |
| C4 | 시나리오 mock 실행 이력 로그 (어떤 스텝이 언제 반환됐는지) |
| C5 | 요청 횟수 기반이 아닌 시간 기반 전환 (N초 후 다음 스텝) |

---

## 6. 데이터 모델 스케치 (CTO 검토용 초안)

> **⚠️ 업데이트 (2026-04-27 CTO cross-review 반영)**: 아래 초안은 `mock_rules` 확장 방식이었으나, CTO ADR-1에서 **`mock_scenarios` 신설** 방식으로 확정되었습니다. 이유: `mock_rules`에 NULL 컬럼 오염 방지, 기존 테이블 완전 무변경으로 M7 하위 호환 달성, ALTER TABLE 없이 CREATE TABLE IF NOT EXISTS로 안전한 마이그레이션. 확정 스키마는 `2026-04-27-scripted-mock-architecture.md` §2 ADR-1 참조.

```sql
-- ❌ 초안 (폐기) — mock_rules 확장 방식
-- ALTER TABLE mock_rules ADD COLUMN script TEXT DEFAULT NULL;
-- ALTER TABLE mock_rules ADD COLUMN step_index INTEGER DEFAULT 0;
-- ALTER TABLE mock_rules ADD COLUMN loop INTEGER DEFAULT 0;

-- ✅ 확정 (ADR-1) — mock_scenarios 신설
CREATE TABLE IF NOT EXISTS mock_scenarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    domain          TEXT,
    path_pattern    TEXT,
    method          TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    current_step    INTEGER NOT NULL DEFAULT 0,
    steps           TEXT    NOT NULL,  -- JSON: [{status_code, headers, response_body, label?}]
    loop            INTEGER NOT NULL DEFAULT 0,
    created_at      REAL    NOT NULL
);
-- steps 내부 헤더 키: "headers" (간결함 우선, CTO cross-review 합의)
```

### 시퀀스 응답 로직 (addon.py 내부)

```python
# pseudo-code — core/scenarios.py get_and_advance_step()으로 구현 (ADR-2)
def get_and_advance_step(db_path, scenario_id) -> dict | None:
    """원자적으로 현재 스텝 응답 반환 + 인덱스 증가. BEGIN IMMEDIATE tx."""
    with BEGIN IMMEDIATE transaction:
        row = SELECT current_step, steps, loop FROM mock_scenarios WHERE id = scenario_id AND enabled = 1
        if not row: return None
        steps = json.loads(row.steps)
        idx = row.current_step
        step = steps[idx]                              # 현재 스텝 캡처
        next_idx = (idx + 1) % len(steps) if row.loop else min(idx + 1, len(steps) - 1)
        UPDATE mock_scenarios SET current_step = next_idx WHERE id = scenario_id
        return step
```

---

## 7. 구현 완료 정의 (Definition of Done)

- [ ] `uv run pytest` 전체 통과 (unit + e2e)
- [ ] `uv run python scripts/lint_layers.py` 위반 0건
- [ ] `uv run python scripts/check_file_size.py` 위반 0건
- [ ] 기존 mock_rules 데이터 마이그레이션 검증 (기존 rows 동작 변화 없음, `mock_scenarios` 신규 테이블만 추가)
- [ ] 4-단계 시나리오 E2E 테스트 통과: `[200, 500, 503, 200]` 순환 확인
- [ ] MCP tool 문서 (`tools.py` schema) 업데이트 — `troxy_scenario_*` 6개 tool
- [ ] `troxy_scenario_list` 출력에 `current_step`/`total_steps` 포함

---

*이 문서는 팀 전체의 구현 방향 정렬을 위한 CEO 관점의 성공 기준이다. 구체적 기술 설계(DB 스키마 확정, 함수 시그니처, 마이그레이션 전략)는 CTO 스펙 문서에서 상세화한다.*
