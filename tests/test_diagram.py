from __future__ import annotations

from traceback_coach._core import (
    ParsedError, Frame, build_mermaid, build_fallback_diagram, _fill,
)
from traceback_coach.knowledge import lookup


def _name_error():
    return ParsedError(
        error_type="NameError",
        message="name 'total' is not defined",
        line_no=2,
        source_line="print(total)",
        token="total",
        frames=[Frame("<cell>", 2, "print(total)")],
    )


def test_fill_replaces_token_and_type():
    p = _name_error()
    out = _fill("name `{token}` in {error_type} on line {line_no}", p)
    assert out == "name `total` in NameError on line 2"


def test_mermaid_has_break_node_and_type():
    p = _name_error()
    body = build_mermaid(p, lookup("NameError"))
    assert body.startswith("graph TD")
    assert "💥" in body
    assert "NameError" in body
    assert "total" in body
    assert "style" in body  # red break node styling


def test_mermaid_escapes_double_quotes():
    p = _name_error()
    p.source_line = 'print("oops)'
    body = build_mermaid(p, lookup("NameError"))
    assert '"oops' not in body  # double quotes inside labels are neutralised


def test_fallback_is_html_with_boxes_and_arrow():
    p = _name_error()
    out = build_fallback_diagram(p, lookup("NameError"))
    assert "<div" in out and "&rarr;" in out
    assert "NameError" in out


def test_flat_cell_has_no_foreign_frame_nodes():
    # A flat cell (no user functions) must not leak the harness/exec frame
    # into the diagram as an intermediate "F0" node.
    import sys
    from traceback_coach._core import parse_traceback

    src = "xs = [1, 2, 3]\nprint(xs[5])\n"
    try:
        exec(compile(src, "<cell>", "exec"), {})
    except BaseException:
        p = parse_traceback(*sys.exc_info(), cell_source=src)
    body = build_mermaid(p, lookup("IndexError"))
    assert "F0[" not in body
