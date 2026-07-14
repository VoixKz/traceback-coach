# tests/test_hermes_memory.py
from __future__ import annotations

import pytest

from traceback_coach.hermes_memory import HermesMemory


@pytest.fixture
def mem(tmp_path):
    return HermesMemory(store_path=str(tmp_path / "traceback_coach_history.md"))


def test_record_creates_file_and_counts(mem):
    mem.record("IndexError", "2026-07-14")
    mem.record("IndexError", "2026-07-15")
    s = mem.summary()
    assert s["IndexError"]["seen"] == 2
    assert s["IndexError"]["fixed"] == 0
    assert s["IndexError"]["last"] == "2026-07-15"


def test_record_fixed_increments_only_existing(mem):
    mem.record("NameError", "2026-07-14")
    mem.record_fixed("NameError")
    mem.record_fixed("KeyError")  # unknown family: no-op, no crash
    s = mem.summary()
    assert s["NameError"]["fixed"] == 1
    assert "KeyError" not in s


def test_summary_round_trips_via_disk(tmp_path):
    p = str(tmp_path / "traceback_coach_history.md")
    HermesMemory(store_path=p).record("ValueError", "2026-07-14")
    # a fresh instance reads what the first one wrote
    assert HermesMemory(store_path=p).summary()["ValueError"]["seen"] == 1


def test_corrupt_file_reads_as_empty(tmp_path):
    p = tmp_path / "traceback_coach_history.md"
    p.write_text("total garbage, not our format\n", encoding="utf-8")
    assert HermesMemory(store_path=str(p)).summary() == {}


def test_top_weakness(mem):
    mem.record("IndexError", "2026-07-14")
    mem.record("IndexError", "2026-07-14")
    mem.record("NameError", "2026-07-14")
    assert mem.top_weakness() == ("IndexError", 2)


def test_top_weakness_empty_is_none(mem):
    assert mem.top_weakness() is None


def test_forget_deletes_the_file(mem, tmp_path):
    mem.record("IndexError", "2026-07-14")
    mem.forget()
    assert mem.summary() == {}
    assert not (tmp_path / "traceback_coach_history.md").exists()
