# Scripted Mock — Architecture Spec (ADR)

> 작성: CTO · 2026-04-27  
> 상태: **✅ 최종 확정** (team-lead final decision · 2026-04-27)  
> 참조: `2026-04-27-scripted-mock-vision.md` (CEO)

---

## ⚡ FINAL DECISIONS (team-lead · 2026-04-27)

| # | 항목 | **최종 결정** |
|---|------|--------------|
| 1 | 데이터 모델 | **`mock_scenarios` 신규 테이블** — CTO 결정 유지 |
| 2 | MCP 도구 | **`troxy_mock_add`에 `sequence` 배열 파라미터** — Designer 결정 유지. `sequence` 있으면 `mock_scenarios`에 저장, 없으면 `mock_rules`. 신규 tool: `troxy_mock_reset`, `troxy_mock_update`만 추가 |
| 3 | steps JSON 헤더 키 | **`headers`** — 짧은 키, JSON 페이로드 내에서 모호하지 않음 |

---

## 1. 배경 및 목표

사용자 요구:

> "refresh #1 = 정상 → #2 = 에러 → #3 = 다른 에러 → #4 = 정상" 같은 시나리오 응답 지원.  
> 그리고 mock 생성 워크플로 단순화.

현재 `mock_rules`는 단일 고정 응답만 지원한다. 동일 URL에 요청이 반복될 때 순서에 따라 다른 응답을 내려주는 "시나리오 mock"이 없다.

CEO 비전 문서(§1)에서 정량화된 페인 포인트:
- 단순 mock 생성: 현재 4–6 MCP 호출 → 목표 1–2회
- 4-단계 시나리오 mock: 현재 불가능 → 단일 명령으로

---

## 2. 핵심 설계 결정 (ADR)

---

### ADR-1: `mock_scenarios` 테이블 신설 vs `mock_rules` 확장

#### CEO 비전 초안과의 차이

CEO 비전 §6은 `mock_rules` 테이블에 `script`, `step_index`, `loop` 컬럼을 추가하는 방향을 초안으로 제시했다. 이 ADR에서는 별도 테이블을 신설하는 방향으로 결정하며, 그 이유를 아래에 설명한다.

#### 선택지 비교

| | 방안 A: `mock_rules` 확장 (CEO 초안) | 방안 B: `mock_scenarios` 신설 (CTO 채택) |
|---|---|---|
| 스키마 변경 | `script JSON`, `step_index`, `loop` 컬럼 추가 | 새 테이블, 기존 테이블 무변경 |
| 단일 응답 규칙의 NULL 오염 | script=NULL, step_index=0 등 의미없는 값 | 없음 (테이블 분리) |
| 하위 호환 (M7) | script=NULL이면 기존 동작 fallback | 완전히 별개 테이블, 완전 호환 |
| addon 코드 조건 분기 | if script is NULL else 시퀀스 로직 | 별도 `_check_scenario` 메서드 |
| 장기 확장성 | 테이블이 두 역할 겸임, SRP 위반 | 시나리오 전용 컬럼 자유롭게 추가 |
| CLI/MCP 통합 표면 | `troxy_mock_*` 단일 네임스페이스 | `troxy_mock_*` (단순) + `scenario reset/from-flows` |
| 마이그레이션 | ALTER TABLE + `_run_migrations` | CREATE TABLE IF NOT EXISTS (ALTER 불필요) |

#### 결정: **방안 B — `mock_scenarios` 신설**

핵심 근거:

1. **단일 테이블 이중 역할 회피**: script=NULL → 기존 동작, script=JSON → 시나리오 동작의 이분법은 `mock_rules` 테이블이 두 가지 의미론적으로 다른 엔티티를 담게 만든다. 기존 rows는 영구적으로 step_index=0, loop=0이라는 무의미한 값을 가져야 한다.

2. **addon 코드 명확성**: `_check_mock` 내에 `if rule["script"]` 분기를 추가하면 단일 메서드가 두 가지 동작 모드를 처리해야 한다. 별도 `_check_scenario`로 분리하면 각 메서드의 책임이 명확하다.

3. **하위 호환 M7 달성**: 기존 `mock_rules` 테이블을 전혀 변경하지 않으므로 기존 rows는 완전히 동일하게 동작한다. ALTER TABLE이 없으므로 기존 DB의 기존 rows에 NULL이 생기는 문제도 없다.

4. **CEO 비전 M4/S3 달성**: `troxy_mock_add`에 `script` 파라미터를 추가하는 대신, 시나리오 전용 `troxy_scenario_add`를 노출한다. 사용자 입장에서 "단일 명령" 요구사항은 동일하게 충족된다.

> **CEO에 대한 요청**: 방안 A(테이블 확장)가 아닌 방안 B(신규 테이블)로 결정한 이유를 위에 설명했습니다. `troxy_mock_add`에 `script` 파라미터를 통합하는 것 vs `troxy_scenario_add` 별도 tool이 UX상 차이가 있는지 CEO 관점에서 피드백 주시면 반영하겠습니다.

#### 스키마

```sql
CREATE TABLE IF NOT EXISTS mock_scenarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    domain          TEXT,
    path_pattern    TEXT,
    method          TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    current_step    INTEGER NOT NULL DEFAULT 0,
    steps           TEXT    NOT NULL,   -- JSON: [{status_code, response_headers, response_body, label?}]
    loop            INTEGER NOT NULL DEFAULT 0,
    created_at      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenarios_enabled ON mock_scenarios(enabled);
```

##### `steps` JSON 포맷

```json
[
  {"status_code": 200, "headers": {}, "body": "OK",          "label": "정상"},
  {"status_code": 500, "headers": {}, "body": "Error",       "label": "서버오류"},
  {"status_code": 503, "headers": {}, "body": "Unavailable", "label": "일시적오류"},
  {"status_code": 200, "headers": {}, "body": "OK",          "label": "복구됨"}
]
```

- `headers`: 선택 필드, 응답 헤더 dict (CEO 합의: `response_headers` → `headers`로 단축)
- `body`: 선택 필드, 응답 body 문자열
- `label`: 선택 필드, 표시 전용, 동작에 영향 없음

---

### ADR-2: 카운터 저장 — DB `current_step` vs 메모리

CEO 비전 §4-D와 동일 방향: `BEGIN IMMEDIATE` 트랜잭션으로 원자적 처리.

#### 선택지

| | 방안 A: 메모리 카운터 | 방안 B: DB `current_step` + SQLite IMMEDIATE tx (채택) |
|---|---|---|
| 속도 | 최고 (메모리) | 충분 (WAL 모드, dev/test 규모) |
| addon 재시작 후 | 0 리셋 | 유지 |
| 프로세스 크래시 후 | 0 리셋 | 유지 |
| CLI/MCP에서 step 확인 | 불가 | 가능 (`troxy_mock_list`에서 current_step 노출 — 비전 S6) |
| race 처리 | Python GIL + Lock 필요 | SQLite IMMEDIATE transaction이 직렬화 |

#### 결정: **방안 B — DB `current_step` + SQLite IMMEDIATE transaction**

- mitmproxy addon이 재시작되어도 step 위치가 보존된다.
- CLI/MCP에서 `troxy scenario list`로 현재 step 상태 확인 가능 (비전 S6/M6 충족).
- SQLite WAL 모드에서 IMMEDIATE transaction은 쓰기를 직렬화 → lost-update 없음.
- troxy는 개발/테스트 전용 도구. DB I/O 오버헤드는 허용 범위 내.

#### Atomic step advance 패턴

```python
# core/scenarios.py
def get_and_advance_step(db_path: str, scenario_id: int) -> dict | None:
    """현재 step 데이터를 반환하고 다음으로 전진 (원자적)."""
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT current_step, steps, loop FROM mock_scenarios WHERE id = ? AND enabled = 1",
            (scenario_id,)
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return None
        steps = json.loads(row["steps"])
        idx = row["current_step"]
        step = steps[min(idx, len(steps) - 1)]   # 소진 시 마지막 step 반환
        total = len(steps)
        if row["loop"]:
            next_idx = (idx + 1) % total          # loop=true: 순환
        else:
            next_idx = min(idx + 1, total - 1)    # loop=false: 마지막 step에 clamp
        conn.execute(
            "UPDATE mock_scenarios SET current_step = ? WHERE id = ?",
            (next_idx, scenario_id)
        )
        conn.execute("COMMIT")
        return step
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
```

#### loop=false 소진 동작

마지막 step에서 무한 반복 (clamp). 비전 S3/S5: `loop: true/false` 옵션 — `loop=false`(기본)면 마지막 응답 반복, `loop=true`면 첫 step으로 순환. 둘 다 지원.

---

### ADR-3: addon 통합 흐름

#### 신규 `_check_scenario` 메서드 삽입 위치

```
request hook
  ├─ _check_scenario(flow)   ← 신규 (mock_rules보다 먼저)
  │    └─ 매칭 시나리오 있으면 → step 응답 후 return
  └─ _check_mock(flow)        ← 기존 (시나리오 불일치 fallback)
       └─ 매칭 규칙 있으면 → 단일 응답 후 return
```

#### `_check_scenario` 처리 흐름

```
1. list_enabled_scenarios(db_path) 호출
2. domain / method / path_pattern 매칭 (기존 _check_mock과 동일 fnmatch 로직)
3. 첫 번째 매칭 시나리오 발견 시:
   a. get_and_advance_step(db_path, scenario_id)  ← atomic DB tx
   b. step["status_code"], step["response_headers"], step["response_body"]로 Response 구성
   c. flow.response = http.Response.make(...)
   d. return  (이후 _check_mock 호출 안 함)
4. 매칭 없으면 아무것도 하지 않고 return
```

#### addon.py 변경 범위

```python
def request(self, flow):
    try:
        self._check_scenario(flow)   # ← 추가
        if not flow.response:
            self._check_mock(flow)
        if not flow.response:
            self._check_intercept(flow)
    except Exception as e:
        ...
```

---

### ADR-4: 시나리오 vs `mock_rules` 우선순위

#### 결정: **시나리오가 항상 우선**

| 시나리오 매칭 | mock_rules 매칭 | 동작 |
|---|---|---|
| ✅ 활성 | ✅ | 시나리오 응답 |
| ✅ 비활성 | ✅ | mock_rules 응답 |
| ❌ | ✅ | mock_rules 응답 |
| ❌ | ❌ | 실제 서버로 통과 |

---

### ADR-5: 마이그레이션 전략

#### 방침: `_SCHEMA_SQL`에 `CREATE TABLE IF NOT EXISTS` 추가 + `_run_migrations` 확장

신규 테이블이므로 기존 DB를 가진 사용자에게 자동으로 테이블이 생성된다. `mock_rules`에 ALTER TABLE이 없으므로 기존 rows는 완전히 무변경 (M7 충족).

```python
# db.py _SCHEMA_SQL 추가분
"""
CREATE TABLE IF NOT EXISTS mock_scenarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    domain          TEXT,
    path_pattern    TEXT,
    method          TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    current_step    INTEGER NOT NULL DEFAULT 0,
    steps           TEXT    NOT NULL,
    loop            INTEGER NOT NULL DEFAULT 0,
    created_at      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenarios_enabled ON mock_scenarios(enabled);
"""
```

`DB_SCHEMA_VERSION`은 `2`로 bump (현재 `1`).

---

### ADR-6: `mock_rules` 워크플로 단순화 (CEO 비전 §2 반영)

CEO 비전의 MUST/SHOULD 항목 중 기존 `mock_rules` 개선 사항을 반영한다.

#### `troxy_mock_update` 신규 tool (비전 S1)

현재 수정 방법은 remove + add (2회). `update`로 1회로 단축.

```python
# core/mock.py 추가
def update_mock_rule(
    db_path: str,
    rule_id: int,
    *,
    status_code: int | None = None,
    response_headers: str | None = None,
    response_body: str | None = None,
    enabled: bool | None = None,
) -> None:
    """기존 mock rule 부분 업데이트."""
```

#### `mock_from_flow` 파라미터 확장 (비전 S2)

```python
# core/mock.py 기존 함수 시그니처 확장
def mock_from_flow(
    db_path: str,
    flow_id: int,
    *,
    status_code: int | None = None,
    response_body: str | None = None,     # ← 신규: flow body 오버라이드
    response_headers: str | None = None,  # ← 신규: 헤더 오버라이드
    enabled: bool = True,                 # ← 신규: 바로 활성화 여부
    name: str | None = None,
) -> int:
```

이 두 개선으로 비전 §1-A의 4–6 MCP 호출 → 1–2회 달성.

---

## 3. 신규 파일 구조

```
src/troxy/core/
  scenarios.py          ← 신규 (300줄 이내 목표)
  mock.py               ← update_mock_rule 추가, mock_from_flow 파라미터 확장

src/troxy/
  addon.py              ← _check_scenario 메서드 추가

src/troxy/cli/
  commands/scenarios.py ← 신규 CLI 커맨드 (add/list/reset/remove/toggle/from-flows)

src/troxy/mcp/
  server.py             ← 시나리오 MCP tool 추가 + mock_update, mock_from_flow 개선
```

---

## 4. `scenarios.py` 공개 API

```python
def add_scenario(
    db_path: str,
    *,
    domain: str | None = None,
    path_pattern: str | None = None,
    method: str | None = None,
    name: str | None = None,
    steps: list[dict],         # [{status_code, response_headers?, response_body?, label?}]
    loop: bool = False,
) -> int:
    """시나리오 추가. 생성된 ID 반환."""

def list_scenarios(db_path: str, *, enabled_only: bool = False) -> list[dict]:
    """시나리오 목록 조회 (current_step, total_steps 포함 — 비전 S6/M6)."""

def remove_scenario(db_path: str, scenario_id: int) -> None:
    """시나리오 삭제."""

def toggle_scenario(db_path: str, scenario_id: int, *, enabled: bool) -> None:
    """시나리오 활성/비활성화."""

def reset_scenario(db_path: str, scenario_id: int) -> None:
    """current_step을 0으로 리셋 (비전 S7/M5)."""

def resolve_scenario_ref(db_path: str, ref: str | int) -> int:
    """ID 또는 name으로 scenario_id 해석."""

def scenario_from_flows(
    db_path: str,
    flow_ids: list[int],
    *,
    name: str | None = None,
    loop: bool = False,
) -> int:
    """여러 flow의 응답을 순서대로 묶어 시나리오 생성."""

def get_and_advance_step(db_path: str, scenario_id: int) -> dict | None:
    """현재 step 데이터 반환 + 다음 step으로 원자적 전진. addon hot path에서 사용."""
```

---

## 5. MCP/CLI tool 노출

> Designer DX 설계(Task #4) 반영 · 2026-04-27  
> **핵심 결정**: MCP는 `troxy_mock_*` 네임스페이스 통합, CLI는 `troxy scenario` 서브그룹 신설

### MCP tools

| Tool | 변경 | 시나리오 파라미터 | 비전 항목 |
|------|------|------------------|-----------|
| `troxy_mock_add` | **파라미터 확장** | `sequence=[{status_code, body?, headers?}, ...]` + `loop` 추가 | M4 |
| `troxy_mock_list` | **응답 확장** | 응답에 `current_step`, `total_steps`, `is_sequence` 포함 | M6, S6 |
| `troxy_mock_reset` | **신규** | `id` 또는 `name` | M5, S7 |
| `troxy_mock_update` | **신규** | `id`, 수정할 필드 선택적 | S1 |
| `troxy_mock_from_flow` | **파라미터 확장** | `body`, `headers`, `enabled` 추가 | S2 |
| `troxy_mock_remove` | 기존 유지 | — | — |
| `troxy_mock_toggle` | 기존 유지 | — | — |

**`troxy_scenario_*` 별도 tool 없음.** `troxy_mock_add(sequence=[...])` 한 번으로 동일 기능 제공.  
MCP 파라미터 이름은 `sequence` (내부 DB 컬럼명 `steps`와 다름 — 매핑은 MCP layer에서 처리).

### `troxy_mock_add` 확장 예시

```json
{
  "domain": "api.example.com",
  "path_pattern": "/v1/cart",
  "method": "POST",
  "sequence": [
    {"status_code": 200, "body": "{\"ok\":true}",  "headers": {"Content-Type": "application/json"}},
    {"status_code": 500, "body": "{\"err\":true}", "headers": {"Content-Type": "application/json"}},
    {"status_code": 200, "body": "{\"ok\":true}",  "headers": {"Content-Type": "application/json"}}
  ],
  "loop": true
}
```

`sequence` 제공 시 `status_code`/`body`/`headers` 단순 파라미터는 무시 + 경고 반환.

### CLI 커맨드

```bash
# 시나리오 생성 — CLI는 troxy scenario 서브그룹
troxy scenario add "200,500:body={\"err\":true},200" \
  --domain api.example.com --path /v1/cart [--loop] [--name cart-retry]

# 여러 flow → 시나리오
troxy scenario from-flows 42 55 67 [--name login-sequence] [--loop]

# 조회/관리
troxy scenario list
troxy scenario reset <id|name>   # = troxy mock reset <id|name> (별칭)
troxy scenario remove <id|name>

# mock_rules 개선 (기존 명령 파라미터 확장)
troxy mock from-flow 42 --body '{"ok":true}' --enabled   # S2
troxy mock update 7 --status 503 --body '{"err":"maint"}' # S1
```

---

## 6. 레이어 영향 요약

| 레이어 | 변경 내용 | mitmproxy import |
|--------|----------|-----------------|
| `core/db.py` | `_SCHEMA_SQL`에 `mock_scenarios` 테이블 추가, `DB_SCHEMA_VERSION=2` | ❌ |
| `core/scenarios.py` | 신규 — CRUD + atomic step advance | ❌ |
| `core/mock.py` | `update_mock_rule` 추가, `mock_from_flow` 파라미터 확장 | ❌ |
| `addon.py` | `_check_scenario` 메서드 추가 | ✅ (기존과 동일) |
| `cli/` | `scenario` 서브커맨드 추가 | ❌ |
| `mcp/server.py` | 시나리오 MCP tool 6개 + mock_update/mock_from_flow 개선 | ❌ |

레이어 규칙 (`addon → core ← cli, mcp`) 완전 준수. 새 PyPI 의존성 0 (비전 §4-B 준수).

---

## 7. CEO 비전 MUST 항목 달성 매핑

| 비전 ID | 항목 | CTO 스펙 대응 |
|---------|------|--------------|
| M1 | script 컬럼 추가 | `mock_scenarios.steps` JSON (신규 테이블) |
| M2 | step_index 컬럼 | `mock_scenarios.current_step` |
| M3 | 요청 매칭 시 현재 스텝 반환 + 원자적 증가 | `get_and_advance_step` + IMMEDIATE tx |
| M4 | `troxy_mock_add` sequence 파라미터 | `troxy_mock_add(sequence=[...])` — Designer 확정 ✅ |
| M5 | `troxy_mock_reset` | `troxy_mock_reset` — Designer 확정 ✅ |
| M6 | `troxy_mock_list` 스텝 인덱스 노출 | `troxy_mock_list` 응답에 `current_step`/`total_steps`/`is_sequence` 추가 ✅ |
| M7 | 기존 mock rule 완전 하위 호환 | `mock_rules` 테이블 무변경으로 완전 호환 ✅ |
| M8 | unit 테스트 | engineer/qa task에서 커버 |

---

## 8. 확정 사항 (CEO 최종 승인 · 2026-04-27)

| 항목 | 결정 |
|------|------|
| ADR-1: `mock_scenarios` 신설 | ✅ CEO 승인 |
| ADR-2: DB `current_step` + IMMEDIATE tx | ✅ CEO 승인 |
| ADR-3: addon 통합 흐름 | ✅ CEO 승인 |
| ADR-4: 시나리오 우선순위 | ✅ CEO 승인 |
| ADR-5: CREATE TABLE IF NOT EXISTS 마이그레이션 | ✅ CEO 승인 |
| 동시 활성 시나리오 수 제한 | 무제한 (고성능 시나리오는 Out-of-scope) |
| steps 소진 후 동작 | MVP: 마지막 step 반복. `on_exhaust` 필드는 향후 ALTER TABLE로 추가 |
| MCP tool 이름 | `troxy_mock_*` 통합 (Designer 확정: `troxy_mock_add(sequence=[...])`) |
| steps JSON 헤더 키 | `headers` (CEO 합의 · `response_headers` 아님) |
| steps JSON body 키 | `body` |
| multi-tenant | Out-of-scope (별도 ADR) |

---

## 9. 다음 단계

- [x] CEO vision 문서 cross-review → 완료
- [x] CEO 최종 승인 → 모든 ADR 확정
- [x] steps JSON 키 확정 (`headers`, `body`)
- [x] Designer DX 설계 (Task #4) → MCP: `troxy_mock_*` 통합, CLI: `troxy scenario` 서브그룹
- [ ] Engineer 구현 (Task #5): `core/db.py` → `core/scenarios.py` → `core/mock.py` → `addon.py` → MCP/CLI 순
  - MCP: `troxy_mock_add(sequence=[...])` — 내부 `mock_scenarios` 테이블 사용
  - MCP: `troxy_mock_list` 응답 확장, `troxy_mock_reset` 신규, `troxy_mock_update` 신규
  - CLI: `troxy scenario` 서브그룹 신설
  - S1 포함: `troxy_mock_update`
  - S2 포함: `mock_from_flow` 파라미터 확장 (body/headers/enabled)
- [ ] QA 테스트 플랜 (Task #6): step advance 원자성, loop/non-loop 경계, 기존 mock_rules 회귀
