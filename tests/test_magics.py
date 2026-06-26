from __future__ import annotations

import pytest

IPython = pytest.importorskip("IPython")
from IPython.core.interactiveshell import InteractiveShell

import traceback_coach
from traceback_coach import magics as M


@pytest.fixture
def ip(monkeypatch):
    shell = InteractiveShell.instance()
    captured = []
    # Capture anything the coach displays, headless.
    monkeypatch.setattr(M, "display", lambda obj: captured.append(obj))
    monkeypatch.setattr(M, "HTML", lambda s: s)  # HTML(x) -> x (str)
    # Never call a real LLM in tests.
    monkeypatch.setattr(M, "_LLM", lambda p, s: "")
    # Clean module-global coach state for test isolation.
    M._state.last_error = None
    M._state.watch = False
    M._state.pending_fix = False
    traceback_coach.load_ipython_extension(shell)
    shell._tbc_captured = captured
    yield shell
    traceback_coach.unload_ipython_extension(shell)
    InteractiveShell.clear_instance()


def test_coach_cell_magic_shows_card_on_error(ip):
    ip._tbc_captured.clear()
    ip.run_cell_magic("coach", "", "print(total)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "🧭 Coach" in html
    assert "NameError" in html


def test_coach_lesson_shows_example(ip):
    ip._tbc_captured.clear()
    ip.run_line_magic("coach_lesson", "IndexError")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "IndexError" in html
    assert "example" in html.lower()


def test_watch_then_fix_celebrates(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("print(missing)\n")      # errors -> card + pending_fix
    ip._tbc_captured.clear()
    ip.run_cell("print('ok')\n")          # clean -> celebrate
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "Fixed it" in html


def test_explain_without_error_is_graceful(ip, capsys):
    ip._tbc_captured.clear()
    ip.run_line_magic("coach_explain", "")
    out = capsys.readouterr().out
    assert "no error" in out.lower() or ip._tbc_captured == []
