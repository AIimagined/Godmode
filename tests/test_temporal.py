"""U-T2: red-before-green temporal verification + criterion pre-registration.

A completion claim citing a test command is admissible only when the SAME
command is observed failing before the fix-edit and passing after - the
temporal shape, not just the citation (E4 R4 / E6 tdd, superpowers-class).
Criterion pre-registration (E4): state what passing looks like
before doing the work, and cite it from the claim that judges the work done.

Every fixture transcript line below is built to the REAL host shape pinned
in `godmode_session_log`'s module docstring and exercised in
`tests/test_session_log.py` - no string from a real transcript is
reproduced anywhere here; every value is synthetic.

**The red/green choice this suite exercises.** `godmode_session_log` derives
a command's outcome from a `tool_result` block's `is_error` boolean, not a
parsed exit code (no structured exit code exists on the real shape - see
the module docstring). `_user_result` below sets that flag directly.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime.godmode_attest import (  # noqa: E402
    LATE_CRITERION_FINDING,
    TEMPORAL_REASON,
    open_session,
    record_claim,
    record_criterion,
    record_step,
)
from godmode_runtime.godmode_session_log import session_timeline  # noqa: E402

TEST_COMMAND = "pytest tests/temporal_fixture.py"
CITATION = f"cmd:{TEST_COMMAND}"


def _assistant_bash(tool_id: str, command: str) -> dict:
    """One assistant turn issuing a single Bash tool_use - the real shape."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id, "name": "Bash",
                         "input": {"command": command}}],
            "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0, "output_tokens": 0},
        },
    }


def _assistant_edit(tool_id: str) -> dict:
    """One assistant turn issuing a single Edit tool_use (a mutation turn)."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_id, "name": "Edit",
                         "input": {"file_path": "a.py"}}],
            "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0, "output_tokens": 0},
        },
    }


def _user_result(tool_id: str, is_error: bool) -> dict:
    """A user-role line carrying the `tool_result` for one prior tool_use."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_id,
                         "content": "ok", "is_error": is_error}],
        },
    }


def _write(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _timeline_from(lines: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "t.jsonl"
        _write(path, lines)
        return session_timeline(path)


class CommandTimelineTests(unittest.TestCase):
    """`session_timeline` / `command_timeline` over the pinned transcript shape."""

    def test_a_command_and_its_outcome_are_paired_by_tool_use_id(self) -> None:
        timeline = _timeline_from([
            _assistant_bash("toolu_0", TEST_COMMAND),
            _user_result("toolu_0", is_error=True),
        ])
        digests = list(timeline["commands"].keys())
        self.assertEqual(len(digests), 1)
        self.assertEqual(timeline["commands"][digests[0]], [(1, 1)])
        self.assertEqual(timeline["mutation_turns"], [])

    def test_edit_and_bash_turns_are_both_tracked_across_a_red_then_green_run(self) -> None:
        timeline = _timeline_from([
            _assistant_bash("toolu_0", TEST_COMMAND),
            _user_result("toolu_0", is_error=True),
            _assistant_edit("toolu_1"),
            _assistant_bash("toolu_2", TEST_COMMAND),
            _user_result("toolu_2", is_error=False),
        ])
        self.assertEqual(timeline["mutation_turns"], [2])
        digest = next(iter(timeline["commands"]))
        self.assertEqual(timeline["commands"][digest], [(1, 1), (3, 0)])

    def test_a_command_with_no_returned_result_is_absent_not_guessed(self) -> None:
        timeline = _timeline_from([_assistant_bash("toolu_0", TEST_COMMAND)])
        self.assertEqual(timeline["commands"], {})

    def test_digests_never_carry_the_raw_command_text(self) -> None:
        timeline = _timeline_from([
            _assistant_bash("toolu_0", TEST_COMMAND),
            _user_result("toolu_0", is_error=False),
        ])
        self.assertNotIn(TEST_COMMAND, json.dumps(timeline))


class RecordClaimTemporalTests(unittest.TestCase):
    """The red-before-green rule wired into `record_claim` (U-T2)."""

    def _seed_resolving_attestation(self, archive, session: str) -> None:
        # A `cmd:` citation must resolve (some attestation this session ran
        # it) before the temporal rule even applies - see record_claim's
        # elif ordering. This is that attestation.
        record_step(archive, session, "check:temporal", "ran",
                     result="exit 0", evidence=[CITATION])

    def test_green_only_timeline_downgrades_never_seen_failing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            self._seed_resolving_attestation(archive, session)
            timeline = _timeline_from([
                _assistant_bash("toolu_0", TEST_COMMAND),
                _user_result("toolu_0", is_error=False),
            ])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION], timeline=timeline)
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertTrue(record["data"]["downgraded"])
        self.assertIn("never seen failing", record["data"]["reason"])
        self.assertEqual(record["data"]["reason"], TEMPORAL_REASON)

    def test_red_then_green_across_the_mutation_is_not_downgraded(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            self._seed_resolving_attestation(archive, session)
            timeline = _timeline_from([
                _assistant_bash("toolu_0", TEST_COMMAND),
                _user_result("toolu_0", is_error=True),
                _assistant_edit("toolu_1"),
                _assistant_bash("toolu_2", TEST_COMMAND),
                _user_result("toolu_2", is_error=False),
            ])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION], timeline=timeline)
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertFalse(record["data"]["downgraded"])

    def test_red_only_timeline_downgrades(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            self._seed_resolving_attestation(archive, session)
            timeline = _timeline_from([
                _assistant_bash("toolu_0", TEST_COMMAND),
                _user_result("toolu_0", is_error=True),
                _assistant_edit("toolu_1"),
            ])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION], timeline=timeline)
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertTrue(record["data"]["downgraded"])

    def test_no_timeline_available_is_untouched_a_stated_gap_not_a_penalty(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            self._seed_resolving_attestation(archive, session)
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION], timeline=None)
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertFalse(record["data"]["downgraded"])

    def test_plant_reordering_the_timeline_green_before_red_still_downgrades(self) -> None:
        """The mandated plant: swap the order (green before the mutation,
        red after) - if the rule only checked "both outcomes occurred
        somewhere" this would wrongly pass. It must still downgrade."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            self._seed_resolving_attestation(archive, session)
            timeline = _timeline_from([
                _assistant_bash("toolu_0", TEST_COMMAND),
                _user_result("toolu_0", is_error=False),  # green FIRST
                _assistant_edit("toolu_1"),
                _assistant_bash("toolu_2", TEST_COMMAND),
                _user_result("toolu_2", is_error=True),  # red AFTER the mutation
            ])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION], timeline=timeline)
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertTrue(record["data"]["downgraded"])

    def test_non_fix_claims_are_not_held_to_the_temporal_rule(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            self._seed_resolving_attestation(archive, session)
            timeline = _timeline_from([
                _assistant_bash("toolu_0", TEST_COMMAND),
                _user_result("toolu_0", is_error=False),
            ])
            record = record_claim(archive, project, session,
                                  "The suite covers the retry path.", "verified",
                                  cites=[CITATION], timeline=timeline)
        self.assertEqual(record["data"]["grade"], "verified")


class CriterionTests(unittest.TestCase):
    """`record_criterion`: weak-criterion lint + ordering (U-T2)."""

    def test_weak_criterion_with_no_command_is_advisory(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            record = record_criterion(archive, session, "flaky-fix",
                                      "make the tests better")
        self.assertTrue(
            any("weak criterion" in a for a in record["data"]["advisories"]))

    def test_a_command_backed_criterion_has_no_advisories(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            record = record_criterion(archive, session, "flaky-fix",
                                      "the suite passes twice in a row",
                                      cites=[CITATION])
        self.assertEqual(record["data"]["advisories"], [])
        self.assertFalse(record["data"]["late"])

    def test_a_criterion_recorded_after_a_mutation_is_late(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            timeline = _timeline_from([_assistant_edit("toolu_0")])
            record = record_criterion(archive, session, "flaky-fix",
                                      "the suite passes twice in a row",
                                      cites=[CITATION], timeline=timeline)
        self.assertTrue(record["data"]["late"])
        self.assertIn(LATE_CRITERION_FINDING, record["data"]["advisories"])

    def test_a_criterion_recorded_before_any_mutation_is_not_late(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            timeline = _timeline_from([_assistant_bash("toolu_0", TEST_COMMAND)])
            record = record_criterion(archive, session, "flaky-fix",
                                      "the suite passes twice in a row",
                                      cites=[CITATION], timeline=timeline)
        self.assertFalse(record["data"]["late"])

    def test_no_transcript_leaves_the_ordering_check_unanswered_not_penalised(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            record = record_criterion(archive, session, "flaky-fix",
                                      "the suite passes twice in a row",
                                      cites=[CITATION], timeline=None)
        self.assertFalse(record["data"]["late"])


class ClaimCriterionAdvisoryTests(unittest.TestCase):
    """Criterion pre-registration surfaced on the claim it should have judged."""

    def test_a_fix_claim_without_a_criterion_citation_is_advised_when_one_exists(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            record_criterion(archive, session, "flaky-fix",
                             "the suite passes twice in a row", cites=[CITATION])
            record_step(archive, session, "check:temporal", "ran",
                        result="exit 0", evidence=[CITATION])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION])
        # Advisory, not a downgrade: the claim's grade is untouched.
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertTrue(
            any("no criterion citation" in a for a in record["data"]["advisories"]))

    def test_citing_the_criterion_clears_the_advisory(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            criterion = record_criterion(archive, session, "flaky-fix",
                                         "the suite passes twice in a row",
                                         cites=[CITATION])
            record_step(archive, session, "check:temporal", "ran",
                        result="exit 0", evidence=[CITATION])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION, criterion["subject"]])
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertEqual(record["data"]["advisories"], [])

    def test_no_criterion_ever_recorded_means_no_advisory_friction(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "temporal")
            record_step(archive, session, "check:temporal", "ran",
                        result="exit 0", evidence=[CITATION])
            record = record_claim(archive, project, session,
                                  "Fixed the flaky test.", "verified",
                                  cites=[CITATION])
        self.assertEqual(record["data"]["advisories"], [])


if __name__ == "__main__":
    unittest.main()
