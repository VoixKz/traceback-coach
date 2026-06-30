from __future__ import annotations

from traceback_coach._core import fade_level, render_stats_html


def test_auto_fades_with_repetition():
    assert fade_level(1, "auto") == "full"
    assert fade_level(2, "auto") == "brief"
    assert fade_level(3, "auto") == "min"
    assert fade_level(9, "auto") == "min"


def test_override_wins():
    assert fade_level(1, "min") == "min"
    assert fade_level(99, "full") == "full"
    assert fade_level(2, "brief") == "brief"


def test_unknown_override_falls_back_to_auto():
    assert fade_level(1, "bogus") == "full"
    assert fade_level(3, "bogus") == "min"


def test_stats_html_empty():
    out = render_stats_html({})
    assert "no errors yet" in out.lower()


def test_stats_html_sorted_with_top_and_total():
    out = render_stats_html({"NameError": 1, "IndexError": 3, "TypeError": 2})
    # most common highlighted + a lesson tip + total
    assert "IndexError" in out and "NameError" in out and "TypeError" in out
    assert "%coach_lesson IndexError" in out      # top family suggested
    assert "6" in out                              # total occurrences
    # IndexError row appears before NameError row (sorted desc)
    assert out.index("IndexError") < out.index("NameError")
