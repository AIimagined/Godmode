"""I-4: two red retests of the same check bracket a fix loop; a third edit
to the file with no incident naming a hypothesis and its falsifier is
refused. An incident recorded after the second red run that names both
lifts the refusal.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", Path(__file__).parent, PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_reversals  # noqa: E402
from godmode_runtime.godmode_attest import run_check  # noqa: E402
from godmode_runtime.godmode_mistakes import record_incident  # noqa: E402
from godmode_runtime.godmode_retest import retest_module_names  # noqa: E402
from godmode_runtime.godmode_reversals import third_edit_without_incident  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
                   check=True, capture_output=True, timeout=60)


def _seed(project: Path) -> None:
    """`scripts/widgetry.py`, pinned by `tests/test_widgetry.py` - a test
    that always fails, so every retest run against it is red regardless of
    what the file says. That is the point: this gate reacts to the RETEST
    ATTESTATION'S status, never to whether the source actually changed."""
    (project / "scripts").mkdir()
    (project / "tests").mkdir()
    (project / "scripts" / "widgetry.py").write_text(
        "def widgetry():\n    return 1\n", encoding="utf-8")
    (project / "tests" / "test_widgetry.py").write_text(
        "import unittest\n"
        "from scripts.widgetry import widgetry\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_it(self):\n"
        "        self.assertTrue(False)\n",
        encoding="utf-8",
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "baseline")


def _red_retest(archive, project: Path) -> int:
    """One `check:retest:unittest` attestation, always `blocked` - the
    seeded test never passes. Returns its sequence."""
    outcome = run_check(
        archive, "s1", project, "retest:unittest",
        [sys.executable, "-m", "unittest", "tests.test_widgetry"], timeout=60,
    )
    assert outcome["attested"] == "blocked", outcome
    return outcome["sequence"]


def _edit(archive, path: str) -> int:
    record = archive.append(
        "action", "edit-recorded", {"path": path, "operation": f"edit:{path}"}, evidence=[])
    return record["sequence"]


def _fake_red(archive) -> int:
    """A `check:retest:unittest` `blocked` attestation with the same
    evidence shape `run_check` writes for the real seeded test - written
    directly, without a real subprocess run, so the property sweep below
    can afford hundreds of these. `third_edit_without_incident` reads only
    `data["status"]` and the `cmd:` evidence string; it cannot tell this
    apart from `_red_retest`'s real one."""
    record = archive.append(
        "attestation", "check:retest:unittest", {"status": "blocked"},
        evidence=[f"cmd:{sys.executable} -m unittest tests.test_widgetry"])
    return record["sequence"]


class TwoReversalsGateTests(unittest.TestCase):
    def test_third_edit_after_two_red_retests_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            red1 = _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            red2 = _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            finding = third_edit_without_incident(archive, "scripts/widgetry.py")
            self.assertIsNotNone(finding)
            self.assertEqual(finding["check"], "check:retest:unittest")
            self.assertEqual(finding["red_runs"], [red1, red2])
            self.assertEqual(finding["edits"], 2)
            self.assertIn("--hypothesis", finding["remedy"])
            self.assertIn("--refuted-by", finding["remedy"])

    def test_only_one_edit_on_record_does_not_refuse_yet(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)

            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

    def test_one_red_retest_alone_does_not_refuse(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _edit(archive, "scripts/widgetry.py")

            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

    def test_an_incident_naming_both_fields_after_the_second_red_run_lifts_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            red2 = _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            record_incident(
                archive, "widgetry keeps failing", "read the fixture before trying again",
                hypothesis="the seeded test always fails regardless of the source",
                refuted_by="python -m unittest tests.test_widgetry",
            )
            self.assertGreater(archive.read_events()[-1]["sequence"], red2)

            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

    def test_an_incident_missing_the_falsifier_does_not_lift_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            record_incident(
                archive, "widgetry keeps failing", "a hypothesis with no falsifier",
                hypothesis="the seeded test always fails regardless of the source",
            )

            self.assertIsNotNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

    def test_a_premature_incident_does_not_lift_the_bracket_but_still_shifts_the_anchor(self) -> None:
        """Fix round 2 (re-review of 039b35c): an incident recorded before
        the second red run does not LIFT the current bracket -
        `_incident_lifts_it` only counts one recorded after `red_runs[1]`,
        so this one never satisfies that check. But the anchor rule is
        unconditional on timing ("an incident with both fields resets the
        anchor to after itself"): it still moves the edit count's start
        point to the first red run after it, so the one edit made before
        the second red no longer counts toward the total - a fresh pair of
        edits since THAT point is still needed, and still trips the gate
        once they land."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            red1 = _red_retest(archive, project)
            record_incident(
                archive, "premature", "recorded too early to lift the bracket",
                hypothesis="a guess", refuted_by="python -m unittest tests.test_widgetry",
            )
            _edit(archive, "scripts/widgetry.py")
            red2 = _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            # Anchor shifted to red2 by the premature incident: only one
            # edit landed since then, so this is not yet the third edit.
            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

            _edit(archive, "scripts/widgetry.py")
            finding = third_edit_without_incident(archive, "scripts/widgetry.py")
            self.assertIsNotNone(finding)
            self.assertEqual(finding["red_runs"], [red1, red2])

    def test_a_file_with_no_pinning_test_has_no_closure_to_check(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            self.assertIsNone(third_edit_without_incident(archive, "scripts/unrelated.py"))

    def test_two_back_to_back_reds_with_no_edit_between_do_not_refuse(self) -> None:
        """Fix round 1 (review of ac48f2d, required finding 1.2): two red
        retests run back to back - confirming a failure, not bracketing a
        fix attempt - must not cost the next ordinary edits a false
        refusal, even once two of them have landed since the first red."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _edit(archive, "scripts/widgetry.py")

            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

    def test_two_reds_in_a_row_do_not_clear_an_earlier_bracketed_pair(self) -> None:
        """Fix round 3 (re-review of d6ac766, required finding N-1): the
        bracket used to check only the newest pair of red runs, so once
        that pair became two reds back to back with nothing edited between
        THEM, the gate went slack for every edit after - even though an
        earlier pair in the same run of blocked retests still had a fix
        attempt bracketed between it. Pinned: red, edit, red, edit, red,
        red still refuses (the earlier pairs' edits still count), and one
        more edit with no new green does not clear it either."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)           # red 1
            _edit(archive, "scripts/widgetry.py")   # edit 1
            _red_retest(archive, project)           # red 2
            _edit(archive, "scripts/widgetry.py")   # edit 2
            _red_retest(archive, project)           # red 3
            _red_retest(archive, project)           # red 4 - two in a row, nothing between them

            self.assertIsNotNone(
                third_edit_without_incident(archive, "scripts/widgetry.py"),
                "two red runs back to back must not clear a live refusal")

            _edit(archive, "scripts/widgetry.py")   # edit 3, no new green behind it

            self.assertIsNotNone(
                third_edit_without_incident(archive, "scripts/widgetry.py"),
                "a further edit with no new green must not clear it either")

    def test_the_edit_count_is_monotonic_across_extra_red_runs(self) -> None:
        """Fix round 2 (re-review of 039b35c, required finding 1): anchoring
        the edit count at `red_runs[0]` - the newest pair's own left edge -
        made it slide forward on every new red run, so a live refusal
        cleared itself the instant one more `godmode retest --run` came
        back red with no edit in between - the exact next keystroke this
        gate encourages, and a one-command bypass of its own remedy. Pinned
        here: `red, edit, red, edit` refuses; one more red retest with no
        edit must not clear it."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            self.assertIsNotNone(third_edit_without_incident(archive, "scripts/widgetry.py"),
                                 "red, edit, red, edit must refuse")

            _red_retest(archive, project)  # one more red retest, no edit

            self.assertIsNotNone(third_edit_without_incident(archive, "scripts/widgetry.py"),
                                 "one more red retest alone must not clear a live refusal")

    def test_the_disciplined_edit_retest_loop_still_trips_the_gate(self) -> None:
        """Fix round 2 (re-review of 039b35c, required finding 1): anchoring
        at `red_runs[0]` made `edit, retest red, edit, retest red, ...` -
        retesting after every single edit, the disciplined shape this gate
        exists to catch - the one loop shape it could never refuse, because
        the edit count reset to 1 on every iteration. Pinned: alternating
        red/edit refuses at the third edit and stays refused as the chain
        grows further."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)          # red 1
            _edit(archive, "scripts/widgetry.py")   # edit 1
            _red_retest(archive, project)           # red 2
            _edit(archive, "scripts/widgetry.py")   # edit 2
            _red_retest(archive, project)           # red 3 - the third edit (not yet made) is refused

            self.assertIsNotNone(third_edit_without_incident(archive, "scripts/widgetry.py"),
                                 "the third edit in an alternating red/edit loop must refuse")

            _edit(archive, "scripts/widgetry.py")   # edit 3
            _red_retest(archive, project)           # red 4

            self.assertIsNotNone(third_edit_without_incident(archive, "scripts/widgetry.py"),
                                 "the loop must stay refused as it keeps alternating")

    def test_a_fresh_pair_of_reds_re_arms_the_gate_past_an_old_incident(self) -> None:
        """Fix round 1 (review of ac48f2d, required finding 1.1): the first
        incident ever recorded, with both fields, must not disarm this gate
        for the rest of the project's life - a fresh red/edit/red/edit loop
        re-arms it on its own. Pinned scenario from the review: red, edit,
        red, edit, incident(both fields), edit, red, edit, red, edit, edit
        -> refused again."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)                      # red
            _edit(archive, "scripts/widgetry.py")               # edit
            old_red2 = _red_retest(archive, project)            # red
            _edit(archive, "scripts/widgetry.py")                # edit
            record_incident(                                    # incident(both fields)
                archive, "widgetry keeps failing", "read the fixture before trying again",
                hypothesis="the seeded test always fails regardless of the source",
                refuted_by="python -m unittest tests.test_widgetry",
            )
            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"),
                              "the incident just recorded should lift the OLD pair")

            _edit(archive, "scripts/widgetry.py")               # edit
            new_red3 = _red_retest(archive, project)            # red
            _edit(archive, "scripts/widgetry.py")               # edit
            new_red4 = _red_retest(archive, project)            # red
            _edit(archive, "scripts/widgetry.py")               # edit

            finding = third_edit_without_incident(archive, "scripts/widgetry.py")
            self.assertIsNotNone(finding, "a fresh pair of reds must re-arm the gate")
            self.assertEqual(finding["red_runs"], [new_red3, new_red4])
            self.assertNotIn(old_red2, finding["red_runs"])

    def test_hypothesis_and_refuted_by_recorded_through_the_cli_lift_the_refusal(self) -> None:
        """Fix round 1 (review of ac48f2d, should-fix 2): the remedy this
        gate prints is a `godmode remember` command line - driven through
        the real CLI wiring (`_build_parser` + `cmd_remember`), not by
        calling `record_incident` directly, so an argparse/`getattr` slip
        in `--hypothesis` would fail this test instead of shipping inert."""
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_console import Runtime, _build_parser, cmd_remember

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _git(project, "init", "-q")
            _seed(project)

            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            self.assertIsNotNone(third_edit_without_incident(archive, "scripts/widgetry.py"))

            parser = _build_parser()
            args = parser.parse_args([
                "remember", "--kind", "incident",
                "--subject", "widgetry keeps failing",
                "--value", "read the fixture before trying again",
                "--hypothesis", "the seeded test always fails regardless of the source",
                "--refuted-by", "python -m unittest tests.test_widgetry",
                "--no-repro", "the seeded red retest is the reproduction on record",
            ])
            runtime = Runtime(anchor=resolve_anchor(project), archive=archive)
            result = cmd_remember(args, runtime)
            self.assertEqual(
                result.payload["record"]["data"]["hypothesis"],
                "the seeded test always fails regardless of the source")
            self.assertEqual(
                result.payload["record"]["data"]["refuted_by"],
                "python -m unittest tests.test_widgetry")

            self.assertIsNone(third_edit_without_incident(archive, "scripts/widgetry.py"))


class BoundedMonotonicityPropertyTests(unittest.TestCase):
    """Task 6/7 cross-check (final review, section 3): three hand-written
    fixture rows above each pinned a monotonicity regression a PRIOR
    review round found - round 2 finding 1, round 3 finding N-1. Two
    consecutive rounds of "more evidence disarmed the gate" is exactly the
    evidence that a row-per-bug approach was never going to cover the
    invariant itself. This enumerates every `{red, edit}` sequence up to
    length 6 instead: once a prefix refuses, appending one more red run
    (`R`) or one more edit (`E`) must still refuse - only an incident
    naming both `hypothesis` and `refuted_by` may clear it, and none is
    ever recorded in this sweep.

    `retest_module_names` (`godmode_retest.pinning_tests`) shells out to
    `git ls-files` and regex-scans every test file - 1.3-3.1s per call per
    its own docstring. `third_edit_without_incident` is pure over archive
    records once that one lookup is known (same docstring), so it is
    computed exactly once here, against one seeded project, and reused
    verbatim (`mock.patch.object`) for every one of the (2+4+8+16+32+64=)
    126 sequences below - each on its own fresh, git-free archive, so the
    whole sweep stays stdlib-only and comfortably under a minute.
    """

    PATH = "scripts/widgetry.py"
    MAX_LENGTH = 6

    def test_a_refusing_prefix_never_clears_without_an_incident(self) -> None:
        with isolated_project() as (project, _s, _a, seed_archive):
            seed_archive.initialize()
            _git(project, "init", "-q")
            _seed(project)
            module_names = retest_module_names(project, [self.PATH])
        self.assertTrue(module_names, "the seeded fixture must pin scripts/widgetry.py")

        with mock.patch.object(
                godmode_reversals, "retest_module_names",
                lambda _project, _paths: module_names):
            for length in range(1, self.MAX_LENGTH + 1):
                for sequence in itertools.product("RE", repeat=length):
                    with isolated_project() as (_p, _s, _a, archive):
                        archive.initialize()
                        was_refused = False
                        for step in sequence:
                            if step == "R":
                                _fake_red(archive)
                            else:
                                _edit(archive, self.PATH)
                            finding = third_edit_without_incident(archive, self.PATH)
                            now_refused = finding is not None
                            if was_refused:
                                self.assertTrue(
                                    now_refused,
                                    f"sequence {''.join(sequence)!r} cleared a "
                                    f"live refusal at step {step!r} with no "
                                    "incident recorded")
                            was_refused = now_refused


def _git_anchored_archive(project: Path):
    """`git init` first, THEN resolve the anchor - a subprocess hook call
    resolves its own anchor fresh from the project directory, and does so
    AFTER this test has already run `git init`. `isolated_project`'s own
    anchor is resolved at fixture entry, before the test body's `git init`
    runs, so it stays pinned to the pre-git (state-home) archive location -
    fine for every in-process-only test in this file, but a subprocess
    launched afterward would resolve a git-rooted archive instead and see
    none of what was written. Re-resolving here after `git init` keeps the
    in-process archive and the subprocess's own resolution pointed at the
    same place."""
    from godmode_runtime.godmode_anchor import resolve_anchor
    from godmode_runtime.godmode_chronicle import Chronicle

    _git(project, "init", "-q")
    return Chronicle(resolve_anchor(project))


class HookEnforcementTests(unittest.TestCase):
    """Refused at the pre-tool boundary, not merely reported by the pure
    function above - the same wiring standard `test_scope_fence.py`'s
    `HookEnforcementTests` holds the fence to."""

    HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"

    def _decide(self, project: Path, file_path: str) -> tuple[str, str]:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": file_path, "old_string": "return 1", "new_string": "return 3"},
            "cwd": str(project),
        }
        done = subprocess.run(
            [sys.executable, str(self.HOOK), "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        )
        body = (done.stdout or "").strip()
        if not body:
            return "allow", ""
        specific = json.loads(body).get("hookSpecificOutput") or {}
        return (str(specific.get("permissionDecision", "?")),
                str(specific.get("permissionDecisionReason", "")))

    def test_the_third_edit_does_not_proceed_silently(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_anchored_archive(project)
            archive.initialize()
            _seed(project)
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            decision, reason = self._decide(project, str(project / "scripts" / "widgetry.py"))
        # Fix round 2 (re-review of 039b35c, should-fix): `_decision_for`
        # reads `preview["tier"]` to decide `ask` vs `deny` - asserting the
        # exact value (not merely `!= "allow"`) is what actually exercises
        # the tier this gate sets rather than just its absence.
        self.assertEqual(decision, "ask", reason)
        self.assertIn("ran red twice", reason)
        self.assertIn("--hypothesis", reason)
        self.assertIn("--refuted-by", reason)

    def test_the_verdict_carries_the_registered_tier_and_category(self) -> None:
        """Fix round 1 (review of ac48f2d, should-fix 1): the decision text
        alone does not prove a registered tier/category backs it. Checked
        here, not against a `refusal` archive record: read carefully, this
        gate sits in the LATE Edit/Write target loop
        (`hooks/godmode_session_hook.py`, after the design/fence/frozen-
        region checks), which runs strictly after the earlier,
        classify_action-driven code that decides whether to chronicle a
        `refusal` record at all - a decision already made, for an Edit
        call, before this gate ever runs (verified directly: an Edit/Write
        refusal from this loop, unlike a Bash refusal, never appends one -
        true for the fence and frozen-region gates beside this one too, not
        something Task 6 introduced). `_two_reversals_verdict` is the one
        place tier/category are actually decided for this call, so it is
        asserted directly, against the same registered vocabulary
        (`godmode_sentinel._TIER_BY_CATEGORY`) the hook itself reads."""
        import godmode_session_hook as hook
        from godmode_runtime.godmode_sentinel import _TIER_BY_CATEGORY

        self.assertEqual(_TIER_BY_CATEGORY["fix-loop-reversal"], "R2")

        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_anchored_archive(project)
            archive.initialize()
            _seed(project)
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")

            verdict = hook._two_reversals_verdict(
                archive, project, str(project / "scripts" / "widgetry.py"))
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["tier"], "R2")
        self.assertEqual(verdict["category"], "fix-loop-reversal")

    def test_an_incident_naming_both_fields_clears_the_next_edit(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_anchored_archive(project)
            archive.initialize()
            _seed(project)
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            _red_retest(archive, project)
            _edit(archive, "scripts/widgetry.py")
            record_incident(
                archive, "widgetry keeps failing", "read the fixture before trying again",
                hypothesis="the seeded test always fails regardless of the source",
                refuted_by="python -m unittest tests.test_widgetry",
            )

            decision, reason = self._decide(project, str(project / "scripts" / "widgetry.py"))
        self.assertEqual(decision, "allow", reason)

    def test_an_ordinary_edit_with_no_loop_history_is_unaffected(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            archive = _git_anchored_archive(project)
            archive.initialize()
            _seed(project)

            decision, reason = self._decide(project, str(project / "scripts" / "widgetry.py"))
        self.assertEqual(decision, "allow", reason)


if __name__ == "__main__":
    unittest.main()
