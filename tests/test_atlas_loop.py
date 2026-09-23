"""NS-1 (0.3.28 Plan 5 Task 1): loop records and `atlas loop`.

A retry loop cannot see itself repeating from inside - each attempt
arrives with a plausible next idea and the same underlying failure.
`godmode_looprecords.py` records one attempt's failure signature (the
failing test ids plus the shape of the diff that produced them) per
`loop_step`, and `advance` refuses (`loop_halt`) a third identical one.
Budgets - an operator's own stop flag, then steps, tokens, wall time, in
that order - are checked BEFORE the signature test ever runs. A halt is
reopened only by `resume` evidence from a different actor than whoever
hit the halt.

This suite exercises: signature determinism and sensitivity to each
input; the third-identical-failure halt (and that a changed signature is
allowed); every budget exhaustion, in priority order, with fabricated
ceilings and no wall clock; resume refused for the same actor and
allowed for a different one; and that the kind invariants refuse a
malformed record reaching the archive by a raw append.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_guardrails import OPERATOR_STOP_FLAG  # noqa: E402
from godmode_runtime import godmode_invariants  # noqa: E402
from godmode_runtime import godmode_looprecords as looprecords  # noqa: E402


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-atlas-loop-") as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            yield project, archive


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


_NO_CEILINGS = {"steps": 0, "tokens": 0, "wall_time": 0}
_NO_SPEND = {"steps": 0, "tokens": 0, "wall_time": 0}


class SignatureTests(unittest.TestCase):
    def test_deterministic_for_the_same_inputs(self) -> None:
        shape = {"files": ["a.py", "b.py"], "hunks": 3}
        first = looprecords.signature(["t1", "t2"], shape)
        second = looprecords.signature(["t1", "t2"], shape)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_order_independent_in_test_ids_and_files(self) -> None:
        shape_a = {"files": ["a.py", "b.py"], "hunks": 2}
        shape_b = {"files": ["b.py", "a.py"], "hunks": 2}
        self.assertEqual(
            looprecords.signature(["t2", "t1"], shape_a),
            looprecords.signature(["t1", "t2"], shape_b),
        )

    def test_sensitive_to_failing_test_ids(self) -> None:
        shape = {"files": ["a.py"], "hunks": 1}
        self.assertNotEqual(
            looprecords.signature(["t1"], shape),
            looprecords.signature(["t1", "t2"], shape),
        )

    def test_sensitive_to_files(self) -> None:
        self.assertNotEqual(
            looprecords.signature(["t1"], {"files": ["a.py"], "hunks": 1}),
            looprecords.signature(["t1"], {"files": ["a.py", "b.py"], "hunks": 1}),
        )

    def test_sensitive_to_hunk_count(self) -> None:
        self.assertNotEqual(
            looprecords.signature(["t1"], {"files": ["a.py"], "hunks": 1}),
            looprecords.signature(["t1"], {"files": ["a.py"], "hunks": 2}),
        )


class BudgetOrderTests(unittest.TestCase):
    """Fabricated ceilings, no wall clock: `check_budgets` is pure."""

    def test_within_every_budget_is_not_halted(self) -> None:
        result = looprecords.check_budgets(
            {"steps": 10, "tokens": 1000, "wall_time": 600},
            {"steps": 1, "tokens": 10, "wall_time": 5},
        )
        self.assertFalse(result["halted"])
        self.assertEqual(result["remaining"], {"steps": 9, "tokens": 990, "wall_time": 595})

    def test_a_zero_ceiling_never_exhausts(self) -> None:
        result = looprecords.check_budgets(_NO_CEILINGS, {"steps": 999999, "tokens": 999999, "wall_time": 999999})
        self.assertFalse(result["halted"])
        self.assertEqual(result["remaining"], {"steps": None, "tokens": None, "wall_time": None})

    def test_interrupted_outranks_every_ceiling(self) -> None:
        result = looprecords.check_budgets(
            {"steps": 1, "tokens": 1, "wall_time": 1},
            {"steps": 999, "tokens": 999, "wall_time": 999},
            interrupted="OperatorStop: flag present",
        )
        self.assertTrue(result["halted"])
        self.assertEqual(result["reason"], looprecords.REASON_INTERRUPTED)

    def test_steps_exhausts_before_tokens_and_wall_time(self) -> None:
        result = looprecords.check_budgets(
            {"steps": 1, "tokens": 1, "wall_time": 1},
            {"steps": 2, "tokens": 2, "wall_time": 2},
        )
        self.assertTrue(result["halted"])
        self.assertEqual(result["reason"], "steps-exhausted")

    def test_tokens_exhausts_before_wall_time_when_steps_is_fine(self) -> None:
        result = looprecords.check_budgets(
            {"steps": 10, "tokens": 1, "wall_time": 1},
            {"steps": 0, "tokens": 2, "wall_time": 2},
        )
        self.assertTrue(result["halted"])
        self.assertEqual(result["reason"], "tokens-exhausted")

    def test_wall_time_exhausts_last(self) -> None:
        result = looprecords.check_budgets(
            {"steps": 10, "tokens": 10, "wall_time": 1},
            {"steps": 0, "tokens": 0, "wall_time": 2},
        )
        self.assertTrue(result["halted"])
        self.assertEqual(result["reason"], "wall_time-exhausted")


class AdvanceWithBudgetsTests(unittest.TestCase):
    def test_each_budget_exhaustion_writes_a_named_halt_with_no_signatures(self) -> None:
        for name, ceilings, spent in (
            ("steps-exhausted", {"steps": 1, "tokens": 0, "wall_time": 0}, {"steps": 2, "tokens": 0, "wall_time": 0}),
            ("tokens-exhausted", {"steps": 0, "tokens": 1, "wall_time": 0}, {"steps": 0, "tokens": 2, "wall_time": 0}),
            ("wall_time-exhausted", {"steps": 0, "tokens": 0, "wall_time": 1}, {"steps": 0, "tokens": 0, "wall_time": 2}),
        ):
            with _archive() as (_project, archive), self.subTest(name=name):
                result = looprecords.advance_with_budgets(
                    archive, task="t", failing_test_ids=["t1"], diff_shape={"files": [], "hunks": 0},
                    ceilings=ceilings, spent=spent,
                )
                self.assertTrue(result["halted"])
                self.assertEqual(result["reason"], name)
                self.assertEqual(result["signatures"], [])
                self.assertEqual(result["record"]["kind"], "loop_halt")
                self.assertEqual(result["record"]["data"]["signatures"], [])

    def test_interrupted_halts_before_any_budget_or_signature_check(self) -> None:
        with _archive() as (_project, archive):
            result = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape={"files": [], "hunks": 0},
                ceilings=_NO_CEILINGS, spent=_NO_SPEND, interrupted="OperatorStop: flag present",
            )
            self.assertTrue(result["halted"])
            self.assertEqual(result["reason"], looprecords.REASON_INTERRUPTED)

    def test_a_changed_signature_is_allowed(self) -> None:
        with _archive() as (_project, archive):
            first = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape={"files": ["a.py"], "hunks": 1},
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            second = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t2"], diff_shape={"files": ["b.py"], "hunks": 1},
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            third = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape={"files": ["a.py"], "hunks": 1},
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            self.assertFalse(first["halted"])
            self.assertFalse(second["halted"])
            self.assertFalse(third["halted"])
            self.assertEqual([r["attempt_n"] for r in (first, second, third)], [1, 2, 3])

    def test_a_single_differing_attempt_resets_the_run_a_a_b_a(self) -> None:
        # The halt rule compares the new signature against the last TWO
        # loop_step signatures for the task, not against any earlier one:
        # A,A,B,A never halts, because attempt 4's two predecessors are
        # (A,B), not a matching pair. Pinned because the likely regression
        # is an off-by-one that compares against "any prior signature".
        with _archive() as (_project, archive):
            a_shape = {"files": ["a.py"], "hunks": 1}
            b_shape = {"files": ["b.py"], "hunks": 2}
            results = []
            for ids, shape in (
                (["t1"], a_shape), (["t1"], a_shape), (["t2"], b_shape), (["t1"], a_shape),
            ):
                results.append(looprecords.advance_with_budgets(
                    archive, task="t", failing_test_ids=ids, diff_shape=shape,
                    ceilings=_NO_CEILINGS, spent=_NO_SPEND,
                ))
            self.assertEqual([r["halted"] for r in results], [False, False, False, False])
            self.assertEqual([r["attempt_n"] for r in results], [1, 2, 3, 4])
            # A fifth identical A now has (A,A) immediately behind it and halts.
            fifth = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape=a_shape,
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            self.assertFalse(fifth["halted"])
            sixth = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape=a_shape,
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            self.assertTrue(sixth["halted"])
            self.assertEqual(sixth["reason"], looprecords.REASON_SIGNATURE_REPEATED)

    def test_third_identical_signature_halts_with_all_three_signatures(self) -> None:
        with _archive() as (_project, archive):
            shape = {"files": ["a.py"], "hunks": 1}
            first = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape=shape,
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            second = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape=shape,
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            third = looprecords.advance_with_budgets(
                archive, task="t", failing_test_ids=["t1"], diff_shape=shape,
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
            self.assertFalse(first["halted"])
            self.assertFalse(second["halted"])
            self.assertTrue(third["halted"])
            self.assertEqual(third["reason"], looprecords.REASON_SIGNATURE_REPEATED)
            self.assertEqual(len(third["signatures"]), 3)
            self.assertEqual(len(set(third["signatures"])), 1)
            self.assertEqual(third["record"]["kind"], "loop_halt")
            self.assertEqual(third["record"]["data"]["task"], "t")


class ResumeTests(unittest.TestCase):
    def _halt(self, archive, task: str = "t") -> dict:
        shape = {"files": ["a.py"], "hunks": 1}
        for _ in range(3):
            result = looprecords.advance_with_budgets(
                archive, task=task, failing_test_ids=["t1"], diff_shape=shape,
                ceilings=_NO_CEILINGS, spent=_NO_SPEND,
            )
        return result

    def test_resume_refused_when_evidence_is_from_the_same_actor(self) -> None:
        with _archive() as (_project, archive):
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-a"}, clear=False):
                halt = self._halt(archive)
                self.assertTrue(halt["halted"])
                evidence = archive.append("attestation", "self-review", {"status": "ran"})
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-a"}, clear=False):
                result = looprecords.resume(
                    archive, task="t", evidence_cite=f"seq:{evidence['sequence']}")
            self.assertFalse(result["resumed"])
            self.assertEqual(result["reason"], "same-actor")

    def test_resume_refused_when_no_agent_id_is_declared_on_either_side(self) -> None:
        # With GODMODE_AGENT_ID undeclared - the common single-agent case -
        # every write on one project shares one derived id, so the
        # actor-separateness rule refuses structurally, whoever wrote the
        # evidence. Same limitation the chronicle's own ownership check
        # carries: it bites once the host declares a distinct id per agent.
        with _archive() as (_project, archive):
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GODMODE_AGENT_ID", None)
                halt = self._halt(archive)
                self.assertTrue(halt["halted"])
                evidence = archive.append("attestation", "checker-review", {"status": "ran"})
                result = looprecords.resume(
                    archive, task="t", evidence_cite=f"seq:{evidence['sequence']}")
            self.assertFalse(result["resumed"])
            self.assertEqual(result["reason"], "same-actor")

    def test_resume_allowed_when_evidence_is_from_a_different_actor(self) -> None:
        with _archive() as (_project, archive):
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-a"}, clear=False):
                self._halt(archive)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-b"}, clear=False):
                evidence = archive.append("attestation", "checker-review", {"status": "ran"})
                result = looprecords.resume(
                    archive, task="t", evidence_cite=f"seq:{evidence['sequence']}")
            self.assertTrue(result["resumed"])
            self.assertEqual(result["record"]["kind"], "action")

    def test_resume_resets_the_signature_comparison_window(self) -> None:
        with _archive() as (_project, archive):
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-a"}, clear=False):
                self._halt(archive)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-b"}, clear=False):
                evidence = archive.append("attestation", "checker-review", {"status": "ran"})
                resumed = looprecords.resume(archive, task="t", evidence_cite=f"seq:{evidence['sequence']}")
                self.assertTrue(resumed["resumed"])
                # Same identical signature again, right after resume: allowed once
                # (attempt 1 of the new window), not an instant re-halt.
                shape = {"files": ["a.py"], "hunks": 1}
                again = looprecords.advance_with_budgets(
                    archive, task="t", failing_test_ids=["t1"], diff_shape=shape,
                    ceilings=_NO_CEILINGS, spent=_NO_SPEND,
                )
            self.assertFalse(again["halted"])
            self.assertEqual(again["attempt_n"], 1)

    def test_resume_refused_with_no_halt_recorded(self) -> None:
        with _archive() as (_project, archive):
            evidence = archive.append("attestation", "checker-review", {"status": "ran"})
            result = looprecords.resume(archive, task="never-halted", evidence_cite=f"seq:{evidence['sequence']}")
            self.assertFalse(result["resumed"])
            self.assertEqual(result["reason"], "no-halt")

    def test_resume_refuses_a_malformed_evidence_citation(self) -> None:
        with _archive() as (_project, archive):
            self._halt(archive)
            with self.assertRaises(ArchiveError):
                looprecords.resume(archive, task="t", evidence_cite="not-a-seq-cite")


class InvariantTests(unittest.TestCase):
    def test_reason_vocabularies_stay_in_sync(self) -> None:
        # godmode_invariants.py stays dependency-free of every archive-owning
        # module (so godmode_chronicle can import it with no cycle) and
        # therefore hand-copies this module's own halt reasons - this pins
        # the two sets equal so a new reason added to one is never silently
        # missing from the other.
        self.assertEqual(godmode_invariants.LOOP_HALT_REASONS, looprecords.halt_reasons())

    def test_loop_step_refuses_missing_task(self) -> None:
        with _archive() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append("loop_step", "loop:t", {
                    "attempt_n": 1, "failure_signature_hash": "a" * 64,
                    "budget_remaining": {"steps": None, "tokens": None, "wall_time": None},
                })

    def test_loop_step_refuses_a_non_sha256_signature(self) -> None:
        with _archive() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append("loop_step", "loop:t", {
                    "task": "t", "attempt_n": 1, "failure_signature_hash": "not-a-hash",
                    "budget_remaining": {"steps": None, "tokens": None, "wall_time": None},
                })

    def test_loop_step_refuses_a_malformed_budget(self) -> None:
        with _archive() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append("loop_step", "loop:t", {
                    "task": "t", "attempt_n": 1, "failure_signature_hash": "a" * 64,
                    "budget_remaining": {"steps": -1, "tokens": None, "wall_time": None},
                })

    def test_loop_halt_refuses_an_unknown_reason(self) -> None:
        with _archive() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append("loop_halt", "loop:t", {
                    "task": "t", "reason": "made-up-reason", "signatures": [],
                })

    def test_loop_halt_refuses_two_signatures_for_a_repeated_reason(self) -> None:
        with _archive() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append("loop_halt", "loop:t", {
                    "task": "t", "reason": looprecords.REASON_SIGNATURE_REPEATED,
                    "signatures": ["a" * 64, "a" * 64],
                })

    def test_loop_halt_refuses_signatures_on_a_budget_reason(self) -> None:
        with _archive() as (_project, archive):
            with self.assertRaises(ArchiveError):
                archive.append("loop_halt", "loop:t", {
                    "task": "t", "reason": "steps-exhausted", "signatures": ["a" * 64],
                })


class DiffFromGitTests(unittest.TestCase):
    def test_diff_shape_from_git_counts_files_and_hunks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-loop-git-") as temporary:
            project = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=project, check=True)
            (project / "a.py").write_text("one\ntwo\nthree\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=project, check=True)
            subprocess.run(["git", "commit", "-qm", "seed"], cwd=project, check=True)
            (project / "a.py").write_text("one\nCHANGED\nthree\n\nfour\n", encoding="utf-8")
            shape = looprecords.diff_shape_from_git(project)
            self.assertEqual(shape["files"], ["a.py"])
            self.assertGreaterEqual(shape["hunks"], 1)

    def test_no_diff_is_an_empty_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-loop-git-") as temporary:
            project = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            shape = looprecords.diff_shape_from_git(project)
            self.assertEqual(shape, {"files": [], "hunks": 0})


class CliTests(unittest.TestCase):
    def test_advance_and_third_identical_halt_and_resume_via_cli(self) -> None:
        with _archive() as (project, _archive_obj):
            code, _ = _run(project, "init")
            self.assertEqual(code, 0)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-a"}, clear=False):
                code1, payload1 = _run(project, "atlas", "loop", "advance", "--task", "t",
                                       "--failing", "t1")
                self.assertEqual(code1, 0)
                self.assertFalse(payload1["halted"])
                code2, payload2 = _run(project, "atlas", "loop", "advance", "--task", "t",
                                       "--failing", "t1")
                self.assertEqual(code2, 0)
                code3, payload3 = _run(project, "atlas", "loop", "advance", "--task", "t",
                                       "--failing", "t1")
                self.assertEqual(code3, 2)
                self.assertTrue(payload3["halted"])
                self.assertEqual(payload3["reason"], looprecords.REASON_SIGNATURE_REPEATED)
                self.assertEqual(len(payload3["signatures"]), 3)
            # Same actor's own record is refused as resume evidence.
            code_same, payload_same = _run(
                project, "atlas", "loop", "resume", "--task", "t", "--evidence", "seq:1")
            self.assertEqual(code_same, 2)
            self.assertFalse(payload_same["resumed"])
            # A different actor's record reopens it.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-b"}, clear=False):
                code_open, _ = _run(project, "session", "open")
                self.assertEqual(code_open, 0)
                code_att, payload_att = _run(
                    project, "attest", "--step", "checker-review", "--status", "ran")
                self.assertEqual(code_att, 0)
                evidence_seq = payload_att["record"]["sequence"]
                code_resume, payload_resume = _run(
                    project, "atlas", "loop", "resume", "--task", "t",
                    "--evidence", f"seq:{evidence_seq}")
            self.assertEqual(code_resume, 0)
            self.assertTrue(payload_resume["resumed"])

    def test_operator_stop_flag_halts_before_the_signature_test(self) -> None:
        with _archive() as (project, _archive_obj):
            code, _ = _run(project, "init")
            self.assertEqual(code, 0)
            (project / OPERATOR_STOP_FLAG).write_text("", encoding="utf-8")
            code_advance, payload = _run(
                project, "atlas", "loop", "advance", "--task", "t", "--failing", "t1")
            self.assertEqual(code_advance, 2)
            self.assertTrue(payload["halted"])
            self.assertEqual(payload["reason"], looprecords.REASON_INTERRUPTED)

    def test_diff_from_git_flag_is_reachable(self) -> None:
        with _archive() as (project, _archive_obj):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            code, _ = _run(project, "init")
            self.assertEqual(code, 0)
            code_advance, payload = _run(
                project, "atlas", "loop", "advance", "--task", "t", "--failing", "t1",
                "--diff-from-git")
            self.assertEqual(code_advance, 0)
            self.assertFalse(payload["halted"])


if __name__ == "__main__":
    unittest.main()
