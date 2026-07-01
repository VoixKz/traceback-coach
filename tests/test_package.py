from __future__ import annotations

import re

import traceback_coach


def test_version_present():
    # Present and a well-formed semver — not pinned to a literal, so routine
    # release bumps don't require touching this test.
    assert re.fullmatch(r"\d+\.\d+\.\d+", traceback_coach.__version__)
