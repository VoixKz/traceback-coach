from __future__ import annotations

import pytest

from traceback_coach.knowledge import ErrorFamily, FAMILIES, lookup

EXPECTED = {
    "NameError", "TypeError", "ValueError", "IndexError", "KeyError",
    "AttributeError", "IndentationError", "SyntaxError", "ZeroDivisionError",
    "ModuleNotFoundError", "RecursionError", "UnboundLocalError",
}


def test_twelve_families_present():
    assert EXPECTED.issubset(FAMILIES.keys())


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_every_family_fully_populated(key):
    fam = FAMILIES[key]
    assert isinstance(fam, ErrorFamily)
    for field in (
        fam.translation, fam.family_summary, fam.read_it_yourself,
        fam.cause_phrase, fam.example_code, fam.example_explanation,
        fam.example_avoid, fam.question_template,
    ):
        assert field and field.strip()


def test_lookup_known():
    assert lookup("IndexError").key == "IndexError"


def test_lookup_unknown_returns_generic():
    fam = lookup("SomeNeverSeenError")
    assert fam.key == "Error"
    assert fam.question_template.strip()
