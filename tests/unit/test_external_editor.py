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


def test_resolve_editor_multi_word_editor_env(monkeypatch):
    """EDITOR='code --wait' → which('code') 성공이면 전체 문자열 반환."""
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "code --wait")
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/code" if cmd == "code" else None)
    from troxy.tui.external_editor import resolve_editor
    assert resolve_editor() == "code --wait"


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


# ---------- open_in_editor ----------

import os
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_app():
    """Minimal App mock exposing an async suspend() context manager."""
    app = MagicMock()

    @asynccontextmanager
    async def _suspend():
        yield

    app.suspend = _suspend
    return app


@pytest.mark.asyncio
async def test_open_in_editor_returns_edited_content(monkeypatch, mock_app):
    """Editor writes new content → function returns that content."""
    def fake_run(cmd, **kwargs):
        with open(cmd[1], "w") as f:
            f.write("edited body")
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor
    result = await open_in_editor("original", "application/json", mock_app)
    assert result == "edited body"


@pytest.mark.asyncio
async def test_open_in_editor_raises_when_no_editor(monkeypatch, mock_app):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    from troxy.tui.external_editor import open_in_editor, EditorNotFoundError
    with pytest.raises(EditorNotFoundError):
        await open_in_editor("body", None, mock_app)


@pytest.mark.asyncio
async def test_open_in_editor_raises_cancelled_on_nonzero_exit(monkeypatch, mock_app):
    """returncode != 0 → EditorCancelledError (user quit without saving)."""
    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 1
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor, EditorCancelledError
    with pytest.raises(EditorCancelledError):
        await open_in_editor("body", None, mock_app)


@pytest.mark.asyncio
async def test_open_in_editor_deletes_temp_file(monkeypatch, mock_app):
    """Temp file must be deleted regardless of editor outcome."""
    captured_path: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_path.append(cmd[1])
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor
    await open_in_editor("body", "application/json", mock_app)

    assert captured_path, "subprocess.run was not called"
    assert not os.path.exists(captured_path[0]), "temp file was not deleted"


@pytest.mark.asyncio
async def test_open_in_editor_deletes_temp_file_even_on_cancel(monkeypatch, mock_app):
    """Temp file must be deleted even when editor exits with error."""
    captured_path: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_path.append(cmd[-1])
        result = MagicMock()
        result.returncode = 1
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor, EditorCancelledError
    with pytest.raises(EditorCancelledError):
        await open_in_editor("body", None, mock_app)

    assert captured_path
    assert not os.path.exists(captured_path[0]), "temp file leaked on cancel"


@pytest.mark.asyncio
async def test_open_in_editor_write_failure_no_temp_file_leak(monkeypatch, mock_app):
    """f.write(body) 실패 시에도 임시파일이 삭제돼야 한다 (보안)."""
    import tempfile as _tempfile
    created_path: list[str] = []

    original_ntf = _tempfile.NamedTemporaryFile

    def patched_ntf(**kwargs):
        f = original_ntf(**kwargs)
        created_path.append(f.name)

        class _FailingWrite:
            name = f.name
            def write(self, data):
                raise OSError("disk full")
            def __enter__(self):
                return self
            def __exit__(self, *a):
                f.__exit__(*a)

        return _FailingWrite()

    monkeypatch.setattr("tempfile.NamedTemporaryFile", patched_ntf)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/nano" if cmd == "nano" else None)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    from troxy.tui.external_editor import open_in_editor, EditorIOError
    with pytest.raises(EditorIOError):
        await open_in_editor("body", None, mock_app)

    assert created_path, "NamedTemporaryFile was not called"
    assert not os.path.exists(created_path[0]), "temp file leaked after write failure"


@pytest.mark.asyncio
async def test_open_in_editor_multi_word_editor_passes_args(monkeypatch, mock_app):
    """EDITOR='code --wait' → subprocess.run(['code', '--wait', tmp_path]) 형태로 호출."""
    received_cmd: list[list] = []

    def fake_run(cmd, **kwargs):
        received_cmd.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setenv("EDITOR", "code --wait")
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/code" if cmd == "code" else None)
    monkeypatch.setattr("subprocess.run", fake_run)

    from troxy.tui.external_editor import open_in_editor
    await open_in_editor("body", None, mock_app)

    assert received_cmd, "subprocess.run was not called"
    cmd = received_cmd[0]
    assert cmd[0] == "code"
    assert cmd[1] == "--wait"
    assert cmd[2].endswith(".txt")  # tmp file path
