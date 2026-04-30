"""Tests for external_editor helpers."""

import pytest


# ---------- resolve_editor ----------

def test_resolve_editor_visual_env(monkeypatch):
    monkeypatch.setenv("VISUAL", "nvim")
    monkeypatch.setenv("EDITOR", "emacs")
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "nvim" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "nvim"


def test_resolve_editor_falls_back_to_editor_env(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}" if cmd == "vim" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "vim"


def test_resolve_editor_falls_back_to_nano(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "nano"


def test_resolve_editor_falls_back_to_vi(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/vi" if cmd == "vi" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "vi"


def test_resolve_editor_returns_none_when_all_missing(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() is None


# ---------- ext_for_content_type ----------

def test_ext_for_json():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("application/json") == ".json"


def test_ext_for_json_with_charset():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("application/json; charset=utf-8") == ".json"


def test_ext_for_xml():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("application/xml") == ".xml"


def test_ext_for_html():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("text/html") == ".html"


def test_ext_for_plain_text():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type("text/plain") == ".txt"


def test_ext_for_none():
    from troxy.tui.external_editor import ext_for_content_type
    assert ext_for_content_type(None) == ".txt"


# ---------- prettify_body ----------

def test_prettify_body_json_indents():
    from troxy.tui.external_editor import prettify_body
    result = prettify_body('{"a":1}', "application/json")
    assert result == '{\n  "a": 1\n}'


def test_prettify_body_invalid_json_returns_raw():
    from troxy.tui.external_editor import prettify_body
    raw = "{bad json}"
    assert prettify_body(raw, "application/json") == raw


def test_prettify_body_non_json_returns_raw():
    from troxy.tui.external_editor import prettify_body
    raw = "hello world"
    assert prettify_body(raw, "text/plain") == raw


def test_prettify_body_empty_returns_empty():
    from troxy.tui.external_editor import prettify_body
    assert prettify_body("", "application/json") == ""


def test_prettify_body_none_content_type():
    from troxy.tui.external_editor import prettify_body
    raw = '{"a":1}'
    assert prettify_body(raw, None) == raw


# ---------- validate_json_body ----------

def test_validate_json_valid():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body('{"a": 1}')
    assert ok is True
    assert msg == ""


def test_validate_json_empty_body():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body("")
    assert ok is True
    assert msg == ""


def test_validate_json_whitespace_only():
    from troxy.tui.external_editor import validate_json_body
    ok, _ = validate_json_body("   \n  ")
    assert ok is True


def test_validate_json_invalid_reports_line_col():
    from troxy.tui.external_editor import validate_json_body
    ok, msg = validate_json_body("{bad}")
    assert ok is False
    assert "1행" in msg
    assert "열" in msg


def test_validate_json_multiline_error_line_number():
    from troxy.tui.external_editor import validate_json_body
    body = '{\n  "a": 1,\n  bad\n}'
    ok, msg = validate_json_body(body)
    assert ok is False
    assert "3행" in msg
