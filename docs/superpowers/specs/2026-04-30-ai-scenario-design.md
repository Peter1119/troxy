# AI 자연어 시나리오 설계 spec

**작성일**: 2026-04-30
**작성자**: worker-ai-designer (troxy-issues 팀)
**리뷰어**: team-lead → 사용자(CEO) 승인 필요
**참조 이슈**: https://github.com/Peter1119/troxy/issues/6
**참조 문서**:
- `2026-04-27-scripted-mock-dx.md` (기존 scripted mock 설계)
- `src/troxy/core/scenarios.py` (현재 시나리오 구현)
- `src/troxy/core/tool_catalog.py` (MCP 도구 카탈로그)

---

## 1. 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **troxy는 LLM을 호출하지 않는다** | LLM 호출은 호출자(Claude in MCP) 몫. troxy는 도구 설명·템플릿·검증만 제공 |
| **스키마 변경 없음** | `mock_scenarios` 테이블은 현재 구조 그대로 사용 |
| **기존 1-call rule 계승** | `troxy_mock_add(sequence=[...])` 1호출로 시나리오 생성 완료 |
| **에러 템플릿 first** | LLM이 brief 해석 전에 템플릿 카탈로그를 참조하도록 유도 |
| **조기 실패** | AI가 생성한 body가 잘못됐을 때 명확한 에러 반환, LLM이 자가 수정 가능 |

---

## 2. 컴포넌트 구성

```
이슈 #6 제안 4개 컴포넌트:

A. troxy_mock_error_templates   ← 읽기 전용 카탈로그 (MUST)
B. troxy_mock_from_scenario_brief ← LLM 가이드 도구 (MUST)
C. troxy_mock_add body 검증 강화 ← 방어 레이어 (MUST)
D. CLI troxy scenario from-brief ← 편의 CLI (SHOULD)
```

---

## 3. A — `troxy_mock_error_templates`

### 3-1. 역할
흔히 쓰는 HTTP 에러 응답 템플릿을 정적 카탈로그로 제공. LLM이 brief를 sequence로 변환할 때 이 카탈로그를 먼저 참조해 body/headers를 구성한다.

### 3-2. 입력/출력
- **입력**: 없음 (파라미터 불필요)
- **출력**: 템플릿 배열 JSON

```json
[
  {
    "key": "unauthorized",
    "status_code": 401,
    "description": "인증 실패 — 토큰 없음, 만료, 잘못된 형식 (401 Unauthorized)",
    "body_template": "{\"error\": \"unauthorized\", \"message\": \"{message}\"}",
    "suggested_headers": {"Content-Type": "application/json", "WWW-Authenticate": "Bearer realm=\"api\""},
    "slots": ["message"]
  },
  {
    "key": "forbidden",
    "status_code": 403,
    "description": "권한 부족 — 인증은 됐으나 접근 거부 (403 Forbidden)",
    "body_template": "{\"error\": \"forbidden\", \"message\": \"{message}\"}",
    "suggested_headers": {"Content-Type": "application/json"},
    "slots": ["message"]
  },
  {
    "key": "not_found",
    "status_code": 404,
    "description": "리소스 없음 (404 Not Found)",
    "body_template": "{\"error\": \"not_found\", \"message\": \"{message}\"}",
    "suggested_headers": {"Content-Type": "application/json"},
    "slots": ["message"]
  },
  {
    "key": "validation_failed",
    "status_code": 422,
    "description": "요청 본문 유효성 실패 — 필드 오류, 타입 불일치 (422 Unprocessable Entity)",
    "body_template": "{\"error\": \"validation_failed\", \"fields\": [{\"field\": \"{field}\", \"message\": \"{message}\"}]}",
    "suggested_headers": {"Content-Type": "application/json"},
    "slots": ["field", "message"]
  },
  {
    "key": "rate_limited",
    "status_code": 429,
    "description": "요청 빈도 초과 (429 Too Many Requests)",
    "body_template": "{\"error\": \"rate_limited\", \"message\": \"Too many requests. Retry after {retry_after}s.\", \"retry_after\": {retry_after}}",
    "suggested_headers": {"Content-Type": "application/json", "Retry-After": "{retry_after}"},
    "slots": ["retry_after"]
  },
  {
    "key": "internal_error",
    "status_code": 500,
    "description": "서버 내부 오류 (500 Internal Server Error)",
    "body_template": "{\"error\": \"internal_error\", \"message\": \"{message}\"}",
    "suggested_headers": {"Content-Type": "application/json"},
    "slots": ["message"]
  },
  {
    "key": "service_unavailable",
    "status_code": 503,
    "description": "서버 점검/과부하 (503 Service Unavailable)",
    "body_template": "{\"error\": \"service_unavailable\", \"message\": \"{message}\"}",
    "suggested_headers": {"Content-Type": "application/json", "Retry-After": "60"},
    "slots": ["message"]
  },
  {
    "key": "conflict",
    "status_code": 409,
    "description": "중복 리소스, 낙관적 잠금 충돌 (409 Conflict)",
    "body_template": "{\"error\": \"conflict\", \"message\": \"{message}\"}",
    "suggested_headers": {"Content-Type": "application/json"},
    "slots": ["message"]
  }
]
```

### 3-3. 슬롯 형식
`{변수명}` — Python format string 스타일. LLM이 슬롯 자리에 실제 값을 채운 뒤 `troxy_mock_add`에 전달한다.

### 3-4. 구현 위치
- `src/troxy/core/error_templates.py` — 신규 파일, 정적 데이터만 (`ERROR_TEMPLATES: list[dict]`)
- `src/troxy/core/tool_catalog.py` — 새 도구 스키마 추가
- `src/troxy/mcp/mock_handlers.py` — `handle_error_templates()` 핸들러 추가

---

## 4. B — `troxy_mock_from_scenario_brief`

### 4-1. 설계 철학
이 도구는 **LLM을 guide하는 meta-tool**이다. troxy가 자연어를 직접 파싱하지 않는다. 대신:
1. 도구 description이 충분히 자세해서 LLM이 brief를 어떻게 sequence로 변환할지 이해한다
2. 도구 호출 시 troxy는 available templates + 기존 매칭 도메인/path 규칙 목록을 반환한다
3. LLM이 이 컨텍스트를 바탕으로 `troxy_mock_add(sequence=[...])` 를 직접 호출한다

```
[MCP 호출 흐름]
사용자 → Claude: "결제 API: 1회 성공, 2-3회 401, 4회 500 만들어줘"
Claude → troxy: troxy_mock_error_templates()
troxy → Claude: [unauthorized 템플릿, internal_error 템플릿, ...]
Claude (internally): brief 해석 → 4-step sequence 구성
Claude → troxy: troxy_mock_add(domain="...", sequence=[{200,...},{401,...},{401,...},{500,...}])
troxy → Claude: {"rule_id": 42, "type": "scenario"}
Claude → 사용자: "완료. mock id=42, 4단계 시나리오 활성화됨."
```

### 4-2. `troxy_mock_from_scenario_brief` 입력 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `domain` | string | 선택 | 도메인 필터 |
| `path_pattern` | string | 선택 | 경로 glob |
| `method` | string | 선택 | HTTP 메서드 |
| `brief` | string | **필수** | 자연어 시나리오 설명 |
| `name` | string | 선택 | 시나리오 명칭 |

### 4-3. 반환값
```json
{
  "brief": "1회 성공, 2-3회 401, 4회 500",
  "available_templates": ["unauthorized", "internal_error", "..."],
  "instruction": "troxy_mock_error_templates 결과에서 원하는 템플릿을 선택해 슬롯을 채운 뒤, troxy_mock_add(sequence=[...])를 호출하세요. loop=false이면 마지막 step이 반복됩니다.",
  "example_sequence": [
    {"status_code": 200, "body": "{\"result\": \"ok\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
    {"status_code": 401, "body": "{\"error\": \"unauthorized\", \"message\": \"Token expired\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
    {"status_code": 401, "body": "{\"error\": \"unauthorized\", \"message\": \"Token expired\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
    {"status_code": 500, "body": "{\"error\": \"internal_error\", \"message\": \"Unexpected error\"}", "headers": "{\"Content-Type\": \"application/json\"}"}
  ],
  "context": {"domain": "api.example.com", "path_pattern": "/pay", "method": "POST", "name": null}
}
```

**핵심**: `example_sequence`는 **참고용**. LLM이 brief를 해석해서 실제 sequence를 구성한 후 `troxy_mock_add`를 호출한다.

### 4-4. MCP tool description (draft)

```
이 도구를 먼저 호출해 brief 컨텍스트를 받고, 그 다음 troxy_mock_add(sequence=[...])를 호출하세요.

사용 시나리오 (한국어): "1회는 200 성공, 2~3회는 401 토큰만료, 4회부터는 500"
Usage scenario (English): "1st: 200 OK, 2nd-3rd: 401 expired token, 4th onwards: 500"

워크플로:
1. troxy_mock_from_scenario_brief(brief="...") 호출 → 이 도구가 example_sequence 반환
2. troxy_mock_error_templates() 호출 → body/headers 템플릿 참조
3. brief 해석 → step별 status_code, body, headers 결정
4. troxy_mock_add(sequence=[{step1}, {step2}, ...], loop=false) 호출

loop=false (기본): 마지막 step 무한 반복
loop=true: 첫 step으로 순환
```

### 4-5. 구현 위치
- `src/troxy/core/tool_catalog.py` — `troxy_mock_from_scenario_brief` 스키마 추가
- `src/troxy/mcp/mock_handlers.py` — `handle_mock_from_scenario_brief()` 핸들러

---

## 5. C — `troxy_mock_add` body 검증 강화

### 5-1. 목적
AI가 생성한 step body/headers에 JSON 문법 오류가 있을 때 즉시 명확한 에러를 반환해 LLM 자가 수정(self-correction)을 유도한다.

### 5-2. 검증 규칙

| 규칙 | 동작 |
|------|------|
| `body`가 `{`/`[`로 시작하는데 JSON 파싱 실패 | 에러 반환: `"step N body is not valid JSON: <파싱 오류>"` |
| `headers`가 문자열인데 JSON 파싱 실패 | 에러 반환: `"step N headers is not valid JSON: <파싱 오류>"` |
| `status_code` 누락 | 기존 `_validate_steps()` 처리 유지 |
| 슬롯 미채움 — `body`/`headers`에 `{변수명}` 패턴 잔류 | **경고 반환** (저장 차단 X) — `warnings: ["step N body contains unfilled slot: {message}"]` |
| body content-type 일치 여부 | **검증 안 함** (결정 확정: YAGNI) |

### 5-3. 슬롯 감지 정규식
```python
import re
_UNFILLED_SLOT = re.compile(r'\{[A-Za-z_][A-Za-z0-9_]*\}')
```
`body`와 `headers` 값(JSON 직렬화 후)에 대해 매칭. `{` 만으로 된 JSON 객체 자체는 이미 step 5-2의 JSON 파싱 단계를 통과한 이후라 슬롯 감지와 충돌하지 않는다.

### 5-4. 에러/경고 반환 형식
```json
{
  "rule_id": 42,
  "type": "scenario",
  "warnings": [
    "step 1 body contains unfilled slot: {message}",
    "step 2 headers contains unfilled slot: {retry_after}"
  ]
}
```
경고가 없으면 `warnings` 키 미포함. 에러(JSON 파싱 실패)는 `rule_id` 없이 `{"error": "validation", "detail": "..."}` 반환.

### 5-5. 구현 위치
- `src/troxy/mcp/mock_handlers.py` — `handle_mock_add()` 내에서 sequence steps 검증

---

## 6. D — CLI `troxy scenario from-brief`

### 6-1. 역할
MCP(Claude) 없이 CLI만 쓰는 사용자를 위한 편의 명령. LLM을 직접 호출하지 않으며, 입력 brief를 기반으로 sequence JSON 스캐폴드를 출력한다.

### 6-2. 동작 모드

```bash
# 기본: dry-run 출력만
troxy scenario from-brief \
  --domain api.example.com \
  --path /pay \
  --method POST \
  --brief "1회 200, 2-3회 401 토큰만료, 4회 500"
```

**출력 예시**:
```
Brief: "1회 200, 2-3회 401 토큰만료, 4회 500"
─────────────────────────────────────────────────────
다음 JSON을 troxy_mock_add에 전달하거나 --execute 플래그로 즉시 생성하세요:

[
  {"status_code": 200, "body": "{\"result\": \"ok\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
  {"status_code": 401, "body": "{\"error\": \"unauthorized\", \"message\": \"Token expired\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
  {"status_code": 401, "body": "{\"error\": \"unauthorized\", \"message\": \"Token expired\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
  {"status_code": 500, "body": "{\"error\": \"internal_error\", \"message\": \"Unexpected error\"}", "headers": "{\"Content-Type\": \"application/json\"}"}
]
```

**결정 확정**: LLM 호출 없음. 휴리스틱 파싱만 사용.

### 6-3. Brief 파싱 — 간단 휴리스틱 (LLM 없이)

CLI dry-run에 한해 간단한 규칙 기반 파싱:

1. `"N회"` / `"Nth"` → 해당 step 인덱스 추출
2. `"N-M회"` → 해당 범위를 같은 step으로 반복
3. status code 숫자(200, 401, 500 등) → 직접 매핑
4. 에러 키워드("토큰만료", "unauthorized", "rate limit" 등) → 템플릿 key로 매핑

**결정 확정**: `--json` 플래그 추가.

### 6-4. `--json` 플래그 (결정 확정: 추가)

```bash
troxy scenario from-brief \
  --domain api.example.com --path /pay --method POST \
  --brief "1회 200, 2-3회 401, 4회 500" \
  --json
```

**출력**: pretty-printed JSON 배열만 stdout 출력. 파이프·스크립팅 용도.

```json
[
  {"status_code": 200, "body": "{\"result\": \"ok\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
  ...
]
```

### 6-5. `--execute` 플래그

```bash
troxy scenario from-brief ... --execute --name "payment-retry"
# → 내부적으로 troxy scenario add (core API 직접 호출) 실행
```

### 6-6. 구현 위치
- `src/troxy/cli/scenario_cmds.py` — `from-brief` 서브커맨드 추가
- `src/troxy/core/error_templates.py` — 공유 카탈로그에서 CLI도 참조
- `src/troxy/core/scenario_brief_parser.py` — 공통 휴리스틱 파서 (MCP + CLI 공유, 7-A 참조)

---

## 7-A. 공유 휴리스틱 파서 — `scenario_brief_parser.py`

### 역할
`troxy_mock_from_scenario_brief` (MCP)와 CLI `from-brief` 양쪽에서 `example_sequence`를 생성하는 로직을 한 곳에 모아 중복을 제거한다.

### 모듈 위치
`src/troxy/core/scenario_brief_parser.py` — `core` 레이어이므로 `mitmproxy` 미사용. CLI/MCP 양쪽에서 import 가능.

### 공개 인터페이스
```python
def parse_brief(
    brief: str,
    templates: list[dict],   # ERROR_TEMPLATES 주입
) -> list[dict]:
    """
    자연어 brief를 sequence step 배열로 변환.
    반환: [{"status_code": N, "body": "...", "headers": "..."}, ...]

    파싱 불가 구간은 {"status_code": 200, "body": "TODO: fill body"} 형태로 placeholder 삽입.
    """
```

### 파싱 규칙 (휴리스틱)
1. `"N회"` / `"Nth"` / `"N번"` → step index
2. `"N-M회"` / `"N~M회"` → index N~M 동일 step 반복
3. `"N회부터"` / `"N 이후"` → index N~끝 모두 동일 step (loop=false이면 마지막 step 고정)
4. HTTP status code 숫자 → 직접 매핑
5. 에러 키워드 매핑 (한국어 + 영어 모두 지원):

   | 키워드 | 매핑 key |
   |--------|----------|
   | `토큰만료`, `token expired`, `unauthorized`, `인증` | `unauthorized` |
   | `권한`, `forbidden`, `접근 거부` | `forbidden` |
   | `rate limit`, `속도 제한`, `too many` | `rate_limited` |
   | `서버 오류`, `internal error`, `500` | `internal_error` |
   | `점검`, `unavailable`, `503` | `service_unavailable` |
   | `중복`, `conflict`, `409` | `conflict` |
   | `없음`, `not found`, `404` | `not_found` |
   | `유효성`, `validation`, `422` | `validation_failed` |

6. 매핑 후 템플릿 슬롯에 적절한 기본값 자동 채움 (예: `{message}` → `"Unauthorized"`)

### 의존성
- `src/troxy/core/error_templates.py` (주입 또는 직접 import)
- 표준 라이브러리만 사용 (re, json)

---

## 7-B. 언어 정책 (결정 확정)

| 위치 | 언어 | 근거 |
|------|------|------|
| MCP tool `description` 필드 | **한국어** | troxy CLI 톤 일관성 |
| MCP tool `description` 예시 | **한국어 + 영어 병기** | 다국어 LLM 호환 |
| error template `description` | **한국어** | troxy 내부 카탈로그 |
| error template `body_template` 의 메시지 값 | **영어** | API 응답 관행 (JSON body는 영문) |
| CLI 출력 텍스트 | **한국어** | 기존 troxy CLI 톤 유지 |
| 슬롯 경고 메시지 (`warnings[]`) | **영어** | MCP JSON 응답, LLM 가독성 |

---

## 8. DB 스키마 변경

**없음.** `mock_scenarios` 테이블 현재 구조:

```sql
CREATE TABLE IF NOT EXISTS mock_scenarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    domain       TEXT,
    path_pattern TEXT,
    method       TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    current_step INTEGER NOT NULL DEFAULT 0,
    steps        TEXT    NOT NULL,  -- JSON array
    loop         INTEGER NOT NULL DEFAULT 0,
    created_at   REAL    NOT NULL
);
```

`steps` JSON 형식도 그대로 `[{"status_code": N, "response_body": "...", "response_headers": {...}}, ...]`.

---

## 8. 동시성 / 카운터 정책

### 8-1. 동시 요청
기존 `get_and_advance_step()` — `BEGIN IMMEDIATE` 트랜잭션으로 이미 concurrency-safe. **변경 없음.**

### 8-2. 카운터 reset 정책

| 상황 | 동작 |
|------|------|
| troxy 프로세스 재시작 | `current_step` **유지** (DB에 영속화됨) |
| 명시적 reset 명령 | `troxy_mock_reset` / `troxy scenario reset <id>` |
| 시나리오 sequence 교체 (`troxy_mock_update`) | `current_step → 0` 자동 reset (기존 동작 유지) |

**결정 확정**: 재시작 auto-reset 없음. 명시적 `troxy_mock_reset` / `troxy scenario reset` 만 제공.

---

## 9. 에러 처리 총괄

| 실패 케이스 | 현재 처리 | spec 변경 |
|-------------|-----------|-----------|
| `troxy_mock_add` sequence steps body JSON 오류 | 그냥 저장됨 | validation 에러 반환 |
| brief 해석 실패 (LLM 측) | N/A | LLM 자가 수정 (troxy 무관) |
| 시나리오 소진 (loop=false, 마지막 step) | 마지막 step 무한 반복 (기존) | 변경 없음 |
| LLM이 호출한 troxy_mock_from_scenario_brief에 brief 없음 | N/A | 에러: `"'brief' is required"` |

---

## 10. 테스트 전략

### 10-1. unit tests (`tests/unit/`)

| 파일 | 케이스 |
|------|--------|
| `test_error_templates.py` | 카탈로그 8종 구조 검증 (required 필드: key, status_code, body_template, slots) |
| `test_scenario_brief_parser.py` | `parse_brief()` — 한국어 brief, 영어 brief, 범위 표현(`N-M회`), 알 수 없는 표현(placeholder 생성), 빈 brief |
| `test_mock_validation.py` | body JSON 검증 (valid/invalid/XML), 슬롯 미채움 경고 (단일/복수 슬롯, 슬롯 없음) |

### 10-2. integration / MCP handler tests

| 파일 | 케이스 |
|------|--------|
| `test_mock_handlers.py` | `handle_error_templates()` 반환 구조, `handle_mock_from_scenario_brief(brief=...)` 반환 구조, `brief` 없을 때 에러 |
| 기존 `test_mock_add_sequence.py` | body JSON 파싱 실패 에러, 슬롯 경고 포함 성공 케이스 추가 |

### 10-3. E2E (선택)
MCP 도구 흐름: `troxy_mock_error_templates` → `troxy_mock_add(sequence=[...])` → addon이 실제 요청에 올바른 step 반환 확인 (기존 E2E 패턴 참조).

---

## 11. 파일 영향 범위 (구현 시)

| 파일 | 변경 유형 |
|------|-----------|
| `src/troxy/core/error_templates.py` | **신규** — 정적 카탈로그 데이터 (`ERROR_TEMPLATES`) |
| `src/troxy/core/scenario_brief_parser.py` | **신규** — 공유 휴리스틱 파서 (`parse_brief()`) |
| `src/troxy/core/tool_catalog.py` | **수정** — 2개 도구 스키마 추가 (`troxy_mock_error_templates`, `troxy_mock_from_scenario_brief`) |
| `src/troxy/mcp/mock_handlers.py` | **수정** — 핸들러 2개 추가 + `handle_mock_add()` validation + 슬롯 경고 |
| `src/troxy/mcp/server.py` | **수정** — 신규 도구 라우팅 추가 |
| `src/troxy/cli/scenario_cmds.py` | **수정** — `from-brief` 서브커맨드 추가 (`--json`, `--execute`) |
| `tests/unit/test_error_templates.py` | **신규** |
| `tests/unit/test_scenario_brief_parser.py` | **신규** — 파서 유닛 테스트 |
| `tests/unit/test_mock_validation.py` | **신규** — body JSON 검증 + 슬롯 경고 |

---

## 12. 사용자 결정 항목 — 전체 결정 완료

| # | 항목 | **결정** |
|---|------|---------|
| TBD-1 | CLI `from-brief` LLM 호출 여부 | **없음** — 휴리스틱만 |
| TBD-2 | LLM provider | **N/A** (TBD-1=없음) |
| TBD-3 | body content-type 일치 검증 | **없음** |
| TBD-4 | troxy 재시작 시 카운터 auto-reset | **없음** — 명시적 reset 명령 충분 |
| TBD-5 | 슬롯 미채움(`{변수명}`) 경고 | **추가** — warning 반환, 저장 차단 X |
| TBD-6 | CLI `from-brief --json` 플래그 | **추가** |
| TBD-7 | 에러 템플릿 사용자 커스텀 | **없음** — 정적 8종 |

---

## 13. 우선순위 요약 (이슈 #6 기준)

| 컴포넌트 | 이슈 우선순위 | 결정 |
|----------|--------------|------|
| A. `troxy_mock_error_templates` | MUST | **구현** |
| B. `troxy_mock_from_scenario_brief` | SHOULD | **구현** |
| C. body validation + 슬롯 경고 | MUST | **구현** |
| D. CLI `from-brief` (`--json`, `--execute`) | SHOULD | **구현** (LLM 없이) |
| E. `scenario_brief_parser.py` 공통 모듈 | 내부 설계 결정 | **구현** |

---

*사용자(CEO) 승인 완료. 다음 단계: `writing-plans` 스킬로 구현 플랜 작성.*
