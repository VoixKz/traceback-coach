"""Core engine for traceback-coach. No IPython import — fully headless.

Pipeline: parse_traceback -> build_card -> render_card_html.
"""
from __future__ import annotations

import html as _html
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
    """Make text safe inside a Mermaid "..." node label."""
    return (
        text.replace('"', "'").replace("<", "(").replace(">", ")")
        .replace("\n", " ").strip()
    )


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
        code = (fr.source_line or "").strip()
        if len(code) > 60:
            code = code[:57] + "..."
        steps.append((head, code))
    return steps


def _chain_nodes(chain: List[Frame]):
    """(node_id, mermaid_label) pairs for the call chain — code shown per node."""
    out = []
    for idx, (head, code) in enumerate(_chain_steps(chain)):
        h, c = _mm_escape(head), _mm_escape(code)
        out.append((f"F{idx}", f"{h}<br/>{c}" if c else h))
    return out


def build_mermaid(parsed: ParsedError, family: ErrorFamily) -> str:
    """Build a Mermaid `graph TD` showing the causal chain to the break."""
    cause = _fill(family.cause_phrase, parsed)
    line_label = f"line {parsed.line_no}" if parsed.line_no else "your code"
    src = _mm_escape(parsed.source_line) or "the failing line"

    nodes = ['  S["your code runs"]']
    edges: List[str] = []
    prev = "S"

    chain = parsed.frames[:-1] if len(parsed.frames) > 1 else []
    for nid, label in _chain_nodes(chain):
        nodes.append(f'  {nid}["{label}"]')
        edges.append(f"  {prev} --> {nid}")
        prev = nid

    nodes.append(f'  L["{line_label}: {src}"]')
    edges.append(f"  {prev} --> L")
    nodes.append(f'  X["💥 {parsed.error_type}<br/>{_mm_escape(cause)}"]')
    edges.append("  L -->|breaks| X")

    return (
        "graph TD\n"
        + "\n".join(nodes + edges)
        + "\n  style X fill:#fee2e2,stroke:#ef4444,color:#991b1b"
    )


def build_fallback_diagram(parsed: ParsedError, family: ErrorFamily) -> str:
    """Pure HTML/CSS flow fallback when Mermaid can't render.

    Renders the full call chain top-to-bottom — each call with its own code
    line — down to the line that broke, so the student sees where the bad value
    started and how it flowed to the break.
    """
    esc = _html.escape
    cause = _fill(family.cause_phrase, parsed)
    line_label = f"line {parsed.line_no}" if parsed.line_no else "your code"
    src = parsed.source_line.strip() or "the failing line"

    box = (
        "padding:6px 10px;margin:2px 0;border-radius:6px;border:1px solid #cbd5e1;"
        "background:#f8fafc;font-size:13px"
    )
    break_box = (
        "padding:6px 10px;margin:2px 0;border-radius:6px;border:1px solid #ef4444;"
        "background:#fee2e2;color:#991b1b;font-size:13px"
    )
    code_style = "font-family:monospace;color:#0f172a"
    down = "<div style='color:#94a3b8;margin:0 0 0 10px'>&darr;</div>"

    rows = ["<div style='margin:8px 0'>",
            f"<div style='{box}'>your code runs</div>", down]

    chain = parsed.frames[:-1] if len(parsed.frames) > 1 else []
    for head, code in _chain_steps(chain):
        inner = f"<strong>{esc(head)}</strong>"
        if code:
            inner += f"<br/><span style='{code_style}'>{esc(code)}</span>"
        rows.append(f"<div style='{box}'>{inner}</div>")
        rows.append(down)

    rows.append(
        f"<div style='{box}'><strong>{esc(line_label)}</strong>"
        f"<br/><span style='{code_style}'>{esc(src)}</span></div>"
    )
    rows.append(down)
    rows.append(
        f"<div style='{break_box}'>💥 <strong>{esc(parsed.error_type)}</strong>: {esc(cause)}</div>"
    )
    rows.append("</div>")
    return "".join(rows)


import json as _json
import os as _os
import urllib.request as _req


def llm_question(parsed: ParsedError, cell_source: str) -> str:
    """One short Socratic question from an OpenAI-compatible API.

    Returns "" when no API key is set or on any failure — the caller then
    uses the deterministic template. Honours DIVE's LiteLLM gateway via
    OPENAI_BASE_URL. NEVER asks the model for a fix (system prompt forbids it).
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
                  cell_source: str = "", llm=None) -> str:
    """LLM question if available, else the deterministic template."""
    fn = llm if llm is not None else llm_question
    try:
        question = fn(parsed, cell_source)
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


def build_card(parsed: ParsedError, cell_source: str = "", llm=None) -> CardData:
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
        question=make_question(parsed, family, cell_source, llm),
    )


def lesson_card(family: ErrorFamily) -> CardData:
    """Build a CardData for proactive %coach_lesson (no live error)."""
    synthetic = ParsedError(
        error_type=family.key,
        message="(example)",
        line_no=None,
        source_line=family.example_code.split("\n")[0],
        token="",
        frames=[],
    )
    return build_card(synthetic, family.example_code, llm=lambda p, s: "")


def load_mermaid_js() -> str:
    """Return the vendored Mermaid runtime text, or '' if not packaged."""
    try:
        asset = _resources.files("traceback_coach") / "static" / "mermaid.min.js"
        return asset.read_text(encoding="utf-8")
    except Exception:
        return ""


def render_card_html(card: CardData, diagram_id: str = "tbc-diagram",
                     level: str = "full") -> str:
    """Render the error-anatomy card. `level` controls how much is shown:
    "full" (default) = everything; "brief" = no diagram/example; "min" =
    just the error type + the one guiding question.
    """
    esc = _html.escape
    wrap_open = (
        "<div style=\"border:1px solid #e2e8f0;border-left:4px solid #6366f1;"
        "border-radius:6px;padding:12px 16px;margin:8px 0;font-size:14px;"
        "line-height:1.55\">"
    )
    coach = "<div style=\"font-weight:600;color:#4338ca\">🧭 Coach</div>"
    question = (
        f"<div style=\"margin-top:10px;background:#eef2ff;border-radius:4px;"
        f"padding:8px 10px\">❓ <strong>Question:</strong> {esc(card.question)}</div>"
    )

    if level == "min":
        return (
            wrap_open + coach
            + f"<div style=\"margin-top:6px\">🏷️ <strong>{esc(card.error_type)}</strong>"
              " — you've seen this one; read it yourself.</div>"
            + question + "</div>"
        )

    where = (
        f"line {card.line_no} &rarr; <code>{esc(card.source_line.strip())}</code>"
        if card.line_no else "<code>the failing line</code>"
    )
    translation = (
        f"<div style=\"margin-top:6px\">🔴 <strong>What happened:</strong> "
        f"{esc(card.translation)}</div>"
    )
    family = (
        f"<div style=\"margin-top:6px\">🏷️ <strong>{esc(card.error_type)}:</strong> "
        f"{esc(card.family_summary)}</div>"
        f"<div style=\"margin-top:6px;color:#475569\">🔎 <strong>Read it yourself:</strong> "
        f"{esc(card.read_it_yourself)}</div>"
    )
    where_block = f"<div style=\"margin-top:6px\">📍 <strong>Where:</strong> {where}</div>"

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
        "<div style=\"margin-top:8px\">📊 <strong>Why it breaks:</strong></div>"
        f"<pre class=\"mermaid\" id=\"{diagram_id}\" style=\"display:none;"
        f"background:transparent;border:0\">{esc(card.mermaid_src)}</pre>"
        f"<div class=\"tbc-fallback\" style=\"display:block\">{card.fallback_html}</div>"
        f"{run_script}"
    )
    example = (
        "<details style=\"margin-top:8px\">"
        "<summary style=\"cursor:pointer\">📖 See this error on a small example</summary>"
        f"<pre style=\"background:#f1f5f9;padding:8px;border-radius:4px;overflow:auto\">"
        f"<code>{esc(card.example_code)}</code></pre>"
        f"<div>{esc(card.example_explanation)}</div>"
        f"<div style=\"margin-top:4px;color:#475569\"><strong>Avoid it next time:</strong> "
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
