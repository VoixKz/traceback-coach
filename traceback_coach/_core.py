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
