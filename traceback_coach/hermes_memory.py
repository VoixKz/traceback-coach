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

import asyncio
import re
import shutil
import threading
from pathlib import Path

_PROFILE = "traceback-coach"
_STORE_NAME = "traceback_coach_history.md"

_HEADER = (
    "# Python error history (maintained by traceback-coach)\n\n"
    "Each line: <ErrorFamily>: seen <N>, fixed <M>, last <YYYY-MM-DD>\n\n"
)
_LINE_RE = re.compile(
    r"^- (?P<fam>\w+): seen (?P<seen>\d+), fixed (?P<fixed>\d+), last (?P<last>\S+)\s*$"
)


def _load_profile_manager(command: str | None):
    """Import the SDK's ProfileManager lazily. Raises ImportError if absent."""
    from hermes_acp_sdk import ProfileManager  # optional dependency

    return ProfileManager(
        hermes_path=command or "hermes",
        auto_prefix=True,  # -> profile "app-traceback-coach"
    )


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
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(coro)
        except Exception as exc:  # surface the failure to the caller
            result["error"] = exc
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass  # shutdown must never mask the real result/error
            loop.close()

    t = threading.Thread(target=runner)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result["value"]  # type: ignore[return-value]


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

    # ── store: pure file I/O, no Hermes needed ───────────────────────────
    def _resolve_store_path(self) -> Path:
        if self._store_path is None:
            self._store_path = self._profile_store_path()
        return self._store_path

    def _profile_store_path(self) -> Path:
        mgr = _load_profile_manager(self._command)
        mgr.ensure_profile(self._profile, clone_provider=True)
        home = mgr.get_env(self._profile)["HERMES_HOME"]
        return Path(home) / _STORE_NAME

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

    def forget(self) -> None:
        path = self._resolve_store_path()
        if path.exists():
            path.unlink()
