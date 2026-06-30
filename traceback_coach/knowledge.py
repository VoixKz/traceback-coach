"""Error encyclopedia: maps a Python exception type to teaching content.

No IPython import — fully unit-testable. Template fields may contain the
placeholders {token}, {message}, {error_type}, {line_no}, which are filled by
traceback_coach._core._fill().
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorFamily:
    key: str
    translation: str
    family_summary: str
    read_it_yourself: str
    cause_phrase: str
    example_code: str
    example_explanation: str
    example_avoid: str
    question_template: str


_GENERIC = ErrorFamily(
    key="Error",
    translation="Python stopped because something went wrong: {message}",
    family_summary="An error means Python could not finish running your code.",
    read_it_yourself="Read the LAST line of the traceback first: it names the error type and what went wrong.",
    cause_phrase="Python could not run this line",
    example_code="xs = [1, 2, 3]\nprint(xs[5])   # only indices 0..2 exist",
    example_explanation="Python stops at the first line it cannot run and reports why.",
    example_avoid="Check the values and types on the failing line before running it.",
    question_template="Look at the failing line — what exactly is Python complaining about?",
)

FAMILIES: dict[str, ErrorFamily] = {
    "NameError": ErrorFamily(
        key="NameError",
        translation="Python doesn't recognise the name `{token}` — it was never given a value (or it's a typo).",
        family_summary="you used a name Python has never seen.",
        read_it_yourself="The last line says `name '...' is not defined` — that name is the problem.",
        cause_phrase="name `{token}` was never defined",
        example_code="print(total)   # 'total' was never created",
        example_explanation="Python reads `total`, finds no variable with that name, and stops.",
        example_avoid="Create (assign) the variable before you use it; check spelling and capitalisation.",
        question_template="Where in your code does `{token}` first get a value?",
    ),
    "TypeError": ErrorFamily(
        key="TypeError",
        translation="You combined values whose types don't go together: {message}",
        family_summary="an operation got a type it can't work with (e.g. str + int).",
        read_it_yourself="The message names the clash — read 'unsupported operand' or 'expected ...'.",
        cause_phrase="incompatible types in the operation",
        example_code='age = "5"\nprint(age + 1)   # text + number',
        example_explanation="`age` is text ('5'), so adding the number 1 has no meaning to Python.",
        example_avoid="Convert first, e.g. int(age) + 1, or keep both sides the same type.",
        question_template="What are the types of the two values on the failing line?",
    ),
    "ValueError": ErrorFamily(
        key="ValueError",
        translation="The type was right but the value wasn't allowed: {message}",
        family_summary="right kind of thing, wrong content (e.g. int('abc')).",
        read_it_yourself="The message quotes the bad value — look at what you passed in.",
        cause_phrase="value is not acceptable here",
        example_code='n = int("ten")   # not digits',
        example_explanation="`int()` accepts strings, but only ones that look like whole numbers.",
        example_avoid="Validate or clean the value before converting it.",
        question_template="What exact value reached this line, and is it the form this function expects?",
    ),
    "IndexError": ErrorFamily(
        key="IndexError",
        translation="You asked for a position that doesn't exist in the sequence: {message}",
        family_summary="index out of range (often an off-by-one).",
        read_it_yourself="'list index out of range' means that position is not there.",
        cause_phrase="index is past the end of the sequence",
        example_code="xs = [1, 2, 3]\nprint(xs[3])   # valid indices are 0, 1, 2",
        example_explanation="A list of length 3 has indices 0-2; index 3 is one past the end.",
        example_avoid="Indices start at 0; the last valid one is len(xs) - 1.",
        question_template="How long is the sequence, and what is the largest valid index?",
    ),
    "KeyError": ErrorFamily(
        key="KeyError",
        translation="The key `{token}` isn't in the dictionary.",
        family_summary="you looked up a dict key that isn't there.",
        read_it_yourself="The missing key is shown right after 'KeyError:'.",
        cause_phrase="key `{token}` is not in the dict",
        example_code='d = {"a": 1}\nprint(d["b"])   # there is no "b"',
        example_explanation="`d` has only the key 'a', so looking up 'b' fails.",
        example_avoid="Check with `key in d`, or use d.get(key) for a safe default.",
        question_template="Which keys does the dictionary actually contain right now?",
    ),
    "AttributeError": ErrorFamily(
        key="AttributeError",
        translation="That object has no `{token}`: {message}",
        family_summary="the object doesn't have that method or attribute.",
        read_it_yourself="'... object has no attribute ...' names the type and the missing attribute.",
        cause_phrase="object has no attribute `{token}`",
        example_code='x = "hi"\nx.append("!")   # strings have no .append',
        example_explanation="Strings are immutable and have no `append`; that's a list method.",
        example_avoid="Check the object's real type and which methods that type supports.",
        question_template="What type is that object, and does that type have `{token}`?",
    ),
    "IndentationError": ErrorFamily(
        key="IndentationError",
        translation="The indentation (leading spaces) is off: {message}",
        family_summary="Python groups code by indentation, and it doesn't line up.",
        read_it_yourself="Python's caret (^) points at where the indentation went wrong.",
        cause_phrase="indentation does not line up",
        example_code='def f():\nprint("hi")   # body must be indented',
        example_explanation="The body of def/if/for must be indented under its header.",
        example_avoid="Indent consistently (4 spaces); never mix tabs and spaces.",
        question_template="Which block is this line meant to belong to, and is it indented under it?",
    ),
    "SyntaxError": ErrorFamily(
        key="SyntaxError",
        translation="Python couldn't read this line as valid code: {message}",
        family_summary="the code breaks Python's grammar (missing ':' , ')' , quote...).",
        read_it_yourself="The caret (^) marks where Python got confused; look just before it.",
        cause_phrase="this is not valid Python here",
        example_code="if x == 1\n    print(x)   # missing colon",
        example_explanation="An `if` header must end with a colon `:`.",
        example_avoid="Check for missing colons, brackets, and quotes around the marked spot.",
        question_template="Look just before the ^ — what punctuation might be missing?",
    ),
    "ZeroDivisionError": ErrorFamily(
        key="ZeroDivisionError",
        translation="You divided by zero, which has no result.",
        family_summary="division or % by zero.",
        read_it_yourself="'division by zero' means the divisor was 0 when it ran.",
        cause_phrase="the divisor was 0",
        example_code="n = 0\nprint(10 / n)   # n is 0",
        example_explanation="Dividing by zero is undefined, so Python stops.",
        example_avoid="Check the divisor isn't 0 before dividing.",
        question_template="What value did the divisor hold on this line when it ran?",
    ),
    "ModuleNotFoundError": ErrorFamily(
        key="ModuleNotFoundError",
        translation="Python can't find the module `{token}` to import.",
        family_summary="the import name isn't installed here, or is misspelled.",
        read_it_yourself="\"No module named '...'\" names exactly what it couldn't find.",
        cause_phrase="module `{token}` was not found",
        example_code="import numpyy   # typo for numpy",
        example_explanation="Python searches installed packages and finds nothing by that name.",
        example_avoid="Check the spelling and that the package is installed in this kernel.",
        question_template="Is `{token}` spelled correctly and installed in this kernel?",
    ),
    "RecursionError": ErrorFamily(
        key="RecursionError",
        translation="A function kept calling itself with no stopping point.",
        family_summary="recursion never reached a base case.",
        read_it_yourself="'maximum recursion depth exceeded' means endless self-calls.",
        cause_phrase="no base case stopped the recursion",
        example_code="def f(n):\n    return f(n)   # never stops\nf(3)",
        example_explanation="`f` calls `f` forever; nothing returns without recursing.",
        example_avoid="Add a base case that returns before calling itself, and move toward it.",
        question_template="What condition should stop the recursion, and is it ever reached?",
    ),
    "UnboundLocalError": ErrorFamily(
        key="UnboundLocalError",
        translation="Inside this function, `{token}` is used before it's given a value.",
        family_summary="a local variable was read before assignment (often shadowing a global).",
        read_it_yourself="\"local variable '...' referenced before assignment\" points at the name.",
        cause_phrase="local `{token}` used before assignment",
        example_code="count = 0\ndef inc():\n    count = count + 1   # local 'count' used too early\ninc()",
        example_explanation="Assigning `count` inside `inc` makes it local, so the right-hand `count` has no value yet.",
        example_avoid="Pass values in as parameters, or declare `global`/`nonlocal` deliberately.",
        question_template="Inside the function, where does `{token}` get its first value before it's used?",
    ),
}


def lookup(error_type: str, lang: str = "en") -> ErrorFamily:
    """Return the ErrorFamily for an exception type name, or a generic fallback.

    ImportError (the parent of ModuleNotFoundError) maps to the module family.
    When lang=="zh", the zh-HK translation is returned (falling back to the
    English family for any key not present in FAMILIES_ZH).  The import of
    i18n is deferred inside this branch to avoid a circular import (i18n
    imports ErrorFamily and FAMILIES from this module at the top level).
    """
    if lang == "zh":
        from .i18n import FAMILIES_ZH  # lazy import — avoids circular dependency
        if error_type == "ImportError":
            return FAMILIES_ZH.get("ModuleNotFoundError", FAMILIES["ModuleNotFoundError"])
        return FAMILIES_ZH.get(error_type, FAMILIES.get(error_type, _GENERIC))

    # English path (default) — unchanged behaviour
    if error_type == "ImportError":
        return FAMILIES["ModuleNotFoundError"]
    return FAMILIES.get(error_type, _GENERIC)
