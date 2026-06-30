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
    assert body.count('["') <= 9


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
    # a node that loops to ITSELF (same id on both ends of an edge)
    import re
    assert re.search(r"(\w+)\s*-->\|[^|]*\|\s*\1", body), "expected a self-loop edge"
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
