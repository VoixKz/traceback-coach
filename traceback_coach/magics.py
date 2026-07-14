"""IPython-facing layer: magics, the post_run_cell hook, and display glue.

All rendering/parsing lives in _core (headless). This module only wires those
into IPython and pushes HTML to the front-end.
"""
from __future__ import annotations

import textwrap

from IPython.core.magic import Magics, magics_class, cell_magic, line_magic
from IPython.display import display, HTML

from ._core import (
    parse_traceback, build_card, render_card_html, wrap_quiz_html, load_mermaid_js,
    lesson_card, llm_question, llm_status, fade_level, render_stats_html,
)
from .knowledge import lookup

# Indirection points so tests can patch behaviour:
_LLM = llm_question

import datetime as _datetime


def _today() -> str:
    return _datetime.date.today().isoformat()

BANNER = textwrap.dedent("""\
    🧭  traceback-coach loaded!
    ────────────────────────────
    •  %%coach          run a cell; if it errors, explain the traceback
    •  %coach_watch on  explain errors in every cell automatically
    •  %coach_explain   re-explain the last error
    •  %coach_lesson X  open the lesson for an error type (e.g. IndexError)
    •  %coach_level X   detail level: full | brief | min | auto (fades on repeats)
    •  %coach_stats     your most common errors this session
    •  %coach_llm        LLM status / on / off (personalized vs template questions)
    •  %coach_quiz on   guess the error type before the answer (active recall)
    •  %coach_lang en|zh  set explanation language (default: en)
    •  %coach_compact on  collapse the Python traceback (click to expand)
    •  %coach_help      show help
""")

HELP = textwrap.dedent("""\
    🧭  traceback-coach — commands
    ──────────────────────────────
    %%coach           Run a cell and, on error, show the anatomy card + diagram
    %coach_watch on   Auto-explain any failing cell (use 'off' to stop)
    %coach_off        Stop watching
    %coach_explain    Re-explain the most recent error
    %coach_lesson X   Show the lesson for error type X (NameError, IndexError, …)
    %coach_level X    detail level: full | brief | min | auto (fades on repeats)
    %coach_stats      your most common errors this session
    %coach_llm        LLM status / on / off (personalized vs template questions)
    %coach_quiz on    guess the error type before the answer (active recall)
    %coach_lang en|zh  set explanation language (default: en; status to check)
    %coach_compact on  collapse the Python traceback (click to expand) (on/off/status)
    %coach_help       This help

    The coach never shows the fix — it teaches you to read the error yourself.
""")


class _State:
    def __init__(self):
        self.watch = False
        self.last_error = None      # (exc_type, exc_value, exc_tb, cell_source)
        self.pending_fix = False
        self._id = 0
        self.stats = {}            # error_type -> count, this session
        self.level_override = "auto"
        self.quiz = False
        self.lang = "en"
        self.compact = False       # opt-in compact traceback mode (Task B)
        self.memory = None        # HermesMemory | None
        self.memory_on = False    # recording into the profile store

    def next_id(self) -> str:
        self._id += 1
        return f"tbc-diagram-{self._id}"


_state = _State()


def _count_tb_frames(tb) -> int:
    """Count the number of frames in a traceback chain."""
    count = 0
    while tb is not None:
        count += 1
        tb = tb.tb_next
    return count


def _deepest_tb_line(tb) -> str:
    """Return the source line from the deepest frame in the traceback."""
    import linecache
    deepest = tb
    while tb is not None:
        deepest = tb
        tb = tb.tb_next
    frame = deepest.tb_frame
    lineno = deepest.tb_lineno
    filename = frame.f_code.co_filename
    line = linecache.getline(filename, lineno, frame.f_globals).strip()
    return line or "<source unavailable>"


def _coach_exc(shell, etype, evalue, tb, tb_offset=None):
    """Custom IPython exception renderer used while quiz and/or compact is on.

    Both modes fold the native traceback into a collapsible <details>. Quiz mode
    additionally REDACTS the error type from the visible summary — the whole
    point of the guessing game — revealing it only when the student expands the
    block. Wraps its body in try/except so any internal error falls back to the
    normal traceback display.
    """
    try:
        import html as _html
        import traceback as _tb
        n = _count_tb_frames(tb)
        full = _html.escape("".join(_tb.format_exception(etype, evalue, tb)))
        if _state.quiz:
            # Never name the type here — the student must guess it first; it's
            # revealed inside the (collapsed) body and in the Coach card.
            summary = (
                "🔴 An error was raised · <em>type hidden for the quiz</em> — "
                f"click to expand the full traceback ({n} frames)"
            )
        else:  # compact only
            ename = _html.escape(getattr(etype, "__name__", str(etype)))
            # Truncate the RAW message first, then escape — escaping before
            # truncating can slice an entity (e.g. "&amp;" -> "&am") and emit
            # broken HTML in the summary line.
            raw = str(evalue)
            if len(raw) > 140:
                raw = raw[:140] + "…"
            msg = _html.escape(raw)
            summary = (
                f"▸ <strong>{ename}</strong>: {msg} "
                f"&middot; full Python traceback ({n} frames) — click to expand"
            )
        display(HTML(
            "<details style=\"margin:4px 0\">"
            "<summary style=\"cursor:pointer;color:#991b1b;"
            f"font-family:monospace;font-size:13px\">{summary}</summary>"
            "<pre style=\"background:#fef2f2;border-left:3px solid #ef4444;"
            "padding:8px;overflow:auto;font-size:12px;margin:4px 0\">"
            f"{full}</pre>"
            "</details>"
        ))
    except Exception:  # Exception (not BaseException): never swallow Ctrl-C / SystemExit  # noqa: BLE001
        # Safety net: on any internal error fall back to the normal traceback
        shell.showtraceback()


def _sync_exc_handler(shell) -> None:
    """Install the coach exc renderer when quiz and/or compact is on; otherwise
    restore IPython's default traceback rendering. traceback-coach is the only
    `set_custom_exc` user here, so resetting to the default is safe.
    """
    if _state.quiz or _state.compact:
        shell.set_custom_exc((BaseException,), _coach_exc)
    else:
        shell.set_custom_exc((), None)


def _analyze_and_show(exc_type, exc_value, exc_tb, cell_source: str,
                      tally: bool = True, force: bool = False) -> None:
    # Dedup by exception identity: the SAME exception object can reach us twice
    # (e.g. `%%coach` runs the cell, the post_run_cell hook fires for it, AND the
    # magic explains it). Show it once. Distinct back-to-back errors are distinct
    # objects, so they are never suppressed. `force` lets %coach_explain
    # re-render the last error on demand.
    if (not force and _state.last_error is not None
            and exc_value is _state.last_error[1]):
        return
    lang = _state.lang
    parsed = parse_traceback(exc_type, exc_value, exc_tb, cell_source)
    _state.last_error = (exc_type, exc_value, exc_tb, cell_source)
    if tally:  # re-explaining the same error must not inflate the stats/fade
        _state.stats[parsed.error_type] = _state.stats.get(parsed.error_type, 0) + 1
        if _state.memory_on and _state.memory is not None:
            try:
                _state.memory.record(parsed.error_type, _today())
            except Exception:
                pass  # memory must never break the coach
    seen = _state.stats.get(parsed.error_type, 1)
    if _state.memory_on and _state.memory is not None:
        try:
            seen = _state.memory.summary().get(parsed.error_type, {}).get("seen", seen)
        except Exception:
            pass
    level = fade_level(seen, _state.level_override)
    card = build_card(parsed, cell_source, llm=_LLM, lang=lang, seen_count=seen)
    html = render_card_html(card, diagram_id=_state.next_id(), level=level, lang=lang)
    if _state.quiz:
        html = wrap_quiz_html(html, parsed.error_type, lang=lang, quiz_id=_state.next_id())
    display(HTML(html))
    _state.pending_fix = True


def _show_fixed(lang: str = "en") -> None:
    from .i18n import LABELS
    msg = LABELS[lang]["fixed_it"]
    display(HTML(
        "<div style='background:#d1fae5;border-left:4px solid #10b981;"
        f"padding:10px 14px;margin:8px 0;border-radius:4px;font-size:14px'>{msg}</div>"
    ))


def _show_lesson(family, lang: str = "en") -> None:
    from .i18n import FAMILIES_ZH
    if lang == "zh" and family.key in FAMILIES_ZH:
        loc_family = FAMILIES_ZH[family.key]
    else:
        loc_family = family
    card = lesson_card(loc_family, lang=lang)
    html = render_card_html(card, diagram_id=_state.next_id(), lang=lang)
    display(HTML(
        f"<div style='font-size:13px;color:#64748b;margin-bottom:2px'>"
        f"Lesson: {family.key}</div>{html}"
    ))


def inject_mermaid_runtime() -> None:
    js = load_mermaid_js()
    if not js:
        return
    display(HTML(
        "<script>try{" + js +
        "\nif(window.mermaid){window.mermaid.initialize({startOnLoad:false});}"
        "}catch(e){}</script>"
    ))


@magics_class
class CoachMagics(Magics):
    @cell_magic
    def coach(self, line, cell):
        result = self.shell.run_cell(cell)
        exc = getattr(result, "error_in_exec", None) or getattr(result, "error_before_exec", None)
        if exc is not None:
            _analyze_and_show(type(exc), exc, exc.__traceback__, cell)

    @line_magic
    def coach_watch(self, line):
        mode = line.strip().lower()
        if mode == "on":
            _state.watch = True
            print("🧭  Watching every cell. Errors will be explained automatically.")
        elif mode == "off":
            _state.watch = False
            print("🧭  No longer watching.")
        else:
            print(f"🧭  Auto-watch: {'on' if _state.watch else 'off'}  (use on/off)")

    @line_magic
    def coach_off(self, line):
        _state.watch = False
        print("🧭  Watcher off.")

    @line_magic
    def coach_explain(self, line):
        if _state.last_error is None:
            print("🧭  No error to explain yet. Run some code first.")
            return
        _analyze_and_show(*_state.last_error, tally=False, force=True)

    @line_magic
    def coach_lesson(self, line):
        name = line.strip() or ""
        if not name:
            print("🧭  Usage: %coach_lesson <ErrorType>   e.g. %coach_lesson IndexError")
            return
        _show_lesson(lookup(name), lang=_state.lang)

    @line_magic
    def coach_level(self, line):
        val = line.strip().lower() or "auto"
        if val not in ("full", "brief", "min", "auto"):
            print("🧭  Usage: %coach_level <full|brief|min|auto>")
            return
        _state.level_override = val
        print(f"🧭  Detail level: {val}")

    @line_magic
    def coach_stats(self, line):
        display(HTML(render_stats_html(_state.stats)))

    @line_magic
    def coach_llm(self, line):
        global _LLM
        arg = line.strip().lower()
        if arg == "off":
            _LLM = lambda p, s: ""
            print("🧭  LLM off — using offline template questions.")
            return
        if arg == "on":
            _LLM = llm_question
            print("🧭  LLM on.")
        st = llm_status()
        if not st["key_present"]:
            print("🧭  LLM: not configured (no API key) — offline template questions.\n"
                  "    Set TRACEBACK_COACH_LLM_API_KEY (+ OPENAI_BASE_URL) to personalize.")
        else:
            active = "on" if _LLM is llm_question else "off (forced templates)"
            print(f"🧭  LLM: configured · model={st['model']} · endpoint={st['base_url']} · {active}")

    @line_magic
    def coach_quiz(self, line):
        mode = line.strip().lower()
        if mode == "on":
            _state.quiz = True
            _sync_exc_handler(self.shell)
            print("🧭  Quiz mode on — guess the error type first; the traceback's type stays hidden until you expand it.")
        elif mode == "off":
            _state.quiz = False
            _sync_exc_handler(self.shell)
            print("🧭  Quiz mode off.")
        else:
            print(f"🧭  Quiz mode: {'on' if _state.quiz else 'off'}  (use on/off)")

    @line_magic
    def coach_lang(self, line):
        arg = line.strip().lower()
        if arg == "status":
            print(f"🧭  Language: {_state.lang}")
            return
        if arg not in ("en", "zh"):
            print("🧭  Usage: %coach_lang en|zh|status")
            return
        _state.lang = arg
        label = "English" if arg == "en" else "Traditional Chinese (zh-HK)"
        print(f"🧭  Language set to {label}.")

    @line_magic
    def coach_compact(self, line):
        mode = line.strip().lower()
        if mode == "on":
            _state.compact = True
            _sync_exc_handler(self.shell)
            print("🧭  Compact traceback: ON — Python tracebacks are collapsed (click to expand). The Coach card is untouched.")
        elif mode == "off":
            _state.compact = False
            _sync_exc_handler(self.shell)
            print("🧭  Compact traceback: OFF — full tracebacks restored.")
        else:
            status = "on" if _state.compact else "off"
            print(f"🧭  Compact traceback: {status}  (use on/off to change)")

    @line_magic
    def coach_memory(self, line):
        arg = line.strip().lower()
        if _state.memory is None:
            from .hermes_memory import HermesMemory
            _state.memory = HermesMemory()
        if arg == "on":
            if _state.memory.available():
                _state.memory_on = True
                print("🧭  Memory on — I'll remember your error weaknesses across sessions.")
            else:
                _state.memory_on = False
                print("🧭  Memory needs `pip install traceback-coach[hermes]` and a Hermes profile. Staying off.")
        elif arg == "off":
            _state.memory_on = False
            print("🧭  Memory off (nothing recorded).")
        else:
            state = "on" if _state.memory_on else "off"
            avail = "yes" if _state.memory.available() else "no (needs [hermes] + Hermes)"
            print(f"🧭  Memory: {state}  ·  available: {avail}")

    @line_magic
    def coach_insights(self, line):
        if not (_state.memory_on and _state.memory is not None):
            print("🧭  Turn memory on first: %coach_memory on")
            return
        try:
            text = _state.memory.reflect(lang=_state.lang)
        except Exception as exc:
            print(f"🧭  Couldn't reach the agent for a review ({exc}). Your history is still saved.")
            return
        display(HTML(
            "<div style='background:#eef2ff;border-left:4px solid #6366f1;"
            "padding:10px 14px;margin:8px 0;border-radius:4px;font-size:14px;"
            f"white-space:pre-wrap'>{text}</div>"
        ))

    @line_magic
    def coach_forget(self, line):
        if _state.memory is None or not _state.memory_on:
            print("🧭  Memory is off — nothing to forget.")
            return
        try:
            _state.memory.forget()
            print("🧭  Forgot your saved error history.")
        except Exception as exc:
            print(f"🧭  Couldn't clear history ({exc}).")

    @line_magic
    def coach_help(self, line):
        print(HELP)


def _post_run_cell_hook(result):
    if not _state.watch:
        return
    info = result.info if hasattr(result, "info") and hasattr(result.info, "raw_cell") else result
    source = (getattr(info, "raw_cell", "") or "").strip()
    if not source or source.startswith(("%", "!")):
        return
    exc = getattr(result, "error_in_exec", None) or getattr(result, "error_before_exec", None)
    if exc is not None:
        _analyze_and_show(type(exc), exc, exc.__traceback__, source)
    elif _state.pending_fix:
        _state.pending_fix = False
        if (_state.memory_on and _state.memory is not None
                and _state.last_error is not None):
            try:
                _state.memory.record_fixed(_state.last_error[0].__name__)
            except Exception:
                pass
        _show_fixed(lang=_state.lang)


def register(ipython):
    ipython.register_magics(CoachMagics)
    ipython.events.register("post_run_cell", _post_run_cell_hook)
    from .hermes_memory import HermesMemory
    _state.memory = HermesMemory()
    _state.memory_on = _state.memory.available()
    inject_mermaid_runtime()
    print(BANNER)


def unregister(ipython):
    try:
        ipython.events.unregister("post_run_cell", _post_run_cell_hook)
    except Exception:
        pass
    # If quiz/compact left a custom exc handler installed, restore the default.
    if _state.quiz or _state.compact:
        try:
            ipython.set_custom_exc((), None)
        except Exception:
            pass
        _state.quiz = False
        _state.compact = False
