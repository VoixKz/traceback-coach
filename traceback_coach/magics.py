"""IPython-facing layer: magics, the post_run_cell hook, and display glue.

All rendering/parsing lives in _core (headless). This module only wires those
into IPython and pushes HTML to the front-end.
"""
from __future__ import annotations

import textwrap
import time

from IPython.core.magic import Magics, magics_class, cell_magic, line_magic
from IPython.display import display, HTML

from ._core import (
    parse_traceback, build_card, render_card_html, wrap_quiz_html, load_mermaid_js,
    lesson_card, llm_question, llm_status, fade_level, render_stats_html,
)
from .knowledge import lookup

# Indirection points so tests can patch behaviour:
_LLM = llm_question

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
    •  %coach_compact on  fold the native traceback to a short summary (opt-in)
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
    %coach_compact on  fold the native traceback to a short summary (on/off/status)
    %coach_help       This help

    The coach never shows the fix — it teaches you to read the error yourself.
""")

_DEBOUNCE_SECONDS = 3.0


class _State:
    def __init__(self):
        self.watch = False
        self.last_error = None      # (exc_type, exc_value, exc_tb, cell_source)
        self.pending_fix = False
        self._id = 0
        self._last_analysis = 0.0
        self.stats = {}            # error_type -> count, this session
        self.level_override = "auto"
        self.quiz = False
        self.lang = "en"
        self.compact = False       # opt-in compact traceback mode (Task B)

    def next_id(self) -> str:
        self._id += 1
        return f"tbc-diagram-{self._id}"

    def should_analyze(self) -> bool:
        now = time.monotonic()
        if now - self._last_analysis >= _DEBOUNCE_SECONDS:
            self._last_analysis = now
            return True
        return False


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


def _compact_exc(shell, etype, evalue, tb, tb_offset=None):
    """Custom IPython exception handler that folds the native traceback.

    Prints a compact summary instead of the full (potentially thousands-of-lines)
    traceback. Wraps its body in try/except so that any internal error falls back
    to the normal traceback display.
    """
    try:
        n_frames = _count_tb_frames(tb)
        deepest_line = _deepest_tb_line(tb)
        exc_name = etype.__name__ if etype is not None else "Exception"
        exc_msg = str(evalue) if evalue is not None else ""
        print(
            f"\n{exc_name}: {exc_msg}\n"
            f"  → deepest line: {deepest_line}\n"
            f"… full traceback folded by Coach ({n_frames} frames). "
            "The card below explains it. (%coach_compact off to restore) …\n"
        )
    except Exception:  # Exception (not BaseException): never swallow Ctrl-C / SystemExit  # noqa: BLE001
        # Safety net: on any internal error fall back to the normal traceback
        shell.showtraceback()


def _install_compact_handler(shell) -> None:
    """Register the compact exc handler for the duration of compact mode."""
    shell.set_custom_exc((BaseException,), _compact_exc)


def _restore_default_handler(shell) -> None:
    """Reset to IPython's default traceback rendering.

    We deliberately reset to the default rather than trying to round-trip a
    third-party handler: IPython's `shell.CustomTB` is an already-wrapped bound
    method, so re-feeding it to `set_custom_exc` double-wraps and breaks it.
    traceback-coach is the only `set_custom_exc` user here, so default is right.
    """
    shell.set_custom_exc((), None)


def _analyze_and_show(exc_type, exc_value, exc_tb, cell_source: str,
                      tally: bool = True) -> None:
    lang = _state.lang
    parsed = parse_traceback(exc_type, exc_value, exc_tb, cell_source)
    _state.last_error = (exc_type, exc_value, exc_tb, cell_source)
    if tally:  # re-explaining the same error must not inflate the stats/fade
        _state.stats[parsed.error_type] = _state.stats.get(parsed.error_type, 0) + 1
    count = _state.stats.get(parsed.error_type, 1)
    level = fade_level(count, _state.level_override)
    card = build_card(parsed, cell_source, llm=_LLM, lang=lang)
    html = render_card_html(card, diagram_id=_state.next_id(), level=level, lang=lang)
    if _state.quiz:
        html = wrap_quiz_html(html, lang=lang)
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
        _analyze_and_show(*_state.last_error, tally=False)

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
            print("🧭  Quiz mode on — guess the error type before revealing.")
        elif mode == "off":
            _state.quiz = False
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
            if not _state.compact:
                _install_compact_handler(self.shell)
                _state.compact = True
            print("🧭  Compact traceback: ON — folds ALL errors in this kernel until you run %coach_compact off.")
        elif mode == "off":
            if _state.compact:
                _restore_default_handler(self.shell)
                _state.compact = False
            print("🧭  Compact traceback: OFF — full tracebacks restored.")
        else:
            status = "on" if _state.compact else "off"
            print(f"🧭  Compact traceback: {status}  (use on/off to change)")

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
        if not _state.should_analyze():
            return
        _analyze_and_show(type(exc), exc, exc.__traceback__, source)
    elif _state.pending_fix:
        _state.pending_fix = False
        _show_fixed(lang=_state.lang)


def register(ipython):
    ipython.register_magics(CoachMagics)
    ipython.events.register("post_run_cell", _post_run_cell_hook)
    inject_mermaid_runtime()
    print(BANNER)


def unregister(ipython):
    try:
        ipython.events.unregister("post_run_cell", _post_run_cell_hook)
    except Exception:
        pass
    # If compact mode is on, restore the default exc handler before unloading.
    if _state.compact:
        try:
            _restore_default_handler(ipython)
        except Exception:
            pass
        _state.compact = False
