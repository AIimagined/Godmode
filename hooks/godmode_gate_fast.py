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
# a second, driftable copy of a check that already exists. CX-2 adds Codex's
# `apply_patch` and Grok's `write`/`search_replace` (Addendum 6's tool map,
# `scripts/godmode_runtime/godmode_hostevent.py`'s adapters) - same reasoning,
# same escalate-not-guess default. Grok's `write` is lowercase and therefore
# a distinct string from Claude's `Write` - both are listed.
_FENCED_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "apply_patch",
                          "write", "search_replace"})

# Tools whose `tool_input` carries a shell command this module knows how to
# read. Anything else - including a read-only tool the host's own matcher
# should never have sent here - escalates rather than guesses. CX-2 adds
# Codex's `shell_command` and Grok's `run_terminal_command` (Addendum 6).
_SHELL_TOOLS = frozenset({"Bash", "PowerShell", "shell_command",
                          "run_terminal_command"})

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

# `git log`/`git diff`/`git show` never mutate through a bare positional
# argument the way `branch` does, but they DO carry a real write-to-file
# flag (`--output=<file>` / `--output <file>` / `-o <file>`, inherited from
# the diff-formatting machinery all three share) that writes a file with no
# shell redirect operator involved - invisible to `_REDIRECT_PRESENT`.
# Review round 1 (task-6-review.md, Critical finding 2) reproduced this live:
# `classify_action("git log --output=/tmp/x")` is R0 in the full sentinel
# TODAY too (a real, separately-tracked gap in the full sentinel, being
# fixed in the sentinel lane per the changelog fragment) - which meant the
# one-directional equivalence test passed even though this floor entry
# permits a real, permanent, unrecorded write. Table-driven (not
# hardcoded) so Task 5's generator can extend or correct it without a code
# change here: `table["flag_denylist"][<phrase>]` names the flags a
# floor-clean match for that exact phrase must not carry, checked against
# the part of each trailing token before any `=` (so `--output`,
# `--output=/tmp/x`, and a bare `-o` all match the same bare-flag key).
# `git branch`/`git remote -v` are exact-match-only already (no trailing
# token permitted at all) and never consult this table, since the true
# fix there is "no argument", not "no denylisted flag".

# Quote-aware presence check for an unquoted shell redirect - the same
# operator `godmode_sentinel._REDIRECT` detects, without the target-capture
# group this module never needs (a redirect anywhere disqualifies the whole
# segment; where it points is the full hook's question, not this one's).
#
# Synced with `godmode_sentinel._REDIRECT`'s own fix (task-3-4-review.md
# Critical): the lookbehind used to also exclude a digit immediately before
# `>`, which was meant to keep `2>&1` (fd duplication) from matching but
# also blinded this check to `1>out.txt`/`2>err.log`/`0>f` - real,
# digit-qualified file writes, invisible here exactly as they were in the
# full sentinel. `(?!&)` alone already excludes fd-duplication (the `&`
# immediately after `>` is what makes it a duplication, not a write), so the
# digit exclusion added nothing `(?!&)` didn't already cover.
_REDIRECT_PRESENT = re.compile(r"(?<![<>])>{1,2}(?!&)")

# S12-B (corpus-driven widening, 2026-08-29): a redirect whose target is
# exactly /dev/null mutates nothing - `ls > /dev/null` and `grep -c x f
# 2>/dev/null` are R0 read-only-inspection in the full sentinel (verified
# live before this rule was added), yet the blunt redirect check above
# escalated every one, and they are among the most frequent shapes in the
# corpus's expected-allow set. The match is blanked BEFORE the per-segment
# redirect check, so any remaining `>` still escalates; the optional
# leading digit keeps `2>/dev/null` whole (in the pathological `abc2>` case
# the digit lexes with the word, but eating it here only shortens a token
# in a command that still writes nowhere). `>&` duplication was never
# matched by the check above; `&>/dev/null` still escalates (its `&` is a
# separator to this module and the shapes differ across shells).
_NULL_REDIRECT = re.compile(r"(?:^|(?<=\s))\d?>{1,2}\s*/dev/null(?=$|[\s;&|])")

_SEPARATORS = re.compile(r"[ \t]*(?:\|\||&&|[;|\r\n]|(?<![<>])&)[ \t\r\n]*")

# Final review, Critical finding C1: `$(...)`, backtick, `<(...)`, `>(...)`
# command/process substitution runs a second, entirely unexamined command
# with none of this module's checks ever seeing it - it is not a separator
# `_SEPARATORS` splits on, contains no bare `>` `_REDIRECT_PRESENT` matches
# (process substitution's own `<`/`>` sit directly against `(`, a shape the
# redirect regex's target class `[^\s;&|<>]*` cannot enter, so this is not
# redundant with that check), and its head never appears as a segment head
# at all - `cat $(rm -rf build)` is one segment whose head is `cat`, a
# floor-clean read head, and the substitution's `rm -rf build` is invisible
# to every check below. Reproduced live: `classify_action("cat $(rm -rf
# build)")` is R4/protected in the full sentinel (a regression from this
# plan's own pre-fast-gate baseline, which refused it outright) while the
# fast gate silently allowed it. Fixed by a RAW, pre-parse scan of the exact
# input text - deliberately not quote-aware, and deliberately run before any
# segmentation: `"$(cmd)"` inside double quotes still runs `cmd` (the shell
# only suppresses *word-splitting* of the result, not the substitution
# itself), so exempting quoted spans here would reopen exactly this gap
# through a quote. Any of the four markers anywhere in the raw text
# escalates the whole command; a bare `$` not followed by `(` (`price $40`)
# never matches, so ordinary text with a dollar sign is unaffected.
_SUBSTITUTION_MARKERS = ("`", "$(", "<(", ">(")


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


def _find_mutation_flags(table: dict[str, Any]) -> frozenset[str] | None:
    """The token set that disqualifies ANY segment, table-driven so it stays
    tied to `godmode_sentinel._FIND_MUTATION`'s own five flags
    (`-delete`/`-exec`/`-execdir`/`-ok`/`-okdir`) rather than a second,
    independently-maintained copy of that list. Required and validated like
    every other table field this module trusts: missing or malformed means
    the table cannot be trusted for this either, so the caller escalates
    everything, not just `find` calls - the same fail-closed shape
    `_git_phrases`/`read_heads` already use.
    """
    raw = table.get("find_mutation_flags")
    if not isinstance(raw, list) or not raw:
        return None
    flags = []
    for flag in raw:
        if not isinstance(flag, str):
            return None
        flags.append(flag)
    return frozenset(flags)


def _flag_denylist(table: dict[str, Any]) -> dict[str, frozenset[str]] | None:
    """`{"git log": {"--output", "-o"}, ...}` - the write-capable flags a
    floor-clean match for that exact git phrase must not carry among its
    trailing tokens. Required (see `_find_mutation_flags`'s docstring for
    why missing/malformed means escalate-everything, not skip-the-check).
    A phrase absent from this mapping simply has no denylisted flags -
    `git status`/`ls-files`/etc. carry no write-to-file flag of this shape,
    so they are not required to appear here.
    """
    return _string_set_mapping(table.get("flag_denylist"))


def _output_flags_by_head(table: dict[str, Any]) -> dict[str, frozenset[str]] | None:
    """`{"sort": {"-o", "--output"}, "git": {"--output"}, ...}` - the same
    shape as `_flag_denylist`, keyed by bare command head instead of a full
    git phrase, consulted by the non-git read-head branch. Final review
    Critical finding C2: that branch matched on `tokens[0] in read_heads`
    alone and never checked for a write-capable flag at all, so
    `sort -o /etc/hosts f.txt` fast-allowed a real write the full sentinel
    gates (`godmode_sentinel._OUTPUT_FLAGS_BY_HEAD["sort"]`). Required, same
    fail-closed shape as every other table field.
    """
    return _string_set_mapping(table.get("output_flags_by_head"))


def _string_set_mapping(raw: Any) -> dict[str, frozenset[str]] | None:
    if not isinstance(raw, dict):
        return None
    result: dict[str, frozenset[str]] = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not isinstance(values, list):
            return None
        entries = []
        for value in values:
            if not isinstance(value, str):
                return None
            entries.append(value)
        result[key] = frozenset(entries)
    return result


def _denylisted(token: str, denylisted: frozenset[str]) -> bool:
    """Whether `token` (one trailing token after a floor-clean head/phrase)
    carries a flag in `denylisted`. Shared by the git-phrase branch
    (`flag_denylist`) and the non-git read-head branch
    (`output_flags_by_head`) so the two can never learn to match
    differently. Three spellings of the same flag are all caught: the bare
    flag itself, an `=`-joined value (`--output=/tmp/x` - compare the part
    before any `=`), and - single-character short flags only, matching what
    the tools themselves accept (`sort -oFILE`, git's own glued form) - a
    value glued on with no separator at all (`-o/tmp/x`). A long flag
    (`--output`) is never prefix-matched: gluing a value onto it with no `=`
    is not a form any of these tools accept, and prefix-matching it would
    catch an unrelated long flag that merely starts the same way.
    """
    bare = token.split("=", 1)[0]
    if bare in denylisted:
        return True
    return any(len(flag) == 2 and not flag.startswith("--")
               and token.startswith(flag) and token != flag
               for flag in denylisted)


def _segment_floor_clean(tokens: list[str], git_phrases: list[list[str]],
                          read_heads: set[str],
                          flag_denylist: dict[str, frozenset[str]],
                          output_flags_by_head: dict[str, frozenset[str]]) -> bool:
    if not tokens:
        return False
    head = tokens[0]
    if head != "git":
        if head not in read_heads:
            return False
        denylisted = output_flags_by_head.get(head)
        if denylisted and any(_denylisted(token, denylisted) for token in tokens[1:]):
            return False
        return True
    for phrase in git_phrases:
        n = len(phrase)
        if tokens[:n] != phrase:
            continue
        trailing = tokens[n:]
        joined = " ".join(phrase)
        if not trailing:
            return True
        if joined in _EXACT_ONLY_GIT_PHRASES:
            return False
        denylisted = flag_denylist.get(joined)
        if denylisted and any(_denylisted(token, denylisted) for token in trailing):
            return False
        return True
    return False


def fast_verdict(payload: dict[str, Any], table: dict[str, Any] | None) -> str:
    """`"allow"` only if the raw command carries no command/process
    substitution marker, and every segment is a floor-clean read with no
    redirect, none of the table's `find_mutation_flags`, and no denylisted
    write flag on the git phrase or read head it matches. Anything else -
    malformed input, a malformed table, a fenced tool, an internal exception
    - is `"escalate"`. Never a guess.
    """
    try:
        if not isinstance(table, dict):
            return "escalate"
        if not isinstance(payload, dict):
            return "escalate"
        # CX-2: a local, independent dual-casing lookup - `toolName`/
        # `tool_name`, `toolInput`/`tool_input` - matching
        # `godmode_hostevent.field()`'s alias table without importing it
        # (this module's zero-import boundary; see the module docstring).
        # First-alias-wins (camelCase before snake_case) is deliberate, not
        # incidental `dict.get` fallback ordering (fix round 1, I3): it
        # agrees with `godmode_hostevent.field()` and the hook's own
        # `host_field` lookup, so a payload naming a field under both
        # casings with conflicting values can never be read as two
        # different tools by two different checks.
        tool = payload.get("toolName", payload.get("tool_name"))
        if not isinstance(tool, str) or tool in _FENCED_TOOLS or tool not in _SHELL_TOOLS:
            return "escalate"
        tool_input = payload.get("toolInput", payload.get("tool_input"))
        if not isinstance(tool_input, dict):
            return "escalate"
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            return "escalate"

        # Raw, pre-parse, no quote exemption - see `_SUBSTITUTION_MARKERS`'s
        # comment for why this runs before segmentation and before quotes
        # are ever blanked.
        if any(marker in command for marker in _SUBSTITUTION_MARKERS):
            return "escalate"

        read_heads_raw = table.get("read_heads")
        if not isinstance(read_heads_raw, list):
            return "escalate"
        read_heads = {head for head in read_heads_raw if isinstance(head, str)}
        git_phrases = _git_phrases(table)
        if git_phrases is None:
            return "escalate"
        find_flags = _find_mutation_flags(table)
        if find_flags is None:
            return "escalate"
        flag_denylist = _flag_denylist(table)
        if flag_denylist is None:
            return "escalate"
        output_flags_by_head = _output_flags_by_head(table)
        if output_flags_by_head is None:
            return "escalate"

        segments = _blanked_segments(command)
        if not segments:
            return "escalate"
        for segment in segments:
            segment = _NULL_REDIRECT.sub(" ", segment)
            if _REDIRECT_PRESENT.search(segment):
                return "escalate"
            tokens = segment.split()
            if find_flags.intersection(tokens):
                return "escalate"
            if not _segment_floor_clean(tokens, git_phrases, read_heads,
                                        flag_denylist, output_flags_by_head):
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
