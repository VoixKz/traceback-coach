from __future__ import annotations

import re
import sys

from traceback_coach._core import (
    ParsedError, Frame, build_mermaid, build_fallback_diagram, _fill,
    _display_code, parse_traceback,
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
    # Updated: new design uses flowchart TD (supersedes old graph TD check)
    assert body.startswith("flowchart TD")
    assert "💥" in body
    assert "NameError" in body
    assert "total" in body
    assert "classDef cf_boom" in body  # styling via classDef (supersedes inline style)


def test_mermaid_escapes_double_quotes():
    p = _name_error()
    p.source_line = 'print("oops)'
    body = build_mermaid(p, lookup("NameError"))
    assert '"oops' not in body  # double quotes inside labels are neutralised


def test_fallback_is_html_with_boxes_and_arrow():
    p = _name_error()
    out = build_fallback_diagram(p, lookup("NameError"))
    assert "<div" in out and "&darr;" in out
    assert "NameError" in out


def test_fallback_shows_full_call_chain():
    frames = [
        Frame("run", 14, "return average_of(scores, [0, 1, 5])"),
        Frame("average_of", 8, "total += get_item(data, i)"),
        Frame("get_item", 2, "return data[i]"),  # break
    ]
    p = ParsedError("IndexError", "list index out of range", 2,
                    "return data[i]", "", frames)
    out = build_fallback_diagram(p, lookup("IndexError"))
    assert "run" in out and "average_of" in out and "get_item" in out
    assert "average_of(scores, [0, 1, 5])" in out  # the call that passed index 5


def test_mermaid_chain_nodes_include_code():
    frames = [
        Frame("run", 14, "return average_of(scores, [0, 1, 5])"),
        Frame("get_item", 2, "return data[i]"),  # break
    ]
    p = ParsedError("IndexError", "list index out of range", 2,
                    "return data[i]", "", frames)
    body = build_mermaid(p, lookup("IndexError"))
    assert "average_of(scores, [0, 1, 5])" in body  # code shown on the chain node


def test_deep_recursion_chain_is_collapsed():
    # Direct recursion: now rendered as a self-loop (supersedes old "xN" node approach).
    frames = [Frame("f", 2, "return f(n - 1)") for _ in range(50)]
    frames.append(Frame("f", 2, "return f(n - 1)"))  # the break frame
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return f(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    assert "calls itself" in body                  # self-loop label present
    assert body.count('["') < 8                    # node count stays small


def test_mutual_recursion_chain_is_capped():
    # Alternating frames now rendered as a cycle (supersedes old ellipsis approach).
    frames = []
    for i in range(40):
        if i % 2 == 0:
            frames.append(Frame("is_even", 2, "return is_odd(n - 1)"))
        else:
            frames.append(Frame("is_odd", 2, "return is_even(n - 1)"))
    frames.append(Frame("is_even", 2, "return is_odd(n - 1)"))  # break
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return is_odd(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    assert "loops back" in body
    # bounded regardless of 40 input frames: S + M0 + M1 + X = 4
    assert body.count('["') <= 6


def test_nested_call_chain_shows_each_function():
    # A short chain of distinct frames is shown in full.
    frames = [
        Frame("run", 14, "return average_of(scores, [0, 1, 5])"),
        Frame("average_of", 8, "total += get_item(data, i)"),
        Frame("get_item", 2, "return data[i]"),  # break
    ]
    p = ParsedError("IndexError", "list index out of range", 2,
                    "return data[i]", "", frames)
    body = build_mermaid(p, lookup("IndexError"))
    assert "run" in body and "average_of" in body


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


def test_direct_recursion_renders_self_loop():
    frames = [Frame("countdown", 2, "return countdown(n - 1)") for _ in range(2990)]
    frames.append(Frame("countdown", 2, "return countdown(n - 1)"))  # break
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return countdown(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    # Updated: new design uses dotted self-loop -. "..." .-> (supersedes solid -->|...|)
    assert re.search(r'(\w+)\s*-\.\s*"[^"]*"\s*\.->\s*\1', body), "expected a dotted self-loop edge"
    assert "calls itself" in body
    assert "💥" in body and "RecursionError" in body
    assert body.count('["') < 6   # compact, not thousands of nodes


def test_mutual_recursion_renders_cycle():
    frames = []
    for i in range(2000):
        frames.append(Frame("is_even", 2, "return is_odd(n - 1)") if i % 2 == 0
                       else Frame("is_odd", 4, "return is_even(n - 1)"))
    frames.append(Frame("is_even", 2, "return is_odd(n - 1)"))  # break
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return is_odd(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    assert "is_even" in body and "is_odd" in body
    assert "loops back" in body
    assert body.count('["') <= 6   # the cycle, not 2000 nodes


def test_non_recursive_chain_unchanged():
    # a normal 3-frame chain must still render linearly (no self-loop)
    frames = [Frame("run", 14, "return average_of(scores, [0,1,5])"),
              Frame("average_of", 8, "total += get_item(data, i)"),
              Frame("get_item", 2, "return data[i]")]
    p = ParsedError("IndexError", "list index out of range", 2,
                    "return data[i]", "", frames)
    body = build_mermaid(p, lookup("IndexError"))
    import re
    assert not re.search(r"(\w+)\s*-->\|[^|]*\|\s*\1", body)  # no self-loop
    assert "run" in body and "average_of" in body and "get_item" in body


def test_direct_recursion_with_entry_frame_self_loops():
    # A real traceback includes the cell entry frame before the recursive frames.
    frames = [Frame("your cell", 3, "countdown(5)")]
    frames += [Frame("countdown", 2, "return countdown(n - 1)") for _ in range(2990)]
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return countdown(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    # Updated: new design uses dotted self-loop (supersedes solid arrow check)
    assert re.search(r'(\w+)\s*-\.\s*"[^"]*"\s*\.->\s*\1', body), "expected a dotted self-loop"
    assert "calls itself" in body
    assert body.count('["') < 6


# ── NEW TESTS (RED → GREEN with diagram-polish) ─────────────────────────────

# (a) parse_traceback drops synthetic <genexpr> frames
def test_parse_traceback_drops_genexpr_frame():
    """A traceback passing through a <genexpr> frame must not include it in parsed.frames."""
    src = (
        "def average_of(data, indices):\n"
        "    return sum(data[i] for i in indices) / len(indices)\n"
        "average_of([1, 2], [0, 5])\n"
    )
    try:
        exec(compile(src, "<cell>", "exec"), {})
    except BaseException:
        p = parse_traceback(*sys.exc_info(), cell_source=src)
    locations = [f.location for f in p.frames]
    assert "<genexpr>" not in locations, f"genexpr leaked into frames: {locations}"


# (b) _display_code strips trailing comment, keeps # inside string, truncates >80
def test_display_code_strips_trailing_comment():
    result = _display_code("return average_of(scores, [0,1,5])   # index 5 doesn't exist")
    assert result == "return average_of(scores, [0,1,5])"


def test_display_code_preserves_hash_inside_string():
    result = _display_code('print("a # b")')
    assert result == 'print("a # b")'


def test_display_code_preserves_hash_inside_single_quoted_string():
    result = _display_code("x = 'key # value'  # strip this")
    assert result == "x = 'key # value'"


def test_display_code_truncates_long_lines():
    long_code = "result = " + "x" * 90
    result = _display_code(long_code)
    assert len(result) == 80
    assert result.endswith("…")


def test_display_code_leaves_short_lines_unchanged():
    code = "return data[i]"
    assert _display_code(code) == "return data[i]"


# (c) build_mermaid uses flowchart TD + classDef cf_ + ==>|breaks here|
def test_mermaid_uses_flowchart_td():
    p = _name_error()
    body = build_mermaid(p, lookup("NameError"))
    assert body.startswith("flowchart TD"), f"Expected 'flowchart TD', got: {body[:30]!r}"


def test_mermaid_has_classdef_cf_styles():
    p = _name_error()
    body = build_mermaid(p, lookup("NameError"))
    assert "classDef cf_start" in body
    assert "classDef cf_frame" in body or "classDef cf_break" in body
    assert "classDef cf_boom" in body


def test_mermaid_uses_arrow_breaks_here():
    """The edge into the boom node must use ==>|breaks here|."""
    frames = [
        Frame("run", 14, "return average_of(scores, [0, 1, 5])"),
        Frame("get_item", 2, "return data[i]"),
    ]
    p = ParsedError("IndexError", "list index out of range", 2, "return data[i]", "", frames)
    body = build_mermaid(p, lookup("IndexError"))
    assert "==>|breaks here|" in body, f"Missing '==>|breaks here|' in:\n{body}"


# (d) real code with < renders &lt; (not parens)
def test_mermaid_escapes_angle_brackets_in_label():
    frames = [
        Frame("check", 3, "if x < threshold:"),
        Frame("compute", 1, "return x > 0"),
    ]
    p = ParsedError("ValueError", "bad value", 1, "return x > 0", "", frames)
    body = build_mermaid(p, lookup("ValueError"))
    assert "&lt;" in body, "< should be HTML-escaped to &lt;"
    assert "&gt;" in body, "> should be HTML-escaped to &gt;"
    assert "(threshold)" not in body  # old paren replacement must NOT happen


# (e) direct recursion → dotted self-loop with -. "calls itself
def test_direct_recursion_dotted_self_loop():
    frames = [Frame("f", 2, "return f(n - 1)") for _ in range(50)]
    frames.append(Frame("f", 2, "return f(n - 1)"))
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return f(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    assert '-. "calls itself' in body, f"Expected dotted self-loop in:\n{body}"


# (f) 5-function mutual cycle: all 5 nodes + back-edge to first
def test_five_function_cycle_shows_all_nodes_and_back_edge():
    func_names = ["alpha", "beta", "gamma", "delta", "epsilon"]
    frames = []
    for _ in range(10):
        for name in func_names:
            frames.append(Frame(name, 2, f"return {name}()"))
    frames.append(Frame("alpha", 2, "return alpha()"))  # break frame
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return alpha()", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    for name in func_names:
        assert name in body, f"{name} missing from cycle diagram"
    # back-edge must target the FIRST cycle node (C0)
    assert '-. "loops back' in body, f"Missing back-edge in:\n{body}"
    # The first cycle node id (C0) must appear as the TARGET of the back-edge
    assert re.search(r'-\. "loops back[^"]*" \.->\s*C0', body), \
        f"Back-edge does not point to C0 in:\n{body}"


# (g) non-recursive chain: no self-loop, all functions present
def test_non_recursive_chain_no_self_loop_all_functions():
    frames = [
        Frame("run", 7, "return average_of(scores, [0, 1, 5])"),
        Frame("average_of", 4, "return sum(get_item(data, i) for i in indices) / len(indices)"),
        Frame("get_item", 2, "return data[i]"),
    ]
    p = ParsedError("IndexError", "list index out of range", 2, "return data[i]", "", frames)
    body = build_mermaid(p, lookup("IndexError"))
    assert not re.search(r"(\w+)\s*-+[.>]+[^-]*-+[.>]+\s*\1", body), "Unexpected self/cycle edge"
    assert "run" in body
    assert "average_of" in body
    assert "get_item" in body


# (h) genexpr node text absent from diagram built from frames including a <genexpr>
def test_diagram_excludes_genexpr_node_text():
    src = (
        "def average_of(data, indices):\n"
        "    return sum(data[i] for i in indices) / len(indices)\n"
        "average_of([1, 2], [0, 5])\n"
    )
    try:
        exec(compile(src, "<cell>", "exec"), {})
    except BaseException:
        p = parse_traceback(*sys.exc_info(), cell_source=src)
    body = build_mermaid(p, lookup("IndexError"))
    assert "genexpr" not in body.lower(), f"genexpr leaked into diagram:\n{body}"
