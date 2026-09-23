"""NS-13a + NS-13b: a 5-Whys record validates its chain backwards, names three
countermeasures, and cannot end at a person or "human error".

Each fixture below is incomplete in exactly one way, and the gap it must
produce is named; the whole record is the control that proves the contract
is satisfiable at all.
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

from godmode_runtime.godmode_method import CONTRACTS, FIVE_WHYS, complete  # noqa: E402

WHOLE = {
    "symptom": "the export job writes an empty file",
    "links": [
        {"why": "the query returns no rows", "evidence": "cmd:python export.py --dry"},
        {"why": "the date filter is exclusive at both ends", "evidence": "src/export.py#L40-L44"},
    ],
    "root": "the date-range helper has no inclusive-bound contract or test",
    "validation": [
        {"text": "if the helper had an inclusive-bound test, the filter would not be exclusive",
         "evidence": "tests/test_dates.py#L10-L20"},
        {"text": "if the filter were inclusive, the query would return the day's rows",
         "evidence": "cmd:python export.py --dry"},
    ],
    "countermeasures": {
        "immediate": {"text": "re-run the export for the missed day", "evidence": "seq:41"},
        "preventive": {"text": "make the helper's bounds explicit", "evidence": "src/dates.py#L5-L9"},
        "detection": {"text": "an inclusive-bound unit test in the dates suite",
                      "evidence": "cmd:python -m unittest tests.test_dates"},
    },
}


def _record(**changes):
    record = copy.deepcopy(WHOLE)
    for key, value in changes.items():
        if value is None:
            record.pop(key, None)
        else:
            record[key] = value
    return record


class ContractShapeTests(unittest.TestCase):
    def test_the_contract_names_validation_and_countermeasures(self) -> None:
        self.assertIn("validation", CONTRACTS[FIVE_WHYS])
        self.assertIn("countermeasures", CONTRACTS[FIVE_WHYS])

    def test_a_whole_record_is_complete(self) -> None:
        verdict = complete(FIVE_WHYS, _record())
        self.assertTrue(verdict["complete"], verdict)


class ChainValidationTests(unittest.TestCase):
    def test_an_unvalidated_chain_is_named(self) -> None:
        verdict = complete(FIVE_WHYS, _record(validation=None))
        self.assertFalse(verdict["complete"])
        self.assertIn("chain_not_validated", verdict["gaps"])
        # One gap per fault: the specific gap, not a generic missing: beside it.
        self.assertNotIn("missing:validation", verdict["gaps"])

    def test_an_uncited_backward_step_is_not_validation(self) -> None:
        steps = copy.deepcopy(WHOLE["validation"])
        steps[1]["evidence"] = ""
        self.assertIn("chain_not_validated", complete(FIVE_WHYS, _record(validation=steps))["gaps"])

    def test_a_validation_shorter_than_the_chain_is_not_validation(self) -> None:
        steps = copy.deepcopy(WHOLE["validation"])[:1]
        self.assertIn("chain_not_validated", complete(FIVE_WHYS, _record(validation=steps))["gaps"])

    def test_branches_each_validate_their_own_chain(self) -> None:
        good = {"cause": "helper", "links": WHOLE["links"], "root": WHOLE["root"],
                "validation": WHOLE["validation"]}
        bad = {"cause": "scheduler", "links": [{"why": "ran at midnight", "evidence": "log:cron"}],
               "root": "the scheduler has no timezone declared"}
        record = _record(links=None, root=None, validation=None, branches=[good, bad])
        verdict = complete(FIVE_WHYS, record)
        self.assertIn("chain_not_validated:branch2", verdict["gaps"])
        self.assertNotIn("chain_not_validated:branch1", verdict["gaps"])
        bad["validation"] = [{"text": "with a declared timezone it would not run at midnight",
                              "evidence": "cmd:python -m unittest tests.test_cron"}]
        self.assertTrue(complete(FIVE_WHYS, record)["complete"],
                        complete(FIVE_WHYS, record))


class CountermeasureTests(unittest.TestCase):
    def test_no_detection_countermeasure_is_named(self) -> None:
        measures = copy.deepcopy(WHOLE["countermeasures"])
        del measures["detection"]
        verdict = complete(FIVE_WHYS, _record(countermeasures=measures))
        self.assertIn("countermeasures_missing:detection", verdict["gaps"])
        self.assertNotIn("countermeasures_missing:immediate", verdict["gaps"])

    def test_each_countermeasure_is_named_when_absent(self) -> None:
        verdict = complete(FIVE_WHYS, _record(countermeasures=None))
        for name in ("immediate", "preventive", "detection"):
            self.assertIn(f"countermeasures_missing:{name}", verdict["gaps"])

    def test_an_uncited_countermeasure_is_missing(self) -> None:
        measures = copy.deepcopy(WHOLE["countermeasures"])
        measures["preventive"]["evidence"] = ""
        self.assertIn("countermeasures_missing:preventive",
                      complete(FIVE_WHYS, _record(countermeasures=measures))["gaps"])

    def test_detection_must_name_a_check(self) -> None:
        measures = copy.deepcopy(WHOLE["countermeasures"])
        measures["detection"] = {"text": "be more careful next time", "evidence": "seq:41"}
        self.assertIn("detection_names_no_check",
                      complete(FIVE_WHYS, _record(countermeasures=measures))["gaps"])

    def test_a_checklist_item_or_guarding_prose_is_not_a_check(self) -> None:
        for text in ("add a checklist item for exports", "guard against empty files"):
            measures = copy.deepcopy(WHOLE["countermeasures"])
            measures["detection"] = {"text": text, "evidence": "seq:41"}
            self.assertIn("detection_names_no_check",
                          complete(FIVE_WHYS, _record(countermeasures=measures))["gaps"], text)


class BlameGuardTests(unittest.TestCase):
    def test_developer_forgot_is_blame(self) -> None:
        verdict = complete(FIVE_WHYS, _record(root="developer forgot to update the filter"))
        self.assertIn("root_is_blame", verdict["gaps"])

    def test_human_error_and_the_last_deploy_are_blame(self) -> None:
        for root in ("human error", "the last deploy", "someone changed the config"):
            self.assertIn("root_is_blame", complete(FIVE_WHYS, _record(root=root))["gaps"], root)

    def test_a_named_writer_is_blame(self) -> None:
        verdict = complete(FIVE_WHYS, _record(root="Priya's refactor", author="Priya"))
        self.assertIn("root_is_blame", verdict["gaps"])

    def test_a_design_cause_is_not_blame(self) -> None:
        verdict = complete(FIVE_WHYS, _record(root="the release checklist has no export step"))
        self.assertNotIn("root_is_blame", verdict["gaps"])


class CheckRecordVerbTests(unittest.TestCase):
    """`method --check-record` reports the new gaps and exits non-zero."""

    def test_the_verb_reports_the_gaps(self) -> None:
        from godmode_runtime import godmode_console as console
        from test_godmode_runtime import isolated_project

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with tempfile.TemporaryDirectory() as scratch:
                path = Path(scratch) / "rca.json"
                path.write_text(json.dumps(_record(root="human error", validation=None)),
                                encoding="utf-8")
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out), \
                        mock.patch.object(sys, "stderr", io.StringIO()):
                    code = console.main(["--project", str(project), "method",
                                         "--check-method", "5-whys",
                                         "--check-record", str(path)])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 1, payload)
        self.assertIn("chain_not_validated", payload["gaps"])
        self.assertIn("root_is_blame", payload["gaps"])


if __name__ == "__main__":
    unittest.main()
