#!/usr/bin/env python3
"""Generates `hooks/gate_table.json` from `godmode_sentinel.py`'s own vocab
tables, so the fast gate's decision table can never silently drift from the
classifier it is a shortcut for.

**Step 1 - the reference floor, source and date.** The host's own read-only
auto-allow set (Claude Code's `readOnlyValidation` matcher) is not reachable
from this repo - no bundled copy of the CLI's source ships here, and pinning
this table to an unpinned dependency would be exactly the drift this module
exists to prevent. Pinned instead to the conservative, documented set the
gate-v2 plan recorded for this purpose
(`.superpowers/sdd/2026-08-14-gate-v2/task-5-brief.md`, Step 1), transcribed
here verbatim on 2026-08-14:
    git status|log|diff|show|branch|ls-files|rev-parse|rev-list|remote -v|
    shortlog|describe|blame
    ls, cat, head, tail, wc, grep, rg, find (no -exec/-delete/-execdir/-ok/
    -okdir), pwd, which, echo, sort, uniq, cut, tr, file, stat, du, df
`tr` was excluded from the first (provisional) cut of this floor because the
full sentinel did not yet classify a bare `tr` as read-only at the time that
fixture was hand-built (see `changelog.d/gate-fast-path.added.md`). Verified
again here, live, against the sentinel this script now imports:
`classify_action("tr a b")` is R0 today - the stream-tool gap that exclusion
named was closed by this same plan's Task 3 - so `tr` now belongs on the
floor, and every entry below (git and non-git alike) is re-verified against
`classify_action` at generation time rather than trusted from this docstring:
a floor entry that stops being R0 fails the build loudly, not the table
silently.

**Everything past the floor is generated, not retyped.** `db_clients` is
read directly from the sentinel's own `DB_CLIENTS` tuple.
`find_mutation_flags` is parsed from the compiled `_FIND_MUTATION` pattern's
own alternation (the same parse `tests/test_gate_fast.py`'s drift-guard test
performs independently, so the two can never quietly disagree).
`flag_denylist` combines the sentinel's own `_OUTPUT_FLAGS_BY_HEAD` entry for
`git` (`--output`, a real write-capable flag the sentinel's classifier
itself now gates - see `_output_flag_target`) with a fast-gate-only caution
addition, `-o`: git itself rejects a bare `-o` on `log`/`diff`/`show`, so the
full sentinel owes it nothing, but the fast gate treats it as denylisted
anyway out of defense in depth (documented at its point of use in
`hooks/godmode_gate_fast.py`). `output_flags_by_head` exports
`_OUTPUT_FLAGS_BY_HEAD` verbatim (final review Critical finding C2: the fast
gate's read-head branch matched on head alone and never consulted this table
at all, silently allowing `sort -o /etc/hosts f.txt` - a real write-capable
flag on a non-git read head - past the floor; `flag_denylist` above only ever
covered the three git phrases) - the whole dict, not a filtered subset,
because the git entry is redundant-but-harmless there (the fast gate's git
branch never looks at `output_flags_by_head`, only at `flag_denylist`) and a
verbatim export is the one form that can never itself drift from the source
dict. `git_ask`/`git_refuse` and `mutation_heads` have no single clean data
table in the sentinel to read verbatim - each is a curated candidate list,
classified through `classify_action` at generation time and asserted to land
where its bucket claims (protected + tier != R5 for `git_ask`, protected +
tier == R5 for `git_refuse`, protected + the expected category for a
`mutation_heads` entry) - so a sentinel change that moves one of these
candidates to a different bucket breaks the build instead of shipping a
table that silently disagrees with the classifier it was built from.

Usage: `python scripts/dev/build_decision_table.py` writes
`hooks/gate_table.json`; `--stdout` prints the same JSON to stdout instead
(used by `tests/test_gate_parity.py`'s freshness check, which regenerates
and diffs against the checked-in file).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from godmode_runtime.godmode_sentinel import (  # noqa: E402
    DB_CLIENTS,
    _FIND_MUTATION,
    _OUTPUT_FLAGS_BY_HEAD,
    classify_action,
)

assert set(_OUTPUT_FLAGS_BY_HEAD) >= {"git", "sort"}, (
    "expected heads dropped from the sentinel's own _OUTPUT_FLAGS_BY_HEAD"
)

SENTINEL_PATH = SCRIPTS_DIR / "godmode_runtime" / "godmode_sentinel.py"
TABLE_PATH = REPO_ROOT / "hooks" / "gate_table.json"

# --- Step 1: the reference floor (see module docstring for source + date) --
_GIT_FLOOR = [
    "git status",
    "git log",
    "git diff",
    "git show",
    "git branch",
    "git ls-files",
    "git rev-parse",
    "git rev-list",
    "git remote -v",
    "git shortlog",
    "git describe",
    "git blame",
]

_READ_HEADS = [
    "ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "pwd", "which",
    "echo", "sort", "uniq", "cut", "tr", "file", "stat", "du", "df",
    # S12-B (corpus-driven widening, 2026-08-29): the highest-frequency
    # escalating-but-allow-verdicted heads in the 184-entry corpus and this
    # repo's own sessions. Each is verified R0 by classify_action at
    # generation time exactly like the originals - a wrong guess fails the
    # build loudly, not the table silently.
    "rev", "date", "basename", "dirname", "realpath",
]

# --- git_ask / git_refuse: curated candidates, bucketed by the sentinel's
# own verdict at generation time (see module docstring). Each entry is a
# representative invocation, not a bare head - the categories these fall
# into (git-history-or-remote, git-branch-mutation, worktree-discard,
# local-repository-change) are verb-anchored regexes over the whole command,
# not head-anchored vocabulary, so a bare head alone would not reproduce the
# real match. `git tag`/`git checkout` need a trailing argument to become the
# mutation named here - bare `git tag` and `git checkout` (no args) are
# themselves read-only (`_SAFE_GIT_TAG`, and `checkout` with nothing after it
# falls elsewhere) and are already covered by `_GIT_FLOOR`/read allowances.
_GIT_ASK_CANDIDATES = [
    "git push",
    "git merge",
    "git rebase",
    "git reset",
    "git clean",
    "git tag v1.0",
    "git checkout main",
    "git switch feature",
    "git branch -d old",
    "git worktree remove wt",
    "git worktree prune",
    "git worktree move wt new",
    "git stash drop",
    "git stash pop",
    "git stash clear",
    "git stash apply",
    "git stash push",
    "git stash save",
    "git stash branch name",
    "git stash create",
    "git stash store abc",
    "git remote add name url",
    "git remote remove name",
    "git remote rm name",
    "git remote rename old new",
    "git remote set-url name url",
    "git remote set-head name branch",
    "git remote set-branches name branch",
    "git remote prune name",
    "git remote update",
    "git restore file",
    "git add file",
    "git commit -m msg",
]

_GIT_REFUSE_CANDIDATES = [
    "git push --force",
    "git push --force-with-lease",
    "git reset --hard",
    "git clean --force",
    "git branch -D old",
]

# --- mutation_heads: only categories whose regex is a plain command-name
# alternation (a bare head alone reproduces the real match) are represented -
# categories that require a specific flag or a named tool-plus-verb pair
# (scripted-source-edit, database-mutation's verb-anchored half) are not
# "heads" in this sense and are left out rather than misrepresented; each
# candidate is verified against `classify_action` below.
#
# `move-item` (U-B2 fix-round-1) is deliberately ABSENT: it still sits in
# `_ACTION_PATTERNS`'s filesystem-mutation entry, but a dedicated branch in
# `_categorize` - checked first - now intercepts `mv`/`cp`/`Move-Item`/
# `Copy-Item` before that entry is ever reached, classifying by DESTINATION
# argument (`pinned-evaluator-mutation`, ordinary `worktree-file-mutation`,
# or `unknown-command` when it cannot read one with confidence) rather than
# unconditionally by name. A bare `move-item target` - one positional
# argument - is exactly the shape that new branch cannot read a destination
# from confidently, so it is `unknown-command` now, not
# `filesystem-mutation`; this table generator's own candidate list follows
# that move rather than asserting a bucket the sentinel no longer puts it in.
_MUTATION_HEAD_CANDIDATES: dict[str, list[str]] = {
    "filesystem-mutation": [
        "rm", "rmdir", "rd", "del", "remove-item", "new-item",
        "set-content", "add-content", "out-file", "clear-content",
        "rename-item",
    ],
    "process-control": [
        "kill", "killall", "pkill", "taskkill", "stop-process", "stop-service",
    ],
}

# `-o` is a fast-gate-only caution addition, not a flag the full sentinel
# recognises on these three phrases (git rejects a bare `-o` on log/diff/show
# outright) - see hooks/godmode_gate_fast.py's own comment at its point of
# use for the full reasoning.
_DENYLIST_CAUTION_FLAG = "-o"
_DENYLISTED_GIT_PHRASES = ("git log", "git diff", "git show")


def _build_floor() -> dict[str, list[str]]:
    for phrase in _GIT_FLOOR:
        verdict = classify_action(phrase)
        assert verdict["tier"] == "R0", (
            f"floor entry no longer classifies R0 in the full sentinel: {phrase!r} "
            f"-> {verdict['tier']} ({verdict['category']})"
        )
    return {"claude-code": list(_GIT_FLOOR)}


def _build_read_heads() -> list[str]:
    verified = []
    for head in _READ_HEADS:
        verdict = classify_action(f"{head} somefile")
        assert verdict["tier"] == "R0", (
            f"read-head candidate no longer classifies R0 in the full sentinel: "
            f"{head!r} -> {verdict['tier']} ({verdict['category']})"
        )
        verified.append(head)
    return verified


def _build_find_mutation_flags() -> list[str]:
    match = re.search(r"-\(\?:([^)]+)\)", _FIND_MUTATION.pattern)
    assert match is not None, _FIND_MUTATION.pattern
    return [f"-{name}" for name in match.group(1).split("|")]


def _build_flag_denylist() -> dict[str, list[str]]:
    git_output_flags = list(_OUTPUT_FLAGS_BY_HEAD.get("git", ()))
    assert git_output_flags, "sentinel's _OUTPUT_FLAGS_BY_HEAD['git'] is now empty"
    flags = git_output_flags + [_DENYLIST_CAUTION_FLAG]
    return {phrase: list(flags) for phrase in _DENYLISTED_GIT_PHRASES}


def _build_output_flags_by_head() -> dict[str, list[str]]:
    """`_OUTPUT_FLAGS_BY_HEAD`, exported verbatim (see module docstring for
    why: a filtered subset is a second thing that can drift from the
    source, a verbatim export cannot). Consumed by the fast gate's
    non-git read-head branch, which - unlike the git-phrase branch and its
    `flag_denylist` - had no output-flag check at all before final-review
    Critical finding C2 (`sort -o /etc/hosts f.txt` fast-allowed a real
    write past the floor)."""
    return {head: list(flags) for head, flags in _OUTPUT_FLAGS_BY_HEAD.items()}


def _build_git_ask_refuse() -> tuple[list[str], list[str]]:
    ask: list[str] = []
    for phrase in _GIT_ASK_CANDIDATES:
        verdict = classify_action(phrase)
        assert verdict["protected"], f"git_ask candidate is not protected: {phrase!r}"
        assert verdict["tier"] != "R5", (
            f"git_ask candidate escalated to R5 (belongs in git_refuse now): {phrase!r}"
        )
        ask.append(phrase)

    refuse: list[str] = []
    for phrase in _GIT_REFUSE_CANDIDATES:
        verdict = classify_action(phrase)
        assert verdict["protected"], f"git_refuse candidate is not protected: {phrase!r}"
        assert verdict["tier"] == "R5", (
            f"git_refuse candidate no longer classifies R5 (belongs in git_ask now): "
            f"{phrase!r} -> {verdict['tier']}"
        )
        refuse.append(phrase)
    return ask, refuse


def _build_mutation_heads() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for category, heads in _MUTATION_HEAD_CANDIDATES.items():
        verified = []
        for head in heads:
            verdict = classify_action(f"{head} target")
            assert verdict["protected"] and verdict["category"] == category, (
                f"mutation-head candidate no longer classifies as {category!r}: "
                f"{head!r} -> protected={verdict['protected']} "
                f"category={verdict['category']}"
            )
            verified.append(head)
        result[category] = verified
    return result


def _generated_from() -> str:
    return hashlib.sha256(SENTINEL_PATH.read_bytes()).hexdigest()[:12]


def build_table() -> dict[str, object]:
    git_ask, git_refuse = _build_git_ask_refuse()
    return {
        "version": 1,
        "generated_from": _generated_from(),
        "floor": _build_floor(),
        "read_heads": _build_read_heads(),
        "mutation_heads": _build_mutation_heads(),
        "db_clients": list(DB_CLIENTS),
        "git_ask": git_ask,
        "git_refuse": git_refuse,
        "find_mutation_flags": _build_find_mutation_flags(),
        "flag_denylist": _build_flag_denylist(),
        "output_flags_by_head": _build_output_flags_by_head(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true",
                         help="print the table to stdout instead of writing "
                              "hooks/gate_table.json")
    args = parser.parse_args(argv)

    table = build_table()
    text = json.dumps(table, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        sys.stdout.write(text)
    else:
        TABLE_PATH.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {TABLE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
