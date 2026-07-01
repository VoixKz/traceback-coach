"""Core engine for traceback-coach. No IPython import — fully headless.

Pipeline: parse_traceback -> build_card -> render_card_html.
"""
from __future__ import annotations

import html as _html
import inspect
import re
import traceback as _tb
from dataclasses import dataclass, field
from typing import List, Optional

from .knowledge import ErrorFamily, lookup


@dataclass
class Frame:
    location: str
    line_no: Optional[int]
    source_line: str
    filename: str = ""


@dataclass
class ParsedError:
    error_type: str
    message: str
    line_no: Optional[int]
    source_line: str
    token: str
    frames: List[Frame] = field(default_factory=list)


_TOKEN_PATTERNS = {
    "NameError": r"name '([^']+)' is not defined",
    "UnboundLocalError": r"(?:local variable|access local variable) '([^']+)'",
    "AttributeError": r"has no attribute '([^']+)'",
    "ModuleNotFoundError": r"No module named '([^']+)'",
    "ImportError": r"cannot import name '([^']+)'",
}


def _extract_token(error_type: str, message: str) -> str:
    if error_type == "KeyError":
        return message.strip().strip("'\"")
    pattern = _TOKEN_PATTERNS.get(error_type)
    if pattern:
        m = re.search(pattern, message)
        if m:
            return m.group(1)
    return ""


def parse_traceback(exc_type, exc_value, exc_tb, cell_source: str = "") -> ParsedError:
    """Turn a (type, value, tb) triple into a structured ParsedError."""
    error_type = getattr(exc_type, "__name__", str(exc_type))
    message = str(exc_value).strip()
    src_lines = cell_source.split("\n") if cell_source else []

    frames: List[Frame] = []
    line_no: Optional[int] = None
    source_line = ""

    def _cell_line(n):
        return src_lines[n - 1] if n and 0 < n <= len(src_lines) else ""

    if isinstance(exc_value, SyntaxError) and exc_value.lineno:
        line_no = exc_value.lineno
        source_line = (exc_value.text or "").rstrip("\n") or _cell_line(line_no)
        frames.append(Frame("your cell", line_no, source_line))
    else:
        raw_frames: List[Frame] = []
        for fs in _tb.extract_tb(exc_tb):
            location = "your cell" if fs.name == "<module>" else fs.name
            raw_frames.append(Frame(location, fs.lineno, fs.line or "", fs.filename or ""))

        # The break (deepest) frame is in the student's cell. Keep every frame
        # from that SAME file — that's the student's call chain — and drop
        # harness / IPython-internal frames. Filtering by filename (not source
        # text) is robust even when linecache has no source for the frame.
        if raw_frames:
            cell_file = raw_frames[-1].filename
            frames = [f for f in raw_frames if f.filename == cell_file] or [raw_frames[-1]]
        else:
            frames = []

        # Drop synthetic Python scopes (<genexpr>, <listcomp>, <setcomp>,
        # <dictcomp>, <lambda>) — they show as confusing intermediate nodes.
        # Guard: never empty the list. When the deepest frame is synthetic,
        # drop it so the last non-synthetic frame becomes the break frame
        # (its line_no/source_line are already filled from cell_source above).
        _SYNTHETIC = {"<genexpr>", "<listcomp>", "<setcomp>", "<dictcomp>", "<lambda>"}
        if frames:
            filtered = [f for f in frames if f.location not in _SYNTHETIC]
            if filtered:  # keep the filtered list only if it's non-empty
                frames = filtered

        # Fill any missing source lines from the cell text (linecache may be
        # empty for %%coach's nested run) so each node can show its code.
        for f in frames:
            if not f.source_line:
                f.source_line = _cell_line(f.line_no)

        if frames:
            line_no = frames[-1].line_no
            source_line = frames[-1].source_line or _cell_line(line_no)

    token = _extract_token(error_type, message)
    return ParsedError(error_type, message, line_no, source_line, token, frames)


def _fill(template: str, parsed: ParsedError) -> str:
    """Fill the placeholders used in knowledge templates."""
    return (
        template.replace("{token}", parsed.token or "this name")
        .replace("{message}", parsed.message)
        .replace("{error_type}", parsed.error_type)
        .replace("{line_no}", str(parsed.line_no) if parsed.line_no else "?")
    )


def _mm_escape(text: str) -> str:
    """HTML-escape user text for Mermaid htmlLabels inside double-quoted ["..."] nodes.

    Replaces & < > " with their HTML entities so real code renders correctly.
    Newlines become spaces. The <br/> markup you add yourself is literal (not escaped here).
    """
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("\n", " ")
            .strip()
    )


def _display_code(src: str) -> str:
    """Strip trailing # comment (quote-aware), collapse whitespace, truncate to 80 chars.

    A # inside a string literal is NOT treated as a comment delimiter.
    Examples:
      'return f(x)   # comment' -> 'return f(x)'
      'print("a # b")'          -> 'print("a # b")'
      (anything longer than 80 chars) -> first 79 chars + '…'
    """
    # Walk the string char-by-char, tracking string context, to find the first
    # real (non-string) # character.
    in_str: Optional[str] = None  # current string delimiter (' or ")
    i = 0
    comment_start = -1
    while i < len(src):
        ch = src[i]
        if in_str is None:
            if ch in ('"', "'"):
                in_str = ch
            elif ch == "#":
                comment_start = i
                break
        else:
            if ch == "\\" :
                i += 1  # skip escaped char
            elif ch == in_str:
                in_str = None
        i += 1

    if comment_start >= 0:
        src = src[:comment_start]

    src = src.strip()
    if len(src) > 80:
        src = src[:79] + "…"
    return src


_MAX_CHAIN_NODES = 6


def _chain_steps(chain: List[Frame]):
    """Reduce a call chain to a short list of (head, code) display steps.

    Consecutive identical frames collapse into one step annotated with a repeat
    count (`f (line 2) x998`) — exactly what direct recursion produces. If the
    chain is still long (e.g. mutual recursion), keep the first 3 and last 2 and
    insert one ("... N more calls ...", "") ellipsis step. `head` is the
    function + line; `code` is that call's own source line (may be "").
    """
    # 1. Collapse consecutive identical frames into (frame, count).
    collapsed = []
    for fr in chain:
        if collapsed and collapsed[-1][0].location == fr.location \
                and collapsed[-1][0].line_no == fr.line_no:
            prev_fr, count = collapsed[-1]
            collapsed[-1] = (prev_fr, count + 1)
        else:
            collapsed.append((fr, 1))

    # 2. Cap the number of displayed steps with an ellipsis in the middle.
    if len(collapsed) > _MAX_CHAIN_NODES:
        head_items, tail = collapsed[:3], collapsed[-2:]
        hidden = len(collapsed) - len(head_items) - len(tail)
        items = head_items + [None] + tail
    else:
        items = list(collapsed)
        hidden = 0

    # 3. Emit (head, code) steps.
    steps = []
    for item in items:
        if item is None:
            steps.append((f"... {hidden} more calls ...", ""))
            continue
        fr, count = item
        head = fr.location
        if fr.line_no:
            head += f" (line {fr.line_no})"
        if count > 1:
            head += f" x{count}"
        code = _display_code((fr.source_line or "").strip())
        steps.append((head, code))
    return steps


def _detect_recursion(frames: List[Frame]):
    """Detect recursion in a frame list.

    Returns ("direct", location, count) for direct self-recursion, or
    ("mutual", [(location, line_no, code), ...], total_cycle_count) for
    mutual recursion, or ("none", None, 0) if no recursion detected.

    A location is a (function_name, line_no) pair.
    """
    if not frames:
        return ("none", None, 0)

    # Count (location, line_no) occurrences.
    location_counts: dict = {}
    for f in frames:
        key = (f.location, f.line_no)
        location_counts[key] = location_counts.get(key, 0) + 1

    repeating = {k for k, v in location_counts.items() if v >= 2}
    if not repeating:
        return ("none", None, 0)

    # Build the set of repeating locations in first-seen order.
    seen_order: dict = {}
    for f in frames:
        key = (f.location, f.line_no)
        if key in repeating and key not in seen_order:
            seen_order[key] = f

    repeating_frames = list(seen_order.values())

    # Direct recursion: exactly one location repeats (ignore non-repeating
    # entry frames like "your cell").
    if len(repeating_frames) == 1:
        fr = repeating_frames[0]
        count = location_counts[(fr.location, fr.line_no)]
        return ("direct", fr, count)

    # Mutual recursion: multiple distinct repeating locations — cap at 8.
    ordered = repeating_frames[:8]
    total = len(frames)
    return ("mutual", ordered, total)


_CLASSDEF_LINES = """\
  classDef cf_start fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef cf_frame fill:#eef2ff,stroke:#6366f1,color:#1e1b4b
  classDef cf_break fill:#fef9c3,stroke:#f59e0b,color:#713f12
  classDef cf_boom fill:#fee2e2,stroke:#ef4444,color:#7f1d1d"""


def _node_label(fr: Frame) -> str:
    """Build the inner text of a mermaid node for one frame (HTML-escaped)."""
    loc = _mm_escape(fr.location)
    line_part = f" · line {fr.line_no}" if fr.line_no else ""
    code = _mm_escape(_display_code((fr.source_line or "").strip()))
    head = f"{loc}{line_part}"
    return f"{head}<br/>{code}" if code else head


def build_mermaid(parsed: ParsedError, family: ErrorFamily) -> str:
    """Build a Mermaid `flowchart TD` showing the causal chain to the break."""
    cause = _fill(family.cause_phrase, parsed)
    cause_escaped = _mm_escape(cause)
    error_type_escaped = _mm_escape(parsed.error_type)
    x_label = f"💥 {error_type_escaped}<br/>{cause_escaped}"

    # Check for recursion across all frames (chain + break frame).
    rec_kind, rec_data, rec_count = _detect_recursion(parsed.frames)

    if rec_kind == "direct":
        fr = rec_data
        node_label = _node_label(fr)
        lines = [
            "flowchart TD",
            '  S(["▶ your code runs"]):::cf_start',
            f'  R["{node_label}"]:::cf_break',
            f'  X(["{x_label}"]):::cf_boom',
            "  S --> R",
            f'  R -. "calls itself ×{rec_count}" .-> R',
            "  R ==>|breaks here| X",
            _CLASSDEF_LINES,
        ]
        return "\n".join(lines)

    if rec_kind == "mutual":
        ordered_frames = rec_data  # up to 8, first-seen order
        lines = [
            "flowchart TD",
            '  S(["▶ your code runs"]):::cf_start',
        ]
        cycle_ids: List[str] = []
        for idx, fr in enumerate(ordered_frames):
            nid = f"C{idx}"
            cycle_ids.append(nid)
            label = _node_label(fr)
            # All cycle nodes are cf_break (they all participate in the break)
            lines.append(f'  {nid}["{label}"]:::cf_break')
        lines.append(f'  X(["{x_label}"]):::cf_boom')

        lines.append(f"  S --> {cycle_ids[0]}")
        for i in range(len(cycle_ids) - 1):
            lines.append(f"  {cycle_ids[i]} --> {cycle_ids[i + 1]}")
        # Back-edge from last to FIRST (C0) — the key fix for long cycles
        lines.append(f'  {cycle_ids[-1]} -. "loops back ×{rec_count}" .-> C0')
        lines.append(f"  {cycle_ids[-1]} ==>|breaks here| X")
        lines.append(_CLASSDEF_LINES)
        return "\n".join(lines)

    # Non-recursive: clean linear flowchart.
    chain = parsed.frames[:-1] if len(parsed.frames) > 1 else []
    break_frame = parsed.frames[-1] if parsed.frames else None

    lines = [
        "flowchart TD",
        '  S(["▶ your code runs"]):::cf_start',
    ]
    prev = "S"

    for idx, fr in enumerate(chain):
        nid = f"N{idx}"
        label = _node_label(fr)
        lines.append(f'  {nid}["{label}"]:::cf_frame')
        lines.append(f"  {prev} --> {nid}")
        prev = nid

    # Break (deepest) frame
    if break_frame is not None:
        label = _node_label(break_frame)
        lines.append(f'  N{len(chain)}["{label}"]:::cf_break')
        lines.append(f"  {prev} --> N{len(chain)}")
        prev = f"N{len(chain)}"

    lines.append(f'  X(["{x_label}"]):::cf_boom')
    lines.append(f"  {prev} ==>|breaks here| X")
    lines.append(_CLASSDEF_LINES)
    return "\n".join(lines)


def build_fallback_diagram(parsed: ParsedError, family: ErrorFamily) -> str:
    """Pure HTML/CSS flow fallback when Mermaid can't render.

    Renders the call chain top-to-bottom — each call with its code line (via
    _display_code) — down to the line that broke. For recursive chains, shows
    a compact recursion note instead of listing thousands of frames.
    """
    esc = _html.escape
    cause = _fill(family.cause_phrase, parsed)
    line_label = f"line {parsed.line_no}" if parsed.line_no else "your code"
    src = _display_code(parsed.source_line.strip()) or "the failing line"

    box = (
        "padding:6px 10px;margin:2px 0;border-radius:6px;border:1px solid #cbd5e1;"
        "background:#f8fafc;font-size:13px"
    )
    break_box = (
        "padding:6px 10px;margin:2px 0;border-radius:6px;border:1px solid #f59e0b;"
        "background:#fef9c3;color:#713f12;font-size:13px"
    )
    boom_box = (
        "padding:6px 10px;margin:2px 0;border-radius:6px;border:1px solid #ef4444;"
        "background:#fee2e2;color:#7f1d1d;font-size:13px"
    )
    note_box = (
        "padding:6px 10px;margin:2px 0;border-radius:6px;border:1px solid #6366f1;"
        "background:#eef2ff;color:#1e1b4b;font-size:13px"
    )
    code_style = "font-family:monospace;color:#0f172a"
    down = "<div style='color:#94a3b8;margin:0 0 0 10px'>&darr;</div>"

    rec_kind, rec_data, rec_count = _detect_recursion(parsed.frames)

    rows = ["<div style='margin:8px 0'>",
            f"<div style='{box}'>▶ your code runs</div>", down]

    if rec_kind == "direct":
        fr = rec_data
        loc = esc(fr.location)
        code = esc(_display_code((fr.source_line or "").strip()))
        inner = f"<strong>{loc}</strong>"
        if code:
            inner += f"<br/><span style='{code_style}'>{code}</span>"
        rows.append(f"<div style='{box}'>{inner}</div>")
        rows.append(down)
        rows.append(f"<div style='{note_box}'>↻ calls itself ×{rec_count}</div>")
        rows.append(down)
    elif rec_kind == "mutual":
        ordered_frames = rec_data
        for fr in ordered_frames:
            loc = esc(fr.location)
            code = esc(_display_code((fr.source_line or "").strip()))
            inner = f"<strong>{loc}</strong>"
            if code:
                inner += f"<br/><span style='{code_style}'>{code}</span>"
            rows.append(f"<div style='{box}'>{inner}</div>")
            rows.append(down)
        first_func = esc(ordered_frames[0].location)
        rows.append(f"<div style='{note_box}'>↻ loops back to {first_func} ×{rec_count}</div>")
        rows.append(down)
    else:
        chain = parsed.frames[:-1] if len(parsed.frames) > 1 else []
        for head, code in _chain_steps(chain):
            inner = f"<strong>{esc(head)}</strong>"
            if code:
                inner += f"<br/><span style='{code_style}'>{esc(code)}</span>"
            rows.append(f"<div style='{box}'>{inner}</div>")
            rows.append(down)

    # Break frame
    rows.append(
        f"<div style='{break_box}'><strong>{esc(line_label)}</strong>"
        f"<br/><span style='{code_style}'>{esc(src)}</span></div>"
    )
    rows.append(down)
    rows.append(
        f"<div style='{boom_box}'>💥 <strong>{esc(parsed.error_type)}</strong>: {esc(cause)}</div>"
    )
    rows.append("</div>")
    return "".join(rows)


import json as _json
import os as _os
import urllib.request as _req


def llm_question(parsed: ParsedError, cell_source: str, lang: str = "en") -> str:
    """One short Socratic question from an OpenAI-compatible API.

    Returns "" when no API key is set or on any failure — the caller then
    uses the deterministic template. Honours any OpenAI-compatible gateway via
    OPENAI_BASE_URL. NEVER asks the model for a fix (system prompt forbids it).
    When lang=="zh", instructs the model to reply in Traditional Chinese (zh-HK).
    """
    api_key = (
        _os.environ.get("TRACEBACK_COACH_LLM_API_KEY")
        or _os.environ.get("DEEPSEEK_API_KEY")
        or _os.environ.get("OPENAI_API_KEY")
        or ""
    )
    if not api_key:
        return ""
    base_url = (
        _os.environ.get("TRACEBACK_COACH_LLM_BASE_URL")
        or _os.environ.get("OPENAI_BASE_URL")
        or "https://api.deepseek.com"
    )
    model = (
        _os.environ.get("TRACEBACK_COACH_LLM_MODEL")
        or _os.environ.get("OPENAI_MODEL")
        or "deepseek-chat"
    )
    timeout = int(_os.environ.get("TRACEBACK_COACH_LLM_TIMEOUT", "20"))
    system = (
        "You are a debugging coach for a beginner programmer. Ask EXACTLY ONE "
        "short guiding question that helps them find the bug themselves. Refer to "
        "something specific in their code. NEVER give the fix or any corrected "
        "code. Output only the question."
    )
    if lang == "zh":
        system += " Reply in Traditional Chinese (zh-HK)."
    user = (
        f"Error: {parsed.error_type}: {parsed.message}\n"
        f"Failing line {parsed.line_no}: {parsed.source_line}\n\n"
        f"Their code:\n{cell_source}"
    )
    try:
        body = _json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 80,
            "temperature": 0.5,
        }).encode()
        request = _req.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with _req.urlopen(request, timeout=timeout) as resp:
            data = _json.loads(resp.read())
        text = data["choices"][0]["message"]["content"].strip()
        return text.split("\n")[0].strip().strip('"').strip()
    except Exception:
        return ""


def llm_status() -> dict:
    """Report how the LLM-personalized-question backend is configured (from env)."""
    key = (
        _os.environ.get("TRACEBACK_COACH_LLM_API_KEY")
        or _os.environ.get("DEEPSEEK_API_KEY")
        or _os.environ.get("OPENAI_API_KEY")
        or ""
    )
    base_url = (
        _os.environ.get("TRACEBACK_COACH_LLM_BASE_URL")
        or _os.environ.get("OPENAI_BASE_URL")
        or "https://api.deepseek.com"
    )
    model = (
        _os.environ.get("TRACEBACK_COACH_LLM_MODEL")
        or _os.environ.get("OPENAI_MODEL")
        or "deepseek-chat"
    )
    return {"key_present": bool(key), "base_url": base_url, "model": model}


def make_question(parsed: ParsedError, family: ErrorFamily,
                  cell_source: str = "", llm=None, lang: str = "en") -> str:
    """LLM question if available, else the deterministic template."""
    fn = llm if llm is not None else llm_question
    try:
        n = len(inspect.signature(fn).parameters)
        question = fn(parsed, cell_source, lang) if n >= 3 else fn(parsed, cell_source)
    except Exception:
        question = ""
    if question:
        return question.strip()
    return _fill(family.question_template, parsed)


import importlib.resources as _resources


@dataclass
class CardData:
    error_type: str
    translation: str
    mermaid_src: str
    fallback_html: str
    line_no: Optional[int]
    source_line: str
    token: str
    family_summary: str
    read_it_yourself: str
    example_code: str
    example_explanation: str
    example_avoid: str
    question: str


def build_card(parsed: ParsedError, cell_source: str = "", llm=None,
               lang: str = "en") -> CardData:
    from .i18n import FAMILIES_ZH
    if lang == "zh" and parsed.error_type in FAMILIES_ZH:
        family = FAMILIES_ZH[parsed.error_type]
    else:
        family = lookup(parsed.error_type)
    return CardData(
        error_type=parsed.error_type,
        translation=_fill(family.translation, parsed),
        mermaid_src=build_mermaid(parsed, family),
        fallback_html=build_fallback_diagram(parsed, family),
        line_no=parsed.line_no,
        source_line=parsed.source_line,
        token=parsed.token,
        family_summary=family.family_summary,
        read_it_yourself=family.read_it_yourself,
        example_code=family.example_code,
        example_explanation=family.example_explanation,
        example_avoid=family.example_avoid,
        question=make_question(parsed, family, cell_source, llm, lang),
    )


def lesson_card(family: ErrorFamily, lang: str = "en") -> CardData:
    """Build a CardData for proactive %coach_lesson (no live error)."""
    synthetic = ParsedError(
        error_type=family.key,
        message="(example)",
        line_no=None,
        source_line=family.example_code.split("\n")[0],
        token="",
        frames=[],
    )
    return build_card(synthetic, family.example_code, llm=lambda p, s: "", lang=lang)


def load_mermaid_js() -> str:
    """Return the vendored Mermaid runtime text, or '' if not packaged."""
    try:
        asset = _resources.files("traceback_coach") / "static" / "mermaid.min.js"
        return asset.read_text(encoding="utf-8")
    except Exception:
        return ""


def render_card_html(card: CardData, diagram_id: str = "tbc-diagram",
                     level: str = "full", lang: str = "en") -> str:
    """Render the error-anatomy card. `level` controls how much is shown:
    "full" (default) = everything; "brief" = no diagram/example; "min" =
    just the error type + the one guiding question.
    """
    from .i18n import LABELS
    lbl = LABELS[lang]
    esc = _html.escape
    wrap_open = (
        "<div style=\"border:1px solid #e2e8f0;border-left:4px solid #6366f1;"
        "border-radius:6px;padding:12px 16px;margin:8px 0;font-size:14px;"
        "line-height:1.55\">"
    )
    coach = f"<div style=\"font-weight:600;color:#4338ca\">{lbl['coach']}</div>"
    question = (
        f"<div style=\"margin-top:10px;background:#eef2ff;border-radius:4px;"
        f"padding:8px 10px\">❓ <strong>{lbl['question']}</strong> {esc(card.question)}</div>"
    )

    if level == "min":
        return (
            wrap_open + coach
            + f"<div style=\"margin-top:6px\">🏷️ <strong>{esc(card.error_type)}</strong>"
              f"{lbl['seen_min']}</div>"
            + question + "</div>"
        )

    where = (
        f"line {card.line_no} &rarr; <code>{esc(card.source_line.strip())}</code>"
        if card.line_no else "<code>the failing line</code>"
    )
    translation = (
        f"<div style=\"margin-top:6px\">🔴 <strong>{lbl['what_happened']}</strong> "
        f"{esc(card.translation)}</div>"
    )
    family = (
        f"<div style=\"margin-top:6px\">🏷️ <strong>{esc(card.error_type)}:</strong> "
        f"{esc(card.family_summary)}</div>"
        f"<div style=\"margin-top:6px;color:#475569\">🔎 <strong>{lbl['family_read']}</strong> "
        f"{esc(card.read_it_yourself)}</div>"
    )
    where_block = f"<div style=\"margin-top:6px\">📍 <strong>{lbl['where']}</strong> {where}</div>"

    if level == "brief":
        return wrap_open + coach + translation + where_block + family + question + "</div>"

    # level == "full" (default)
    run_script = (
        "<script>(function(){var el=document.getElementById('%(id)s');"
        "if(!el)return;try{if(window.mermaid){"
        "el.style.display='block';window.mermaid.run({nodes:[el]});"
        "var f=el.parentNode.querySelector('.tbc-fallback');"
        "if(f)f.style.display='none';}}catch(e){}})();</script>"
    ) % {"id": diagram_id}
    diagram = (
        f"<div style=\"margin-top:8px\">📊 <strong>{lbl['why_breaks']}</strong></div>"
        f"<pre class=\"mermaid\" id=\"{diagram_id}\" style=\"display:none;"
        f"background:transparent;border:0\">{esc(card.mermaid_src)}</pre>"
        f"<div class=\"tbc-fallback\" style=\"display:block\">{card.fallback_html}</div>"
        f"{run_script}"
    )
    example = (
        "<details style=\"margin-top:8px\">"
        f"<summary style=\"cursor:pointer\">📖 {lbl['see_example']}</summary>"
        f"<pre style=\"background:#f1f5f9;padding:8px;border-radius:4px;overflow:auto\">"
        f"<code>{esc(card.example_code)}</code></pre>"
        f"<div>{esc(card.example_explanation)}</div>"
        f"<div style=\"margin-top:4px;color:#475569\"><strong>{lbl['avoid_next']}</strong> "
        f"{esc(card.example_avoid)}</div></details>"
    )
    return (wrap_open + coach + translation + diagram + where_block + family
            + example + question + "</div>")


def fade_level(seen_count: int, override: str = "auto") -> str:
    """Resolve how much of the card to show.

    override in {"full","brief","min"} forces that level. "auto" (default)
    fades as the student repeats an error type: 1st time full, 2nd brief,
    3rd+ minimal — so they learn to read it themselves.
    """
    if override in ("full", "brief", "min"):
        return override
    if seen_count <= 1:
        return "full"
    if seen_count == 2:
        return "brief"
    return "min"


def wrap_quiz_html(card_html: str, lang: str = "en") -> str:
    """Wrap a rendered card in an active-recall 'guess the error first' prompt.

    The student predicts the error type, then expands the <details> to reveal
    the Coach's analysis — recall before the answer aids retention.
    """
    from .i18n import LABELS
    lbl = LABELS[lang]
    return (
        "<div style=\"background:#fef3c7;border-left:4px solid #f59e0b;"
        "border-radius:6px;padding:10px 14px;margin:8px 0;font-size:14px\">"
        f"{lbl['guess_first']}</div>"
        "<details style=\"margin:6px 0\">"
        "<summary style=\"cursor:pointer;font-weight:600;color:#4338ca\">"
        f"{lbl['reveal']}</summary>"
        + card_html +
        "</details>"
    )


def render_stats_html(stats: dict) -> str:
    """Render a session summary of which error types occurred, most-common first."""
    esc = _html.escape
    if not stats:
        return (
            "<div style=\"border:1px solid #e2e8f0;border-radius:6px;"
            "padding:10px 14px;margin:8px 0;font-size:14px\">"
            "🧭 <strong>Coach:</strong> no errors yet this session — nice.</div>"
        )
    items = sorted(stats.items(), key=lambda kv: (-kv[1], kv[0]))
    top = items[0][0]
    total = sum(stats.values())
    rows = "".join(
        f"<tr><td style=\"padding:2px 10px\">{esc(k)}</td>"
        f"<td style=\"padding:2px 10px;text-align:right\">{v}</td></tr>"
        for k, v in items
    )
    return (
        "<div style=\"border:1px solid #e2e8f0;border-left:4px solid #6366f1;"
        "border-radius:6px;padding:12px 16px;margin:8px 0;font-size:14px\">"
        "<div style=\"font-weight:600;color:#4338ca\">🧭 Your errors this session</div>"
        f"<table style=\"margin:8px 0;border-collapse:collapse\">{rows}</table>"
        f"<div>Most common: <strong>{esc(top)}</strong> &middot; total: {total}. "
        f"Read up on it: <code>%coach_lesson {esc(top)}</code></div>"
        "</div>"
    )
