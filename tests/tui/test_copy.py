"""Tests for troxy.tui.copy — user-facing text constants and functions."""

from troxy.tui.copy import (
    LIST_HINT,
    DETAIL_HINT,
    MOCK_LIST_HINT,
    COPY_OPTIONS,
    filter_status_text,
    toast_copied,
    toast_mock_saved,
    toast_mock_deleted,
    toast_cleared,
    toast_intercept_placeholder,
    confirm_clear,
    confirm_mock_delete,
    info_bar,
    header_text,
)


def test_list_hint_contains_all_actions():
    assert "필터" in LIST_HINT
    assert "mock" in LIST_HINT
    assert "초기화" in LIST_HINT
    assert "종료" in LIST_HINT
    assert "상세" in LIST_HINT
    assert "사이드" in LIST_HINT


def test_detail_hint_contains_all_actions():
    assert "복사" in DETAIL_HINT
    assert "스크롤" in DETAIL_HINT
    assert "mock" in DETAIL_HINT
    assert "curl" in DETAIL_HINT
    assert "Esc" in DETAIL_HINT
    assert "탭 전환" in DETAIL_HINT


def test_mock_list_hint_contains_all_actions():
    assert "토글" in MOCK_LIST_HINT
    assert "편집" in MOCK_LIST_HINT
    assert "삭제" in MOCK_LIST_HINT
    assert "뒤로" in MOCK_LIST_HINT


def test_copy_options_has_six_entries():
    assert len(COPY_OPTIONS) == 6
    keys = [opt[0] for opt in COPY_OPTIONS]
    assert keys == ["1", "2", "3", "4", "5", "6"]


def test_filter_status_text():
    # Round 7: signature collapsed to (summary); Esc no longer clears filter,
    # so "Esc" copy was removed and replaced with "f to edit".
    result = filter_status_text("host:api.* status:4xx")
    assert "host:api.* status:4xx" in result
    assert "f 편집" in result
    assert "Esc" not in result


def test_filter_status_text_uses_search_icon():
    # Mutation probe: swap 🔍 for another glyph → this test FAILs.
    result = filter_status_text("host:a.com")
    assert "\U0001f50d" in result


def test_toast_copied_small():
    result = toast_copied("URL", 128)
    assert "128b" in result
    assert "URL" in result


def test_toast_copied_large():
    result = toast_copied("Response", 2048)
    assert "2.0KB" in result
    assert "Response" in result


def test_toast_mock_saved():
    result = toast_mock_saved("users-401")
    assert "users-401" in result
    assert "활성화" in result


def test_toast_mock_deleted():
    result = toast_mock_deleted("login-200")
    assert "login-200" in result
    assert "삭제됨" in result


def test_toast_cleared():
    result = toast_cleared(42)
    assert "42" in result
    assert "초기화됨" in result


def test_toast_intercept_placeholder():
    result = toast_intercept_placeholder()
    assert "v0.4" in result
    assert "인터셉트" in result


def test_confirm_clear():
    result = confirm_clear(100)
    assert "100" in result
    assert "[y/N]" in result


def test_confirm_mock_delete():
    result = confirm_mock_delete("my-mock")
    assert "my-mock" in result
    assert "[y/N]" in result


def test_info_bar_without_mcp():
    result = info_bar("192.168.0.56", False)
    assert "192.168.0.56" in result
    assert "MCP" not in result


def test_info_bar_with_mcp():
    result = info_bar("192.168.0.56", True)
    assert "192.168.0.56" in result
    assert "MCP" in result
    assert "Claude" in result


def test_header_text():
    result = header_text("~/.troxy/flows.db", 1247)
    assert "~/.troxy/flows.db" in result
    assert "1,247" in result
    assert "개 flow" in result


def test_header_text_zero():
    result = header_text("/tmp/test.db", 0)
    assert "0개 flow" in result
