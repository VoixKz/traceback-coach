from __future__ import annotations

from traceback_coach._core import parse_traceback, ParsedError


def _capture(cell_source):
    """Exec cell_source, return (exc_type, exc_value, exc_tb)."""
    import sys
    try:
        exec(compile(cell_source, "<cell>", "exec"), {})
    except BaseException:
        return sys.exc_info()
    raise AssertionError("cell did not raise")


def test_name_error_token_and_line():
    src = "a = 1\nprint(total)\n"
    p = parse_traceback(*_capture(src), cell_source=src)
    assert isinstance(p, ParsedError)
    assert p.error_type == "NameError"
    assert p.token == "total"
    assert p.line_no == 2


def test_key_error_token():
    src = 'd = {"a": 1}\nprint(d["b"])\n'
    p = parse_traceback(*_capture(src), cell_source=src)
    assert p.error_type == "KeyError"
    assert p.token == "b"


def test_attribute_error_token():
    src = 'x = "hi"\nx.append("!")\n'
    p = parse_traceback(*_capture(src), cell_source=src)
    assert p.error_type == "AttributeError"
    assert p.token == "append"


def test_syntax_error_line_from_value():
    src = "if x == 1\n    print(x)\n"
    p = parse_traceback(*_capture(src), cell_source=src)
    assert p.error_type == "SyntaxError"
    assert p.line_no == 1


def test_unknown_token_is_empty_string():
    src = "print(10 / 0)\n"
    p = parse_traceback(*_capture(src), cell_source=src)
    assert p.error_type == "ZeroDivisionError"
    assert p.token == ""
    assert "0" in p.source_line
