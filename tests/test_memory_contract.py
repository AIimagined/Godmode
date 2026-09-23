"""NS-11f: the archive's five memory layers, proven as a contract.

Godmode already implements four of the five layers of the memory model this
task's brief names, under other names of its own (working = the session
brief, episodic = the chronicle's action/refusal/incident/checkpoint kinds,
semantic = decisions/invariants/claims, procedural = skills); the fifth
(forgetting) is Task 7's `godmode forget`. This module is the eight-test
contract the brief asks for across all five: amnesia, contradiction,
staleness, promotion, load, scheduled, continuity, isolation.

Every test builds its own isolated archive (`isolated_project()` sets
`GODMODE_STATE_HOME` to a fresh temp directory per test - never the live
archive) and reads real records back through real, already-shipped surfaces
(`build_context_brief`, `why`, `hygiene`, `latest_by_subject`, the SessionStart
hook, `SkillProposal`/`skill forge`) - nothing here fakes an answer a real
call did not produce.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import (  # noqa: E402
    anchor_fingerprint, resolve_anchor)
from godmode_runtime.godmode_chronicle import (  # noqa: E402
    Chronicle, TRUST_ORDER, _record_hash, latest_by_subject, writer_fingerprint)
from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_constants import SCHEMA_VERSION  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError, ForgeError  # noqa: E402
from godmode_runtime.godmode_forge import SkillProposal, forge_skill  # noqa: E402
from godmode_runtime.godmode_hygiene import DEFAULT_CAP, hygiene  # noqa: E402
from godmode_runtime.godmode_lens import build_context_brief, why  # noqa: E402

from test_godmode_runtime import isolated_project  # noqa: E402

observe = importlib.import_module("test_observe_mode")


def _run(project: Path, *argv: str, stdin: str | None = None) -> tuple[int, dict]:
    """One CLI round trip, JSON in, JSON out - same harness
    `tests/test_writer_trust.py` uses, reused rather than reinvented."""
    out = io.StringIO()
    stdin_ctx = (
        mock.patch.object(sys, "stdin", io.StringIO(stdin))
        if stdin is not None else contextlib.nullcontext()
    )
    with stdin_ctx, contextlib.redirect_stdout(out):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


def _run_err(project: Path, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = console_main(["--project", str(project), "--json", *argv])
    return code, out.getvalue().strip()


class AmnesiaTests(unittest.TestCase):
    """A fact recorded in one session is recalled in the next - the working
    layer overflowing to a new brief build must not lose it."""

    def test_a_decision_recorded_in_session_one_is_recalled_in_session_two(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            archive.append(
                "decision", "release-cadence",
                {"value": "ship weekly, not nightly", "status": "active"},
                evidence=["seq:1"],
            )
            # "Session two": nothing but the archive persists - a fresh brief
            # build is exactly what a brand-new session sees.
            brief = build_context_brief(anchor, archive)
            subjects = {record["subject"] for record in brief["records"]}
            self.assertIn("release-cadence", subjects)

    def test_the_same_fact_is_recalled_by_context_why(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            archive.append(
                "decision", "release-cadence",
                {"value": "ship weekly, not nightly", "status": "active"},
                evidence=["seq:1"],
            )
            answer = why(anchor, archive, "release-cadence")
            self.assertEqual(
                [item["subject"] for item in answer["decisions"]], ["release-cadence"])


class ContradictionTests(unittest.TestCase):
    """Two conflicting facts are flagged for a human to resolve - never
    silently picked between."""

    def test_two_conflicting_decisions_on_one_subject_are_flagged_not_chosen(self) -> None:
        # NS-10e/`latest_by_subject`: two records under the EXACT SAME
        # subject fold to one "latest" before hygiene ever compares them
        # (`godmode_hygiene.py`'s own self-check documents exactly this
        # gap: identical subjects may find nothing, which is why its
        # assertion tolerates either outcome). A real contradiction is two
        # DIFFERENT subjects whose CONTENT says opposite things about the
        # same fact - the near-duplicate/contradiction pass's actual,
        # intended shape (see the module's own lesson example).
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = archive.append(
                "decision", "stdin-read-behavior-full",
                {"value": "hooks read stdin to EOF", "status": "active"}, evidence=[],
            )
            second = archive.append(
                "decision", "stdin-read-behavior-partial",
                {"value": "hooks do not read stdin to EOF; they stop at the "
                          "first object", "status": "active"},
                evidence=[],
            )
            report = hygiene(archive.read_events())
            self.assertTrue(report["contradictions"], report)
            flagged = report["contradictions"][0]
            self.assertEqual(
                set(flagged["sequences"]), {first["sequence"], second["sequence"]})
            # Flagged, not chosen: `hygiene` decides nothing and deletes
            # nothing - both records are still on the archive afterwards.
            live_sequences = {record["sequence"] for record in archive.read_events()}
            self.assertIn(first["sequence"], live_sequences)
            self.assertIn(second["sequence"], live_sequences)


class SemanticDecisionInvariantTests(unittest.TestCase):
    """NS-11c: a decision that opts into the semantic-fact contract by
    carrying its own `data['subject']` must also carry `value` and
    `evidence`, or the write is refused naming what is missing. Declared-
    contract, not blanket - every existing decision writer this sprint
    already ships (register-shaped, `absorb:`, plain `remember`) sets no
    such key and is untouched by it; see `godmode_invariants.
    _semantic_decision_invariants`'s own docstring for why a blanket rule
    is not possible here."""

    def test_a_semantic_decision_missing_value_and_evidence_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as ctx:
                archive.append(
                    "decision", "some-label",
                    {"subject": "database-choice"},  # value, evidence missing
                    evidence=[],
                )
            message = str(ctx.exception)
            self.assertIn("value", message)
            self.assertIn("evidence", message)

    def test_a_complete_semantic_decision_is_accepted(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "decision", "some-label",
                {"subject": "database-choice", "value": "postgres",
                 "evidence": ["seq:1"]},
                evidence=[],
            )
            self.assertEqual(record["data"]["value"], "postgres")

    def test_absorb_and_plain_decisions_without_the_opt_in_key_are_unaffected(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            # A plain decision via `remember`, with no --evidence at all -
            # the exact shape `tests/test_writer_trust.py` and
            # `tests/test_supersession.py` rely on staying legal.
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "plain",
                "--value", "x")
            self.assertEqual(code, 0, payload)


class StalenessTests(unittest.TestCase):
    """An expired (superseded) fact is not surfaced as the current answer -
    the semantic layer's conflict resolution NS-10e already ships."""

    def test_a_superseded_decision_is_not_the_current_value_for_its_subject(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            old = archive.append(
                "decision", "database-choice",
                {"value": "sqlite", "status": "active"}, evidence=[],
            )
            new = archive.append(
                "decision", "database-choice",
                {"value": "postgres", "status": "active", "supersedes": old["sequence"]},
                evidence=[],
            )
            latest = latest_by_subject(archive.read_events())
            current = latest["database-choice"]
            self.assertEqual(current["sequence"], new["sequence"])
            self.assertEqual(current["data"]["value"], "postgres")
            self.assertNotEqual(current["sequence"], old["sequence"])


class PromotionTests(unittest.TestCase):
    """NS-11d: a method becomes a skill candidate only after three recorded
    successes of one task type, each cited by an evidence seq - not two, and
    not a bare, uncited count."""

    @staticmethod
    def _proposal(**overrides: object) -> SkillProposal:
        values: dict[str, object] = {
            "name": "load-test-observer",
            "purpose": "Summarize load-test evidence without mutating repository state.",
            "gap_evidence": "Three load-test sessions lacked one repeatable evidence summary.",
            "repeated_uses": 3,
            "positive_triggers": (
                "summarize load-test evidence for a review",
                "check whether the load fixture behaved as expected",
            ),
            "negative_triggers": (
                "the user asks to publish a release",
                "the user only asks for the current version number",
            ),
            "assertions": ("The result lists the inspected evidence",),
        }
        values.update(overrides)
        return SkillProposal(**values)  # type: ignore[arg-type]

    def test_two_recorded_successes_do_not_promote(self) -> None:
        with self.assertRaises(ForgeError):
            self._proposal(repeated_uses=2).validate()

    def test_three_recorded_successes_promote(self) -> None:
        proposal = self._proposal(repeated_uses=3)
        proposal.validate()  # must not raise
        with tempfile.TemporaryDirectory() as raw:
            created = forge_skill(raw, proposal)
            self.assertTrue((Path(created) / "SKILL.md").is_file())

    def _forge_argv(self, destination: Path, *, repeated_uses: str = "3",
                    success_evidence: tuple[str, ...] = ("seq:1", "seq:2", "seq:3"),
                    ) -> list[str]:
        argv = [
            "skill", "forge",
            "--destination", str(destination),
            "--name", "load-test-observer",
            "--purpose", "Summarize load-test evidence without mutating repository state.",
            "--gap-evidence", "Three load-test sessions lacked one repeatable evidence summary.",
            "--repeated-uses", repeated_uses,
        ]
        for cite in success_evidence:
            argv += ["--success-evidence", cite]
        argv += [
            "--positive", "summarize load-test evidence for a review",
            "--positive", "check whether the load fixture behaved as expected",
            "--negative", "the user asks to publish a release",
            "--negative", "the user only asks for the current version number",
            "--assertion", "The result lists the inspected evidence",
        ]
        return argv

    def test_cli_refuses_fewer_than_three_success_evidence_citations(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            destination = Path(project) / "skills"
            code, err = _run_err(
                project, *self._forge_argv(destination, success_evidence=("seq:1", "seq:2")))
            self.assertNotEqual(code, 0)
            self.assertIn("success-evidence", err)
            self.assertFalse((destination / "load-test-observer").exists())

    def test_cli_refuses_a_malformed_evidence_citation(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            destination = Path(project) / "skills"
            code, err = _run_err(
                project, *self._forge_argv(
                    destination, success_evidence=("seq:1", "seq:2", "not-a-seq")))
            self.assertNotEqual(code, 0)
            self.assertIn("seq:", err)

    @staticmethod
    def _three_recorded_successes(archive: Chronicle) -> tuple[str, ...]:
        """Three real records, cited by their real sequences (B3). The
        earlier version of this test cited `seq:1 seq:2 seq:3` against an
        archive holding nothing but `init` and asserted SUCCESS, which
        locked in the very gap NS-11d names: it made "three well-formed
        strings" the bar and called it evidence."""
        return tuple(
            f"seq:{archive.append('action', f'load-test-run-{index}', {'gate': 'allow'})['sequence']}"
            for index in range(3)
        )

    def test_cli_creates_the_skill_with_three_valid_citations_and_records_them(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            destination = Path(project) / "skills"
            cites = self._three_recorded_successes(archive)
            code, payload = _run(
                project, *self._forge_argv(destination, success_evidence=cites))
            self.assertEqual(code, 0, payload)
            self.assertTrue((destination / "load-test-observer" / "SKILL.md").is_file())
            created = [
                record for record in archive.read_events()
                if record["kind"] == "decision"
                and record["subject"] == "skill-created:load-test-observer"
            ]
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0]["data"]["success_evidence"], list(cites))
            self.assertEqual(created[0]["evidence"], list(cites))

    def test_cli_refuses_one_success_cited_three_times(self) -> None:
        # B3: `seq:1 seq:1 seq:1` is three citations of one success, and it
        # created the skill before this. The archive here HOLDS the record,
        # so this is the distinctness rule failing, not resolution.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            destination = Path(project) / "skills"
            cite = self._three_recorded_successes(archive)[0]
            code, err = _run_err(
                project,
                *self._forge_argv(destination, success_evidence=(cite, cite, cite)))
            self.assertNotEqual(code, 0)
            self.assertIn("DISTINCT", err)
            self.assertFalse((destination / "load-test-observer").exists())

    def test_cli_refuses_citations_that_name_no_record(self) -> None:
        # B3: three distinct, well-formed, entirely fictional sequences.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            destination = Path(project) / "skills"
            code, err = _run_err(
                project,
                *self._forge_argv(
                    destination,
                    success_evidence=("seq:999999", "seq:888888", "seq:777777")))
            self.assertNotEqual(code, 0)
            self.assertIn("seq:999999", err)
            self.assertFalse((destination / "load-test-observer").exists())

    def test_cli_refuses_a_zero_citation(self) -> None:
        # B3: zero is never a minted sequence, and `seq:0` matched the
        # shape regex exactly as well as any real cite did.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            destination = Path(project) / "skills"
            code, err = _run_err(
                project,
                *self._forge_argv(
                    destination, success_evidence=("seq:0", "seq:00", "seq:000")))
            self.assertNotEqual(code, 0)
            self.assertFalse((destination / "load-test-observer").exists())


def _fabricate_records(archive: Chronicle, count: int) -> float:
    """Write `count` structurally-valid records directly to disk, bypassing
    `Chronicle.append()`'s per-record fsync x3 (event file, chain anchor,
    head) - measured at ~50ms/record, which would put a real 10k-record
    write past ten minutes. The chain is still computed correctly (each
    record's `previous_hash`/`record_hash` genuinely link, same shape
    `_write_record` produces) so `read_events(verify=True)` - what
    `build_context_brief` actually calls - still walks and verifies it for
    real; only the anchor/head hint files and the fsync-per-file durability
    are deferred to one write at the end, which a synthetic load fixture
    does not need. Returns the wall-clock seconds the write took (reported,
    never asserted - NS-11f's own rule for this test)."""
    sequence, tail = archive._chain_tail()
    fingerprint = anchor_fingerprint(archive.anchor)
    agent = writer_fingerprint()
    now_iso = datetime.now(timezone.utc).isoformat()
    kinds = ("action", "decision", "invariant", "checkpoint", "obligation")
    started = time.time()
    for index in range(count):
        seq = sequence + 1 + index
        record_id = uuid.uuid4().hex
        record = {
            "schema_version": SCHEMA_VERSION,
            "project_key": archive.anchor.project_key,
            "sequence": seq,
            "record_id": record_id,
            "recorded_at": now_iso,
            "anchor_fingerprint": fingerprint,
            "agent": agent,
            "writer": "agent",
            "trust": TRUST_ORDER["agent"],
            "kind": kinds[index % len(kinds)],
            "subject": f"load-fixture-{index}",
            "data": {"value": f"fabricated value {index}", "status": "active"},
            "evidence": [],
            "previous_hash": tail,
        }
        record["record_hash"] = _record_hash(record)
        tail = record["record_hash"]
        path = archive.events / f"{seq:012d}-{record_id}.godmode.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    archive._write_chain_anchor(sequence + count, tail)
    archive._write_head(sequence + count, tail)
    archive._drop_events_cache(rewrite=True)
    return time.time() - started


class LoadTests(unittest.TestCase):
    """10k fabricated records: `build_context_brief` and `hygiene` complete
    and see every record - the timing is measured and reported (stderr),
    never asserted, per NS-11f's own rule (tests assert state, not wall
    clock)."""

    def test_ten_thousand_records_build_a_brief_and_run_hygiene(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            record_count = 10_000
            write_seconds = _fabricate_records(archive, record_count)

            # COLD first, and on its own `Chronicle` (fix round 1, M4): the
            # warm number below excludes the archive read, which is the
            # dominant cost and the one a real session actually pays - the
            # read that precedes it in this test is what warms the cache.
            start = time.time()
            build_context_brief(anchor, Chronicle(anchor))
            cold_brief_seconds = time.time() - start

            start = time.time()
            records = archive.read_events()
            read_seconds = time.time() - start

            start = time.time()
            brief = build_context_brief(anchor, archive)
            brief_seconds = time.time() - start

            start = time.time()
            report = hygiene(records)
            hygiene_seconds = time.time() - start

            # What each number is and is not (fix round 1, M4): the records
            # are fabricated, so this is 10k records READ, VERIFIED and
            # BRIEFED, never 10k appended - `Chronicle.append`'s validators,
            # dedupe, lock and fsync discipline are not exercised here.
            # `hygiene` folds to latest-per-subject and then keeps
            # `[-cap:]` per kind, so it compares at most a few hundred
            # records at any archive size; its timing is not a 10k number.
            print(
                f"NS-11f load: {record_count} fabricated records (read path) - "
                f"write {write_seconds:.2f}s, read+verify {read_seconds:.2f}s, "
                f"brief build COLD {cold_brief_seconds:.2f}s / WARM "
                f"{brief_seconds:.2f}s, hygiene {hygiene_seconds:.2f}s "
                f"(cap={DEFAULT_CAP} per kind, not {record_count})",
                file=sys.stderr,
            )

            # Completion and counts - never a duration bound.
            self.assertEqual(len(records), record_count)
            self.assertIn("records", brief)
            self.assertIn("estimated_tokens", brief)
            self.assertIsInstance(report["considered"], dict)
            self.assertGreaterEqual(report["considered"].get("decision", 0), 1)


class ScheduledForgetTests(unittest.TestCase):
    """The eighth contract test: one scheduled `godmode forget` pass over a
    fixture with all three of its cases planted (NS-11e/NS-11g).

    This was a named skip while Task 7 was in flight in a sibling worktree.
    Task 7 has landed, so the skip is lifted and every clause of its own
    un-skip criterion is asserted here: an episodic record past TTL rotated
    into a cold, still-chained segment; the supersession chain reported; a
    same-subject, conflicting-value, both-active pair flagged as an open
    `review`; and the pass recording that it ran.

    `now` is passed rather than the records being aged on disk: rewriting a
    record's `recorded_at` in place breaks the very chain the pass verifies
    before it does anything, so the clock is moved instead of the archive.
    """

    def test_a_scheduled_forget_pass_expires_supersedes_and_flags_contradictions(self) -> None:
        from godmode_runtime.godmode_constants import FORGET_PASS_SUBJECT
        from godmode_runtime.godmode_forget import forget
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            stale = archive.append("action", "ran the load fixture", {"gate": "allow"})
            first = archive.append(
                "decision", "index-strategy", {"value": "btree", "status": "active"})
            second = archive.append(
                "decision", "index-strategy",
                {"value": "hash", "status": "active", "supersedes": first["sequence"]})
            left = archive.append(
                "decision", "retry-budget", {"value": "two attempts", "status": "active"})
            right = archive.append(
                "decision", "retry-budget", {"value": "five attempts", "status": "active"})

            report = forget(archive, now="2099-01-01T00:00:00+00:00")

            # Expire: the episodic record is gone from the hot tier and the
            # chain the pass left behind still verifies end to end.
            self.assertIn(stale["sequence"], report["expire"]["eligible"])
            self.assertTrue(report["expire"]["rotated"], report["expire"])
            self.assertTrue(archive.cold_segment_paths())
            hot = archive.read_events(verify=True)
            self.assertNotIn(stale["sequence"], [record["sequence"] for record in hot])
            # The two semantic kinds are untouched by expiry.
            self.assertIn(left["sequence"], [record["sequence"] for record in hot])

            # Supersede: reported, never rewritten.
            self.assertIn({"from": first["sequence"], "to": second["sequence"],
                           "subject": "index-strategy"},
                          report["supersede"]["chains"])

            # Contradiction: flagged as one open review naming both sides,
            # and the superseded pair above is NOT flagged - a record
            # something has already superseded is not still standing.
            flagged = report["contradictions"]["flagged"]
            self.assertEqual([item["subject"] for item in flagged], ["retry-budget"])
            self.assertEqual(flagged[0]["sequences"], [left["sequence"], right["sequence"]])
            reviews = [record for record in hot if record["kind"] == "review"]
            self.assertEqual(len(reviews), 1, reviews)
            self.assertEqual(reviews[0]["data"]["status"], "open")

            # And the pass says it ran, so "when did one last run" is
            # answerable without re-deriving it.
            self.assertIn("pass_recorded", report)
            passes = [record for record in hot
                      if record["subject"] == FORGET_PASS_SUBJECT]
            self.assertEqual(len(passes), 1, passes)
            self.assertEqual(passes[0]["data"]["expired"], report["expire"]["count"])


class ContinuityTests(unittest.TestCase):
    """A multi-session task's progress (its last checkpoint and open next-
    actions) survives the session boundary - nothing but the archive
    persists between the two calls."""

    def test_next_actions_from_session_one_are_counted_in_session_two(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append(
                "checkpoint", "midway through the memory contract",
                {"status": "active",
                 "next": ["write the load test", "write the isolation test"]},
                evidence=[],
            )
            # "Session two": a brand-new SessionStart call, in a fresh
            # subprocess, with nothing carried over except the archive.
            brief = observe._session_start(project)
            context = brief["hookSpecificOutput"]["additionalContext"]
            _prefix, _, payload = context.partition("\n")
            digest = json.JSONDecoder().raw_decode(payload)[0]["resume"]
            self.assertEqual(
                digest["last_checkpoint"]["subject"], "midway through the memory contract")
            self.assertEqual(digest["last_checkpoint"]["status"], "active")
            self.assertEqual(digest["open_obligations"], 2)


class IsolationTests(unittest.TestCase):
    """Project A's records never reach project B's brief, including when
    both share one operator's state home (`archive_root` is namespaced by
    `project_key`, never by insertion order or process)."""

    def test_project_as_records_never_reach_project_bs_brief(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            shared_state = base / "shared-state"
            project_a = base / "project-a"
            project_b = base / "project-b"
            project_a.mkdir()
            project_b.mkdir()
            with mock.patch.dict(
                    os.environ, {"GODMODE_STATE_HOME": str(shared_state)}, clear=False):
                anchor_a = resolve_anchor(project_a)
                anchor_b = resolve_anchor(project_b)
                self.assertNotEqual(anchor_a.project_key, anchor_b.project_key)
                archive_a = Chronicle(anchor_a)
                archive_b = Chronicle(anchor_b)
                archive_a.initialize()
                archive_b.initialize()
                archive_a.append(
                    "decision", "project-a-secret-choice",
                    {"value": "only ever true in project A", "status": "active"},
                    evidence=[],
                )
                self.assertEqual(len(archive_b.read_events()), 0)
                brief_b = build_context_brief(anchor_b, archive_b)
                rendered = json.dumps(brief_b)
                self.assertNotIn("project-a-secret-choice", rendered)
                self.assertNotIn("only ever true in project A", rendered)


if __name__ == "__main__":
    unittest.main()
