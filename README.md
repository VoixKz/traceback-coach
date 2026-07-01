# traceback-coach

A visual **error-literacy** coach for Jupyter notebooks. When a cell raises, it
turns the traceback into a teaching moment: a plain-language translation, a
**causal diagram** of why it broke, a **worked example**, and **one** guiding
question — so students learn to *read errors themselves* and not repeat them.

**It never shows the fix.** The goal is independence: read the error, understand
the cause, fix it yourself.

> *"An expert is a person who has made all the mistakes that can be made in a very
> narrow field."* — Niels Bohr

Works fully **offline** — no account, no network required. An LLM is optional and
only personalizes the guiding question.

## Features

| Feature | What it does |
|---|---|
| **`%%coach`** cell magic | Explain the error in a single cell |
| **`%coach_watch on`** | Auto-explain every failing cell the moment it breaks |
| **Anatomy card** | Plain translation + causal diagram + worked example + one question |
| **Causal diagram** | Mermaid flowchart of the call chain — **recursion drawn as a loop** |
| **Never the fix** | Only a guiding question; *you* fix it yourself |
| **Progressive fade** | Full card → brief → minimal nudge as you repeat an error type |
| **Quiz / active recall** | Guess the error type before the analysis is revealed |
| **Bilingual** | The whole card in English or Traditional Chinese (zh-HK) |
| **Collapsible traceback** | Fold the giant red Python traceback into a click-to-expand line |
| **Error stats** | See which error types you hit most this session |
| **Lessons on demand** | Open a lesson for any error family — no error needed |
| **Offline diagrams** | Mermaid is vendored — renders with no network |

## Install

```bash
pip install traceback-coach
```

Then in a notebook:

```python
%load_ext traceback_coach
```

## Quick start

```python
%%coach
print(total)        # `total` was never defined
```

Instead of a wall of red, the Coach shows an **anatomy card** — something like:

> 🔴 **What happened** — the name `total` is used before it's defined; Python has
> no value bound to it yet (`NameError: name 'total' is not defined`).
> 📊 **Why it breaks** — a diagram tracing the cell down to the failing line.
> 🏷️ **NameError** · 🔎 *a NameError means a name is used before it exists — check
> for a typo, or whether you assigned it earlier.*
> ❓ **Question:** *Where should `total` receive its first value, before this line?*

…and never the corrected code. Or watch every cell automatically:

```python
%coach_watch on
xs = [1, 2, 3]
xs[5]               # IndexError is explained the moment it happens
```

## How it works

```
┌───────────────┐   ┌───────────────┐   ┌──────────────────────────┐   ┌───────────────┐
│ Cell raises   │ → │ Parse the     │ → │ Build the card:          │ → │ Render inline │
│ (type, value, │   │ traceback     │   │  · plain translation     │   │ in the        │
│  frames)      │   │ (drop noise   │   │  · causal diagram        │   │ notebook —    │
│               │   │  frames)      │   │  · worked example        │   │ never a fix   │
│               │   │               │   │  · ONE guiding question  │   │               │
└───────────────┘   └───────────────┘   └──────────────────────────┘   └───────────────┘
```

The card is built to teach, not to solve. On every error the engine:

1. Translates the traceback into one plain sentence.
2. Draws **where** it broke — recursion becomes a visible loop, not a 1000-line wall.
3. Shows the same error on minimal code, plus how to avoid it next time.
4. Asks exactly **one** guiding question — never the corrected code.

## Commands

| Command | What it does |
|---|---|
| `%load_ext traceback_coach` | load the extension |
| `%%coach` | run a cell; if it raises, show the anatomy card |
| `%coach_watch on` / `off` | auto-explain **every** failing cell |
| `%coach_explain` | re-explain the most recent error |
| `%coach_lesson <Type>` | open a lesson for an error family (no error needed), e.g. `%coach_lesson IndexError` |
| `%coach_level full\|brief\|min\|auto` | detail level; **`auto`** fades as you repeat an error (full → brief → minimal) |
| `%coach_stats` | a session map of which error types you hit most |
| `%coach_quiz on` / `off` | **active recall** — guess the error type before revealing the analysis |
| `%coach_lang en\|zh` | explanation language: English or **Traditional Chinese (zh-HK)** |
| `%coach_llm` / `on` / `off` | LLM status / toggle personalized vs template questions |
| `%coach_compact on` / `off` | fold the red Python traceback into a click-to-expand line |
| `%coach_help`, `%coach_off` | help / stop watching |

## The anatomy card

On any error the Coach shows:

- 🔴 **What happened** — the traceback in one plain sentence
- 📊 **Why it breaks** — a Mermaid flowchart of the call chain *with the code at
  each step*, down to the line that broke. **Recursion is drawn as a loop** — a
  self-loop labelled `calls itself ×N` for direct recursion, or a cycle that
  `loops back ×N` for mutual recursion. Falls back to a pure HTML/CSS diagram if
  Mermaid can't render.
- 📍 **Where** — the line + offending token
- 🏷️ **Error family** + 🔎 *how to read this kind of error yourself*
- 📖 **Worked example** (collapsible) — the same error on minimal code + how to
  avoid it next time
- ❓ **One guiding question** — never the fix

Covers 12 beginner error families: `NameError, TypeError, ValueError, IndexError,
KeyError, AttributeError, IndentationError, SyntaxError, ZeroDivisionError,
ModuleNotFoundError/ImportError, RecursionError, UnboundLocalError`.

## Feature highlights

- **Progressive fade** (`%coach_level auto`, default) — the 1st time you hit an
  error type you get the full card; the 2nd a brief one; the 3rd+ a minimal
  nudge. Force a level with `%coach_level full|brief|min`.
- **Error stats** (`%coach_stats`) — see your most common mistakes this session.
- **Quiz / active recall** (`%coach_quiz on`) — predict the error type before
  revealing the analysis; recalling first aids retention.
- **Bilingual** (`%coach_lang zh`) — the whole card (translation, family, “read
  it yourself”, worked example, question, UI labels) in Traditional Chinese for
  Hong Kong learners. English is the default and unchanged.
- **Collapsible traceback** (`%coach_compact on`) — fold the giant red Python
  traceback into one click-to-expand line; the Coach card stays untouched.
- **Personalized questions** — with an LLM configured, the guiding question
  references the student's actual variables (and is asked in the chosen
  language); without one, a built-in template is used. Either way, never a fix.

### Optional: personalized questions via an LLM

Set **any** OpenAI-compatible endpoint. With nothing set, everything still works
on templates.

| Variable | Purpose |
|---|---|
| `TRACEBACK_COACH_LLM_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | API key (any one) |
| `OPENAI_BASE_URL` / `TRACEBACK_COACH_LLM_BASE_URL` | endpoint (any OpenAI-compatible gateway) |
| `OPENAI_MODEL` / `TRACEBACK_COACH_LLM_MODEL` | model id (default `deepseek-chat`) |

Check it live with `%coach_llm`. The model is told to **never** output a fix.

## Notebooks

The package ships demo + lesson notebooks — ready to run, start with
`00_start_here.ipynb`:

- **`00_start_here.ipynb` — run it yourself** (start here, hands-on): the whole
  package end-to-end — collapsible traceback (fold the red wall), recursion-as-a-loop,
  progressive fade, stats, quiz, bilingual EN/中文, LLM, lessons. *Restart Kernel & Run All Cells.*
- **`01_showcase.ipynb` — the full feature tour**: anatomy card, causal
  diagram, recursion-as-a-loop, progressive fade, stats, quiz, bilingual EN/中文,
  LLM-personalized questions, collapsible tracebacks, watch mode, lessons.
- `02_basics_tour.ipynb` — basic tour (nested calls, recursion, watch mode)
- `03_features_tour.ipynb` — fade before/after, stats, quiz, language, LLM toggle
- `lesson_01_names_and_types`, `lesson_02_lists_and_dicts`,
  `lesson_03_functions_and_recursion`, `lesson_04_values_and_math` — short
  beginner Python lessons, each with a broken cell to read and fix.

## Developer guide

```
traceback_coach/
├── __init__.py     # version, load/unload_ipython_extension
├── knowledge.py    # ErrorFamily + 12 English FAMILIES + lookup()      [no IPython]
├── i18n.py         # zh-HK FAMILIES_ZH + bilingual LABELS              [no IPython]
├── _core.py        # parse_traceback, diagrams, question, card, render [no IPython]
├── magics.py       # CoachMagics, post_run_cell hook, display glue     [IPython]
└── static/mermaid.min.js   # vendored, offline
```

- `knowledge.py`, `i18n.py`, `_core.py` import **no IPython** — they're
  unit-testable headless. `magics.py` is the only IPython-facing module.
- **Add an error family:** add an `ErrorFamily(...)` to `FAMILIES` in
  `knowledge.py` (and a zh entry in `i18n.py`). Templates may use `{token}`,
  `{message}`, `{error_type}`, `{line_no}`.
- **Add a language:** add a `FAMILIES_<lang>` + a `LABELS["<lang>"]` map and a
  `lookup(error_type, lang)` branch; thread the lang code through `%coach_lang`.
- **Run tests:** `pip install -e ".[dev]" && pytest -v` (112 tests).
- **Build & verify in a clean env:** `python -m build`, then install the wheel
  in a fresh venv and import (two-venv pattern).

## License

MIT
