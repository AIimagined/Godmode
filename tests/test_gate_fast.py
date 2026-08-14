"""The fast pre-tool gate: one table lookup, allow or escalate, never a guess.

`fast_verdict` is checked here against the same corpus `test_gate_corpus.py`
built from real denials, plus its own targeted red/green pairs. The corpus
check is deliberately ONE-DIRECTIONAL: it asserts fast-allow implies
full-allow, and never the converse. A command the fast gate escalates may
still be one the full sentinel would allow - that just means the full hook
paid its own cost to say so, which is always safe. A command the fast gate
allows that the full sentinel would ask or refuse about is the one failure
mode this module exists to make impossible, and that is the one direction
this test enforces. Written this way, the test is robust to `godmode_sentinel`
changing under it (a concurrent task on this same plan is doing exactly
that): a segment the sentinel newly starts recognising only ever makes the
corpus's `expected`/`fullv` pair agree *more* often, never less.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = PLUGIN_ROOT / "hooks"
FAST_GATE = HOOKS_DIR / "godmode_gate_fast.py"
TABLE_PATH = HOOKS_DIR / "gate_table.json"

_spec = importlib.util.spec_from_file_location("godmode_gate_fast", FAST_GATE)
fast = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(fast)

SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tests.test_gate_corpus import corpus_entries, _decision  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    _raw_segments, _executable_text, _FIND_MUTATION, classify_action,
)


def payload(command: str, tool: str = "Bash") -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
    }


def _table() -> dict[str, Any]:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


TABLE = _table()


class TableShape(unittest.TestCase):
    """The provisional fixture itself: schema-shaped, freshness-agnostic
    (nothing here pins `generated_from` - Task 5 replaces this file's
    contents, not its shape, and this suite must survive that swap)."""

    def test_required_keys_present(self) -> None:
        for key in ("version", "generated_from", "floor", "read_heads",
                    "mutation_heads", "db_clients", "git_ask", "git_refuse",
                    "find_mutation_flags", "flag_denylist",
                    "output_flags_by_head"):
            self.assertIn(key, TABLE)

    def test_output_flags_by_head_matches_the_sentinels_own_table(self) -> None:
        """Final review Critical finding C2's fix: `output_flags_by_head` is
        an exported copy of `_OUTPUT_FLAGS_BY_HEAD`, not a retyped one - pin
        it against the real dict directly so the two can never drift."""
        from godmode_runtime.godmode_sentinel import _OUTPUT_FLAGS_BY_HEAD
        expected = {head: set(flags) for head, flags in _OUTPUT_FLAGS_BY_HEAD.items()}
        actual = {head: set(flags) for head, flags in TABLE["output_flags_by_head"].items()}
        self.assertEqual(actual, expected)

    def test_floor_is_conservative_read_only_in_full_sentinel(self) -> None:
        """Every literal floor phrase, run bare, is R0 in the full sentinel
        today. This is the parity property Task 5's own table build will
        re-check for real; this fixture is built to already satisfy it."""
        for phrase in TABLE["floor"]["claude-code"]:
            with self.subTest(phrase=phrase):
                verdict = classify_action(phrase, project_root=PLUGIN_ROOT)
                self.assertEqual(verdict["tier"], "R0", phrase)

    def test_read_heads_are_r0_in_full_sentinel_bare(self) -> None:
        for head in TABLE["read_heads"]:
            with self.subTest(head=head):
                verdict = classify_action(f"{head} somefile", project_root=PLUGIN_ROOT)
                self.assertEqual(verdict["tier"], "R0", head)

    def test_find_mutation_flags_match_the_sentinels_own_set(self) -> None:
        """Review round 1, Critical finding 1: the fast gate's find-flag
        check only covered `-exec`/`-delete`, missing `-execdir`/`-ok`/
        `-okdir` from `_FIND_MUTATION` (godmode_sentinel.py). Now
        table-driven; this is the drift guard tying the table's flag set to
        the regex's own alternation, parsed directly from the compiled
        pattern rather than retyped by hand - so a sixth flag added to
        `_FIND_MUTATION` later shows up here as a mismatch instead of
        silently reopening the gap.
        """
        match = re.search(r"-\(\?:([^)]+)\)", _FIND_MUTATION.pattern)
        self.assertIsNotNone(match, _FIND_MUTATION.pattern)
        sentinel_flags = {f"-{name}" for name in match.group(1).split("|")}
        self.assertEqual(set(TABLE["find_mutation_flags"]), sentinel_flags)

    def test_flag_denylist_entries_name_real_floor_phrases(self) -> None:
        floor_phrases = set(TABLE["floor"]["claude-code"])
        for phrase in TABLE["flag_denylist"]:
            self.assertIn(phrase, floor_phrases, phrase)

    def test_denylisted_git_output_flags_are_gated_in_full_sentinel(self) -> None:
        """The full sentinel closed its `--output=<file>` gap (review Critical
        finding 2, fixed in the sentinel lane). The fast gate's denylist is
        now redundant-but-still-correct defense in depth: fast escalates,
        full gates the write. This pins the full sentinel's side so the pair
        can never silently reopen."""
        for phrase, flags in TABLE["flag_denylist"].items():
            for flag in flags:
                if not flag.startswith("--"):
                    # Short flags (-o) sit in the denylist as fast-gate
                    # caution only: git rejects them on log/diff/show, so
                    # the full sentinel owes them nothing.
                    continue
                command = f"{phrase} {flag}=/tmp/x"
                with self.subTest(command=command):
                    verdict = classify_action(command, project_root=PLUGIN_ROOT)
                    self.assertNotEqual(verdict["tier"], "R0", command)


class Equivalence(unittest.TestCase):
    def test_fast_allow_iff_full_sentinel_allows(self) -> None:
        for entry in corpus_entries():
            fastv = fast.fast_verdict(payload(entry["operation"]), TABLE)
            fullv = _decision(entry["operation"])
            if fastv == "allow":
                self.assertEqual(fullv, "allow", entry["operation"][:80])


class SegmentSplitEquivalence(unittest.TestCase):
    """Drift guard for the local duplicate. `_blanked_segments` splits at the
    same boundaries as `godmode_sentinel._raw_segments` for every command
    this suite exercises - the two must never learn to disagree about where
    a segment ends, even though one blanks quotes and the other keeps them."""

    def _samples(self) -> list[str]:
        return [entry["operation"] for entry in corpus_entries()] + [
            "git status && ls -la", "echo hi | grep x", "a; b; c",
            'echo "a; b" && echo c', "ls\r\ncat file.txt",
        ]

    def test_segment_count_matches_the_source_of_truth(self) -> None:
        for command in self._samples():
            with self.subTest(command=command[:60]):
                local = fast._blanked_segments(command)
                source = _raw_segments(command)
                self.assertEqual(len(local), len(source), command[:80])

    def test_segment_content_matches_the_source_of_truth(self) -> None:
        """Review round 1, Minor finding 1: the original guard only checked
        segment *count*. `_executable_text`, applied per-segment to
        `_raw_segments`'s raw (quote-intact) output, blanks quotes the same
        way `_blanked_segments` does in one fused pass - a segment boundary
        only ever falls where the quote-tracking state is already `None`
        (that's what makes it a boundary), so blanking each raw segment
        independently is provably equivalent to blanking during the single
        fused pass, and the two lists must now match element-for-element,
        not just in length.
        """
        for command in self._samples():
            with self.subTest(command=command[:60]):
                local = fast._blanked_segments(command)
                source = [_executable_text(segment).strip()
                          for segment in _raw_segments(command)]
                self.assertEqual(local, source, command[:80])


class NoArchiveIO(unittest.TestCase):
    def test_allow_path_opens_no_files(self) -> None:
        opened: list[Any] = []
        real_open = builtins.open

        def spy(*args: Any, **kwargs: Any) -> Any:
            opened.append(args[0] if args else kwargs.get("file"))
            return real_open(*args, **kwargs)

        builtins.open = spy
        try:
            verdict = fast.fast_verdict(payload("git status"), TABLE)
        finally:
            builtins.open = real_open
        self.assertEqual(verdict, "allow")
        self.assertEqual(opened, [])


class FailOpen(unittest.TestCase):
    """'Fail open' here means fail toward escalation, never toward allow -
    the gate's only safe direction when anything is uncertain."""

    def test_internal_exception_escalates(self) -> None:
        self.assertEqual(
            fast.fast_verdict({"tool_input": {"command": None}}, {"broken": True}),
            "escalate",
        )

    def test_missing_table_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status"), None), "escalate")

    def test_malformed_table_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status"), []), "escalate")
        self.assertEqual(fast.fast_verdict(payload("git status"), "not a dict"), "escalate")

    def test_corrupt_table_shapes_all_escalate(self) -> None:
        corrupt_tables = [
            {},
            {"floor": None, "read_heads": ["ls"]},
            {"floor": {"claude-code": ["git status"]}, "read_heads": "ls,cat"},
            {"floor": {"claude-code": [1, 2, 3]}, "read_heads": ["ls"]},
            {"floor": {}, "read_heads": None},
        ]
        for table in corrupt_tables:
            with self.subTest(table=table):
                self.assertEqual(fast.fast_verdict(payload("git status"), table), "escalate")

    def test_forced_internal_exception_still_escalates(self) -> None:
        """Not just an anticipated bad-input shape - a genuinely unexpected
        exception raised deep inside the verdict path must still resolve to
        escalate, never propagate and never allow."""
        real_segments = fast._blanked_segments
        fast._blanked_segments = lambda command: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            verdict = fast.fast_verdict(payload("git status"), TABLE)
        finally:
            fast._blanked_segments = real_segments
        self.assertEqual(verdict, "escalate")

    def test_fenced_tools_always_escalate(self) -> None:
        for tool in ("Edit", "Write", "NotebookEdit"):
            with self.subTest(tool=tool):
                pl = {"hook_event_name": "PreToolUse", "tool_name": tool,
                      "tool_input": {"file_path": "x.py", "content": "y"}}
                self.assertEqual(fast.fast_verdict(pl, TABLE), "escalate")

    def test_unknown_tool_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status", tool="Read"), TABLE),
                         "escalate")


class KnownShapes(unittest.TestCase):
    """Green controls: the exact shapes the floor is built to allow, and the
    exact shapes it must still escalate even though the floor's head or
    phrase matches on the surface."""

    def test_bare_floor_reads_allow(self) -> None:
        for command in ("git status", "git log", "ls -la", "cat file.txt",
                        "grep -rn pattern .", "git remote -v"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_redirect_always_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git status > out.txt"), TABLE),
                         "escalate")
        self.assertEqual(fast.fast_verdict(payload("cat file.txt >> log"), TABLE),
                         "escalate")

    def test_find_exec_and_delete_escalate(self) -> None:
        self.assertEqual(
            fast.fast_verdict(payload("find . -name x -exec rm {} +"), TABLE),
            "escalate")
        self.assertEqual(fast.fast_verdict(payload("find . -delete"), TABLE), "escalate")

    def test_find_execdir_ok_okdir_escalate(self) -> None:
        """Review round 1, Critical finding 1 - reproduced live against the
        pre-fix module (fast: allow, full: R4/protected) for all three;
        fixed by table-driving the full `_FIND_MUTATION` flag set instead
        of a hand-picked two-flag subset."""
        for command in ("find . -execdir rm {} ;", "find . -ok rm {} ;",
                         "find . -okdir rm {} ;"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_find_without_a_mutation_flag_still_allows(self) -> None:
        """Green control: the fix must not make ordinary `find` protected."""
        self.assertEqual(fast.fast_verdict(payload("find . -name x"), TABLE), "allow")

    def test_git_output_flag_escalates_on_log_diff_show(self) -> None:
        """Review round 1, Critical finding 2 - reproduced live against the
        pre-fix module (fast: allow, full: R0 - a real, unrecorded write the
        full sentinel doesn't yet catch either; see the changelog fragment
        for the separately-tracked sentinel-lane fix). `--output=<file>`,
        `--output <file>`-shaped (bare `--output` token), and bare `-o`
        must all escalate."""
        for command in ("git log --output=/tmp/x", "git diff --output=/tmp/x",
                         "git show --output=/tmp/x", "git log --output /tmp/x",
                         "git log -o /tmp/x", "git diff -o /tmp/x",
                         "git show -o /tmp/x"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_log_diff_show_without_a_write_flag_still_allow(self) -> None:
        """Green controls: the fix must not degrade the fast path's
        everyday utility - ordinary log/diff formatting flags stay allowed."""
        for command in ("git log --oneline -20", "git diff --stat",
                         "git show --stat", "git log -- src/foo.py"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_glued_short_flag_denylist_escalates(self) -> None:
        """Task 5 deferred-minor fix: the denylist match compared a trailing
        token to the denylisted flag exactly (after stripping any `=value`),
        which caught `-o /tmp/x` (two tokens) and `-o=x` but not git's own
        glued short-flag spelling `-oFILE` (one token, no separator at all) -
        `git log -o/tmp/x` fast-allowed a real, unrecorded write. Matching
        must prefix-match short (single-dash, single-character) denylisted
        flags against each trailing token instead of comparing for equality."""
        for command in ("git log -o/tmp/x", "git diff -o/tmp/x",
                         "git show -o/tmp/x"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_glued_short_flag_fix_does_not_overmatch_long_flags(self) -> None:
        """Green control: a long flag must never prefix-match - only the
        exact `--output`/`--output=...` forms are denylisted, so an unrelated
        long flag that happens to start with the same letters stays allowed."""
        self.assertEqual(
            fast.fast_verdict(payload("git log --oneline"), TABLE), "allow")

    def test_bare_git_branch_create_escalates(self) -> None:
        """The one real mutation reachable without any flag at all on this
        floor - a bare trailing word after `git branch` creates a branch."""
        self.assertEqual(fast.fast_verdict(payload("git branch new-feature"), TABLE),
                         "escalate")

    def test_git_branch_delete_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git branch -d old"), TABLE),
                         "escalate")

    def test_git_remote_v_with_trailing_token_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("git remote -v origin"), TABLE),
                         "escalate")

    def test_compound_command_with_one_unrecognised_segment_escalates(self) -> None:
        self.assertEqual(
            fast.fast_verdict(payload("git status && rm -rf build"), TABLE),
            "escalate")

    def test_unrecognised_head_escalates(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("npm view pkg version"), TABLE),
                         "escalate")

    def test_bare_tr_is_on_the_floor(self) -> None:
        """Reverses the provisional table's deliberate exclusion. That
        fixture left `tr` off the floor because `classify_action` did not
        yet recognise a bare `tr` as read-only (one of the FP3 corpus
        entries this same plan's Task 3 exists to fix). Task 5's generator
        re-verifies this live against the sentinel at build time
        (`scripts/dev/build_decision_table.py::_build_read_heads`) rather
        than trusting the old exclusion: `classify_action("tr a b")` is R0
        now, so `tr` belongs on the floor, and the fast gate must fast-allow
        it exactly like every other read head.
        """
        self.assertIn("tr", TABLE["read_heads"])
        self.assertEqual(fast.fast_verdict(payload("tr a b"), TABLE), "allow")


class Adversarial(unittest.TestCase):
    """Final whole-branch review (final-review.md), two Critical findings.
    Synthetic, hand-constructed probes - deliberately NOT added to
    `tests/fixtures/gate_corpus.json`, whose provenance is real denials
    only; a synthetic entry there would corrupt that population. This class
    is where synthetic adversarial coverage belongs instead.
    """

    def test_c1_command_substitution_escalates(self) -> None:
        """Reproduced red against the pre-fix module (fast: allow, exit 0,
        silent - the full hook never invoked; full sentinel: R4 or R5,
        protected). A REGRESSION from this plan's own pre-fast-gate
        baseline, which refused `cat $(rm -rf /)` outright - the fast gate
        had reopened a hole the branch itself had closed."""
        for command in (
            "cat $(rm -rf build)",
            "echo $(git push --force origin main)",
            "ls `rm -rf x`",
            "diff <(cat a) <(cat b)",
            "cat <(rm -rf build)",
            "grep x <(rm -rf build)",
            "echo hi >(tee /etc/hosts)",
        ):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_c1_quoting_does_not_exempt_substitution(self) -> None:
        """The fix is a RAW scan on purpose: `"$(...)"` inside double quotes
        still runs the inner command (the shell only suppresses
        word-splitting of the result), so a quote-aware exemption here would
        reopen the exact gap this fixes through a quote."""
        self.assertEqual(
            fast.fast_verdict(payload('echo "$(rm -rf build)"'), TABLE),
            "escalate")

    def test_c1_green_controls_unaffected(self) -> None:
        """A bare `$` not followed by `(` is ordinary text, not a
        substitution marker - ordinary floor-clean commands must stay
        allowed."""
        for command in ("git status", 'grep "price $40" f.txt',
                         "echo $HOME", "ls -la"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_c2_sort_output_flag_escalates(self) -> None:
        """Reproduced red against the pre-fix module (fast: allow, silent;
        full sentinel: R2/ask via `_OUTPUT_FLAGS_BY_HEAD["sort"]`). The
        read-head branch matched on head alone and never consulted an
        output-flag table at all - the git-phrase branch's `flag_denylist`
        fix from review round 1 covered only git, not the other read heads
        that share the same write-capable-flag shape."""
        for command in ("sort -o /etc/hosts f.txt",
                         "sort --output=/etc/hosts f.txt",
                         "sort -o/etc/hosts f.txt",
                         "sort --output /etc/hosts f.txt"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE),
                                 "escalate")

    def test_c2_sort_without_an_output_flag_still_allows(self) -> None:
        """Green controls: ordinary `sort` usage - including short flags
        that are not the denylisted `-o` - must stay fast-allowed."""
        for command in ("sort f.txt", "sort -u f.txt", "sort -n -r data.csv"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command), TABLE), "allow")

    def test_c1_and_c2_end_to_end_through_the_real_script(self) -> None:
        """The exact end-to-end smoke the review asked for: pipe the C1
        payload into the actual script and confirm the full hook's
        refusal JSON appears on stdout, proving escalation - not just the
        in-process `fast_verdict` call - actually happens."""
        raw = json.dumps(payload("cat $(rm -rf build)")).encode("utf-8")
        result = subprocess.run(
            [sys.executable, str(FAST_GATE)],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PLUGIN_ROOT, timeout=30,
        )
        self.assertIn(b"permissionDecision", result.stdout)


class Latency(unittest.TestCase):
    def test_thousand_verdicts_under_budget(self) -> None:
        start = time.perf_counter()
        for _ in range(1000):
            fast.fast_verdict(payload("git status"), TABLE)
        self.assertLess(time.perf_counter() - start, 1.0)


class EndToEndSmoke(unittest.TestCase):
    """Real subprocess invocations of the fast gate script itself, exactly
    as the host would run it."""

    def _run(self, command: str, tool: str = "Bash") -> subprocess.CompletedProcess[bytes]:
        raw = json.dumps(payload(command, tool=tool)).encode("utf-8")
        return subprocess.run(
            [sys.executable, str(FAST_GATE)],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PLUGIN_ROOT, timeout=30,
        )

    def test_a_floor_read_exits_silently(self) -> None:
        result = self._run("git status")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_a_refused_mutation_escalates_to_the_full_hook(self) -> None:
        result = self._run("git push --force")
        self.assertIn(b"permissionDecision", result.stdout)
        self.assertIn(b"deny", result.stdout)

    def test_empty_stdin_escalates_without_crashing(self) -> None:
        """Empty input carries no `hook_event_name: PreToolUse`, so the full
        hook it escalates to takes its non-pretool branch (`return 0 if
        preview["allow"] else 3`) rather than the pretool one - confirmed
        directly against `godmode_session_hook.py` before writing this
        assertion, not assumed. The point of this test is only that the
        fast gate never crashes and always mirrors whatever the full hook
        actually does, exit code included."""
        result = subprocess.run(
            [sys.executable, str(FAST_GATE)],
            input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PLUGIN_ROOT, timeout=30,
        )
        direct = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "godmode_session_hook.py"), "pre-action"],
            input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=PLUGIN_ROOT, timeout=30,
        )
        self.assertEqual(result.returncode, direct.returncode)
        self.assertEqual(result.stdout, direct.stdout)


if __name__ == "__main__":
    unittest.main()
