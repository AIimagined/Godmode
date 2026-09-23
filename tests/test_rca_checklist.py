"""NS-13g: the RCA ritual is a checklist template, and `method --check-record`
reads it - a record that skips a step is incomplete, and names the step.
"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_checklist import RCA_STEPS, TEMPLATES, rca_gaps  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from test_method_contracts import WHOLE  # noqa: E402

RCA = {
    "what": {"expected": "a file with the day's rows", "actual": "an empty file",
             "evidence": ["repro:python export.py --dry", "expected:the day's rows",
                          "actual:an empty file"]},
    "when": {"evidence": ["cmd:git bisect run python export.py --dry"]},
    "where": {"evidence": ["file:src/dates.py#L5-L9"]},
    "why": {"evidence": ["file:docs/rca-export.json"]},
    "fix-root": {"evidence": ["file:src/dates.py#L5-L9"]},
    "lock": {"evidence": ["cmd:python -m unittest tests.test_dates"]},
}


def _run(project, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = console.main(["--project", str(project), *argv])
    return code, json.loads(out.getvalue()), err.getvalue()


def _check(project, record):
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "rca.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return _run(project, "method", "--check-method", "5-whys", "--check-record", str(path))


class TemplateTests(unittest.TestCase):
    def test_the_template_exists_with_six_steps_in_order(self) -> None:
        self.assertIn("rca", TEMPLATES)
        self.assertEqual(RCA_STEPS, ("what", "when", "where", "why", "fix-root", "lock"))

    def test_a_whole_checklist_has_no_gaps(self) -> None:
        self.assertEqual(rca_gaps(RCA, contract_complete=True), [])

    def test_skipping_when_is_incomplete(self) -> None:
        skipped = copy.deepcopy(RCA)
        del skipped["when"]
        self.assertEqual(rca_gaps(skipped, contract_complete=True), ["incomplete:when"])

    def test_when_needs_a_bisect_or_last_green_cite(self) -> None:
        vague = copy.deepcopy(RCA)
        vague["when"] = {"evidence": ["file:notes.md"]}
        self.assertIn("incomplete:when", rca_gaps(vague, contract_complete=True))

    def test_lock_needs_a_test_that_runs(self) -> None:
        # Early review 2, M4: "test" as a substring is not a test.
        for cite in ("file:latest.md", "cmd:echo hi"):
            loose = copy.deepcopy(RCA)
            loose["lock"] = {"evidence": [cite]}
            self.assertIn("incomplete:lock", rca_gaps(loose, contract_complete=True), cite)
        for cite in ("cmd:npm test", "file:tests/test_dates.py#L3", "cmd:pytest -q"):
            tight = copy.deepcopy(RCA)
            tight["lock"] = {"evidence": [cite]}
            self.assertNotIn("incomplete:lock", rca_gaps(tight, contract_complete=True), cite)

    def test_what_needs_expected_and_actual_either_way(self) -> None:
        # Early review 2, M5: the archived path proves as much as the inline one.
        bare = {"evidence": ["repro:python export.py --dry"], "archived": True}
        self.assertIn("incomplete:what", rca_gaps({**RCA, "what": bare}, contract_complete=True))

    def test_an_empty_inline_checklist_is_six_gaps(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, payload, _err = _check(project, {**WHOLE, "rca": {}})
        self.assertEqual(code, 1)
        self.assertEqual([g for g in payload["gaps"] if g.startswith("incomplete:")],
                         [f"incomplete:{step}" for step in RCA_STEPS])

    def test_why_needs_a_complete_method_contract(self) -> None:
        self.assertIn("incomplete:why", rca_gaps(RCA, contract_complete=False))

    def test_the_verb_prints_the_template(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, payload, err = _run(project, "checklist", "template", "rca", "--for", "export")
        self.assertEqual(code, 0, err)
        self.assertEqual([row["item"] for row in payload["items"]],
                         [f"rca:export:{step}" for step in RCA_STEPS])


class CheckRecordReadsTheChecklistTests(unittest.TestCase):
    def test_an_inline_checklist_skipping_when_fails_the_record(self) -> None:
        skipped = copy.deepcopy(RCA)
        del skipped["when"]
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, payload, _err = _check(project, {**WHOLE, "rca": skipped})
        self.assertEqual(code, 1)
        self.assertIn("incomplete:when", payload["gaps"])

    def test_an_inline_whole_checklist_passes(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, payload, _err = _check(project, {**WHOLE, "rca": RCA})
        self.assertEqual(code, 0, payload)

    def test_an_archived_checklist_is_read_by_label(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for step in RCA_STEPS:
                if step == "when":
                    continue
                argv = ["checklist", "update", "--item", f"rca:export:{step}",
                        "--status", "complete"]
                for cite in RCA[step]["evidence"]:
                    argv += ["--evidence", cite]
                code, _p, err = _run(project, *argv)
                self.assertEqual(code, 0, err)
            code, payload, _err = _check(project, {**WHOLE, "rca": "export"})
            self.assertEqual(code, 1)
            self.assertEqual([g for g in payload["gaps"] if g.startswith("incomplete:")],
                             ["incomplete:when"])
            _run(project, "checklist", "update", "--item", "rca:export:when",
                 "--status", "complete", "--evidence", "cmd:git log --oneline -20")
            code, payload, _err = _check(project, {**WHOLE, "rca": "export"})
        self.assertEqual(code, 0, payload)


if __name__ == "__main__":
    unittest.main()
