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

One exception to "never decides": a project with no Godmode archive at all
(`ungoverned_project`) has no full hook to escalate to, so this module
answers it (`uninitialized_body`). In the default `guard` mode a
harm-class command - force-push, history rewrite, a delete outside the
project, a release or publish - gets the host's own ask (a deny with the
remedy on a host with no ask), and everything else stays silent. A cheap
keyword screen (`harm_candidate`) keeps ordinary commands on the stat-only
path; only a command that names a harm-class word pays for the runtime's
own classifier (`godmode_sentinel.classify_action`, the same splitter and
rules a governed project uses). No archive is created or opened.
"""

from __future__ import annotations

# Fix round 2 (C-5's honest A/B showed the derived-state cache bought
# nothing measurable - reverted; the real cost centre this module can
# actually move is process start and its own top-level imports, per
# `python -X importtime` evidence: fast_allow p95 +20% mean / +23% median
# over 5 trials, n=21, against 100-400ms of measurement noise). `subprocess` is
# deferred into `main()`'s one use site (the escalate branch - the SILENT
# ALLOW path, this module's whole reason to exist, never spawns anything)
# - the same deferred-import discipline `godmode_anchor.py:109-112` states
# for `secrets`/`hmac`. `typing.Any` is NOT imported at all: every reference
# below is inside a type annotation, and `from __future__ import
# annotations` above (PEP 563) stores every annotation as an unevaluated
# string - the name `Any` never needs to exist at runtime for this module
# to run correctly. No type checker is configured for this repository
# (confirmed: no mypy/pyright config anywhere in it); if one ever is, the
# import can come back guarded by `typing.TYPE_CHECKING`.
import json
import os
import re
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
TABLE_PATH = HOOKS_DIR / "gate_table.json"
FULL_HOOK = HOOKS_DIR / "godmode_session_hook.py"
# Under every host's pre-tool timeout (30s in every manifest this plugin ships).
FULL_HOOK_DEADLINE_SECONDS = 25

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
                          "run_terminal_command",
                          # Antigravity's shell tool (tenth field report).
                          "run_command"})

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

# G-5: this module splits and blanks with Bash's lexical rules. PowerShell
# reads some text differently, and three of the differences can hide a
# second command from a Bash-rules reading: a backslash is literal (so
# `cat "a\"; git push --force` closes its string and pushes), a here-string
# (`@'`/`@"`) holds quote characters literally, and a typographic quote
# closes a string. A grouping `(...)` also runs a command in argument
# position. A PowerShell command carrying any of these - or any non-ASCII
# character - escalates, and the full hook parses it under PowerShell's own
# rules (`godmode_parseview`). Deliberately not imported here: the fast
# path's zero-import boundary. `tests/test_parse_view.py` keeps these tool
# sets in step with `godmode_parseview.dialect_for_tool`.
# `#` (review H1): a PowerShell comment, `#` or `<# #>`, holds quote
# characters literally; any PowerShell command carrying one escalates.
_PWSH_DIVERGENT = re.compile(r"""[(#]|@["']|\\(?=["';&|<>\r\n]|$)""")
_POWERSHELL_TOOLS = frozenset({"PowerShell"})
# Shell tools whose host does not say which shell runs them; on Windows
# that may be PowerShell.
_UNDECLARED_SHELL_TOOLS = frozenset({"shell_command", "run_terminal_command",
                                     "run_command"})


def _may_be_powershell(tool: str) -> bool:
    return tool in _POWERSHELL_TOOLS or _may_be_cmd(tool)


def _may_be_cmd(tool: str) -> bool:
    """An undeclared shell on Windows may be cmd.exe, which the full hook
    reads as a third dialect (`godmode_parseview.DIALECT_EITHER`)."""
    return tool in _UNDECLARED_SHELL_TOOLS and sys.platform == "win32"


# cmd.exe reads a single quote as an ordinary character (so `'a & b'` runs
# `b`), `^` as its escape, and expands `%VAR%` / `!VAR!` before it splits
# the line, so an expansion can carry a separator. A command that may run
# under cmd and carries any of these escalates.
_CMD_DIVERGENT = re.compile(r"['^%!]")


# The characters after which a `#` starts a new word, and so a comment -
# the sentinel's `_COMMENT_WORD_START`, copied (zero-import boundary).
_COMMENT_WORD_START = frozenset(" \t<>()")


def _blank_quotes(text: str) -> str:
    """`text` with its quoted spans blanked character for character - the
    sentinel's `_executable_text`, copied for the comment branch below.
    `SegmentSplitEquivalence` compares the two on every corpus row."""
    out: list[str] = []
    quote: str | None = None
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "\\" and quote != "'" and index + 1 < length:
            out.append(" " if quote else character)
            out.append(" " if quote else text[index + 1])
            index += 2
            continue
        if quote:
            if character == quote:
                quote = None
            out.append(" ")
        elif character in "\"'":
            quote = character
            out.append(" ")
        else:
            out.append(character)
        index += 1
    return "".join(out)


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
    # The last raw character consumed into this segment, for the comment
    # rule below (`current` holds blanked text, which cannot tell `"x"#y`,
    # one word, from `x #y`, a comment).
    last: str | None = None
    index = 0
    length = len(command)
    while index < length:
        character = command[index]
        if character == "\\" and quote != "'" and index + 1 < length:
            blank = quote is not None
            current.append(" " if blank else character)
            current.append(" " if blank else command[index + 1])
            has_content = True
            # An escaped character is part of the word it sits in, so a
            # `#` right after one does not start a comment.
            last = "\\"
            index += 2
            continue
        if quote is None and character == "#" and (last is None or last in _COMMENT_WORD_START):
            # The sentinel's rule (`_walk_segments`): a word-start `#` is a
            # comment to the end of the line; its quotes open nothing and its
            # separators split nothing. Blanked the way `_executable_text`
            # blanks the same text in the sentinel's segment.
            end = index
            while end < length and command[end] not in "\r\n":
                end += 1
            current.append(_blank_quotes(command[index:end]))
            has_content = True
            last = command[end - 1]
            index = end
            continue
        last = character
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
            last = None
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
        tool_input = payload.get("toolInput", payload.get("tool_input"))
        # Tenth field report 2026-09-05: Antigravity rides the tool on a
        # nested `toolCall` object - `{"toolCall": {"name": "run_command",
        # "args": {"CommandLine": ...}}}` - so every Antigravity call missed
        # the flat lookup above and escalated. Read that shape too; the
        # command text is `CommandLine` there, `command` elsewhere.
        tool_call = payload.get("toolCall")
        if isinstance(tool_call, dict) and tool is None:
            tool = tool_call.get("name")
            tool_input = tool_call.get("args")
        if not isinstance(tool, str) or tool in _FENCED_TOOLS or tool not in _SHELL_TOOLS:
            return "escalate"
        if not isinstance(tool_input, dict):
            return "escalate"
        command = tool_input.get("command", tool_input.get("CommandLine"))
        if not isinstance(command, str) or not command.strip():
            return "escalate"

        # Raw, pre-parse, no quote exemption - see `_SUBSTITUTION_MARKERS`'s
        # comment for why this runs before segmentation and before quotes
        # are ever blanked.
        if any(marker in command for marker in _SUBSTITUTION_MARKERS):
            return "escalate"
        # Review H1: a multi-line command escalates in every dialect. A line
        # break is where comments, here-strings and continuations change
        # how the rest of the text is read, and one-line reads - the whole
        # reason this path exists - never carry one.
        # Likewise any `#`: whether it opens a comment, and what a comment
        # hides, is the full hook's question to answer.
        if "\n" in command or "\r" in command or "#" in command:
            return "escalate"
        # A non-ASCII character escalates in every dialect: a lookalike
        # letter makes a different command name that reads as a known one,
        # and a non-ASCII space splits words here that the shell keeps
        # whole. The full hook judges the name.
        if not command.isascii():
            return "escalate"
        if _may_be_powershell(tool) and _PWSH_DIVERGENT.search(command):
            return "escalate"
        if _may_be_cmd(tool) and _CMD_DIVERGENT.search(command):
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
    # G-8: the same decode the full hook's `_input()` now uses on these
    # exact bytes (`godmode_stdin.parse_first_json`) - a leading BOM, CRLF,
    # or anything after the first JSON object (trailing data, a second
    # concatenated object) is tolerated here exactly as it is there, so a
    # shape this module can decide about (a read-only command) never
    # escalates purely because of how it was decoded. Unparsable input
    # still falls through to `{}`, which `fast_verdict` always escalates on
    # - the full hook's own tolerant parse gets the final say either way.
    sys.path.insert(0, str(HOOKS_DIR))
    from godmode_stdin import parse_first_json
    value, _malformed = parse_first_json(raw)
    return value


def ungoverned_project(start: Path) -> bool:
    """True only when no Godmode archive exists anywhere this project's
    could live - the answer `godmode_initstate.project_state` gives with
    stats alone, the same answer the full hook reaches after loading the
    whole runtime. Nothing was ever initialized there and there is nothing
    to gate. Field walk 2026-09-05: the not-initialized notice cost 380-520
    ms per mutating call, more than a governed project pays, because it
    needed the whole runtime to say so. Field report 2026-09-23: that walk
    covered only a plain git checkout, so a directory that is not a
    repository (or a linked worktree) still escalated every mutating call
    into a second interpreter, and under machine load those calls ran past
    the host's timeout. Any doubt - including a missing sibling module -
    escalates, and the full hook keeps every other answer.
    """
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    try:
        from godmode_initstate import ABSENT, project_state
    except ImportError:
        return False
    state, _root = project_state(str(start))
    return state == ABSENT


def brief_pending(start: Path) -> bool:
    """Grok only: the session-start hook parked a continuity brief that the
    first allowed tool call must carry (obligation 8584 - Grok reads no
    other hook output). One stat on a marker in the git dir; a worktree's
    `.git` file escalates anyway. Any doubt reads as pending, which costs
    one full-hook run, never a missed delivery."""
    if not (os.environ.get("GROK_AGENT") or os.environ.get("GROK_HOOK_EVENT")):
        return False
    try:
        git = start / ".git"
        return git.is_file() or (git / "godmode-brief-pending").exists()
    except Exception:  # noqa: BLE001 - doubt escalates
        return True


# ---------------------------------------------------------------------------
# Edit clearance: an ordinary in-tree edit decided without the full hook.
# ---------------------------------------------------------------------------
#
# Every Write/Edit used to start a second interpreter that loaded the whole
# runtime (R11, 2026-09-23). The checks that can refuse an edit - the
# classifier's protected paths and pinned evaluators, the design boundary,
# the scope fence, frozen regions, repeated reversal, plan-first, the
# unattended skill-change report, declared tool gates, observe mode, run ceilings, the watchdog and
# the required-sources ask - read the archive or project settings, so this
# module cannot run them. It does not try to. The full hook, after running
# every one of them on an edit of file F and allowing it silently, records
# a clearance for F: the session, the archive head it judged, and the state
# of every project setting those checks read. The next edit of F in the same
# session is allowed here only when that clearance still describes the
# project exactly:
#   - same session and project, F inside the tree, F an existing file and
#     not a protected path (`protected_edit_paths` in gate_table.json);
#   - F carries no frozen-region marker (the frozen-region check reads the
#     file, so a marker added since would change its answer);
#   - every setting file (policy, ceilings, boundaries, roles, the operator
#     stop flag) and git's HEAD unchanged;
#   - the archive head unchanged, or moved only by records that cannot change
#     any of those answers (an edit's own bookkeeping, an operator request),
#     chained record by record from the head the clearance saw.
# The full hook grants a clearance only when no answer can move without one
# of those changing: no run ceiling counts calls, no check has two red
# retests (the repeated-reversal precondition), and plan-first allowed F for
# a standing reason (gate off, throwaway branch, approved plan, or F already
# part of the change). Anything else - a first edit, a new file, a setting
# or record this module cannot vouch for, any doubt at all - escalates
# exactly as before.

CLEARANCE_NAME = "godmode-edit-clearance.json"
CLEARANCE_VERSION = 1
# Claude-shaped edit tools whose one target is `tool_input.file_path`.
_CLEARABLE_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
# Project settings the edit checks read, by file; the operator stop flag
# counts by its presence.
CLEARANCE_SETTINGS = (".godmode-authorization-policy.json", ".godmode-ceilings.json",
                      ".godmode-boundaries.json", ".godmode-roles.json", ".godmode-stop")
# Records that may land between a clearance and the next edit without
# voiding it: an edit's own bookkeeping, and what an operator's prompt
# records. None is read by any edit check (see the module block above).
_NEUTRAL_ACTIONS = frozenset({"edit-recorded", "prompt-shape-nudge", "agent-relay-seen"})
_MAX_TAIL = 32
_MAX_CLEARED_TARGETS = 256
_MAX_TARGET_BYTES = 4 * 1024 * 1024
_FROZEN_MARKER = b"godmode-editable-"


def _fingerprint(path: str) -> list[int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return [stat.st_mtime_ns, stat.st_size]


def clearance_settings(root: str) -> dict[str, Any]:
    """The state of every project setting an edit check reads, plus git's
    HEAD (the branch decides a throwaway-branch pass)."""
    state: dict[str, Any] = {name: _fingerprint(os.path.join(root, name))
                             for name in CLEARANCE_SETTINGS}
    state["HEAD"] = _fingerprint(os.path.join(root, ".git", "HEAD"))
    return state


def read_head(path: str) -> dict[str, Any] | None:
    """The archive head hint as `{sequence, record_hash}`, or None."""
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("sequence"), int):
        return None
    return {"sequence": value["sequence"], "record_hash": value.get("record_hash")}


def tree_relative(target: str, root: str) -> str | None:
    """`target`'s path inside `root` (posix), resolved through links; None
    when it is not an absolute path inside the tree."""
    if not isinstance(target, str) or not target or "\0" in target or not os.path.isabs(target):
        return None
    real = os.path.realpath(target)
    base = os.path.realpath(root)
    try:
        if os.path.commonpath([os.path.normcase(real), os.path.normcase(base)]) != os.path.normcase(base):
            return None
    except ValueError:
        return None
    relative = os.path.relpath(real, base).replace("\\", "/")
    if relative in (".", "") or relative.startswith("../"):
        return None
    return relative


def _neutral(record: dict[str, Any]) -> bool:
    kind = record.get("kind")
    subject = str(record.get("subject") or "")
    if kind == "action":
        return subject in _NEUTRAL_ACTIONS
    return kind == "request" and subject.startswith("ask:")


def _head_still_clear(cleared: dict[str, Any], head_path: str) -> bool:
    """Whether the archive head is the one the clearance saw, or moved from
    it only through neutral records, each chained to the one before."""
    head = read_head(head_path)
    if head is None or not isinstance(cleared, dict):
        return False
    start = cleared.get("sequence")
    if not isinstance(start, int):
        return False
    if head == {"sequence": start, "record_hash": cleared.get("record_hash")}:
        return True
    if not start < head["sequence"] <= start + _MAX_TAIL:
        return False
    events = os.path.join(os.path.dirname(head_path), "godmode-events")
    wanted = {f"{sequence:012d}-": sequence
              for sequence in range(start + 1, head["sequence"] + 1)}
    found: dict[int, str] = {}
    with os.scandir(events) as entries:
        for entry in entries:
            sequence = wanted.get(entry.name[:13])
            if sequence is None:
                continue
            if sequence in found:
                return False
            found[sequence] = entry.path
    previous = cleared.get("record_hash")
    for sequence in range(start + 1, head["sequence"] + 1):
        path = found.get(sequence)
        if path is None:
            return False
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
        if (not isinstance(record, dict) or record.get("sequence") != sequence
                or record.get("previous_hash") != previous or not _neutral(record)):
            return False
        previous = record.get("record_hash")
    return previous == head["record_hash"]


def _clearance_path(common: str) -> str:
    return os.path.join(common, CLEARANCE_NAME)


def _load_clearance(common: str) -> dict[str, Any] | None:
    try:
        with open(_clearance_path(common), encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("version") != CLEARANCE_VERSION:
        return None
    return value


def _save_clearance(common: str, value: dict[str, Any]) -> None:
    path = _clearance_path(common)
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
        os.replace(temporary, path)
    except OSError:  # godmode: swallow-ok: a clearance that cannot be saved only means the next edit escalates
        try:
            os.remove(temporary)
        except OSError:  # godmode: swallow-ok: nothing left to clean up
            pass


def drop_edit_clearance(common: str) -> None:
    try:
        os.remove(_clearance_path(common))
    except OSError:  # godmode: swallow-ok: no clearance is the state asked for
        pass


def _session_of(payload: dict[str, Any]) -> str:
    value = payload.get("session_id") or payload.get("sessionId")
    return value if isinstance(value, str) else ""


def _git_root(start: str) -> tuple[str, str] | None:
    """(project root, git dir) for a plain checkout; None otherwise."""
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    from godmode_initstate import _git_location, canonical
    located = _git_location(canonical(start))
    if located is None:
        return None
    root, common = located
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    return root, common


def grant_edit_clearance(payload: dict[str, Any], start: str, target: str,
                         head_path: str) -> bool:
    """Called by the full hook after it ran every edit check on `target`
    and allowed it silently, with nothing left that could change those
    answers but the state recorded here (see the block comment above)."""
    session = _session_of(payload)
    located = _git_root(start)
    if not session or located is None:
        return False
    root, common = located
    relative = tree_relative(target, root)
    head = read_head(head_path)
    if relative is None or head is None:
        return False
    settings = clearance_settings(root)
    current = _load_clearance(common)
    targets: list[str] = []
    if (current is not None and current.get("session") == session
            and current.get("root") == root and current.get("head_path") == head_path
            and current.get("head") == head and current.get("settings") == settings):
        targets = [t for t in current.get("targets") or [] if isinstance(t, str)]
    if relative not in targets:
        targets.append(relative)
    _save_clearance(common, {
        "version": CLEARANCE_VERSION, "session": session, "root": root,
        "head_path": head_path, "head": head, "settings": settings,
        "targets": targets[-_MAX_CLEARED_TARGETS:],
    })
    return True


def advance_edit_clearance(start: str, record: dict[str, Any]) -> None:
    """Called by the post-edit hook with the bookkeeping record it just
    appended: when that record sits directly on the head a clearance saw,
    the clearance moves with it. Anything else leaves the clearance alone,
    and the gate reads the moved head itself."""
    try:
        located = _git_root(start)
        if located is None or not _neutral(record):
            return
        _root, common = located
        current = _load_clearance(common)
        if current is None:
            return
        head = current.get("head") or {}
        if (record.get("sequence") != (head.get("sequence") or 0) + 1
                or record.get("previous_hash") != head.get("record_hash")):
            return
        current["head"] = {"sequence": record["sequence"], "record_hash": record.get("record_hash")}
        _save_clearance(common, current)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a clearance left behind only costs one escalation
        pass


def edit_cleared(payload: dict[str, Any], start: Path, table: dict[str, Any] | None) -> bool:
    """True only when this edit is the ordinary re-edit a standing
    clearance covers; any doubt is False (escalate)."""
    try:
        if not isinstance(table, dict) or not isinstance(payload, dict):
            return False
        tool = payload.get("toolName", payload.get("tool_name"))
        tool_input = payload.get("toolInput", payload.get("tool_input"))
        if tool not in _CLEARABLE_TOOLS or not isinstance(tool_input, dict):
            return False
        target = tool_input.get("file_path")
        session = _session_of(payload)
        if not isinstance(target, str) or not session or _hears_no_session_start(payload):
            return False
        protected = table.get("protected_edit_paths")
        if not isinstance(protected, list) or not protected:
            return False
        located = _git_root(str(start))
        if located is None:
            return False
        root, common = located
        cleared = _load_clearance(common)
        if cleared is None or cleared.get("session") != session or cleared.get("root") != root:
            return False
        relative = tree_relative(target, root)
        if relative is None or relative not in (cleared.get("targets") or []):
            return False
        for pattern in protected:
            if not isinstance(pattern, str) or re.search(pattern, target) or re.search(pattern, relative):
                return False
        real = os.path.realpath(target)
        if not os.path.isfile(real) or os.path.getsize(real) > _MAX_TARGET_BYTES:
            return False
        with open(real, "rb") as handle:
            if _FROZEN_MARKER in handle.read().lower():
                return False
        if cleared.get("settings") != clearance_settings(root):
            return False
        head_path = cleared.get("head_path")
        if not isinstance(head_path, str) or os.path.basename(head_path) != "godmode-head.json":
            return False
        return _head_still_clear(cleared.get("head"), head_path)
    except Exception:  # noqa: BLE001 - doubt escalates
        return False


# ---------------------------------------------------------------------------
# Uninitialized projects: the harm guard.
# ---------------------------------------------------------------------------

# Every word that can make `classify_action` answer a harm-class tier, or
# that names the guard's own setting. A superset on purpose: a hit only
# costs the runtime classifier (about 0.1 s); a miss would be a silent
# allow. `tests/test_gate_fast.py::UninitializedGuard` runs the gate corpus
# and a harm sample list through the classifier and fails if any harm-class
# command is not a candidate here.
_HARM_HINT = re.compile(
    r"(?:^|[^a-z0-9_])(?:push|reset|clean|branch|drop|truncate|rm|rmdir|rd|del|delete|"
    r"erase|unlink|remove|rmtree|move-item|new-item|set-content|add-content|out-file|"
    r"clear-content|rename-item|find|deploy|publish|release|upload|send|post|create|"
    r"eval|vssadmin|wmic|wbadmin|tmutil|password|godmode|uninitialized|config)"
    r"(?=[^a-z0-9_]|$)|shadowcopy|computerrestore")
# Quote, escape and caret characters a shell removes before it runs a word:
# `r"m"`, `p\ush` and `pu^sh` all run the word the screen must see.
_FLATTEN = re.compile(r"[\"'\\^`]")
# The `$` of Bash's ANSI-C and locale quoting (`$'sh'`, `$"sh"`) and the `+`
# joining two quoted PowerShell strings (`'pu'+'sh'`): both vanish before
# the word runs, so `git "pu"$'sh'` is read as `git push`.
_QUOTE_JOINS = re.compile(r"\$(?=[\"'])|(?<=[\"'])\s*\+\s*(?=[\"'])")
# An expansion the shell performs before the word runs: its result is not
# in the text, so no keyword screen can clear it. Any `$` that expands
# (`$x`, `$@`, `$*`, `${x}`, `$(...)`, `$'..'`), a backtick substitution,
# a cmd `%x%`, and a brace or glob spliced into a word (`pu{s,}h`,
# `pu?h`): `git pu$@sh -f` runs `git push -f`.
_EXPANSION = re.compile(
    r"\$[\w@*#?!$({'\"-]|`|%\w+%|[a-z]\{[^}\s]*[,.][^}\s]*\}|\{[^}\s]*,[^}\s]*\}[a-z]"
    r"|[a-z][?*\[]|[?*\]][a-z]")
# `godmode_sentinel._SCRIPT_HEADS` (copied; the drift guard compares them):
# the classifier reads a script these run, so the screen reads it too.
_SCRIPT_HEADS = frozenset({
    "python", "python3", "py", "node", "bun", "deno",
    "ruby", "perl", "bash", "sh", "zsh", "pwsh", "powershell",
})
_MAX_SCRIPT_BYTES = 256 * 1024
_MAX_HINT_STRINGS = 512
# The verbs `godmode_sentinel`'s filesystem-mutation rule names, as heads.
_MUTATING_VERBS = frozenset({
    "rm", "rm.exe", "rmdir", "rd", "del", "erase", "unlink", "remove-item", "move-item",
    "new-item", "set-content", "add-content", "out-file", "clear-content",
    "rename-item", "find",
})

# The guard's own setting, named in a command or targeted by an edit.
_GUARD_SETTING_TEXT = re.compile(r"(?i)uninitialized|godmode-settings|\.git[\\/]+config\b")
_GIT_CONFIG = re.compile(r"(?is)\bgit\b.*\bconfig\b")


def _hint_strings(payload: dict[str, Any]) -> list[str] | None:
    """Every string the tool call carries, or None when there are more
    than this screen reads (which the caller treats as a candidate)."""
    source: Any = payload.get("toolInput", payload.get("tool_input"))
    if source is None and isinstance(payload.get("toolCall"), dict):
        source = payload["toolCall"]
    if source is None:
        source = payload
    found: list[str] = []
    stack: list[tuple[Any, int]] = [(source, 0)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, (dict, list)):
            if depth > 8:
                return None
            items = value.values() if isinstance(value, dict) else value
            stack.extend((item, depth + 1) for item in items)
        if len(found) > _MAX_HINT_STRINGS:
            return None
    return found


# A script body is code, not a command line: only the substitutions a
# shell script runs count there, so indexing and globs in ordinary source
# keep `python tool.py` on the stat-only path.
_BODY_EXPANSION = re.compile(r"\$[({'\"]")


def _names_harm(text: str, script: bool = False) -> bool:
    lowered = text.lower()
    if (_BODY_EXPANSION if script else _EXPANSION).search(lowered):
        return True
    joined = _FLATTEN.sub("", _QUOTE_JOINS.sub("", lowered))
    return bool(_HARM_HINT.search(lowered) or _HARM_HINT.search(_FLATTEN.sub("", lowered))
                or _HARM_HINT.search(joined))


def _script_bodies(text: str, roots: list[str]) -> list[str] | None:
    """The scripts a script head in `text` would run, read the way the
    classifier reads them; None when one cannot be read (a candidate)."""
    bodies: list[str] = []
    tokens = text.split()
    for index, token in enumerate(tokens):
        head = _FLATTEN.sub("", token).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if head.endswith(".exe"):
            head = head[:-4]
        if head not in _SCRIPT_HEADS:
            continue
        for operand in tokens[index + 1:]:
            if operand.startswith("-"):
                continue
            operand = operand.strip("\"'")
            for base in roots:
                path = operand if os.path.isabs(operand) else os.path.join(base, operand)
                try:
                    if not os.path.isfile(path):
                        continue
                    if os.path.getsize(path) > _MAX_SCRIPT_BYTES:
                        continue
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        bodies.append(handle.read())
                except OSError:
                    return None
            break
    return bodies


def harm_candidate(payload: dict[str, Any], roots: list[str]) -> bool:
    """Whether this call might be harm-class or might touch the guard's
    own setting - decided with regular expressions and at most a script
    read, nothing imported. False only when no string in the call, nor
    any script it runs, names a word the classifier could turn into a
    harm-class answer."""
    strings = _hint_strings(payload)
    if strings is None:
        return True
    for text in strings:
        if _names_harm(text):
            return True
        bodies = _script_bodies(text, roots)
        if bodies is None or any(_names_harm(body, script=True) for body in bodies):
            return True
    # A path that resolves to the guard's own setting names no keyword at
    # all when it is spelled with a glob (`.gi?/conf*`).
    try:
        return _writes_guard_setting(strings, roots[0] if roots else None,
                                     roots[1] if len(roots) > 1 else None)
    except Exception:  # noqa: BLE001 - an unresolvable path is doubt, and doubt is a candidate
        return True


# Words that change the directory a later relative path resolves against,
# and the ones that return to a directory a `pushd` saved.
_CHDIR_HEADS = frozenset({"cd", "chdir", "set-location", "sl"})
_PUSHD_HEADS = frozenset({"pushd", "push-location"})
_POPD_HEADS = frozenset({"popd", "pop-location"})
_CD_HEADS = _CHDIR_HEADS | _PUSHD_HEADS
_DIRECTORY_HEADS = _CD_HEADS | _POPD_HEADS
# Words that may stand before the command word of a segment.
_LEAD_WORDS = frozenset({"then", "do", "else", "elif", "if", "while", "until", "!",
                         "builtin", "command", "time", "noglob"})
_ASSIGNMENT_WORD = re.compile(r"^[A-Za-z_]\w*=")
# Operators between the segments of one command text. After a pipe, a
# background `&` or a group bracket a directory change may run in a
# subshell, so it may or may not persist.
_SEGMENT_OPERATORS = ("&&", "||", ";", "\n", "|", "&", "(", ")", "{", "}")
_LOOSE_OPERATORS = frozenset({"|", "&", "(", ")", "{", "}"})
# Past this many possible directories the text is not followed any further.
_MAX_DIRECTORY_STATES = 64
# A command that makes a link, a junction or a drive letter: a path through
# it names whatever it points at, which the text does not show until it
# exists, so any word that could name the setting file counts.
_LINK_MAKER = re.compile(
    r"(?i)(?:^|[\s;&|(){}'\"`])(?:ln|link|mklink|subst|mount|new-psdrive|ndr)(?:\.exe)?"
    r"(?=[\s;&|(){}'\"`]|$)|symbolic|junction|hardlink|\bcp\b[^;&|\n]*\s-[a-z]*s")
# Where one path-shaped word ends: whitespace and the shell's own operators,
# plus the `=`/`,` a `dd of=...` or a `-Path:...` style argument joins on.
_PATH_WORD_SPLIT = re.compile(r"[\s;&|()<>=,{}]+")
# A word the shell expands before it is a path: its value is not in the text.
_DYNAMIC_WORD = re.compile(r"[$`%]")
_GLOB_CHARS = re.compile(r"[*?\[]")
# `Set-Location`'s parameters whose value is the directory, matched by any
# prefix PowerShell accepts (`-Pat`, `-Lit`) or their alias.
_CD_PATH_FLAGS = ("-path", "-literalpath", "-pspath")
# A word that is no directory: a flag, `--`, or cmd's `/d`.
_UNREAD_TARGET = object()


def _directory_target(rest: list[str]) -> tuple[Any, bool]:
    """The directory a `cd`/`pushd`/`Set-Location` whose words after the
    head are `rest` names, and whether the change is certain to happen.
    The target is `""` when none is named (a bare `cd`), `"-"` for the
    previous directory, and `_UNREAD_TARGET` when a flag this cannot read
    makes it unknowable. Mirrors `godmode_sentinel._directory_change`:
    flags are skipped (`-P`, `-LP`, `--`, `/d`), `-Path x`, `-LiteralPath
    x` and `-Path:x` name `x`. A short switch one shell takes and another
    refuses (`-P` is bash's physical switch, an ambiguous prefix to
    PowerShell) may leave the directory unchanged, so it is not certain."""
    certain = True
    index = 0
    while index < len(rest):
        word = rest[index]
        lowered = word.lower()
        if word == "--":
            return (rest[index + 1] if index + 1 < len(rest) else "", certain)
        if word == "-":
            return ("-", certain)
        if lowered == "/d":
            index += 1
            continue
        if not word.startswith("-"):
            return (word, certain)
        name, joined, value = word.partition(":")
        name = name.lower()
        if name == "-lp" or (len(name) >= 4 and any(flag.startswith(name) for flag in _CD_PATH_FLAGS)):
            if joined and value:
                return (value, certain)
            return ((rest[index + 1], certain) if index + 1 < len(rest)
                    else (_UNREAD_TARGET, False))
        if not joined and re.fullmatch(r"-[LPe@]+", word):
            certain = False
            index += 1
            continue
        if not joined and len(name) >= 4 and "-passthru".startswith(name):
            index += 1
            continue
        return (_UNREAD_TARGET, False)
    return ("", certain)


def _guard_setting_files(root: str | None) -> list[str]:
    """The files the guard's setting lives in, as absolute paths: the
    machine-wide settings file and, for a repository, `<git common dir>/
    config` (the file `godmode.uninitialized` is read from)."""
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    from godmode_initstate import _git_location, canonical, machine_settings_path
    files = [machine_settings_path()]
    if root:
        try:
            located = _git_location(canonical(root))
        except (OSError, ValueError):
            located = None
        if located is not None:
            files.append(os.path.join(located[1], "config"))
    return [os.path.normcase(os.path.normpath(os.path.abspath(path))) for path in files]


def _command_segments(text: str) -> list[tuple[frozenset[str], str]]:
    """`text` cut at the shell's command operators outside quotes, each
    segment with the operators that stood before it. A `#` starting a word
    comments out the rest of its line. A quote the text never closes keeps
    the rest in one segment, whose directory words are then read as
    unknown (see `_directory_states`)."""
    segments: list[tuple[frozenset[str], str]] = []
    buffer: list[str] = []
    operators: set[str] = {";"}
    quote = ""
    index = 0

    def flush() -> None:
        piece = "".join(buffer).strip()
        buffer.clear()
        if piece:
            segments.append((frozenset(operators), piece))
            operators.clear()

    while index < len(text):
        char = text[index]
        if quote:
            buffer.append(char)
            if char == quote:
                quote = ""
            elif char == "\\" and quote == '"' and index + 1 < len(text):
                buffer.append(text[index + 1])
                index += 1
            index += 1
            continue
        if char in "'\"":
            quote = char
            buffer.append(char)
            index += 1
            continue
        if char == "\\" and index + 1 < len(text):
            buffer.append(text[index:index + 2])
            index += 2
            continue
        if char == "#" and (not buffer or buffer[-1].isspace()):
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        operator = next((op for op in _SEGMENT_OPERATORS if text.startswith(op, index)), None)
        if operator is None:
            buffer.append(char)
            index += 1
            continue
        flush()
        operators.add(operator)
        index += len(operator)
    flush()
    return segments


def _segment_words(segment: str) -> list[list[str]]:
    """The whitespace words of one segment in both readings: quotes
    dropped (a backslash is a Windows separator) and flattened the way
    the shell removes escapes."""
    return [[word for word in reading.split() if word]
            for reading in (re.sub(r"[\"']", "", segment), _FLATTEN.sub("", segment))]


def _head_index(words: list[str]) -> int:
    index = 0
    while index < len(words) and (words[index].lower() in _LEAD_WORDS
                                   or _ASSIGNMENT_WORD.match(words[index])):
        index += 1
    return index


def _head_name(word: str) -> str:
    head = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return head[:-4] if head.endswith(".exe") else head


# One possible shell state: the current directory (None when the text
# cannot say), the previous one (`cd -`), the `pushd` stack, and whether
# the last command succeeded (which `&&` and `||` read). Annotations only:
# `_State` is `tuple[str | None, str | None, tuple, bool]`.


def _changed_states(state: _State, kind: str, rest: list[str], home: str,
                    cdpath: bool) -> set[_State]:
    """The states one `cd`/`pushd`/`popd` whose words after the head are
    `rest` can leave `state` in. A change that may fail keeps the
    unchanged state beside the moved one, marked as failed."""
    current, previous, stack, _ok = state
    failed = (current, previous, stack, False)
    unknown = (None, current, (), True)
    if kind == "popd":
        if rest:
            return {unknown, failed}
        if stack:
            return {(stack[-1], current, stack[:-1], True)}
        # The host shell's own stack is not in the text.
        return {unknown, failed}
    target, certain = _directory_target(rest)
    if kind == "pushd" and target == "":
        if stack:
            return {(stack[-1], current, (*stack[:-1], current), True)}
        return {unknown, failed}
    if target == "":
        moved = home
    elif target == "-":
        moved = previous
    elif (target is _UNREAD_TARGET or _DYNAMIC_WORD.search(target) or _GLOB_CHARS.search(target)
          or (kind == "pushd" and re.fullmatch(r"[+-]\d+", target))):
        moved = None
    else:
        if target.startswith("~"):
            target = home + target[1:]
        if os.path.isabs(target) or re.match(r"^[A-Za-z]:", target):
            moved = os.path.normpath(target)
        elif current is None or (cdpath and not target.startswith(".")):
            # `CDPATH` can send a bare name anywhere.
            moved = None
        else:
            moved = os.path.normpath(os.path.join(current, target))
    if moved is not None and not os.path.isdir(moved):
        # A directory that is not there yet (made earlier in the same
        # text, or found through `CDPATH`) is not known to be this one.
        certain, moved = False, None
    after = (moved, current, (*stack, current) if kind == "pushd" else stack, True)
    return {after} if certain and moved is not None else {after, failed}


def _directory_states(text: str, starts: list[str], home: str):
    """Each segment of `text` with the directories it may run in: one
    current directory per possible state, followed through every `cd`,
    `cd -`, `pushd`, `popd` and `Set-Location` the way the shell runs
    them - `&&` runs the next segment only where the last succeeded, `||`
    only where it failed. A directory the text cannot resolve is None."""
    cdpath = "cdpath" in text.lower() or bool(os.environ.get("CDPATH"))
    states: set[_State] = {(start, None, (), True) for start in starts}
    after_heredoc = False
    for operators, segment in _command_segments(text):
        loose = after_heredoc or bool(operators & _LOOSE_OPERATORS)
        if loose or operators & {";", "\n"}:
            running = set(states)
        elif "&&" in operators:
            running = {state for state in states if state[3]}
        else:
            running = {state for state in states if not state[3]}
        idle = states if loose else states - running
        yield segment, {state[0] for state in running}
        moved: set[_State] = set()
        readings = _segment_words(segment)
        for state in running:
            changed: set[_State] = set()
            for words in readings:
                head = _head_index(words)
                name = _head_name(words[head]) if head < len(words) else ""
                if name in _POPD_HEADS:
                    changed |= _changed_states(state, "popd", words[head + 1:], home, cdpath)
                elif name in _CD_HEADS:
                    kind = "pushd" if name in _PUSHD_HEADS else "chdir"
                    changed |= _changed_states(state, kind, words[head + 1:], home, cdpath)
                elif any(_head_name(word) in _DIRECTORY_HEADS
                         for word in _PATH_WORD_SPLIT.split(" ".join(words)) if word):
                    # A directory change this cannot place (quoted, wrapped
                    # in `eval`, an `sh -c` argument): anywhere at all.
                    changed |= {(None, None, (), True), (None, None, (), False)}
            if not changed:
                current, previous, stack, _ok = state
                changed = {(current, previous, stack, True), (current, previous, stack, False)}
            moved |= changed
        if loose:
            moved |= {(state[0], state[1], state[2], ok) for state in running for ok in (True, False)}
        states = set(idle) | moved
        if len(states) > _MAX_DIRECTORY_STATES:
            states = {(None, None, (), True), (None, None, (), False)}
        if "<<" in segment:
            after_heredoc = True


def _writes_guard_setting(texts: list[str], root: str | None, cwd: str | None = None) -> bool:
    """Whether any path-shaped word in `texts` resolves to a file the
    guard's setting lives in - read from what the path resolves to, not
    how it is spelled: `.` and `..` are normalised, a `cd`/`pushd`/`popd`/
    `Set-Location` earlier in the call moves the directory relative words
    resolve against (`_directory_states`), and a glob matches when it
    could name the file. A directory the text cannot resolve (`cd $x`)
    makes any word that could name `config` count. Relative words start
    from both the project root and the call's own directory (`cwd`): a
    host shell that kept an earlier `cd .git` runs the call from there."""
    spelled = _guard_setting_files(root)
    # Each file as spelled and as the filesystem resolves it (a symlinked
    # home or checkout), and its identity, which a hard link shares.
    files = list(dict.fromkeys(
        [*spelled, *(os.path.normcase(os.path.realpath(path)) for path in spelled)]))
    identities = set()
    for path in spelled:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        if stat.st_ino:
            identities.add((stat.st_dev, stat.st_ino))
    starts = list(dict.fromkeys(
        os.path.abspath(start) for start in (root, cwd) if start)) or [os.getcwd()]
    home = os.path.expanduser("~")
    linking = any(_LINK_MAKER.search(text) for text in texts)
    for text in texts:
        for segment, directories in _directory_states(text, starts, home):
            if linking:
                directories = {*directories, None}
            for words in _segment_words(segment):
                for word in (piece for word in words
                             for piece in _PATH_WORD_SPLIT.split(word) if piece):
                    if _names_setting_file(word, directories, files, identities, home):
                        return True
    return False


def _names_setting_file(word: str, directories: set[Any], files: list[str],
                        identities: set[Any], home: str) -> bool:
    """Whether `word`, read from any of `directories`, is one of `files`:
    `.` and `..` normalised, the longest existing prefix resolved through
    symlinks and junctions (`g/config` after `ln -s .git g`), and an
    existing file compared by identity (a hard link)."""
    if word.startswith("~"):
        word = home + word[1:]
    leaf = word.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()
    dynamic = bool(_DYNAMIC_WORD.search(word))
    if leaf and (dynamic or None in directories) and any(
            _fnmatch(os.path.basename(path), leaf) for path in files):
        return True
    if dynamic:
        return False
    for known in directories:
        if known is None:
            continue
        joined = os.path.join(known, word)
        for shown in {os.path.normcase(os.path.normpath(joined)),
                      os.path.normcase(os.path.realpath(joined))}:
            if any(_fnmatch(path, shown) for path in files):
                return True
        if identities and not _GLOB_CHARS.search(word) and os.path.isfile(joined):
            stat = os.stat(joined)
            if (stat.st_dev, stat.st_ino) in identities:
                return True
    return False


def _fnmatch(name: str, pattern: str) -> bool:
    import fnmatch
    if not _GLOB_CHARS.search(pattern):
        return os.path.normcase(name) == os.path.normcase(pattern)
    return fnmatch.fnmatchcase(os.path.normcase(name), os.path.normcase(pattern))


def _disables_guard(operation: str, targets: list[str], root: str | None = None,
                    cwd: str | None = None) -> bool:
    """Whether this call would change the guard's own setting: the
    machine-wide file, `godmode config set uninitialized`, or a
    repository's `godmode.uninitialized` key. Changing it is the operator's
    decision, so it is asked about like a harm-class command, and never
    rides silently beside one in the same compound command. A write is
    judged by the file it resolves to (`_writes_guard_setting`), however
    the path to it is spelled."""
    for text in (operation, _FLATTEN.sub("", operation)):
        if _GUARD_SETTING_TEXT.search(text):
            return True
        if _GIT_CONFIG.search(text) and re.search(r"(?i)godmode|[$`%]", text):
            return True
    for target in targets:
        shown = target.replace("\\", "/").lower().rstrip("/")
        if (shown == ".git/config" or shown.endswith("/.git/config")
                or shown.endswith("godmode-settings.json")):
            return True
    try:
        return _writes_guard_setting([operation, *targets], root, cwd)
    except Exception:  # noqa: BLE001 - a path this cannot resolve is doubt, and doubt asks
        return True


def _inside_tree(text: str, root: str, contained: Any) -> bool:
    """Whether every operand of one filesystem-mutation segment lands
    inside `root`. Operands are whitespace words with quotes dropped; a
    backslash is read both as an escape and as a separator, and both
    readings must stay inside. No operand at all (`xargs rm`) is not
    known to be inside."""
    tokens = text.split()
    # Operands follow the mutating verb, not a wrapper before it
    # (`xargs rm`, `sudo rm`): the verb itself is never an operand.
    verb = next((index for index, token in enumerate(tokens)
                 if _FLATTEN.sub("", token).replace("\\", "/").rsplit("/", 1)[-1].lower()
                 in _MUTATING_VERBS), 0)
    operands: list[str] = []
    for token in tokens[verb + 1:]:
        if token in ("{}", ";", "\\;", "+"):
            continue
        if token.startswith("-"):
            for separator in ("=", ":"):
                if separator in token:
                    operands.append(token.split(separator, 1)[1])
                    break
            continue
        operands.append(token)
    if not operands:
        return False
    for operand in operands:
        bare = operand.replace('"', "").replace("'", "")
        if not bare:
            continue
        for reading in {bare, bare.replace("\\", "/"), bare.replace("\\", "")}:
            if not reading or not contained(reading, Path(root)):
                return False
    return True


def _harm_category(verdict: dict[str, Any], root: str, contained: Any) -> str | None:
    """The harm-class category in a classifier verdict, or None. Harm is
    the classifier's own irreversible tiers (a forced push, a hard reset,
    a push or release, a delete); a delete or overwrite whose every operand
    stays inside the project is not harm here."""
    tier = verdict.get("tier")
    category = str(verdict.get("category") or "unclassified")
    if tier == "R5":
        return category
    if tier != "R4":
        return None
    parts = [part for part in verdict.get("components") or []
             if isinstance(part, dict) and part.get("tier") in ("R4", "R5")]
    if not parts:
        return category
    for part in parts:
        part_category = str(part.get("category") or category)
        if (part_category != "filesystem-mutation"
                or not _inside_tree(str(part.get("text") or ""), root, contained)):
            return part_category
    return None


def _guard_decision(payload: dict[str, Any], root: str) -> dict[str, Any] | None:
    """The host body for a harm-class call in an uninitialized project, or
    None to allow. Only reached by a `harm_candidate`; any failure here
    asks (or denies) rather than allowing, since the call already named a
    harm-class word.

    This is the one branch that needs the real classifier and the host
    dialect renderer, both from `godmode_runtime` - imports this module's
    own docstring forbids at any depth. That half of the work lives in the
    sibling hooks module `godmode_uninitialized_guard.py` instead; a hook
    importing another hook is not the boundary `godmode_atlas
    .direction_findings` enforces, so reaching it here, only on this rare
    confirmed-candidate path, keeps this module itself import-free. A
    deployment missing that sibling file is judged exactly like a runtime
    the sibling module itself could not reach: refused, not raised."""
    try:
        if str(HOOKS_DIR) not in sys.path:
            sys.path.insert(0, str(HOOKS_DIR))
        from godmode_uninitialized_guard import guard_decision
    except Exception:  # noqa: BLE001 - the sibling guard module is unreachable; deny, never raise
        return _unjudged_refusal()
    return guard_decision(payload, root)


def _unjudged_refusal(host: str = "unknown", event_name: str = "PreToolUse") -> dict[str, Any]:
    """The deny for a harm-class candidate this module could not judge -
    in the host's own dialect when the runtime can render it, else every
    documented dialect's keys at once. See `_guard_decision` above: the
    rendering lives in `godmode_uninitialized_guard.py` for the same
    zero-import reason; this module's own fallback below covers a
    deployment missing that sibling file too, the same way it already
    covered a runtime the sibling module could not reach."""
    reason = ("godmode: refused - this names a harm-class operation and Godmode, "
              "not initialized here, could not classify it. Run it yourself in a "
              "terminal, run `godmode init` here, or turn this guard off with "
              "`godmode config set uninitialized off`.")
    try:
        if str(HOOKS_DIR) not in sys.path:
            sys.path.insert(0, str(HOOKS_DIR))
        from godmode_uninitialized_guard import unjudged_refusal
        return unjudged_refusal(host, event_name)
    except Exception:  # noqa: BLE001 - the runtime and the sibling guard module are both unreachable
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": reason},
                "decision": "deny", "reason": reason}


def _hears_no_session_start(payload: dict[str, Any]) -> bool:
    """Grok ignores SessionStart output; the first PreToolUse answer is
    where its model hears anything. The same env chain as
    `godmode_hostevent.detect_host`, cut to the one answer needed here."""
    declared = os.environ.get("GODMODE_HOST")
    if declared:
        return declared == "grok"
    if isinstance(payload.get("toolCall"), dict) or os.environ.get(
            "ANTIGRAVITY_AGENT") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID"):
        return False
    return bool(os.environ.get("GROK_AGENT") or os.environ.get("GROK_PLUGIN_ROOT")
                or os.environ.get("GROK_HOOK_EVENT"))


def _session_mark(payload: dict[str, Any]) -> str:
    direct = payload.get("session_id") or payload.get("sessionId")
    if isinstance(direct, str) and direct:
        return direct
    transcript = payload.get("transcript_path") or payload.get("transcriptPath")
    return str(transcript or "")


def _notice_marker(root: str) -> str:
    """One small file per project in the application home - never in the
    working tree, never an archive - holding the session that heard the
    notice last."""
    from godmode_initstate import _sha256_hex, application_home, canonical
    key = _sha256_hex(f"notice\0{canonical(root)}".encode("utf-8"))[:24]
    return os.path.join(application_home(), "notices", key)


def _notice_due(payload: dict[str, Any], root: str) -> bool:
    try:
        with open(_notice_marker(root), encoding="utf-8") as handle:
            return handle.read() != _session_mark(payload)
    except OSError:
        return True


def _mark_notice(payload: dict[str, Any], root: str) -> None:
    try:
        marker = _notice_marker(root)
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write(_session_mark(payload))
    except OSError:  # godmode: swallow-ok: a missed mark repeats the notice once more; nothing worse
        pass


def uninitialized_notice_due(payload: dict[str, Any], start: Path) -> bool:
    """Grok only: this uninitialized, guarded project's session has not
    yet heard the notice, so even a floor read must answer with it."""
    if not _hears_no_session_start(payload):
        return False
    try:
        if str(HOOKS_DIR) not in sys.path:
            sys.path.insert(0, str(HOOKS_DIR))
        from godmode_initstate import ABSENT, UNINITIALIZED_OFF, project_state, uninitialized_mode
        state, root = project_state(str(start))
        if state != ABSENT or not root:
            return False
        return uninitialized_mode(root) != UNINITIALIZED_OFF and _notice_due(payload, root)
    except Exception:  # noqa: BLE001 - a notice is never worth a failed call
        return False


def uninitialized_body(payload: dict[str, Any], start: Path,
                       root: str | None = None) -> dict[str, Any] | None:
    """What a project with no Godmode archive answers for one pre-tool
    call: None for a silent allow, else the host body to print. `off`
    (machine-wide or for this repository) is always silent; `guard` asks
    about harm-class commands and, on a host that ignores SessionStart,
    carries the not-initialized notice on the session's first call."""
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    from godmode_initstate import GUARD_NOTICE, UNINITIALIZED_OFF, project_state, uninitialized_mode
    if root is None:
        _state, root = project_state(str(start))
    root = root or str(start)
    if uninitialized_mode(root) == UNINITIALIZED_OFF:
        return None
    body = None
    if harm_candidate(payload, [root, str(start)]):
        body = _guard_decision(payload, root)
    if _hears_no_session_start(payload) and _notice_due(payload, root):
        if body is None:
            body = {"decision": "allow",
                    "hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "additionalContext": GUARD_NOTICE}}
        else:
            specific = body.setdefault("hookSpecificOutput", {"hookEventName": "PreToolUse"})
            specific["additionalContext"] = GUARD_NOTICE
        _mark_notice(payload, root)
    return body


def spoken_allow(payload: dict[str, Any]) -> None:
    """Antigravity reads a silent PreToolUse as a denial (a memory plugin's
    Antigravity bridge, verified on agy 1.0.15: a bare `{}` refuses every matched
    call), so on that host an allow is spoken. Every other host's contract
    reads silence as allow, and a body there could be read as something
    else, so this prints nothing for them. Obligation 9862."""
    if (os.environ.get("ANTIGRAVITY_AGENT") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
            or isinstance(payload.get("toolCall"), dict)):
        sys.stdout.write('{"decision": "allow"}\n')


# The escalation's second interpreter runs the full hook through the session
# entry's loader, so its 5,000 lines come from the private byte-code cache
# instead of being compiled on every escalated call. argv: hooks directory,
# hook path, event.
_RUN_FULL_HOOK = ("import sys;sys.path.insert(0,sys.argv.pop(1));"
                  "import godmode_session_entry as e;raise SystemExit(e.run_hook(sys.argv.pop(1)))")


def _bytecode_flags() -> list[str]:
    """The launcher's byte-code choice, carried into the escalation (flags
    do not inherit): its private cache when it named one, else -B."""
    prefix = getattr(sys, "pycache_prefix", None)
    if prefix and not sys.dont_write_bytecode:
        return [f"-Xpycache_prefix={prefix}"]
    return ["-B"]


def main() -> int:
    # Obligation 9863: the first complete JSON object, never EOF (a Windows
    # host's pipe close can lag past the hook timeout). The reader is a
    # sibling module; `-I` keeps this directory off sys.path by design.
    sys.path.insert(0, str(HOOKS_DIR))
    from godmode_stdin import read_first_json
    raw = read_first_json()
    payload = _parse_payload(raw)
    table = _load_table()
    # Same project the full hook would resolve: the payload's `cwd` when
    # it carries one, else the process directory.
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    start = Path(cwd) if cwd else Path.cwd()
    if (fast_verdict(payload, table) == "allow" and not brief_pending(start)
            and not uninitialized_notice_due(payload, start)):
        spoken_allow(payload)
        return 0
    # An ordinary re-edit the full hook already cleared, with nothing it
    # judged having moved since (see "Edit clearance" above).
    if edit_cleared(payload, start, table):
        spoken_allow(payload)
        return 0
    # The full hook reads a non-string `cwd` as `str(cwd)`, not as the
    # process directory, so only a string or absent `cwd` may take this exit.
    if payload and (cwd or payload.get("cwd") in (None, "")) and ungoverned_project(start):
        # Nothing was initialized for this checkout: no archive, no
        # policy, no pins. Ordinary work is a silent allow; a harm-class
        # command gets the host's ask (`uninitialized_body`) unless the
        # operator turned that guard off. A malformed payload (parsed to
        # `{}`) never takes this exit; it still fails closed below.
        # The full hook would exit silently for this project, so a failure
        # here is judged here: a harm-class candidate is refused, anything
        # else is ordinary work and allowed.
        try:
            body = uninitialized_body(payload, start)
        except Exception:  # noqa: BLE001 - judged below, never raised into the host
            try:
                candidate = harm_candidate(payload, [str(start)])
            except Exception:  # noqa: BLE001 - an unreadable call is treated as a candidate
                candidate = True
            body = _unjudged_refusal() if candidate else None
        if body is None:
            spoken_allow(payload)
        else:
            sys.stdout.write(json.dumps(body, ensure_ascii=False) + "\n")
        return 0
    # Escalate: re-feed the exact bytes read from stdin to the full hook and
    # mirror its stdout/stderr/exit code verbatim - the fast gate must be
    # invisible to the host on every path except the one it actually skips.
    # `-I` and the byte-code choice again (obligation 9866): interpreter
    # flags do not inherit, and an isolation that ends at the first
    # escalation is none.
    #
    # Deferred here, not module scope (fix round 2): `subprocess`'s own
    # import cost (~5.3ms measured, `python -X importtime`; the overall
    # gain this bought fast_allow is p95 +20% mean / +23% median over 5
    # trials, n=21, against 100-400ms of measurement noise) is paid only on
    # the path that was always going to spawn a whole second interpreter
    # anyway - never on the silent allow path, this module's entire reason
    # to exist.
    import subprocess
    # A host treats a hook that outlives its timeout as a failed hook and runs
    # the tool anyway, so a slow full check was an open gate: on a 21k-record
    # archive it took 7.6-8.2s against an 8s budget and a push went through
    # unchecked (2026-09-24). The fast gate keeps its own deadline under the
    # host's and refuses when the full check has not answered by then.
    try:
        result = subprocess.run(
            [sys.executable, "-I", *_bytecode_flags(), "-c", _RUN_FULL_HOOK,
             str(HOOKS_DIR), str(FULL_HOOK), "pre-action"],
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=FULL_HOOK_DEADLINE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"godmode: refused - the gate could not decide within "
            f"{FULL_HOOK_DEADLINE_SECONDS}s, and an undecided call is not an allowed one. "
            "Retry; if it repeats, run `godmode doctor`.\n")
        return 2
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
