"""Falsifier aging (I-3): a hypothesis claim's or an incident's own
`refuted_by` command is a theory's one exit - the observation that would
kill it. Left unrun, it never gets the chance, and the theory just sits.
`due_falsifiers` names every claim (grade hypothesis) or incident whose
falsifier is old (default: two days) with no attestation citing that
command since it was recorded; `falsifier_stale_findings` folds that into
one preflight judgment finding; `verify --falsifiers` runs the due ones.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_attest import (  # noqa: E402
    open_session, record_claim, resolve_claim, run_check,
)
from godmode_runtime.godmode_console import (  # noqa: E402
    Runtime, cmd_remember, cmd_verify,
)
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_falsifiers import (  # noqa: E402
    due_falsifiers, falsifier_stale_findings,
)
from godmode_runtime.godmode_mistakes import record_incident  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

_RUNNABLE = f'"{sys.executable}" -c "pass"'
_THREE_DAYS = timedelta(days=3)


def _remember_args(**over):
    base = dict(kind="incident", subject=None, value=None, text=None,
                status=None, evidence=[], guard=None, intent_preserved=None,
                failure_class=None, turning_point=False, predicts=None,
                refuted_by=None, session=None,
                # NS-13e: an incident written through the verb carries a
                # reproduction or the stated reason it has none.
                repro=None, no_repro="fixture: no reproduction command")
    base.update(over)
    return argparse.Namespace(**base)


class DueFalsifiersTests(unittest.TestCase):
    def test_nothing_recorded_is_nothing_due(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(due_falsifiers(archive), [])

    def test_a_fresh_hypothesis_is_not_yet_due(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_claim(archive, project, "S", "the cache drops the second write",
                        "hypothesis", refuted_by=_RUNNABLE)
            self.assertEqual(due_falsifiers(archive, now=datetime.now(timezone.utc)), [])

    def test_a_three_day_old_hypothesis_is_due(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_claim(archive, project, "S", "the cache drops the second write",
                                  "hypothesis", refuted_by=_RUNNABLE)
            later = datetime.now(timezone.utc) + _THREE_DAYS
            due = due_falsifiers(archive, now=later)
            self.assertEqual(len(due), 1, due)
            row = due[0]
            self.assertEqual(row["kind"], "claim")
            self.assertEqual(row["sequence"], record["sequence"])
            self.assertEqual(row["refuted_by"], _RUNNABLE)
            self.assertGreaterEqual(row["age_days"], 3)
            self.assertTrue(row["citation"].startswith("cmd:"))

    def test_an_observed_claim_with_refuted_by_is_not_a_falsifier_target(self) -> None:
        # `refuted_by` on anything but a hypothesis is stored, but only a
        # hypothesis ages into a finding - an observed/verified claim
        # already stands on its own citations.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_claim(archive, project, "S", "the parser drops trailing commas",
                        "observed", cites=["cmd:true"], refuted_by=_RUNNABLE)
            later = datetime.now(timezone.utc) + _THREE_DAYS
            self.assertEqual(due_falsifiers(archive, now=later), [])

    def test_an_incident_carries_refuted_by_and_ages(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_incident(archive, "export broke", "boom",
                                     refuted_by=_RUNNABLE)
            self.assertEqual(record["data"]["refuted_by"], _RUNNABLE)
            later = datetime.now(timezone.utc) + _THREE_DAYS
            due = due_falsifiers(archive, now=later)
            self.assertEqual(len(due), 1, due)
            self.assertEqual(due[0]["kind"], "incident")
            self.assertEqual(due[0]["sequence"], record["sequence"])

    def test_a_classless_incident_with_no_refuted_by_is_not_due(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_incident(archive, "export broke", "boom")
            later = datetime.now(timezone.utc) + _THREE_DAYS
            self.assertEqual(due_falsifiers(archive, now=later), [])

    def test_running_the_falsifier_clears_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_incident(archive, "export broke", "boom", refuted_by=_RUNNABLE)
            session = open_session(archive, "test")
            later = datetime.now(timezone.utc) + _THREE_DAYS
            self.assertEqual(len(due_falsifiers(archive, now=later)), 1)
            run_check(archive, session, project, "manual-run",
                     [sys.executable, "-c", "pass"])
            self.assertEqual(due_falsifiers(archive, now=later), [])

    def test_a_run_from_before_the_record_does_not_clear_it(self) -> None:
        # "Never run" means never run AFTER this record - an attestation
        # naming the same command from before the incident existed proves
        # an earlier state, not this one.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "test")
            run_check(archive, session, project, "earlier-run",
                     [sys.executable, "-c", "pass"])
            record_incident(archive, "export broke", "boom", refuted_by=_RUNNABLE)
            later = datetime.now(timezone.utc) + _THREE_DAYS
            due = due_falsifiers(archive, now=later)
            self.assertEqual(len(due), 1, due)

    def test_a_claim_resolved_held_is_not_due(self) -> None:
        # A resolution answers the question the falsifier stood in for -
        # whatever the outcome, the claim is closed, not standing on
        # nothing.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            claim = record_claim(archive, project, "S", "the cache drops the second write",
                                 "hypothesis", refuted_by=_RUNNABLE)
            resolve_claim(archive, project, "S", claim["sequence"], "held",
                          cites=["file:README.md"])
            later = datetime.now(timezone.utc) + _THREE_DAYS
            self.assertEqual(due_falsifiers(archive, now=later), [])

    def test_a_claim_resolved_superseded_is_not_due(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            claim = record_claim(archive, project, "S", "the cache drops the second write",
                                 "hypothesis", refuted_by=_RUNNABLE)
            resolve_claim(archive, project, "S", claim["sequence"], "superseded",
                          cites=["file:README.md"])
            later = datetime.now(timezone.utc) + _THREE_DAYS
            self.assertEqual(due_falsifiers(archive, now=later), [])

    def test_an_unresolved_hypothesis_stays_due(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "README.md").write_text("x", encoding="utf-8")
            record_claim(archive, project, "S", "the cache drops the second write",
                        "hypothesis", refuted_by=_RUNNABLE)
            # An unrelated resolution elsewhere in the ledger must not
            # blank out a claim it does not name.
            other = record_claim(archive, project, "S", "the queue drains in order",
                                 "hypothesis", refuted_by=_RUNNABLE)
            resolve_claim(archive, project, "S", other["sequence"], "held",
                          cites=["file:README.md"])
            later = datetime.now(timezone.utc) + _THREE_DAYS
            due = due_falsifiers(archive, now=later)
            self.assertEqual(len(due), 1, due)

    def test_a_due_falsifier_past_the_old_500_record_cap_is_still_found(self) -> None:
        """Task 5 residue (final review, wave item 4): `due_falsifiers`
        used to read claims/incidents/attestations through
        `archive.select(kind=..., limit=500)`, which keeps only the 500
        MOST RECENT records of that kind - an old-enough-to-be-due
        incident is exactly what such a cap ages out first once enough
        later, unrelated incidents pile up behind it. Now reads unbounded
        off `read_events()`."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_incident(archive, "export broke", "boom",
                                     refuted_by=_RUNNABLE)
            for i in range(510):
                record_incident(archive, f"unrelated noise {i}", "padding")
            later = datetime.now(timezone.utc) + _THREE_DAYS
            due = due_falsifiers(archive, now=later)
            sequences = [row["sequence"] for row in due]
            self.assertIn(record["sequence"], sequences, due)


class FalsifierStaleFindingTests(unittest.TestCase):
    def test_nothing_due_is_no_finding(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(falsifier_stale_findings(archive), [])

    def test_a_due_falsifier_is_one_aggregated_finding(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_incident(archive, "export broke", "boom", refuted_by=_RUNNABLE)
            later = datetime.now(timezone.utc) + _THREE_DAYS
            findings = falsifier_stale_findings(archive, now=later)
            self.assertEqual(len(findings), 1, findings)
            finding = findings[0]
            self.assertEqual(finding["check"], "falsifier-stale")
            self.assertEqual(finding["class"], "invented-information")
            self.assertIn("export broke".split()[0], finding["detail"])

    def test_class_is_on_the_closed_table(self) -> None:
        from godmode_runtime.godmode_mistakes import FAILURE_CLASSES
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_incident(archive, "export broke", "boom", refuted_by=_RUNNABLE)
            later = datetime.now(timezone.utc) + _THREE_DAYS
            finding = falsifier_stale_findings(archive, now=later)[0]
            self.assertIn(finding["class"], FAILURE_CLASSES)


class RememberRefutedByTests(unittest.TestCase):
    def test_kind_incident_accepts_refuted_by(self) -> None:
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            runtime = Runtime(anchor=anchor, archive=archive)
            args = _remember_args(subject="cache maybe drops second write",
                                  value="observed twice in staging",
                                  refuted_by=_RUNNABLE)
            result = cmd_remember(args, runtime)
            self.assertEqual(result.payload["record"]["data"]["refuted_by"], _RUNNABLE)

    def test_the_flag_is_on_the_parser(self) -> None:
        from godmode_runtime.godmode_console import _build_parser
        parser = _build_parser()
        args = parser.parse_args([
            "remember", "--kind", "incident", "--subject", "s",
            "--value", "v", "--refuted-by", _RUNNABLE,
        ])
        self.assertEqual(args.refuted_by, _RUNNABLE)


class VerifyFalsifiersCLITests(unittest.TestCase):
    def _runtime(self, project, archive):
        from godmode_runtime.godmode_anchor import resolve_anchor
        return Runtime(anchor=resolve_anchor(project), archive=archive)

    def test_bare_verify_without_command_or_falsifiers_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "test")
            runtime = self._runtime(project, archive)
            args = argparse.Namespace(name="x", command=None, rule=[], session=None,
                                      timeout=900, offline=False, falsifiers=False,
                                      dry_run=False)
            with self.assertRaises(ArchiveError):
                cmd_verify(args, runtime)

    def test_dry_run_lists_due_without_attesting(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "test")
            runtime = self._runtime(project, archive)
            fake_due = [{"kind": "incident", "sequence": 1, "subject": "x",
                        "refuted_by": _RUNNABLE, "age_days": 5, "citation": "cmd:x"}]
            before = len(archive.select(kind="attestation", limit=50))
            with mock.patch("godmode_runtime.godmode_falsifiers.due_falsifiers",
                            return_value=fake_due):
                args = argparse.Namespace(name=None, command=None, rule=[], session=None,
                                          timeout=900, offline=False, falsifiers=True,
                                          dry_run=True)
                result = cmd_verify(args, runtime)
            self.assertEqual(result.payload["due"], fake_due)
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(len(archive.select(kind="attestation", limit=50)), before)

    def test_falsifiers_mode_runs_and_attests_each_due_one(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_session(archive, "test")
            runtime = self._runtime(project, archive)
            fake_due = [{"kind": "incident", "sequence": 1, "subject": "x",
                        "refuted_by": _RUNNABLE, "age_days": 5, "citation": "cmd:x"}]
            with mock.patch("godmode_runtime.godmode_falsifiers.due_falsifiers",
                            return_value=fake_due):
                args = argparse.Namespace(name=None, command=None, rule=[], session=None,
                                          timeout=900, offline=False, falsifiers=True,
                                          dry_run=False)
                result = cmd_verify(args, runtime)
            self.assertEqual(result.payload["count"], 1)
            self.assertTrue(result.payload["ran"][0]["passed"])
            attestations = archive.select(kind="attestation", limit=50)
            self.assertTrue(any(a["subject"].startswith("check:falsifier:incident-1")
                                for a in attestations))

    def test_the_verb_exposes_the_flags(self) -> None:
        import subprocess
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / "godmode.py"), "verify", "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertIn("--falsifiers", done.stdout)
        self.assertIn("--dry-run", done.stdout)


class PreflightWiringTests(unittest.TestCase):
    def test_a_due_falsifier_surfaces_as_a_judgment_finding(self) -> None:
        import subprocess
        import tempfile
        from godmode_runtime.godmode_preflight import push_preflight

        finding = {"check": "falsifier-stale", "class": "invented-information",
                  "detail": "1 falsifier(s) aged past 2d"}
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, capture_output=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                            "commit", "--allow-empty", "-qm", "seed"],
                           cwd=repo, capture_output=True)
            from godmode_runtime.godmode_anchor import resolve_anchor
            from godmode_runtime.godmode_chronicle import Chronicle
            with mock.patch.dict("os.environ",
                                 {"GODMODE_STATE_HOME": str(Path(tmp) / "state")},
                                 clear=False):
                archive = Chronicle(resolve_anchor(repo))
                archive.initialize()
                with mock.patch("godmode_runtime.godmode_falsifiers.falsifier_stale_findings",
                                return_value=[finding]):
                    report = push_preflight(repo, archive=archive)
            checks = [j.get("check") for j in report["judgment"]]
            self.assertIn("falsifier-stale", checks)
            self.assertEqual(report["verdict"], "findings")


if __name__ == "__main__":
    unittest.main()
