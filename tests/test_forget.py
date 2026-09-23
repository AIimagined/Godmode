"""NS-11e + NS-11g: the forgetting engine and its cold tier (0.3.28 Plan 5
Task 7).

`godmode forget` runs three operations together: expire (episodic kinds
past a per-kind TTL rotate out of the hot tier into a still hash-chained
cold segment; pins are exempt), supersede (a read-only report of every
supersession chain, through `superseded_sequences` alone - NS-10e), and
flag contradictions (two or more active records on one subject whose
`value` disagree get a single `review` record).

Every test that cares about age passes an explicit `now` - never a
wall-clock assertion. Records that must read as "old" are appended with a
frozen clock (`_append_at`), never mutated in place afterward: the record
is sealed normally, under a clock this test controls, so its own
`record_hash` is exactly what a real record written at that moment would
have carried - no hand re-derived hash anywhere in this file.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
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
from godmode_runtime import godmode_chronicle  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from godmode_runtime import godmode_forget as forget_mod  # noqa: E402


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


def _append_at(archive: Chronicle, kind: str, subject: str, data: dict, when: datetime, **kwargs):
    """Append a record whose `recorded_at` is fabricated as `when`, by
    freezing `godmode_chronicle`'s own `datetime.now()` for exactly this
    one call. The record is sealed through the real `append()` path, so
    its `record_hash`/chain link are exactly what a record actually
    written at `when` would carry."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102 - matches datetime.now's own signature
            return when.astimezone(tz) if tz is not None else when

    with mock.patch("godmode_runtime.godmode_chronicle.datetime", _Frozen):
        return archive.append(kind, subject, data, **kwargs)


def _run_refusal(project: Path, *argv: str) -> tuple[int, dict]:
    """`_run` for a call expected to REFUSE: the console renders a refusal on
    stderr, so a stdout-only capture reads it as an empty payload."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = console_main(["--project", str(project), "--json", *argv])
    text = (out.getvalue().strip() or err.getvalue().strip())
    return code, (json.loads(text) if text else {})


@contextlib.contextmanager
def deep_isolated_project():
    """`isolated_project` with a state home deep enough that a record file's
    own path runs past MAX_PATH (fix round 2, R2-B1).

    The archive ROOT stays inside the limit - `initialize()` creates it with a
    plain `mkdir` - while the fixed-width record name underneath it
    (`godmode-events/<12-digit seq>-<32 hex>.godmode.json`, ~74 characters)
    pushes the file itself past 260. That is exactly the shape an operator's
    own `GODMODE_STATE_HOME` produces on Windows, and the shape in which
    `Path.unlink` silently does nothing.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        state = base / ("d" * 60) / ("e" * 60)
        os.makedirs(state, exist_ok=True)
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


def _run_text(project: Path, *argv: str) -> tuple[int, str]:
    """The same in-process CLI drive as `_run`, in a text profile - `--terse`
    is the surface review B's B2 was about, and only the rendered text can
    show whether it names the next step."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = console_main(["--project", str(project), "--terse", *argv])
    return code, out.getvalue()


def _hot_path_for(archive: Chronicle, sequence: int) -> Path | None:
    prefix = f"{sequence:012d}-"
    for path in archive.event_paths():
        if path.name.startswith(prefix):
            return path
    return None


NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
OLD_ACTION = NOW - timedelta(days=forget_mod.TTL_DAYS["action"] + 1)
FRESH_ACTION = NOW - timedelta(days=1)


class EligibilityTests(unittest.TestCase):
    """`eligible_for_expiry`/`age_days`: pure functions of `now`, no wall clock."""

    def test_episodic_kind_past_ttl_is_eligible(self) -> None:
        record = {"kind": "action", "recorded_at": OLD_ACTION.isoformat(), "sequence": 1}
        # The newest record always stays hot (review A, N4), so the fixture
        # carries the tail the next append would link from.
        tail = {"kind": "decision", "recorded_at": NOW.isoformat(), "sequence": 2}
        self.assertEqual(forget_mod.eligible_for_expiry([record, tail], now=NOW), [record])

    def test_the_newest_record_is_never_eligible(self) -> None:
        record = {"kind": "action", "recorded_at": OLD_ACTION.isoformat(), "sequence": 1}
        self.assertEqual(forget_mod.eligible_for_expiry([record], now=NOW), [])

    def test_episodic_kind_within_ttl_is_not_eligible(self) -> None:
        record = {"kind": "action", "recorded_at": FRESH_ACTION.isoformat(), "sequence": 1}
        self.assertEqual(forget_mod.eligible_for_expiry([record], now=NOW), [])

    def test_non_episodic_kind_is_never_eligible_no_matter_how_old(self) -> None:
        record = {"kind": "decision", "recorded_at": (NOW - timedelta(days=9999)).isoformat(),
                  "sequence": 1}
        self.assertEqual(forget_mod.eligible_for_expiry([record], now=NOW), [])

    def test_pin_kind_is_never_eligible_no_matter_how_old(self) -> None:
        record = {"kind": "pin", "recorded_at": (NOW - timedelta(days=9999)).isoformat(),
                  "sequence": 1}
        self.assertEqual(forget_mod.eligible_for_expiry([record], now=NOW), [])

    def test_missing_recorded_at_is_never_eligible(self) -> None:
        record = {"kind": "action", "sequence": 1}
        self.assertEqual(forget_mod.eligible_for_expiry([record], now=NOW), [])


class ExpireOperationTests(unittest.TestCase):
    def test_expire_rotates_old_episodic_records_and_leaves_fresh_ones_hot(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            old = _append_at(archive, "action", "old-action", {"summary": "x"}, OLD_ACTION)
            fresh = _append_at(archive, "action", "fresh-action", {"summary": "y"}, FRESH_ACTION)
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [old["sequence"]])
            self.assertTrue(report["expire"]["rotated"])
            self.assertTrue((archive.root / report["expire"]["segment"]).is_file())
            self.assertIsNone(_hot_path_for(archive, old["sequence"]))
            self.assertIsNotNone(_hot_path_for(archive, fresh["sequence"]))
            self.assertTrue(archive.verify()["ok"])

    def test_dry_run_expire_writes_nothing(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old-action", {"summary": "x"}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            before = forget_mod.archive_digest(archive.root)
            report = forget_mod.forget(archive, now=NOW.isoformat(), dry_run=True)
            after = forget_mod.archive_digest(archive.root)
            self.assertEqual(before, after)
            self.assertTrue(report["digest_unchanged"])
            self.assertEqual(report["expire"]["count"], 1)
            self.assertFalse(report["expire"]["rotated"])
            self.assertEqual(len(archive.event_paths()), 2)
            self.assertEqual(archive.cold_segment_paths(), [])

    def test_pins_are_exempt_from_expiry(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            pin = _append_at(
                archive, "pin", "some/file.py",
                {"action": "pin", "path": "some/file.py", "sha256": "a" * 64},
                OLD_ACTION,
            )
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertNotIn(pin["sequence"], report["expire"]["eligible"])
            self.assertFalse(report["expire"]["rotated"])
            self.assertIsNotNone(_hot_path_for(archive, pin["sequence"]))

    def test_rotating_a_pin_directly_is_refused(self) -> None:
        # Defense in depth (Chronicle.rotate_to_cold's own refusal), not
        # just "expire never selects one" - proven independently of
        # `godmode_forget`'s own kind filter.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            pin = archive.append(
                "pin", "some/file.py",
                {"action": "pin", "path": "some/file.py", "sha256": "b" * 64},
                evidence=[],
            )
            with self.assertRaises(Exception):
                archive.rotate_to_cold([pin["sequence"]])

    def test_cold_record_reachable_by_sequence_through_history(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            old = _append_at(archive, "refusal", "old-refusal", {"why": "z"}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            forget_mod.forget(archive, now=NOW.isoformat())
            code, payload = _run(project, "history", "--seq", str(old["sequence"]))
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["records"][0]["sequence"], old["sequence"])
            self.assertEqual(payload["records"][0]["kind"], "refusal")

    def test_verify_after_rotation_and_a_later_append_extends_correctly(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old-1", {}, OLD_ACTION)
            _append_at(archive, "action", "old-2", {}, OLD_ACTION)
            kept = archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertTrue(archive.verify()["ok"])
            # The pass records itself (review B, cadence), so the next
            # sequence follows THAT record, not `kept`.
            self.assertEqual(report["pass_recorded"], kept["sequence"] + 1)
            newest = archive.append("decision", "after-rotation", {"value": "n"}, evidence=[])
            self.assertEqual(newest["sequence"], report["pass_recorded"] + 1)
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])

    def test_scattered_rotation_still_verifies_hot_and_cold(self) -> None:
        # Eligible sequences interleaved with kinds `expire` never touches -
        # the realistic shape, not a clean prefix.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = _append_at(archive, "action", "old-1", {}, OLD_ACTION)
            archive.append("decision", "kept-1", {"value": 1}, evidence=[])
            third = _append_at(archive, "refusal", "old-2", {}, OLD_ACTION)
            archive.append("decision", "kept-2", {"value": 2}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [first["sequence"], third["sequence"]])
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])

    def test_tamper_in_a_cold_segment_is_detected(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {"summary": "distinctive-marker"}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            segment = Path(archive.root) / report["expire"]["segment"]
            text = segment.read_text(encoding="utf-8")
            tampered = text.replace("distinctive-marker", "tampered-value!")
            self.assertNotEqual(text, tampered)
            segment.write_text(tampered, encoding="utf-8")
            outcome = archive.verify_cold()
            self.assertFalse(outcome["ok"])
            self.assertIn("tampered", outcome["message"])


class SupersedeOperationTests(unittest.TestCase):
    def test_supersede_reports_the_chain_and_writes_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, _payload = _run(project, "remember", "--kind", "decision",
                                  "--subject", "storage", "--value", "local")
            self.assertEqual(code, 0)
            code, _payload = _run(project, "remember", "--kind", "decision",
                                  "--subject", "storage-v2", "--value", "cloud",
                                  "--supersedes", "1")
            self.assertEqual(code, 0)
            # Fix round 1: a real PASS now records itself (one `action` /
            # `forget-pass` record - review B's cadence finding), so the
            # digest assertion is aimed at the supersede operation itself,
            # which is the thing that must write nothing.
            before = forget_mod.archive_digest(archive.root)
            chains = forget_mod._supersede_report(archive.read_events())
            after = forget_mod.archive_digest(archive.root)
            self.assertEqual(before, after, "supersede must write nothing")
            self.assertEqual(
                chains["chains"], [{"from": 1, "to": 2, "subject": "storage-v2"}])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(
                report["supersede"]["chains"],
                [{"from": 1, "to": 2, "subject": "storage-v2"}],
            )


class ContradictionOperationTests(unittest.TestCase):
    def test_conflicting_active_decisions_flag_a_review_record(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "postgres")
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "sqlite")
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["contradictions"]["count"], 1)
            flagged = report["contradictions"]["flagged"][0]
            self.assertEqual(flagged["kind"], "decision")
            self.assertEqual(flagged["sequences"], [1, 2])
            self.assertEqual(len(report["contradictions"]["written"]), 1)
            review_seq = report["contradictions"]["written"][0]
            review = archive.find_by_sequence(review_seq)
            self.assertEqual(review["kind"], "review")
            self.assertEqual(sorted(review["data"]["sequences"]), [1, 2])
            self.assertEqual(review["data"]["kind"], "decision")

    def test_contradiction_is_flagged_once_idempotent_on_rerun(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "postgres")
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "sqlite")
            first = forget_mod.forget(archive, now=NOW.isoformat())
            review_seq = first["contradictions"]["written"][0]

            def _reviews() -> list[int]:
                return [int(r["sequence"]) for r in archive.read_events()
                        if r.get("kind") == "review"]

            self.assertEqual(_reviews(), [review_seq])
            second = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(_reviews(), [review_seq],
                             "re-running forget must not write a second review record")
            # Fix round 1 (review B, B4): the finding is still REPORTED, with
            # the status of the review already on record - it is simply not
            # written a second time.
            self.assertEqual(second["contradictions"]["written"], [])
            self.assertEqual(second["contradictions"]["flagged"][0]["status"], "open")

    def test_agreeing_active_decisions_are_not_flagged(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "postgres")
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "postgres")
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["contradictions"]["count"], 0)
            self.assertEqual(report["contradictions"]["written"], [])

    def test_a_superseded_decision_is_excluded_from_contradiction(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "postgres")
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "sqlite",
                "--supersedes", "1")
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["contradictions"]["count"], 0)

    def test_dry_run_reports_but_does_not_write_the_review(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "postgres")
            _run(project, "remember", "--kind", "decision", "--subject", "db", "--value", "sqlite")
            report = forget_mod.forget(archive, now=NOW.isoformat(), dry_run=True)
            self.assertEqual(report["contradictions"]["count"], 1)
            self.assertEqual(report["contradictions"]["written"], [])
            self.assertEqual(len(archive.read_events()), 2)


class DryRunDigestTests(unittest.TestCase):
    def test_digest_ignores_disposable_read_caches(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "x", {"value": 1}, evidence=[])
            before = forget_mod.archive_digest(archive.root)
            archive.verify()  # may (re)write head/checkpoint-registry/index sidecars
            after = forget_mod.archive_digest(archive.root)
            self.assertEqual(before, after)

    def test_digest_changes_after_a_real_write(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            before = forget_mod.archive_digest(archive.root)
            archive.append("decision", "x", {"value": 1}, evidence=[])
            after = forget_mod.archive_digest(archive.root)
            self.assertNotEqual(before, after)


class RecurringRegistrationTests(unittest.TestCase):
    def test_recurring_says_so_when_no_pass_is_on_record(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "x", {"value": 1}, evidence=[])
            code, payload = _run(project, "recurring")
            self.assertEqual(code, 0, payload)
            self.assertIsNone(payload["forget_due"]["last_pass"])
            self.assertIn("no `godmode forget` pass is on record",
                          payload["forget_due"]["detail"])

    def test_recurring_reads_the_recorded_pass_and_never_runs_one(self) -> None:
        # Fix round 1 (review A, B8): `recurring` used to call
        # `forget(..., dry_run=True)` on every invocation - a full verified
        # archive read plus two digest sweeps, measured at 20-35 s on this
        # project's own archive. It now reads the record a real pass leaves
        # behind, and the proof is that it never touches `forget` at all.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            ancient = datetime.now(timezone.utc) - timedelta(
                days=forget_mod.TTL_DAYS["action"] + 3650)
            _append_at(archive, "action", "old", {}, ancient)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive)
            self.assertEqual(report["expire"]["count"], 1)
            with mock.patch.object(forget_mod, "forget",
                                   side_effect=AssertionError("recurring ran a forget pass")):
                code, payload = _run(project, "recurring")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["forget_due"]["last_pass_seq"],
                             report["pass_recorded"])
            self.assertEqual(payload["forget_due"]["expired"], 1)

    def test_recurring_json_omits_prose_report(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run(project, "recurring")
            self.assertEqual(code, 0, payload)
            self.assertNotIn("report", payload)


class CLIWiringTests(unittest.TestCase):
    def test_forget_is_a_registered_verb(self) -> None:
        from godmode_runtime.godmode_console import _build_parser
        parser = _build_parser()
        verbs = {
            name
            for action in parser._actions  # noqa: SLF001
            for name in getattr(action, "choices", None) or []
        }
        self.assertIn("forget", verbs)

    def test_cli_dry_run_and_now_round_trip(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            code, payload = _run(project, "forget", "--dry-run", "--now", NOW.isoformat())
            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["expire"]["count"], 1)
            self.assertTrue(payload["digest_unchanged"])
            self.assertEqual(len(archive.event_paths()), 2)

    def test_cli_real_run_rotates(self) -> None:
        # No `--now`: a write pass reads the real clock (review A, B5), so the
        # fixture is manufactured old relative to whenever this suite runs.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            ancient = datetime.now(timezone.utc) - timedelta(
                days=forget_mod.TTL_DAYS["action"] + 3650)
            _append_at(archive, "action", "old", {}, ancient)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            code, payload = _run(project, "forget")
            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["expire"]["rotated"])
            self.assertEqual(len(archive.cold_segment_paths()), 1)
            self.assertIsNone(_hot_path_for(archive, 1))
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])


# ---------------------------------------------------------------------------
# Fix round 1. Every test below fails on 4a57784 (the commit the two reviews
# examined) and passes here; each names the finding it closes.
# ---------------------------------------------------------------------------


class TailCountRefusesAGapTests(unittest.TestCase):
    """Review A, B2 - the finding that reaches an archive with no cold tier."""

    def test_a_record_file_deleted_from_the_middle_refuses_the_next_append(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(5):
                archive.append("decision", f"d{index}", {"value": index}, evidence=[])
            victim = _hot_path_for(archive, 3)
            self.assertIsNotNone(victim)
            victim.unlink()
            # No cold tier anywhere near this: a plain filesystem deletion.
            self.assertEqual(archive.cold_segment_paths(), [])
            self.assertIsNone(archive._read_cold_registry())  # noqa: SLF001
            with self.assertRaises(GodmodeError) as caught:
                archive.append("decision", "after-the-hole", {"value": "x"}, evidence=[])
            self.assertIn("not contiguous", str(caught.exception))
            # And the archive still says so on a read, rather than having been
            # extended past the break.
            self.assertFalse(archive.verify(archive.read_events(verify=False))["ok"])

    def test_the_fast_path_still_works_across_a_legitimate_rotation(self) -> None:
        # The other half of B2: the guard must not refuse the gap a rotation
        # legitimately creates.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old-1", {}, OLD_ACTION)
            _append_at(archive, "action", "old-2", {}, OLD_ACTION)
            kept = archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [1, 2])
            newest = archive.append("decision", "after", {"value": "n"}, evidence=[])
            self.assertEqual(newest["sequence"], report["pass_recorded"] + 1)
            self.assertGreater(newest["sequence"], kept["sequence"])
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])


class TheTailStaysHotTests(unittest.TestCase):
    """Review A, N4 - the invariant the docstring asserted and nothing enforced."""

    def test_the_newest_record_is_never_eligible_however_old_it_is(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = _append_at(archive, "action", "old-1", {}, OLD_ACTION)
            tail = _append_at(archive, "action", "old-2", {}, OLD_ACTION)
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [first["sequence"]])
            self.assertIsNotNone(_hot_path_for(archive, tail["sequence"]))

    def test_rotating_the_tail_directly_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "a", {"value": 1}, evidence=[])
            tail = archive.append("decision", "b", {"value": 2}, evidence=[])
            with self.assertRaises(GodmodeError) as caught:
                archive.rotate_to_cold([tail["sequence"]])
            self.assertIn("newest record", str(caught.exception))

    def test_the_append_after_a_rotation_never_reuses_a_sequence(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(3):
                _append_at(archive, "action", f"old-{index}", {}, OLD_ACTION)
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [1, 2])
            newest = archive.append("decision", "after", {"value": "n"}, evidence=[])
            self.assertEqual(newest["sequence"], report["pass_recorded"] + 1)
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])


class ColdTierVerifiesItselfTests(unittest.TestCase):
    """Review A, B1 - `verify_cold()` walks the segments, not the registry."""

    def _rotate_two(self, archive: Chronicle) -> dict:
        _append_at(archive, "action", "old-1", {"summary": "one"}, OLD_ACTION)
        _append_at(archive, "action", "old-2", {"summary": "two"}, OLD_ACTION)
        archive.append("decision", "kept", {"value": "k"}, evidence=[])
        return forget_mod.forget(archive, now=NOW.isoformat())

    def test_a_deleted_segment_with_a_doctored_registry_is_caught(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            report = self._rotate_two(archive)
            (archive.root / report["expire"]["segment"]).unlink()
            payload = json.loads(archive.cold_registry.read_text(encoding="utf-8"))
            payload["segments"] = []  # `rotated`/`hash_by_sequence` left intact
            archive.cold_registry.write_text(json.dumps(payload), encoding="utf-8")
            outcome = archive.verify_cold()
            self.assertFalse(outcome["ok"], outcome)
            self.assertIn("rotated but in no segment", outcome["message"])

    def test_a_dropped_line_with_a_refreshed_digest_is_caught(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            report = self._rotate_two(archive)
            segment = archive.root / report["expire"]["segment"]
            lines = [line for line in segment.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(lines), 2)
            text = lines[0] + "\n"          # the second record simply disappears
            segment.write_text(text, encoding="utf-8")
            payload = json.loads(archive.cold_registry.read_text(encoding="utf-8"))
            payload["segments"][0]["sha256"] = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            archive.cold_registry.write_text(json.dumps(payload), encoding="utf-8")
            outcome = archive.verify_cold()
            self.assertFalse(outcome["ok"], outcome)
            self.assertIn("holds sequence(s)", outcome["message"])

    def test_an_intact_cold_tier_still_verifies(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self._rotate_two(archive)
            outcome = archive.verify_cold()
            self.assertTrue(outcome["ok"], outcome.get("message"))


class RotationResumesAfterACrashTests(unittest.TestCase):
    """Review A, B3 - the window between the registry write and the unlinks."""

    @staticmethod
    def _unlink_raises():
        # The rotation's delete goes through `os.remove(_syscall_path(path))`
        # (fix round 2, R2-B1), so the crash is simulated there rather than on
        # `Path.unlink`; every other removal in the same call must still work.
        original = os.remove

        def _boom(target, *args, **kwargs):
            text = str(target)
            if text.endswith(".godmode.json") and "godmode-events" in text:
                raise OSError("simulated crash between the registry write and the unlink")
            return original(target, *args, **kwargs)

        return mock.patch.object(godmode_chronicle.os, "remove", _boom)

    def test_a_crash_before_the_unlink_resumes_on_the_next_pass(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old-1", {}, OLD_ACTION)
            _append_at(archive, "action", "old-2", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            with self._unlink_raises():
                with self.assertRaises(GodmodeError) as caught:
                    forget_mod.forget(archive, now=NOW.isoformat())
            self.assertIn("Cannot remove the hot record file", str(caught.exception))
            # The half-finished state: registered cold, still hot.
            registry = archive._read_cold_registry()  # noqa: SLF001
            self.assertEqual(registry["rotated"], [1, 2])
            self.assertIsNotNone(_hot_path_for(archive, 1))
            # Neither verifier cries tamper on an archive whose chain is intact.
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"], archive.verify_cold())
            # And the next pass finishes the job instead of refusing forever.
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [1, 2])
            self.assertEqual(report["expire"]["resumed"], [1, 2])
            self.assertIsNone(_hot_path_for(archive, 1))
            self.assertIsNone(_hot_path_for(archive, 2))
            self.assertEqual(len(archive.cold_segment_paths()), 1,
                             "a resume must not write a second segment")
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])

    def test_a_sequence_that_is_cold_and_gone_is_still_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            forget_mod.forget(archive, now=NOW.isoformat())
            with self.assertRaises(GodmodeError) as caught:
                archive.rotate_to_cold([1])
            self.assertIn("already in the cold tier", str(caught.exception))


class ColdReadIsVerifiedTests(unittest.TestCase):
    """Review A, B4 - `history --seq` must not serve a rewritten record."""

    def test_history_seq_refuses_a_forged_cold_record(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "refusal", "old", {"why": "honest"}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            segment = archive.root / report["expire"]["segment"]
            record = json.loads(segment.read_text(encoding="utf-8").splitlines()[0])
            record["data"] = {"why": "FORGED - rewritten in the cold segment"}
            text = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            segment.write_text(text, encoding="utf-8")
            # The segment's own digest is refreshed too, so only the record's
            # content hash is left to catch this.
            payload = json.loads(archive.cold_registry.read_text(encoding="utf-8"))
            payload["segments"][0]["sha256"] = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            archive.cold_registry.write_text(json.dumps(payload), encoding="utf-8")
            code, served = _run_refusal(project, "history", "--seq", "1")
            self.assertNotEqual(code, 0, served)
            self.assertIn("no longer matches its own content hash", served["message"])
            self.assertIn("godmode doctor", served["message"])

    def test_history_seq_refuses_a_filter_it_would_have_ignored(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            code, payload = _run_refusal(project, "history", "--seq", "1", "--kind", "action")
            self.assertNotEqual(code, 0, payload)
            self.assertIn("--kind", payload["message"])


class CheckpointAcceleratorSurvivesRotationTests(unittest.TestCase):
    """Review A, B7 - one position convention, and a registry that rebuilds."""

    def test_a_rotation_does_not_kill_the_verified_checkpoint_accelerator(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(4):
                _append_at(archive, "action", f"old-{index}", {}, OLD_ACTION)
            for index in range(10):
                archive.append("decision", f"before-{index}", {"value": index}, evidence=[])
            archive.append("checkpoint", "mid", {"status": "progress"})
            for index in range(2):
                archive.append("decision", f"after-{index}", {"value": index}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [1, 2, 3, 4])
            # One forced full walk - what `godmode doctor` does - is what
            # registers a checkpoint. Before this fix it could never register
            # one again after a rotation, so every later read walked from 0.
            records = archive.read_events(verify=False)
            walk = archive.verify(records, trusted_prefix=0, use_checkpoint=False)
            self.assertTrue(walk["ok"], walk.get("message"))
            self.assertTrue(archive.checkpoint_registry.is_file(),
                            "the post-rotation full walk registered no checkpoint")
            boundary = archive._checkpoint_boundary(records)  # noqa: SLF001
            self.assertIsNotNone(
                boundary, "a rotation must not cost the archive its read accelerator")
            with mock.patch.object(godmode_chronicle, "_record_hash",
                                   wraps=godmode_chronicle._record_hash) as hashed:
                result = archive.verify(records, trusted_prefix=0)
            self.assertTrue(result["ok"], result.get("message"))
            self.assertLessEqual(hashed.call_count, 5)
            self.assertLess(hashed.call_count, len(records))


class CitedRecordsSurviveTests(unittest.TestCase):
    """Review A, B6 - the exemption set that actually exists."""

    OLD_ATTESTATION = NOW - timedelta(days=forget_mod.TTL_DAYS["attestation"] + 1)

    def test_an_attestation_cited_by_a_live_claim_survives_forget(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            witnessed = _append_at(archive, "attestation", "the step ran",
                                   {"rule": "R-1"}, self.OLD_ATTESTATION)
            archive.append("claim", "the step ran", {"text": "the step ran",
                                                     "grade": "observed"},
                           evidence=[f"seq:{witnessed['sequence']}"])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertNotIn(witnessed["sequence"], report["expire"]["eligible"])
            self.assertIsNotNone(_hot_path_for(archive, witnessed["sequence"]))
            self.assertIn(witnessed["sequence"],
                          forget_mod.protected_sequences(archive.read_events()))

    def test_the_same_attestation_expires_once_the_claim_is_settled(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            witnessed = _append_at(archive, "attestation", "the step ran",
                                   {"rule": "R-1"}, self.OLD_ATTESTATION)
            claim = archive.append("claim", "the step ran",
                                   {"text": "the step ran", "grade": "observed"},
                                   evidence=[f"seq:{witnessed['sequence']}"])
            archive.append("claim", "the step ran",
                           {"text": "the step ran", "resolves": claim["sequence"],
                            "outcome": "failed"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertIn(witnessed["sequence"], report["expire"]["eligible"])

    def test_a_pin_and_what_it_cites_are_both_protected(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            old = _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("pin", "some/file.py",
                           {"action": "pin", "path": "some/file.py", "sha256": "c" * 64},
                           evidence=[f"seq:{old['sequence']}"])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [])
            self.assertIsNotNone(_hot_path_for(archive, old["sequence"]))


class NowIsPreviewOnlyTests(unittest.TestCase):
    """Review A, B5 and review B, B1."""

    def test_now_on_a_write_pass_is_refused_with_a_remedy(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            code, payload = _run_refusal(project, "forget", "--now", "2999-01-01")
            self.assertNotEqual(code, 0, payload)
            self.assertIn("--dry-run", payload["message"])
            self.assertIsNotNone(_hot_path_for(archive, 1))
            self.assertEqual(archive.cold_segment_paths(), [])

    def test_now_with_a_dry_run_is_still_accepted(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            code, payload = _run(project, "forget", "--dry-run", "--now", "2999-01-01")
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["expire"]["count"], 1)

    def test_garbage_in_now_is_a_named_refusal_not_a_traceback(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run_refusal(project, "forget", "--dry-run", "--now", "not-a-date")
            self.assertNotEqual(code, 0, payload)
            self.assertIn("ISO-8601", payload["message"])
        with self.assertRaises(GodmodeError):
            forget_mod._parse_now("not-a-date")


class ReportNamesTheNextStepTests(unittest.TestCase):
    """Review B, B2 - `--terse` must not say "no findings" while holding some."""

    def test_terse_names_the_next_step(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            _run(project, "remember", "--kind", "decision", "--subject", "db",
                 "--value", "postgres")
            _run(project, "remember", "--kind", "decision", "--subject", "db",
                 "--value", "sqlite")
            code, text = _run_text(project, "forget", "--dry-run", "--now", NOW.isoformat())
            self.assertEqual(code, 0, text)
            self.assertIn("next: run `godmode forget`", text)
            self.assertNotIn("no findings reported", text)
            self.assertIn("past their kind's TTL", text)

    def test_terse_says_nothing_is_due_when_nothing_is(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            code, text = _run_text(project, "forget", "--dry-run", "--now", NOW.isoformat())
            self.assertEqual(code, 0, text)
            self.assertIn("nothing is due", text)


class ReviewRecordsCloseTests(unittest.TestCase):
    """Review B, B3 and B4 - a status vocabulary, and surfaces that read it."""

    def _flagged(self, project: Path, archive: Chronicle) -> dict:
        _run(project, "remember", "--kind", "decision", "--subject", "db",
             "--value", "postgres")
        _run(project, "remember", "--kind", "decision", "--subject", "db",
             "--value", "sqlite")
        return forget_mod.forget(archive, now=NOW.isoformat())

    def test_a_review_without_a_status_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(GodmodeError) as caught:
                archive.append("review", "db", {"kind": "decision", "sequences": [1, 2]},
                               evidence=[])
            self.assertIn("status", str(caught.exception))

    def test_a_review_with_an_invented_status_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(GodmodeError):
                archive.append("review", "db",
                               {"kind": "decision", "sequences": [1, 2], "status": "ignored"},
                               evidence=[])

    def test_an_acknowledged_contradiction_never_reopens(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            first = self._flagged(project, archive)
            self.assertEqual(len(first["contradictions"]["written"]), 1)
            code, payload = _run(project, "remember", "--kind", "review",
                                 "--subject", "db", "--status", "acknowledged")
            self.assertEqual(code, 0, payload)
            second = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(second["contradictions"]["written"], [])
            self.assertEqual(second["contradictions"]["flagged"][0]["status"],
                             "acknowledged")
            self.assertEqual(second["contradictions"]["open"], 0)
            self.assertEqual(
                godmode_chronicle.open_reviews(archive.read_events()), [])

    def test_open_reviews_surface_in_hygiene_status_and_the_brief(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            archive.initialize()
            self._flagged(project, archive)
            code, payload = _run(project, "hygiene")
            self.assertEqual(code, 0, payload)
            self.assertEqual([entry["subject"] for entry in payload["open_reviews"]],
                             ["db"])
            self.assertIn("review", payload["next"])

            from godmode_runtime.godmode_status import remaining
            left = remaining(archive, project)
            self.assertTrue(any(item["source"] == "review" and item["id"] == "db"
                                for item in left["remaining"]), left["remaining"])

            from godmode_runtime.godmode_lens import detect_context_issues
            issues = detect_context_issues(anchor, archive.read_events(), archive=archive)
            self.assertTrue(
                any(issue["code"] == "open-contradiction-review" for issue in issues),
                issues)

    def test_closing_a_review_that_does_not_exist_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run_refusal(project, "remember", "--kind", "review",
                                         "--subject", "nothing-here", "--status", "dismissed")
            self.assertNotEqual(code, 0, payload)
            self.assertIn("godmode forget", payload["message"])


class EveryOpenReviewIsClosableTests(unittest.TestCase):
    """Fix round 2, R2-B5 - one subject, two open reviews, both reachable."""

    def _two_open_reviews(self, project: Path, archive: Chronicle) -> list[dict]:
        _run(project, "remember", "--kind", "decision", "--subject", "t3", "--value", "A")
        _run(project, "remember", "--kind", "decision", "--subject", "t3", "--value", "B")
        forget_mod.forget(archive, now=NOW.isoformat())
        _run(project, "remember", "--kind", "decision", "--subject", "t3", "--value", "C")
        forget_mod.forget(archive, now=NOW.isoformat())
        reviews = godmode_chronicle.open_reviews(archive.read_events())
        self.assertEqual(len(reviews), 2, reviews)
        return reviews

    def test_the_older_open_review_is_closable_by_name(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            reviews = self._two_open_reviews(project, archive)
            older = min(reviews, key=lambda entry: entry["sequence"])
            code, payload = _run(project, "remember", "--kind", "review",
                                 "--subject", "t3", "--status", "acknowledged",
                                 "--review", f"seq:{older['sequence']}")
            self.assertEqual(code, 0, payload)
            left = godmode_chronicle.open_reviews(archive.read_events())
            self.assertEqual([entry["sequences"] for entry in left],
                             [max(reviews, key=lambda e: e["sequence"])["sequences"]])
            # And then the other one, so the drawer can actually be emptied.
            code, payload = _run(project, "remember", "--kind", "review",
                                 "--subject", "t3", "--status", "dismissed",
                                 "--review", f"seq:{left[0]['sequence']}")
            self.assertEqual(code, 0, payload)
            self.assertEqual(godmode_chronicle.open_reviews(archive.read_events()), [])
            code, payload = _run(project, "hygiene")
            self.assertEqual(payload["open_reviews"], [])

    def test_an_unnamed_close_with_two_open_refuses_and_lists_them(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            reviews = self._two_open_reviews(project, archive)
            code, payload = _run_refusal(project, "remember", "--kind", "review",
                                         "--subject", "t3", "--status", "acknowledged")
            self.assertNotEqual(code, 0, payload)
            for entry in reviews:
                self.assertIn(f"seq:{entry['sequence']}", payload["message"])
            self.assertIn("--review seq:", payload["message"])
            # The refusal wrote nothing: both are still open.
            self.assertEqual(len(godmode_chronicle.open_reviews(archive.read_events())), 2)

    def test_a_single_open_review_still_closes_without_naming_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "t1", "--value", "A")
            _run(project, "remember", "--kind", "decision", "--subject", "t1", "--value", "B")
            forget_mod.forget(archive, now=NOW.isoformat())
            code, payload = _run(project, "remember", "--kind", "review",
                                 "--subject", "t1", "--status", "acknowledged")
            self.assertEqual(code, 0, payload)
            self.assertEqual(godmode_chronicle.open_reviews(archive.read_events()), [])

    def test_naming_a_review_on_another_subject_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _run(project, "remember", "--kind", "decision", "--subject", "t1", "--value", "A")
            _run(project, "remember", "--kind", "decision", "--subject", "t1", "--value", "B")
            forget_mod.forget(archive, now=NOW.isoformat())
            opened = godmode_chronicle.open_reviews(archive.read_events())[0]
            code, payload = _run_refusal(project, "remember", "--kind", "review",
                                         "--subject", "somewhere-else",
                                         "--status", "dismissed",
                                         "--review", f"seq:{opened['sequence']}")
            self.assertNotEqual(code, 0, payload)
            self.assertIn("not 'somewhere-else'", payload["message"])


class EveryCitationFormProtectsTests(unittest.TestCase):
    """Fix round 2, R2-B6 - three citation forms, free text, and every kind."""

    @staticmethod
    def _old(kind: str, subject: str, sequence: int, data: dict | None = None) -> dict:
        return {"kind": kind, "subject": subject, "sequence": sequence,
                "recorded_at": OLD_ACTION.isoformat(), "data": data or {}}

    @staticmethod
    def _citing(kind: str, sequence: int, *, evidence=None, data=None) -> dict:
        return {"kind": kind, "subject": "citer", "sequence": sequence,
                "recorded_at": NOW.isoformat(), "evidence": evidence or [],
                "data": data or {}}

    def test_verdict_and_diff_cites_protect_what_they_name(self) -> None:
        records = [
            self._old("attestation", "a", 1),
            self._old("attestation", "b", 2),
            self._citing("checkpoint", 3, evidence=["verdict:1", "diff:2"]),
            self._old("action", "tail", 4),
        ]
        self.assertEqual(forget_mod.protected_sequences(records), {1, 2})
        self.assertEqual([r["sequence"] for r in
                          forget_mod.eligible_for_expiry(records, now=NOW)], [])

    def test_a_seq_cite_inside_free_text_protects(self) -> None:
        records = [
            self._old("attestation", "a", 1),
            self._citing("decision", 2, data={"value": "kept because seq:1 says so"}),
            self._old("action", "tail", 3),
        ]
        self.assertEqual(forget_mod.protected_sequences(records), {1})

    def test_a_cite_from_a_kind_outside_the_old_allow_list_protects(self) -> None:
        for kind in ("decision", "verdict", "obligation", "incident",
                     "improvement_proposal"):
            with self.subTest(kind=kind):
                records = [
                    self._old("attestation", "a", 1),
                    self._citing(kind, 2, evidence=["seq:1"]),
                    self._old("action", "tail", 3),
                ]
                self.assertIn(1, forget_mod.protected_sequences(records))

    def test_an_episodic_record_citing_another_protects_nothing(self) -> None:
        # Otherwise two expired actions citing each other pin each other hot
        # forever, and the pass can never make progress.
        records = [
            self._old("action", "a", 1),
            self._old("action", "b", 2, {"evidence": ["seq:1"]}),
            self._old("action", "tail", 3),
        ]
        self.assertEqual(forget_mod.protected_sequences(records), set())
        self.assertEqual([r["sequence"] for r in
                          forget_mod.eligible_for_expiry(records, now=NOW)], [1, 2])

    def test_a_dormant_law_guard_still_protects_nothing_extra(self) -> None:
        records = [
            self._old("attestation", "a", 1),
            self._citing("lesson", 2, evidence=["seq:1"],
                         data={"enforce": {"kind": "decision"}, "status": "superseded"}),
            self._old("action", "tail", 3),
        ]
        self.assertEqual(forget_mod.protected_sequences(records), set())

    def test_the_fold_stays_linear_at_twenty_thousand_records(self) -> None:
        # The measured budget is 19.5 ms per call at N=20,000; this asserts the
        # ORDER OF MAGNITUDE, not a stopwatch reading, so it cannot flake into
        # a false failure on a loaded machine.
        import time
        # Every record non-episodic and carrying prose - the shape that pays
        # the most, since an episodic record short-circuits before the scan.
        records = [self._citing("decision", i + 1,
                                data={"value": "an ordinary summary of what happened, "
                                               "in the writer's own words"})
                   for i in range(20000)]
        records.append(self._citing("checkpoint", 20001, evidence=["seq:7"]))
        started = time.perf_counter()
        protected = forget_mod.protected_sequences(records)
        elapsed = time.perf_counter() - started
        self.assertIn(7, protected)
        self.assertLess(elapsed, 1.0, f"protected_sequences took {elapsed:.3f}s at N=20,000")


class TheGapBridgeNeedsARealHashTests(unittest.TestCase):
    """Fix round 2, R2-B4 - `None == None` is not a chain link."""

    @staticmethod
    def _rotate_two(archive: Chronicle) -> dict:
        _append_at(archive, "action", "old-1", {"summary": "one"}, OLD_ACTION)
        _append_at(archive, "action", "old-2", {"summary": "two"}, OLD_ACTION)
        archive.append("decision", "kept", {"value": "k"}, evidence=[])
        return forget_mod.forget(archive, now=NOW.isoformat())

    def test_a_registry_that_rotates_a_sequence_it_holds_no_hash_for_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self._rotate_two(archive)
            self.assertIsNotNone(archive._read_cold_registry())  # noqa: SLF001
            payload = json.loads(archive.cold_registry.read_text(encoding="utf-8"))
            payload["hash_by_sequence"].pop("2")
            archive.cold_registry.write_text(json.dumps(payload), encoding="utf-8")
            # `rotated` claims 2; nothing records what it sealed with. An
            # incomplete registry is an unreadable one.
            self.assertIsNone(archive._read_cold_registry())  # noqa: SLF001

    def test_a_null_previous_hash_is_never_a_bridged_gap(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self._rotate_two(archive)
            records = archive.read_events(verify=False)
            # A registry that names the gap but holds no hash for it, against a
            # record whose own `previous_hash` is null: two `None`s that used to
            # compare equal and bless a record linked to nothing.
            forged = dict(records[0])
            forged["previous_hash"] = None
            archive.cold_registry.write_text(
                json.dumps({"format": 1, "rotated": [1, 2],
                            "hash_by_sequence": {}, "segments": []}),
                encoding="utf-8")
            outcome = archive.verify([forged] + records[1:], check_anchor=False,
                                     use_checkpoint=False)
            self.assertFalse(outcome["ok"], outcome)
            self.assertIn("not contiguous", outcome["message"])
            self.assertIn("cold registry", outcome["message"])

    def test_an_honest_registry_still_bridges_its_own_rotation(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self._rotate_two(archive)
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])


class ClosingAReviewComparesTrustTests(unittest.TestCase):
    """Fix round 2, R2-B7 - the close guard was identity-only, and by default
    two undeclared agents on one project share one `agent_id`."""

    _FINDING = {"kind": "decision", "sequences": [1, 2]}

    def test_a_plain_agent_may_not_dismiss_an_operator_opened_review(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("review", "t2", {**self._FINDING, "status": "open"},
                           evidence=[], as_operator=True, operator_verified=True)
            with self.assertRaises(GodmodeError) as caught:
                archive.append("review", "t2", {**self._FINDING, "status": "dismissed"},
                               evidence=[])
            self.assertIn("lower-trust writer", str(caught.exception))
            self.assertIn("operator", str(caught.exception))
            self.assertEqual(
                [entry["subject"]
                 for entry in godmode_chronicle.open_reviews(archive.read_events())],
                ["t2"])

    def test_an_operator_may_close_a_review_a_plain_agent_opened(self) -> None:
        # The other direction, which the guard must NOT refuse: trust ranks
        # downward, never upward.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("review", "t2", {**self._FINDING, "status": "open"},
                           evidence=[])
            archive.append("review", "t2", {**self._FINDING, "status": "acknowledged"},
                           evidence=[], as_operator=True, operator_verified=True)
            self.assertEqual(godmode_chronicle.open_reviews(archive.read_events()), [])

    def test_an_agent_may_still_close_a_review_an_agent_opened(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("review", "t2", {**self._FINDING, "status": "open"},
                           evidence=[])
            archive.append("review", "t2", {**self._FINDING, "status": "dismissed"},
                           evidence=[])
            self.assertEqual(godmode_chronicle.open_reviews(archive.read_events()), [])


class ColdSegmentsAreScannedTests(unittest.TestCase):
    """Review B, B5 - the two CLI claims THREAT-MODEL.md makes."""

    def test_doctor_reports_a_broken_cold_segment(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {"summary": "distinctive"}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            segment = archive.root / report["expire"]["segment"]
            segment.write_text(
                segment.read_text(encoding="utf-8").replace("distinctive", "tampered!!!"),
                encoding="utf-8")
            _code, payload = _run(project, "doctor")
            codes = [issue["code"] for issue in payload.get("issues", [])]
            self.assertIn("cold-segment-broken", codes, payload)

    def test_a_secret_in_a_cold_segment_is_found(self) -> None:
        from godmode_runtime.godmode_console import _secret_scan_targets
        from godmode_runtime.godmode_sentinel import find_secret_shapes
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            token = "ghp_" + "a1b2c3d4e5" * 3 + "abcdef"
            (archive.root / "events-cold-1.jsonl").write_text(
                json.dumps({"sequence": 1, "data": {"token": token}}) + "\n",
                encoding="utf-8")
            found = [f"{label}:{item}"
                     for label, value in _secret_scan_targets(archive.root)
                     for item in find_secret_shapes(value)]
            self.assertTrue(any(hit.startswith("events-cold-1.jsonl:1:") for hit in found),
                            found)
            self.assertTrue(any("$.data.token" in hit for hit in found), found)


class PassIsOnRecordTests(unittest.TestCase):
    """Review B, cadence / N9 - Task 8's "the forget pass ran" evidence."""

    def test_a_real_pass_records_itself(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat())
            recorded = archive.find_by_sequence(report["pass_recorded"])
            self.assertEqual(recorded["kind"], "action")
            self.assertEqual(recorded["subject"], "forget-pass")
            self.assertEqual(recorded["data"]["expired"], 1)
            self.assertEqual(recorded["data"]["ran_at"], NOW.isoformat())

    def test_a_dry_run_records_nothing(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            report = forget_mod.forget(archive, now=NOW.isoformat(), dry_run=True)
            self.assertNotIn("pass_recorded", report)
            self.assertTrue(report["digest_unchanged"])
            self.assertEqual([r for r in archive.read_events()
                              if r.get("subject") == "forget-pass"], [])


class DigestIsScopedTests(unittest.TestCase):
    """Review A, B8 - the digest covers what a pass can change, not the root."""

    def test_the_digest_ignores_a_file_no_pass_can_touch(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "x", {"value": 1}, evidence=[])
            before = forget_mod.archive_digest(archive.root)
            (archive.root / "some-unrelated-sidecar.json").write_text("{}", encoding="utf-8")
            self.assertEqual(before, forget_mod.archive_digest(archive.root))

    def test_the_digest_still_covers_records_segments_and_the_registry(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _append_at(archive, "action", "old", {}, OLD_ACTION)
            archive.append("decision", "kept", {"value": "k"}, evidence=[])
            before = forget_mod.archive_digest(archive.root)
            forget_mod.forget(archive, now=NOW.isoformat())
            self.assertNotEqual(before, forget_mod.archive_digest(archive.root))
            self.assertTrue(archive.cold_registry.is_file())


class RotationRemovesWhatItClaimsTests(unittest.TestCase):
    """Fix round 2, R2-B1 - a rotation that reports success removed the files."""

    @staticmethod
    def _seed(archive: Chronicle) -> None:
        archive.initialize()
        for index in range(4):
            _append_at(archive, "action", f"old-{index}", {"summary": index}, OLD_ACTION)
        archive.append("decision", "kept", {"value": "k"}, evidence=[])

    @unittest.skipUnless(os.name == "nt", "MAX_PATH is a Windows limit")
    def test_a_rotation_past_max_path_actually_removes_the_hot_files(self) -> None:
        with deep_isolated_project() as (_project, _state, _anchor, archive):
            self._seed(archive)
            longest = max(len(str(path)) for path in archive.event_paths())
            self.assertGreater(longest, 260, "the fixture must exceed MAX_PATH to mean anything")
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["eligible"], [1, 2, 3, 4])
            # The whole finding: `Path.unlink(missing_ok=True)` returned
            # normally here and left every record hot.
            for sequence in (1, 2, 3, 4):
                self.assertIsNone(_hot_path_for(archive, sequence),
                                  f"sequence {sequence} was reported rotated and is still hot")
            self.assertEqual(len(archive.cold_segment_paths()), 1)
            # ... and the second pass must not write a second segment holding
            # records that never left the hot tier.
            forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(len(archive.cold_segment_paths()), 1)
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])

    def test_a_delete_that_leaves_the_file_behind_refuses_to_report_success(self) -> None:
        # The half that is not about path length at all: a locked or
        # read-only record file gave the same silent success. Simulated by a
        # `remove` that returns without removing - which is precisely what
        # Windows did past MAX_PATH.
        with isolated_project() as (_project, _state, _anchor, archive):
            self._seed(archive)
            original = os.remove

            def _pretend(target, *args, **kwargs):
                text = str(target)
                if text.endswith(".godmode.json") and "godmode-events" in text:
                    return None
                return original(target, *args, **kwargs)

            with mock.patch.object(godmode_chronicle.os, "remove", _pretend):
                with self.assertRaises(GodmodeError) as caught:
                    forget_mod.forget(archive, now=NOW.isoformat())
            self.assertIn("still present after being removed", str(caught.exception))
            self.assertIn("godmode forget", str(caught.exception))
            # Nothing was lost: the segment and the registry are on disk, and
            # the next pass resumes rather than duplicating.
            report = forget_mod.forget(archive, now=NOW.isoformat())
            self.assertEqual(report["expire"]["resumed"], [1, 2, 3, 4])
            self.assertEqual(len(archive.cold_segment_paths()), 1)
            self.assertTrue(archive.verify()["ok"])
            self.assertTrue(archive.verify_cold()["ok"])


class RotationDoesNotErodeTheAcceleratorsTests(unittest.TestCase):
    """Fix round 2, N1-N3 and N11 - the four same-shape costs the review's
    table named: a number read off the hot tier where a sequence belongs."""

    @staticmethod
    def _rotated(archive: Chronicle) -> None:
        archive.initialize()
        _append_at(archive, "action", "old-1", {"summary": "one"}, OLD_ACTION)
        _append_at(archive, "action", "old-2", {"summary": "two"}, OLD_ACTION)
        archive.append("decision", "kept", {"value": "k"}, evidence=[])
        forget_mod.forget(archive, now=NOW.isoformat())

    def test_the_parsed_cache_still_extends_after_a_rotation(self) -> None:
        # N2: `len(cache) == sequence - 1` is false forever after a rotation,
        # so every append dropped the parsed cache for the life of the archive.
        with isolated_project() as (_project, _state, _anchor, archive):
            self._rotated(archive)
            archive.read_events()                      # warm the cache
            self.assertIsNotNone(archive._events_cache)  # noqa: SLF001
            before = len(archive._events_cache)         # noqa: SLF001
            archive.append("decision", "after", {"value": "n"}, evidence=[])
            self.assertIsNotNone(archive._events_cache,  # noqa: SLF001
                                 "the append dropped the cache instead of extending it")
            self.assertEqual(len(archive._events_cache), before + 1)  # noqa: SLF001

    def test_the_enforce_index_stays_caught_up_after_a_rotation(self) -> None:
        # N3: `total = len(records)` against a `count` that is a sequence -
        # tier 1 stopped recognising a caught-up index and tier 3 stopped
        # refreshing the sidecar, so every append re-paid the full walk.
        with isolated_project() as (_project, _state, _anchor, archive):
            self._rotated(archive)
            archive.append("decision", "after", {"value": "n"}, evidence=[])
            tail = archive.read_events()[-1]["sequence"]
            self.assertEqual(archive._enforce_index_upto, tail)  # noqa: SLF001
            self.assertTrue((archive.root / "godmode-enforce.index.json").is_file())

    def test_the_anchor_check_is_answered_when_the_anchored_record_is_cold(self) -> None:
        # N1: `_anchor_gap` found no hot record at the anchored length and
        # returned None - the anchored-head check silently skipped.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for index in range(4):
                _append_at(archive, "action", f"old-{index}", {"summary": index}, OLD_ACTION)
            archive.rotate_to_cold([2])
            archive._events_cache_key = None  # noqa: SLF001
            records = archive.read_events(verify=False)
            state = {"length": 2,
                     "head_hash": archive._read_cold_registry()["hash_by_sequence"][2]}  # noqa: SLF001
            self.assertIsNone(archive._anchor_gap(state, records))  # noqa: SLF001
            forged = {"length": 2, "head_hash": "0" * 64}
            self.assertEqual(archive._anchor_gap(forged, records),  # noqa: SLF001
                             (2, len(records)))

    def test_doctor_names_a_cold_segment_nobody_owns(self) -> None:
        # N11: both verifiers walk only the segments the registry NAMES.
        with isolated_project() as (project, _state, _anchor, archive):
            self._rotated(archive)
            (archive.root / "events-cold-9.jsonl").write_text(
                json.dumps({"sequence": 99}) + "\n", encoding="utf-8")
            _code, payload = _run(project, "doctor")
            codes = [issue["code"] for issue in payload.get("issues", [])]
            self.assertIn("cold-segment-unowned", codes, payload)

    def test_verify_reports_a_count_that_does_not_shrink(self) -> None:
        # N5's honest half: `records` is what this walk saw (the hot tier),
        # and `sealed_records` is the number a rotation never lowers.
        with isolated_project() as (_project, _state, _anchor, archive):
            self._rotated(archive)
            archive._events_cache_key = None  # noqa: SLF001
            outcome = archive.verify(archive.read_events(verify=False))
            self.assertTrue(outcome["ok"], outcome)
            self.assertGreater(outcome["sealed_records"], outcome["records"])
            self.assertEqual(outcome["sealed_records"],
                             archive.read_events(verify=False)[-1]["sequence"])


if __name__ == "__main__":
    unittest.main()
