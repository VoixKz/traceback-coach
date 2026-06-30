# Progressive Fade + coach_stats + Showcase — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add two pedagogy features to `traceback-coach` — *progressive fade* (the coach shows less as a student repeats the same error type) and `%coach_stats` (a session map of which errors the student hits most) — plus a showcase notebook that makes the fade visible (same error → full → brief → minimal) and seeds the lab with content.

**Architecture:** Keep the existing split — pure, headless logic in `_core.py` (fade-level resolver + stats renderer + level-aware card render); IPython-only wiring in `magics.py` (per-session tally + two new magics). No new runtime dependencies.

**Tech Stack:** Python ≥3.9, IPython ≥8, pytest. Tests run with `~/tbc-build/bin/python -m pytest`.

## Global Constraints

- Repo root: `traceback-coach/` (this repo). Work on branch `feature/progressive-fade-stats`.
- Every module starts with `from __future__ import annotations`.
- `_core.py` and `knowledge.py` MUST NOT import IPython (stay headless/unit-testable). `magics.py` is the only IPython-facing module.
- Runtime dependency stays **`ipython` only** — no new deps.
- TDD per task: write failing test → confirm RED → implement → confirm GREEN → commit. Run tests with `~/tbc-build/bin/python -m pytest <files> -q`.
- The coach NEVER shows the fix/corrected code — only the existing guiding question. Preserve this in every render level.
- Fade thresholds (auto mode), keyed on how many times that error type has occurred this session: **1st occurrence → `full`; 2nd → `brief`; 3rd and later → `min`.**
- Backward compatibility: `render_card_html` gains a `level` parameter that DEFAULTS to `"full"`, so existing call sites and tests are unchanged.

---

### Task 1: Fade-level resolver + stats renderer (`_core.py`, headless)

**Files:**
- Modify: `traceback_coach/_core.py` (append two functions)
- Test: `tests/test_fade.py` (new)

**Interfaces produced:**
- `fade_level(seen_count: int, override: str = "auto") -> str` → one of `"full" | "brief" | "min"`.
- `render_stats_html(stats: dict[str, int]) -> str` → HTML summary of error counts.

- [ ] **Step 1: Write the failing test** `tests/test_fade.py`

```python
from __future__ import annotations

from traceback_coach._core import fade_level, render_stats_html


def test_auto_fades_with_repetition():
    assert fade_level(1, "auto") == "full"
    assert fade_level(2, "auto") == "brief"
    assert fade_level(3, "auto") == "min"
    assert fade_level(9, "auto") == "min"


def test_override_wins():
    assert fade_level(1, "min") == "min"
    assert fade_level(99, "full") == "full"
    assert fade_level(2, "brief") == "brief"


def test_unknown_override_falls_back_to_auto():
    assert fade_level(1, "bogus") == "full"
    assert fade_level(3, "bogus") == "min"


def test_stats_html_empty():
    out = render_stats_html({})
    assert "no errors yet" in out.lower()


def test_stats_html_sorted_with_top_and_total():
    out = render_stats_html({"NameError": 1, "IndexError": 3, "TypeError": 2})
    # most common highlighted + a lesson tip + total
    assert "IndexError" in out and "NameError" in out and "TypeError" in out
    assert "%coach_lesson IndexError" in out      # top family suggested
    assert "6" in out                              # total occurrences
    # IndexError row appears before NameError row (sorted desc)
    assert out.index("IndexError") < out.index("NameError")
```

- [ ] **Step 2: Run test → RED**

`~/tbc-build/bin/python -m pytest tests/test_fade.py -q` → FAIL (names not importable).

- [ ] **Step 3: Append to `traceback_coach/_core.py`**

```python
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
```

- [ ] **Step 4: Run test → GREEN**, then **Step 5: Commit**

```bash
git add traceback_coach/_core.py tests/test_fade.py
git commit -m "Add fade_level resolver and render_stats_html (RED->GREEN)"
```

---

### Task 2: Level-aware card rendering (`_core.render_card_html`)

**Files:**
- Modify: `traceback_coach/_core.py` (`render_card_html`)
- Test: `tests/test_render.py` (append)

**Interfaces:** `render_card_html(card: CardData, diagram_id: str = "tbc-diagram", level: str = "full") -> str`. `level` defaults to `"full"` (unchanged behavior). `"brief"` omits the diagram and the worked-example `<details>`. `"min"` shows only error type + the one guiding question.

- [ ] **Step 1: Append failing tests to `tests/test_render.py`**

```python
def _name_card():
    src = "print(total)\n"
    return build_card(parse_traceback(*_capture(src), cell_source=src), src,
                      llm=lambda p, s: "")


def test_brief_omits_diagram_and_example_keeps_question():
    html = render_card_html(_name_card(), diagram_id="b1", level="brief")
    assert 'class="mermaid"' not in html      # no diagram
    assert "<details" not in html              # no worked example
    assert "Question:" in html                 # still guides
    assert "NameError" in html


def test_min_is_one_line_type_plus_question():
    html = render_card_html(_name_card(), diagram_id="m1", level="min")
    assert "NameError" in html
    assert "Question:" in html
    assert 'class="mermaid"' not in html and "<details" not in html
    assert "What happened" not in html         # no full translation block


def test_full_is_unchanged_default():
    html = render_card_html(_name_card(), diagram_id="f1")  # default level
    assert 'class="mermaid"' in html and "<details" in html and "Question:" in html
```

- [ ] **Step 2: Run → RED** (`level` kwarg + behavior not present).

- [ ] **Step 3: Replace `render_card_html` in `_core.py`** with this level-aware version (keeps the existing full layout, adds brief/min):

```python
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
```

- [ ] **Step 4: Run → GREEN** (`tests/test_render.py` all pass, including the pre-existing full-card tests). **Step 5: Commit**

```bash
git add traceback_coach/_core.py tests/test_render.py
git commit -m "Make render_card_html level-aware (full/brief/min) (RED->GREEN)"
```

---

### Task 3: Wire fade + stats into magics (`magics.py`)

**Files:**
- Modify: `traceback_coach/magics.py`
- Test: `tests/test_magics.py` (append + extend fixture)

**Interfaces / behavior:**
- `_State` gains `stats: dict[str,int]` (default empty) and `level_override: str = "auto"`.
- `_analyze_and_show` tallies `parsed.error_type`, computes `level = fade_level(count, _state.level_override)`, and passes `level` to `render_card_html`.
- New line magics: `%coach_level <full|brief|min|auto>` (sets `_state.level_override`) and `%coach_stats` (displays `render_stats_html(_state.stats)`).
- Banner/help updated to list both.
- Consumes from `_core`: `fade_level`, `render_stats_html` (import them).

- [ ] **Step 1: Append failing tests to `tests/test_magics.py`** (and extend the `ip` fixture to also reset `M._state.stats = {}` and `M._state.level_override = "auto"` for isolation):

```python
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
```

- [ ] **Step 2: Run → RED.**

- [ ] **Step 3: Edit `magics.py`:**

(a) Update the import from `_core` to add `fade_level, render_stats_html`:

```python
from ._core import (
    parse_traceback, build_card, render_card_html, load_mermaid_js,
    lesson_card, llm_question, fade_level, render_stats_html,
)
```

(b) In `class _State.__init__`, add:

```python
        self.stats = {}            # error_type -> count, this session
        self.level_override = "auto"
```

(c) Replace `_analyze_and_show` body so it tallies and fades:

```python
def _analyze_and_show(exc_type, exc_value, exc_tb, cell_source: str) -> None:
    parsed = parse_traceback(exc_type, exc_value, exc_tb, cell_source)
    _state.last_error = (exc_type, exc_value, exc_tb, cell_source)
    _state.stats[parsed.error_type] = _state.stats.get(parsed.error_type, 0) + 1
    level = fade_level(_state.stats[parsed.error_type], _state.level_override)
    card = build_card(parsed, cell_source, llm=_LLM)
    display(HTML(render_card_html(card, diagram_id=_state.next_id(), level=level)))
    _state.pending_fix = True
```

(d) Add two line magics inside `CoachMagics` (next to the others):

```python
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
```

(e) Add these two lines to the `BANNER` and `HELP` text blocks (anywhere in their lists):

```
    •  %coach_level X   detail level: full | brief | min | auto (fades on repeats)
    •  %coach_stats     your most common errors this session
```

- [ ] **Step 4: Run → GREEN** (`~/tbc-build/bin/python -m pytest tests/test_magics.py tests/test_fade.py tests/test_render.py -q`). **Step 5: Commit**

```bash
git add traceback_coach/magics.py tests/test_magics.py
git commit -m "Wire progressive fade + coach_level/coach_stats into magics (RED->GREEN)"
```

---

### Task 4: Showcase notebook + seed all notebooks into the lab image

**Files:**
- Create: `demo_02_features.ipynb`
- Modify: `deploy/Dockerfile` (seed every top-level `*.ipynb`, not just `demo.ipynb`)

**Interfaces:** none (content + packaging). This is the visible "before/after" deliverable.

- [ ] **Step 1: Create `demo_02_features.ipynb`** (nbformat 4) with these cells in order:
  1. markdown: title "traceback-coach — features tour" + note that re-running the same error shows the coach fade (full → brief → minimal).
  2. code: `%load_ext traceback_coach`
  3. markdown: "## Progressive fade — run the SAME error three times"
  4. code: `%%coach` + `print(total)`  (1st = full card)
  5. code: `%%coach` + `print(total)`  (2nd = brief)
  6. code: `%%coach` + `print(total)`  (3rd = minimal)
  7. markdown: "## Force the detail level back" + code: `%coach_level full`
  8. markdown: "## Your error stats" + code: `%coach_stats`
  9. markdown: "## Watch mode + lessons" + code: `%coach_watch on`
  10. code: `xs = [1, 2, 3]\nxs[7]`  (IndexError, auto-explained)
  11. code: `%coach_lesson ZeroDivisionError`

  Validate it parses: `~/tbc-build/bin/python -c "import json; json.load(open('demo_02_features.ipynb'))"`.

- [ ] **Step 2: Update `deploy/Dockerfile`** — change the line that copies the demo so ALL top-level notebooks land in the lab work dir. Find:

  ```
  cp /opt/app/demo.ipynb ${NB_WORKDIR}/demo.ipynb
  ```
  Replace with:
  ```
  cp /opt/app/*.ipynb ${NB_WORKDIR}/
  ```

- [ ] **Step 3: Commit**

```bash
git add demo_02_features.ipynb deploy/Dockerfile
git commit -m "Add features-tour notebook; seed all *.ipynb into the lab image"
```

---

## Self-Review

- Fade thresholds (1→full, 2→brief, ≥3→min) live in `fade_level` (Task 1) and are exercised end-to-end in Task 3's repeat test. ✓
- `render_card_html` stays backward-compatible (default `level="full"`); existing render tests untouched. ✓
- Stats keyed on `parsed.error_type`, rendered by a pure function (Task 1) and surfaced by `%coach_stats` (Task 3). ✓
- No new deps; `_core` stays IPython-free (fade/stats are pure). ✓
- No-fix invariant preserved at every level (min still shows only the question). ✓
- Showcase makes the difference visible (same error ×3) and fills the lab (Dockerfile seeds all notebooks). ✓
