# traceback-coach

A visual **error-literacy** coach for Jupyter notebooks. When a cell raises, it
turns the traceback into a teaching moment: a plain-language translation, a
**causal diagram** of why it broke, a **worked example** of that error family,
and **one** guiding question — so students learn to *read errors themselves*.

**It never shows the fix.** The goal is independence: read the error, understand
the cause, and not repeat it next time.

Built for the [DIVE](https://github.com/dive4dec) virtual learning environment
(CityU CS1302), as a companion to
[`socratic-watchdog`](https://github.com/xamzar/socratic-watchdog). Where
socratic-watchdog asks *“is your code right?”*, traceback-coach answers *“how do
you read this error?”*.

---

## Motivation

For a beginner, the single most common wall is a red traceback they can't
decode. `traceback-coach` makes every error legible:

- **Translates** the exception into one plain sentence.
- **Draws the causal chain** — what ran, which line, and *why* it broke — as a
  Mermaid flowchart (with a pure-HTML fallback when Mermaid can't render).
- **Shows a worked example** of the same error family on minimal code, with a
  "how to avoid it next time" note.
- **Asks one guiding question** toward the fix — never the fix itself.

The 12 most common beginner errors (NameError, TypeError, IndexError, …) are
covered **deterministically and offline** — no API key required. An LLM, if
configured, only personalises the guiding question.

## Install

```bash
pip install traceback-coach
```

Then in a notebook:

```python
%load_ext traceback_coach
```

## User Guide

**Explain one cell**

```python
%%coach
print(total)        # NameError → full anatomy card + diagram
```

**Watch every cell automatically**

```python
%coach_watch on
xs = [1, 2, 3]
xs[5]               # IndexError is explained as soon as it happens
%coach_watch off
```

When you fix a cell that was failing, the coach shows a short **“✅ Fixed it!”**
note and asks you to reflect on what changed.

**Re-explain the last error**

```python
%coach_explain
```

**Open a lesson proactively** (no error needed) — great for revision:

```python
%coach_lesson IndexError
```

**Help**

```python
%coach_help
```

### Optional: personalised questions via an LLM

By default the guiding question comes from a built-in template. To have it
reference your specific variables, set an OpenAI-compatible endpoint (e.g. the
DIVE LiteLLM gateway). With nothing set, everything still works.

| Variable | Purpose |
|---|---|
| `TRACEBACK_COACH_LLM_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` | API key (any one) |
| `OPENAI_BASE_URL` / `TRACEBACK_COACH_LLM_BASE_URL` | Endpoint (DIVE LiteLLM gateway) |
| `TRACEBACK_COACH_LLM_MODEL` / `OPENAI_MODEL` | Model id (default `deepseek-chat`) |
| `TRACEBACK_COACH_LLM_TIMEOUT` | Request timeout, seconds (default 20) |

The LLM is told to **never** output a fix — only a single question.

## Developer Guide

```
traceback_coach/
├── __init__.py     # __version__, load/unload_ipython_extension
├── knowledge.py    # ErrorFamily + FAMILIES (12) + lookup()   [no IPython]
├── _core.py        # parse_traceback, diagrams, question, card, render  [no IPython]
├── magics.py       # CoachMagics, post_run_cell hook, display glue  [IPython]
└── static/
    └── mermaid.min.js   # vendored, offline (no CDN)
```

- `knowledge.py` and `_core.py` import **no IPython** — they're unit-testable
  headless. `magics.py` is the only IPython-facing module.
- **Add an error family:** add one `ErrorFamily(...)` entry to `FAMILIES` in
  `knowledge.py`. Templates may use `{token}`, `{message}`, `{error_type}`,
  `{line_no}`. If the type needs token extraction, add a regex to
  `_TOKEN_PATTERNS` in `_core.py`.
- **Run tests:**

  ```bash
  pip install -e ".[dev]"
  pytest -v
  ```

- **Build & verify in a clean env** (two-venv pattern):

  ```bash
  python -m build
  python -m venv /tmp/tbc-test
  /tmp/tbc-test/bin/pip install dist/traceback_coach-0.1.0-py3-none-any.whl pytest
  /tmp/tbc-test/bin/python -c "import traceback_coach, traceback_coach._core as c; assert c.load_mermaid_js()"
  ```

## License

MIT
