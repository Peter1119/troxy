# troxy

> terminal + proxy = troxy

mitmproxy가 캡처한 HTTP 트래픽을 CLI와 Claude MCP로 쉽게 조회하는 도구.

## 왜 만들었나

mitmproxy TUI는 사람이 직접 조작하기엔 괜찮지만:
- AI 에이전트(Claude 등)가 TUI를 조작할 수 없음 (키 입력 실패)
- flow body 복사, 검색, 필터링이 번거로움
- 스크립트로 자동화하기 어려움

troxy는 mitmproxy addon으로 모든 flow를 SQLite에 기록하고, CLI와 MCP로 조회합니다.

## 설치

```bash
brew install Peter1119/troxy/troxy
```

## 사용법

```bash
# 1. mitmproxy를 troxy addon과 함께 시작
troxy start

# 2. 앱을 프록시(8080 포트)를 통해 사용
#    flow가 자동으로 ~/.troxy/flows.db에 기록됨

# 3. 조회
troxy flows                        # 전체 flow 목록
troxy flows -d example.com         # 도메인 필터
troxy flows -s 401                 # 상태코드 필터
troxy flow 42 --body               # request/response body 확인
troxy flow 42 --export curl        # curl 명령어로 변환
troxy search "access_token"        # body 텍스트 검색
troxy tail                         # 실시간 스트리밍
```

## CLI 명령어

### 조회

```bash
troxy flows                        # flow 목록
troxy flows -d example.com         # 도메인 필터 (부분 매칭)
troxy flows -s 401                 # 상태코드 필터
troxy flows -m POST                # HTTP 메서드 필터
troxy flows -p /api/users          # 경로 필터
troxy flows -n 5                   # 최대 5개
troxy flows --since 5m             # 최근 5분
troxy flows --json                 # JSON 출력

troxy flow 42                      # flow 상세 (헤더 + body)
troxy flow 42 --body               # body만
troxy flow 42 --headers            # 헤더만
troxy flow 42 --request            # request만
troxy flow 42 --response           # response만
troxy flow 42 --export curl        # curl로 변환
troxy flow 42 --export httpie      # httpie로 변환

troxy search "token"               # 전체 body에서 검색
troxy search "token" -d example    # 도메인 범위 제한
troxy search "email" --in request  # request body에서만 검색

troxy tail                         # 실시간 flow 스트리밍
troxy tail -d example.com          # 특정 도메인만 스트리밍
troxy status                       # DB 상태 (flow 수, 크기)
troxy clear --yes                  # 전체 삭제
```

### Mock 응답

서버에 요청을 보내지 않고 가짜 응답을 반환:

```bash
troxy mock add -d api.example.com -p "/api/users/*" -s 200 \
  --body '{"id": 1, "name": "mock"}'

troxy mock from-flow 42            # 캡처된 flow의 응답을 mock으로 등록
troxy mock list                    # mock 규칙 목록
troxy mock disable 1               # 비활성화
troxy mock enable 1                # 활성화
troxy mock remove 1                # 삭제
```

### 요청 가로채기

요청을 가로채서 수정 후 전송:

```bash
troxy intercept add -d api.example.com -m POST
troxy pending                      # 가로챈 요청 목록
troxy modify 1 --header "Authorization: Bearer new_token"
troxy release 1                    # 수정 후 전송
troxy drop 1                       # 요청 취소
troxy replay 42                    # 저장된 flow 다시 보내기
```

## Claude MCP 연동

Claude Code에 MCP 서버를 등록하면, Claude가 mitmproxy flow를 직접 조회할 수 있습니다:

```bash
claude mcp add -e TROXY_DB=~/.troxy/flows.db -s user troxy -- troxy-mcp
```

이후 Claude에게 자연어로 요청:

- "401 에러 나는 요청 보여줘"
- "response body 확인해줘"
- "access_token이 포함된 요청 찾아줘"
- "curl로 변환해줘"

<details>
<summary>MCP 도구 목록 (17개)</summary>

| 도구 | 설명 |
|------|------|
| `troxy_status` | DB 상태 |
| `troxy_list_flows` | flow 목록/필터 |
| `troxy_get_flow` | flow 상세 |
| `troxy_search` | body 검색 |
| `troxy_export` | curl/httpie 변환 |
| `troxy_mock_add` | mock 규칙 추가 |
| `troxy_mock_list` | mock 규칙 목록 |
| `troxy_mock_remove` | mock 규칙 삭제 |
| `troxy_mock_toggle` | mock 활성화/비활성화 |
| `troxy_mock_from_flow` | flow에서 mock 생성 |
| `troxy_intercept_add` | 가로채기 규칙 추가 |
| `troxy_intercept_list` | 가로채기 규칙 목록 |
| `troxy_intercept_remove` | 가로채기 규칙 삭제 |
| `troxy_pending_list` | 대기 중인 flow 목록 |
| `troxy_modify` | 대기 flow 수정 |
| `troxy_release` | 대기 flow 전송 |
| `troxy_drop` | 대기 flow 취소 |

</details>

## 구조

```
mitmproxy -s troxy/addon.py
         |
    troxy addon (request/response hook)
         | 기록
         v
    SQLite (~/.troxy/flows.db)
         | 조회
    +----+----+
    v         v
  troxy     troxy
  CLI       MCP Server
```

## 설정

| 우선순위 | 방법 |
|---------|------|
| 1 | `--db` 플래그 |
| 2 | `TROXY_DB` 환경변수 |
| 3 | `~/.troxy/flows.db` (기본값) |

## License

MIT
