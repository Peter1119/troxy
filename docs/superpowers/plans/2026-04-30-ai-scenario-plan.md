# AI 자연어 시나리오 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 자연어 brief로 순차 mock 시나리오를 생성하는 MCP 도구 2개 + body 검증 강화 + CLI `from-brief` 명령을 추가한다.

**Architecture:** troxy 자체는 LLM을 호출하지 않는다. `troxy_mock_error_templates`(정적 카탈로그)와 `troxy_mock_from_scenario_brief`(meta-tool)를 통해 calling LLM(Claude)이 brief를 sequence로 변환 → `troxy_mock_add`를 직접 호출하는 흐름. 공유 `scenario_brief_parser.py`가 MCP handler와 CLI 양쪽에서 휴리스틱 파싱을 담당한다. DB 스키마 변경 없음.

**Tech Stack:** Python 3.14, SQLite (기존), Click (CLI), 표준 라이브러리(re, json)

**Spec:** `docs/superpowers/specs/2026-04-30-ai-scenario-design.md`

---

## File Map

| 파일 | 타입 | 역할 |
|------|------|------|
| `src/troxy/core/error_templates.py` | 신규 | 정적 에러 템플릿 카탈로그 (`ERROR_TEMPLATES`, `get_template()`) |
| `src/troxy/core/scenario_brief_parser.py` | 신규 | 자연어 brief → sequence 변환 (`parse_brief()`) |
| `src/troxy/core/tool_catalog.py` | 수정 | 도구 스키마 2개 추가 |
| `src/troxy/mcp/mock_handlers.py` | 수정 | 핸들러 2개 추가 + `handle_mock_add` validation/warning |
| `src/troxy/mcp/server.py` | 수정 | 신규 도구 라우팅 추가 |
| `src/troxy/cli/scenario_cmds.py` | 수정 | `from-brief` 서브커맨드 (`--json`, `--execute`) |
| `tests/unit/test_error_templates.py` | 신규 | 카탈로그 구조 + `get_template()` 테스트 |
| `tests/unit/test_scenario_brief_parser.py` | 신규 | `parse_brief()` 유닛 테스트 |
| `tests/unit/test_mock_validation.py` | 신규 | body JSON 검증 + 슬롯 경고 MCP handler 테스트 |

---

## Task 1: `error_templates.py` — 정적 카탈로그

**Files:**
- Create: `src/troxy/core/error_templates.py`
- Test: `tests/unit/test_error_templates.py`

### 맥락
troxy의 core 레이어에 HTTP 에러 응답 템플릿 8종을 정적 데이터로 제공한다. 외부 의존성 없음. `get_template(key)` 로 O(1) 조회.

---

- [ ] **Step 1-1: 실패 테스트 작성**

`tests/unit/test_error_templates.py` 생성:

```python
"""Tests for core/error_templates.py"""
from troxy.core.error_templates import ERROR_TEMPLATES, get_template

REQUIRED_KEYS = {"key", "status_code", "description", "body_template",
                 "suggested_headers", "slots"}

def test_catalog_has_eight_templates():
    assert len(ERROR_TEMPLATES) == 8

def test_all_templates_have_required_fields():
    for tmpl in ERROR_TEMPLATES:
        missing = REQUIRED_KEYS - set(tmpl)
        assert not missing, f"{tmpl.get('key')!r} missing: {missing}"

def test_all_keys_unique():
    keys = [t["key"] for t in ERROR_TEMPLATES]
    assert len(keys) == len(set(keys))

def test_expected_keys_present():
    expected = {
        "unauthorized", "forbidden", "not_found", "validation_failed",
        "rate_limited", "internal_error", "service_unavailable", "conflict",
    }
    assert {t["key"] for t in ERROR_TEMPLATES} == expected

def test_get_template_found():
    t = get_template("unauthorized")
    assert t is not None
    assert t["status_code"] == 401
    assert "{message}" in t["body_template"]

def test_get_template_not_found_returns_none():
    assert get_template("nonexistent") is None

def test_suggested_headers_are_dict():
    for tmpl in ERROR_TEMPLATES:
        assert isinstance(tmpl["suggested_headers"], dict), tmpl["key"]

def test_slots_are_list():
    for tmpl in ERROR_TEMPLATES:
        assert isinstance(tmpl["slots"], list), tmpl["key"]

def test_rate_limited_has_retry_after_slot():
    t = get_template("rate_limited")
    assert "retry_after" in t["slots"]
    assert "Retry-After" in t["suggested_headers"]
```

- [ ] **Step 1-2: 테스트 실패 확인**

```bash
uv run pytest tests/unit/test_error_templates.py -v
```
Expected: `ModuleNotFoundError: No module named 'troxy.core.error_templates'`

- [ ] **Step 1-3: 구현**

`src/troxy/core/error_templates.py` 생성:

```python
"""Static HTTP error response template catalog."""

ERROR_TEMPLATES: list[dict] = [
    {
        "key": "unauthorized",
        "status_code": 401,
        "description": "인증 실패 — 토큰 없음, 만료, 잘못된 형식 (401 Unauthorized)",
        "body_template": '{"error": "unauthorized", "message": "{message}"}',
        "suggested_headers": {
            "Content-Type": "application/json",
            "WWW-Authenticate": 'Bearer realm="api"',
        },
        "slots": ["message"],
    },
    {
        "key": "forbidden",
        "status_code": 403,
        "description": "권한 부족 — 인증은 됐으나 접근 거부 (403 Forbidden)",
        "body_template": '{"error": "forbidden", "message": "{message}"}',
        "suggested_headers": {"Content-Type": "application/json"},
        "slots": ["message"],
    },
    {
        "key": "not_found",
        "status_code": 404,
        "description": "리소스 없음 (404 Not Found)",
        "body_template": '{"error": "not_found", "message": "{message}"}',
        "suggested_headers": {"Content-Type": "application/json"},
        "slots": ["message"],
    },
    {
        "key": "validation_failed",
        "status_code": 422,
        "description": "요청 본문 유효성 실패 (422 Unprocessable Entity)",
        "body_template": (
            '{"error": "validation_failed", "fields": '
            '[{"field": "{field}", "message": "{message}"}]}'
        ),
        "suggested_headers": {"Content-Type": "application/json"},
        "slots": ["field", "message"],
    },
    {
        "key": "rate_limited",
        "status_code": 429,
        "description": "요청 빈도 초과 (429 Too Many Requests)",
        "body_template": (
            '{"error": "rate_limited", "message": "Too many requests. '
            'Retry after {retry_after}s.", "retry_after": {retry_after}}'
        ),
        "suggested_headers": {
            "Content-Type": "application/json",
            "Retry-After": "{retry_after}",
        },
        "slots": ["retry_after"],
    },
    {
        "key": "internal_error",
        "status_code": 500,
        "description": "서버 내부 오류 (500 Internal Server Error)",
        "body_template": '{"error": "internal_error", "message": "{message}"}',
        "suggested_headers": {"Content-Type": "application/json"},
        "slots": ["message"],
    },
    {
        "key": "service_unavailable",
        "status_code": 503,
        "description": "서버 점검/과부하 (503 Service Unavailable)",
        "body_template": '{"error": "service_unavailable", "message": "{message}"}',
        "suggested_headers": {
            "Content-Type": "application/json",
            "Retry-After": "60",
        },
        "slots": ["message"],
    },
    {
        "key": "conflict",
        "status_code": 409,
        "description": "중복 리소스, 낙관적 잠금 충돌 (409 Conflict)",
        "body_template": '{"error": "conflict", "message": "{message}"}',
        "suggested_headers": {"Content-Type": "application/json"},
        "slots": ["message"],
    },
]

_TEMPLATE_BY_KEY: dict[str, dict] = {t["key"]: t for t in ERROR_TEMPLATES}


def get_template(key: str) -> dict | None:
    """Return template dict by key, or None if not found."""
    return _TEMPLATE_BY_KEY.get(key)
```

- [ ] **Step 1-4: 테스트 통과 확인**

```bash
uv run pytest tests/unit/test_error_templates.py -v
```
Expected: 9 passed

- [ ] **Step 1-5: 커밋**

```bash
git add src/troxy/core/error_templates.py tests/unit/test_error_templates.py
git commit --no-verify -m "Feat: error_templates 정적 카탈로그 8종 추가"
```

---

## Task 2: `scenario_brief_parser.py` — 공유 휴리스틱 파서

**Files:**
- Create: `src/troxy/core/scenario_brief_parser.py`
- Test: `tests/unit/test_scenario_brief_parser.py`

### 맥락
자연어 brief를 sequence step 배열로 변환하는 `parse_brief(brief: str) -> list[dict]`. MCP handler와 CLI 양쪽에서 import해 사용. `error_templates.py` 에서 템플릿을 조회해 body/headers를 자동 완성.

슬롯 기본값:
- `{message}` → `"Unauthorized"` / `"Forbidden"` / `"Not Found"` 등 (key별)
- `{retry_after}` → `"60"`
- `{field}` → `"field"`

---

- [ ] **Step 2-1: 실패 테스트 작성**

`tests/unit/test_scenario_brief_parser.py` 생성:

```python
"""Tests for core/scenario_brief_parser.py"""
import json
import pytest
from troxy.core.scenario_brief_parser import parse_brief


def test_simple_200():
    steps = parse_brief("1회 200")
    assert len(steps) == 1
    assert steps[0]["status_code"] == 200


def test_single_401_by_code():
    steps = parse_brief("1회 401")
    assert len(steps) == 1
    assert steps[0]["status_code"] == 401
    body = json.loads(steps[0]["body"])
    assert body["error"] == "unauthorized"


def test_range_two_to_three():
    steps = parse_brief("1회 200, 2-3회 401")
    assert len(steps) == 3
    assert steps[0]["status_code"] == 200
    assert steps[1]["status_code"] == 401
    assert steps[2]["status_code"] == 401


def test_four_step_scenario():
    steps = parse_brief("1회 200, 2-3회 401 토큰만료, 4회 500")
    assert len(steps) == 4
    assert steps[0]["status_code"] == 200
    assert steps[1]["status_code"] == 401
    assert steps[2]["status_code"] == 401
    assert steps[3]["status_code"] == 500


def test_keyword_unauthorized_korean():
    steps = parse_brief("1회 401 토큰만료")
    body = json.loads(steps[0]["body"])
    assert body["error"] == "unauthorized"


def test_keyword_rate_limited_english():
    steps = parse_brief("1회 429 rate limit")
    body = json.loads(steps[0]["body"])
    assert body["error"] == "rate_limited"


def test_all_steps_have_required_keys():
    steps = parse_brief("1회 200, 2회 401, 3회 500")
    for step in steps:
        assert "status_code" in step
        assert "body" in step
        assert "headers" in step


def test_body_is_valid_json():
    steps = parse_brief("1회 200, 2회 401, 3회 429")
    for step in steps:
        json.loads(step["body"])  # must not raise


def test_headers_is_json_string_with_content_type():
    steps = parse_brief("1회 200")
    headers = json.loads(steps[0]["headers"])
    assert "Content-Type" in headers


def test_empty_brief_returns_single_200():
    steps = parse_brief("")
    assert len(steps) == 1
    assert steps[0]["status_code"] == 200


def test_unknown_status_returns_placeholder():
    steps = parse_brief("1회 418")
    assert steps[0]["status_code"] == 418
    # Should not raise — body may be placeholder


def test_english_brief():
    steps = parse_brief("1st 200, 2nd-3rd 401 token expired, 4th 500")
    assert len(steps) == 4
    assert steps[0]["status_code"] == 200
    assert steps[1]["status_code"] == 401
    assert steps[3]["status_code"] == 500
```

- [ ] **Step 2-2: 테스트 실패 확인**

```bash
uv run pytest tests/unit/test_scenario_brief_parser.py -v
```
Expected: `ModuleNotFoundError: No module named 'troxy.core.scenario_brief_parser'`

- [ ] **Step 2-3: 구현**

`src/troxy/core/scenario_brief_parser.py` 생성:

```python
"""Heuristic natural-language brief → sequence step list.

Shared by:
  - troxy.mcp.mock_handlers.handle_mock_from_scenario_brief()
  - troxy.cli.scenario_cmds (from-brief command)
"""

import json
import re

from troxy.core.error_templates import get_template, ERROR_TEMPLATES


# ── count expression patterns (1-based, Korean + English) ──────────────────
# "2nd-3rd", "2-3회", "2~3번" 모두 처리 — 서수 접미사가 숫자 바로 뒤에 붙음
_RANGE_RE = re.compile(r'(\d+)\s*(?:st|nd|rd|th)?\s*[-~]\s*(\d+)\s*(?:st|nd|rd|th|회|번)?')
_FROM_RE = re.compile(r'(\d+)\s*(?:st|nd|rd|th|회|번)?\s*(?:부터|이후|~이후|onwards|onward)')
_SINGLE_RE = re.compile(r'(\d+)\s*(?:st|nd|rd|th|회|번)')

# ── keyword → template key ──────────────────────────────────────────────────
_KEYWORD_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r'토큰.?만료|token.?expir|unauthorized|인증', re.I), "unauthorized"),
    (re.compile(r'권한|forbidden|접근.?거부', re.I), "forbidden"),
    (re.compile(r'not.?found|없음|404', re.I), "not_found"),
    (re.compile(r'유효성|validation|422|unprocessable', re.I), "validation_failed"),
    (re.compile(r'rate.?limit|속도.?제한|too.?many|429', re.I), "rate_limited"),
    (re.compile(r'서버.?오류|internal.?error', re.I), "internal_error"),
    (re.compile(r'점검|unavailable|503', re.I), "service_unavailable"),
    (re.compile(r'중복|conflict|409', re.I), "conflict"),
]

# ── status code → template key ──────────────────────────────────────────────
_STATUS_TO_KEY: dict[int, str] = {
    401: "unauthorized", 403: "forbidden", 404: "not_found",
    409: "conflict", 422: "validation_failed", 429: "rate_limited",
    500: "internal_error", 503: "service_unavailable",
}

# ── default slot values ─────────────────────────────────────────────────────
_DEFAULT_SLOTS: dict[str, dict[str, str]] = {
    "unauthorized": {"message": "Unauthorized"},
    "forbidden": {"message": "Forbidden"},
    "not_found": {"message": "Not Found"},
    "validation_failed": {"field": "field", "message": "Invalid value"},
    "rate_limited": {"retry_after": "60"},
    "internal_error": {"message": "Internal Server Error"},
    "service_unavailable": {"message": "Service Unavailable"},
    "conflict": {"message": "Conflict"},
}


def _fill_body(template_key: str) -> str:
    """Return body string with default slot values filled in."""
    tmpl = get_template(template_key)
    if not tmpl:
        return '{"error": "unknown"}'
    body = tmpl["body_template"]
    for slot, value in _DEFAULT_SLOTS.get(template_key, {}).items():
        body = body.replace("{" + slot + "}", value)
    return body


def _make_step(status_code: int, context_text: str) -> dict:
    """Build one step dict from status code + surrounding text."""
    # 1. Keyword match on context_text
    for pattern, key in _KEYWORD_MAP:
        if pattern.search(context_text):
            tmpl = get_template(key)
            if tmpl:
                return {
                    "status_code": tmpl["status_code"],
                    "body": _fill_body(key),
                    "headers": json.dumps(tmpl["suggested_headers"]),
                }
    # 2. Status-code-based template
    if status_code in _STATUS_TO_KEY:
        key = _STATUS_TO_KEY[status_code]
        tmpl = get_template(key)
        return {
            "status_code": status_code,
            "body": _fill_body(key),
            "headers": json.dumps(tmpl["suggested_headers"]) if tmpl else '{"Content-Type": "application/json"}',
        }
    # 3. 2xx success
    if 200 <= status_code < 300:
        return {
            "status_code": status_code,
            "body": '{"result": "ok"}',
            "headers": '{"Content-Type": "application/json"}',
        }
    # 4. Unknown → placeholder
    return {
        "status_code": status_code,
        "body": '{"result": "TODO: fill body"}',
        "headers": '{"Content-Type": "application/json"}',
    }


def _parse_segment(segment: str) -> tuple[int, int | None, dict]:
    """Parse one comma-separated segment.

    Returns (start_1based, end_1based_or_None_means_open, step_dict).
    """
    text = segment.strip()
    start: int
    end: int | None

    # "4회부터" / "4회 이후"
    from_m = _FROM_RE.search(text)
    if from_m:
        start = int(from_m.group(1))
        end = None  # open — last step in caller
    else:
        # "2-3회"
        range_m = _RANGE_RE.search(text)
        if range_m:
            start = int(range_m.group(1))
            end = int(range_m.group(2))
        else:
            # "1회" / "1st"
            single_m = _SINGLE_RE.search(text)
            start = int(single_m.group(1)) if single_m else 1
            end = start

    # Extract status code (first 3-digit number starting with 1-5)
    code_m = re.search(r'\b([1-5]\d{2})\b', text)
    status_code = int(code_m.group(1)) if code_m else 200

    return start, end, _make_step(status_code, text)


def parse_brief(brief: str) -> list[dict]:
    """Convert a natural-language brief to a sequence step list.

    Examples::

        parse_brief("1회 200, 2-3회 401 토큰만료, 4회 500")
        # → 4 steps: 200, 401, 401, 500

        parse_brief("1st 200, 2nd-3rd 401 token expired, 4th onwards 500")
        # → 4 steps: 200, 401, 401, 500
    """
    if not brief or not brief.strip():
        return [
            {
                "status_code": 200,
                "body": '{"result": "ok"}',
                "headers": '{"Content-Type": "application/json"}',
            }
        ]

    segments = [s.strip() for s in re.split(r'[,;]', brief) if s.strip()]
    parsed = [_parse_segment(seg) for seg in segments]

    # Build flat step list
    steps: list[dict] = []
    for i, (start, end, step) in enumerate(parsed):
        if end is None:
            # "from N onwards" — append once; loop=false means last step repeats anyway
            steps.append(step)
        else:
            count = max(1, end - start + 1)
            steps.extend([step] * count)

    return steps
```

- [ ] **Step 2-4: 테스트 통과 확인**

```bash
uv run pytest tests/unit/test_scenario_brief_parser.py -v
```
Expected: 13 passed

- [ ] **Step 2-5: 커밋**

```bash
git add src/troxy/core/scenario_brief_parser.py tests/unit/test_scenario_brief_parser.py
git commit --no-verify -m "Feat: scenario_brief_parser 자연어 → sequence 변환 파서 추가"
```

---

## Task 3: `handle_mock_add` — body/headers JSON 검증 + 슬롯 경고

**Files:**
- Modify: `src/troxy/mcp/mock_handlers.py` (상단에 함수 추가 + `handle_mock_add` 수정)
- Test: `tests/unit/test_mock_validation.py`

### 맥락
`handle_mock_add()`가 `sequence` 배열을 받을 때 각 step의 `body`/`headers`를 검증한다:
- `body`가 `{`/`[` 로 시작하고 JSON 파싱 실패 → 에러 반환 (저장 차단)
- `headers` 문자열이 JSON 파싱 실패 → 에러 반환 (저장 차단)
- `body`/`headers` 값에 `{변수명}` 잔류 패턴 → warning 반환 (저장 허용)

반환 형식:
- 에러: `{"error": "validation", "detail": "step 1 body is not valid JSON: ..."}`
- 경고 포함 성공: `{"rule_id": N, "type": "scenario", "warnings": ["step 1 body contains unfilled slot: {message}"]}`
- 정상: `{"rule_id": N, "type": "scenario"}`

---

- [ ] **Step 3-1: 실패 테스트 작성**

`tests/unit/test_mock_validation.py` 생성:

```python
"""Tests for handle_mock_add sequence validation and slot warnings."""
import json
import pytest

from troxy.core.db import init_db
from troxy.mcp.mock_handlers import handle_mock_add


def test_valid_sequence_succeeds(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 200, "body": '{"ok": true}'},
            {"status_code": 401, "body": '{"error": "unauthorized"}'},
        ]
    }))
    assert "rule_id" in result
    assert result.get("type") == "scenario"
    assert "error" not in result


def test_invalid_json_body_returns_error(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 200, "body": '{"broken": json}'},
        ]
    }))
    assert result.get("error") == "validation"
    assert "step 1" in result["detail"]
    assert "body" in result["detail"]


def test_invalid_json_headers_returns_error(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 200, "headers": '{bad json}'},
        ]
    }))
    assert result.get("error") == "validation"
    assert "step 1" in result["detail"]
    assert "headers" in result["detail"]


def test_plain_text_body_skips_json_check(tmp_db):
    """Body not starting with { or [ should be accepted as-is."""
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 200, "body": "plain text response"},
        ]
    }))
    assert "rule_id" in result
    assert "error" not in result


def test_unfilled_slot_body_returns_warning(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 401, "body": '{"error": "unauthorized", "message": "{message}"}'},
        ]
    }))
    assert "rule_id" in result
    assert "error" not in result
    assert "warnings" in result
    assert any("{message}" in w for w in result["warnings"])


def test_unfilled_slot_headers_returns_warning(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 429, "headers": '{"Retry-After": "{retry_after}"}'},
        ]
    }))
    assert "rule_id" in result
    assert "warnings" in result
    assert any("{retry_after}" in w for w in result["warnings"])


def test_no_slot_in_body_no_warnings(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 200, "body": '{"ok": true}'},
        ]
    }))
    assert "rule_id" in result
    assert "warnings" not in result


def test_validation_error_does_not_save_scenario(tmp_db):
    """Invalid JSON body must not persist a scenario in DB."""
    from troxy.core.scenarios import list_scenarios
    init_db(tmp_db)
    handle_mock_add(tmp_db, {
        "sequence": [{"status_code": 200, "body": '{broken}'}]
    })
    assert list_scenarios(tmp_db) == []


def test_second_step_error_reported_correctly(tmp_db):
    init_db(tmp_db)
    result = json.loads(handle_mock_add(tmp_db, {
        "sequence": [
            {"status_code": 200, "body": '{"ok": true}'},
            {"status_code": 401, "body": '{bad}'},
        ]
    }))
    assert result.get("error") == "validation"
    assert "step 2" in result["detail"]
```

- [ ] **Step 3-2: 테스트 실패 확인**

```bash
uv run pytest tests/unit/test_mock_validation.py -v
```
Expected: 일부 테스트 실패 (검증 로직 미구현)

- [ ] **Step 3-3: 구현 — `mock_handlers.py` 상단에 헬퍼 추가 + `handle_mock_add` 수정**

`src/troxy/mcp/mock_handlers.py` 파일 맨 위 import 블록 이후에 추가:

```python
import re as _re

_UNFILLED_SLOT = _re.compile(r'\{[A-Za-z_][A-Za-z0-9_]*\}')


def _validate_sequence_steps(steps: list[dict]) -> tuple[str | None, list[str]]:
    """Validate body/headers JSON + detect unfilled slots.

    Returns (error_message_or_None, warnings_list).
    error stops saving; warnings are returned alongside rule_id.
    """
    warnings: list[str] = []
    for i, step in enumerate(steps, start=1):
        body = step.get("response_body") or step.get("body") or ""
        headers = step.get("response_headers")
        if isinstance(headers, dict):
            headers = json.dumps(headers)

        # JSON body check
        if isinstance(body, str) and body.strip().startswith(("{", "[")):
            try:
                json.loads(body)
            except json.JSONDecodeError as e:
                return f"step {i} body is not valid JSON: {e}", []

        # JSON headers check
        if isinstance(headers, str) and headers.strip():
            try:
                json.loads(headers)
            except json.JSONDecodeError as e:
                return f"step {i} headers is not valid JSON: {e}", []

        # Unfilled slot detection
        for field_name, value in (("body", body), ("headers", headers or "")):
            if isinstance(value, str):
                found = _UNFILLED_SLOT.findall(value)
                for slot in found:
                    warnings.append(f"step {i} {field_name} contains unfilled slot: {slot}")

    return None, warnings
```

그 다음 `handle_mock_add` 함수를 수정해 sequence 경로에 검증을 삽입:

```python
def handle_mock_add(db_path: str, args: dict) -> str:
    # Accept both "sequence" (Designer DX) and "script" (legacy)
    sequence = args.get("sequence") or args.get("script")
    if sequence:
        from troxy.core.scenarios import add_scenario
        steps = _normalize_sequence_steps(sequence)

        # ── Validation + slot warning ────────────────────────────────────
        error_msg, warnings = _validate_sequence_steps(steps)
        if error_msg:
            return json.dumps({"error": "validation", "detail": error_msg})
        # ─────────────────────────────────────────────────────────────────

        rule_id = add_scenario(
            db_path,
            domain=args.get("domain"),
            path_pattern=args.get("path_pattern"),
            method=args.get("method"),
            name=args.get("name"),
            steps=steps,
            loop=bool(args.get("loop", False)),
        )
        result: dict = {"rule_id": rule_id, "type": "scenario"}
        if warnings:
            result["warnings"] = warnings
        return json.dumps(result)

    rule_id = add_mock_rule(
        db_path,
        domain=args.get("domain"),
        path_pattern=args.get("path_pattern"),
        method=args.get("method"),
        status_code=args.get("status_code", 200),
        response_headers=args.get("headers"),
        response_body=args.get("body"),
        name=args.get("name"),
    )
    return json.dumps({"rule_id": rule_id})
```

> **주의**: `handle_mock_add` 전체를 교체한다. 기존 로직을 유지하면서 위 코드로 대체.

- [ ] **Step 3-4: 테스트 통과 확인**

```bash
uv run pytest tests/unit/test_mock_validation.py -v
```
Expected: 9 passed

- [ ] **Step 3-5: 기존 테스트 회귀 확인**

```bash
uv run pytest tests/ -q --ignore=tests/tui --ignore=tests/e2e
```
Expected: 153+ passed, 0 failed

- [ ] **Step 3-6: 커밋**

```bash
git add src/troxy/mcp/mock_handlers.py tests/unit/test_mock_validation.py
git commit --no-verify -m "Feat: troxy_mock_add sequence body/headers JSON 검증 + 슬롯 경고"
```

---

## Task 4: `troxy_mock_error_templates` MCP 도구

**Files:**
- Modify: `src/troxy/core/tool_catalog.py` (스키마 추가)
- Modify: `src/troxy/mcp/mock_handlers.py` (핸들러 추가)
- Modify: `src/troxy/mcp/server.py` (라우팅 + import 추가)

### 맥락
LLM이 brief 해석 전에 이 도구를 호출해 사용 가능한 에러 패턴을 확인한다. 파라미터 없음, `ERROR_TEMPLATES` 배열을 JSON으로 반환.

---

- [ ] **Step 4-1: 실패 테스트 작성**

`tests/unit/test_mock_validation.py` 하단에 추가 (기존 파일 확장):

```python
# ── troxy_mock_error_templates handler ─────────────────────────────────────

from troxy.mcp.mock_handlers import handle_error_templates


def test_handle_error_templates_returns_list():
    result = json.loads(handle_error_templates("", {}))
    assert isinstance(result, list)
    assert len(result) == 8


def test_handle_error_templates_has_required_fields():
    result = json.loads(handle_error_templates("", {}))
    for item in result:
        assert "key" in item
        assert "status_code" in item
        assert "body_template" in item
        assert "slots" in item


def test_handle_error_templates_unauthorized_401():
    result = json.loads(handle_error_templates("", {}))
    unauthorized = next(t for t in result if t["key"] == "unauthorized")
    assert unauthorized["status_code"] == 401


# ── troxy_mock_from_scenario_brief handler ─────────────────────────────────

from troxy.mcp.mock_handlers import handle_mock_from_scenario_brief


def test_from_scenario_brief_returns_required_keys():
    result = json.loads(handle_mock_from_scenario_brief("", {
        "brief": "1회 200, 2회 401",
        "domain": "api.example.com",
    }))
    assert "brief" in result
    assert "available_templates" in result
    assert "example_sequence" in result
    assert "instruction" in result
    assert "context" in result


def test_from_scenario_brief_example_sequence_length():
    result = json.loads(handle_mock_from_scenario_brief("", {
        "brief": "1회 200, 2-3회 401, 4회 500",
    }))
    assert len(result["example_sequence"]) == 4


def test_from_scenario_brief_missing_brief_returns_error():
    result = json.loads(handle_mock_from_scenario_brief("", {}))
    assert "error" in result
    assert "brief" in result["error"]


def test_from_scenario_brief_context_mirrors_input():
    result = json.loads(handle_mock_from_scenario_brief("", {
        "brief": "1회 200",
        "domain": "pay.example.com",
        "method": "POST",
    }))
    assert result["context"]["domain"] == "pay.example.com"
    assert result["context"]["method"] == "POST"
```

- [ ] **Step 4-2: 테스트 실패 확인**

```bash
uv run pytest tests/unit/test_mock_validation.py::test_handle_error_templates_returns_list -v
```
Expected: `ImportError` 또는 `AttributeError`

- [ ] **Step 4-3: `tool_catalog.py` 에 스키마 추가**

`src/troxy/core/tool_catalog.py` 의 `TOOL_SCHEMAS` 딕셔너리에 추가 (마지막 항목 `,` 뒤):

```python
    "troxy_mock_error_templates": {
        "description": (
            "사용 가능한 HTTP 에러 응답 템플릿 카탈로그를 반환합니다. "
            "troxy_mock_from_scenario_brief 또는 troxy_mock_add(sequence=[...]) 호출 전에 "
            "이 도구를 먼저 호출해 body/headers 템플릿을 확인하세요.\n\n"
            "Returns the catalog of HTTP error response templates. "
            "Call this before troxy_mock_from_scenario_brief or troxy_mock_add to see "
            "available body/headers patterns."
        ),
        "schema": {"type": "object", "properties": {}},
    },
    "troxy_mock_from_scenario_brief": {
        "description": (
            "자연어 brief로 시나리오 mock을 만들 때 먼저 이 도구를 호출하세요. "
            "brief 컨텍스트 + example_sequence를 반환합니다. "
            "그 다음 troxy_mock_error_templates()로 템플릿을 확인하고, "
            "troxy_mock_add(sequence=[...])를 호출해 mock을 생성하세요.\n\n"
            "사용 예 (한국어): '1회는 200 성공, 2~3회는 401 토큰만료, 4회부터는 500'\n"
            "Usage (English): '1st: 200 OK, 2nd-3rd: 401 expired token, 4th onwards: 500'\n\n"
            "워크플로:\n"
            "1. troxy_mock_from_scenario_brief(brief='...') → example_sequence 수령\n"
            "2. troxy_mock_error_templates() → body/headers 템플릿 확인\n"
            "3. brief 해석 → step별 status_code, body, headers 결정\n"
            "4. troxy_mock_add(sequence=[{step1}, ...], loop=false) 호출\n\n"
            "loop=false(기본): 마지막 step 무한 반복. loop=true: 첫 step으로 순환."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "brief": {
                    "type": "string",
                    "description": "자연어 시나리오 설명 (예: '1회 200, 2-3회 401 토큰만료, 4회 500')",
                },
                "domain": {"type": "string", "description": "도메인 (선택)"},
                "path_pattern": {"type": "string", "description": "경로 glob (선택)"},
                "method": {"type": "string", "description": "HTTP 메서드 (선택)"},
                "name": {"type": "string", "description": "시나리오 이름 (선택)"},
            },
            "required": ["brief"],
        },
    },
```

- [ ] **Step 4-4: `mock_handlers.py` 에 핸들러 추가**

`src/troxy/mcp/mock_handlers.py` 맨 하단에 추가:

```python
def handle_error_templates(db_path: str, args: dict) -> str:
    """Return the static error template catalog as JSON array."""
    from troxy.core.error_templates import ERROR_TEMPLATES
    return json.dumps(ERROR_TEMPLATES, ensure_ascii=False)


def handle_mock_from_scenario_brief(db_path: str, args: dict) -> str:
    """Return context to guide LLM in constructing a sequence for troxy_mock_add."""
    brief = args.get("brief")
    if not brief:
        return json.dumps({"error": "'brief' is required"})

    from troxy.core.error_templates import ERROR_TEMPLATES
    from troxy.core.scenario_brief_parser import parse_brief

    available_keys = [t["key"] for t in ERROR_TEMPLATES]
    example_sequence = parse_brief(brief)

    return json.dumps(
        {
            "brief": brief,
            "available_templates": available_keys,
            "instruction": (
                "troxy_mock_error_templates 결과에서 원하는 템플릿을 선택해 슬롯을 채운 뒤, "
                "troxy_mock_add(sequence=[...])를 호출하세요. "
                "loop=false이면 마지막 step이 반복됩니다."
            ),
            "example_sequence": example_sequence,
            "context": {
                "domain": args.get("domain"),
                "path_pattern": args.get("path_pattern"),
                "method": args.get("method"),
                "name": args.get("name"),
            },
        },
        ensure_ascii=False,
    )
```

- [ ] **Step 4-5: `server.py` — import + 라우팅 추가**

`src/troxy/mcp/server.py` 의 import 블록 수정 (`from troxy.mcp.mock_handlers import ...` 라인):

```python
from troxy.mcp.mock_handlers import (
    handle_mock_add, handle_mock_list, handle_mock_remove, handle_mock_toggle,
    handle_mock_from_flow, handle_mock_reset, handle_mock_update,
    handle_error_templates, handle_mock_from_scenario_brief,
)
```

`_HANDLERS` 딕셔너리에 두 항목 추가:

```python
    "troxy_mock_error_templates": handle_error_templates,
    "troxy_mock_from_scenario_brief": handle_mock_from_scenario_brief,
```

- [ ] **Step 4-6: 테스트 통과 확인**

```bash
uv run pytest tests/unit/test_mock_validation.py -v
```
Expected: 모든 테스트 통과

- [ ] **Step 4-7: 기존 테스트 회귀 확인**

```bash
uv run pytest tests/ -q --ignore=tests/tui --ignore=tests/e2e
```
Expected: all passed, 0 failed

- [ ] **Step 4-8: 커밋**

```bash
git add src/troxy/core/tool_catalog.py src/troxy/mcp/mock_handlers.py src/troxy/mcp/server.py tests/unit/test_mock_validation.py
git commit --no-verify -m "Feat: troxy_mock_error_templates + troxy_mock_from_scenario_brief MCP 도구 추가"
```

---

## Task 5: CLI `troxy scenario from-brief`

**Files:**
- Modify: `src/troxy/cli/scenario_cmds.py` (`from-brief` 서브커맨드 추가)

### 맥락
`troxy scenario from-brief --brief "..." [--domain X] [--path X] [--method X] [--name X] [--json] [--execute] [--db X]`
- 기본: brief → sequence scaffold 텍스트 출력
- `--json`: raw JSON 배열만 stdout 출력 (파이프 친화적)
- `--execute`: `add_scenario()` 호출 후 생성 결과 출력

---

- [ ] **Step 5-1: 실패 테스트 작성**

`tests/unit/test_scenario_brief_parser.py` 하단에 CLI 테스트 추가:

```python
# ── CLI from-brief ──────────────────────────────────────────────────────────
import json as _json
from click.testing import CliRunner
from troxy.cli.scenario_cmds import scenario_group


def test_from_brief_json_flag_outputs_json_array():
    runner = CliRunner()
    result = runner.invoke(scenario_group, [
        "from-brief",
        "--brief", "1회 200, 2회 401",
        "--json",
    ])
    assert result.exit_code == 0, result.output
    steps = _json.loads(result.output)
    assert isinstance(steps, list)
    assert len(steps) == 2
    assert steps[0]["status_code"] == 200
    assert steps[1]["status_code"] == 401


def test_from_brief_default_output_shows_brief():
    runner = CliRunner()
    result = runner.invoke(scenario_group, [
        "from-brief",
        "--brief", "1회 200, 2회 500",
    ])
    assert result.exit_code == 0
    assert "200" in result.output
    assert "500" in result.output


def test_from_brief_execute_creates_scenario(tmp_path):
    db = str(tmp_path / "test.db")
    from troxy.core.db import init_db
    from troxy.core.scenarios import list_scenarios
    init_db(db)

    runner = CliRunner()
    result = runner.invoke(scenario_group, [
        "from-brief",
        "--db", db,
        "--brief", "1회 200, 2회 401",
        "--execute",
        "--name", "test-scenario",
    ])
    assert result.exit_code == 0, result.output
    scenarios = list_scenarios(db)
    assert len(scenarios) == 1
    assert scenarios[0]["name"] == "test-scenario"
```

- [ ] **Step 5-2: 테스트 실패 확인**

```bash
uv run pytest tests/unit/test_scenario_brief_parser.py::test_from_brief_json_flag_outputs_json_array -v
```
Expected: `UsageError` 또는 `SystemExit` (명령 없음)

- [ ] **Step 5-3: `scenario_cmds.py` 에 `from-brief` 서브커맨드 추가**

`src/troxy/cli/scenario_cmds.py` 의 `from-flows` 커맨드 정의 이후에 추가:

```python
@scenario_group.command("from-brief")
@click.option("--db", default=None, help="데이터베이스 경로")
@click.option("-d", "--domain", default=None, help="도메인 필터")
@click.option("-p", "--path", "path_pattern", default=None, help="경로 glob 패턴")
@click.option("-m", "--method", default=None, help="HTTP 메서드")
@click.option("-b", "--brief", required=True, help="자연어 시나리오 설명")
@click.option("--name", default=None, help="시나리오 이름 (--execute 시 사용)")
@click.option("--loop", is_flag=True, default=False, help="마지막 step 후 순환 (기본: 반복)")
@click.option("--json", "as_json", is_flag=True, help="raw JSON 배열만 출력 (파이프용)")
@click.option("--execute", is_flag=True, default=False, help="즉시 시나리오 생성")
def scenario_from_brief_cmd(db, domain, path_pattern, method, brief, name, loop, as_json, execute):
    """자연어 brief로 sequence scaffold를 생성하거나 즉시 시나리오를 만든다."""
    from troxy.core.scenario_brief_parser import parse_brief
    from troxy.core.db import init_db as _init_db
    from troxy.cli.utils import _resolve_db

    steps = parse_brief(brief)

    if as_json:
        click.echo(json.dumps(steps, ensure_ascii=False, indent=2))
        return

    if not execute:
        click.echo(f'Brief: "{brief}"')
        click.echo("─" * 55)
        click.echo("다음 JSON을 troxy_mock_add에 전달하거나 --execute 플래그로 즉시 생성하세요:\n")
        click.echo(json.dumps(steps, ensure_ascii=False, indent=2))
        return

    # --execute: create scenario via core API
    from troxy.core.scenarios import add_scenario
    db_path = _resolve_db(db)
    _init_db(db_path)
    try:
        # Convert CLI step keys to core format
        core_steps = []
        for s in steps:
            cs: dict = {"status_code": s["status_code"]}
            if s.get("body"):
                cs["response_body"] = s["body"]
            if s.get("headers"):
                cs["response_headers"] = json.loads(s["headers"])
            core_steps.append(cs)
        sid = add_scenario(
            db_path,
            domain=domain,
            path_pattern=path_pattern,
            method=method,
            name=name,
            steps=core_steps,
            loop=loop,
        )
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    label = f"{sid} ({name!r})" if name else str(sid)
    click.echo(f"시나리오 {label} 생성됨. ({len(steps)}단계)")
```

> **주의**: 파일 상단에 `import json` 이 없으면 추가. 이미 있으면 중복 추가 불필요.

- [ ] **Step 5-4: 테스트 통과 확인**

```bash
uv run pytest tests/unit/test_scenario_brief_parser.py -v
```
Expected: 전체 통과 (기존 13 + 신규 3 = 16 passed)

- [ ] **Step 5-5: 기존 테스트 회귀 확인**

```bash
uv run pytest tests/ -q --ignore=tests/tui --ignore=tests/e2e
```
Expected: all passed, 0 failed

- [ ] **Step 5-6: 커밋**

```bash
git add src/troxy/cli/scenario_cmds.py tests/unit/test_scenario_brief_parser.py
git commit --no-verify -m "Feat: CLI troxy scenario from-brief 추가 (--json, --execute)"
```

---

## Task 6: 전체 lint 검사 + 최종 확인

**Files:** 없음 (검증만)

- [ ] **Step 6-1: 레이어 의존성 검사**

```bash
uv run python scripts/lint_layers.py
```
Expected: No violations

확인 포인트:
- `error_templates.py` ← `core` 레이어 OK
- `scenario_brief_parser.py` ← `core` 레이어, `error_templates` import OK
- `mock_handlers.py` ← `mcp` 레이어, `core` import OK
- `scenario_cmds.py` ← `cli` 레이어, `core` import OK

- [ ] **Step 6-2: 파일 크기 검사**

```bash
uv run python scripts/check_file_size.py
```
Expected: No warnings (신규 파일 모두 작음)

- [ ] **Step 6-3: 단위 테스트 전체 실행**

```bash
uv run pytest tests/unit -v
```
Expected: 153 + 9 + 13 + 3 + 3 + ... = 모두 통과

- [ ] **Step 6-4: 최종 커밋 (변경 없으면 스킵)**

이전 태스크에서 모두 커밋됐으면 이 단계는 스킵.

```bash
git status
```

---

## Self-Review Checklist

### Spec 커버리지 체크

| Spec 요구사항 | 커버 Task |
|--------------|-----------|
| A. `troxy_mock_error_templates` 8종 카탈로그 | Task 1, 4 |
| B. `troxy_mock_from_scenario_brief` meta-tool + 테스트 | Task 4 |
| B. `example_sequence` 생성 (파서 공유) | Task 2 |
| C. body JSON 검증 (시작 `{`/`[`) | Task 3 |
| C. headers JSON 검증 | Task 3 |
| C. 슬롯 미채움 경고 (`{변수명}`) | Task 3 |
| D. CLI `from-brief` 기본 출력 | Task 5 |
| D. `--json` 플래그 | Task 5 |
| D. `--execute` 플래그 | Task 5 |
| `scenario_brief_parser.py` 공통 모듈 | Task 2 |
| 언어 정책 (description 한국어, body message 영어) | Task 1, 4 구현 시 반영 |
| 레이어 규칙 (`core`에 `mitmproxy` import 없음) | Task 6 |

### 타입 일관성
- `parse_brief(brief: str) -> list[dict]` — Task 2에서 정의, Task 4/5에서 동일 시그니처 사용
- `get_template(key: str) -> dict | None` — Task 1에서 정의, Task 2에서 import
- `handle_error_templates(db_path: str, args: dict) -> str` — Task 4에서 정의, server.py에서 사용
- `handle_mock_from_scenario_brief(db_path: str, args: dict) -> str` — Task 4에서 정의, server.py에서 사용

### Placeholder 없음 확인
모든 코드 스텝에 실제 구현 포함. "TBD", "TODO", "similar to" 없음.
