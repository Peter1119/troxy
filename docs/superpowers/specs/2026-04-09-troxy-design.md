# troxy — Design Spec

> terminal + proxy = troxy
> mitmproxy를 Claude와 사람 모두 쉽게 사용할 수 있게 만드는 도구

## Problem

Claude가 mitmproxy TUI를 조작하지 못한다.
- `cmux send-key Enter/Tab`으로 flow 상세 진입 시도 → 실패
- body 복사, response 탭 전환 불가
- 결국 curl로 우회하거나 화면에 보이는 목록만으로 분석

사람도 mitmproxy TUI에서 특정 flow를 빠르게 찾고 body를 추출하는 게 번거롭다.

## Solution

mitmproxy addon이 flow를 SQLite에 실시간 기록하고, CLI와 MCP Server가 동일한 DB를 조회한다.

## Architecture

```
┌─────────────────────────────────┐
│  mitmproxy TUI (사람용, 기존)    │
│  mitmproxy -s troxy/addon.py   │
│         │                       │
│   troxy addon                   │
│   (flow → SQLite 실시간 기록)    │
└────────┬────────────────────────┘
         │ writes
         ▼
┌──────────────────┐
│  SQLite (flows.db) │
│  - flows table     │
└────────┬─────────┘
         │ reads
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│ troxy  │ │ troxy    │
│ CLI    │ │ MCP      │
│        │ │ Server   │
└────────┘ └──────────┘
```

### Layers

| Layer | Responsibility | Dependencies |
|-------|---------------|-------------|
| **addon** | mitmproxy response hook → SQLite 기록 | mitmproxy API, core |
| **core** | SQLite 조회 로직 (필터, 검색, export) | sqlite3 (stdlib) |
| **cli** | `troxy` 명령어 → stdout 출력 | core |
| **mcp** | MCP Server → JSON 응답 | core |

### Dependency Rule

`addon → core ← cli, mcp`

- core는 mitmproxy를 import하지 않는다 (순수 SQLite 로직)
- cli와 mcp는 서로 의존하지 않는다
- addon만 mitmproxy API를 사용한다

## Addon

mitmproxy의 `response` hook에서 flow 완료 시 SQLite에 기록한다.

### 기록하는 데이터

| Field | Source | Type |
|-------|--------|------|
| id | auto increment | INTEGER |
| timestamp | flow.timestamp_start | REAL |
| method | flow.request.method | TEXT |
| scheme | flow.request.scheme | TEXT |
| host | flow.request.host | TEXT |
| port | flow.request.port | INTEGER |
| path | flow.request.path | TEXT |
| query | flow.request.query string | TEXT |
| request_headers | JSON serialized | TEXT |
| request_body | flow.request.content (bytes→text or base64) | TEXT |
| request_content_type | Content-Type header | TEXT |
| status_code | flow.response.status_code | INTEGER |
| response_headers | JSON serialized | TEXT |
| response_body | flow.response.content (bytes→text or base64) | TEXT |
| response_content_type | Content-Type header | TEXT |
| duration_ms | (timestamp_end - timestamp_start) * 1000 | REAL |

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    method TEXT NOT NULL,
    scheme TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    path TEXT NOT NULL,
    query TEXT,
    request_headers TEXT NOT NULL,  -- JSON
    request_body TEXT,
    request_content_type TEXT,
    status_code INTEGER NOT NULL,
    response_headers TEXT NOT NULL,  -- JSON
    response_body TEXT,
    response_content_type TEXT,
    duration_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_flows_host ON flows(host);
CREATE INDEX IF NOT EXISTS idx_flows_status ON flows(status_code);
CREATE INDEX IF NOT EXISTS idx_flows_method ON flows(method);
CREATE INDEX IF NOT EXISTS idx_flows_timestamp ON flows(timestamp);
```

### Body Encoding

- text/* 또는 application/json: UTF-8 텍스트로 저장
- 그 외 binary: base64 인코딩 후 `b64:` prefix 붙여서 저장
- body가 없으면 NULL

## CLI

### Commands

```bash
# Flow 목록 조회
troxy flows [OPTIONS]
  --domain, -d TEXT      호스트 필터 (부분 매칭)
  --status, -s INT       상태코드 필터
  --method, -m TEXT      HTTP 메서드 필터
  --path, -p TEXT        경로 필터 (부분 매칭)
  --limit, -n INT        결과 수 (기본 50)
  --since TEXT           시간 필터 ("5m", "1h", "2024-01-01")
  --json                 JSON 출력
  --db PATH              DB 경로 (기본 ~/.troxy/flows.db)

# Flow 상세 조회
troxy flow ID [OPTIONS]
  --request              request만 표시
  --response             response만 표시
  --headers              headers만 표시
  --body                 body만 표시
  --raw                  포맷팅 없이 raw 출력
  --json                 JSON 출력
  --export FORMAT        curl|httpie|raw_request|raw_response

# 텍스트 검색
troxy search QUERY [OPTIONS]
  --domain, -d TEXT      도메인 범위 제한
  --in request|response  검색 범위
  --limit, -n INT        결과 수

# DB 관리
troxy clear              # 모든 flow 삭제
troxy clear --before 1h  # 1시간 이전 삭제
troxy status             # DB 상태 (flow 수, 크기, 경로)
```

### 출력 포맷

기본 목록 출력:
```
ID   TIME     METHOD  HOST                    PATH                         STATUS  SIZE   DURATION
42   09:55:13 GET     api.example.com        /api/users/17ov.../ratings   401     152b   30ms
43   09:55:13 POST    api.example.com        /api/users                   200     840b   371ms
```

상세 출력 (`troxy flow 42`):
```
── Request ──────────────────────────────
GET https://api.example.com/api/users/17ovVJlDr1vzy/ratings/2026/4
Host: api.example.com
Authorization: Bearer eyJ...
Accept: application/json

── Response (401) ── 30ms ───────────────
Content-Type: application/json

{
  "error": "unauthorized",
  "message": "Invalid or expired token"
}
```

## MCP Server

### Tools

```
troxy_list_flows(domain?, status?, method?, path?, limit?, since?)
→ Flow 목록 (id, timestamp, method, host, path, status_code, duration_ms)

troxy_get_flow(id, part?)
→ Flow 상세 (part: "all"|"request"|"response"|"body")

troxy_search(query, domain?, scope?, limit?)
→ 매칭된 flow 목록 + 매칭 위치 (scope: "request"|"response"|"all")

troxy_export(id, format?)
→ curl/httpie/raw 문자열 (format: "curl"|"httpie"|"raw_request"|"raw_response")

troxy_status()
→ DB 상태 정보
```

### MCP 등록

Claude Code settings.json에 추가:
```json
{
  "mcpServers": {
    "troxy": {
      "command": "python3",
      "args": ["-m", "troxy.mcp"],
      "env": {
        "TROXY_DB": "~/.troxy/flows.db"
      }
    }
  }
}
```

## Harness Engineering

### Repository-Level

**구조적 제약 (CI로 강제):**
1. 레이어 의존성 검증 — core 모듈에 `import mitmproxy` 있으면 실패
2. 파일 크기 제한 — 단일 .py 파일 300줄 이하
3. 테스트 커버리지 — core 레이어 90% 이상
4. 모든 CLI 명령어에 대한 E2E 테스트 존재

**테스트 하네스:**

| Level | What | How |
|-------|------|-----|
| Unit | core 조회 로직 | fixture DB → 함수 호출 → 결과 검증 |
| Integration | addon 기록 | mitmdump + test server → DB에 기록되었는지 검증 |
| CLI E2E | 명령어 실행 | subprocess로 troxy 실행 → stdout 검증 |
| MCP E2E | 도구 호출 | MCP 프로토콜로 도구 호출 → JSON 응답 검증 |

### Application-Level

**시나리오 기반 평가:**

실제 디버깅 상황을 fixture DB로 만들어서 도구가 충분한 정보를 제공하는지 검증.

| Scenario | Fixture | Pass Criteria |
|----------|---------|---------------|
| 401 원인 찾기 | 인증 실패 flows | `troxy flows --status 401` → flow 찾기, `troxy flow ID --body` → 에러 메시지 추출 |
| POST body 확인 | POST /api/users flows | `troxy flow ID --request --body` → JSON body 반환 |
| 리다이렉트 추적 | 302→302→200 chain | `troxy flows --domain X` → 시간순 체인 확인 |
| 텍스트 검색 | token 포함 body들 | `troxy search "access_token"` → 해당 flow 식별 |
| 대용량 응답 | 100KB+ body | body 온전히 반환, 잘리지 않음 |
| binary 응답 | image 응답 | base64로 안전하게 처리 |

**에이전트 평가:**

Claude가 MCP 도구를 사용하여 디버깅 태스크를 완수하는지 측정:

```
eval/
├── fixtures/           # 시나리오별 SQLite DB
│   ├── auth_failure.db
│   ├── redirect_chain.db
│   └── api_debug.db
├── scenarios/          # 태스크 정의 + 기대 결과
│   ├── find_401_cause.yaml
│   ├── extract_post_body.yaml
│   └── trace_redirect.yaml
└── runner.py           # 시나리오 실행 + 결과 검증
```

각 시나리오:
```yaml
name: find_401_cause
fixture: auth_failure.db
task: "api.example.com에서 401 응답이 오는 요청의 원인을 찾아라"
expected_tool_calls:
  - troxy_list_flows(status=401)
  - troxy_get_flow(id=*, part="response")
pass_criteria:
  - output_contains: "unauthorized"
  - flow_identified: true
```

## Project Structure

```
troxy/
├── CLAUDE.md               # 에이전트 지침 (맵)
├── ARCHITECTURE.md         # 아키텍처 개요
├── pyproject.toml          # uv project config
├── src/
│   └── troxy/
│       ├── __init__.py
│       ├── addon.py        # mitmproxy addon
│       ├── core/
│       │   ├── __init__.py
│       │   ├── db.py       # SQLite 연결/마이그레이션
│       │   ├── store.py    # flow 저장
│       │   ├── query.py    # flow 조회/필터/검색
│       │   └── export.py   # curl/httpie export
│       ├── cli/
│       │   ├── __init__.py
│       │   └── main.py     # click CLI
│       └── mcp/
│           ├── __init__.py
│           └── server.py   # MCP server
├── tests/
│   ├── conftest.py         # fixture DB 생성 helpers
│   ├── unit/
│   │   ├── test_db.py
│   │   ├── test_store.py
│   │   ├── test_query.py
│   │   └── test_export.py
│   ├── integration/
│   │   └── test_addon.py
│   └── e2e/
│       ├── test_cli.py
│       └── test_mcp.py
├── eval/
│   ├── fixtures/
│   ├── scenarios/
│   └── runner.py
├── scripts/
│   ├── lint_layers.py      # 레이어 의존성 검증
│   └── check_file_size.py  # 파일 크기 제한 검증
└── docs/
    ├── DESIGN.md
    └── superpowers/
        └── specs/
            └── 2026-04-09-troxy-design.md
```

## Tech Stack

- **Python 3.14** (시스템에 설치됨)
- **uv** — 패키지 관리
- **mitmproxy 12.2.1** — addon API
- **sqlite3** — 표준 라이브러리
- **click** — CLI 프레임워크
- **mcp** — MCP server SDK (anthropic/python-sdk)
- **pytest** — 테스트

## Configuration

DB 경로 결정 우선순위:
1. CLI `--db` 플래그
2. 환경변수 `TROXY_DB`
3. 기본값 `~/.troxy/flows.db`

addon도 동일한 환경변수를 참조한다.

## Out of Scope

- mitmproxy 설정 자동화 (인증서, 프록시 모드 등)
- flow 수정/리플레이 기능
- 웹 UI
- 원격 접속/멀티 사용자
