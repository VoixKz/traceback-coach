from __future__ import annotations

from traceback_coach._core import make_question, ParsedError, Frame
from traceback_coach.knowledge import lookup


def _p():
    return ParsedError("NameError", "name 'total' is not defined", 2,
                       "print(total)", "total", [Frame("<cell>", 2, "print(total)")])


def test_falls_back_to_template_when_llm_empty():
    q = make_question(_p(), lookup("NameError"), "print(total)", llm=lambda p, s: "")
    assert q == "Where in your code does `total` first get a value?"


def test_uses_llm_question_when_present():
    q = make_question(_p(), lookup("NameError"), "print(total)",
                      llm=lambda p, s: "What line defines total?")
    assert q == "What line defines total?"


def test_llm_exception_falls_back_to_template():
    def boom(p, s):
        raise RuntimeError("network down")

    q = make_question(_p(), lookup("NameError"), "print(total)", llm=boom)
    assert "total" in q  # template used, no crash


def test_llm_question_returns_empty_without_api_key(monkeypatch):
    from traceback_coach import _core
    for var in ("TRACEBACK_COACH_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert _core.llm_question(_p(), "print(total)") == ""


def test_make_question_does_not_double_call_on_internal_typeerror():
    # A 3-arg llm that raises TypeError internally must be called ONCE and fall
    # back to the template — not retried as if it had the wrong arity.
    calls = {"n": 0}

    def boom(parsed, cell_source, lang="en"):
        calls["n"] += 1
        raise TypeError("internal boom")

    q = make_question(_p(), lookup("NameError"), "print(total)\n", llm=boom)
    assert calls["n"] == 1          # called exactly once, no retry
    assert "total" in q             # fell back to the template
