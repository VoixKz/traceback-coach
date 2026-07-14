# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.1] - 2026-07-14

### Fixed
- `%coach_insights` now renders the agent's light Markdown (bold and paragraphs)
  in the review card instead of showing literal `**` asterisks.

## [0.5.0] - 2026-07-14

### Added
- **Cross-session memory (optional, `traceback-coach[hermes]`).** The coach can now
  remember which Python errors you keep struggling with — across kernel restarts —
  backed by an isolated Hermes profile. `%coach_memory on|off|status` toggles it.
  Only error-family names, counts, and dates are stored; never your code.
- **`%coach_insights`** — an on-demand Socratic review of your recurring weaknesses,
  written by the Hermes agent (the one place a provider is ever used).
- **`%coach_forget`** — erase your saved error history.
- Progressive fade and the guiding question now personalize from your cross-session
  history when memory is on (e.g. "you've hit IndexError 9 times now — what's your rule?").
- `04_memory_tour.ipynb` — a demo of the memory engine (runs fully offline).
- This changelog.

### Notes
- Memory is a strictly additive, **optional** backend: with `hermes-acp-sdk` absent
  (the default), the coach behaves exactly as before — no memory, no provider calls.
- The `%coach_insights` review requires Hermes ≥ 0.18 (for `hermes acp` + profile cloning).

## [0.4.2] - 2026-07-02

### Changed
- Active-recall quiz: the dropdown is trimmed to the common error families the
  coach teaches; the free-text field covers everything else.

## [0.4.1] - 2026-07-02

### Added
- Quiz: a free-text field alongside the dropdown, with case-insensitive checking.

### Changed
- Broadened the quiz dropdown.

## [0.4.0] - 2026-07-02

### Added
- Interactive active-recall quiz: pick (or type) the error you expect, hit
  **Submit** to check your guess, then the coach reveals its guiding question.

## [0.3.1] - 2026-07-02

### Fixed
- Quiz no longer leaks the error type before you guess, and honors watch-skip.
- Unified the traceback exception handler across entry points.

## [0.3.0] - 2026-07-01

### Added
- `%coach_compact`: fold the native Python traceback into a collapsible
  `<details>` block (opt-in), keeping the coach card front and center.
- Recursion is now drawn as a loop (self-loop / cycle) in the call-graph diagram.

### Changed
- Independent, self-authored project metadata and a richer README.
- Consistent, polished notebook set (`00_start_here`, `01_showcase`, tours, and
  the beginner lesson notebooks).

## [0.2.0] - 2026-06-30

### Added
- First tagged release. Core coaching: automatic traceback analysis with
  **Socratic guiding questions** (the coach never hands you the fix).
- **Progressive fade** — the coach shows less as you get better at an error
  family — plus `%coach_stats` to see where you struggle.
- `%coach_quiz`: active-recall mode (guess the error before it's revealed).
- `%coach_llm`: optional LLM-personalized guiding questions (offline templates
  by default; no key required).
- Multi-language guidance, English and Traditional Chinese, via `%coach_lang`.
- Call-graph diagram of the failing call stack.
- Beginner Python lesson notebooks (names/types, lists/dicts,
  functions/recursion, values/math).

[Unreleased]: https://github.com/VoixKz/traceback-coach/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.5.1
[0.5.0]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.5.0
[0.4.2]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.4.2
[0.4.1]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.4.1
[0.4.0]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.4.0
[0.3.1]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.3.1
[0.3.0]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.3.0
[0.2.0]: https://github.com/VoixKz/traceback-coach/releases/tag/v0.2.0
