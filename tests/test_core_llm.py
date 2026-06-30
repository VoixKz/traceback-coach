from __future__ import annotations
from traceback_coach._core import llm_status


def test_llm_status_no_key(monkeypatch):
    for v in ("TRACEBACK_COACH_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    st = llm_status()
    assert st["key_present"] is False
    assert st["model"] and st["base_url"]


def test_llm_status_with_key(monkeypatch):
    monkeypatch.setenv("TRACEBACK_COACH_LLM_API_KEY", "sk-fake")
    monkeypatch.setenv("TRACEBACK_COACH_LLM_MODEL", "my-model")
    st = llm_status()
    assert st["key_present"] is True and st["model"] == "my-model"
