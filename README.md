# troxy

> **terminal + proxy = troxy**
> mitmproxy flow를 터미널 한 줄로 꺼내 쓰는 프록시 인스펙터. AI 쓰면 더 강해짐.

mitmproxy로 캡처한 모든 HTTP flow를 SQLite에 기록하고, **CLI와 (선택적으로) Claude MCP**로 조회합니다. TUI 키 안 외워도 되고, Claude 안 써도 손해 없고, Claude 쓰면 "401 왜 떠?"에 flow 보고 답해줍니다.

## 이런 분들을 위한 물건

- **mitmproxy는 쓰지만 키바인딩 외우기 귀찮아서 read-only만 쓰는 분** → `troxy flows -s 401`, `troxy explain 42` 한 줄이면 끝.
- **Charles/Proxyman 쓰다가 CLI로 넘어오려는 분** → GUI 없이도 `troxy quick` / `troxy explain`으로 한눈에 감 잡음.
- **Claude Code를 매일 쓰는 프론트/모바일 개발자** → `troxy init` 한 번으로 Claude가 flow를 직접 읽음.

## mitmproxy / Charles 대비

| | Charles / Proxyman | mitmproxy TUI | **troxy** |
|---|---|---|---|
| 한 줄로 flow 꺼내기 | ❌ GUI 필수 | ⚠ 키바인딩 필요 | ⭕ `troxy quick 42` |
| mock/intercept 한 줄 명령 | ❌ | ⚠ 모달 UI | ⭕ `troxy mock from-status 401` |
| shell 조합 (grep, jq) | ❌ | ⚠ | ⭕ `troxy flows --json \| jq` |
| AI로 자동 디버깅 | ❌ | ❌ | ⭕ MCP 17개 도구 |
| 가격 | 유료 | 무료 | 무료 / MIT |

## 60초 셋업

> Homebrew가 없으면 [brew.sh](https://brew.sh) 참고. troxy는 내부적으로 `python@3.14` + `uv`에 의존하는데 brew가 자동으로 받아와요.

```bash
# 1. 설치 (tap 자동 추가 + Formula 설치)
brew install peter1119/troxy/troxy

# 2. 가이드 온보딩 — CA 생성·신뢰·기기 프록시 안내까지 한 번에
troxy onboard            # 없으면 CA 자동 생성 → macOS 키체인 신뢰 → iOS/Android 안내
troxy doctor             # 환경 검증 (cert / DB / MCP 등)

# 3. (선택) Claude MCP 등록 — AI 없이도 troxy 다 쓸 수 있음
troxy init
```

### 이미 설치했는데 명령어가 없다고 나오면
```bash
brew update && brew upgrade peter1119/troxy/troxy    # formula 최신화
```

### 기기에 CA 설치하기 (HTTPS 가로채려면 필수)

`troxy onboard`가 대부분 안내하지만 요약:

| 플랫폼 | 방법 |
|---|---|
| macOS | `troxy onboard` 가 `sudo` 1회로 시스템 키체인에 자동 등록 |
| iOS Simulator / 실기 | 기기를 `127.0.0.1:8080` 프록시로 연결한 뒤 Safari에서 `http://mitm.it` → iOS 프로필 설치 → **설정 → 일반 → 정보 → 인증서 신뢰 설정**에서 mitmproxy 토글 ON |
| Android Emulator | 프록시 켠 뒤 `http://mitm.it` 에서 CA 설치. 단 Android 7+ 는 앱이 `network_security_config.xml` 로 user CA 신뢰해야 가로채짐 |

### 첫 흐름 확인

```bash
troxy flows           # 최근 flow 목록
troxy status          # 캡처된 수 / DB 크기
```

### Claude에게 물어보기

MCP 등록이 되어 있으면 Claude Code에서 바로:

> "`api.example.com`에서 최근 5분 안에 401 떠?"
> "그 flow의 response body 보여줘"
> "위 요청을 curl로 뽑아줘"

Claude가 `troxy_list_flows`, `troxy_get_flow`, `troxy_export` 도구를 체인해서 답합니다.

## 핵심 명령어

### 조회 (read-only 유저 입문 루트)
```bash
troxy flows                        # 전체 flow
troxy pick                         # ↑↓로 고르는 interactive picker (TTY)
troxy flows -d example.com -s 401  # 도메인+상태코드 필터
troxy flows -m POST --since 5m     # POST + 최근 5분
troxy quick 42                     # 한 줄 요약 (mitmproxy Enter 대체)
troxy explain 42                   # 자동 진단 (JWT 만료, Retry-After, Cache-Control, 5xx trace 등)
troxy flow 42 --body               # body만
troxy flow 42 --export curl        # curl로 변환 (shell-safe quoting)
troxy search "access_token"        # 전체 body 검색
troxy tail -s 4xx                  # 4xx 실시간 스트리밍
```

### Session (프로젝트별 DB)
```bash
troxy session save example-debug /tmp/example.db
troxy session list                 # 저장된 세션
eval "$(troxy session use example-debug)"   # 현재 셸에서 TROXY_DB 세팅
```

### Alias (자주 쓰는 필터 단축어)
```bash
troxy alias add auth   "flows -s 401"
troxy alias add slow   "flows --since 5m -m POST"
troxy auth                         # `troxy flows -s 401` 실행
troxy alias                        # 등록된 alias 목록
```

### Mock (서버 대신 가짜 응답)
```bash
troxy mock from-status 401 -d api.example.com   # 최근 401을 한 줄로 mock화
troxy mock from-flow 42                         # 특정 flow 재사용
troxy mock add --name user-500 -d api.example.com -p "/api/users/*" -s 500 \
  --body '{"error": "boom"}'
troxy mock disable user-500                     # 이름으로 toggle
troxy mock list
```

### Intercept (요청 가로채서 수정)
```bash
troxy intercept add -d api.example.com -m POST
troxy pending                      # 가로챈 요청 대기열
troxy modify 1 --header "Authorization: Bearer new_token"
troxy release 1                    # 수정 후 서버로 전송
troxy drop 1                       # 취소
troxy replay 42 --header "X-Debug: 1"  # 저장된 flow 재전송 + 헤더 오버라이드
```

### 관리
```bash
troxy version                      # 버전/환경 정보
troxy doctor                       # 설정 진단 (cert, MCP, DB)
troxy onboard                      # 가이드 온보딩 (cert trust + 기기 프록시)
troxy init                         # Claude MCP 자동 등록
troxy mcp-tools                    # MCP 도구 목록 + 예시 프롬프트
troxy clear --before 1h            # 1시간 이상 된 flow 삭제
```

### Body 크기 제한 (기본 1MB)
대용량 응답으로 DB가 비대해지지 않도록 body 저장 시 자동 잘라냅니다.
```bash
TROXY_MAX_BODY=10MB troxy start    # 기본값 바꾸기
TROXY_MAX_BODY=0 troxy start       # 제한 해제
```
**기존 DB는 영향 받지 않습니다** — 새로 들어오는 flow에만 적용됩니다.

## Claude MCP 도구 (17개)

<details>
<summary>펼치기</summary>

| 도구 | 설명 |
|------|------|
| `troxy_status` | DB 상태 |
| `troxy_list_flows` | flow 목록 (`since` 상대시간 지원) |
| `troxy_get_flow` | flow 상세 (part: all/request/response/body) |
| `troxy_search` | body + header 검색 |
| `troxy_export` | curl/httpie 변환 |
| `troxy_mock_add/list/remove/toggle/from_flow` | Mock 규칙 CRUD |
| `troxy_intercept_add/list/remove` | Intercept 규칙 CRUD |
| `troxy_pending_list` | 가로챈 flow 대기열 |
| `troxy_modify/release/drop` | 가로챈 flow 제어 |

</details>

## 아키텍처

```
mitmproxy -s troxy/addon.py
     │  (request/response hook)
     ▼
SQLite (~/.troxy/flows.db)
     │
   ┌─┴─┐
   ▼   ▼
  CLI  MCP Server
```

레이어 규칙:
- `src/troxy/core/`는 **mitmproxy import 금지** (순수 SQLite)
- `addon.py`만 mitmproxy 의존
- `cli`, `mcp`는 서로 의존하지 않고 `core`만 씀

자세한 내용: [ARCHITECTURE.md](ARCHITECTURE.md)

## 설정

| 우선순위 | 방법 |
|---------|------|
| 1 | `--db` 플래그 |
| 2 | `TROXY_DB` 환경변수 |
| 3 | `~/.troxy/flows.db` (기본값) |

## 보안 주의

- **Authorization / Cookie / body에 든 비밀**이 그대로 SQLite에 평문 저장됩니다.
- 공용 머신에서 쓸 때는 `troxy clear`로 주기적으로 비우거나 `TROXY_DB`로 분리하세요.
- CI나 공유 저장소에 `~/.troxy/flows.db`를 커밋하지 마세요.

## 트러블슈팅

`troxy doctor`가 대부분 찾아줍니다. 자주 나오는 이슈:

| 증상 | 원인 | 해결 |
|---|---|---|
| `troxy doctor`/`onboard`/`explain`이 "No such command" | 구버전(v0.2.0) 설치 | `brew update && brew upgrade peter1119/troxy/troxy` |
| 인증서 에러 (SSL handshake 실패) | CA cert 미신뢰 | `troxy onboard` — macOS 키체인 자동 등록. iOS/Android는 기기에서 `http://mitm.it` 접속해 설치 |
| `troxy-mcp not on PATH` | 수동 설치 후 PATH 누락 | `brew reinstall peter1119/troxy/troxy` — brew 경로로 재설치 |
| Claude에서 MCP 안 보임 | 등록 scope 문제 | `troxy init --force --scope user` |

## 개발

```bash
uv sync --all-extras
uv run pytest                         # 76 tests
uv run python scripts/lint_layers.py
uv run python scripts/check_file_size.py
```

## License

MIT
