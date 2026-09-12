"""An assumption doing all the work says what fails without it.

The product already forces falsifiability after the fact: an incident's
hypothesis is not evidence until it forbids something, and a mechanism that
only explains is refused. Nothing forced it before the work started. A plan can
rest entirely on one unexamined premise and every record about it will look
locally justified.

So an assumption may be marked load-bearing, and marking it requires naming
what fails in its absence. That is the same contract `--turning-point` already
holds for an incident: both are causal claims, and a causal claim with no
citation is an assertion wearing a record's clothes.

Deliberately the same mechanism rather than a second one. A parallel
convention would drift from the first, which is the duplicate-authority
failure this codebase has already been bitten by twice.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_mistakes import validate_load_bearing  # noqa: E402


class MarkingItRequiresNamingTheConsequence(unittest.TestCase):
    def test_load_bearing_without_evidence_is_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            validate_load_bearing(True, [])

    def test_load_bearing_with_no_evidence_argument_at_all_is_refused(self) -> None:
        with self.assertRaises(ArchiveError):
            validate_load_bearing(True, None)

    def test_load_bearing_with_evidence_is_accepted(self) -> None:
        validate_load_bearing(True, ["without it the release has no CI gate at all"])

    def test_an_ordinary_assumption_needs_nothing(self) -> None:
        """Only the causal claim carries the burden."""
        validate_load_bearing(False, None)


class TheRefusalSaysWhatToSupply(unittest.TestCase):
    def test_the_message_names_the_missing_argument(self) -> None:
        with self.assertRaises(ArchiveError) as caught:
            validate_load_bearing(True, [])
        message = str(caught.exception)
        self.assertIn("--evidence", message)

    def test_the_message_says_what_the_evidence_should_state(self) -> None:
        """"Requires evidence" alone does not tell the author what to write."""
        with self.assertRaises(ArchiveError) as caught:
            validate_load_bearing(True, [])
        self.assertIn("without it", str(caught.exception).lower())


class ItMirrorsTheIncidentContract(unittest.TestCase):
    def test_blank_evidence_does_not_satisfy_it(self) -> None:
        """A citation of whitespace is not a citation."""
        with self.assertRaises(ArchiveError):
            validate_load_bearing(True, ["   "])

    def test_the_turning_point_contract_still_behaves_the_same_way(self) -> None:
        """The control: this did not change the mechanism it copies."""
        from godmode_runtime.godmode_mistakes import record_incident

        class Archive:
            def append(self, *a, **k):
                return {"sequence": 1, "kind": "incident"}

            def select(self, *a, **k):
                return []

        with self.assertRaises(ArchiveError):
            record_incident(Archive(), "s", "v", turning_point=True, cites=[])


if __name__ == "__main__":
    unittest.main()
