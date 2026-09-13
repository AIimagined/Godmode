"""Regions a machine-authored edit is allowed to touch, and the rest.

A file declares its editable regions with a pair of marker lines. Everything
outside them is immutable, and immutability is enforced **twice**:

- `redact_immutable` builds the view an editor is shown, with the frozen text
  removed. What is not seen cannot be rewritten.
- `is_span_mutable` refuses a patch whose span is not fully inside one
  declared region. What is seen and edited anyway is still refused.

The second half is the point. A rule stated only in a prompt is a rule the
editor can argue itself out of - it reads the frozen text, decides this case is
different, and edits it. Withholding the text removes the temptation; refusing
the write removes the option.

Two decisions that look like details and are not:

**Absent markers mean opposite things to the two callers, deliberately.**
`check_patch` refuses: it answers "may this exact span be patched", and a file
with no declared editable region has nothing a patch may claim. `edit_verdict`
allows: it answers the pre-tool boundary, where every project predating this
feature has no markers and none may start refusing edits because it shipped.
The first is a library contract, the second is a deployment decision, and
collapsing them would either break every existing project or make the guard
decoration.

**An unclosed start yields no region.** "Editable to end of file" is exactly
what a truncated or half-written marker would produce, so it is refused
instead.
"""
from __future__ import annotations

import re
from typing import Any

#: The marker words. Chosen to be greppable and to say what they do.
MARKER_START_TEXT = "GODMODE-EDITABLE-START"
MARKER_END_TEXT = "GODMODE-EDITABLE-END"

#: What replaces frozen text in the editor's view. It is visible on purpose: a
#: silent elision reads as a complete file and invites a rewrite of the gap.
ELISION = "<... frozen region withheld ...>"

#: Comment openers a mixed repository actually uses. A marker recognised only
#: in Python silently does nothing in the YAML beside it - failing open, which
#: is the wrong direction for a guard.
_OPENERS = r"(?:\#|//|--|<!--|/\*|;|!|%)?"
_CLOSERS = r"(?:-->|\*/)?"


def _marker(word: str) -> re.Pattern[str]:
    return re.compile(
        rf"^[^\S\n]*{_OPENERS}[^\S\n]*{re.escape(word)}[^\S\n]*{_CLOSERS}[^\S\n]*$"
    )


_START = _marker(MARKER_START_TEXT)
_END = _marker(MARKER_END_TEXT)


def _line_offsets(text: str) -> list[tuple[int, int, str]]:
    """(start, end_including_newline, line_without_newline) for every line."""
    out: list[tuple[int, int, str]] = []
    position = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        out.append((position, position + len(line), stripped))
        position += len(line)
    return out


def mutable_ranges(text: str) -> list[tuple[int, int]]:
    """Character ranges that a machine-authored edit may touch.

    Markers are collected in position order and resolved with a stack, so
    nested regions produce correct spans. A pairwise scan that assumes start
    and end alternate is wrong the first time someone nests, and someone will.

    Returns spans sorted by start offset. Nested spans are all returned; use
    `merged_ranges` when you need each byte represented once.
    """
    spans: list[tuple[int, int]] = []
    stack: list[int] = []

    for start, end, line in _line_offsets(text):
        if _START.match(line):
            # The region begins after the marker line, so the marker itself is
            # never inside the editable span and cannot be edited away.
            stack.append(end)
        elif _END.match(line):
            if stack:
                spans.append((stack.pop(), start))

    return sorted(spans)


def merged_ranges(text: str) -> list[tuple[int, int]]:
    """`mutable_ranges` with overlaps and nesting collapsed.

    Redaction uses this: emitting a nested span separately would print the
    inner body twice, and a view that duplicates text is a view an editor will
    faithfully duplicate back.
    """
    merged: list[tuple[int, int]] = []
    for start, end in mutable_ranges(text):
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def redact_immutable(text: str, elision: str = ELISION) -> str:
    """The view an editor is shown: editable bodies only, gaps marked."""
    parts: list[str] = []
    cursor = 0
    for start, end in merged_ranges(text):
        if start > cursor:
            parts.append(elision + "\n")
        parts.append(text[start:end])
        cursor = end
    if cursor < len(text):
        parts.append(elision + "\n")
    return "".join(parts)


def is_span_mutable(text: str, start: int, end: int) -> bool:
    """True when `[start, end)` lies wholly inside one declared region.

    Partial overlap is refusal, not truncation. An edit that half-lands is a
    corrupted file, which is worse than a refused edit.
    """
    if start > end:
        return False
    return any(
        region_start <= start and end <= region_end
        for region_start, region_end in mutable_ranges(text)
    )


class FrozenRegionError(Exception):
    """A patch was refused because its span is not inside a declared region."""


def check_patch(text: str, start: int, end: int) -> None:
    """Raise unless `[start, end)` lies wholly inside one declared region.

    The refusal names the offsets and the regions that were available. A
    refusal that does not say what it protected cannot be acted on, and an
    editor handed a bare "denied" will retry the same edit.
    """
    if is_span_mutable(text, start, end):
        return

    regions = mutable_ranges(text)
    if not regions:
        raise FrozenRegionError(
            f"refusing a patch at [{start}, {end}): this file declares no "
            f"editable region, so all of it is frozen. Add a "
            f"{MARKER_START_TEXT} / {MARKER_END_TEXT} pair around the part "
            f"that may be edited."
        )
    raise FrozenRegionError(
        f"refusing a patch at [{start}, {end}): it is not contained by any "
        f"editable region. Declared editable ranges: {regions}. A patch that "
        f"straddles a boundary is refused rather than trimmed, because a "
        f"half-applied edit corrupts the file."
    )


def edit_verdict(text: str, old_string: str | None) -> dict[str, Any]:
    """Whether a machine-authored edit to `text` may proceed.

    Answers in the shape the fence and design boundaries beside it already use,
    so the pre-tool hook gains a third check rather than a new pattern.

    Three decisions that are not obvious:

    **Opt-in.** A file declaring no region allows everything. Every project
    predating this has no markers, and none may start refusing edits because
    the feature shipped.

    **A whole-file write is refused where regions exist.** A write replaces the
    frozen text along with everything else and carries no span to check, so
    treating "no span" as "nothing to check" would make the guard avoidable by
    choosing the blunter tool.

    **A search string absent from the file is allowed.** That edit cannot
    apply, the host will say so, and refusing here would report a
    frozen-region violation for an edit that was never going to touch anything.

    Every occurrence is checked, not merely the first: an editor replacing all
    matches would otherwise reach frozen text through a token that also appears
    inside the editable region.
    """
    ranges = mutable_ranges(text)
    if not ranges:
        return {"allowed": True,
                "detail": "no editable region is declared in this file",
                "remedy": ""}

    if old_string is None:
        return {
            "allowed": False,
            "detail": ("this file declares an editable region, and a whole-file "
                       "write would replace the frozen text with it"),
            "remedy": (f"edit inside the {MARKER_START_TEXT} / {MARKER_END_TEXT} "
                       f"pair instead of rewriting the file"),
        }

    occurrences: list[int] = []
    start = text.find(old_string)
    while start != -1:
        occurrences.append(start)
        start = text.find(old_string, start + 1)

    if not occurrences:
        return {"allowed": True,
                "detail": "the search text does not occur in this file",
                "remedy": ""}

    outside = [at for at in occurrences
               if not is_span_mutable(text, at, at + len(old_string))]
    if not outside:
        return {"allowed": True,
                "detail": f"every occurrence lies inside a declared editable region",
                "remedy": ""}

    return {
        "allowed": False,
        "detail": (f"{len(outside)} of {len(occurrences)} occurrence(s) of the "
                   f"search text lie outside every declared editable region"),
        "remedy": (f"edit inside the {MARKER_START_TEXT} / {MARKER_END_TEXT} "
                   f"pair, or move the marker if the region is wrong"),
    }
