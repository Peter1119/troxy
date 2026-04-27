# Scripted Mock — Test Plan

**작성일**: 2026-04-27  
**작성자**: QA (troxy-scripted-mock 팀)  
**리뷰어**: Engineer  
**참고 문서**: scripted-mock-spec.md, scripted-mock-architecture.md, scripted-mock-vision.md, scripted-mock-dx.md  
**업데이트**: Designer DX 스펙 반영 — `troxy_mock_add(sequence=...)` 확장 방식 채택

---

## 1. 테스트 범위 요약

| 구분 | 파일 | 대상 |
|------|------|------|
| Unit | `tests/unit/test_scenarios.py` | `core/scenarios.py` CRUD + step advance 로직 |
| E2E CLI | `tests/e2e/test_scenarios_cli.py` | CLI `troxy scenario` 서브커맨드 |
| E2E MCP | `tests/e2e/test_scenarios_mcp.py` (신규) | `troxy_mock_add(sequence=...)` + `troxy_mock_reset` + `troxy_mock_update` |
| 회귀 | 기존 전체 suite | 기존 mock/intercept/flow 기능 무변화 확인 |

> **Designer 결정**: `troxy_scenario_*` 별도 tool 대신 기존 `troxy_mock_*` 네임스페이스 확장.
> `troxy_mock_add(sequence=[...])`, `troxy_mock_reset`, `troxy_mock_update` 신규 추가.

---

## 2. 테스트 매트릭스

### 2-A. Happy Path

| TC-ID | 설명 | 입력 | 기대 결과 |
|-------|------|------|-----------|
| HP-01 | 2-step 시나리오 생성 | `add_scenario(steps=[{200,"OK"},{500,"Err"}])` | ID 반환, DB 저장 확인 |
| HP-02 | step 순서대로 반환 | `get_and_advance_step` 연속 2회 | 1회=step[0], 2회=step[1] |
| HP-03 | list_scenarios 전체 조회 | 2개 시나리오 생성 후 list | 길이 2, 필드 확인 |
| HP-04 | scenario_from_flows | flow 2개로 시나리오 생성 | steps[i].response_body == flow_i.response_body |
| HP-05 | reset 후 처음부터 다시 | step 1 → 2 진행 후 reset → step 0 반환 | step[0] 응답 |
| HP-06 | name으로 resolve | `add_scenario(name="x")` → `resolve_scenario_ref("x")` | 동일 ID |
| HP-07 | MCP tool `troxy_scenario_add` | sequence 2스텝 전달 | `{"scenario_id": N}` |
| HP-08 | MCP tool `troxy_scenario_list` | 시나리오 1개 생성 후 list | `[{...current_step:0, total_steps:2...}]` |
| HP-09 | MCP tool `troxy_scenario_reset` | 진행 후 reset 호출 | current_step 0 확인 |
| HP-10 | CLI `scenario add` | `--steps '[{...}]'` | returncode==0, list에 표시 |

---

### 2-B. Loop ON / OFF

| TC-ID | 설명 | 입력 | 기대 결과 |
|-------|------|------|-----------|
| LOOP-01 | loop=False: 마지막 step 반복 (sticky last) | steps=[A,B], loop=False, advance 4회 | 1=A, 2=B, 3=B, 4=B |
| LOOP-02 | loop=True: 처음으로 순환 | steps=[A,B], loop=True, advance 4회 | 1=A, 2=B, 3=A, 4=B |
| LOOP-03 | loop=False 단일 step | steps=[A], loop=False, advance 3회 | 모두 A |
| LOOP-04 | loop=True 단일 step | steps=[A], loop=True, advance 3회 | 모두 A |
| LOOP-05 | loop=True 3-step 순환 | steps=[A,B,C], loop=True, advance 7회 | A,B,C,A,B,C,A |

---

### 2-C. Multi-Step (4+ 스텝)

| TC-ID | 설명 | 입력 | 기대 결과 |
|-------|------|------|-----------|
| MULTI-01 | 4-step [200,500,503,200] | loop=False, advance 5회 | 200,500,503,200,200 |
| MULTI-02 | 4-step loop | loop=True, advance 6회 | 200,500,503,200,200,500 |
| MULTI-03 | step별 response_headers 다름 | 각 step에 다른 Content-Type | 각 호출에서 올바른 헤더 반환 |
| MULTI-04 | step에 label 포함 | `label: "정상"` | 동작에 영향 없음, label 보존됨 |

---

### 2-D. 동시 요청 (원자성)

| TC-ID | 설명 | 방법 | 기대 결과 |
|-------|------|------|-----------|
| ATOM-01 | 동시 advance 중복 없음 | ThreadPoolExecutor 10개 동시 advance | 각 스텝 정확히 1회씩 할당 |
| ATOM-02 | BEGIN IMMEDIATE 직렬화 | 2 thread, 2-step 시나리오 | step[0] + step[1] 각 1번 (순서 임의) |

---

### 2-E. 카운터 리셋

| TC-ID | 설명 | 입력 | 기대 결과 |
|-------|------|------|-----------|
| RESET-01 | 중간 reset | step 1 진행 후 reset | 다음 advance → step[0] |
| RESET-02 | 완전 소진 후 reset | loop=False, 완전 소진 후 reset | 다음 advance → step[0] |
| RESET-03 | reset 후 list | reset 후 list_scenarios | current_step == 0 |
| RESET-04 | ID로 reset | `reset_scenario(id)` | OK |
| RESET-05 | name으로 reset | `reset_scenario(resolve("name"))` | OK |

---

### 2-F. 시나리오 vs mock_rules 우선순위

| TC-ID | 설명 | 기대 결과 |
|-------|------|-----------|
| PRI-01 | 동일 패턴에 scenario + mock_rule | scenario 응답 우선 (addon 레벨 — 아키텍처 ADR-4 확인) |
| PRI-02 | scenario disable → mock_rule fallback | mock_rule 응답 |
| PRI-03 | 두 시나리오 같은 패턴 | 첫 번째 생성 시나리오(낮은 ID) 우선 |

> **Note**: 우선순위 테스트(PRI-*)는 addon.py 통합 단계에서 검증. unit 테스트는 scenarios.py 레이어만 검증.

---

## 3. 엣지 케이스

| TC-ID | 설명 | 입력 | 기대 결과 |
|-------|------|------|-----------|
| EDGE-01 | 빈 steps 리스트 | `add_scenario(steps=[])` | `ValueError` raise |
| EDGE-02 | steps=None | `add_scenario(steps=None)` | `TypeError` / `ValueError` |
| EDGE-03 | 단일 step (loop=False) | advance 3회 | 모두 step[0] |
| EDGE-04 | count=0 edge (current_step 직접 조작) | DB에서 current_step=-1로 설정 후 advance | 안전한 처리 (clamp to 0 또는 ValueError) |
| EDGE-05 | 매칭 도메인 없음 | `get_and_advance_step`에 없는 ID | `None` 반환 |
| EDGE-06 | 비활성 시나리오 advance | `toggle_scenario(enabled=False)` 후 advance | `None` 반환 |
| EDGE-07 | 중복 name | `add_scenario(name="x")` 2회 | `ValueError` raise |
| EDGE-08 | steps 항목에 status_code 없음 | `[{"response_body": "ok"}]` | `ValueError` raise or default 200 (구현 합의 필요) |
| EDGE-09 | DB 없는 상태에서 advance | uninitialized DB | 예외 전파 (init_db 전제) |
| EDGE-10 | name=None 시 resolve_scenario_ref | int ID만 사용 가능 | ID 기반 조회 동작 |

---

## 4. 기존 회귀 테스트

신규 코드가 기존 기능을 깨지 않음을 보장하는 항목:

| TC-ID | 설명 | 방법 |
|-------|------|------|
| REG-01 | 기존 mock_rules CRUD 전체 통과 | `pytest tests/unit/test_mock.py` |
| REG-02 | 기존 E2E mock CLI 전체 통과 | `pytest tests/e2e/test_cli_mock.py` |
| REG-03 | 기존 MCP handler 전체 통과 | `pytest tests/e2e/test_mcp.py` |
| REG-04 | form-urlencoded 파서 전체 통과 | `pytest tests/unit/test_formats.py` |
| REG-05 | store 전체 통과 | `pytest tests/unit/test_store.py` |
| REG-06 | DB init_db가 mock_scenarios 테이블 포함해 생성 | `init_db` 후 `PRAGMA table_info` 확인 |
| REG-07 | 기존 DB(v1)에 init_db 재실행 시 에러 없음 | 기존 rows 유지, 신규 테이블 추가 |

---

## 5. 테스트 코드 구조

### 5-A. `tests/unit/test_scenarios.py`

```python
"""tests for core/scenarios.py — CRUD + step advance logic."""

# fixtures: tmp_db (from conftest)
# imports: add_scenario, list_scenarios, remove_scenario, toggle_scenario,
#          reset_scenario, resolve_scenario_ref, scenario_from_flows, get_and_advance_step

# 검증 방식:
# - DB 직접 조회 (sqlite3)로 내부 상태 검증
# - get_and_advance_step 반환값으로 step 응답 검증
# - concurrent 테스트: threading.ThreadPoolExecutor
```

**테스트 함수 목록**:
```
test_add_scenario_returns_id
test_add_scenario_name_conflict_raises
test_add_scenario_empty_steps_raises
test_list_scenarios_all
test_list_scenarios_enabled_only
test_remove_scenario
test_toggle_scenario_disable_enable
test_reset_scenario_rewinds_to_zero
test_resolve_scenario_ref_by_id
test_resolve_scenario_ref_by_name
test_resolve_scenario_ref_not_found_raises
test_get_and_advance_step_two_step_sequence
test_get_and_advance_step_loop_false_sticky_last
test_get_and_advance_step_loop_true_cycles
test_get_and_advance_step_disabled_returns_none
test_get_and_advance_step_missing_scenario_returns_none
test_get_and_advance_step_single_step_always_returns_same
test_get_and_advance_step_concurrent_no_duplicates  (ThreadPoolExecutor)
test_scenario_from_flows_creates_steps_in_order
test_scenario_from_flows_missing_flow_raises
test_reset_scenario_after_exhaustion
test_db_has_mock_scenarios_table_after_init
test_existing_db_migration_adds_table_without_error
```

---

### 5-B. `tests/e2e/test_scenarios_cli.py`

```python
"""E2E tests for 'troxy scenario' CLI subcommands."""

# _run_troxy helper (같은 패턴 — test_cli_mock.py 참고)

# 검증 방식: subprocess + --json 출력 파싱
```

**테스트 함수 목록**:
```
test_scenario_add_and_list
test_scenario_remove
test_scenario_disable_enable
test_scenario_reset_via_cli
test_scenario_from_flows_cli
test_scenario_list_shows_current_step
test_scenario_add_loop_flag
test_scenario_add_invalid_steps_errors
```

---

### 5-C. `tests/e2e/test_mcp.py` 보강 (기존 파일 하단 추가)

**추가할 테스트 함수**:
```
test_handle_scenario_add_returns_id
test_handle_scenario_add_two_step
test_handle_scenario_list_shows_current_step
test_handle_scenario_reset
test_handle_scenario_remove
test_handle_scenario_toggle
test_handle_scenario_from_flows
test_handle_scenario_advance_sequence_via_get_and_advance  (MCP 레이어 아닌 core 직접)
```

---

## 6. 구현 가정 (Engineer와 합의 필요)

다음 사항은 engineer 구현에 따라 테스트 코드가 달라질 수 있습니다:

| # | 항목 | 현재 가정 |
|---|------|-----------|
| 1 | `steps=[]` 처리 | `ValueError` raise |
| 2 | step에 `status_code` 없을 때 | `ValueError` raise (기본 200 부여 여부 논의 필요) |
| 3 | `scenario_from_flows` 없는 flow ID | `ValueError` raise |
| 4 | `get_and_advance_step` 비활성 시나리오 | `None` 반환 |
| 5 | 동시 advance 직렬화 방식 | `BEGIN IMMEDIATE` transaction (ADR-2 기준) |
| 6 | MCP tool 이름 | `troxy_scenario_*` (ADR-3/5 기준) |
| 7 | CLI 커맨드명 | `troxy scenario *` |
| 8 | `list_scenarios` 응답 필드 | `current_step`, `total_steps`, `loop`, `name`, `domain`, `path_pattern` 포함 |

---

## 7. 완료 기준 (Definition of Done)

- [ ] `uv run python -m pytest` 전체 통과 (신규 + 기존 회귀)
- [ ] `test_scenarios.py`: 모든 happy path + loop + atomic 테스트 통과
- [ ] `test_scenarios_cli.py`: 모든 CLI 시나리오 명령 E2E 통과
- [ ] `test_mcp.py`: 시나리오 MCP tool handler 추가 테스트 통과
- [ ] `uv run python scripts/lint_layers.py` 위반 0건
- [ ] 기존 107개 테스트 회귀 없음
