"""Tests for body format parsers."""

import base64

from troxy.core.formats import parse_form_body


def test_parse_simple_form():
    result = parse_form_body("a=1&b=2")
    assert result == {"fields": {"a": "1", "b": "2"}, "truncated": False}


def test_parse_url_decodes_values():
    result = parse_form_body("ticket_type=Ticket%3A%3ATall")
    assert result["fields"]["ticket_type"] == "Ticket::Tall"
    assert result["truncated"] is False


def test_empty_body_returns_empty_fields():
    assert parse_form_body("") == {"fields": {}, "truncated": False}
    assert parse_form_body(None) == {"fields": {}, "truncated": False}  # type: ignore[arg-type]


def test_blank_value_kept():
    result = parse_form_body("a=&b=2")
    assert result["fields"] == {"a": "", "b": "2"}


def test_long_base64_value_summarized():
    blob = base64.b64encode(b"x" * 500).decode("ascii")
    result = parse_form_body(f"receipt_data={blob}&ticket_type=Ticket%3A%3ATall")
    receipt = result["fields"]["receipt_data"]
    assert isinstance(receipt, dict)
    assert receipt["_kind"] == "binary-base64"
    assert receipt["len"] == len(blob)
    assert len(receipt["sha256"]) == 16
    assert receipt["preview"] == blob[:64]
    # Short value still raw.
    assert result["fields"]["ticket_type"] == "Ticket::Tall"


def test_long_non_base64_value_summarized_as_long_text():
    long_value = "héllo " * 200
    # parse_qsl will percent-decode, so feed it percent-encoded equivalent
    from urllib.parse import quote
    body = f"description={quote(long_value)}"
    result = parse_form_body(body)
    desc = result["fields"]["description"]
    assert isinstance(desc, dict)
    assert desc["_kind"] == "long-text"
    assert desc["len"] == len(long_value)


def test_truncation_marker_detected():
    body = "a=1&b=2\n[truncated at 1024B]"
    result = parse_form_body(body)
    assert result["fields"] == {"a": "1", "b": "2"}
    assert result["truncated"] is True


def test_summary_threshold_override():
    result = parse_form_body("a=" + "x" * 50, summary_threshold=10)
    a = result["fields"]["a"]
    assert isinstance(a, dict)
    assert a["len"] == 50


def test_duplicate_keys_keep_last():
    result = parse_form_body("a=1&a=2&a=3")
    assert result["fields"]["a"] == "3"
