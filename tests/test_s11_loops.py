"""S11: the loops maintain themselves.

A: the debrief gauges its own staleness. D: `law amend` executes a
recommendation and newest-wins makes it the law. E: an instruction marker
with no imperative verb behind it is conversation, not a rule - both live
false captures from 2026-08-29 fail that bar. C: the flake registry parses.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from _law_fixtures import operator_lesson  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    amend_law, debrief, debrief_status, record_instruction_candidate, top_laws,
)


class DebriefGaugeTests(unittest.TestCase):
    def test_no_receipt_ever_reads_stale(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            status = debrief_status(archive)
        self.assertTrue(status["stale"])
        self.assertIsNone(status["last_receipt_seq"])

    def test_a_fresh_debrief_clears_staleness(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            debrief(archive)
            status = debrief_status(archive)
        self.assertFalse(status["stale"])
        self.assertLessEqual(status["records_since"], 1)


class AmendTests(unittest.TestCase):
    """NS-2 (the authority gate) reaches the amendment loop: a guard is the
    law only with approval lineage or operator trust. These laws are the
    operator's (`tests/_law_fixtures.operator_lesson`), and the amendments
    below are the operator's too - `amend_law(..., as_operator=True)` is the
    same write `law amend --as-operator` makes. `PendingAmendmentTests`
    covers the other actor: an agent's amendment never unseats them."""

    def _law(self, archive, subject, guard, **extra):
        return operator_lesson(archive, subject, guard, **extra)

    def _amend(self, archive, seq, guard):
        return amend_law(archive, seq, guard,
                         as_operator=True, operator_verified=True)

    def test_an_amendment_becomes_the_law(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "one-law", "old guard text here")["sequence"]
            amended = self._amend(archive, seq, "new guard text here, reviewed")
            laws = top_laws(archive, 5)
        self.assertFalse(amended["pending"])
        subjects = [l["subject"] for l in laws]
        self.assertEqual(subjects.count("one-law"), 1)
        self.assertIn("new guard", laws[0]["guard"])
        self.assertIsNone(laws[0]["pending_amendment"])

    def test_amending_a_retired_law_refuses(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "dead-law", "old guard")["sequence"]
            # The operator retires it: the single-writer close guard
            # (NS-11h) already refuses an agent closing an operator's lesson.
            archive.append("lesson", "dead-law", {"status": "retired"}, evidence=[],
                           as_operator=True, operator_verified=True)
            with self.assertRaises(ArchiveError):
                amend_law(archive, seq, "resurrection attempt")

    def test_an_empty_guard_refuses(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "a-law", "guard")["sequence"]
            with self.assertRaises(ArchiveError):
                amend_law(archive, seq, "   ")

    def test_amending_a_standing_law_keeps_it_pinned(self) -> None:
        # A standing law's pin lives on the record newest-wins dedup reads;
        # amending it must carry the flag forward, or a reworded guard
        # silently un-pins a law the operator marked enforcing.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(archive, "standing-law", "old guard",
                            standing=True)["sequence"]
            for index in range(3):
                self._law(archive, f"newer-{index}", f"guard {index}")
            self._amend(archive, seq, "new guard text here, reviewed")
            laws = top_laws(archive, 2)
        self.assertEqual(laws[0]["subject"], "standing-law")
        self.assertTrue(laws[0]["standing"])
        self.assertIn("new guard", laws[0]["guard"])

    def test_amending_an_enforcing_law_keeps_the_guard_armed(self) -> None:
        # I-1 fix round 2 (Blocking 3): `amend_law` built its replacement
        # lesson from scratch and carried forward only `standing`, never
        # `enforce`. `Chronicle._refuse_incomplete_supersession` refuses ANY
        # `lesson` append on a subject with an active `enforce` unless the
        # new record reaffirms it or moves to a dormant status, so amending
        # an enforcing law used to be refused outright, with no way for
        # this verb to comply - amending is exactly the "living law" case
        # the completeness rule is supposed to let through.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = self._law(
                archive, "no-todo", "no TODOs", value="guard",
                enforce={"kind": "decision", "predicate": "value contains TODO"},
            )["sequence"]
            self._amend(archive, seq, "no TODOs, reworded")
            laws = top_laws(archive, 5)
        self.assertEqual(laws[0]["subject"], "no-todo")
        self.assertIn("reworded", laws[0]["guard"])
        # The guard is still armed - the amendment reworded it, not
        # silently disarmed it.
        with self.assertRaises(ArchiveError):
            archive.append("decision", "ship-it", {"value": "a TODO here", "status": "active"})


class PendingAmendmentTests(unittest.TestCase):
    """The regression the 0.3.28 release preflight found: with the gate read
    on the newest record only, an agent's `law amend` on an operator's law
    wrote a record the gate refused and the subject compiled NOTHING - the
    operator's standing law vanished because an agent edited it. Now the
    amendment is pending, the authorised guard binds until it is approved,
    and every reader says so."""

    def test_an_agent_amendment_leaves_the_operator_guard_in_force(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = operator_lesson(archive, "one-law", "the operator guard")["sequence"]
            amended = amend_law(archive, seq, "an agent rewording")
            laws = top_laws(archive, 5)
        self.assertTrue(amended["pending"])
        self.assertEqual([l["subject"] for l in laws], ["one-law"])
        self.assertEqual(laws[0]["guard"], "the operator guard")
        self.assertEqual(laws[0]["seq"], seq)
        self.assertEqual(laws[0]["pending_amendment"], amended["sequence"])

    def test_a_standing_law_stays_pinned_through_a_pending_amendment(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = operator_lesson(archive, "standing-law", "old guard",
                                  standing=True)["sequence"]
            for index in range(3):
                operator_lesson(archive, f"newer-{index}", f"guard {index}")
            amend_law(archive, seq, "an agent rewording")
            laws = top_laws(archive, 2)
        self.assertEqual(laws[0]["subject"], "standing-law")
        self.assertTrue(laws[0]["standing"])
        self.assertEqual(laws[0]["guard"], "old guard")

    def test_an_agent_cannot_revive_a_retired_law_by_amending_it(self) -> None:
        # The walk back stops at a retirement: `amend_law` itself refuses a
        # retired subject, so this is the raw append an agent could still
        # make - and it revives nothing. The retirement is the operator's;
        # the single-writer close guard (NS-11h) refuses an agent's.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            operator_lesson(archive, "dead-law", "the operator guard")
            archive.append("lesson", "dead-law", {"status": "retired"}, evidence=[],
                           as_operator=True, operator_verified=True)
            archive.append("lesson", "dead-law", {
                "status": "active", "generalized_guard": "back from the dead"},
                evidence=[])
            laws = top_laws(archive, 5)
        self.assertEqual(laws, [])

    def test_an_agent_cannot_lift_an_operator_law_with_status_superseded(self) -> None:
        """Review B2: `retired` was refused by the single-writer close
        guard, `superseded` was not, and the compiler read it as a lift -
        one status word de-legislated the operator. Two layers now: the
        archive refuses the write as a close, and even a record that gets
        past it (here: the same write forced through the guard-free append
        path a test can reach) is pending, not a lift, because its trust
        is below the standing record's."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = operator_lesson(archive, "one-law", "the operator guard")["sequence"]
            with self.assertRaises(ArchiveError) as refused:
                archive.append("lesson", "one-law", {
                    "status": "superseded", "generalized_guard": "AGENT rewrite"},
                    evidence=[f"seq:{seq}"])
            self.assertIn("lower-trust writer may not close", str(refused.exception))
            laws = top_laws(archive, 5)
        self.assertEqual([l["guard"] for l in laws], ["the operator guard"])

    def test_an_agent_still_supersedes_its_own_lesson(self) -> None:
        # The close guard keys on creator identity and trust rank: an
        # agent's own lesson is its own to end, with either word.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("lesson", "mine", {
                "status": "active", "generalized_guard": "first"}, evidence=[])
            record = archive.append("lesson", "mine", {
                "status": "superseded", "generalized_guard": "first"}, evidence=[])
        self.assertEqual(record["data"]["status"], "superseded")

    def test_a_second_operator_amendment_supersedes_the_pending_one(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            seq = operator_lesson(archive, "one-law", "first")["sequence"]
            amend_law(archive, seq, "an agent rewording")
            amend_law(archive, seq, "the operator rewording",
                      as_operator=True, operator_verified=True)
            laws = top_laws(archive, 5)
        self.assertEqual(laws[0]["guard"], "the operator rewording")
        self.assertIsNone(laws[0]["pending_amendment"])


class InstructionPrecisionTests(unittest.TestCase):
    def test_the_live_false_capture_no_longer_fires(self) -> None:
        # Verbatim shape of the 2026-08-29 chat-noise capture (seq 4583).
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(record_instruction_candidate(
                archive, "Whenever ready: 9 fragments to v0.3.3 why dont we "
                         "do this now?", session="S-1"))

    def test_a_real_standing_rule_still_fires(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_instruction_candidate(
                archive, "always run the godmode-governance preview before "
                         "any multi-file removal or untracking", session="S-1")
        self.assertIsNotNone(record)

    def test_a_marker_with_a_distant_verb_does_not_fire(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(record_instruction_candidate(
                archive, "never in all my years of looking at broken pipelines "
                         "and flaky suites did the batch run clean", session="S-1"))


class CandidateDismissalTests(unittest.TestCase):
    def test_a_retired_candidate_leaves_the_cluster_list(self) -> None:
        from godmode_runtime.godmode_law import law_candidates

        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_instruction_candidate(
                archive, "always run the preview before removals",
                session="S-1")
            self.assertEqual(len(law_candidates(archive)), 1)
            archive.append("lesson", record["subject"],
                           {"status": "retired"}, evidence=[])
            self.assertEqual(law_candidates(archive), [])


class FlakyRegistryTests(unittest.TestCase):
    def test_registry_parses_and_names_the_known_flake(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "dev"))
        import run_with_flaky_retry as runner

        flaky = runner.known_flaky()
        self.assertIn(
            "tests.test_law.BriefTests.test_session_start_brief_carries_the_top_laws",
            flaky)

    def test_failure_parser_reads_unittest_output(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "dev"))
        import run_with_flaky_retry as runner

        sample = ("FAIL: test_x (tests.test_mod.SomeTests.test_x)\n"
                  "ERROR: test_y (tests.test_other.OtherTests.test_y)\n")
        self.assertEqual(runner.failing_ids(sample),
                         ["tests.test_mod.SomeTests.test_x",
                          "tests.test_other.OtherTests.test_y"])


class ClaimSupersessionTests(unittest.TestCase):
    def test_a_verified_retry_clears_the_downgraded_listing(self) -> None:
        # Observed live 2026-08-29: two hypothesis-graded retries sat in
        # `status remaining` beside their own verified successor.
        import inspect

        from godmode_runtime.godmode_attest import open_session, record_claim
        from godmode_runtime.godmode_status import remaining

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "supersede")
            text = "the queue holds three commits tonight"
            record_claim(archive, project, session, text, "verified", cites=[])
            parameters = set(inspect.signature(remaining).parameters)
            kwargs = {}
            if "session" in parameters:
                kwargs["session"] = session
            if "project" in parameters:
                kwargs["project"] = project
            listed = remaining(archive, **kwargs)
            self.assertTrue(any(
                e["source"] == "claim" for e in listed["remaining"]))
            archive.append("action", "attest-cmd", {}, evidence=[])
            record_claim(archive, project, session, text, "observed", cites=[])
            cleared = remaining(archive, **kwargs)
            self.assertFalse(any(
                e["source"] == "claim" for e in cleared["remaining"]))


class HostAwareGuideTests(unittest.TestCase):
    def _guide(self, env_extra: dict) -> str:
        import os
        import subprocess

        env = {k: v for k, v in os.environ.items()
               if k not in ("GODMODE_HOST", "GROK_AGENT", "GROK_PLUGIN_ROOT",
                            "GROK_HOOK_EVENT", "CLAUDE_CODE_ENTRYPOINT",
                            "PLUGIN_ROOT")}
        env.update(env_extra)
        done = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
             "guide"], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, env=env)
        return done.stdout

    def test_a_no_ask_host_sees_deny_not_ask(self) -> None:
        text = self._guide({"GROK_PLUGIN_ROOT": "C:/x"})
        self.assertIn("HAS NO ASK", text)
        self.assertIn("authorize stage", text)
        self.assertNotIn("WHAT ASKS FIRST", text)

    def test_an_ask_host_keeps_the_dialog_line(self) -> None:
        text = self._guide({"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertIn("WHAT ASKS FIRST", text)
        self.assertNotIn("HAS NO ASK", text)


class VersionOneLinerTests(unittest.TestCase):
    def test_bare_version_prints_the_package_and_writes_nothing(self) -> None:
        import subprocess

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            before = len(archive.read_events())
            done = subprocess.run(
                [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
                 "--project", str(project), "version"],
                capture_output=True, text=True, encoding="utf-8", timeout=120)
            archive._events_cache_key = None
            after = len(archive.read_events())
        self.assertIn("0.3.", done.stdout)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
