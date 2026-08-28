"""Sprint L2 of the Code of Law loop: detectors, receipts, guard-run grading.

Three mechanisms, each answering a field report from 2026-08-28:
- `record_correction_candidate`: the operator-correction detector. A
  correction-shaped prompt writes a law CANDIDATE (a lesson with
  status "candidate") carrying keywords and a digest, never the sentence.
  `law candidates` clusters them read-time by keyword identity so the
  promotion ladder counts recurrence across sessions instead of splitting
  its own counter on duplicates.
- delivery receipts: the brief's law block writes a counts-only action
  record naming which laws were delivered - the denominator without which
  "violated 0" is unfalsifiable.
- guard-run grading (obligation 4122): a verified claim whose evidence is
  a test file it READ needs the run - `cmd:` beside the `file:` - or it
  grades hypothesis with a reason naming the missing run.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS,):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import open_session, record_claim  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    law_candidates, record_correction_candidate, record_delivery, top_laws,
)


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-lawloop-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


class CorrectionDetectorTests(unittest.TestCase):
    def test_a_correction_shaped_prompt_writes_a_candidate_without_its_text(self) -> None:
        with _project() as (_root, archive):
            record = record_correction_candidate(
                archive, "no, that's wrong - you missed the registry check again",
                session="S-1")
            self.assertIsNotNone(record)
            data = record["data"]
        self.assertEqual(data["status"], "candidate")
        self.assertIn("registry", data["keywords"])
        self.assertNotIn("you missed the registry check", record["subject"])
        self.assertTrue(record["subject"].startswith("correction:"))

    def test_an_ordinary_prompt_writes_nothing(self) -> None:
        with _project() as (_root, archive):
            self.assertIsNone(record_correction_candidate(
                archive, "please add a button to the settings page", session="S-1"))

    def test_candidates_cluster_by_keywords_and_count_distinct_sessions(self) -> None:
        with _project() as (_root, archive):
            for session in ("S-1", "S-2", "S-2", "S-3"):
                record_correction_candidate(
                    archive, "wrong again - you missed the registry check",
                    session=session)
            clusters = law_candidates(archive)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["occurrences"], 4)
        self.assertEqual(clusters[0]["distinct_sessions"], 3)

    def test_candidates_never_become_laws_without_a_guard(self) -> None:
        from godmode_runtime.godmode_law import compile_laws

        with _project() as (root, archive):
            record_correction_candidate(
                archive, "no - wrong file again", session="S-1")
            report = compile_laws(archive, root)
        self.assertEqual(report["laws"], 0)
        self.assertNotIn("wrong file", top_laws(archive, 5).__repr__())


class DeliveryReceiptTests(unittest.TestCase):
    def test_delivery_writes_a_counts_only_action(self) -> None:
        with _project() as (_root, archive):
            archive.append("lesson", "probe-reach",
                           {"status": "active", "value": "v",
                            "generalized_guard": "read the counters"}, evidence=[])
            laws = top_laws(archive, 3)
            record = record_delivery(archive, laws, session="S-1")
            self.assertEqual(record["data"]["delivered"], 1)
            self.assertEqual(record["data"]["law_seqs"], [laws[0]["seq"]])
            self.assertNotIn("read the counters", str(record["data"]))

    def test_delivery_of_nothing_writes_nothing(self) -> None:
        with _project() as (_root, archive):
            self.assertIsNone(record_delivery(archive, [], session="S-1"))


class GuardRunGradingTests(unittest.TestCase):
    def test_a_test_file_citation_without_its_run_downgrades(self) -> None:
        with _project() as (root, archive):
            (root / "tests").mkdir()
            (root / "tests" / "test_guard.py").write_text("def test(): pass\n",
                                                          encoding="utf-8")
            session = open_session(archive, "work")
            record = record_claim(
                archive, root, session,
                "the invariant is protected by the guard", "verified",
                cites=["file:tests/test_guard.py"])
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("run", record["data"]["reason"])

    def test_the_same_citation_with_its_run_stays_verified(self) -> None:
        with _project() as (root, archive):
            (root / "tests").mkdir()
            (root / "tests" / "test_guard.py").write_text("def test(): pass\n",
                                                          encoding="utf-8")
            session = open_session(archive, "work")
            # The run is attested in this session - which is the whole
            # point: the cmd: citation resolves through the attestation of
            # the run, not through the sentence claiming it.
            archive.append("attestation", "ran the guard",
                           {"session": session, "status": "ok", "result": "exit 0"},
                           evidence=["cmd:python -m unittest tests.test_guard"])
            record = record_claim(
                archive, root, session,
                "the invariant is protected by the guard", "verified",
                cites=["file:tests/test_guard.py",
                       "cmd:python -m unittest tests.test_guard"])
        self.assertEqual(record["data"]["grade"], "verified")

    def test_a_non_test_file_citation_is_untouched_by_the_rule(self) -> None:
        with _project() as (root, archive):
            (root / "lib.py").write_text("x = 1\n", encoding="utf-8")
            session = open_session(archive, "work")
            record = record_claim(
                archive, root, session, "the constant is defined", "verified",
                cites=["file:lib.py"])
        self.assertEqual(record["data"]["grade"], "verified")


if __name__ == "__main__":
    unittest.main()
