"""Field report file 2026-09-10, Part 4: a check that cannot fail earns no
verified grade; a claim carries the hash of the files its text names; a
quoted sentence is not a claim; a latency task lists its measurement
environment; the project's own debt counters are recorded and a rise is
named; the observe advisory on process control names the restore
obligation."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


class FalsifiableCheckTests(unittest.TestCase):
    def test_a_state_report_cannot_earn_verified(self) -> None:
        from godmode_runtime.godmode_attest import falsifiable, record_claim, run_check

        self.assertFalse(falsifiable("cmd:git status --short"))
        self.assertFalse(falsifiable("cmd:echo done"))
        self.assertTrue(falsifiable("cmd:npx vitest run tests/x.test.ts"))
        self.assertTrue(falsifiable("cmd:python scan.py"))
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            run_check(archive, "s1", project, "claim-verify-1", ["git", "status", "--short"])
            record = record_claim(archive, project, "s1", "nothing was implemented this turn", "verified",
                                  cites=["cmd:git status --short"])
            self.assertNotEqual(record["data"]["grade"], "verified", record["data"])


class SubjectFileTests(unittest.TestCase):
    def test_a_claim_about_a_file_goes_stale_when_that_file_changes(self) -> None:
        from godmode_runtime.godmode_attest import record_claim, stale_claims, subject_files

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "app").mkdir()
            (project / "app" / "admin.tsx").write_text("export const a = 1;\n", encoding="utf-8")
            self.assertEqual(subject_files(project, "costs x2 -> x1 in app/admin.tsx after the fix"), ["app/admin.tsx"])
            record_claim(archive, project, "s1", "admin costs x2 -> x1 in app/admin.tsx", "observed",
                         cites=["doc:notes.md"])
            self.assertEqual(stale_claims(archive, project), [])
            (project / "app" / "admin.tsx").write_text("export const a = 2;\n", encoding="utf-8")
            stale = stale_claims(archive, project)
            self.assertEqual(len(stale), 1, stale)
            self.assertEqual(stale[0]["citation"], "file:app/admin.tsx")
            self.assertEqual(stale[0]["reason"], "changed")


class QuotedSentenceTests(unittest.TestCase):
    def test_a_quotation_of_the_operator_is_not_a_claim(self) -> None:
        self.assertIsNotNone(hook._QUOTED_SENTENCE.search('The owner asked for "everything strictly 100% perfect" today.'))
        self.assertIsNone(hook._QUOTED_SENTENCE.search('The suite is "green" now.'))


class MeasurementEnvironmentTests(unittest.TestCase):
    def test_a_latency_task_lists_the_measurement_environment(self) -> None:
        from godmode_runtime.godmode_precheck import missing_surface

        surfaces = {m["surface"] for m in missing_surface("studio latency: duplicate /api/me requests")}
        self.assertIn("measurement environment", surfaces)
        self.assertNotIn("measurement environment", {m["surface"] for m in missing_surface("rename a helper")})


class RatchetTests(unittest.TestCase):
    def test_a_rise_between_two_runs_is_named_by_integrity(self) -> None:
        from godmode_runtime.godmode_ratchet import declared_ratchets, ratchet_findings, run_ratchets

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            counter = project / "count.txt"
            counter.write_text("3", encoding="utf-8")
            (project / ".godmode-ratchets.json").write_text(json.dumps({
                "lint-debt": f"\"{sys.executable}\" -c \"import pathlib; print(pathlib.Path('count.txt').read_text())\""}),
                encoding="utf-8")
            self.assertEqual(list(declared_ratchets(project)), ["lint-debt"])
            first = run_ratchets(archive, project)
            self.assertTrue(first["ok"], first)
            self.assertEqual(first["rows"][0]["value"], 3)
            counter.write_text("5", encoding="utf-8")
            second = run_ratchets(archive, project)
            self.assertFalse(second["ok"])
            self.assertEqual(second["rose"], ["lint-debt"])
            findings = ratchet_findings(archive)
            self.assertEqual(len(findings), 1)
            self.assertIn("rose from 3 to 5", findings[0]["detail"])
            counter.write_text("4", encoding="utf-8")
            self.assertTrue(run_ratchets(archive, project)["ok"])
            self.assertEqual(ratchet_findings(archive), [])


if __name__ == "__main__":
    unittest.main()
