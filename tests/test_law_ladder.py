"""Sprint L3: the promotion ladder, promotable flags, dormancy.

Adopted from loop-engineering's reliability discipline: nothing escalates
on one observation. A correction cluster is PROMOTABLE only after it recurs
in three distinct sessions; promotion itself always writes a reviewed guard
(`law promote`), because a candidate carries keywords, never prose worth
enshrining verbatim. A law nothing has delivered recently is flagged
dormant rather than silently carried forever.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS, Path(__file__).parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from _law_fixtures import operator_lesson  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    PROMOTION_SESSIONS, law_candidates, promote_candidate,
    record_correction_candidate, record_delivery, top_laws,
)
from godmode_runtime.godmode_lessons import approve  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-ladder-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


def _recur(archive, sessions):
    for session in sessions:
        record_correction_candidate(
            archive, "wrong again - you missed the registry check",
            session=session)


class PromotableTests(unittest.TestCase):
    def test_a_cluster_below_the_session_bar_is_not_promotable(self) -> None:
        with _project() as (_root, archive):
            _recur(archive, ["S-1", "S-2"])
            cluster = law_candidates(archive)[0]
        self.assertFalse(cluster["promotable"])

    def test_three_distinct_sessions_make_a_cluster_promotable(self) -> None:
        with _project() as (_root, archive):
            _recur(archive, ["S-1", "S-2", "S-3"])
            cluster = law_candidates(archive)[0]
        self.assertTrue(cluster["promotable"])
        self.assertEqual(cluster["distinct_sessions"], PROMOTION_SESSIONS)


class PromoteTests(unittest.TestCase):
    def test_promotion_writes_a_candidate_lesson_and_a_chained_promotion(self) -> None:
        # 0.3.28 Plan 5 Task 2: the ladder no longer writes an active law
        # directly - it writes a CANDIDATE lesson (citing the cluster) plus
        # a `lesson_promotion` naming this same actor; neither alone
        # compiles.
        with _project() as (_root, archive):
            _recur(archive, ["S-1", "S-2", "S-3"])
            cluster = law_candidates(archive)[0]
            record = promote_candidate(
                archive, cluster["first_seq"],
                guard="verify against the registry before ranking",
                subject="registry-check-before-ranking")
            laws = top_laws(archive, 3)
        self.assertEqual(record["data"]["generalized_guard"],
                         "verify against the registry before ranking")
        self.assertEqual(record["data"]["status"], "candidate")
        self.assertIn(f"seq:{cluster['first_seq']}", str(record["evidence"]))
        self.assertIn("promotion", record)
        self.assertEqual(record["promotion"]["lesson_seq"], record["sequence"])
        self.assertFalse(
            any(law["subject"] == "registry-check-before-ranking" for law in laws))

    def test_promotion_graduates_to_a_law_only_after_a_chained_approval(self) -> None:
        with _project() as (_root, archive):
            _recur(archive, ["S-1", "S-2", "S-3"])
            cluster = law_candidates(archive)[0]
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "ladder-agent"}):
                record = promote_candidate(
                    archive, cluster["first_seq"],
                    guard="verify against the registry before ranking",
                    subject="registry-check-before-ranking")
            promotion_seq = record["promotion"]["sequence"]
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                approve(archive, promotion_seq,
                       rerun_hash=hashlib.sha256(b"an-independent-rerun").hexdigest())
            laws = top_laws(archive, 3)
        self.assertEqual(laws[0]["subject"], "registry-check-before-ranking")
        self.assertEqual(laws[0]["guard"], "verify against the registry before ranking")

    def test_promotion_below_the_bar_is_refused(self) -> None:
        with _project() as (_root, archive):
            _recur(archive, ["S-1"])
            cluster = law_candidates(archive)[0]
            with self.assertRaises(ArchiveError):
                promote_candidate(archive, cluster["first_seq"],
                                  guard="g", subject="too-early")

    def test_promotion_of_an_unknown_candidate_is_refused(self) -> None:
        with _project() as (_root, archive):
            with self.assertRaises(ArchiveError):
                promote_candidate(archive, 99999, guard="g", subject="ghost")


class DormancyTests(unittest.TestCase):
    def test_a_law_recently_delivered_is_not_dormant(self) -> None:
        with _project() as (_root, archive):
            # NS-2 fix round 1 (B1): dormancy is about DELIVERY, not
            # admission - the operator carve-out is the one-write way to
            # get a standing law for it to measure.
            operator_lesson(archive, "fresh-law", "guard", value="v")
            laws = top_laws(archive, 3)
            record_delivery(archive, laws, session="S-1")
            refreshed = top_laws(archive, 3)
        self.assertFalse(refreshed[0]["dormant"])

    def test_a_law_never_delivered_is_flagged_dormant(self) -> None:
        with _project() as (_root, archive):
            operator_lesson(archive, "sleeping-law", "guard", value="v")
            laws = top_laws(archive, 3)
        self.assertTrue(laws[0]["dormant"])


if __name__ == "__main__":
    unittest.main()
