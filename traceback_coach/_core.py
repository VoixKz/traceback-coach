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

    if isinstance(exc_value, SyntaxError) and exc_value.lineno:
        line_no = exc_value.lineno
        source_line = (exc_value.text or "").rstrip("\n")
        if not source_line and 0 < line_no <= len(src_lines):
            source_line = src_lines[line_no - 1]
        frames.append(Frame("<cell>", line_no, source_line))
    else:
        for fs in _tb.extract_tb(exc_tb):
            location = "<cell>" if fs.name == "<module>" else fs.name
            frames.append(Frame(location, fs.lineno, fs.line or ""))
        if frames:
            last = frames[-1]
            line_no = last.line_no
            source_line = last.source_line
            if not source_line and line_no and 0 < line_no <= len(src_lines):
                source_line = src_lines[line_no - 1]

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
    return text.replace('"', "'").replace("\n", " ").strip()


def build_mermaid(parsed: ParsedError, family: ErrorFamily) -> str:
    """Build a Mermaid `graph TD` showing the causal chain to the break."""
    cause = _fill(family.cause_phrase, parsed)
    line_label = f"line {parsed.line_no}" if parsed.line_no else "your code"
    src = _mm_escape(parsed.source_line) or "the failing line"

    nodes = ['  S["your code runs"]']
    edges: List[str] = []
    prev = "S"

    chain = parsed.frames[:-1] if len(parsed.frames) > 1 else []
    for i, fr in enumerate(chain):
        nid = f"F{i}"
        label = _mm_escape(fr.location)
        if fr.line_no:
            label = f"{label} (line {fr.line_no})"
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
    """Pure HTML/CSS boxes-and-arrows fallback when Mermaid can't render."""
    cause = _fill(family.cause_phrase, parsed)
    line_label = f"line {parsed.line_no}" if parsed.line_no else "your code"
    src = parsed.source_line.strip() or "the failing line"
    box = (
        "display:inline-block;padding:6px 10px;margin:4px;border-radius:6px;"
        "border:1px solid #cbd5e1;background:#f8fafc;font-family:monospace;font-size:13px"
    )
    break_box = (
        "display:inline-block;padding:6px 10px;margin:4px;border-radius:6px;"
        "border:1px solid #ef4444;background:#fee2e2;color:#991b1b;font-size:13px"
    )
    arrow = "<span style='margin:0 6px;color:#64748b'>&rarr;</span>"
    return (
        "<div style='margin:8px 0'>"
        f"<span style='{box}'>your code runs</span>{arrow}"
        f"<span style='{box}'>{line_label}: {_html.escape(src)}</span>{arrow}"
        f"<span style='{break_box}'>💥 {parsed.error_type}: {_html.escape(cause)}</span>"
        "</div>"
    )


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
