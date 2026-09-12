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

**Absent markers mean nothing is editable, not everything.** A file that never
opted in is fully frozen. The alternative fails open, and a guard that fails
open on the most common input is decoration.

**An unclosed start yields no region.** "Editable to end of file" is exactly
what a truncated or half-written marker would produce, so it is refused
instead.
"""
from __future__ import annotations

import re

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
