"""Tests for troxy.tui.theme — color palette and style constants."""

from troxy.tui.theme import status_color, status_icon, method_color


def test_status_color_2xx():
    assert status_color(200) == "green"
    assert status_color(204) == "green"


def test_status_color_3xx():
    assert status_color(301) == "blue"
    assert status_color(304) == "blue"


def test_status_color_4xx():
    assert status_color(401) == "yellow"
    assert status_color(404) == "yellow"


def test_status_color_5xx():
    assert status_color(500) == "red"
    assert status_color(503) == "red"


def test_status_color_unknown():
    assert status_color(100) == "white"
    assert status_color(999) == "white"


def test_status_icon_2xx():
    assert status_icon(200) == "\u2713"


def test_status_icon_3xx():
    assert status_icon(301) == "\u2014"


def test_status_icon_4xx():
    assert status_icon(404) == "\u26a0"


def test_status_icon_5xx():
    assert status_icon(503) == "\U0001f525"


def test_status_icon_unknown():
    assert status_icon(100) == ""


def test_method_color_get():
    assert method_color("GET") == "green"


def test_method_color_post():
    assert method_color("POST") == "blue"


def test_method_color_put():
    assert method_color("PUT") == "#ff8800"


def test_method_color_delete():
    assert method_color("DELETE") == "red"


def test_method_color_patch():
    assert method_color("PATCH") == "cyan"


def test_method_color_head():
    assert method_color("HEAD") == "dim"


def test_method_color_case_insensitive():
    assert method_color("get") == "green"
    assert method_color("post") == "blue"
    assert method_color("delete") == "red"


def test_method_color_unknown():
    assert method_color("CONNECT") == "white"
