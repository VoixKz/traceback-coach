# Recursion-as-loop diagram + compact native traceback

**Goal:** (A) draw recursion as a visual loop (self-loop for direct recursion, a cycle for mutual) so it's obvious the code calls itself; (B) add an opt-in `%coach_compact` mode that folds Python's huge native traceback (e.g. RecursionError) into a short summary, leaving the Coach card to explain.

**Tech Stack:** Python ≥3.9, IPython ≥8, pytest. Tests: `~/tbc-build/bin/python -m pytest`.

## Global Constraints
- Branch `feature/recursion-loop-compact`. `from __future__ import annotations` in every module.
- `_core.py`/`knowledge.py`/`i18n.py` stay headless (no IPython). No new runtime deps.
- Defaults unchanged: non-recursive diagrams render exactly as today; `%coach_compact` is OFF by default and fully reversible (must never break normal error display).
- TDD per task: failing test → RED → implement → GREEN → commit.

---

### Task A: recursion → loop in `build_mermaid` (`_core.py`)

**Files:** Modify `traceback_coach/_core.py` (`build_mermaid`, maybe a small helper). Test: `tests/test_diagram.py` (append).

**Behavior:** In `build_mermaid`, inspect the frames (chain + break). Detect recursion = some frame *location* occurs ≥2 times (also treat `parsed.error_type == "RecursionError"` as a strong hint). When recursion is detected, render a LOOP instead of the long linear chain:
- **Direct self-recursion** (one location repeats, consecutively): one node `R` for that function (`location (line N)<br/>code`), a self-loop edge `R -->|"calls itself ×{count}"| R`, then `S --> R` and `R -->|breaks| X`. `{count}` = how many times that frame appears.
- **Mutual recursion** (2+ distinct locations repeat, alternating): take the distinct repeating locations in first-seen order (cap at 3), chain them `A --> B (--> C)`, add a back-edge from the last to the first labeled `loops back ×{N}` (N = total frames in the cycle), then `S --> A` and `<last> -->|breaks| X`.
- **Non-recursive:** unchanged (existing linear chain via `_chain_nodes`).
Keep the `💥 {error_type}<br/>{cause}` break node `X` and its red `style X` line in all cases.

- [ ] **Step 1: failing tests** (append to `tests/test_diagram.py`)
```python
def test_direct_recursion_renders_self_loop():
    frames = [Frame("countdown", 2, "return countdown(n - 1)") for _ in range(2990)]
    frames.append(Frame("countdown", 2, "return countdown(n - 1)"))  # break
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return countdown(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    # a node that loops to ITSELF (same id on both ends of an edge)
    import re
    assert re.search(r"(\w+)\s*-->\|[^|]*\|\s*\1", body), "expected a self-loop edge"
    assert "calls itself" in body
    assert "💥" in body and "RecursionError" in body
    assert body.count('["') < 6   # compact, not thousands of nodes

def test_mutual_recursion_renders_cycle():
    frames = []
    for i in range(2000):
        frames.append(Frame("is_even", 2, "return is_odd(n - 1)") if i % 2 == 0
                       else Frame("is_odd", 4, "return is_even(n - 1)"))
    frames.append(Frame("is_even", 2, "return is_odd(n - 1)"))  # break
    p = ParsedError("RecursionError", "maximum recursion depth exceeded", 2,
                    "return is_odd(n - 1)", "", frames)
    body = build_mermaid(p, lookup("RecursionError"))
    assert "is_even" in body and "is_odd" in body
    assert "loops back" in body
    assert body.count('["') <= 6   # the cycle, not 2000 nodes

def test_non_recursive_chain_unchanged():
    # a normal 3-frame chain must still render linearly (no self-loop)
    frames = [Frame("run", 14, "return average_of(scores, [0,1,5])"),
              Frame("average_of", 8, "total += get_item(data, i)"),
              Frame("get_item", 2, "return data[i]")]
    p = ParsedError("IndexError", "list index out of range", 2,
                    "return data[i]", "", frames)
    body = build_mermaid(p, lookup("IndexError"))
    import re
    assert not re.search(r"(\w+)\s*-->\|[^|]*\|\s*\1", body)  # no self-loop
    assert "run" in body and "average_of" in body and "get_item" in body
```

- [ ] **Step 2: RED.** Step 3: implement the recursion detection + loop rendering in `build_mermaid` (reuse `_mm_escape`, `_fill`, the existing `X`/style). Step 4: GREEN + full suite. Step 5: commit `Render recursion as a loop (self-loop / cycle) in the diagram (RED->GREEN)`.

---

### Task B: `%coach_compact` — fold the native traceback (`magics.py`)

**Files:** Modify `traceback_coach/magics.py`. Test: `tests/test_magics.py` (append).

**Behavior:** New line magic `%coach_compact on|off|status` (default off; `_state.compact = False`). When ON, install a custom exception renderer so the kernel prints a SHORT traceback instead of the full one; the Coach card (from `%%coach`/watch) still explains it. When OFF, restore the default. Must be reversible and never break error display.

Implementation guidance:
- Use `self.shell.set_custom_exc((BaseException,), _compact_exc)` to register, and `self.shell.set_custom_exc((), None)`-style restore (store/restore the previous handler; IPython exposes `shell.custom_exceptions`). The handler signature is `def _compact_exc(shell, etype, evalue, tb, tb_offset=None):`.
- The handler prints a compact summary — the exception type + message + the deepest in-cell line + a note like `… full traceback folded by Coach (N frames). The card below explains it. (%coach_compact off to restore) …` — then returns. Wrap the whole handler body in try/except: on ANY error, fall back to `shell.showtraceback()` so errors are never swallowed.
- Compute frame count from the traceback for the "(N frames)" note.
- `unregister(ipython)` (called on `%unload_ext`) must also restore the default handler if compact was on.
- Reset `_state.compact = False` in the `ip` test fixture; restoring the default exc handler in the fixture teardown is also fine.
- Add a BANNER (bulleted) + HELP (no bullet) entry for `%coach_compact`.

- [ ] **Step 1: failing tests** (append to `tests/test_magics.py`)
```python
def test_coach_compact_folds_traceback(ip, capsys):
    ip.run_line_magic("coach_compact", "on")
    ip.run_cell("def f(n):\n    return f(n-1)\nf(3)\n")   # RecursionError
    out = capsys.readouterr().out + capsys.readouterr().err
    # the compact note appears and the output is far shorter than a raw RecursionError
    assert "folded" in out.lower() or "Coach" in out
    assert out.count("return f(n-1)") < 50          # NOT thousands of repeated frames

def test_coach_compact_off_restores_default(ip):
    ip.run_line_magic("coach_compact", "on")
    ip.run_line_magic("coach_compact", "off")
    # default handler restored: a normal error still shows (no crash)
    res = ip.run_cell("print(undef_x)\n")
    assert res.error_in_exec is not None
```
(If asserting on captured traceback text is unreliable in the test shell, assert instead that `M._state.compact` flips and that registering/unregistering the custom exc handler does not raise — keep the test meaningful, not vacuous.)

- [ ] **Step 2: RED.** Step 3: implement. Step 4: GREEN + full suite (must stay pristine; existing error tests unaffected when compact is off). Step 5: commit `Add %coach_compact to fold the native traceback (opt-in) (RED->GREEN)`.

---

## Self-Review
- Non-recursive diagrams unchanged; recursion shows a clear loop. ✓
- `%coach_compact` off by default, reversible, never swallows errors (try/except → default). ✓
- Headless `_core`; no new deps. ✓
