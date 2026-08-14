"""U-V2: disposition register + rejection precedent.

A closed-enumeration register over decisions where "was true, got
superseded" and "worse than baseline" are first-class facts, refusals
become citable precedent, and every entry points at its evidence. The
register itself is a derived view - a pure fold over `decision` records
whose subject is `reg:<domain>:<key>` - never a stored second copy, so it
can never drift from the ledger that backs it.
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

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_register import (  # noqa: E402
    STATES,
    conflict_findings,
    rejected_precedents,
    register_view,
    set_state,
    state_of,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class FoldTests(unittest.TestCase):
    def test_fold_returns_the_latest_state_for_a_key(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = set_state(archive, "retrieval", "rank-fusion", "established",
                              ["file:notes.md"])
            set_state(archive, "retrieval", "rank-fusion", "superseded",
                     ["file:notes.md"], supersedes=first["sequence"])
            view = register_view(archive, "retrieval")
        self.assertEqual(view["rank-fusion"]["state"], "superseded")
        self.assertEqual(view["rank-fusion"]["lineage"],
                         [first["sequence"], first["sequence"] + 1])

    def test_a_different_domain_does_not_leak_into_the_view(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            set_state(archive, "retrieval", "rank-fusion", "established", ["file:a.md"])
            set_state(archive, "ranking", "rank-fusion", "established", ["file:b.md"])
            view = register_view(archive, "retrieval")
        self.assertEqual(set(view.keys()), {"rank-fusion"})


class DefaultOpenTests(unittest.TestCase):
    def test_an_unlisted_key_reads_as_the_explicit_default_open(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertEqual(state_of(archive, "retrieval", "never-set"), "open")

    def test_an_unlisted_key_is_absent_from_the_folded_view(self) -> None:
        """`open` is a named default, not a dict entry that happens to exist -
        register_view() only returns keys that actually have records."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            set_state(archive, "retrieval", "rank-fusion", "established", ["file:a.md"])
            view = register_view(archive, "retrieval")
        self.assertNotIn("never-set", view)
        self.assertEqual(state_of(archive, "retrieval", "never-set"), "open")


class EvidenceRequiredTests(unittest.TestCase):
    def test_a_non_open_state_with_no_evidence_is_refused_at_set(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "rank-fusion", "established", [])

    def test_an_open_state_needs_no_evidence(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = set_state(archive, "retrieval", "rank-fusion", "open", [])
        self.assertEqual(record["data"]["state"], "open")

    def test_evidence_without_a_recognised_prefix_does_not_count(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "rank-fusion", "established",
                         ["just some prose, not a citation"])

    def test_a_raw_append_that_strips_evidence_is_refused_at_the_archive_seam(self) -> None:
        """The plant: not just set_state's own precondition, but the
        archive-seam invariant (godmode_invariants._register_invariants)
        catches a raw append that skips set_state entirely."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "decision", "reg:retrieval:rank-fusion",
                    {"register_domain": "retrieval", "register_key": "rank-fusion",
                     "state": "established", "supersedes": None, "delta": None,
                     "evidence": []},
                    evidence=[],
                )

    def test_a_raw_append_with_an_unlisted_state_is_refused_at_the_archive_seam(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "decision", "reg:retrieval:rank-fusion",
                    {"register_domain": "retrieval", "register_key": "rank-fusion",
                     "state": "half-decided", "supersedes": None, "delta": None,
                     "evidence": ["file:notes.md"]},
                    evidence=["file:notes.md"],
                )

    def test_an_ordinary_decision_record_is_unaffected(self) -> None:
        """The archive-seam invariant only fires on register-shaped data
        (a `register_key` field); every other decision subject this kind
        already carries must keep working unexamined."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = archive.append("decision", "removal:vector-embeddings",
                                    {"reason": "no network", "status": "removed"},
                                    evidence=[])
        self.assertEqual(record["data"]["status"], "removed")


class TransitionMatrixTests(unittest.TestCase):
    def test_open_reaches_any_state(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for state in STATES:
                evidence = [] if state == "open" else ["file:notes.md"]
                record = set_state(archive, "retrieval", f"key-{state}", state, evidence)
                self.assertEqual(record["data"]["state"], state)

    def test_established_to_superseded_needs_supersedes_citing_the_seq(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            established = set_state(archive, "retrieval", "rank-fusion", "established",
                                    ["file:a.md"])
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "rank-fusion", "superseded", ["file:b.md"])
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "rank-fusion", "superseded", ["file:b.md"],
                         supersedes=established["sequence"] + 999)
            superseded = set_state(archive, "retrieval", "rank-fusion", "superseded",
                                   ["file:b.md"], supersedes=established["sequence"])
        self.assertEqual(superseded["data"]["state"], "superseded")
        self.assertEqual(superseded["data"]["supersedes"], established["sequence"])

    def test_rejected_precedent_reopens_to_established_only_via_supersede(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            rejected = set_state(archive, "retrieval", "vector-search", "rejected-precedent",
                                 ["file:a.md"])
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "vector-search", "established", ["file:b.md"])
            reopened = set_state(archive, "retrieval", "vector-search", "established",
                                 ["file:b.md"], supersedes=rejected["sequence"])
        self.assertEqual(reopened["data"]["state"], "established")
        self.assertEqual(reopened["data"]["supersedes"], rejected["sequence"])

    def test_rejected_precedent_cannot_reopen_to_any_other_state(self) -> None:
        """Only `established` is reachable from `rejected-precedent` - not
        `superseded`, even with a correctly-cited supersede."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            rejected = set_state(archive, "retrieval", "vector-search", "rejected-precedent",
                                 ["file:a.md"])
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "vector-search", "superseded", ["file:b.md"],
                         supersedes=rejected["sequence"])

    def test_established_cannot_move_to_rejected_precedent(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            established = set_state(archive, "retrieval", "rank-fusion", "established",
                                    ["file:a.md"])
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "rank-fusion", "rejected-precedent",
                         ["file:b.md"], supersedes=established["sequence"])


class ConflictFindingsTests(unittest.TestCase):
    def test_a_hand_appended_conflicting_second_state_is_a_blocking_finding(self) -> None:
        """The plant: set_state() would have refused this transition
        (no legal, correctly-cited supersede). A raw archive.append() that
        skips set_state entirely still passes the archive-seam invariant
        (valid state, evidence present) and lands on disk - conflict_findings
        is the read-time detector that catches the resulting fork."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            established = set_state(archive, "retrieval", "rank-fusion", "established",
                                    ["file:a.md"])
            archive.append(
                "decision", "reg:retrieval:rank-fusion",
                {"register_domain": "retrieval", "register_key": "rank-fusion",
                 "state": "superseded", "supersedes": None, "delta": None,
                 "evidence": ["file:b.md"]},
                evidence=["file:b.md"],
            )
            findings = conflict_findings(archive, "retrieval")
        self.assertTrue(findings)
        self.assertEqual(findings[0]["key"], "rank-fusion")
        self.assertGreater(findings[0]["sequence"], established["sequence"])

    def test_a_clean_lineage_has_no_conflicts(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            established = set_state(archive, "retrieval", "rank-fusion", "established",
                                    ["file:a.md"])
            set_state(archive, "retrieval", "rank-fusion", "superseded", ["file:b.md"],
                     supersedes=established["sequence"])
            findings = conflict_findings(archive, "retrieval")
        self.assertEqual(findings, [])

    def test_an_empty_domain_has_no_conflicts(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertEqual(conflict_findings(archive, "retrieval"), [])


class DeltaTests(unittest.TestCase):
    def test_delta_is_visible_in_the_view_against_the_parent_it_replaced(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            established = set_state(archive, "retrieval", "rank-fusion", "established",
                                    ["file:a.md"], delta="added")
            view_after_add = register_view(archive, "retrieval")
            set_state(archive, "retrieval", "rank-fusion", "superseded", ["file:b.md"],
                     supersedes=established["sequence"], delta="modified")
            view_after_modify = register_view(archive, "retrieval")
        self.assertEqual(view_after_add["rank-fusion"]["delta"], "added")
        self.assertEqual(view_after_modify["rank-fusion"]["delta"], "modified")

    def test_an_unlisted_delta_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                set_state(archive, "retrieval", "rank-fusion", "established",
                         ["file:a.md"], delta="rewritten")


class RejectedPrecedentTests(unittest.TestCase):
    def test_rejected_precedents_are_collected_across_domains(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            set_state(archive, "retrieval", "vector-search", "rejected-precedent",
                     ["file:a.md"])
            set_state(archive, "ranking", "rank-fusion", "established", ["file:b.md"])
            hits = rejected_precedents(archive)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["domain"], "retrieval")
        self.assertEqual(hits[0]["key"], "vector-search")

    def test_a_reopened_precedent_stops_being_reported(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            rejected = set_state(archive, "retrieval", "vector-search", "rejected-precedent",
                                 ["file:a.md"])
            set_state(archive, "retrieval", "vector-search", "established", ["file:b.md"],
                     supersedes=rejected["sequence"])
            hits = rejected_precedents(archive)
        self.assertEqual(hits, [])


class InvariantSyncTests(unittest.TestCase):
    """godmode_invariants._register_invariants duplicates STATES/prefixes
    rather than importing this module (avoiding an import cycle back
    through godmode_chronicle - see that module's own docstring). A drift
    between the two would silently narrow or widen what the archive seam
    refuses; this pins them equal."""

    def test_the_archive_seam_state_enumeration_matches_this_module(self) -> None:
        from godmode_runtime import godmode_invariants

        self.assertEqual(set(godmode_invariants._REGISTER_STATES), set(STATES))

    def test_the_archive_seam_evidence_prefixes_match_this_module(self) -> None:
        from godmode_runtime import godmode_invariants
        from godmode_runtime.godmode_register import EVIDENCE_PREFIXES

        self.assertEqual(set(godmode_invariants._REGISTER_EVIDENCE_PREFIXES),
                         set(EVIDENCE_PREFIXES))

    def test_kind_invariants_is_populated_eagerly_at_chronicle_import(self) -> None:
        from godmode_runtime import godmode_chronicle

        self.assertIsNotNone(godmode_chronicle.KIND_INVARIANTS.get("decision"))


class ConsoleSmokeTests(unittest.TestCase):
    def test_the_register_set_command_writes_a_record(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            from godmode_runtime.godmode_console import main

            exit_code = main([
                "--project", str(project), "register", "set",
                "--domain", "retrieval", "--key", "rank-fusion",
                "--state", "established", "--evidence", "file:notes.md",
            ])
            view = register_view(archive, "retrieval")
        self.assertEqual(exit_code, 0)
        self.assertEqual(view["rank-fusion"]["state"], "established")

    def test_the_register_supersede_command_requires_supersedes(self) -> None:
        from godmode_runtime.godmode_console import _build_parser

        with self.assertRaises(SystemExit):
            _build_parser().parse_args([
                "register", "supersede", "--domain", "retrieval", "--key", "rank-fusion",
                "--state", "superseded", "--evidence", "file:notes.md",
            ])

    def test_the_register_show_command_surfaces_conflicts(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            from godmode_runtime.godmode_console import main

            main(["--project", str(project), "register", "set",
                  "--domain", "retrieval", "--key", "rank-fusion",
                  "--state", "established", "--evidence", "file:a.md"])
            archive.append(
                "decision", "reg:retrieval:rank-fusion",
                {"register_domain": "retrieval", "register_key": "rank-fusion",
                 "state": "superseded", "supersedes": None, "delta": None,
                 "evidence": ["file:b.md"]},
                evidence=["file:b.md"],
            )
            exit_code = main(["--project", str(project), "register", "show",
                              "--domain", "retrieval"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
