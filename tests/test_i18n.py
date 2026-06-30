from __future__ import annotations
import pytest
from traceback_coach.knowledge import FAMILIES, lookup
from traceback_coach.i18n import FAMILIES_ZH, LABELS

KEYS = sorted(FAMILIES.keys())

def test_zh_has_all_families():
    assert set(FAMILIES_ZH) >= set(FAMILIES)

@pytest.mark.parametrize("k", KEYS)
def test_zh_fields_translated_and_nonempty(k):
    en, zh = FAMILIES[k], FAMILIES_ZH[k]
    assert zh.key == en.key
    assert zh.example_code == en.example_code            # code not translated
    for field in ("translation","family_summary","read_it_yourself",
                  "cause_phrase","example_explanation","example_avoid","question_template"):
        ztext = getattr(zh, field)
        assert ztext and ztext.strip()
        assert ztext != getattr(en, field)               # actually translated
        assert any("一" <= ch <= "鿿" for ch in ztext)   # contains Han characters

def test_lookup_lang():
    assert lookup("NameError").key == "NameError"                 # en default
    assert lookup("NameError", "zh") is FAMILIES_ZH["NameError"]
    assert lookup("NameError", "en") is FAMILIES["NameError"]
    # unknown type still returns a generic family in both langs
    assert lookup("WeirdError", "zh").question_template.strip()

def test_labels_have_both_langs():
    need = {"coach","what_happened","why_breaks","where","family_read",
            "see_example","avoid_next","question","seen_min","guess_first","reveal","fixed_it"}
    assert need <= set(LABELS["en"]) and need <= set(LABELS["zh"])
    for k in need:
        assert LABELS["en"][k].strip() and LABELS["zh"][k].strip()
        assert any("一" <= ch <= "鿿" for ch in LABELS["zh"][k])
