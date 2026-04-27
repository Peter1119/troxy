# Scripted Mock DX Design — CLI & MCP Interface

**작성일**: 2026-04-27  
**작성자**: Designer (troxy-scripted-mock 팀)  
**리뷰어**: PM  
**참조**:
- `2026-04-27-scripted-mock-vision.md` (CEO 스펙)
- `2026-04-27-scripted-mock-spec.md` (PM 스펙 — 유저 스토리, AC)

---

## 1. 설계 원칙

### 1-A. 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **1-call rule** | 에이전트가 시나리오 하나를 단일 MCP 호출로 완성할 수 있어야 한다 |
| **점진적 복잡도** | 간단한 케이스(status만)는 인라인으로, 복잡한 케이스(큰 body)는 JSON 파일로 |
| **기존 톤 유지** | `troxy mock` CLI 출력 스타일 (click echo, `[id]` prefix) 그대로 상속 |
| **LLM 친화적 description** | MCP tool description은 "언제 써야 하는지"를 첫 문장에 명시 |
| **하위 호환** | 기존 `troxy_mock_add` (단일 응답) 동작 변경 없음 |

### 1-B. 네이밍 결정

**CLI**: `troxy scenario` 서브그룹 — 시나리오 개념이 단순 mock rule과 구분됨을 사용자에게 알림. `troxy mock add --sequence`보다 인라인 syntax와의 조합이 자연스럽고 탭 완성이 빠르다. `troxy mock reset` 은 mock 그룹의 extension으로도 제공 (별칭).

**MCP**: 기존 `troxy_mock_*` 네임스페이스 내 확장 — `troxy_mock_add`에 `sequence` 파라미터 추가. 에이전트가 이미 `troxy_mock_add`를 알고 있으면 즉시 사용 가능. 신규 독립 tool은 `troxy_mock_reset`, `troxy_mock_update`만 추가.

**근거**: MCP 도구 수가 적을수록 에이전트가 선택 오류를 줄인다. `troxy_scenario_add`와 `troxy_mock_add(sequence=...)`가 공존하면 "어느 걸 써야 하나" 혼란을 유발한다.

---

## 1-C. PM 미결 사항 결정 (5개)

pm 스펙(`2026-04-27-scripted-mock-spec.md`) 하단에 designer 결정 요청 사항이 5개 있다. 아래에 명시적으로 결정한다.

| # | 미결 사항 | **결정** | 근거 |
|---|-----------|----------|------|
| 1 | 파라미터 이름: `sequence` vs `steps` vs `responses` | **`sequence`** | PM 스펙 전체가 `sequence` 사용. "순서형 시퀀스"라는 의미를 가장 잘 전달. `steps`는 UI wizard 느낌, `responses`는 방향 없음 |
| 2 | 소진 후 동작: sticky last vs 404 vs passthrough | **sticky last (기본값)** | AC-2에 명시됨. 404는 앱 crash 유발 위험. passthrough는 mock 의도를 무너뜨림. `loop=true` 옵션으로 순환 지원 |
| 3 | 단순 Mock + sequence 동시 전달 | **sequence 우선, 단순 파라미터 무시 + 경고 반환** | 에러로 막으면 에이전트 retry 비용 증가. 경고 메시지로 충분: `"sequence provided; status_code/body/headers ignored"` |
| 4 | CLI 명령어: `mock reset` vs `mock rewind` | **`troxy mock reset` (+ `troxy scenario reset`)** | "reset"은 보편적 기술 용어. `troxy_mock_reset` MCP tool명과 일치. 두 그룹 모두에서 동작 |
| 5 | 시퀀스 아이템 필수 필드 | **`status_code` 만 필수, `body`/`headers` optional** | 상태 코드만으로도 완전한 시나리오 가능 (e.g. `[{status_code:200}, {status_code:500}]`). 누락 시 빈 body, 기본 헤더 반환 |

---

## 2. 인라인 Step Syntax

짧은 시나리오는 따옴표로 감싼 comma-separated 문자열로 표현한다.

### 2-A. BNF

```
<steps>   ::= <step> ("," <step>)*
<step>    ::= <code> (":" <kv>)*
<kv>      ::= <key> "=" <value>
<key>     ::= "body" | "ct" | "header.<HeaderName>"
<code>    ::= 3-digit HTTP status code
<value>   ::= unquoted string (공백 없을 때) | 따옴표 없이 끝까지
```

### 2-B. 예시

```bash
# 가장 단순 — status code만
"200,401,500,200"

# body 포함 (짧은 JSON body는 인라인 가능)
"200:body={\"ok\":true},401:body={\"error\":\"unauthorized\"},500"

# content-type 지정
"200:body={\"ok\":true}:ct=application/json,401"

# 커스텀 헤더 포함
"200:body=OK:header.X-RateLimit-Remaining=0,429:body=Too Many Requests"
```

### 2-C. 파싱 규칙

- `body=` 뒤 값은 다음 `:key=` 또는 `,` 전까지 전체를 값으로 취급
- `:` 를 body 내부에 포함하려면 JSON 파일(`--from-json`) 사용 권장
- `ct=` 는 `Content-Type` 헤더의 축약 (별도로 `header.Content-Type=` 도 가능)
- `body=` 값이 `@path/to/file` 형태면 파일 내용을 읽음 (C2 — 2차 릴리즈)

### 2-D. 한계 (JSON 파일로 이전해야 하는 경우)

- body에 쉼표(`,`) 또는 콜론(`:`) 이 포함된 경우
- body가 100자 초과인 경우 (가독성 기준)
- 헤더 개수 3개 이상인 경우

---

## 3. CLI 명령 설계

### 3-A. `troxy scenario add` — 인라인

```
troxy scenario add -d <domain> -p <path> -s <steps> [options]
```

**옵션**:

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `-d, --domain` | 없음 | 매칭 도메인 (생략 시 전체) |
| `-p, --path` | `/*` | Glob 패턴 |
| `-m, --method` | 모든 메서드 | HTTP method |
| `-s, --steps` | **필수** | 인라인 step 문자열 |
| `--loop` | OFF | 소진 후 처음부터 순환 |
| `--name` | 없음 | 이름 (reset/remove 시 참조용) |
| `--db` | `~/.troxy/flows.db` | DB 경로 |

**실행 예시**:

```bash
$ troxy scenario add -d api.example.com -p /pay -s "200,401,500,200" --name pay-flicker
```

**출력**:

```
Scenario rule 7 ('pay-flicker') added.
  Steps: [200] → [401] → [500] → [200]
  Loop:  off (마지막 응답 반복 후 hold)
  Match: api.example.com /pay *
```

---

### 3-B. `troxy scenario add --from-json` — 파일 입력

복잡한 body나 다수 헤더가 필요할 때 JSON 파일로 정의한다.

```bash
$ troxy scenario add --from-json pay-scenario.json
```

**JSON 파일 형식** (`pay-scenario.json`):

```json
{
  "domain": "api.example.com",
  "path": "/pay",
  "method": "POST",
  "name": "pay-full-flow",
  "loop": false,
  "steps": [
    {
      "status_code": 200,
      "body": "{\"transaction_id\": \"txn_001\", \"status\": \"pending\"}",
      "headers": {"Content-Type": "application/json"}
    },
    {
      "status_code": 200,
      "body": "{\"transaction_id\": \"txn_001\", \"status\": \"processing\"}",
      "headers": {"Content-Type": "application/json"}
    },
    {
      "status_code": 200,
      "body": "{\"transaction_id\": \"txn_001\", \"status\": \"completed\"}",
      "headers": {"Content-Type": "application/json"}
    },
    {
      "status_code": 402,
      "body": "{\"error\": \"payment_failed\", \"code\": \"CARD_DECLINED\"}",
      "headers": {"Content-Type": "application/json", "X-Error-Code": "CARD_DECLINED"}
    }
  ]
}
```

**출력**:

```
Scenario rule 8 ('pay-full-flow') added.
  Steps: [200] → [200] → [200] → [402]
  Loop:  off
  Match: api.example.com /pay POST
```

---

### 3-C. `troxy scenario list`

```bash
$ troxy scenario list
```

**출력**:

```
[7] 'pay-flicker'   api.example.com /pay        step 1/4  loop=off  enabled
[8] 'pay-full-flow' api.example.com /pay POST   step 3/4  loop=off  enabled
[9] (unnamed)       api.example.com /auth/token  step 2/2  loop=on   disabled
```

- `--json` 플래그: JSON 배열 출력
- `--no-color` 플래그: ANSI 색상 제거 (CI 친화)

---

### 3-D. `troxy scenario status <rule_ref>`

현재 시퀀스 인덱스와 다음 응답 미리보기를 보여준다.

```bash
$ troxy scenario status pay-flicker
```

**출력**:

```
Scenario 7 'pay-flicker' — step 1/4
  Next response: 200 OK
  Remaining: [401] → [500] → [200]
  Loop: off
```

---

### 3-E. `troxy scenario reset <rule_ref>`

시퀀스 인덱스를 0으로 초기화한다.

```bash
$ troxy scenario reset pay-flicker
```

**출력**:

```
Scenario 7 'pay-flicker' reset to step 1.
```

---

### 3-F. `troxy scenario remove <rule_ref>`

```bash
$ troxy scenario remove pay-flicker
$ troxy scenario remove 7
```

**출력**:

```
Scenario rule 7 ('pay-flicker') removed.
```

---

### 3-G. `troxy scenario from-flows`

최근 N개 flow를 캡처해 시나리오를 자동 생성한다.

```bash
$ troxy scenario from-flows -d api.example.com -p /pay --last 4
```

**출력**:

```
Collected 4 flows for api.example.com /pay:
  flow 42: 200 OK
  flow 51: 401 Unauthorized
  flow 58: 500 Internal Server Error
  flow 63: 200 OK

Scenario rule 9 created.
  Steps: [200] → [401] → [500] → [200]
  Match: api.example.com /pay *
```

**옵션**:

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `-d, --domain` | **필수** | 도메인 필터 |
| `-p, --path` | **필수** | 경로 필터 |
| `--last` | 5 | 최근 N개 flow 사용 |
| `--name` | 없음 | 시나리오 이름 |
| `--loop` | OFF | 순환 여부 |

---

## 4. MCP 도구 설계

### 4-A. 설계 결정: 신규 도구 vs 기존 확장

**결론: 기존 `troxy_mock_*` 네임스페이스 확장 + 신규 도구 최소 추가**

| 도구 | 변경 유형 | 근거 |
|------|-----------|------|
| `troxy_mock_add` | **파라미터 확장** (`sequence` 추가) | 에이전트가 이미 아는 도구. 하위 호환 |
| `troxy_mock_list` | **응답 확장** (step 정보 포함) | 시그니처 변경 없음 |
| `troxy_mock_from_flow` | **파라미터 확장** (`body`, `enabled` 추가) | CEO SHOULD S2 |
| `troxy_mock_update` | **신규** | remove+add 제거용, CEO SHOULD S1 |
| `troxy_mock_reset` | **신규** | CEO MUST M5 |

`troxy_scenario_add` 같은 별도 도구는 추가하지 않는다. `troxy_mock_add(sequence=[...])` 로 동일 기능을 커버하며, 도구 수를 늘리면 에이전트의 선택 혼란이 증가한다.

---

### 4-B. `troxy_mock_add` — 확장 (sequence 파라미터 추가)

```json
{
  "name": "troxy_mock_add",
  "description": "Add a mock response rule. For a single static response, use status_code/body/headers. For a sequence of responses that rotate on each request (e.g. 200→401→500→200), use the 'sequence' parameter with an array of step objects — this replaces multiple troxy_mock_add calls with one. Set loop=true to cycle back to step 1 after the last step; default is to repeat the last step indefinitely.",
  "schema": {
    "type": "object",
    "properties": {
      "domain": {
        "type": "string",
        "description": "Domain to match (e.g. 'api.example.com'). Omit to match all domains."
      },
      "path_pattern": {
        "type": "string",
        "description": "Glob pattern for path (e.g. '/pay', '/user/*'). Default: matches all paths."
      },
      "method": {
        "type": "string",
        "description": "HTTP method to match (GET, POST, etc.). Omit to match all methods."
      },
      "status_code": {
        "type": "integer",
        "default": 200,
        "description": "Response status code. Used only when 'sequence' is not provided."
      },
      "headers": {
        "type": "string",
        "description": "JSON string of response headers (e.g. '{\"Content-Type\": \"application/json\"}'). Used only when 'sequence' is not provided."
      },
      "body": {
        "type": "string",
        "description": "Response body string. Used only when 'sequence' is not provided."
      },
      "name": {
        "type": "string",
        "description": "Optional name for easy reference in reset/remove/update calls (e.g. 'pay-error-flow')."
      },
      "sequence": {
        "type": "array",
        "description": "Array of response steps for a scripted/sequential mock. Each request advances to the next step. Provide this instead of status_code/body/headers when you need rotating responses.",
        "items": {
          "type": "object",
          "properties": {
            "status_code": {
              "type": "integer",
              "description": "HTTP status code for this step (e.g. 200, 401, 500)"
            },
            "body": {
              "type": "string",
              "description": "Response body for this step"
            },
            "headers": {
              "type": "string",
              "description": "JSON string of response headers for this step"
            }
          },
          "required": ["status_code"]
        }
      },
      "loop": {
        "type": "boolean",
        "default": false,
        "description": "When sequence is provided: if true, cycle back to step 1 after the last step. If false (default), repeat the last step indefinitely."
      }
    }
  }
}
```

**에이전트 사용 예시 (1-call 시나리오 생성)**:

```json
{
  "domain": "api.example.com",
  "path_pattern": "/pay",
  "method": "POST",
  "name": "pay-error-flow",
  "sequence": [
    {"status_code": 200, "body": "{\"status\": \"ok\"}", "headers": "{\"Content-Type\": \"application/json\"}"},
    {"status_code": 401, "body": "{\"error\": \"unauthorized\"}"},
    {"status_code": 500, "body": "{\"error\": \"server_error\"}"},
    {"status_code": 200, "body": "{\"status\": \"ok\"}"}
  ],
  "loop": true
}
```

---

### 4-C. `troxy_mock_reset` — 신규

```json
{
  "name": "troxy_mock_reset",
  "description": "Reset a scripted mock rule's sequence back to step 1. Use this when you want to replay the full scenario from the beginning (e.g. after running through the sequence in a test, reset before the next test run). Accepts the rule ID or name.",
  "schema": {
    "type": "object",
    "properties": {
      "id": {
        "type": "integer",
        "description": "Mock rule ID (from troxy_mock_list)"
      },
      "name": {
        "type": "string",
        "description": "Mock rule name (alternative to id)"
      }
    }
  }
}
```

---

### 4-D. `troxy_mock_update` — 신규

**참조 vs 변경 파라미터 분리 결정**: `name`이 "규칙 참조용"과 "이름 변경용"으로 혼용되지 않도록 명확히 분리한다.
- **참조**: `id` (integer) 또는 `name` (현재 이름, string) — 둘 중 하나 필수
- **이름 변경**: `new_name` (string, optional) — 별도 파라미터

```json
{
  "name": "troxy_mock_update",
  "description": "Update an existing mock rule in-place. Prefer this over troxy_mock_remove + troxy_mock_add when you only need to change one field (e.g. fix a typo in body, change status code). Reference the rule by 'id' (integer) or 'name' (current name string). To rename the rule, provide 'new_name'. Only provided fields are updated — others remain unchanged.",
  "schema": {
    "type": "object",
    "properties": {
      "id": {
        "type": "integer",
        "description": "Mock rule ID to reference (from troxy_mock_list). Use id OR name to identify the rule."
      },
      "name": {
        "type": "string",
        "description": "Current mock rule name to reference (alternative to id). This identifies which rule to update — not the new name."
      },
      "new_name": {
        "type": "string",
        "description": "Rename the rule to this new name. Optional."
      },
      "status_code": {
        "type": "integer",
        "description": "New status code (for single-response rules only)"
      },
      "body": {
        "type": "string",
        "description": "New response body (for single-response rules only)"
      },
      "headers": {
        "type": "string",
        "description": "New response headers as JSON string (for single-response rules only)"
      },
      "sequence": {
        "type": "array",
        "description": "Replace the entire step sequence (for scripted mock rules). Providing this replaces all steps.",
        "items": {
          "type": "object",
          "properties": {
            "status_code": {"type": "integer"},
            "body": {"type": "string"},
            "headers": {"type": "string"}
          },
          "required": ["status_code"]
        }
      },
      "loop": {
        "type": "boolean",
        "description": "Change loop behavior for scripted rules"
      },
      "enabled": {
        "type": "boolean",
        "description": "Enable or disable the rule"
      }
    },
    "oneOf": [
      {"required": ["id"]},
      {"required": ["name"]}
    ]
  }
}
```

---

### 4-E. `troxy_mock_from_flow` — 파라미터 확장

기존 도구에 `body`, `headers`, `enabled` 파라미터를 추가해 flow → enabled mock을 1회 호출로 완료한다.

```json
{
  "name": "troxy_mock_from_flow",
  "description": "Create a mock rule from an existing flow's response. To immediately activate the mock and optionally override the body, set enabled=true and provide a body. This reduces the typical 3-step workflow (from_flow → list → toggle) to a single call.",
  "schema": {
    "type": "object",
    "properties": {
      "flow_id": {
        "type": "integer",
        "description": "Flow ID to base the mock on (from troxy_list_flows)"
      },
      "status_code": {
        "type": "integer",
        "description": "Override the response status code (default: use flow's status code)"
      },
      "body": {
        "type": "string",
        "description": "Override the response body (default: use flow's response body)"
      },
      "headers": {
        "type": "string",
        "description": "Override response headers as JSON string (default: use flow's headers)"
      },
      "enabled": {
        "type": "boolean",
        "default": true,
        "description": "Whether to immediately enable the mock rule (default: true)"
      },
      "name": {
        "type": "string",
        "description": "Optional name for the created rule"
      }
    },
    "required": ["flow_id"]
  }
}
```

---

### 4-F. `troxy_mock_list` — 응답 확장

스키마 변경 없음. 응답 객체에 `sequence_steps`, `current_step` 필드 추가:

```json
[
  {
    "id": 3,
    "name": "pay-error-flow",
    "domain": "api.example.com",
    "path_pattern": "/pay",
    "method": null,
    "enabled": true,
    "status_code": null,
    "response_body": null,
    "sequence_steps": 4,
    "current_step": 2,
    "loop": true
  },
  {
    "id": 4,
    "name": "user-401",
    "domain": "api.example.com",
    "path_pattern": "/user/*",
    "method": null,
    "enabled": true,
    "status_code": 401,
    "response_body": "{\"error\": \"unauthorized\"}",
    "sequence_steps": null,
    "current_step": null,
    "loop": null
  }
]
```

- 단일 응답 rule: `sequence_steps=null`, `current_step=null`
- 시나리오 rule: `sequence_steps=N`, `current_step=<0-based index>`
- **`current_step` 인덱싱 규칙**: JSON 응답은 **0-based** (0 = 첫 번째 스텝 대기 중). CLI 출력은 **1-based** (`step 1/4`). 즉 JSON `current_step=2` → CLI `step 3/4`. Engineer는 CLI 출력 시 `+1` 변환 필요.

---

## 5. 에이전트 친화적 패턴

### 5-A. Description 작성 원칙

MCP tool description은 LLM tool-selection에서 결정적 역할을 한다. 아래 원칙을 적용한다:

1. **첫 문장 = 언제 써야 하는가** (When to use)
2. **두 번째 = 무엇을 하는가** (What it does)
3. **파라미터 description = "e.g." 포함** — 구체적 값 예시 필수
4. **대안 언급** — "X 대신 이것을 쓰라" 패턴으로 선택 오류 감소

**Before (기존 `troxy_mock_add`)**:
```
"Add a mock response rule. Matching requests get fake response instead of hitting server."
```

**After (확장된 `troxy_mock_add`)**:
```
"Add a mock response rule. For a single static response, use status_code/body/headers. 
For a sequence of responses that rotate on each request (e.g. 200→401→500→200), 
use the 'sequence' parameter with an array of step objects — this replaces multiple 
troxy_mock_add calls with one."
```

### 5-B. 에이전트 워크플로 — Before vs After

**Before: 4-step 시나리오 생성 (기존)**

```
call 1: troxy_mock_add(domain, path, status=200, body=...)
call 2: troxy_mock_add(domain, path, status=401, body=...)
call 3: troxy_mock_add(domain, path, status=500, body=...)
call 4: troxy_mock_add(domain, path, status=200, body=...)
# 4개 별도 rule 생성. 순서 보장 없음. 각각 toggle로 관리해야 함.
```

**After: 1-call (신규)**

```
call 1: troxy_mock_add(domain, path, sequence=[{200,...},{401,...},{500,...},{200,...}], loop=true)
# 완료. 순서 보장, 자동 순환, 단일 reset으로 초기화.
```

**Before: flow → mock 활성화 (기존, 최소 4 calls)**

```
call 1: troxy_list_flows(domain=..., limit=1)   → flow_id=42
call 2: troxy_get_flow(id=42)                    → body, headers 확인
call 3: troxy_mock_from_flow(flow_id=42)         → rule_id=7
call 4: troxy_mock_toggle(id=7, enabled=true)    → enabled
```

**After: 2 calls (개선된 troxy_mock_from_flow)**

```
call 1: troxy_list_flows(domain=..., limit=1)              → flow_id=42
call 2: troxy_mock_from_flow(flow_id=42, enabled=true)     → rule_id=7, enabled
```

### 5-C. `--json` 플래그 일관성

모든 `troxy scenario` CLI 명령에 `--json` 출력 지원. 에이전트가 CLI를 통해 호출할 경우 파싱 가능한 구조화 출력을 반환한다.

```bash
$ troxy scenario list --json
[
  {"id": 7, "name": "pay-flicker", "domain": "api.example.com",
   "path_pattern": "/pay", "current_step": 1, "total_steps": 4, "loop": false, "enabled": true}
]
```

---

## 6. 기존 mock 명령과의 시각적 일관성

### 6-A. 출력 스타일 비교

| 영역 | 기존 `troxy mock` 패턴 | `troxy scenario` 패턴 |
|------|----------------------|----------------------|
| 생성 메시지 | `Mock rule 3 added.` | `Scenario rule 7 ('name') added.` |
| 목록 포맷 | `[3] domain path -> 200 (enabled)` | `[7] 'name' domain path   step 1/4  loop=off  enabled` |
| 제거 메시지 | `Mock rule 3 removed.` | `Scenario rule 7 ('name') removed.` |
| 에러 | `click.echo(str(e), err=True)` + sys.exit(1) | 동일 |
| DB 플래그 | `--db` 공통 옵션 | 동일 |
| 색상 | `--no-color` 공통 옵션 | 동일 |

### 6-B. `troxy mock list` — 기존 출력에 시나리오 통합

기존 `mock list`도 시나리오 rule을 함께 표시. 시나리오 rule은 status_code 대신 `[seq:N]` 표시:

```
[3] 'user-401'    api.example.com /user/*   -> 401     (enabled)
[7] 'pay-flicker' api.example.com /pay      -> [seq:4] (enabled)  step=1/4
[9] (unnamed)     api.example.com /token    -> 200     (disabled)
```

---

## 7. CLI 모듈 구조

```
src/troxy/cli/
├── mock_cmds.py          # 기존 — 변경 최소화
├── scenario_cmds.py      # 신규 — troxy scenario 서브그룹
│                         #   add, list, status, reset, remove, from-flows
└── main.py               # _register_subgroups()에 scenario_group 추가
```

`scenario_cmds.py` 는 `core/mock.py` 또는 `core/mock_sequence.py` 의 함수만 import. `mock_cmds.py` import 금지 (순환 의존 방지).

---

## 8. 구현 우선순위 매핑 (CEO 스펙 → DX 구현 항목)

| CEO ID | 항목 | DX 구현 항목 |
|--------|------|-------------|
| M4 | `troxy_mock_add` sequence 파라미터 | §4-B |
| M5 | `troxy_mock_reset` MCP tool | §4-C |
| M6 | `troxy_mock_list` step 정보 노출 | §4-F |
| M7 | 기존 단일 응답 mock 호환 | §4-B (sequence 없을 때 기존 동작) |
| —  | **시나리오 rule enable/disable** | 기존 `troxy_mock_toggle` 그대로 동작 (schema 변경 없음, sequence rule도 동일 toggle 지원) |
| S1 | `troxy_mock_update` MCP tool | §4-D |
| S2 | `troxy_mock_from_flow` body/enabled 파라미터 | §4-E |
| S3 | loop 옵션 | §4-B (loop 파라미터), §3-A (--loop 플래그) |
| S5 | CLI scenario 서브커맨드 | §3 전체 |

---

## 9. Resolved Questions (PM 답변 완료)

| # | 질문 | **PM 결정** |
|---|------|------------|
| Q1 | `troxy scenario from-flows` flow 선택 기준 | ✅ **최근 N개 (삽입 순서)**. `-d`(domain)와 `-p`(path) 둘 다 필수 강제. 누락 시 명시적 에러 메시지 출력 |
| Q2 | `troxy_mock_update`의 이름 변경 허용 여부 | ✅ **허용**. 참조는 `id` or `name`(현재 이름), 이름 변경은 `new_name` 별도 파라미터로 분리 (§4-D 반영 완료) |
| Q3 | `troxy_mock_list` `response_body` truncate | ✅ **100자 초과 시 truncate** (기존 동작 유지) |
| Q4 | 시나리오 rule `mock enable/disable` 지원 | ✅ **기존 `troxy_mock_toggle` 그대로** (§8 매핑 테이블에 명시 완료) |

---

## 10. PM 스펙 Cross-Review (`2026-04-27-scripted-mock-spec.md`)

> Designer가 PM 스펙을 읽고 DX 관점에서 피드백한다.

### 잘된 점

- **유저 스토리 5개**가 실제 개발자 사용 패턴을 정확히 반영 (결제 retry, 401→갱신, 페이지네이션, 단순 1-call, reset)
- **AC-2의 sticky last 명시** — "마지막 항목을 계속 반환"이 정확한 기본 동작
- **AC-3의 1 MCP 호출 제약** — 측정 가능한 성공 기준이 명확
- **아키텍처 영향 섹션** — `sequence_json`, `sequence_index` 컬럼명이 구체적이고 engineer에게 충분한 신호를 줌

### 스코프 불일치 — 수정 제안

| 항목 | PM 스펙 현재 | DX 설계 결정 | 조정 필요 |
|------|-------------|-------------|----------|
| 외부 파일 import | "Out-of-Scope" (§3-B in CEO 스펙) | **CLI `--from-json` 로컬 파일은 허용** | PM 스펙에 "CLI --from-json: in-scope, MCP tool의 file path 파라미터: out-of-scope" 로 세분화 필요 |
| CLI 명령 | `troxy mock add --sequence`, `troxy mock reset` | `troxy scenario add -s`, `troxy mock reset` (별칭) | PM 명령 와이어프레임에 `troxy scenario` 그룹 반영 필요 |

### 미결 사항 — 이 문서(§1-C)에서 결정 완료

PM 스펙 하단에 나열된 5개 미결 사항은 이 DX 문서 §1-C에서 모두 결정했다:
1. `sequence` (확정)  
2. sticky last 기본값 (확정)  
3. sequence 우선 + 경고 (확정)  
4. `troxy mock reset` / `troxy scenario reset` 둘 다 (확정)  
5. `status_code` 만 필수 (확정)

### 추가 제안 (Engineer를 위해)

- PM 스펙 §아키텍처 영향에서 `mcp/server.py: 없음 (addon에서 처리)` — 확인 필요. MCP tool schema는 `core/tool_catalog.py`에서 관리하므로 `tool_catalog.py` 수정이 필요함. `mcp/server.py` 자체 변경은 없어도 됨 (tool_catalog에 신규 도구 추가 → MCP server 자동 노출).

---

*이 문서는 Designer 관점의 CLI/MCP DX 설계다. 구체적 DB 스키마와 함수 시그니처는 CTO 아키텍처 스펙에서 확정하고, 이 문서의 MCP schema를 기준으로 engineer가 구현한다.*
