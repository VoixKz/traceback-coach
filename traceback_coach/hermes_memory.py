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
