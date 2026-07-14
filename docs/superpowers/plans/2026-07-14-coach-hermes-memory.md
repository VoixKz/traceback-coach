# Coach Hermes-Profile Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the coach optional, offline-first cross-session memory of a learner's error weaknesses, backed by an isolated Hermes profile, plus an on-demand Socratic weakness review.

**Architecture:** A new module `traceback_coach/hermes_memory.py` owns a small per-error-family store (a markdown file inside the coach's Hermes profile home) and an agentic `reflect()` that drives the Hermes agent via `hermes-acp-sdk`. `magics.py` records into it, reads it for cross-session fade, and exposes three magics. Everything is a no-op when the `[hermes]` extra / a Hermes profile is absent.

**Tech Stack:** Python ≥3.8, IPython, `hermes-acp-sdk>=0.2` (optional extra), pytest.

## Global Constraints

- The coach MUST behave exactly as today when `hermes-acp-sdk` is not installed or no Hermes profile is reachable — memory is a strictly additive, optional backend.
- Only error-family names, counts (`seen`, `fixed`), and ISO dates (`YYYY-MM-DD`) are ever persisted. NEVER code, variable names, tracebacks, or messages.
- No LLM/provider call per error. The provider is touched ONLY by `%coach_insights`.
- Optional extra is named `hermes` → `traceback-coach[hermes]`; module is `traceback_coach/hermes_memory.py`; magics are `%coach_memory`, `%coach_insights`, `%coach_forget`.
- Keep the coach's course/DIVE-free framing: no course names in any user-facing string or docstring.
- Follow the repo pattern: headless logic testable without IPython; `magics.py` is the only IPython-facing layer.
- Run tests with `~/tbc-build/bin/pytest` (the project's build venv).

---

### Task 1: Store layer (`HermesMemory` file store) + `[hermes]` extra

**Files:**
- Create: `traceback_coach/hermes_memory.py`
- Modify: `pyproject.toml` (add the `hermes` optional extra)
- Test: `tests/test_hermes_memory.py`

**Interfaces:**
- Produces: `HermesMemory(profile="traceback-coach", store_path=None, command=None)` with methods `record(error_type: str, when: str) -> None`, `record_fixed(error_type: str) -> None`, `summary() -> dict[str, dict]` (each value `{"seen": int, "fixed": int, "last": str}`), `top_weakness() -> tuple[str, int] | None`, `forget() -> None`. Store file name is `traceback_coach_history.md`. `_CHRONIC_THRESHOLD = 3`.
- When `store_path` is injected, all store methods work with NO Hermes present. `_profile_store_path()` is defined but raises `NotImplementedError` here (Task 2 implements it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hermes_memory.py
from __future__ import annotations

import pytest

from traceback_coach.hermes_memory import HermesMemory


@pytest.fixture
def mem(tmp_path):
    return HermesMemory(store_path=str(tmp_path / "traceback_coach_history.md"))


def test_record_creates_file_and_counts(mem):
    mem.record("IndexError", "2026-07-14")
    mem.record("IndexError", "2026-07-15")
    s = mem.summary()
    assert s["IndexError"]["seen"] == 2
    assert s["IndexError"]["fixed"] == 0
    assert s["IndexError"]["last"] == "2026-07-15"


def test_record_fixed_increments_only_existing(mem):
    mem.record("NameError", "2026-07-14")
    mem.record_fixed("NameError")
    mem.record_fixed("KeyError")  # unknown family: no-op, no crash
    s = mem.summary()
    assert s["NameError"]["fixed"] == 1
    assert "KeyError" not in s


def test_summary_round_trips_via_disk(tmp_path):
    p = str(tmp_path / "traceback_coach_history.md")
    HermesMemory(store_path=p).record("ValueError", "2026-07-14")
    # a fresh instance reads what the first one wrote
    assert HermesMemory(store_path=p).summary()["ValueError"]["seen"] == 1


def test_corrupt_file_reads_as_empty(tmp_path):
    p = tmp_path / "traceback_coach_history.md"
    p.write_text("total garbage, not our format\n", encoding="utf-8")
    assert HermesMemory(store_path=str(p)).summary() == {}


def test_top_weakness(mem):
    mem.record("IndexError", "2026-07-14")
    mem.record("IndexError", "2026-07-14")
    mem.record("NameError", "2026-07-14")
    assert mem.top_weakness() == ("IndexError", 2)


def test_top_weakness_empty_is_none(mem):
    assert mem.top_weakness() is None


def test_forget_deletes_the_file(mem, tmp_path):
    mem.record("IndexError", "2026-07-14")
    mem.forget()
    assert mem.summary() == {}
    assert not (tmp_path / "traceback_coach_history.md").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/tbc-build/bin/pytest tests/test_hermes_memory.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'traceback_coach.hermes_memory'`.

- [ ] **Step 3: Implement the store**

```python
# traceback_coach/hermes_memory.py
"""Optional Hermes-profile memory backend for the coach.

Active only when the `traceback-coach[hermes]` extra is installed AND a Hermes
profile is reachable. Captures per-error-family counts to a markdown file the
coach owns inside the profile home, and (on demand) asks the Hermes agent for a
Socratic weakness review. The coach works exactly as before when this backend is
unavailable.

Privacy: only error-family names, counts, and ISO dates are ever written — never
code, variable names, tracebacks, or messages.
"""
from __future__ import annotations

import re
from pathlib import Path

_PROFILE = "traceback-coach"
_STORE_NAME = "traceback_coach_history.md"
_CHRONIC_THRESHOLD = 3

_HEADER = (
    "# Python error history (maintained by traceback-coach)\n\n"
    "Each line: <ErrorFamily>: seen <N>, fixed <M>, last <YYYY-MM-DD>\n\n"
)
_LINE_RE = re.compile(
    r"^- (?P<fam>\w+): seen (?P<seen>\d+), fixed (?P<fixed>\d+), last (?P<last>\S+)\s*$"
)


class HermesMemory:
    """Per-error-family memory stored in the coach's Hermes profile home.

    Pass ``store_path`` to point at an explicit file (used by tests and when the
    caller already knows the profile home); otherwise the path is resolved from
    the profile via the SDK (see :meth:`_profile_store_path`).
    """

    def __init__(self, profile: str = _PROFILE, store_path: str | None = None,
                 command: str | None = None) -> None:
        self._profile = profile
        self._command = command
        self._store_path = Path(store_path) if store_path else None

    # ── store: pure file I/O, no Hermes needed ───────────────────────────
    def _resolve_store_path(self) -> Path:
        if self._store_path is None:
            self._store_path = self._profile_store_path()
        return self._store_path

    def _profile_store_path(self) -> Path:
        # Implemented in Task 2 (resolve the profile home via the SDK).
        raise NotImplementedError

    def _read(self) -> dict[str, dict]:
        path = self._resolve_store_path()
        stats: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                m = _LINE_RE.match(line.strip())
                if m:
                    stats[m["fam"]] = {
                        "seen": int(m["seen"]),
                        "fixed": int(m["fixed"]),
                        "last": m["last"],
                    }
        return stats

    def _write(self, stats: dict[str, dict]) -> None:
        path = self._resolve_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [_HEADER]
        for fam in sorted(stats):
            s = stats[fam]
            lines.append(
                f"- {fam}: seen {s['seen']}, fixed {s['fixed']}, last {s['last']}\n"
            )
        path.write_text("".join(lines), encoding="utf-8")

    def summary(self) -> dict[str, dict]:
        """{family: {"seen": int, "fixed": int, "last": "YYYY-MM-DD"}}."""
        return self._read()

    def record(self, error_type: str, when: str) -> None:
        stats = self._read()
        s = stats.get(error_type) or {"seen": 0, "fixed": 0, "last": when}
        s["seen"] += 1
        s["last"] = when
        stats[error_type] = s
        self._write(stats)

    def record_fixed(self, error_type: str) -> None:
        stats = self._read()
        if error_type in stats:
            stats[error_type]["fixed"] += 1
            self._write(stats)

    def top_weakness(self) -> tuple[str, int] | None:
        stats = self._read()
        if not stats:
            return None
        fam = max(stats, key=lambda k: stats[k]["seen"])
        return (fam, stats[fam]["seen"])

    def forget(self) -> None:
        path = self._resolve_store_path()
        if path.exists():
            path.unlink()
```

- [ ] **Step 4: Add the `hermes` optional extra**

In `pyproject.toml`, change the `[project.optional-dependencies]` block from:

```toml
[project.optional-dependencies]
dev = ["pytest", "jupyterlab"]
```
to:
```toml
[project.optional-dependencies]
dev = ["pytest", "jupyterlab"]
hermes = ["hermes-acp-sdk>=0.2"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `~/tbc-build/bin/pytest tests/test_hermes_memory.py -q`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add traceback_coach/hermes_memory.py tests/test_hermes_memory.py pyproject.toml
git commit -m "feat(memory): per-error-family store for the coach (offline file layer)"
```

---

### Task 2: Availability + profile provisioning

**Files:**
- Modify: `traceback_coach/hermes_memory.py`
- Test: `tests/test_hermes_memory.py`

**Interfaces:**
- Consumes: `HermesMemory` from Task 1.
- Produces: `available() -> bool` (True iff `hermes_acp_sdk` imports AND a `hermes` binary resolves), `ensure_profile() -> None` (lazily create the profile via `clone_provider=True`), and a real `_profile_store_path()` that returns `<profile_home>/traceback_coach_history.md`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_hermes_memory.py
def test_available_false_when_sdk_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "hermes_acp_sdk" or name.startswith("hermes_acp_sdk."):
            raise ImportError("no sdk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert HermesMemory().available() is False


def test_profile_store_path_uses_profile_home(monkeypatch, tmp_path):
    # Stub the SDK's ProfileManager so no real Hermes is needed.
    class FakePM:
        def __init__(self, *a, **k):
            pass

        def ensure_profile(self, name, clone_provider=False):
            return None

        def get_env(self, name):
            return {"HERMES_HOME": str(tmp_path / "profiles" / "app-traceback-coach")}

    import traceback_coach.hermes_memory as hm
    monkeypatch.setattr(hm, "_load_profile_manager", lambda command: FakePM())
    p = HermesMemory()._profile_store_path()
    assert p == tmp_path / "profiles" / "app-traceback-coach" / "traceback_coach_history.md"
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/tbc-build/bin/pytest tests/test_hermes_memory.py -q -k "available or profile_store_path"`
Expected: FAIL — `NotImplementedError` (from `_profile_store_path`) and `AttributeError: 'HermesMemory' object has no attribute 'available'`.

- [ ] **Step 3: Implement availability + provisioning**

Add these imports near the top of `hermes_memory.py` (below the existing `from pathlib import Path`):

```python
import shutil
```

Add a module-level helper (below the regex constants) so tests can stub the SDK:

```python
def _load_profile_manager(command: str | None):
    """Import the SDK's ProfileManager lazily. Raises ImportError if absent."""
    from hermes_acp_sdk import ProfileManager  # optional dependency

    return ProfileManager(
        hermes_path=command or "hermes",
        auto_prefix=True,  # -> profile "app-traceback-coach"
    )
```

Add these methods to `HermesMemory` (below `__init__`):

```python
    def available(self) -> bool:
        """True iff the SDK imports and a `hermes` binary can be found."""
        try:
            import hermes_acp_sdk  # noqa: F401
        except Exception:
            return False
        return bool(self._command or shutil.which("hermes"))

    def ensure_profile(self) -> None:
        """Create the coach's profile (cloning the host provider) if needed."""
        mgr = _load_profile_manager(self._command)
        mgr.ensure_profile(self._profile, clone_provider=True)
```

Replace the `_profile_store_path` stub with:

```python
    def _profile_store_path(self) -> Path:
        mgr = _load_profile_manager(self._command)
        mgr.ensure_profile(self._profile, clone_provider=True)
        home = mgr.get_env(self._profile)["HERMES_HOME"]
        return Path(home) / _STORE_NAME
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/tbc-build/bin/pytest tests/test_hermes_memory.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add traceback_coach/hermes_memory.py tests/test_hermes_memory.py
git commit -m "feat(memory): availability check + lazy profile provisioning (clone_provider)"
```

---

### Task 3: Agentic reflection (`reflect()`)

**Files:**
- Modify: `traceback_coach/hermes_memory.py`
- Test: `tests/test_hermes_memory.py`

**Interfaces:**
- Consumes: `HermesMemory`, `summary()` from Tasks 1–2.
- Produces: `reflect(lang: str = "en") -> str` — builds a prompt from the history summary, drives the Hermes agent via the SDK on a background thread (Jupyter already owns the main event loop), returns the agent's text. Empty history → a plain "not enough history yet" line without calling the agent.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_hermes_memory.py
def test_reflect_prompts_agent_with_history_and_returns_text(monkeypatch, tmp_path):
    mem = HermesMemory(store_path=str(tmp_path / "traceback_coach_history.md"))
    mem.record("IndexError", "2026-07-14")

    captured = {}

    async def fake_drive(prompt, profile, command):
        captured["prompt"] = prompt
        captured["profile"] = profile
        return "Focus on off-by-one indexing. What is the last valid index?"

    import traceback_coach.hermes_memory as hm
    monkeypatch.setattr(hm, "_drive_agent", fake_drive)

    out = mem.reflect(lang="en")
    assert "IndexError" in captured["prompt"]        # history reached the agent
    assert captured["profile"] == "traceback-coach"
    assert "off-by-one" in out


def test_reflect_empty_history_skips_agent(tmp_path):
    mem = HermesMemory(store_path=str(tmp_path / "traceback_coach_history.md"))
    out = mem.reflect(lang="en")
    assert "history" in out.lower()  # a friendly "no history yet" message
```

- [ ] **Step 2: Run to verify it fails**

Run: `~/tbc-build/bin/pytest tests/test_hermes_memory.py -q -k reflect`
Expected: FAIL — `AttributeError: 'HermesMemory' object has no attribute 'reflect'`.

- [ ] **Step 3: Implement `reflect()` + the async driver + thread helper**

Add imports near the top of `hermes_memory.py`:

```python
import asyncio
import threading
```

Add the module-level async driver + a sync thread-runner (below `_load_profile_manager`):

```python
async def _drive_agent(prompt: str, profile: str, command: str | None) -> str:
    """Open a Hermes session in `profile` and return the agent's text answer."""
    from hermes_acp_sdk import HermesClient, AgentText

    kwargs = {"profile": profile, "clone_provider": True, "auto_prefix": True}
    if command:
        kwargs["command"] = command
    async with HermesClient(**kwargs) as hermes:
        async with hermes.session() as session:
            chunks: list[str] = []
            async for event in session.prompt(prompt):
                if isinstance(event, AgentText):
                    chunks.append(event.text)
            return "".join(chunks).strip()


def _run_async(coro) -> str:
    """Run `coro` to completion even when a Jupyter event loop is already
    running: execute it on a dedicated thread with its own loop and block."""
    result: dict[str, object] = {}

    def runner():
        loop = asyncio.new_event_loop()
        try:
            result["value"] = loop.run_until_complete(coro)
        except Exception as exc:  # surface the failure to the caller
            result["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=runner)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result["value"]  # type: ignore[return-value]
```

Add the `reflect` method to `HermesMemory` (below `top_weakness`):

```python
    def _build_reflect_prompt(self, lang: str) -> str:
        stats = self._read()
        lines = [
            f"- {fam}: seen {s['seen']} times, fixed {s['fixed']}"
            for fam, s in sorted(stats.items(), key=lambda kv: -kv[1]["seen"])
        ]
        history = "\n".join(lines)
        reply_lang = "Traditional Chinese" if lang == "zh" else "English"
        return (
            "You are a Socratic Python coach. Here is a learner's error history "
            "(most frequent first):\n"
            f"{history}\n\n"
            "In 3-4 sentences, name their biggest weakness and ask ONE guiding "
            "question that helps them self-correct next time. Do NOT give the fix "
            f"or any code. Reply in {reply_lang}."
        )

    def reflect(self, lang: str = "en") -> str:
        """On-demand agentic weakness review. Uses the provider (once)."""
        if not self._read():
            return ("Not enough error history yet — keep coding and the coach "
                    "will learn where you struggle.")
        prompt = self._build_reflect_prompt(lang)
        return _run_async(_drive_agent(prompt, self._profile, self._command))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/tbc-build/bin/pytest tests/test_hermes_memory.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add traceback_coach/hermes_memory.py tests/test_hermes_memory.py
git commit -m "feat(memory): on-demand agentic weakness review (reflect) via the SDK"
```

---

### Task 4: Offline chronic-weakness line in the template question

**Files:**
- Modify: `traceback_coach/_core.py` (`make_question`, `build_card`)
- Modify: `traceback_coach/i18n.py` (add a `chronic` label to `LABELS` en + zh)
- Test: `tests/test_core.py` (or the existing question test module)

**Interfaces:**
- Consumes: existing `make_question(parsed, family, cell_source="", llm=None, lang="en")` and `build_card(parsed, cell_source="", llm=None, lang="en")`.
- Produces: both gain a trailing `seen_count: int = 0` parameter. When `seen_count >= 3` and the deterministic template is used (no LLM answer), a localized chronic-weakness sentence is appended. Existing callers/tests that omit `seen_count` are unaffected (default 0).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core.py  (add)
from traceback_coach._core import make_question, parse_traceback


def _parsed_index_error():
    try:
        [][5]
    except IndexError as e:
        return parse_traceback(type(e), e, e.__traceback__, "[][5]")


def test_make_question_adds_chronic_line_when_repeated():
    from traceback_coach.knowledge import lookup
    parsed = _parsed_index_error()
    fam = lookup("IndexError")
    q = make_question(parsed, fam, cell_source="[][5]", llm=lambda *a: "",
                      seen_count=9)
    assert "9" in q  # references how many times


def test_make_question_no_chronic_line_below_threshold():
    from traceback_coach.knowledge import lookup
    parsed = _parsed_index_error()
    fam = lookup("IndexError")
    q = make_question(parsed, fam, cell_source="[][5]", llm=lambda *a: "",
                      seen_count=1)
    assert "1 times" not in q and "9" not in q
```

- [ ] **Step 2: Run to verify it fails**

Run: `~/tbc-build/bin/pytest tests/test_core.py -q -k chronic`
Expected: FAIL — `make_question() got an unexpected keyword argument 'seen_count'`.

- [ ] **Step 3: Add the localized label**

In `traceback_coach/i18n.py`, add a `"chronic"` key to each language in `LABELS`. Find the `LABELS = {` dict; add to the `"en"` sub-dict:

```python
        "chronic": "You've hit {error_type} {n} times now — what's your rule for avoiding it?",
```

and to the `"zh"` sub-dict:

```python
        "chronic": "你已經遇到 {error_type} {n} 次了——你避免它的規則是什麼？",
```

- [ ] **Step 4: Thread `seen_count` through `_core`**

In `traceback_coach/_core.py`, change `make_question`'s signature and template branch:

```python
def make_question(parsed: ParsedError, family: ErrorFamily,
                  cell_source: str = "", llm=None, lang: str = "en",
                  seen_count: int = 0) -> str:
    """LLM question if available, else the deterministic template."""
    fn = llm if llm is not None else llm_question
    try:
        n = len(inspect.signature(fn).parameters)
        question = fn(parsed, cell_source, lang) if n >= 3 else fn(parsed, cell_source)
    except Exception:
        question = ""
    if question:
        return question.strip()
    q = _fill(family.question_template, parsed)
    if seen_count >= 3:
        from .i18n import LABELS
        chronic = LABELS.get(lang, LABELS["en"]).get("chronic", "")
        if chronic:
            q = q + " " + chronic.replace("{error_type}", parsed.error_type).replace("{n}", str(seen_count))
    return q
```

Then thread `seen_count` through `build_card`. Find `def build_card(parsed: ParsedError, cell_source: str = "", llm=None,` and add `seen_count: int = 0` to its signature, and pass it where it calls `make_question(...)`:

```python
def build_card(parsed: ParsedError, cell_source: str = "", llm=None,
               lang: str = "en", seen_count: int = 0) -> CardData:
    ...
    question = make_question(parsed, family, cell_source, llm=llm, lang=lang,
                             seen_count=seen_count)
    ...
```

(Keep the rest of `build_card` unchanged; only the signature and the
`make_question(...)` call gain `seen_count`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `~/tbc-build/bin/pytest tests/test_core.py -q && ~/tbc-build/bin/pytest -q`
Expected: PASS — the two new tests pass and the full suite stays green.

- [ ] **Step 6: Commit**

```bash
git add traceback_coach/_core.py traceback_coach/i18n.py tests/test_core.py
git commit -m "feat(memory): offline chronic-weakness line in the template question"
```

---

### Task 5: Wire memory into the magics layer

**Files:**
- Modify: `traceback_coach/magics.py`
- Test: `tests/test_magics.py`

**Interfaces:**
- Consumes: `HermesMemory` (Tasks 1–3), `build_card(..., seen_count=...)` (Task 4).
- Produces: `_State.memory` (a `HermesMemory | None`), `_State.memory_on` (bool); `_analyze_and_show` records + drives fade from cross-session `seen`; the fix hook records `record_fixed`; magics `%coach_memory`, `%coach_insights`, `%coach_forget`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_magics.py  (add)
import datetime

import traceback_coach.magics as magics
from traceback_coach.hermes_memory import HermesMemory


class _FakeMem:
    def __init__(self):
        self.recorded = []
        self.fixed = []
        self._summary = {}

    def available(self):
        return True

    def record(self, et, when):
        self.recorded.append((et, when))
        self._summary.setdefault(et, {"seen": 0, "fixed": 0, "last": when})
        self._summary[et]["seen"] += 1

    def record_fixed(self, et):
        self.fixed.append(et)

    def summary(self):
        return self._summary

    def reflect(self, lang="en"):
        return "REFLECTION TEXT"


def test_analyze_records_into_memory_when_on(monkeypatch):
    fake = _FakeMem()
    monkeypatch.setattr(magics._state, "memory", fake, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", True, raising=False)
    monkeypatch.setattr(magics._state, "last_error", None, raising=False)
    monkeypatch.setattr(magics, "display", lambda *a, **k: None)
    try:
        [][5]
    except IndexError as e:
        magics._analyze_and_show(type(e), e, e.__traceback__, "[][5]")
    assert fake.recorded and fake.recorded[0][0] == "IndexError"


def test_memory_off_does_not_record(monkeypatch):
    fake = _FakeMem()
    monkeypatch.setattr(magics._state, "memory", fake, raising=False)
    monkeypatch.setattr(magics._state, "memory_on", False, raising=False)
    monkeypatch.setattr(magics._state, "last_error", None, raising=False)
    monkeypatch.setattr(magics, "display", lambda *a, **k: None)
    try:
        {}["x"]
    except KeyError as e:
        magics._analyze_and_show(type(e), e, e.__traceback__, '{}["x"]')
    assert fake.recorded == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/tbc-build/bin/pytest tests/test_magics.py -q -k "records_into_memory or memory_off"`
Expected: FAIL — `_analyze_and_show` does not touch `_state.memory` yet.

- [ ] **Step 3: Add memory state + a date helper**

In `traceback_coach/magics.py`, add to `_State.__init__` (after `self.compact = False`):

```python
        self.memory = None        # HermesMemory | None
        self.memory_on = False    # recording into the profile store
```

Add a module-level helper near the other module functions (e.g. below `_LLM = llm_question`):

```python
import datetime as _datetime


def _today() -> str:
    return _datetime.date.today().isoformat()
```

- [ ] **Step 4: Record + drive fade from memory in `_analyze_and_show`**

Replace the tally/fade block in `_analyze_and_show` (currently lines that do
`if tally: _state.stats[...] = ...` through `card = build_card(...)`) with:

```python
    if tally:  # re-explaining the same error must not inflate the stats/fade
        _state.stats[parsed.error_type] = _state.stats.get(parsed.error_type, 0) + 1
        if _state.memory_on and _state.memory is not None:
            try:
                _state.memory.record(parsed.error_type, _today())
            except Exception:
                pass  # memory must never break the coach
    seen = _state.stats.get(parsed.error_type, 1)
    if _state.memory_on and _state.memory is not None:
        try:
            seen = _state.memory.summary().get(parsed.error_type, {}).get("seen", seen)
        except Exception:
            pass
    level = fade_level(seen, _state.level_override)
    card = build_card(parsed, cell_source, llm=_LLM, lang=lang, seen_count=seen)
```

- [ ] **Step 5: Record fixes in the post-run hook**

In `_post_run_cell_hook`, change the `elif _state.pending_fix:` branch to also
record the fix:

```python
    elif _state.pending_fix:
        _state.pending_fix = False
        if (_state.memory_on and _state.memory is not None
                and _state.last_error is not None):
            try:
                _state.memory.record_fixed(_state.last_error[0].__name__)
            except Exception:
                pass
        _show_fixed(lang=_state.lang)
```

- [ ] **Step 6: Add the three magics**

Add these methods inside the `CoachMagics` class (next to the other `@line_magic`
methods):

```python
    @line_magic
    def coach_memory(self, line):
        arg = line.strip().lower()
        if _state.memory is None:
            from .hermes_memory import HermesMemory
            _state.memory = HermesMemory()
        if arg == "on":
            if _state.memory.available():
                _state.memory_on = True
                print("🧭  Memory on — I'll remember your error weaknesses across sessions.")
            else:
                _state.memory_on = False
                print("🧭  Memory needs `pip install traceback-coach[hermes]` and a Hermes profile. Staying off.")
        elif arg == "off":
            _state.memory_on = False
            print("🧭  Memory off (nothing recorded).")
        else:
            state = "on" if _state.memory_on else "off"
            avail = "yes" if _state.memory.available() else "no (needs [hermes] + Hermes)"
            print(f"🧭  Memory: {state}  ·  available: {avail}")

    @line_magic
    def coach_insights(self, line):
        if not (_state.memory_on and _state.memory is not None):
            print("🧭  Turn memory on first: %coach_memory on")
            return
        try:
            text = _state.memory.reflect(lang=_state.lang)
        except Exception as exc:
            print(f"🧭  Couldn't reach the agent for a review ({exc}). Your history is still saved.")
            return
        display(HTML(
            "<div style='background:#eef2ff;border-left:4px solid #6366f1;"
            "padding:10px 14px;margin:8px 0;border-radius:4px;font-size:14px;"
            f"white-space:pre-wrap'>{text}</div>"
        ))

    @line_magic
    def coach_forget(self, line):
        if _state.memory is None or not _state.memory_on:
            print("🧭  Memory is off — nothing to forget.")
            return
        try:
            _state.memory.forget()
            print("🧭  Forgot your saved error history.")
        except Exception as exc:
            print(f"🧭  Couldn't clear history ({exc}).")
```

- [ ] **Step 7: Auto-detect memory on load**

In `register(ipython)`, after `ipython.register_magics(CoachMagics)`, initialize
memory (auto-on when available):

```python
    from .hermes_memory import HermesMemory
    _state.memory = HermesMemory()
    _state.memory_on = _state.memory.available()
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `~/tbc-build/bin/pytest tests/test_magics.py -q && ~/tbc-build/bin/pytest -q`
Expected: PASS — new magics tests pass and the full suite stays green.

- [ ] **Step 9: Commit**

```bash
git add traceback_coach/magics.py tests/test_magics.py
git commit -m "feat(memory): wire Hermes-profile memory into the magics (record, fade, insights)"
```

---

## Self-Review

**Spec coverage:**
- Optional backend / offline-first → Global Constraints + Task 5 (`memory_on` gates everything; `available()` in Task 2). ✓
- Store format + privacy → Task 1. ✓
- Capture (cheap) + offline recall (fade + template) → Tasks 1, 4, 5. ✓
- Agentic reflection on demand (`%coach_insights`) → Task 3 + Task 5. ✓
- Magics `%coach_memory|insights|forget` → Task 5. ✓
- Async-in-Jupyter handled → Task 3 (`_run_async` background thread). ✓
- Fade uses cross-session `seen` → Task 5 Step 4. ✓
- `[hermes]` extra → Task 1 Step 4. ✓
- Open item (home persistence in DIVE) is a runtime verification, not code — correctly omitted from tasks.

**Placeholder scan:** none — every code step shows full code; the one `NotImplementedError` (`_profile_store_path` in Task 1) is intentional and replaced in Task 2.

**Type consistency:** `record(error_type, when)`, `record_fixed(error_type)`, `summary() -> {fam: {seen,fixed,last}}`, `reflect(lang)`, `available()`, `top_weakness()`, `seen_count` param — used identically across Tasks 1–5. `_drive_agent(prompt, profile, command)` and `_load_profile_manager(command)` signatures match their call sites and test stubs.
