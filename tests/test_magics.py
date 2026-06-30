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
    M._state.stats = {}
    M._state.level_override = "auto"
    M._state._last_analysis = 0.0
    M._state.quiz = False
    M._state.lang = "en"
    M._state.compact = False
    # Ensure the compact exc handler is not installed at the start of each test.
    shell.set_custom_exc((), None)
    # Disable debounce in tests so rapid back-to-back run_cell calls all go through.
    monkeypatch.setattr(M._state, "should_analyze", lambda: True)
    traceback_coach.load_ipython_extension(shell)
    shell._tbc_captured = captured
    yield shell
    # Teardown: restore default exc handler if compact was left on by a test.
    if M._state.compact:
        shell.set_custom_exc((), None)
        M._state.compact = False
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


def test_repeated_error_fades_full_then_brief_then_min(ip):
    ip.run_line_magic("coach_watch", "on")
    htmls = []
    for _ in range(3):
        ip._tbc_captured.clear()
        ip.run_cell("print(missing_var)\n")
        htmls.append("".join(x for x in ip._tbc_captured if isinstance(x, str)))
    # 1st full (has diagram), 2nd brief (no diagram, no details), 3rd min
    assert 'class="mermaid"' in htmls[0]
    assert 'class="mermaid"' not in htmls[1] and "<details" not in htmls[1]
    assert "you've seen this one" in htmls[2]
    # every level still asks a question, never shows a fix
    assert all("Question:" in h for h in htmls)


def test_coach_level_override_forces_full(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_line_magic("coach_level", "full")
    for _ in range(3):
        ip._tbc_captured.clear()
        ip.run_cell("print(missing_var)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert 'class="mermaid"' in html      # forced full despite repetition


def test_coach_stats_shows_tally(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("print(a_undef)\n")
    ip.run_cell("xs = [1]; xs[9]\n")
    ip._tbc_captured.clear()
    ip.run_line_magic("coach_stats", "")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "NameError" in html and "IndexError" in html


def test_explain_does_not_double_count_stats(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("print(missing_var)\n")
    assert M._state.stats.get("NameError") == 1
    # re-explaining the SAME error must not inflate the tally or advance the fade
    ip.run_line_magic("coach_explain", "")
    assert M._state.stats.get("NameError") == 1


def test_coach_llm_status_no_key(ip, monkeypatch, capsys):
    for v in ("TRACEBACK_COACH_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    ip.run_line_magic("coach_llm", "")
    out = capsys.readouterr().out.lower()
    assert "not configured" in out or "offline" in out


def test_coach_llm_off_forces_template_question(ip):
    # With a fake LLM that returns a marker, 'off' must switch to templates.
    M._LLM = lambda p, s: "FAKE_LLM_QUESTION"
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("print(zzz_undef)\n")
    html_on = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "FAKE_LLM_QUESTION" in html_on          # LLM used while on
    ip.run_line_magic("coach_llm", "off")
    ip._tbc_captured.clear()
    ip.run_cell("print(zzz_undef)\n")
    html_off = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "FAKE_LLM_QUESTION" not in html_off      # template after off


def test_quiz_mode_wraps_card_in_guess_prompt(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_line_magic("coach_quiz", "on")
    ip.run_cell("print(qz_undef)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "Guess first" in html and "<details" in html
    assert "NameError" in html          # the card is still there, inside details


def test_quiz_off_is_normal_card(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("print(qz_undef)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "Guess first" not in html


# ---------------------------------------------------------------------------
# Task 2: lang threading tests
# ---------------------------------------------------------------------------

def test_coach_lang_zh_makes_chinese_cards(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_line_magic("coach_lang", "zh")
    ip.run_cell("print(zh_undef)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert any("一" <= ch <= "鿿" for ch in html)
    assert "NameError" in html        # error-type name stays English


def test_coach_lang_default_en(ip):
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("print(en_undef)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "What happened" in html or "Question:" in html   # English UI


# ---------------------------------------------------------------------------
# Task B: %coach_compact — fold the native traceback
# ---------------------------------------------------------------------------

def test_coach_compact_default_off(ip):
    """compact must be OFF by default — must not affect normal error display."""
    assert M._state.compact is False
    # A normal error must still surface (error_in_exec is not None)
    res = ip.run_cell("print(undef_compact_default)\n")
    assert res.error_in_exec is not None


def test_coach_compact_on_sets_state_and_registers_handler(ip):
    """Turning compact ON must flip _state.compact and register a custom exc handler."""
    assert M._state.compact is False
    ip.run_line_magic("coach_compact", "on")
    assert M._state.compact is True
    # IPython stores active custom exc tuples in shell.custom_exceptions
    assert ip.custom_exceptions != ()


def test_coach_compact_off_clears_state_and_restores_handler(ip):
    """Turning compact OFF must flip _state.compact back and restore the default handler."""
    ip.run_line_magic("coach_compact", "on")
    assert M._state.compact is True
    ip.run_line_magic("coach_compact", "off")
    assert M._state.compact is False
    # Default exc handler restored: custom_exceptions should be empty tuple
    assert ip.custom_exceptions == ()
    # A normal error must still surface after restoring
    res = ip.run_cell("print(undef_compact_off)\n")
    assert res.error_in_exec is not None


def test_coach_compact_status_reports_state(ip, capsys):
    """'status' sub-command must print the current compact state."""
    ip.run_line_magic("coach_compact", "status")
    out1 = capsys.readouterr().out
    assert "off" in out1.lower() or "compact" in out1.lower()
    ip.run_line_magic("coach_compact", "on")
    ip.run_line_magic("coach_compact", "status")
    out2 = capsys.readouterr().out
    assert "on" in out2.lower() or "compact" in out2.lower()


def test_coach_compact_on_folds_output(ip, capsys):
    """When compact is ON, the custom handler prints a folded note."""
    ip.run_line_magic("coach_compact", "on")
    # Trigger a NameError (simpler than RecursionError, but same handler path)
    ip.run_cell("print(undefined_var_compact)\n")
    out = capsys.readouterr().out + capsys.readouterr().err
    # The compact summary note must appear
    assert "folded" in out.lower() or "compact" in out.lower() or "Coach" in out


def test_coach_compact_idempotent_double_on(ip):
    """Calling 'on' twice must not crash and must still be reversible."""
    ip.run_line_magic("coach_compact", "on")
    ip.run_line_magic("coach_compact", "on")  # second call — must not raise
    assert M._state.compact is True
    ip.run_line_magic("coach_compact", "off")
    assert M._state.compact is False
    assert ip.custom_exceptions == ()


def test_coach_compact_banner_and_help_mention_compact(ip, capsys):
    """BANNER and HELP strings must reference %coach_compact."""
    assert "coach_compact" in M.BANNER
    assert "coach_compact" in M.HELP


def test_unregister_with_compact_on_restores_handler(ip):
    """unregister() while compact is on must still restore the default exc handler."""
    import traceback_coach
    ip.run_line_magic("coach_compact", "on")
    assert ip.custom_exceptions != ()
    traceback_coach.unload_ipython_extension(ip)
    assert ip.custom_exceptions == ()
    # Re-register so the ip fixture's own teardown doesn't crash
    traceback_coach.load_ipython_extension(ip)
