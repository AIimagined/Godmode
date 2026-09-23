"""NS-2 + NS-10j (0.3.28 Plan 5 Task 2): structured lessons graduate into
the compiled law only through a chained promotion + approval.

`lessons promote <lesson-seq> --cite ... --rerun-hash <h>` refuses an
unstructured lesson, naming the missing fields. `lessons approve
<promotion-seq> --rerun-hash <h>` refuses the same actor approving its own
promotion, and refuses a rerun_hash that repeats the promotion's own -
compared as fingerprints (Task 5's `agent_id()`), never as role labels.
Only a genuinely chained, genuinely independent approval graduates the
lesson to `status: active`, which is what `godmode_law._guarded_lessons`
(law compile) actually reads.
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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from _law_fixtures import OPERATOR_RECORD_FIELDS  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime import godmode_law  # noqa: E402
from godmode_runtime.godmode_law import (  # noqa: E402
    _standing_record, compile_laws, hygiene, law_candidates, promote_candidate,
    record_correction_candidate, shelve_oldest_candidates, top_laws,
)
from godmode_runtime.godmode_lessons import (  # noqa: E402
    MAX_CANDIDATE_CHARS, MAX_CANDIDATES, approve, promote,
)


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-approval-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_STRUCTURED = {
    "root_cause": "the export ran before the archive flushed",
    "correction": "flush the archive before exporting",
    "reflection": "any export needs its precondition named",
    "generalized_guard": "flush the archive before every export",
    "refuted_by": "an export succeeds even when the archive was not flushed",
}


def _structured_lesson(archive: Chronicle, subject: str, **overrides) -> dict:
    data = {"status": "candidate", "value": "v", **_STRUCTURED, **overrides}
    return archive.append("lesson", subject, data, evidence=[])


class PromoteRefusalTests(unittest.TestCase):
    def test_promotion_of_an_unstructured_lesson_names_the_missing_fields(self) -> None:
        with _project() as (_root, archive):
            lesson = archive.append(
                "lesson", "half-written",
                {"status": "candidate", "value": "v",
                 "generalized_guard": "g", "root_cause": "x"},
                evidence=[])
            with self.assertRaises(ArchiveError) as ctx:
                promote(archive, lesson["sequence"], ["seq:1"], _hash("rerun-a"))
        # The refusal names exactly the fields this lesson lacks - not
        # merely a generic "incomplete" message.
        named = str(ctx.exception).split(
            "missing structured field(s) ", 1)[1].split(" -", 1)[0]
        self.assertEqual(sorted(f.strip() for f in named.split(",")),
                         ["correction", "falsifier", "reflection"])

    def test_promotion_with_no_citation_is_refused(self) -> None:
        with _project() as (_root, archive):
            lesson = _structured_lesson(archive, "flush-before-export")
            with self.assertRaises(ArchiveError):
                promote(archive, lesson["sequence"], [], _hash("rerun-a"))

    def test_promotion_with_a_malformed_rerun_hash_is_refused(self) -> None:
        with _project() as (_root, archive):
            lesson = _structured_lesson(archive, "flush-before-export")
            with self.assertRaises(ArchiveError):
                promote(archive, lesson["sequence"], ["seq:1"], "not-a-hash")

    def test_promotion_of_an_unknown_lesson_is_refused(self) -> None:
        with _project() as (_root, archive):
            with self.assertRaises(ArchiveError):
                promote(archive, 99999, ["seq:1"], _hash("rerun-a"))


class ApproveRefusalTests(unittest.TestCase):
    def _promote(self, archive: Chronicle, subject: str = "flush-before-export"):
        lesson = _structured_lesson(archive, subject)
        with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
            promotion = promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun"))
        return lesson, promotion

    def test_same_actor_approval_is_refused(self) -> None:
        with _project() as (_root, archive):
            _lesson, promotion = self._promote(archive)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                with self.assertRaises(ArchiveError) as ctx:
                    approve(archive, promotion["sequence"], _hash("checker-rerun"))
        self.assertIn("same actor", str(ctx.exception))

    def test_same_rerun_hash_is_refused(self) -> None:
        with _project() as (_root, archive):
            _lesson, promotion = self._promote(archive)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                with self.assertRaises(ArchiveError) as ctx:
                    approve(archive, promotion["sequence"], _hash("author-rerun"))
        self.assertIn("rerun_hash", str(ctx.exception))

    def test_approval_of_an_unknown_promotion_is_refused(self) -> None:
        with _project() as (_root, archive):
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                with self.assertRaises(ArchiveError):
                    approve(archive, 99999, _hash("checker-rerun"))


class ChainedApprovalCompilesTests(unittest.TestCase):
    def test_a_chained_approval_graduates_the_lesson_and_compiles(self) -> None:
        with _project() as (root, archive):
            lesson = _structured_lesson(archive, "flush-before-export")
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                promotion = promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun"))
            # Not yet: only a promotion exists, no approval.
            self.assertEqual(top_laws(archive, 5), [])
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                outcome = approve(archive, promotion["sequence"], _hash("checker-rerun"))
            self.assertIsNotNone(outcome["graduated_seq"])
            laws = top_laws(archive, 5)
            report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
        self.assertEqual(len(laws), 1)
        self.assertEqual(laws[0]["subject"], "flush-before-export")
        self.assertEqual(laws[0]["guard"], _STRUCTURED["generalized_guard"])
        self.assertEqual(report["laws"], 1)
        self.assertIn("flush the archive before every export", text)

    def test_a_second_promotion_of_a_graduated_candidate_is_refused(self) -> None:
        # B2 + nit 5 (task-2-review.md), the reaffirmation case: once the
        # candidate has graduated, it is no longer a candidate and no
        # longer the subject's current record, so a second promotion of it
        # is refused rather than minting a second active law on one
        # subject. Re-affirming a standing law means promoting its CURRENT
        # record, not re-running the one that is already spent.
        with _project() as (_root, archive):
            lesson = _structured_lesson(archive, "flush-before-export")
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                promotion = promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun"))
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                first = approve(archive, promotion["sequence"], _hash("checker-rerun-1"))
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                with self.assertRaises(ArchiveError) as ctx:
                    promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun-2"))
            laws = top_laws(archive, 5)
            actives = [r for r in archive.read_events()
                       if r.get("kind") == "lesson"
                       and str((r.get("data") or {}).get("status")) == "active"]
        self.assertIsNotNone(first["graduated_seq"])
        # The candidate record itself is untouched (the archive is
        # append-only), so what makes the second promotion stale is that
        # the subject has MOVED PAST it - which is the rule being tested.
        self.assertIn("no longer what this subject says", str(ctx.exception))
        self.assertEqual(len(laws), 1)
        # One subject, one active record - never the duplicate-active shape.
        self.assertEqual(len(actives), 1)

    def test_an_approval_cannot_resurrect_a_retired_subject(self) -> None:
        # B2 (task-2-review.md): `approve` graduated from the record the
        # promotion PINNED and never looked at what was newest for the
        # subject, so a promotion minted before a retirement could be
        # approved after it - by a third party - and put the retired guard
        # straight back into the compiled law with no refusal anywhere.
        # Retirement is the archive's own documented way to lift a bad
        # guard; nothing may silently undo it.
        with _project() as (_root, archive):
            lesson = _structured_lesson(archive, "bad-guard")
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                promotion = promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun"))
            archive.append(
                "lesson", "bad-guard",
                {"status": "retired", "value": "lifted", **_STRUCTURED},
                evidence=[])
            self.assertEqual(top_laws(archive, 5), [])
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                with self.assertRaises(ArchiveError) as ctx:
                    approve(archive, promotion["sequence"], _hash("checker-rerun"))
            laws = top_laws(archive, 5)
            approvals = [r for r in archive.read_events()
                         if r.get("kind") == "lesson_approval"]
        self.assertIn("stale", str(ctx.exception))
        self.assertIn("retired", str(ctx.exception))
        self.assertEqual(laws, [])
        # A refused approval leaves no `lesson_approval` behind claiming it
        # graduated something.
        self.assertEqual(approvals, [])

    def test_an_unchanged_subject_still_approves(self) -> None:
        # B2's other direction: the staleness rule must not refuse the
        # ordinary case it exists to protect.
        with _project() as (_root, archive):
            lesson = _structured_lesson(archive, "still-current")
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                promotion = promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun"))
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                outcome = approve(archive, promotion["sequence"], _hash("checker-rerun"))
            laws = top_laws(archive, 5)
        self.assertIsNotNone(outcome["graduated_seq"])
        self.assertEqual([law["subject"] for law in laws], ["still-current"])

    def test_a_promotion_is_approved_only_once(self) -> None:
        # M2 (task-2-review.md): a second approval of the SAME promotion
        # used to mint a second `lesson_approval` and a second active
        # `lesson` on one subject - the duplicate-active shape
        # `_guarded_lessons`'s own dedup comment records as a bug fixed
        # once already, and the shape `godmode forget`'s contradiction pass
        # exists to flag. Refused by name, citing the first approval.
        with _project() as (_root, archive):
            lesson = _structured_lesson(archive, "approved-once")
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
                promotion = promote(archive, lesson["sequence"], ["seq:1"], _hash("author-rerun"))
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
                first = approve(archive, promotion["sequence"], _hash("checker-rerun-1"))
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "third-agent"}):
                with self.assertRaises(ArchiveError) as ctx:
                    approve(archive, promotion["sequence"], _hash("checker-rerun-2"))
            approvals = [r for r in archive.read_events()
                         if r.get("kind") == "lesson_approval"]
            actives = [r for r in archive.read_events()
                       if r.get("kind") == "lesson"
                       and str((r.get("data") or {}).get("status")) == "active"]
        # The refusal names the first approval, never merely "already done".
        self.assertIn(str(first["sequence"]), str(ctx.exception))
        self.assertEqual(len(approvals), 1)
        self.assertEqual(len(actives), 1)

    def test_a_lesson_that_is_not_a_candidate_cannot_be_promoted(self) -> None:
        # Nit 5 (task-2-review.md): promoting an already-active lesson
        # succeeded and then granted nothing - `approve` wrote a real
        # `lesson_approval` and reported `graduated_seq: None`. A promotion
        # that cannot graduate anything is refused where it can be read.
        with _project() as (_root, archive):
            active = _structured_lesson(archive, "already-law", status="active")
            with self.assertRaises(ArchiveError) as ctx:
                promote(archive, active["sequence"], ["seq:1"], _hash("rerun"))
        self.assertIn("not 'candidate'", str(ctx.exception))


class LadderFeedsPromotionTests(unittest.TestCase):
    def test_the_ladder_writes_a_promotion_not_a_direct_law(self) -> None:
        with _project() as (_root, archive):
            for session in ("S-1", "S-2", "S-3"):
                record_correction_candidate(
                    archive, "wrong again - you missed the registry check",
                    session=session)
            cluster = law_candidates(archive)[0]
            record = promote_candidate(
                archive, cluster["first_seq"],
                guard="verify against the registry before ranking",
                subject="registry-check-before-ranking")
        self.assertEqual(record["data"]["status"], "candidate")
        self.assertIn("promotion", record)
        self.assertEqual(record["promotion"]["lesson_seq"], record["sequence"])
        self.assertEqual(top_laws(archive, 5), [])


class HygieneStaleCandidateTests(unittest.TestCase):
    def test_hygiene_lists_a_candidate_never_promoted_after_three_sessions(self) -> None:
        with _project() as (_root, archive):
            for session in ("S-1", "S-2", "S-3"):
                record_correction_candidate(
                    archive, "wrong again - you missed the registry check",
                    session=session)
            findings = [f for f in hygiene(archive)["findings"]
                        if f["check"] == "stale-candidate"]
        self.assertEqual(len(findings), 1)

    def test_a_below_bar_candidate_is_not_yet_stale(self) -> None:
        with _project() as (_root, archive):
            record_correction_candidate(
                archive, "wrong again - you missed the registry check",
                session="S-1")
            findings = [f for f in hygiene(archive)["findings"]
                        if f["check"] == "stale-candidate"]
        self.assertEqual(findings, [])

    def test_a_promoted_cluster_is_no_longer_a_stale_candidate(self) -> None:
        with _project() as (_root, archive):
            for session in ("S-1", "S-2", "S-3"):
                record_correction_candidate(
                    archive, "wrong again - you missed the registry check",
                    session=session)
            cluster = law_candidates(archive)[0]
            promote_candidate(
                archive, cluster["first_seq"], guard="g", subject="s")
            findings = [f for f in hygiene(archive)["findings"]
                        if f["check"] == "stale-candidate"]
        self.assertEqual(findings, [])


class ShelvingTests(unittest.TestCase):
    def test_shelving_is_a_no_op_under_the_caps(self) -> None:
        with _project() as (_root, archive):
            archive.append(
                "lesson", "one-candidate",
                {"status": "candidate", "value": "v", "generalized_guard": "g"},
                evidence=[])
            report = shelve_oldest_candidates(archive)
        self.assertEqual(report["archived"], 0)

    def test_shelving_takes_the_oldest_over_the_count_cap_and_never_breaks_the_chain(self) -> None:
        with _project() as (root, archive):
            for index in range(MAX_CANDIDATES + 5):
                archive.append(
                    "lesson", f"candidate-{index}",
                    {"status": "candidate", "value": "v",
                     "generalized_guard": f"guard {index}"},
                    evidence=[])
            report = shelve_oldest_candidates(archive)
            archived_note = next(
                r for r in archive.read_events() if r["kind"] == "lesson_candidate")
            verify = archive.verify(archive.read_events())
        self.assertEqual(report["archived"], 5)
        self.assertEqual(len(archived_note["data"]["archived_seqs"]), 5)
        # The oldest five (seq 1..5) are the ones named, never the newest.
        self.assertEqual(sorted(archived_note["data"]["archived_seqs"]), [1, 2, 3, 4, 5])
        self.assertTrue(verify["ok"], verify)
        # A second call over the same set shelves nothing further.
        self.assertEqual(shelve_oldest_candidates(archive)["archived"], 0)

    def test_a_shelved_candidate_is_no_longer_live_for_the_candidate_reader(self) -> None:
        # M3 (task-2-review.md): the cap has to bound what the candidate
        # reader actually returns. Before this, `law_candidates` ignored
        # the shelf note entirely - a shelved candidate still clustered,
        # still counted toward the promotion ladder's recurrence bar, and
        # was still promotable, so the cap bought nothing but its own
        # idempotence while its docstring claimed a bound.
        with _project() as (_root, archive):
            for session in ("S-1", "S-2", "S-3"):
                record_correction_candidate(
                    archive, "wrong again - you missed the registry check",
                    session=session)
            before = law_candidates(archive)
            self.assertEqual(len(before), 1)
            self.assertEqual(before[0]["occurrences"], 3)
            shelved = [int(r["sequence"]) for r in archive.read_events()
                       if r.get("kind") == "lesson"
                       and str((r.get("data") or {}).get("status")) == "candidate"]
            archive.append(
                "lesson_candidate", "candidate-shelf",
                {"archived_seqs": shelved, "archived_count": len(shelved),
                 "reason": "shelved by this test"},
                evidence=[f"seq:{seq}" for seq in shelved])
            after = law_candidates(archive)
        self.assertEqual(after, [])

    def test_shelving_takes_the_oldest_over_the_char_cap(self) -> None:
        with _project() as (_root, archive):
            big_guard = "g" * (MAX_CANDIDATE_CHARS // 2)
            for index in range(3):
                archive.append(
                    "lesson", f"candidate-{index}",
                    {"status": "candidate", "value": "v",
                     "generalized_guard": big_guard},
                    evidence=[])
            report = shelve_oldest_candidates(archive)
            verify = archive.verify(archive.read_events())
        self.assertGreaterEqual(report["archived"], 1)
        self.assertTrue(verify["ok"], verify)


class StandingRecordTests(unittest.TestCase):
    """`_standing_record` on hand-built histories: which record binds, and
    which newer records lift it, are decided by authority and trust rank,
    not by recency alone. Records are dicts shaped like sealed ones -
    `writer` is a top-level field (`OPERATOR_RECORD_FIELDS`), never data."""

    @staticmethod
    def _record(seq: int, data: dict, *, operator: bool = False) -> dict:
        record = {"kind": "lesson", "subject": "s", "sequence": seq,
                  "data": data, "recorded_at": "2026-09-23T00:00:00+00:00"}
        if operator:
            record.update(OPERATOR_RECORD_FIELDS)
        return record

    def _operator_law(self, seq: int = 1) -> dict:
        return self._record(seq, {"status": "active", "generalized_guard": "OP guard"},
                            operator=True)

    def test_an_agent_superseded_record_is_pending_not_a_lift(self) -> None:
        history = [self._operator_law(),
                   self._record(2, {"status": "superseded", "generalized_guard": "x"})]
        standing, pending = _standing_record(history, 0)
        self.assertEqual(standing["sequence"], 1)
        self.assertEqual(pending["sequence"], 2)

    def test_an_agent_guard_drop_on_an_operator_law_is_pending(self) -> None:
        history = [self._operator_law(),
                   self._record(2, {"status": "active", "value": "no guard here"})]
        standing, pending = _standing_record(history, 0)
        self.assertEqual(standing["sequence"], 1)
        self.assertEqual(pending["sequence"], 2)

    def test_an_operator_guard_drop_lifts_the_law(self) -> None:
        history = [self._operator_law(),
                   self._record(2, {"status": "active", "value": "guard withdrawn"},
                                operator=True)]
        self.assertEqual(_standing_record(history, 0), (None, None))

    def test_an_operator_supersession_lifts_the_law(self) -> None:
        history = [self._operator_law(),
                   self._record(2, {"status": "superseded"}, operator=True)]
        self.assertEqual(_standing_record(history, 0), (None, None))

    def test_an_agent_lifts_a_grandfathered_agent_law(self) -> None:
        # Equal trust: the writer that set the guard may end it. The cutoff
        # grandfathers seq 1; the retirement above it needs no authority.
        history = [self._record(1, {"status": "active", "generalized_guard": "old"}),
                   self._record(2, {"status": "retired"})]
        self.assertEqual(_standing_record(history, 1), (None, None))

    def test_a_pending_lift_then_an_operator_reissue_binds_the_reissue(self) -> None:
        history = [self._operator_law(),
                   self._record(2, {"status": "superseded"}),
                   self._record(3, {"status": "active", "generalized_guard": "OP v2"},
                                operator=True)]
        standing, pending = _standing_record(history, 0)
        self.assertEqual(standing["sequence"], 3)
        self.assertIsNone(pending)


class GrandfatherMigrationTests(unittest.TestCase):
    """NS-2 fix round 2: the upgrade blocker. The authority gate is right
    for every new write and retroactive against every old one - an archive
    recorded before it existed holds guarded lessons with neither approval
    lineage nor operator trust, because at the time neither was asked for,
    so the first compile after the upgrade emptied the project's whole Code
    of Law in silence. The remedy is one chained migration record drawing a
    cutoff under the past. These tests hold that line where it belongs: old
    laws survive, a guard written after the gate shipped still needs a
    second actor, the migration happens once, retirement still lifts a
    grandfathered guard, and the compiled file says which laws were
    grandfathered rather than quietly carrying them.
    """

    @staticmethod
    @contextmanager
    def _before_the_gate():
        """Compile as if the gate had not shipped yet, which is what makes
        the records these tests write genuinely pre-gate. The boundary is a
        DATE (`godmode_law.GATE_SHIPPED_DATE`) read once, by the migration
        writer; every reader afterwards works off the sequence the
        migration recorded, so this window has to cover the first compile
        and nothing else."""
        with mock.patch.object(godmode_law, "GATE_SHIPPED_DATE", "2999-01-01"):
            yield

    @staticmethod
    def _pre_gate(archive, subject: str, guard: str, value: str = "observed"):
        """A lesson exactly as an agent wrote it before the gate existed:
        active, guarded, no promotion, no approval, agent trust."""
        return archive.append(
            "lesson", subject,
            {"status": "active", "value": value, "generalized_guard": guard},
            evidence=[])

    @staticmethod
    def _graduated(archive, subject: str, guard: str):
        """A lesson that earned its way in the designed way, for contrast:
        structured candidate, promoted by one actor, approved by another."""
        lesson = _structured_lesson(archive, subject, generalized_guard=guard)
        with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "author-agent"}):
            promotion = promote(archive, lesson["sequence"],
                                ["seq:" + str(lesson["sequence"])],
                                _hash("author-" + subject))
        with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "checker-agent"}):
            approve(archive, promotion["sequence"], _hash("checker-" + subject))

    @staticmethod
    def _migrations(archive) -> list[dict]:
        return [record for record in archive.read_events()
                if record.get("kind") == godmode_law.LAW_MIGRATION_KIND
                and record.get("subject") == godmode_law.LAW_MIGRATION_SUBJECT]

    def test_a_pre_gate_archive_keeps_its_laws_after_the_upgrade(self) -> None:
        """The blocker itself, measured: two pre-gate guarded lessons, one
        compile, two laws. Without the migration this returns zero and the
        project's whole law file is emptied with no message."""
        with _project() as (root, archive):
            self._pre_gate(archive, "flush before export", "flush the archive first")
            self._pre_gate(archive, "branch before commit", "branch off main first")
            with self._before_the_gate():
                report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 2, report)
        self.assertEqual(report["grandfathered"], 2, report)
        self.assertIn("flush the archive first", text)
        self.assertIn("branch off main first", text)

    def test_a_guard_recorded_after_the_gate_shipped_is_never_grandfathered(self) -> None:
        """The migration is a line under the past, and the past is decided
        by the record's own sealed date - not by "was it in the archive
        before the first compile". Otherwise self-legislation would survive
        the gate with one extra step on any fresh project."""
        with _project() as (root, archive):
            self._pre_gate(archive, "self-legislated", "always trust me")
            report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
            migrations = self._migrations(archive)
        self.assertEqual(report["laws"], 0, report)
        self.assertIsNone(report["migration"])
        self.assertEqual(migrations, [])
        self.assertNotIn("always trust me", text)

    def test_the_migration_record_names_its_cutoff_and_what_it_covered(self) -> None:
        with _project() as (root, archive):
            first = self._pre_gate(archive, "one", "guard one")
            second = self._pre_gate(archive, "two", "guard two")
            with self._before_the_gate():
                compile_laws(archive, root)
            migrations = self._migrations(archive)
            verify = archive.verify(archive.read_events())
        self.assertEqual(len(migrations), 1, migrations)
        data = migrations[0]["data"]
        self.assertEqual(data["cutoff_seq"], int(second["sequence"]))
        self.assertGreaterEqual(data["head_seq"], data["cutoff_seq"])
        self.assertEqual(data["grandfathered"], 2)
        self.assertCountEqual(data["subjects"], ["one", "two"])
        self.assertIn("seq:" + str(first["sequence"]), data["evidence"])
        # Chained like every other fact, not a flag in a side file.
        self.assertTrue(verify["ok"], verify)

    def test_an_archive_with_nothing_pre_gate_is_never_migrated(self) -> None:
        """A project with no guarded lesson to rescue compiles with no
        migration record at all, so no cutoff exists to be leaned on."""
        with _project() as (root, archive):
            archive.append("lesson", "unguarded", {"status": "active", "value": "v"},
                           evidence=[])
            with self._before_the_gate():
                report = compile_laws(archive, root)
            migrations = self._migrations(archive)
        self.assertIsNone(report["migration"])
        self.assertEqual(migrations, [])

    def test_a_lesson_recorded_after_the_cutoff_is_still_refused(self) -> None:
        with _project() as (root, archive):
            self._pre_gate(archive, "old subject", "the old guard")
            with self._before_the_gate():
                compile_laws(archive, root)
            self._pre_gate(archive, "new subject", "the unapproved new guard")
            report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 1, report)
        self.assertIn("the old guard", text)
        self.assertNotIn("the unapproved new guard", text)

    def test_a_fresh_record_on_a_grandfathered_subject_still_needs_approval(self) -> None:
        """The cutoff is a line under the past, not a standing exemption for
        a subject: re-recording the same subject after the migration does
        not put the new guard into the law - that record has to earn its
        own way in. What it does NOT do (0.3.28 release preflight) is lift
        the grandfathered guard: an unapproved record is pending, and the
        law the operator was already living under stays in force, marked."""
        with _project() as (root, archive):
            self._pre_gate(archive, "one subject", "the grandfathered guard")
            with self._before_the_gate():
                compile_laws(archive, root)
            fresh = self._pre_gate(
                archive, "one subject", "a widened guard nobody approved")
            report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 1, report)
        self.assertEqual(report["pending_amendments"], 1, report)
        self.assertNotIn("a widened guard nobody approved", text)
        self.assertIn("the grandfathered guard", text)
        self.assertIn(f"[AMENDMENT PENDING seq:{fresh['sequence']}]", text)

    def test_the_migration_is_idempotent(self) -> None:
        with _project() as (root, archive):
            self._pre_gate(archive, "one", "guard one")
            with self._before_the_gate():
                first = compile_laws(archive, root)
                second = compile_laws(archive, root)
            third = compile_laws(archive, root)
            migrations = self._migrations(archive)
        self.assertIsNotNone(first["migration"])
        self.assertIsNone(second["migration"])
        self.assertIsNone(third["migration"])
        self.assertEqual(len(migrations), 1, migrations)
        self.assertEqual(second["laws"], 1)
        self.assertEqual(third["laws"], 1)

    def test_retiring_a_grandfathered_lesson_still_lifts_its_guard(self) -> None:
        """Retirement is the archive's documented way to lift a bad guard,
        and a grandfathered guard is exactly the kind most likely to be
        wrong. The retirement record sits ABOVE the cutoff and carries no
        approval - it must still count, because dormancy is read before
        authority is ever asked about."""
        with _project() as (root, archive):
            self._pre_gate(archive, "retire me", "the guard to lift")
            with self._before_the_gate():
                compile_laws(archive, root)
            archive.append(
                "lesson", "retire me",
                {"status": "retired", "value": "v",
                 "generalized_guard": "the guard to lift"},
                evidence=[])
            report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 0, report)
        self.assertNotIn("the guard to lift", text)

    def test_the_compiled_file_marks_which_laws_were_grandfathered(self) -> None:
        with _project() as (root, archive):
            self._pre_gate(archive, "pre-gate subject", "the old guard")
            self._graduated(archive, "approved subject", "the approved guard")
            with self._before_the_gate():
                report = compile_laws(archive, root)
            text = (root / "GODMODE-CODE-OF-LAW.md").read_text(encoding="utf-8")
        self.assertEqual(report["laws"], 2, report)
        self.assertEqual(report["grandfathered"], 1, report)
        # Once in the note that explains the marker, once on the one law.
        self.assertEqual(text.count("[GRANDFATHERED]"), 2, text)
        self.assertIn("lessons approve", text)
        marked = [line for line in text.splitlines()
                  if line.startswith("## Law") and "[GRANDFATHERED]" in line]
        self.assertEqual(len(marked), 1, marked)
        self.assertIn("pre-gate subject", marked[0])

    def test_hygiene_counts_the_grandfathered_laws_still_unapproved(self) -> None:
        with _project() as (root, archive):
            self._pre_gate(archive, "one", "guard one")
            self._pre_gate(archive, "two", "guard two")
            self._graduated(archive, "three", "guard three")
            with self._before_the_gate():
                compile_laws(archive, root)
            report = hygiene(archive)
        self.assertEqual(report["grandfathered_unapproved"], 2, report)
        checks = [finding["check"] for finding in report["findings"]]
        self.assertIn("grandfathered-law", checks)

    def test_hygiene_reports_nothing_grandfathered_on_an_approved_archive(self) -> None:
        with _project() as (root, archive):
            self._graduated(archive, "three", "guard three")
            with self._before_the_gate():
                compile_laws(archive, root)
            report = hygiene(archive)
        self.assertEqual(report["grandfathered_unapproved"], 0, report)
        self.assertNotIn("grandfathered-law",
                         [finding["check"] for finding in report["findings"]])


if __name__ == "__main__":
    unittest.main()
