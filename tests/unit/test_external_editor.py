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
