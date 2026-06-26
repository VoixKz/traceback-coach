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
