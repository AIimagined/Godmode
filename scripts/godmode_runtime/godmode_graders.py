"""A closed vocabulary of deterministic comparators for eval definitions.

An eval that grades its own output with hand-rolled string logic per skill
drifts the moment two authors phrase the same comparison differently -
one writes `expected in actual`, another writes `actual.startswith`, and
"pass" quietly means something different in each file. This module names
the small set of comparisons Godmode's evals actually need and gives each
one exactly one implementation, so a grader name in an eval definition is a
promise about behaviour, not a hint.

The vocabulary is closed on purpose: `grade()` refuses an unknown name
instead of guessing, because a typo in a grader field should fail loudly at
eval-authoring time, not silently grade nothing forever.

`json_match` is the one comparator with a safety property worth stating
twice: invalid JSON on either side NEVER matches, even when both sides are
byte-identical malformed strings. "Matches" means the parsed values are
structurally equal - it does not mean "the grader could not tell and let it
through." A comparator that matches on failure is a comparator an attacker
can satisfy by breaking the output.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from .godmode_errors import GodmodeError


def grade_match(actual: str, expected: str | Iterable[str], *, prefix: bool = False) -> bool:
    """True when `actual` equals `expected`, or equals any one of `expected`.

    `expected` may be a single string or an iterable of candidates (any-of).
    `prefix=True` checks `actual.startswith(candidate)` instead of equality,
    for the case where only the leading shape of the output is asserted.
    """
    candidates = [expected] if isinstance(expected, str) else list(expected)
    if not candidates:
        return False
    if prefix:
        return any(actual.startswith(candidate) for candidate in candidates)
    return any(actual == candidate for candidate in candidates)


def grade_includes(actual: str, expected: str) -> bool:
    """True when `expected` appears anywhere inside `actual`."""
    return expected in actual


def grade_fuzzy(actual: str, expected: str) -> bool:
    """Mutual containment after whitespace/case normalisation.

    True when either normalised string contains the other. Two empty
    strings (after normalisation) are equal, not a vacuous match against
    everything else.
    """

    def normalize(text: str) -> str:
        return " ".join(text.split()).lower()

    left, right = normalize(actual), normalize(expected)
    if not left or not right:
        return left == right
    return left in right or right in left


def grade_json_match(actual: str, expected: str) -> bool:
    """True when `actual` and `expected` parse to structurally equal JSON.

    Key order and surrounding whitespace never matter - only the parsed
    values are compared. Invalid JSON on either side never matches: a
    `json.JSONDecodeError` (or a non-string input) is treated as "no match",
    fail-closed, regardless of what the other side contains.
    """
    try:
        parsed_actual = json.loads(actual)
        parsed_expected = json.loads(expected)
    except (json.JSONDecodeError, TypeError):
        return False
    return parsed_actual == parsed_expected


GRADERS: dict[str, Any] = {
    "match": grade_match,
    "includes": grade_includes,
    "fuzzy": grade_fuzzy,
    "json_match": grade_json_match,
}


def grade(name: str, actual: str, expected: Any, **kwargs: Any) -> bool:
    """Dispatch to a named grader from the closed vocabulary.

    An unknown name is refused rather than guessed at, so a typo in an eval
    definition surfaces as a raised error instead of a comparison that
    silently always fails or always passes.
    """
    try:
        grader = GRADERS[name]
    except KeyError:
        raise GodmodeError(
            f"unknown grader {name!r}; closed vocabulary is {sorted(GRADERS)}"
        ) from None
    return grader(actual, expected, **kwargs)


def _self_check() -> None:
    assert grade_match("gm1.abc", "gm1.abc")
    assert not grade_match("gm1.abc", "gm1.xyz")
    assert grade_match("gm1.abc", "gm1.", prefix=True)
    assert grade_match("beta", ["alpha", "beta", "gamma"])
    assert not grade_match("delta", ["alpha", "beta", "gamma"])
    assert not grade_match("x", [])

    assert grade_includes("the quick fox", "quick")
    assert not grade_includes("the quick fox", "slow")

    assert grade_fuzzy("Retry Backoff", "retry   backoff")
    assert grade_fuzzy("retry", "retry backoff strategy")
    assert not grade_fuzzy("retry", "backoff strategy")
    assert grade_fuzzy("", "")
    assert not grade_fuzzy("", "backoff")

    assert grade_json_match('{"a": 1, "b": 2}', '{"b":2,"a":1}')
    assert grade_json_match(' {"a":1}\n', '{"a": 1}')
    assert not grade_json_match('{"a": 1}', '{"a": 2}')
    # Fail-closed: invalid JSON never matches, even against itself.
    assert not grade_json_match("{not json", "{not json")
    assert not grade_json_match("{not json", '{"a": 1}')
    assert not grade_json_match('{"a": 1}', "{not json")

    assert grade("match", "gm1.abc", "gm1.abc")
    try:
        grade("no-such-grader", "x", "y")
        raise AssertionError("unknown grader name must be refused")
    except GodmodeError:
        pass

    print("godmode_graders self-check OK")


if __name__ == "__main__":
    _self_check()
