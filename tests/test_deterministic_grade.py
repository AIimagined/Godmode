"""The done-bar grade as a deterministic picker (obligations 10118, 10245, 9702).

Twenty-first field report: "grades observed without executing anything". A
claim cited with a file or sequence earned `observed` and the done-bar
passed it. Now, from three independent sources in the research ledger
(the deterministic-picker pattern, a verifier-gated RL objective, and a
grounded-claims sidecar): the deciding grade is composed from executed
predicates in Python, never asserted. A run-shaped claim (tests pass, the
build is green, the suite ran) citing `cmd:<command>` is `verified` only
when an attestation for that exact command ran green on the current tree;
otherwise it stays `observed` and the done-bar names the executed check
that would settle it, once.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime.godmode_attest import (  # noqa: E402
    executed_predicates, open_session, record_claim, run_check,
)
from godmode_runtime.godmode_claimscan import recorded_claim_grades  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
from godmode_session_hook import _unrecorded_done_claims, _settleable_done_claims  # noqa: E402

TRUE_CMD = [sys.executable, "-c", "import sys; sys.exit(0)"]
CITE = "cmd:" + " ".join(TRUE_CMD)[:160]


def _git_project(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                    "--allow-empty", "-m", "first"], cwd=project, check=True)


class ExecutedPredicatesTests(unittest.TestCase):
    def test_a_green_attestation_for_the_cited_command_on_this_tree_composes_verified(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            run_check(archive, session, project, "suite", TRUE_CMD)
            predicates = executed_predicates(archive, project, [CITE])
            self.assertTrue(predicates["check_ran"])
            self.assertTrue(predicates["exit_recorded"])
            self.assertTrue(predicates["head_matches"])
            self.assertEqual(predicates["grade"], "verified")
            record = record_claim(archive, project, session, "All tests pass on the suite",
                                  "observed", cites=[CITE])
            self.assertEqual(record["data"]["grade"], "verified")
            self.assertEqual(record["data"]["composed_from"], ["check_ran", "exit_recorded", "head_matches"])

    def test_no_attestation_keeps_observed_and_names_the_settling_check(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            record = record_claim(archive, project, session, "All tests pass on the suite",
                                  "observed", cites=[CITE])
            self.assertEqual(record["data"]["grade"], "observed")
            self.assertIn("claim --verify", record["data"]["settleable_by"])

    def test_a_red_attestation_never_composes_verified(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            red = [sys.executable, "-c", "import sys; sys.exit(3)"]
            run_check(archive, session, project, "suite", red)
            cite = "cmd:" + " ".join(red)[:160]
            self.assertEqual(executed_predicates(archive, project, [cite])["grade"], "observed")

    def test_a_claim_no_command_can_settle_is_left_alone(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            record = record_claim(archive, project, session, "The design favours one file",
                                  "observed", cites=["docs/x.md"])
            self.assertEqual(record["data"]["grade"], "observed")
            self.assertNotIn("settleable_by", record["data"])


class DoneBarPicksExecutedGradeTests(unittest.TestCase):
    def test_grades_are_readable_per_recorded_claim(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            record_claim(archive, project, session, "All tests pass on the suite", "observed", cites=[CITE])
            grades = recorded_claim_grades(archive)
            self.assertEqual(set(grades.values()), {"observed"})

    def test_a_recorded_observed_run_claim_is_named_as_settleable_at_the_done_bar(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            record_claim(archive, project, session, "All tests pass on the suite", "observed", cites=[CITE])
            reply = "Done. All tests pass on the suite."
            # Recorded, so not unrecorded...
            self.assertEqual(_unrecorded_done_claims(archive, reply), [])
            # ...but recorded on an asserted grade an executed check could settle.
            settleable = _settleable_done_claims(archive, reply)
            self.assertEqual(len(settleable), 1)
            self.assertIn("All tests pass", settleable[0])

    def test_a_verified_run_claim_is_not_settleable(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize(); _git_project(project)
            session = open_session(archive, "t")
            run_check(archive, session, project, "suite", TRUE_CMD)
            record_claim(archive, project, session, "All tests pass on the suite", "observed", cites=[CITE])
            self.assertEqual(_settleable_done_claims(archive, "All tests pass on the suite."), [])


if __name__ == "__main__":
    unittest.main()
