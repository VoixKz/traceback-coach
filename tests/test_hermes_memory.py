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


def test_available_false_when_sdk_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "hermes_acp_sdk" or name.startswith("hermes_acp_sdk."):
            raise ImportError("no sdk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert HermesMemory().available() is False


def test_profile_store_path_uses_profile_home(monkeypatch, tmp_path):
    # Stub the SDK's ProfileManager so no real Hermes is needed.
    class FakePM:
        def __init__(self, *a, **k):
            pass

        def ensure_profile(self, name, clone_provider=False):
            return None

        def get_env(self, name):
            return {"HERMES_HOME": str(tmp_path / "profiles" / "app-traceback-coach")}

    import traceback_coach.hermes_memory as hm
    monkeypatch.setattr(hm, "_load_profile_manager", lambda command: FakePM())
    p = HermesMemory()._profile_store_path()
    assert p == tmp_path / "profiles" / "app-traceback-coach" / "traceback_coach_history.md"
