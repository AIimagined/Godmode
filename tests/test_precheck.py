"""Whether this was already built, and whether it was already refused.

Two questions asked before work starts, because both were answered wrong in
the session that produced this module. A sentinel allowlist was one command
from being rebuilt after two shipped releases had already fixed it, and a
reinvention check designed in an earlier session was rediscovered from scratch
because nothing read the record that it had been designed.

The archive already holds both answers. `removal` records why something was
deleted, decisions record what was rejected, the changelog records what
shipped, and the atlas records what exists. Nothing consults any of them at the
moment a task arrives, which is the only moment the answer is worth having.

It reports where it looked. An absence claim with no search behind it is the
claim this project refuses everywhere else, and `nothing found` from a check
that examined nothing is worse than no check — it reads as clearance.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_precheck import precheck  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class ExistingWorkTests(unittest.TestCase):
    def test_a_symbol_that_already_exists_is_reported(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "fence.py").write_text(
                "def fence_verdict():\n    return True\n", encoding="utf-8")
            report = precheck(project, archive, "add a fence verdict")
        self.assertTrue(any("fence" in hit["where"] for hit in report["already_built"]))

    def test_an_unrelated_request_finds_nothing_built(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "fence.py").write_text(
                "def fence_verdict():\n    return True\n", encoding="utf-8")
            report = precheck(project, archive, "invoice rounding for VAT")
        self.assertEqual(report["already_built"], [])


class PriorRejectionTests(unittest.TestCase):
    def test_a_recorded_rejection_is_surfaced(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "rank-fusion-rejected",
                           {"value": "rank fusion across rankers was rejected as "
                                     "incompatible with local-first retrieval",
                            "status": "decided"})
            report = precheck(project, archive, "add rank fusion to retrieval")
        self.assertTrue(report["already_rejected"])

    def test_a_removal_reason_is_surfaced(self) -> None:
        """`removal` exists to remember why something was deleted. Nothing read
        it, so the reason was preserved and never consulted."""
        from godmode_runtime.godmode_removal import REQUIRED_FIELDS, record_removal

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_removal(archive, "vector embeddings", {
                field: "vector embeddings removed: no network and no daemon"
                for field in REQUIRED_FIELDS})
            report = precheck(project, archive, "bring back vector embeddings")
        self.assertTrue(report["already_rejected"])

    def test_an_unrelated_request_is_not_matched_to_a_rejection(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "rank-fusion-rejected",
                           {"value": "rank fusion rejected", "status": "decided"})
            report = precheck(project, archive, "invoice rounding for VAT")
        self.assertEqual(report["already_rejected"], [])


class SearchDisclosureTests(unittest.TestCase):
    def test_the_report_names_where_it_looked(self) -> None:
        """An absence claim needs the search that would have disproved it.
        `nothing found` from a check that examined nothing reads as clearance,
        which is worse than no check at all."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            report = precheck(project, archive, "anything")
        self.assertIn("searched", report)
        self.assertTrue(report["searched"])

    def test_the_report_says_how_much_it_examined(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "fence.py").write_text("def x():\n    return 1\n", encoding="utf-8")
            report = precheck(project, archive, "anything")
        self.assertGreater(report["symbols_examined"], 0)

    def test_a_clean_precheck_says_proceed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            report = precheck(project, archive, "invoice rounding for VAT")
        self.assertEqual(report["verdict"], "no-prior-work-found")

    def test_a_precheck_with_hits_does_not_say_proceed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "rank-fusion-rejected",
                           {"value": "rank fusion rejected", "status": "decided"})
            report = precheck(project, archive, "add rank fusion")
        self.assertEqual(report["verdict"], "prior-work-found")

    def test_it_never_decides_for_the_reader(self) -> None:
        """Findings, never closures — the contract requests, obligations and
        closure all keep. Prior work is a reason to look, not a refusal."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "rank-fusion-rejected",
                           {"value": "rank fusion rejected", "status": "decided"})
            report = precheck(project, archive, "add rank fusion")
        for hit in report["already_rejected"]:
            self.assertIn("question", hit)


class ClosureReasonTests(unittest.TestCase):
    """Why a thing was closed, kept rather than flattened.

    `closed` currently covers two opposite outcomes. A request closed because
    the thing already existed and a request closed because it was refused leave
    the same record, so the next session reading the archive cannot tell "we
    built this" from "we decided not to" — and the precheck above, which reads
    exactly these records, inherits the ambiguity.
    """

    def test_a_closure_can_say_it_was_already_built(self) -> None:
        from godmode_runtime.godmode_requests import CLOSED_STATUSES, closure_reason

        self.assertIn("already-built", CLOSED_STATUSES)
        self.assertEqual(closure_reason("already-built"), "already-built")

    def test_a_closure_can_say_it_was_refused(self) -> None:
        from godmode_runtime.godmode_requests import CLOSED_STATUSES, closure_reason

        self.assertIn("refused", CLOSED_STATUSES)
        self.assertEqual(closure_reason("refused"), "refused")

    def test_a_plain_closure_still_closes_and_says_it_was_unspecified(self) -> None:
        """Every closure written before this shipped stays a closure. A
        migration that reopened old work would be a worse bug than the
        ambiguity it fixed."""
        from godmode_runtime.godmode_requests import closure_reason

        self.assertEqual(closure_reason("closed"), "unspecified")

    def test_an_open_request_has_no_closure_reason(self) -> None:
        from godmode_runtime.godmode_requests import closure_reason

        self.assertIsNone(closure_reason("open"))

    def test_a_refused_request_still_stops_being_reported(self) -> None:
        from godmode_runtime.godmode_requests import record_request, review_requests

        class Ledger:
            def __init__(self):
                self.records = []

            def read_events(self):
                return self.records

            def append(self, kind, subject, data, evidence):
                record = {"kind": kind, "subject": subject, "data": data,
                          "sequence": len(self.records) + 1, "evidence": evidence}
                self.records.append(record)
                return record

        ledger = Ledger()
        record = record_request(ledger, "add rank fusion")
        ledger.append("request", "add rank fusion",
                      {"digest": record["data"]["digest"], "status": "refused"}, [])
        self.assertEqual(review_requests(ledger.records)["findings"], [])

    def test_the_precheck_reads_a_refusal_reason(self) -> None:
        """The whole point of keeping the reason: the next precheck can say
        `this was refused` rather than `this was closed`."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("request", "add rank fusion to retrieval",
                           {"status": "refused",
                            "value": "rank fusion rejected as incompatible with "
                                     "local-first retrieval"})
            report = precheck(project, archive, "add rank fusion to retrieval")
        self.assertTrue(report["already_rejected"], report)


if __name__ == "__main__":
    unittest.main()
