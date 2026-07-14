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
    M._state.quiz = False
    M._state.lang = "en"
    M._state.compact = False
    # Ensure no custom exc handler is installed at the start of each test.
    shell.set_custom_exc((), None)
    traceback_coach.load_ipython_extension(shell)
    shell._tbc_captured = captured
    yield shell
    # Teardown: restore default exc handler if quiz/compact was left on by a test.
    if M._state.compact or M._state.quiz:
        shell.set_custom_exc((), None)
        M._state.compact = False
        M._state.quiz = False
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


def test_coach_compact_collapses_traceback(ip):
    """When compact is ON, the custom handler renders the full traceback in a collapsible <details>."""
    ip.run_line_magic("coach_compact", "on")
    ip._tbc_captured.clear()
    ip.run_cell("def f(n):\n    return f(n - 1)\nf(3)\n")   # RecursionError
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "<details" in html and "click to expand" in html   # collapsible
    assert "RecursionError" in html                            # summary names the error
    assert "<pre" in html                                       # full traceback inside


def test_coach_compact_escapes_html_in_message(ip):
    """A message containing <, >, & must be HTML-escaped, not injected raw."""
    ip.run_line_magic("coach_compact", "on")
    ip._tbc_captured.clear()
    ip.run_cell("raise ValueError('bad <tag> & \"quote\" here')\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    # the special chars appear escaped in the summary, never as a raw tag
    assert "&lt;tag&gt;" in html
    assert "<tag>" not in html
    assert "&amp;" in html


def test_coach_compact_coach_card_untouched(ip):
    """With compact ON, a %%coach cell still produces the Coach card (OUR output is untouched)."""
    ip.run_line_magic("coach_compact", "on")
    ip._tbc_captured.clear()
    ip.run_cell_magic("coach", "", "print(compact_undef_var)\n")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "🧭 Coach" in html   # Coach card is still rendered


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


# ---------------------------------------------------------------------------
# Skip bug: consecutive errors were dropped by a time debounce; now deduped
# by exception identity instead.
# ---------------------------------------------------------------------------

def test_watch_explains_consecutive_distinct_errors(ip):
    """Two DIFFERENT errors run back-to-back must BOTH get a card (no skip)."""
    ip.run_line_magic("coach_watch", "on")
    ip._tbc_captured.clear()
    ip.run_cell("[][0]\n")            # IndexError
    ip.run_cell("{}['missing']\n")    # KeyError
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "IndexError" in html
    assert "KeyError" in html


def test_coach_magic_with_watch_shows_card_once(ip):
    """`%%coach` while watching must not double-explain the same exception."""
    ip.run_line_magic("coach_watch", "on")
    ip._tbc_captured.clear()
    ip.run_cell_magic("coach", "", "undef_double_var + 1\n")   # NameError
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert html.count("🧭 Coach") == 1


def test_coach_explain_reexplains_same_error(ip):
    """%coach_explain must re-render the last error even though it's the same
    exception object (force bypasses the identity dedup)."""
    ip.run_line_magic("coach_watch", "on")
    ip.run_cell("undef_explain_var\n")   # NameError -> analyzed, last_error set
    ip._tbc_captured.clear()
    ip.run_line_magic("coach_explain", "")
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "🧭 Coach" in html


# ---------------------------------------------------------------------------
# Quiz bug: the error type leaked via the traceback before "reveal". Quiz mode
# now folds the traceback with the type redacted from the visible summary.
# ---------------------------------------------------------------------------

def test_coach_quiz_hides_error_type_until_expand(ip):
    """With quiz ON, the type must NOT appear in the visible <summary>, only in
    the collapsed body (revealed on expand)."""
    import re
    ip.run_line_magic("coach_quiz", "on")
    ip._tbc_captured.clear()
    ip.run_cell("undefined_quiz_var + 1\n")   # NameError
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    m = re.search(r"<summary[^>]*>(.*?)</summary>", html, re.S)
    assert m, "expected a collapsed <details> summary while quiz is on"
    assert "NameError" not in m.group(1)       # type hidden in the visible summary
    assert "NameError" in html                 # but present in the hidden body


def test_quiz_card_has_dropdown_submit_and_answer(ip):
    """With quiz + watch on, the card is wrapped with an interactive dropdown +
    Submit that checks the guess before revealing the analysis."""
    ip.run_line_magic("coach_watch", "on")
    ip.run_line_magic("coach_quiz", "on")
    ip._tbc_captured.clear()
    ip.run_cell("undefined_quiz_pick\n")   # NameError
    html = "".join(x for x in ip._tbc_captured if isinstance(x, str))
    assert "<select" in html and "<option" in html   # dropdown of types
    assert "<input" in html                            # free-text field for other types
    assert "Submit" in html                            # submit button
    assert "addEventListener" in html                  # checked client-side
    assert 'var ans="NameError"' in html               # correct answer embedded for the check
    assert ">IndexError<" in html                      # distractors present


def test_coach_quiz_syncs_exc_handler(ip):
    """quiz on installs a custom exc handler; quiz off restores the default."""
    assert ip.custom_exceptions == ()
    ip.run_line_magic("coach_quiz", "on")
    assert ip.custom_exceptions != ()
    ip.run_line_magic("coach_quiz", "off")
    assert ip.custom_exceptions == ()


def test_quiz_and_compact_share_handler(ip):
    """With both on, turning one off keeps the handler while the other is on."""
    ip.run_line_magic("coach_quiz", "on")
    ip.run_line_magic("coach_compact", "on")
    assert ip.custom_exceptions != ()
    ip.run_line_magic("coach_quiz", "off")
    assert ip.custom_exceptions != ()          # compact still on
    ip.run_line_magic("coach_compact", "off")
    assert ip.custom_exceptions == ()


def test_unregister_with_compact_on_restores_handler(ip):
    """unregister() while compact is on must still restore the default exc handler."""
    import traceback_coach
    ip.run_line_magic("coach_compact", "on")
    assert ip.custom_exceptions != ()
    traceback_coach.unload_ipython_extension(ip)
    assert ip.custom_exceptions == ()
    # Re-register so the ip fixture's own teardown doesn't crash
    traceback_coach.load_ipython_extension(ip)


# ---------------------------------------------------------------------------
# Task 5: Hermes-profile memory wired into the magics layer
# ---------------------------------------------------------------------------

import datetime

import traceback_coach.magics as magics
from traceback_coach.hermes_memory import HermesMemory


class _FakeMem:
    def __init__(self):
        self.recorded = []
        self.fixed = []
        self._summary = {}
        self.forgotten = False

    def available(self):
        return True

    def record(self, et, when):
        self.recorded.append((et, when))
        self._summary.setdefault(et, {"seen": 0, "fixed": 0, "last": when})
        self._summary[et]["seen"] += 1

    def record_fixed(self, et):
        self.fixed.append(et)

    def summary(self):
        return self._summary

    def reflect(self, lang="en"):
        return "REFLECTION TEXT"

    def forget(self):
        self.forgotten = True


def test_analyze_records_into_memory_when_on(monkeypatch):
    fake = _FakeMem()
    monkeypatch.setattr(magics._state, "memory", fake, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", True, raising=False)
    monkeypatch.setattr(magics._state, "last_error", None, raising=False)
    monkeypatch.setattr(magics, "display", lambda *a, **k: None)
    try:
        [][5]
    except IndexError as e:
        magics._analyze_and_show(type(e), e, e.__traceback__, "[][5]")
    assert fake.recorded and fake.recorded[0][0] == "IndexError"


def test_memory_off_does_not_record(monkeypatch):
    fake = _FakeMem()
    monkeypatch.setattr(magics._state, "memory", fake, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", False, raising=False)
    monkeypatch.setattr(magics._state, "last_error", None, raising=False)
    monkeypatch.setattr(magics, "display", lambda *a, **k: None)
    try:
        {}["x"]
    except KeyError as e:
        magics._analyze_and_show(type(e), e, e.__traceback__, '{}["x"]')
    assert fake.recorded == []


def test_chronic_line_absent_when_memory_off(monkeypatch):
    """Regression test for Fix 1: with memory OFF (the default), the chronic
    'you've hit X N times now' line must never appear, even after the same
    error family repeats 3x in one session — this is pre-feature behaviour
    and must stay identical.
    """
    monkeypatch.setattr(magics._state, "memory", None, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", False, raising=False)
    monkeypatch.setattr(magics._state, "last_error", None, raising=False)
    monkeypatch.setattr(magics._state, "stats", {}, raising=False)
    captured = []
    monkeypatch.setattr(magics, "display", lambda obj: captured.append(obj))
    monkeypatch.setattr(magics, "HTML", lambda s: s)

    html = ""
    for _ in range(3):
        captured.clear()
        try:
            [][5]
        except IndexError as e:
            magics._analyze_and_show(type(e), e, e.__traceback__, "[][5]")
        html = "".join(x for x in captured if isinstance(x, str))
    assert "times now" not in html


class _FakeMemFixedSummary:
    """Fake memory whose summary() is a fixed value, independent of record()
    calls — lets the test pin the chronic count precisely."""

    def __init__(self, summary):
        self._summary = summary
        self.recorded = []

    def available(self):
        return True

    def record(self, et, when):
        self.recorded.append((et, when))

    def summary(self):
        return self._summary


def test_chronic_line_present_when_memory_on(monkeypatch):
    """When memory is ON and reports a chronic count, the chronic line must
    still appear — proves Fix 1 didn't disable the feature, only gated it.
    """
    fake = _FakeMemFixedSummary({"IndexError": {"seen": 9, "fixed": 0, "last": "2026-07-14"}})
    monkeypatch.setattr(magics._state, "memory", fake, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", True, raising=False)
    monkeypatch.setattr(magics._state, "last_error", None, raising=False)
    monkeypatch.setattr(magics._state, "stats", {}, raising=False)
    captured = []
    monkeypatch.setattr(magics, "display", lambda obj: captured.append(obj))
    monkeypatch.setattr(magics, "HTML", lambda s: s)

    try:
        [][5]
    except IndexError as e:
        magics._analyze_and_show(type(e), e, e.__traceback__, "[][5]")
    html = "".join(x for x in captured if isinstance(x, str))
    assert "9" in html
    assert "times now" in html


def test_coach_forget_works_when_memory_off(ip, monkeypatch):
    """A user who turned memory off must still be able to erase previously
    saved history — %coach_forget must not require memory_on."""
    fake = _FakeMem()
    monkeypatch.setattr(magics._state, "memory", fake, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", False, raising=False)
    ip.run_line_magic("coach_forget", "")
    assert fake.forgotten is True
