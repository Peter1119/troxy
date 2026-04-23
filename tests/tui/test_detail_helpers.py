"""Design-spec regression guards for DetailScreen helpers (b7bbc70 follow-up).

code-review mutation probe on b7bbc70 found that the four design-critical
decisions — query 32-char truncation, header 20-char key padding, header
80-char value fold, JSON Monokai theme — had zero test coverage: mutating
the constants (e.g., QUERY_PREVIEW_MAX = 9999) kept 10/10 existing tests
green, so a future refactor could silently undo the design.

Same class of bug as ef726d5's ``theme.METHOD_COLORS`` being defined but
never called; 7c81975 added the corresponding regression guard. These
tests apply that pattern to detail_helpers.

Each assertion below has a corresponding mutation probe recorded in the
commit message (mutate constant → this test FAILs).
"""

from rich.syntax import Syntax

from troxy.tui.detail_helpers import (
    HEADER_KEY_WIDTH,
    HEADER_VALUE_FOLD,
    QUERY_PREVIEW_MAX,
    body_renderable,
    fold_value,
    preview_query,
    render_headers,
)


# ---------- preview_query: pins QUERY_PREVIEW_MAX = 32 ----------

def test_preview_query_returns_as_is_under_limit():
    """Queries <= QUERY_PREVIEW_MAX pass through untouched."""
    assert preview_query("short=value") == "short=value"


def test_preview_query_truncates_over_limit():
    """Queries over the limit get `<first16>...(<bytes>b)` suffix with exact 16-char head."""
    long = "a" * 100
    result = preview_query(long)
    assert result.startswith("a" * 16)
    assert "...(100b)" in result
    assert len(result) < len(long)


def test_preview_query_limit_is_32():
    """QUERY_PREVIEW_MAX specifically tuned to 32 — truncation must kick in at 33 chars."""
    # Guards against QUERY_PREVIEW_MAX being bumped up (e.g., 9999), which
    # would silently disable query truncation.
    assert QUERY_PREVIEW_MAX == 32
    boundary_pass = "x" * 32
    boundary_trim = "x" * 33
    assert preview_query(boundary_pass) == boundary_pass
    assert preview_query(boundary_trim) != boundary_trim
    assert "..." in preview_query(boundary_trim)


# ---------- fold_value: pins HEADER_VALUE_FOLD = 80 ----------

def test_fold_value_returns_as_is_under_limit():
    """Short values render verbatim."""
    assert fold_value("short").plain == "short"


def test_fold_value_folds_over_limit():
    """Values > 80 chars get folded with byte-count + `y to copy` hint."""
    long = "x" * 100
    result = fold_value(long).plain
    assert "y to copy" in result
    assert "100b" in result
    assert len(result) < len(long)


def test_fold_value_limit_is_80():
    """HEADER_VALUE_FOLD tuned to 80 — fold must kick in at 81 chars."""
    # Guards HEADER_VALUE_FOLD against being widened (e.g., 99999), which
    # would silently disable the cookie/authorization fold behavior.
    assert HEADER_VALUE_FOLD == 80
    boundary_pass = "z" * 80
    boundary_fold = "z" * 81
    assert fold_value(boundary_pass).plain == boundary_pass
    assert "y to copy" in fold_value(boundary_fold).plain


# ---------- render_headers: pins HEADER_KEY_WIDTH = 20 ----------

def test_render_headers_pads_key_to_20_chars():
    """Keys are left-padded to HEADER_KEY_WIDTH for alignment."""
    out = render_headers({"host": "example.com"}).plain
    # Prefix is two leading spaces + 20-char padded key + two separator spaces.
    assert out.startswith("  host" + " " * (HEADER_KEY_WIDTH - len("host")) + "  ")
    assert "example.com" in out


def test_render_headers_width_is_20():
    """HEADER_KEY_WIDTH tuned to 20 — padding must produce exactly 20 chars."""
    # Guards HEADER_KEY_WIDTH against being narrowed (e.g., 2), which
    # would collapse the key column and destroy key/value visual hierarchy.
    assert HEADER_KEY_WIDTH == 20
    out = render_headers({"x": "v"}).plain
    # Key "x" padded to 20 chars → "x" + 19 spaces.
    assert "  x" + " " * 19 + "  v" in out


def test_render_headers_folds_long_value():
    """Long header values reuse fold_value (integration with HEADER_VALUE_FOLD)."""
    long = "a" * 120
    out = render_headers({"cookie": long}).plain
    assert "y to copy" in out
    assert "120b" in out


# ---------- body_renderable: pins Syntax theme = "monokai" ----------

def test_body_renderable_json_uses_monokai_theme():
    """JSON bodies render via rich.syntax.Syntax with Monokai theme."""
    # Guards against theme being swapped (e.g., "default", "ansi_light"),
    # which would break the key/string/number color distinction the user
    # explicitly called out in Round 3.
    result = body_renderable('{"ok": true}', "application/json")
    assert isinstance(result, Syntax)
    # rich stores the theme as a PygmentsSyntaxTheme wrapping a pygments
    # style class; the class name is "MonokaiStyle" for Monokai.
    style_class = result._theme._pygments_style_class
    assert "monokai" in style_class.__name__.lower()


def test_body_renderable_json_background_is_default():
    """JSON Syntax uses ``background_color="default"`` so the pane bg shows through."""
    result = body_renderable('{"ok": true}', "application/json")
    assert isinstance(result, Syntax)
    assert result.background_color == "default"
