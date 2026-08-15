"""U-R3: commit-linked experiment ledger with epsilon adjudication.

Each `run_experiment()` call is one CYCLE. `record_experiment_verdict`
adjudicates a cycle - keep/discard/keep-simpler, computed from
`{metric, before, after, epsilon}`, commit-linked via `run_git rev-parse
HEAD` - and `run_experiment` refuses to start another cycle until the one
before it has a verdict (verdict-before-next-cycle). A declared
`max_cycles` bounds the SERIES itself: exhausting it with no explicit
completion claim on record writes a closing ledger record with
`run_state: "truncated"`, never a completion (E78's positive completion
sentinel) - a completion claim is audited by U-V1's own, unmodified
citation-grading machinery, not reimplemented here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_guardrails import (  # noqa: E402
    EXPERIMENT_FILENAME,
    record_experiment_verdict,
    run_experiment,
)
from godmode_runtime.godmode_loop import analyze, unadjudicated_experiment_cycles  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PY = json.dumps(sys.executable)[1:-1]  # unquoted, shell-safe on this platform


def _write_spec(project: Path, **overrides: object) -> None:
    spec = {
        "hypothesis": "the change helps",
        "command": f'{PY} -c "pass"',
        "success_exit": 0,
        "max_runs": 1,
    }
    spec.update(overrides)
    (project / EXPERIMENT_FILENAME).write_text(json.dumps(spec), encoding="utf-8")


def _git(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(project), capture_output=True, text=True, timeout=30
    )


def _git_repo_with_commit(project: Path) -> str:
    """Init a throwaway repo, commit once, return the real HEAD digest -
    an independent measurement (plain `git rev-parse HEAD`), not the code
    under test, so the assertion has something to check against."""
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "Test")
    (project / "a.txt").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "first")
    return _git(project, "rev-parse", "HEAD").stdout.strip()


def _raw_cycle(archive, hypothesis: str, *, succeeded: bool, run_state: str = "terminated") -> dict:
    return archive.append(
        "action", f"experiment:{hypothesis}",
        {"runs": [{"attempt": 1, "exit": 0 if succeeded else 3}],
         "succeeded": succeeded, "bound": 1, "run_state": run_state},
    )


class VerdictBeforeNextCycleTests(unittest.TestCase):
    """The plant: skip a verdict, and the next cycle is refused red."""

    def test_a_second_cycle_is_refused_while_the_first_has_no_verdict(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project)
            first = run_experiment(archive, project, timeout=60)
            self.assertTrue(first["succeeded"])
            with self.assertRaises(ArchiveError) as ctx:
                run_experiment(archive, project, timeout=60)
        message = str(ctx.exception).lower()
        self.assertIn("verdict-before-next-cycle", message)
        self.assertIn(f"seq:{first['cycle_seq']}", str(ctx.exception))

    def test_recording_the_verdict_unblocks_the_next_cycle(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project)
            first = run_experiment(archive, project, timeout=60)
            record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0, epsilon=1.0,
                cycle_seq=first["cycle_seq"],
            )
            second = run_experiment(archive, project, timeout=60)
        self.assertTrue(second["succeeded"])
        self.assertNotEqual(second["cycle_seq"], first["cycle_seq"])

    def test_the_first_ever_cycle_needs_no_prior_verdict(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project)
            report = run_experiment(archive, project, timeout=60)  # must not raise
        self.assertTrue(report["succeeded"])


class EpsilonAdjudicationTests(unittest.TestCase):
    def test_improvement_at_or_above_epsilon_keeps(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "keep-case", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=10.0, after=12.0,
                epsilon=1.0, cycle_seq=cycle["sequence"],
            )
        data = record["data"]
        self.assertEqual(data["adjudication"], "keep")
        self.assertEqual(data["improvement"], 2.0)

    def test_a_worse_after_value_discards(self) -> None:
        # `improvement = after - before`: a metric where a smaller reading is
        # better (latency, error rate) must be handed to this function
        # already oriented so "after" is the higher-is-better direction -
        # this pins the raw arithmetic, not a domain-specific convention.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "worse-case", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=100.0, after=98.0,
                epsilon=1.0, cycle_seq=cycle["sequence"],
            )
        self.assertEqual(record["data"]["adjudication"], "discard")

    def test_improvement_below_epsilon_discards(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "small-gain", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=10.0, after=10.05,
                epsilon=1.0, cycle_seq=cycle["sequence"],
            )
        self.assertEqual(record["data"]["adjudication"], "discard")

    def test_equal_and_simpler_flag_is_honored(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "flat-but-simpler", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=10.0, after=10.0,
                epsilon=1.0, cycle_seq=cycle["sequence"], simpler=True,
            )
        self.assertEqual(record["data"]["adjudication"], "keep-simpler")

    def test_equal_without_the_simpler_flag_still_discards(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "flat-plain", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=10.0, after=10.0,
                epsilon=1.0, cycle_seq=cycle["sequence"], simpler=False,
            )
        self.assertEqual(record["data"]["adjudication"], "discard")

    def test_a_regression_is_not_rescued_by_the_simpler_flag(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "regression", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=10.0, after=8.0,
                epsilon=1.0, cycle_seq=cycle["sequence"], simpler=True,
            )
        self.assertEqual(record["data"]["adjudication"], "discard")

    def test_non_positive_epsilon_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "bad-epsilon", succeeded=True)
            with self.assertRaises(ArchiveError):
                record_experiment_verdict(
                    archive, project, metric="score", before=1.0, after=2.0,
                    epsilon=0.0, cycle_seq=cycle["sequence"],
                )

    def test_one_verdict_per_cycle(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "once-only", succeeded=True)
            record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=2.0,
                epsilon=0.1, cycle_seq=cycle["sequence"],
            )
            with self.assertRaises(ArchiveError):
                record_experiment_verdict(
                    archive, project, metric="score", before=1.0, after=2.0,
                    epsilon=0.1, cycle_seq=cycle["sequence"],
                )

    def test_an_unknown_cycle_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_experiment_verdict(
                    archive, project, metric="score", before=1.0, after=2.0,
                    epsilon=0.1, cycle_seq=999,
                )

    def test_no_cycle_recorded_yet_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_experiment_verdict(
                    archive, project, metric="score", before=1.0, after=2.0, epsilon=0.1,
                )


class CommitDigestTests(unittest.TestCase):
    def test_the_verdict_carries_the_real_head_digest(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            head = _git_repo_with_commit(project)
            cycle = _raw_cycle(archive, "commit-linked", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0,
                epsilon=1.0, cycle_seq=cycle["sequence"],
            )
        self.assertEqual(record["data"]["commit"], head)
        self.assertIn(f"commit:{head}", record["evidence"])

    def test_no_git_repo_records_a_none_commit_not_a_crash(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "no-git", succeeded=True)
            record = record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0,
                epsilon=1.0, cycle_seq=cycle["sequence"],
            )
        self.assertIsNone(record["data"]["commit"])


class LoopExhaustionTruncatedTests(unittest.TestCase):
    """Positive completion sentinel (E78): exhausting the declared
    `max_cycles` with no explicit completion claim writes a closing
    ledger record with run_state=truncated - loop exhaustion is never
    read as a completion."""

    def test_exhaustion_with_no_completion_claim_records_truncated_and_refuses(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project, max_cycles=1)
            first = run_experiment(archive, project, timeout=60)
            record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0,
                epsilon=1.0, cycle_seq=first["cycle_seq"],
            )
            with self.assertRaises(ArchiveError) as ctx:
                run_experiment(archive, project, timeout=60)
            closing = [
                r for r in archive.read_events()
                if r["kind"] == "verdict" and r["subject"].startswith("experiment-series-exhausted")
            ]
        self.assertEqual(len(closing), 1)
        self.assertEqual(closing[0]["data"]["run_state"], "truncated")
        self.assertIsNone(closing[0]["data"]["disposition"])
        message = str(ctx.exception).lower()
        self.assertIn("exhausted", message)
        self.assertIn("truncated", message)

    def test_exhaustion_with_a_completion_claim_on_record_refuses_differently_and_writes_nothing_new(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project, max_cycles=1)
            first = run_experiment(archive, project, timeout=60)
            verdict = record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0,
                epsilon=1.0, cycle_seq=first["cycle_seq"],
            )
            # An explicit completion claim citing the cycle's verdict.
            archive.append(
                "claim", "the experiment is complete",
                {"text": "the experiment is complete", "grade": "stated"},
                evidence=[f"verdict:{verdict['sequence']}"],
            )
            before_count = len(archive.read_events())
            with self.assertRaises(ArchiveError) as ctx:
                run_experiment(archive, project, timeout=60)
            after_count = len(archive.read_events())
        self.assertEqual(before_count, after_count)  # no new closing record written
        self.assertIn("already complete", str(ctx.exception).lower())

    def test_no_max_cycles_declared_never_exhausts(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project)  # no max_cycles at all
            first = run_experiment(archive, project, timeout=60)
            record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0,
                epsilon=1.0, cycle_seq=first["cycle_seq"],
            )
            second = run_experiment(archive, project, timeout=60)  # must not raise
        self.assertTrue(second["succeeded"])


class ArchiveSeamIntegrationTests(unittest.TestCase):
    """A truncated series feeding a confirmed verdict must hit the REAL
    archive-seam invariant (`godmode_invariants._verdict_invariants`),
    unmodified here - integration through the actual guard, not a mock."""

    def test_an_exhausted_cycle_cannot_be_recorded_confirmed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            # bound-reached: ran to its own natural stop, but never hit
            # success_exit - loop exhaustion, not an explicit completion.
            cycle = _raw_cycle(archive, "never-succeeded", succeeded=False, run_state="terminated")
            with self.assertRaises(ArchiveError) as ctx:
                record_experiment_verdict(
                    archive, project, metric="score", before=1.0, after=100.0,
                    epsilon=0.1, cycle_seq=cycle["sequence"], acquitted_by="independent",
                )
        self.assertIn("truncated", str(ctx.exception).lower())

    def test_a_budget_cut_cycle_also_cannot_be_recorded_confirmed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "budget-cut", succeeded=False, run_state="truncated")
            with self.assertRaises(ArchiveError):
                record_experiment_verdict(
                    archive, project, metric="score", before=1.0, after=100.0,
                    epsilon=0.1, cycle_seq=cycle["sequence"], acquitted_by="independent",
                )

    def test_the_self_acquitted_default_never_risks_the_invariant(self) -> None:
        """`acquitted_by="self"` (the default) never sets disposition, so
        the SAME exhausted cycle records cleanly through the default path -
        proving the refusal above is about the confirmed/truncated
        combination specifically, not about exhaustion on its own."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            cycle = _raw_cycle(archive, "never-succeeded", succeeded=False, run_state="terminated")
            record = record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=100.0, epsilon=0.1,
                cycle_seq=cycle["sequence"],
            )
        self.assertIsNone(record["data"]["disposition"])
        self.assertEqual(record["data"]["run_state"], "truncated")
        self.assertEqual(record["data"]["adjudication"], "keep")


class ReadTimeDetectionTests(unittest.TestCase):
    """`unadjudicated_experiment_cycles`: the detection-at-read half, for a
    raw append that bypasses `run_experiment`'s own write-time refusal."""

    def test_a_raw_appended_second_cycle_over_an_unverdicted_first_is_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = _raw_cycle(archive, "bypassed", succeeded=True)
            _raw_cycle(archive, "bypassed-again", succeeded=True)
            findings = unadjudicated_experiment_cycles(archive.read_events())
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["blocking"])
        self.assertIn(f"seq:{first['sequence']}", findings[0]["citations"])

    def test_a_single_unverdicted_cycle_is_not_flagged(self) -> None:
        """The latest cycle alone is allowed to be mid-flight unadjudicated."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _raw_cycle(archive, "only-one", succeeded=True)
            findings = unadjudicated_experiment_cycles(archive.read_events())
        self.assertEqual(findings, [])

    def test_a_verdicted_first_cycle_clears_the_finding(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = _raw_cycle(archive, "clean", succeeded=True)
            record_experiment_verdict(
                archive, project, metric="score", before=1.0, after=5.0,
                epsilon=1.0, cycle_seq=first["sequence"],
            )
            _raw_cycle(archive, "clean-again", succeeded=True)
            findings = unadjudicated_experiment_cycles(archive.read_events())
        self.assertEqual(findings, [])

    def test_analyze_surfaces_the_same_finding_as_a_blocking_verdict(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _raw_cycle(archive, "bypassed", succeeded=True)
            _raw_cycle(archive, "bypassed-again", succeeded=True)
            report = analyze(archive)
        detectors = {f["detector"] for f in report["findings"]}
        self.assertIn("unadjudicated-experiment-cycle", detectors)
        self.assertTrue(report["blocking"])


class ConsoleSmokeTests(unittest.TestCase):
    def test_experiment_run_then_verdict_through_the_cli(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project)
            from godmode_runtime.godmode_console import main

            run_code = main(["--project", str(project), "experiment", "run"])
            cycles = [r for r in archive.read_events() if r["kind"] == "action"
                     and r["subject"].startswith("experiment:")]
            self.assertEqual(run_code, 0)
            self.assertEqual(len(cycles), 1)
            verdict_code = main([
                "--project", str(project), "experiment", "verdict",
                "--metric", "score", "--before", "1", "--after", "5", "--epsilon", "1",
            ])
        self.assertEqual(verdict_code, 0)

    def test_a_second_cli_run_before_a_verdict_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_spec(project)
            from godmode_runtime.godmode_console import main

            main(["--project", str(project), "experiment", "run"])
            with self.assertRaises(ArchiveError):
                run_experiment(archive, project, timeout=60)


if __name__ == "__main__":
    unittest.main()
