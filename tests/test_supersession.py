"""NS-10e: supersession as a typed edge (0.3.28 Plan 5 Task 6).

WHY: `expunge` stays the retraction; `remember --supersedes <seq>` records
VERSIONED supersession instead - a new record naming exactly which earlier
record it replaces. `godmode_chronicle.superseded_sequences`/
`latest_by_subject` are the ONE place the resulting rule lives: a record is
never "latest" again once some other record has named its sequence via
`supersedes`, no matter how much later, chronologically, an unrelated
record on the same key sits with no edge of its own. Every latest-per-
subject reader this sprint could find by grep routes through that helper
(listed in the task report); this file proves the write-time validation,
the helper's own rule in isolation, each reader honouring it, the
`history --subject` chain render, and the graph's generic derivation.
"""

from __future__ import annotations

import contextlib
import io
import json
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

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import (  # noqa: E402
    Chronicle,
    latest_by_subject,
    superseded_sequences,
)
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime import godmode_graph as graph  # noqa: E402
from godmode_runtime import godmode_hygiene  # noqa: E402
from godmode_runtime import godmode_iteration  # noqa: E402
from godmode_runtime import godmode_mistakes  # noqa: E402
from godmode_runtime import godmode_obligations  # noqa: E402
from godmode_runtime import godmode_requests  # noqa: E402
from godmode_runtime import godmode_status  # noqa: E402
from godmode_runtime.godmode_attest import lesson_pipeline, obligations_digest  # noqa: E402


@contextlib.contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


def _run(project: Path, *argv: str) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


def _run_err(project: Path, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = console_main(["--project", str(project), "--json", *argv])
    return code, out.getvalue().strip()


class SupersedesValidationTests(unittest.TestCase):
    def test_unknown_sequence_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, err = _run_err(
                project, "remember", "--kind", "decision", "--subject", "d",
                "--value", "v2", "--supersedes", "999")
            self.assertNotEqual(code, 0)
            self.assertIn("999", err)
            self.assertIn("names no record", err)

    def test_different_kind_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "d", {"value": "v1", "status": "active"})
            code, err = _run_err(
                project, "remember", "--kind", "obligation", "--subject", "o",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertNotEqual(code, 0)
            self.assertIn("decision", err)
            self.assertIn("can only supersede", err)

    def test_already_superseded_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "d", {"value": "v1", "status": "active"})
            code, _ = _run(
                project, "remember", "--kind", "decision", "--subject", "d",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertEqual(code, 0)
            code, err = _run_err(
                project, "remember", "--kind", "decision", "--subject", "d3",
                "--value", "v3", "--supersedes", str(first["sequence"]))
            self.assertNotEqual(code, 0)
            self.assertIn("already superseded", err)

    def test_success_stores_field(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "d", {"value": "v1", "status": "active"})
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "d",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertEqual(code, 0)
            self.assertEqual(payload["record"]["data"]["supersedes"], first["sequence"])

    def test_pattern_and_incident_kinds_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "pattern", "p", {"workaround": "w", "class": "test-fabrication", "occurrences": [1]})
            code, err = _run_err(
                project, "remember", "--kind", "pattern", "--subject", "p",
                "--class", "test-fabrication", "--occurrence", "seq:1",
                "--value", "w2", "--supersedes", str(first["sequence"]))
            self.assertNotEqual(code, 0)
            self.assertIn("not supported for --kind pattern", err)

    def test_incident_kind_refused(self) -> None:
        # S5 (fix round 1): the `pattern` half of the refusal was tested;
        # the `incident` early-return branch (console.py's `cmd_remember`,
        # before the `incident` return at :3944) runs the exact same
        # `_SUPERSEDES_UNSUPPORTED_KINDS` check first, but it was unproven.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("incident", "i", {"detail": "d"})
            code, err = _run_err(
                project, "remember", "--kind", "incident", "--subject", "i",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertNotEqual(code, 0)
            self.assertIn("not supported for --kind incident", err)


class WriterTrustGatesSupersessionTests(unittest.TestCase):
    """B1 (fix round 1): supersession sat upstream of Task 5's writer-trust
    rule and bypassed it entirely - an agent's `--supersedes` could erase
    an operator's record from every latest-per-subject reader, something
    NS-8k's own status-flip refusal would never have allowed. Both halves
    of the fix: write-time (`_validate_supersedes` refuses the write) and
    read-time (`superseded_sequences` ignores a citation from a
    lower-trust writer than its target - the durable half, since a raw
    append bypasses the CLI's write-time gate by design)."""

    def test_agent_cannot_supersede_an_operator_record(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "obligation", "o", {"status": "open", "value": "v1"},
                as_operator=True, operator_verified=True)
            self.assertEqual(first["writer"], "operator")
            code, err = _run_err(
                project, "remember", "--kind", "obligation", "--subject", "o2",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertNotEqual(code, 0)
            self.assertIn("operator", err)
            self.assertIn("--as-operator", err)

    def test_hand_appended_lower_trust_edge_is_ignored_by_latest_by_subject(self) -> None:
        # The write-time gate above only covers the CLI. A record already
        # on disk - written before this field existed, or by a path that
        # bypassed the console entirely - still marks its target
        # `supersedes`, and `superseded_sequences` must still refuse to
        # honour a citation from a writer trust cannot back.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "obligation", "o", {"status": "open", "value": "v1"},
                as_operator=True, operator_verified=True)
            self.assertEqual(first["writer"], "operator")
            archive.append(
                "obligation", "o2",
                {"status": "open", "value": "v2", "supersedes": first["sequence"]})
            latest = latest_by_subject(archive.read_events())
            self.assertEqual(latest["o"]["sequence"], first["sequence"])
            self.assertNotIn(first["sequence"], superseded_sequences(archive.read_events()))


class DigestAgreesWithRemainingTests(unittest.TestCase):
    """B2 (fix round 1): `godmode_attest.obligations_digest` fed `status
    --digest` and the session closure verdict through a plain per-subject
    fold that never honoured a `supersedes` edge, so `godmode status` and
    `godmode status --digest` could disagree about the same archive -
    `remaining()` drops a superseded obligation, `obligations_digest`
    still counted it open."""

    def test_status_and_digest_agree_after_supersession(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("obligation", "old duty", {"status": "open", "value": "v1"})
            archive.append(
                "obligation", "new duty",
                {"status": "open", "value": "v2", "supersedes": first["sequence"]})
            report = godmode_status.remaining(archive, project)
            open_ids = {e["id"] for e in report["remaining"] if e["source"] == "obligation"}
            self.assertEqual(open_ids, {"new duty"})
            digest = obligations_digest(archive)
            self.assertEqual(digest["open"], len(open_ids))

    def test_review_obligations_agrees_too(self) -> None:
        # S1: `checkpoint --review`'s reviewer - NS-10e's own use case
        # ("obligations a later handover made moot") - routed the same way.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append("obligation", "old duty", {"status": "open", "value": "v1"})
            archive.append(
                "obligation", "new duty",
                {"status": "open", "value": "v2", "supersedes": first["sequence"]})
            report = godmode_obligations.review_obligations(archive.read_events())
            obligations_seen = report["obligations_seen"]
            self.assertEqual(obligations_seen, 1)


class LatestBySubjectRuleTests(unittest.TestCase):
    """The helper's rule in isolation, no archive involved."""

    def test_superseded_record_never_latest_even_past_a_later_untagged_one(self) -> None:
        # A(seq 3) is superseded by C(seq 9, supersedes=3). B(seq 7) sits
        # on the SAME subject with no edge at all, chronologically between
        # them. Naive "highest sequence per subject" already lands on C
        # here (9 > 7 > 3) - the rule this test actually pins is narrower
        # and sharper: A must never win even when the record that
        # excludes it (C) is temporarily removed from view, i.e. A's own
        # exclusion does not depend on C being the survivor - it depends
        # only on A having been named.
        records = [
            {"kind": "decision", "subject": "x", "sequence": 3, "data": {"value": "a"}},
            {"kind": "decision", "subject": "x", "sequence": 7, "data": {"value": "b"}},
        ]
        # Without C on record, B (7) is latest - the base case.
        latest = latest_by_subject(records)
        self.assertEqual(latest["x"]["sequence"], 7)
        # C explicitly supersedes A (3), not B. A must drop out; B (7,
        # chronologically BETWEEN A and C, no edge of its own) is still a
        # candidate and, being the highest remaining sequence, still wins
        # over the excluded A - proving exclusion is per-record, not
        # "whatever the superseding record's own subject fold picks".
        with_c = records + [
            {"kind": "decision", "subject": "x", "sequence": 9, "data": {"value": "c", "supersedes": 3}},
        ]
        latest2 = latest_by_subject(with_c)
        self.assertEqual(latest2["x"]["sequence"], 9)
        self.assertIn(3, superseded_sequences(with_c))
        self.assertNotIn(7, superseded_sequences(with_c))

    def test_superseded_record_is_the_highest_on_its_own_key(self) -> None:
        # S4: the case that actually distinguishes the rule from naive
        # "highest sequence per key wins". C (seq 5) IS the highest
        # sequence on key "x" - no rule at all already lands on it. D
        # (seq 9, key "y", a DIFFERENT key) supersedes it anyway. The
        # LOWER surviving record on key "x" (A, seq 1) must become
        # latest for "x" - proving the exclusion fires even when the
        # excluded record was never merely "beaten to the punch" by a
        # later record on its own key.
        records = [
            {"kind": "decision", "subject": "x", "sequence": 1, "data": {"value": "a"}},
            {"kind": "decision", "subject": "x", "sequence": 5, "data": {"value": "c"}},
            {"kind": "decision", "subject": "y", "sequence": 9,
             "data": {"value": "d", "supersedes": 5}},
        ]
        latest = latest_by_subject(records)
        self.assertEqual(latest["x"]["sequence"], 1)
        self.assertNotIn(5, {r["sequence"] for r in latest.values()})

    def test_supersession_crosses_keys(self) -> None:
        # The record naming the successor carries a DIFFERENT key
        # (subject) from what it supersedes - a plain per-key fold could
        # never see this link; the helper still excludes the old one.
        records = [
            {"kind": "request", "subject": "ask:aaa", "sequence": 1, "data": {"digest": "aaa"}},
            {"kind": "request", "subject": "ask:bbb", "sequence": 2,
             "data": {"digest": "bbb", "supersedes": 1}},
        ]
        latest = latest_by_subject(records, key=lambda r: str(r["data"]["digest"]))
        self.assertEqual(set(latest), {"bbb"})

    def test_combine_composes_instead_of_replacing(self) -> None:
        calls: list[tuple[object, object]] = []

        def combine(current, record):
            calls.append((current, record))
            return record

        records = [
            {"kind": "obligation", "subject": "o", "sequence": 1, "data": {"status": "open"}},
            {"kind": "obligation", "subject": "o", "sequence": 2, "data": {"status": "open"}},
        ]
        latest_by_subject(records, combine=combine)
        self.assertEqual(len(calls), 2)


class ReaderFollowsEdgeTests(unittest.TestCase):
    """One test per enumerated latest-per-subject reader."""

    def test_open_stated_requests(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "request", "ask:one",
                {"digest": "digest-one", "status": "open", "source": "stated",
                 "keywords": ["one"]})
            archive.append(
                "request", "ask:two",
                {"digest": "digest-two", "status": "open", "source": "stated",
                 "keywords": ["two"], "supersedes": first["sequence"]})
            records, _ = godmode_requests.read_request_window(archive)
            opened = godmode_requests.open_stated_requests(records)
            subjects = {r["subject"] for r in opened}
            self.assertIn("ask:two", subjects)
            self.assertNotIn("ask:one", subjects)

    def test_status_remaining_latest_obligation(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("obligation", "keep tests green", {"status": "open", "value": "v"})
            archive.append(
                "obligation", "different words, same duty",
                {"status": "open", "value": "v2", "supersedes": first["sequence"]})
            report = godmode_status.remaining(archive, project)
            ids = {e["id"] for e in report["remaining"] if e["source"] == "obligation"}
            self.assertIn("different words, same duty", ids)
            self.assertNotIn("keep tests green", ids)

    def test_status_remaining_latest_claim(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = "s1"
            first = archive.append(
                "claim", "c1", {"session": session, "downgraded": True, "reason": "unsupported"})
            archive.append(
                "claim", "c2",
                {"session": session, "downgraded": True, "reason": "unsupported",
                 "supersedes": first["sequence"]})
            report = godmode_status.remaining(archive, project, session=session)
            ids = [e["id"] for e in report["remaining"] if e["source"] == "claim"]
            self.assertIn("c2", ids)
            self.assertNotIn("c1", ids)

    def test_iteration_open_scope_latest_obligation(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "obligation", "temporary:stash", {"status": "open", "value": "v"})
            archive.append(
                "obligation", "temporary:stash-renamed",
                {"status": "open", "value": "v2", "supersedes": first["sequence"]})
            scope = godmode_iteration.open_scope(archive, None)
            joined = " ".join(scope["temporaries"])
            self.assertIn("temporary:stash-renamed", joined)
            self.assertNotIn("temporary:stash ", joined)

    def test_hygiene_lesson_dedup(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "lesson", "verify before claiming done",
                {"value": "run the suite before saying the work is done", "status": "active"})
            archive.append(
                "lesson", "run the suite before done",
                {"value": "verify by running the suite before claiming the work is done",
                 "status": "active", "supersedes": first["sequence"]})
            records = archive.read_events()
            report = godmode_hygiene.hygiene(records)
            self.assertEqual(report["considered"]["lesson"], 1)

    def test_list_patterns(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "pattern", "flaky-import",
                {"workaround": "retry", "class": "test-fabrication", "occurrences": [1]})
            # A pattern cannot be superseded through the CLI (refused
            # above), but the read-time rule is generic: a raw archive
            # write (a hand-edited or pre-CLI record) still marks its
            # target excluded, exactly as `superseded_sequences`'s own
            # docstring says it must.
            archive.append(
                "pattern", "flaky-import-merged",
                {"workaround": "retry with backoff", "class": "test-fabrication",
                 "occurrences": [1], "supersedes": first["sequence"]})
            rows = godmode_mistakes.list_patterns(archive)
            subjects = {row["subject"] for row in rows}
            self.assertIn("flaky-import-merged", subjects)
            self.assertNotIn("flaky-import", subjects)

    def test_lesson_pipeline(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append(
                "lesson", "escape shell args",
                {"value": "v1", "generalized_guard": "every exec"},
                evidence=["file:run.py"])
            archive.append(
                "lesson", "escape shell args, reworded",
                {"value": "v2", "generalized_guard": "every exec call",
                 "supersedes": first["sequence"]},
                evidence=["file:run.py"])
            report = lesson_pipeline(archive)
            subjects = {l["subject"] for l in report["lessons"]}
            self.assertIn("escape shell args, reworded", subjects)
            self.assertNotIn("escape shell args", subjects)
            self.assertEqual(len(report["lessons"]), 1)


class SupersededStandingLessonTests(unittest.TestCase):
    """godmode_law.py is out of bounds for this task; this proves the
    shared helper already treats a superseded standing/enforce lesson as
    no longer latest, which is what any reader (godmode_law included)
    gets for free by routing through it."""

    def test_superseded_standing_lesson_is_not_latest(self) -> None:
        records = [
            {"kind": "lesson", "subject": "never commit secrets", "sequence": 4,
             "data": {"value": "v1", "generalized_guard": "scan before commit",
                       "standing": True, "status": "active"}},
            {"kind": "lesson", "subject": "never commit secrets v2", "sequence": 11,
             "data": {"value": "v2", "generalized_guard": "scan every write, not just commit",
                       "standing": True, "status": "active", "supersedes": 4}},
        ]
        latest = latest_by_subject(records)
        sequences = {r["sequence"] for r in latest.values()}
        self.assertIn(11, sequences)
        self.assertNotIn(4, sequences)


class HistoryChainRenderTests(unittest.TestCase):
    def test_history_subject_renders_chain(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "d", {"value": "v1", "status": "active"})
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "d",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertEqual(code, 0)
            second_seq = payload["record"]["sequence"]
            code, history = _run(project, "history", "--kind", "decision", "--subject", "d")
            self.assertEqual(code, 0)
            self.assertIn("chain", history)
            self.assertEqual(history["chain"], [f"{first['sequence']} → {second_seq}"])

    def test_history_subject_with_no_supersession_has_no_chain(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("decision", "d", {"value": "v1", "status": "active"})
            code, history = _run(project, "history", "--kind", "decision", "--subject", "d")
            self.assertEqual(code, 0)
            self.assertNotIn("chain", history)

    def test_history_subject_renders_the_cross_subject_chain(self) -> None:
        # B3: the design's own motivating case - "a lesson restated under a
        # new subject" (chronicle.py's docstring) - has its successor
        # OUTSIDE the queried `--subject`'s selection by definition.
        # `history --subject old-name` must still show it, with the
        # successor's own subject named since it differs.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "old-name", {"value": "v1", "status": "active"})
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "new-name",
                "--value", "v2", "--supersedes", str(first["sequence"]))
            self.assertEqual(code, 0, payload)
            second_seq = payload["record"]["sequence"]
            code, history = _run(project, "history", "--kind", "decision", "--subject", "old-name")
            self.assertEqual(code, 0, history)
            self.assertIn("chain", history)
            self.assertEqual(
                history["chain"], [f"{first['sequence']} → {second_seq} (new-name)"])
            # And the returned records themselves are still exactly the
            # queried subject's own history - the cross-subject successor
            # is resolved for the CHAIN, never smuggled into `records`.
            self.assertEqual({r["subject"] for r in history["records"]}, {"old-name"})


class GraphSupersessionEdgeTests(unittest.TestCase):
    def test_generic_supersedes_edge_derived(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append("obligation", "o", {"status": "open", "value": "v1"})
            second = archive.append(
                "obligation", "o2", {"status": "open", "value": "v2", "supersedes": first["sequence"]})
            built = graph.rebuild(archive)
            edges = [e for e in built["edges"] if e["type"] == graph.SUPERSEDES]
            self.assertTrue(any(
                e["src"] == f"obligation:{second['sequence']}"
                and e["dst"] == f"obligation:{first['sequence']}"
                for e in edges), edges)

    def test_no_supersedes_edge_when_the_field_is_absent(self) -> None:
        # Nit (fix round 1): the old name claimed a byte-for-byte
        # comparison against pre-change bytes this test never took: it
        # rebuilds twice against CURRENT code both times. What it actually
        # proves - and the only assertion that earns a claim - is the
        # empty `SUPERSEDES` edge list below: the generic branch adds
        # nothing when no record carries `supersedes` at all.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("obligation", "c", {"status": "open", "blocked_by": []})
            archive.append("obligation", "b", {"status": "open", "blocked_by": ["c"]})
            first = graph.rebuild(archive)
            second = graph.rebuild(archive)
            self.assertEqual(first["hash"], second["hash"])
            self.assertEqual(
                [e for e in first["edges"] if e["type"] == graph.SUPERSEDES], [])

    def test_rebuild_idempotent_with_generic_edge(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "reworded-idea", {"value": "v1", "status": "active"})
            archive.append(
                "decision", "reworded-idea-2",
                {"value": "v2", "status": "active", "supersedes": first["sequence"]})
            built_a = graph.rebuild(archive)
            built_b = graph.rebuild(archive)
            self.assertEqual(built_a["hash"], built_b["hash"])
            self.assertEqual(built_a, built_b)


if __name__ == "__main__":
    unittest.main()
