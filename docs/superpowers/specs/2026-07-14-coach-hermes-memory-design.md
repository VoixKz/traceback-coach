# traceback-coach: Hermes-profile memory — Design

**Date:** 2026-07-14
**Status:** Approved (brainstorm), pending implementation plan

## Goal

Let the coach **remember each learner's weaknesses across sessions** and, on
request, give a **personalized Socratic review** — powered by an isolated Hermes
profile — while keeping the coach fully **offline-first** when Hermes isn't
present.

## Context

Today `_state.stats` (per-error-family counts) lives only in the kernel and
resets on restart; `fade_level()` and `%coach_stats` read it; `make_question()`
builds the guiding question from the current cell only, with no history.

We deliberately route memory through a **Hermes profile** (not a plain local
file): the profile gives an isolated home, a cloned provider (no key handling),
and Hermes's own self-learning memory that accumulates across sessions. This
uses `hermes-acp-sdk >= 0.2` (`HermesClient(profile=..., clone_provider=True)`).

## Non-goals

- Not a core dependency: the coach must run exactly as today with no Hermes.
- No per-error LLM calls. The LLM/provider is touched only on an explicit review.
- No storage of code, variable names, tracebacks, or messages — only error-family
  names, counts, and dates.
- Not a multi-student store: one profile = one learner (each DIVE student has
  their own Jupyter server / home).

## Architecture

New optional module `traceback_coach/hermes_memory.py`, active only when the
`traceback-coach[hermes]` extra is installed **and** a Hermes profile is
reachable. It owns:

- **Capture** (cheap, offline): append/update per-family counts in a file the
  coach owns inside the profile home.
- **Recall** (offline): parse those counts for template personalization and fade.
- **Reflection** (agentic, on demand): open a Hermes session in the profile and
  ask for a Socratic weakness review; Hermes's own memory (`USER.md`) accumulates
  its reflections across sessions — this is the "self-learn like hermes" part.

Thin wiring lives in `magics.py`; `_core.make_question()` gains an optional
memory summary. No other component changes behavior when memory is off.

### Interaction with the existing coach

- `_analyze_and_show()` (in `magics.py`), when memory is on and available, calls
  `mem.record(error_type)` after tallying.
- The **fade count** for a family becomes the memory's cross-session `seen` count
  when memory is on; it falls back to the in-kernel `_state.stats` count when off.
- `make_question()` receives `mem.summary()` so the deterministic template can
  reference a chronic weakness ("you've hit IndexError 9 times…"), with **no LLM**.

## Data model & store

One file the coach owns, in the profile home:

```
<profile_home>/traceback_coach_history.md
```

Format (human- and agent-readable; the coach parses the bullet lines):

```markdown
# Python error history (maintained by traceback-coach)

Each line: <ErrorFamily>: seen <N>, fixed <M>, last <YYYY-MM-DD>

- IndexError: seen 9, fixed 4, last 2026-07-14
- NameError: seen 3, fixed 3, last 2026-07-13
```

- `seen` — total times this family was hit (across sessions).
- `fixed` — times a "Fixed it!" followed for this family.
- `last` — ISO date (YYYY-MM-DD) of the most recent occurrence.

Parser: read lines matching `- <Family>: seen <int>, fixed <int>, last <date>`.
Missing/corrupt file → treat as empty history and recreate on next write.

**Privacy:** only family names + counts + dates are ever written. The file lives
in the profile home, not an arbitrary local path.

## Public API — `hermes_memory.HermesMemory`

```python
class HermesMemory:
    def __init__(self, profile: str = "traceback-coach",
                 store_path: str | None = None,   # injectable for tests
                 command: str | None = None): ...

    def available(self) -> bool:
        """True iff hermes-acp-sdk imports AND a hermes binary resolves."""

    def ensure_profile(self) -> None:
        """Lazily create the profile via clone_provider=True on first use."""

    def record(self, error_type: str, when: str) -> None:
        """Increment `seen` for the family, set `last=when`, persist."""

    def record_fixed(self, error_type: str) -> None:
        """Increment `fixed` for the family, persist."""

    def summary(self) -> dict[str, dict]:
        """Parsed stats: {family: {"seen": int, "fixed": int, "last": str}}."""

    def top_weakness(self) -> tuple[str, int] | None:
        """(family, seen) with the highest seen count, or None."""

    def reflect(self, lang: str = "en") -> str:
        """Agentic review: open a Hermes session in the profile, hand it the
        history, ask for a Socratic weakness review (no fixes). Return the text."""

    def forget(self) -> None:
        """Delete the coach's history file (leaves the profile intact)."""
```

`when` is passed in by the caller (the magic captures the date) so the module
stays free of hidden clocks and is deterministic under test.

### Running async from a Jupyter magic

The SDK is async and the Jupyter kernel already runs an event loop, so
`asyncio.run()` inside a cell raises "event loop already running". `reflect()`
MUST execute the coroutine on a **dedicated background thread with its own event
loop** (a small `_run_async(coro)` helper) and block for the result. Capture and
recall are plain file I/O — no event loop needed.

## Magics (in `magics.py`)

- `%coach_memory on|off|status` — toggle; status reports available / profile /
  store path / why-off.
- `%coach_insights` — run `reflect()` and render the Socratic review. This is the
  only path that uses the provider (the hub's keyless gateway), and it is
  learner-triggered.
- `%coach_forget` — clear the history file after a confirmation.

## Error handling & edge cases

- hermes-acp-sdk not installed, hermes binary missing, or profile creation fails
  → memory silently **off**; the coach behaves exactly as today; `status`
  explains which precondition failed.
- Corrupt/missing history file → empty history, recreated on next write.
- `reflect()` provider failure (gateway down, model error) → a clean message;
  offline counts and template personalization keep working.
- **Open item to verify (does not block design):** whether `~/.hermes` (hence the
  profile) persists across a DIVE server restart. JupyterHub usually persists
  `/home/jovyan`, which would make memory survive; if the home is ephemeral, the
  memory resets on restart. To be checked in the hub, noted as a limitation.

## Testing

`tests/test_hermes_memory.py` (offline; `store_path` injected to a `tmp_path`):

- `record` creates the file and increments `seen`; parse round-trips.
- `record_fixed` increments `fixed`.
- `summary` parses multiple families; corrupt file → empty.
- `top_weakness` returns the highest-seen family.
- `forget` deletes the file.
- `available()` is False when the SDK import fails (simulated).
- `reflect()` with a **mocked** `HermesClient`/session: assert the prompt
  includes the history summary and the returned text is surfaced (no real
  provider call in tests).

`tests/test_magics.py`: `%coach_memory on|off|status`, `%coach_insights` (mocked
`reflect`), and that fade uses the persistent `seen` count when memory is on.

An optional `@pytest.mark.integration` test may hit a real profile+reflection;
deselected by default.

## File structure

- Create: `traceback_coach/hermes_memory.py`
- Modify: `traceback_coach/magics.py` (record hook + 3 magics)
- Modify: `traceback_coach/_core.py` (`make_question` takes an optional summary)
- Modify: `pyproject.toml` (`[project.optional-dependencies] hermes = ["hermes-acp-sdk>=0.2"]`)
- Create: `tests/test_hermes_memory.py`

## Naming (confirmed)

- Optional extra: `traceback-coach[hermes]`
- Module: `traceback_coach/hermes_memory.py`
- Magics: `%coach_memory`, `%coach_insights`, `%coach_forget`
