# form-urlencoded 디코딩 개선

## 배경

Apple IAP receipt 디버깅 중, `application/x-www-form-urlencoded` 바디가 `troxy_list_flows` / `troxy_get_flow` 결과에서 `b64:...` prefix 단일 덩어리로만 보이는 문제가 발견됐다. 사람이 직접 base64 → URL-decode → form split → ASN.1까지 손으로 풀어야 받아볼 수 있는 상태.

근본 원인은 `src/troxy/core/store.py:_encode_body`의 텍스트 화이트리스트(`text/`, `json`, `xml`, `javascript`, `html`)에 `application/x-www-form-urlencoded`가 빠져 있어서, ASCII 텍스트인데도 binary 분기로 떨어지는 것이다.

## 목표

1. form-urlencoded 바디는 wire format 텍스트(`a=1&b=2`)로 저장돼 모든 reader에서 자연스럽게 읽힘.
2. 에이전트/사람이 `troxy_get_flow`를 한 번 호출해 `{"key": "decoded value", ...}` 맵을 받을 수 있음 (URL-decode 포함, 큰 base64 값은 길이/sha 요약).

## 비목표

- PKCS7 / ASN.1 파싱
- Apple IAP receipt 도메인 지식 (bundle_id, in_app[*] 등)
- StoreKit Test vs Sandbox 감지
- multipart/form-data, gzip, Content-Encoding 핸들링

위 항목은 추후 별도 작업.

## 아키텍처

레이어 규칙(`addon → core ← cli, mcp`)을 그대로 유지한다.

| 파일 | 변경 |
|------|------|
| `src/troxy/core/store.py` | `_encode_body` 화이트리스트에 `x-www-form-urlencoded` 추가 (`in` 매칭으로 charset 파라미터 포함 케이스 커버) |
| `src/troxy/core/formats.py` | **신규**. `parse_form_body(body, *, summary_threshold=256) -> dict` 순수 함수 |
| `src/troxy/core/tool_catalog.py` | `troxy_get_flow` `part` enum에 `"form"` 추가, description 보강 |
| `src/troxy/mcp/server.py` | `handle_get_flow`에 `part == "form"` 분기 추가 |

새 파이썬 패키지 의존성 없음. URL-decode는 표준라이브러리 `urllib.parse.parse_qsl`.

## `_encode_body` 변경

```python
# 추가
or "x-www-form-urlencoded" in content_type
```

`startswith` 대신 부분 매칭 — `application/x-www-form-urlencoded; charset=utf-8` 케이스 커버.

## `parse_form_body` 명세

**시그니처**:
```python
def parse_form_body(body: str, *, summary_threshold: int = 256) -> dict
```

**출력 모양 (성공)**:
```json
{
  "fields": {
    "ticket_type": "Ticket::Tall",
    "receipt_data": {
      "_kind": "binary-base64",
      "len": 12345,
      "sha256": "abcd...",
      "preview": "MIIWXAYJ..."
    }
  },
  "truncated": false
}
```

**규칙**:
1. `urllib.parse.parse_qsl(body, keep_blank_values=True, strict_parsing=False)` 사용. 파싱 실패 시 `{"error": "form parse failed", "reason": ...}`.
2. 같은 키 중복 시 마지막 값 사용 (단순화).
3. 각 값에 대해:
   - 길이 ≤ `summary_threshold` → 디코드된 문자열 그대로
   - 길이 > `summary_threshold`이고 base64-like (`^[A-Za-z0-9+/=]+$`, 길이 ≥ 100) → `{"_kind": "binary-base64", "len": <원본 길이>, "sha256": <앞 16자>, "preview": <앞 64자>}`
   - 그 외 큰 값 → `{"_kind": "long-text", "len": N, "sha256": ..., "preview": ...}`
4. 바디에 `\n[truncated at NB]` 마커가 있으면 제거하고 `truncated: true`.

## `troxy_get_flow` part="form"

**핸들러 분기 (`handle_get_flow`)**:
1. content-type이 `x-www-form-urlencoded`를 포함하지 않으면 → `{"error": "not form-urlencoded", "content_type": "<actual>"}`
2. 바디가 None / 빈 문자열 → `{"fields": {}, "truncated": false}`
3. 바디가 `b64:`로 시작 (레거시 데이터) → base64 decode → utf-8 decode → `parse_form_body`
4. 그 외 → `parse_form_body(body)` 호출 결과 반환

## 호환성

- 기존 `b64:`로 저장된 form 데이터는 retroactive 변환하지 않음. `part="form"` 호출 시 핸들러가 b64 prefix 감지 → decode → 파싱.
- 신규 캡처는 텍스트로 저장되므로 cli/formatting/tui 등 기존 reader에 추가 변경 불필요.

## 테스트

**unit (`tests/unit/`)**:

`test_store.py` 보강:
- `application/x-www-form-urlencoded` 바디 → 텍스트 그대로 (b64 prefix 없음)
- `application/x-www-form-urlencoded; charset=utf-8` (파라미터 포함) → 동일

`test_formats.py` (신규):
- `a=1&b=2` → `{"a":"1","b":"2"}`
- URL-encoded: `ticket_type=Ticket%3A%3ATall` → `Ticket::Tall`
- 큰 base64-like 값 → `_kind: binary-base64` + len/sha/preview
- 큰 일반 텍스트 → `_kind: long-text`
- truncation 마커 포함 → `truncated: true`
- 빈 바디 → `{"fields": {}, "truncated": false}`

`test_mcp_server.py` (또는 신규):
- 신규 텍스트 form 바디 part="form" → 파싱 결과
- 레거시 `b64:` form 바디 part="form" → 파싱 결과
- form 아닌 content-type part="form" → `not form-urlencoded` 에러
- 빈 바디 part="form" → 빈 fields

**lint**:
- `uv run python scripts/lint_layers.py`
- `uv run python scripts/check_file_size.py`

## 실행 순서

1. `core/formats.py` + 단위 테스트
2. `core/store.py` 화이트리스트 수정 + 단위 테스트
3. `core/tool_catalog.py` 스키마 갱신
4. `mcp/server.py` 핸들러 분기 + 통합 테스트
5. 전체 테스트 + lint
