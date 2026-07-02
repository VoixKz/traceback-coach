from __future__ import annotations

from traceback_coach._core import (
    parse_traceback, build_card, render_card_html, CardData, lesson_card,
)
from traceback_coach.knowledge import lookup


def _capture(src):
    import sys
    try:
        exec(compile(src, "<cell>", "exec"), {})
    except BaseException:
        return sys.exc_info()
    raise AssertionError("no raise")


def _name_card():
    src = "print(total)\n"
    return build_card(parse_traceback(*_capture(src), cell_source=src), src,
                      llm=lambda p, s: "")


def test_build_card_fields():
    src = "print(total)\n"
    card = build_card(parse_traceback(*_capture(src), cell_source=src), src,
                      llm=lambda p, s: "")
    assert isinstance(card, CardData)
    assert card.error_type == "NameError"
    assert "total" in card.translation
    assert card.question  # non-empty
    assert "append" not in card.example_code  # it's the NameError example


def test_render_contains_all_sections():
    src = "print(total)\n"
    card = build_card(parse_traceback(*_capture(src), cell_source=src), src,
                      llm=lambda p, s: "")
    html = render_card_html(card, diagram_id="tbc-x")
    assert "🧭 Coach" in html
    assert "What happened" in html
    assert 'class="mermaid"' in html
    assert "tbc-fallback" in html          # CSS fallback present
    assert "<details" in html              # collapsible worked example
    assert "Question:" in html
    assert card.question in html


def test_no_fix_field_exists():
    # Structural guarantee: CardData has no fix/solution/corrected field.
    forbidden = {"fix", "solution", "corrected", "answer"}
    assert forbidden.isdisjoint(set(CardData.__dataclass_fields__))


def test_lesson_card_for_known_family():
    card = lesson_card(lookup("IndexError"))
    assert card.error_type == "IndexError"
    assert card.example_code
    assert card.question


def test_mermaid_runtime_is_vendored():
    from traceback_coach._core import load_mermaid_js
    js = load_mermaid_js()
    assert js and "mermaid" in js.lower()


def test_brief_omits_diagram_and_example_keeps_question():
    html = render_card_html(_name_card(), diagram_id="b1", level="brief")
    assert 'class="mermaid"' not in html      # no diagram
    assert "<details" not in html              # no worked example
    assert "Question:" in html                 # still guides
    assert "NameError" in html


def test_min_is_one_line_type_plus_question():
    html = render_card_html(_name_card(), diagram_id="m1", level="min")
    assert "NameError" in html
    assert "Question:" in html
    assert 'class="mermaid"' not in html and "<details" not in html
    assert "What happened" not in html         # no full translation block


def test_full_is_unchanged_default():
    html = render_card_html(_name_card(), diagram_id="f1")  # default level
    assert 'class="mermaid"' in html and "<details" in html and "Question:" in html


def test_wrap_quiz_html_prompts_and_hides_card():
    from traceback_coach._core import wrap_quiz_html
    out = wrap_quiz_html("<div>INNER_CARD</div>", "NameError")
    assert "Guess first" in out
    assert "<details" in out and "Reveal" in out
    assert "INNER_CARD" in out          # the real card is inside the details (hidden)
    # interactive quiz: a dropdown of types, a Submit button, and the correct
    # answer are all present, wired by an inline script
    assert "<select" in out and "<option" in out
    assert "Submit" in out
    assert ">NameError<" in out          # the correct type is a selectable option
    assert "addEventListener" in out     # submit is wired
    # the answer is embedded for the check, but only inside the script / options
    assert "IndexError" in out           # distractor options are present too


def test_wrap_quiz_html_answer_matches_error_type():
    from traceback_coach._core import wrap_quiz_html
    out = wrap_quiz_html("<div>C</div>", "ZeroDivisionError", quiz_id="q9")
    # the embedded JS answer must be the actual error type
    assert 'var ans="ZeroDivisionError"' in out
    assert 'id="q9-sel"' in out and 'id="q9-btn"' in out and 'id="q9-card"' in out


# ---------------------------------------------------------------------------
# Task 2: lang threading tests
# ---------------------------------------------------------------------------

def _zh_card():
    src = "print(total)\n"
    from traceback_coach._core import build_card, parse_traceback
    return build_card(parse_traceback(*_capture(src), cell_source=src), src,
                      llm=lambda p, s: "", lang="zh")


def test_zh_card_renders_chinese_labels():
    from traceback_coach._core import render_card_html
    html = render_card_html(_zh_card(), diagram_id="z1", lang="zh")
    assert any("一" <= ch <= "鿿" for ch in html)   # has Han characters
    assert "Question:" not in html                          # en label replaced
