# Scripted Mock (시나리오 목 규칙)

## 배경

현재 troxy의 목 시스템은 단일 규칙(single static rule) 단위다. AI에게 복잡한 mock 시나리오를 만들어달라고 하면:
- 규칙 1개당 MCP 호출 1회 이상 필요
- "첫 번째 요청은 200, 두 번째는 401, 세 번째는 다시 200" 같은 시퀀스를 표현하는 방법이 없음
- 시나리오 전체를 구성하려면 10회 이상 MCP 호출이 필요한 경우가 많음

**사용자의 핵심 불만**: "목 데이터 만드는 과정이 어려움. AI에게 시키니 MCP 호출이 많고 오래 걸림."

**두 가지 해결 방향**:
1. **단순화**: 1번 MCP 호출로 body/header 등을 한 번에 세팅
2. **시퀀스**: refresh #1=정상 → #2=에러 → #3=다른에러 → #4=정상 같은 순서형 시나리오

두 가지 모두 MVP에 포함한다.

---

## 사용자 스토리

### US-1. 결제 실패 retry 시나리오 (iOS 앱)

> iOS 결제 화면에서 "결제 실패 → 재시도 → 성공" 플로우를 테스트하고 싶다.
> 매번 서버를 통하지 않고, 항상 재현 가능한 시나리오가 필요하다.

**As** an iOS developer  
**I want** `POST /v1/payments` 첫 호출은 500, 두 번째는 200 응답을 돌려주는 목 규칙을  
**So that** 재시도 로직이 제대로 작동하는지 자동화 테스트 없이 수동으로 검증할 수 있다.

```
AI에게: "결제 API를 1회는 500, 2회는 200으로 Mock 해줘"
기대: troxy_mock_add 1번 호출로 완료
```

---

### US-2. 401 → 토큰 갱신 → 재요청 시나리오

> 액세스 토큰 만료 → 리프레시 → 원래 API 재요청까지의 전체 흐름을 테스트하고 싶다.

**As** an iOS developer  
**I want** `GET /api/me` 첫 호출은 401, 두 번째는 200을 반환하는 시퀀스를  
**So that** 토큰 만료 처리 코드(자동 갱신 로직)가 올바르게 동작하는지 확인할 수 있다.

```
AI에게: "GET /api/me를 401 먼저 내보내고, 그 다음부터 200 반환해줘"
기대: troxy_mock_add 1번 호출로 완료
```

---

### US-3. 페이지네이션 빈 목록 엣지케이스

> "3페이지까지는 데이터 있고, 4페이지는 빈 배열" 시나리오를 고정하고 싶다.

**As** an iOS developer  
**I want** `GET /api/posts?page=N` 3번은 데이터 있는 응답, 그 이후는 빈 배열 응답을 반환하도록  
**So that** 무한스크롤 "더 이상 없음" 처리가 잘 되는지 확인할 수 있다.

```
AI에게: "포스트 목록 3번까지는 데이터 있는 Mock, 그다음은 빈 목록으로"
기대: troxy_mock_add 1번 호출로 완료
```

---

### US-4. 단순 body/header 즉시 Mock

> 현재 mock_add는 body, headers, status_code를 파라미터로 받지만 한 번에 body와 헤더를 세팅하는 게 번거롭다.

**As** an AI agent  
**I want** 단 1번의 `troxy_mock_add` 호출로 도메인·경로·메서드·상태코드·헤더·바디를 모두 설정  
**So that** 여러 번 호출하지 않고도 완전한 Mock을 만들 수 있다.

```
AI에게: "GET /api/user를 200, {"name":"testuser"} 바디로 Mock 해줘"
기대: troxy_mock_add 1번 호출, 완료
```

---

### US-5. 시나리오 리셋

> 테스트가 끝난 뒤, 같은 시나리오를 처음부터 다시 돌리고 싶다.

**As** an iOS developer  
**I want** 시퀀스 Mock의 진행 상태를 초기화하는 명령  
**So that** 같은 시나리오를 여러 번 반복 실행할 수 있다.

```
troxy_mock_reset --name "payment-retry"
```

---

## Acceptance Criteria

### AC-1. 단순 Mock (단일 응답) — must

**Given** AI가 특정 API의 고정 응답 Mock을 요청할 때  
**When** `troxy_mock_add`를 body·headers·status_code 포함해 1번 호출하면  
**Then** 이후 해당 경로로 오는 모든 요청이 지정된 응답을 반환한다

---

### AC-2. 시퀀스 Mock — must

**Given** 사용자가 "1번째=A, 2번째=B, 3번째 이후=C" 시나리오를 원할 때  
**When** `troxy_mock_add`를 `sequence` 파라미터로 1번 호출하면  
**Then**  
- 첫 번째 매칭 요청 → sequence[0] 응답  
- 두 번째 매칭 요청 → sequence[1] 응답  
- 마지막 항목 이후 요청 → 마지막 항목을 계속 반환 (sticky last)

---

### AC-3. 1 MCP 호출 제약 — must

**Given** AI가 시나리오 Mock 생성을 위임받았을 때  
**When** `troxy_mock_add` 1번 호출로 시나리오 전체(시퀀스 포함)를 표현할 수 있어야 하고  
**Then** 추가 MCP 호출 없이 동작 가능해야 한다

---

### AC-4. 기존 mock_rules 호환 — must

**Given** 기존에 `add_mock_rule`로 생성된 단순 Mock 규칙이 있을 때  
**When** 새 시퀀스 기능을 도입해도  
**Then** 기존 규칙 동작에 변화가 없어야 한다 (하위 호환)

---

### AC-5. 시나리오 초기화 — should

**Given** 시퀀스 Mock이 일부 진행된 상태일 때  
**When** `troxy_mock_reset`을 호출하면  
**Then** 해당 규칙의 시퀀스 인덱스가 0으로 리셋된다

---

### AC-6. Mock 이름 참조 — should

**Given** Mock 규칙에 `--name` 을 부여했을 때  
**When** reset·toggle·remove 등을 호출하면  
**Then** ID 대신 이름으로 참조 가능하다 (기존 `resolve_mock_ref` 활용)

---

## MVP 컷

### Must (MVP)

| 항목 | 설명 |
|------|------|
| 단순 Mock 1-call 완성 | body·headers·status_code 한 번에 세팅 (현재도 가능하지만 MCP 스키마·문서 명확화) |
| **시퀀스 Mock** | `sequence: [{status, headers, body}, ...]` 파라미터 추가. sticky last 동작 |
| 시퀀스 상태 저장 | DB에 현재 인덱스(cursor) 저장. 재시작 후에도 상태 유지 |
| `troxy_mock_add` 확장 | `sequence` 파라미터 추가, 기존 단순 파라미터 유지 |
| 1 MCP 호출 보장 | 시나리오 전체를 단 1회 `troxy_mock_add`로 표현 가능 |
| 기존 호환 | `sequence` 없으면 기존 단일 응답 동작 그대로 |

### Should (다음 버전)

| 항목 | 설명 |
|------|------|
| `troxy_mock_reset` | 이름/ID로 시퀀스 커서 초기화 |
| `troxy_mock_clone` | 기존 규칙을 기반으로 복제 |
| 조건부 분기 | 요청 body 내용에 따라 다른 응답 (scripted lambda) |

### Could (장기)

| 항목 | 설명 |
|------|------|
| 확률 기반 응답 | 30% 확률로 500 반환 |
| 지연(delay) 주입 | 응답 지연 시간 설정 |
| 시나리오 그룹 | 여러 규칙을 하나의 시나리오로 묶고 일괄 on/off |
| YAML/JSON 파일 import | 파일로 복잡한 시나리오 정의 (MCP tool에서 파일 경로 전달은 보안상 비목표. CLI `--from-json` 은 로컬 파일로 허용) |

---

## 명령 와이어프레임

> **Note**: 자세한 파라미터 syntax 및 DX 설계는 designer 담당.
> 여기서는 의도와 예시 위주로 기술한다.

### 단순 Mock (현행 유지, 문서 명확화)

```
AI 요청: "GET /api/me를 200, JSON 바디로 Mock 해줘"

troxy_mock_add(
  domain="api.example.com",
  path_pattern="/api/me",
  method="GET",
  status_code=200,
  headers='{"Content-Type": "application/json"}',
  body='{"id": 1, "name": "testuser"}'
)
# → rule id 반환, 완료
```

### 시퀀스 Mock (신규)

```
AI 요청: "결제 API 첫 호출은 500, 두 번째부터 200으로"

troxy_mock_add(
  domain="api.example.com",
  path_pattern="/v1/payments",
  method="POST",
  sequence=[
    {"status_code": 500, "body": '{"error": "payment_failed"}'},
    {"status_code": 200, "body": '{"ok": true, "order_id": "ORD-001"}'},
  ]
)
# → rule id 반환, 완료
# 이후: 1번 요청 → 500, 2번~이후 요청 → 200 (sticky last)
```

```
AI 요청: "인증 API 401→200 시나리오"

troxy_mock_add(
  domain="api.example.com",
  path_pattern="/api/me",
  method="GET",
  name="auth-retry",
  sequence=[
    {"status_code": 401, "body": '{"error": "unauthorized"}'},
    {"status_code": 200, "body": '{"id": 1, "name": "testuser"}'},
  ]
)
```

### 시퀀스 초기화 (should)

```
troxy_mock_reset(name="auth-retry")
# → 시퀀스 커서 0으로 리셋
```

### CLI 대응 예시 (의도)

```bash
# 인라인 시퀀스 (troxy scenario 서브그룹)
troxy scenario add -d api.example.com -p /v1/payments -m POST \
  -s "500,200" --name pay-retry

# 복잡한 body는 JSON 파일로
troxy scenario add --from-json pay-scenario.json

# 시퀀스 초기화
troxy scenario reset auth-retry
# 또는
troxy mock reset auth-retry
```

---

## 비기능 요구사항

| 항목 | 요구 |
|------|------|
| **1 MCP 호출** | AI가 시나리오 Mock 전체를 `troxy_mock_add` 1번으로 완성 가능 |
| **하위 호환** | `sequence` 파라미터 없을 때 기존 단일 Mock 동작 100% 유지 |
| **상태 영속성** | 시퀀스 커서는 DB에 저장. mitmproxy/troxy 재시작 후에도 유지 |
| **레이어 준수** | `core/`에 시퀀스 로직 구현. `addon.py`만 mitmproxy import |
| **atomic 매칭** | 시퀀스 커서 증가는 요청 처리와 atomic하게 (동시 요청 시 중복 카운트 방지) |
| **파일 크기 제한** | `check_file_size.py` 통과 유지 |

---

## 아키텍처 영향

### DB 스키마 변경

```sql
-- mock_rules 테이블에 추가
ALTER TABLE mock_rules ADD COLUMN sequence_json TEXT;       -- JSON array of {status_code, headers, body}
ALTER TABLE mock_rules ADD COLUMN sequence_index INTEGER DEFAULT 0; -- 현재 커서
```

단순 Mock: `sequence_json = NULL`, 기존 컬럼 그대로 사용.  
시퀀스 Mock: `sequence_json = '[{...}, {...}]'`, `response_*` 컬럼은 무시.

### 파일별 변경 범위 (참고용)

| 파일 | 변경 |
|------|------|
| `core/mock.py` | `add_mock_rule`에 `sequence` 파라미터 추가, `get_next_mock_response(rule_id)` 신규 |
| `core/db.py` or migration | `mock_rules` 스키마 migration |
| `core/tool_catalog.py` | `troxy_mock_add` 스키마에 `sequence` 파라미터 추가, `troxy_mock_reset`/`troxy_mock_update` 신규 스키마 |
| `mcp/server.py` | 신규 MCP 도구(`troxy_mock_reset`, `troxy_mock_update`) 핸들러 추가 |
| `addon.py` | `mock_from_rule` 로직에서 시퀀스 분기 처리 |
| `cli/scenario_cmds.py` | **신규** — `troxy scenario` 서브그룹 (add, list, status, reset, remove, from-flows) |
| `cli/main.py` | `scenario_group` 등록 |

> 자세한 구현 설계는 engineer 담당.

---

## 미결 사항 — designer DX 스펙(`2026-04-27-scripted-mock-dx.md`)에서 결정됨

| # | 질문 | 결정 |
|---|------|------|
| 1 | 파라미터 이름 | **`sequence`** (MCP), CLI 인라인 `-s` 플래그 |
| 2 | sticky last 기본값 | `loop=false` → 마지막 step 무한 반복 (sticky last) |
| 3 | 단순 Mock + sequence 동시 전달 | `sequence` 우선, status_code/body/headers 무시 + 경고 문자열 반환 (에러 아님) |
| 4 | CLI 명령어 그룹 | `troxy scenario` 서브그룹 신설. reset은 `troxy scenario reset` / `troxy mock reset` 둘 다 허용 |
| 5 | 시퀀스 아이템 필수 필드 | `status_code`만 필수, `headers`/`body` optional |

**잔여 open questions (DX 스펙 §9)**:

- **Q1**: `troxy scenario from-flows` — flow 선택 기준: 최근 N개(삽입 순서) ✅ PM 확인 (아래)
- **Q2**: `troxy_mock_update` name 필드 수정 가능 여부 → ✅ 허용
- **Q3**: `troxy_mock_list` response_body 100자 초과 시 truncate → ✅ 유지
- **Q4**: 시나리오 rule도 `troxy_mock_toggle` 으로 on/off → ✅ 허용 (기존 동작 그대로)
