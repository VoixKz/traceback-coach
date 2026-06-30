# traceback-coach

A visual **error-literacy** coach for Jupyter notebooks. When a cell raises, it
turns the traceback into a teaching moment: a plain-language translation, a
**causal diagram** of why it broke, a **worked example**, and **one** guiding
question — so students learn to *read errors themselves* and not repeat them.

**It never shows the fix.** The goal is independence: read the error, understand
the cause, fix it yourself.

Built for the [DIVE](https://github.com/dive4dec) virtual learning environment
(CityU CS1302). Works fully offline; an LLM is optional and only personalizes
the guiding question.

---

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
print(total)        # NameError → the Coach explains it (no fix given)
```

Or watch every cell automatically:

```python
%coach_watch on
xs = [1, 2, 3]
xs[5]               # IndexError is explained the moment it happens
```

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
| `%coach_help`, `%coach_off` | help / stop watching |

## The anatomy card

On any error the Coach shows:

- 🔴 **What happened** — the traceback in one plain sentence
- 📊 **Why it breaks** — a Mermaid flowchart of the call chain *with the code at
  each step*, down to the line that broke (recursion is collapsed to `f ×998`,
  mutual recursion is capped with `… N more calls …`). Falls back to a pure
  HTML/CSS diagram if Mermaid can't render.
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
- **Personalized questions** — with an LLM configured, the guiding question
  references the student's actual variables (and is asked in the chosen
  language); without one, a built-in template is used. Either way, never a fix.

### Optional: personalized questions via an LLM

Set an OpenAI-compatible endpoint (e.g. the DIVE LiteLLM gateway). With nothing
set, everything still works on templates.

| Variable | Purpose |
|---|---|
| `TRACEBACK_COACH_LLM_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | API key (any one) |
| `OPENAI_BASE_URL` / `TRACEBACK_COACH_LLM_BASE_URL` | endpoint (e.g. DIVE LiteLLM gateway) |
| `OPENAI_MODEL` / `TRACEBACK_COACH_LLM_MODEL` | model id (default `deepseek-chat`) |

Check it live with `%coach_llm`. The model is told to **never** output a fix.

## Notebooks

The package ships demo + lesson notebooks (also seeded into the deploy lab):

- `demo.ipynb` — basic tour (nested calls, recursion, watch mode)
- `demo_02_features.ipynb` — fade before/after, stats, quiz, language, LLM toggle
- `lesson_01_names_and_types`, `lesson_02_lists_and_dicts`,
  `lesson_03_functions_and_recursion`, `lesson_04_values_and_math` — short
  CS1302 lessons, each with a broken cell to read and fix.

## Deploy as a shared lab

`deploy/` contains an always-on, hardened setup (Docker + Cloudflare Tunnel +
optional Access, no inbound ports, hashed password) so a class can reach the lab
on your own domain. See **[deploy/README.md](deploy/README.md)** and
`deploy/bootstrap.sh` for the one-command setup.

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
- **Run tests:** `pip install -e ".[dev]" && pytest -v` (84 tests).
- **Build & verify in a clean env:** `python -m build`, then install the wheel
  in a fresh venv and import (two-venv pattern).

## License

MIT
