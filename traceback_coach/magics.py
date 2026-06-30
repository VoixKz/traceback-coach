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
    parse_traceback, build_card, render_card_html, load_mermaid_js,
    lesson_card, llm_question, fade_level, render_stats_html,
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


def _analyze_and_show(exc_type, exc_value, exc_tb, cell_source: str) -> None:
    parsed = parse_traceback(exc_type, exc_value, exc_tb, cell_source)
    _state.last_error = (exc_type, exc_value, exc_tb, cell_source)
    _state.stats[parsed.error_type] = _state.stats.get(parsed.error_type, 0) + 1
    level = fade_level(_state.stats[parsed.error_type], _state.level_override)
    card = build_card(parsed, cell_source, llm=_LLM)
    display(HTML(render_card_html(card, diagram_id=_state.next_id(), level=level)))
    _state.pending_fix = True


def _show_fixed() -> None:
    display(HTML(
        "<div style='background:#d1fae5;border-left:4px solid #10b981;"
        "padding:10px 14px;margin:8px 0;border-radius:4px;font-size:14px'>"
        "✅ <strong>Fixed it!</strong> The cell that was failing now runs clean. "
        "What did you change, and why did it work?</div>"
    ))


def _show_lesson(family) -> None:
    card = lesson_card(family)
    html = render_card_html(card, diagram_id=_state.next_id())
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
        _analyze_and_show(*_state.last_error)

    @line_magic
    def coach_lesson(self, line):
        name = line.strip() or ""
        if not name:
            print("🧭  Usage: %coach_lesson <ErrorType>   e.g. %coach_lesson IndexError")
            return
        _show_lesson(lookup(name))

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
        _show_fixed()


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
