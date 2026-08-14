#!/usr/bin/env python3
"""Fast pre-tool gate: one table lookup before the full sentinel is paid for.

Every mutating tool call today runs the full hook (`godmode_session_hook.py`)
- archive resolution, chronicle I/O, ceiling checks, the whole classifier -
even for `git status`. That is real, measured latency spent on a decision the
plan's own decision table (`gate_table.json`) already knows the answer to:
a command whose head is on a vetted, host-parity, read-only floor cannot be
anything the full sentinel would refuse or ask about.

This module is the fast R0 check, and nothing else. It NEVER decides `ask` or
`refuse` itself - those decisions, and every side effect that belongs to them
(archive writes, ceiling metering, the scope fence), stay the full hook's job.
`fast_verdict` returns exactly two values: `"allow"` (skip the full hook
entirely, silently) or `"escalate"` (run the full hook, unchanged, and mirror
whatever it says). The asymmetry is deliberate and load-bearing: escalating
when unsure costs one subprocess call; allowing when wrong costs a bypassed
gate. Every ambiguous path in this module resolves to `"escalate"`.

Zero-import boundary: this module imports nothing from `godmode_runtime` -
not even to reuse the segment splitter. `_blanked_segments` below is a LOCAL,
independent copy of the quote/backslash/separator state machine that lives in
`scripts/godmode_runtime/godmode_sentinel.py` as `_raw_segments` (splitting)
fused with `_executable_text` (quote-blanking) - that module is the source of
truth for the real rule; this is a purpose-built duplicate that only needs to
answer "is every segment head floor-clean", not carry the sentinel's full
`Segment` contract. `tests/test_gate_fast.py::SegmentSplitEquivalence` is the
drift guard: it runs both implementations against the same command list and
fails if they ever disagree about where a segment ends.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HOOKS_DIR = Path(__file__).resolve().parent
TABLE_PATH = HOOKS_DIR / "gate_table.json"
FULL_HOOK = HOOKS_DIR / "godmode_session_hook.py"

# Tools the scope fence governs by naming their own target file. They never
# reach the fast path - not because they are always dangerous, but because
# this module has no fence logic of its own and duplicating it here would be
# a second, driftable copy of a check that already exists.
_FENCED_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})

# Tools whose `tool_input` carries a shell command this module knows how to
# read. Anything else - including a read-only tool the host's own matcher
# should never have sent here - escalates rather than guesses.
_SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

# `git branch <name>` (no flag) creates a branch; `git branch -d/-D/-m/-M/
# --delete <name>` deletes or renames one. Both are real mutations reachable
# with nothing but a trailing word after the floor phrase, unlike every other
# entry on this floor (status/log/diff/show/ls-files/rev-parse/rev-list/
# shortlog/describe/blame never mutate regardless of trailing arguments -
# confirmed directly against `classify_action` for representative
# invocations of each before this floor was written). `git remote -v` has
# the same shape one token later: `git remote add/remove/set-url ...` is a
# real mutation that starts with the same first two words. For these two
# phrases only, a trailing token of ANY kind - flag or bare word - escalates
# instead of matching the floor.
_EXACT_ONLY_GIT_PHRASES = frozenset({"git branch", "git remote -v"})

# Quote-aware presence check for an unquoted shell redirect - the same
# operator `godmode_sentinel._REDIRECT` detects, without the target-capture
# group this module never needs (a redirect anywhere disqualifies the whole
# segment; where it points is the full hook's question, not this one's).
_REDIRECT_PRESENT = re.compile(r"(?<![0-9<>])>{1,2}(?!&)")

_SEPARATORS = re.compile(r"[ \t]*(?:\|\||&&|[;|\r\n]|(?<![<>])&)[ \t\r\n]*")


def _blanked_segments(command: str) -> list[str]:
    """Split `command` into shell segments, quotes already blanked.

    One character-level pass, quote- and backslash-aware exactly as the
    sentinel's own scanner is (a backslash escapes the next character except
    inside single quotes; a quoted separator does not split; a quote
    character is replaced with a blank rather than dropped, so token
    positions/spacing survive). This fuses what the source module keeps as
    two passes (`_raw_segments` for splitting, `_executable_text` for
    blanking) into one, because this module never needs the original quoted
    text back - only whether a segment's *unquoted* words are floor-clean.
    """
    segments: list[str] = []
    current: list[str] = []
    # Whether the current segment consumed any raw, non-whitespace input -
    # tracked separately from `current`'s (blanked) content, because a
    # segment that is nothing but a quoted string blanks down to spaces and
    # would otherwise look empty and get silently dropped, even though the
    # shell still runs it (a bare quoted word is still a command word). The
    # source module never has this problem - it keeps quotes intact and
    # checks emptiness on the real text - so this flag is what keeps the
    # two implementations agreeing on segment *count*, which is exactly
    # what `SegmentSplitEquivalence` checks.
    has_content = False
    quote: str | None = None
    index = 0
    length = len(command)
    while index < length:
        character = command[index]
        if character == "\\" and quote != "'" and index + 1 < length:
            blank = quote is not None
            current.append(" " if blank else character)
            current.append(" " if blank else command[index + 1])
            has_content = True
            index += 2
            continue
        if quote:
            current.append(" ")
            has_content = True
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "\"'":
            quote = character
            current.append(" ")
            has_content = True
            index += 1
            continue
        match = _SEPARATORS.match(command, index)
        if match:
            if has_content:
                segments.append("".join(current).strip())
            current = []
            has_content = False
            index = match.end()
            continue
        if character not in " \t\r\n":
            has_content = True
        current.append(character)
        index += 1
    if has_content:
        segments.append("".join(current).strip())
    return segments


def _git_phrases(table: dict[str, Any]) -> list[list[str]] | None:
    floor = table.get("floor")
    if not isinstance(floor, dict):
        return None
    entries = floor.get("claude-code")
    if not isinstance(entries, list):
        return None
    phrases: list[list[str]] = []
    for entry in entries:
        if not isinstance(entry, str):
            return None
        words = entry.split()
        if not words or words[0] != "git":
            continue
        phrases.append(words)
    return phrases


def _segment_floor_clean(tokens: list[str], git_phrases: list[list[str]],
                          read_heads: set[str]) -> bool:
    if not tokens:
        return False
    if tokens[0] != "git":
        return tokens[0] in read_heads
    for phrase in git_phrases:
        n = len(phrase)
        if tokens[:n] != phrase:
            continue
        trailing = tokens[n:]
        if not trailing:
            return True
        return " ".join(phrase) not in _EXACT_ONLY_GIT_PHRASES
    return False


def fast_verdict(payload: dict[str, Any], table: dict[str, Any] | None) -> str:
    """`"allow"` only if every segment of a Bash/PowerShell command is a
    floor-clean read with no redirect and no `-exec`/`-delete`. Anything
    else - malformed input, a malformed table, a fenced tool, an internal
    exception - is `"escalate"`. Never a guess.
    """
    try:
        if not isinstance(table, dict):
            return "escalate"
        if not isinstance(payload, dict):
            return "escalate"
        tool = payload.get("tool_name")
        if not isinstance(tool, str) or tool in _FENCED_TOOLS or tool not in _SHELL_TOOLS:
            return "escalate"
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return "escalate"
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return "escalate"

        read_heads_raw = table.get("read_heads")
        if not isinstance(read_heads_raw, list):
            return "escalate"
        read_heads = {head for head in read_heads_raw if isinstance(head, str)}
        git_phrases = _git_phrases(table)
        if git_phrases is None:
            return "escalate"

        segments = _blanked_segments(command)
        if not segments:
            return "escalate"
        for segment in segments:
            if _REDIRECT_PRESENT.search(segment):
                return "escalate"
            tokens = segment.split()
            if "-exec" in tokens or "-delete" in tokens:
                return "escalate"
            if not _segment_floor_clean(tokens, git_phrases, read_heads):
                return "escalate"
        return "allow"
    except Exception:  # noqa: BLE001 - fail-safe boundary, never crash the gate
        return "escalate"


def _load_table() -> dict[str, Any] | None:
    try:
        data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing/corrupt table escalates, it never crashes
        return None
    return data if isinstance(data, dict) else None


def _parse_payload(raw: bytes) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 - unparsable input escalates to the full hook, which
        return {}       # has its own tolerant `_input()` and will handle it the same way
    return value if isinstance(value, dict) else {}


def main() -> int:
    raw = sys.stdin.buffer.read()
    payload = _parse_payload(raw)
    table = _load_table()
    if fast_verdict(payload, table) == "allow":
        return 0
    # Escalate: re-feed the exact bytes read from stdin to the full hook and
    # mirror its stdout/stderr/exit code verbatim - the fast gate must be
    # invisible to the host on every path except the one it actually skips.
    result = subprocess.run(
        [sys.executable, str(FULL_HOOK), "pre-action"],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
