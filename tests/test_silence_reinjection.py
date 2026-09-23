"""NS-10h: an idle obligation or ask is re-surfaced once, then held quiet
for a per-anchor cooldown - `godmode_cooldown.due_for_resurface` is the
pure decision, over `cooldown` records and the caller's own turn count
(state, never the clock).

Fix round 1 adds: the Stop-hook surface (`_idle_resurface_lines`) caps
itself to the same two-line budget `_open_obligations_touched` uses and
only spends a cooldown record on an anchor it actually names; "touched"
is decided against the reply's full vocabulary, not that surface's own
capped return value; a resurfaced ask renders its stated keyword phrase,
not a bare `ask:<hex>`; and the loop half of the non-trip probe goes
through `godmode_loop.analyze`, the function `godmode loop` itself runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
HOOK = HOOKS / "godmode_session_hook.py"
for extra in (SCRIPTS, HOOKS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_constants import (  # noqa: E402
    ACTION_SUBJECTS, BOOKKEEPING_SUBJECTS, COOLDOWN_SUBJECT, RUN_INERT_SUBJECTS,
)
from godmode_runtime.godmode_cooldown import (  # noqa: E402
    due_for_resurface, record_resurfaced,
)
from godmode_runtime.godmode_loop import analyze  # noqa: E402
from godmode_runtime.godmode_requests import record_request  # noqa: E402
from godmode_runtime.godmode_watchdog import watchdog_report  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


class RegistrationTests(unittest.TestCase):
    """The subject the module writes is on every register that reads
    action subjects - `tests/test_action_subjects.py` is the census that
    would otherwise miss it silently."""

    def test_cooldown_subject_is_registered_everywhere(self) -> None:
        self.assertIn(COOLDOWN_SUBJECT, ACTION_SUBJECTS)
        self.assertIn(COOLDOWN_SUBJECT, BOOKKEEPING_SUBJECTS)
        self.assertIn(COOLDOWN_SUBJECT, RUN_INERT_SUBJECTS)


class DueForResurfaceTests(unittest.TestCase):
    def test_never_surfaced_and_idle_is_due(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertTrue(
                due_for_resurface(archive, "ask:aaaaaaaaaaaa", now_turn=5,
                                  last_touched_turn=0, idle_turns=3))

    def test_not_yet_idle_is_not_due(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertFalse(
                due_for_resurface(archive, "ask:aaaaaaaaaaaa", now_turn=2,
                                  last_touched_turn=0, idle_turns=3))

    def test_surfaced_once_then_silent_for_the_cooldown(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            anchor = "ask:bbbbbbbbbbbb"
            self.assertTrue(
                due_for_resurface(archive, anchor, now_turn=3,
                                  last_touched_turn=0, idle_turns=3,
                                  cooldown_turns=5))
            record_resurfaced(archive, anchor, now_turn=3, cooldown_turns=5)
            # Still idle every turn inside the cooldown window - silent.
            for turn in range(4, 8):
                with self.subTest(turn=turn):
                    self.assertFalse(
                        due_for_resurface(archive, anchor, now_turn=turn,
                                          last_touched_turn=0, idle_turns=3,
                                          cooldown_turns=5))
            # The cooldown has elapsed (until_turn == 3 + 5 == 8) - due again.
            self.assertTrue(
                due_for_resurface(archive, anchor, now_turn=8,
                                  last_touched_turn=0, idle_turns=3,
                                  cooldown_turns=5))

    def test_a_touched_ask_resets(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            anchor = "ask:cccccccccccc"
            record_resurfaced(archive, anchor, now_turn=3, cooldown_turns=5)
            # Turn 9 is past the cooldown (until_turn 8), but the anchor
            # was touched at turn 7 - only 2 turns idle, under idle_turns=3.
            self.assertFalse(
                due_for_resurface(archive, anchor, now_turn=9,
                                  last_touched_turn=7, idle_turns=3,
                                  cooldown_turns=5))
            # Enough turns pass with no further touch - idle again.
            self.assertTrue(
                due_for_resurface(archive, anchor, now_turn=10,
                                  last_touched_turn=7, idle_turns=3,
                                  cooldown_turns=5))

    def test_distinct_anchors_do_not_share_a_cooldown(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_resurfaced(archive, "ask:dddddddddddd", now_turn=3, cooldown_turns=5)
            self.assertTrue(
                due_for_resurface(archive, "ask:eeeeeeeeeeee", now_turn=4,
                                  last_touched_turn=0, idle_turns=3))

    def test_an_unreadable_archive_fails_toward_a_resurface(self) -> None:
        class _Broken:
            def select(self, **_kwargs):
                raise RuntimeError("boom")

        self.assertTrue(
            due_for_resurface(_Broken(), "ask:ffffffffffff", now_turn=9,
                              last_touched_turn=0, idle_turns=3))

    def test_cooldown_turns_is_a_real_input_not_dead(self) -> None:
        """Fix round 1, finding S2 (code quality): a caller asking with a
        NARROWER cooldown than the one actually recorded may decide "due"
        sooner than the record alone says."""
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            anchor = "ask:gggggggggggg"
            # Recorded with a generous 10-turn cooldown (until_turn = 13).
            record_resurfaced(archive, anchor, now_turn=3, cooldown_turns=10)
            # Asked about with the narrower default (5 turns): due at 8,
            # well before the recorded until_turn of 13.
            self.assertFalse(
                due_for_resurface(archive, anchor, now_turn=7,
                                  last_touched_turn=0, idle_turns=3,
                                  cooldown_turns=5))
            self.assertTrue(
                due_for_resurface(archive, anchor, now_turn=8,
                                  last_touched_turn=0, idle_turns=3,
                                  cooldown_turns=5))
            # Asked about with the wider, originally-recorded window, the
            # anchor is still silent at turn 8.
            self.assertFalse(
                due_for_resurface(archive, anchor, now_turn=8,
                                  last_touched_turn=0, idle_turns=3,
                                  cooldown_turns=10))


class LoopAndWatchdogNonTripTests(unittest.TestCase):
    """Three cooldown records in a row must never read as a loop (the
    `godmode loop` command's own `analyze`, not merely the private
    `_repeated_actions` detector one layer below it) or an unattested run
    streak (`godmode watchdog`) - they are bookkeeping about an anchor's
    silence, not a step the trajectory took."""

    def test_three_cooldown_records_do_not_trip_the_loop_command(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for turn, anchor in enumerate(
                    ("ask:1111", "ask:2222", "ask:3333"), start=1):
                record_resurfaced(archive, anchor, now_turn=turn, cooldown_turns=5)
            report = analyze(archive)
            self.assertEqual(report["findings"], [])

    def test_three_cooldown_records_do_not_trip_the_watchdog(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for turn, anchor in enumerate(
                    ("ask:1111", "ask:2222", "ask:3333"), start=1):
                record_resurfaced(archive, anchor, now_turn=turn, cooldown_turns=5)
            report = watchdog_report(archive)
            self.assertEqual(report["anomalies"], [])


class IdleResurfaceCapTests(unittest.TestCase):
    """S1-1: an unbounded idle surface named 25 lines / wrote 25 cooldown
    records against one project's 25 open obligations in a single Stop."""

    def test_25_open_obligations_cap_at_two_lines_and_two_records(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for i in range(25):
                archive.append("obligation", f"finish subsystem {i}",
                               {"status": "open", "value": f"subsystem {i} rollout"},
                               evidence=[])
            session = "cap-session"
            state = hook._cooldown_turn_state(archive, session)
            # Seed every anchor as already idle since turn 0 - otherwise
            # the first sighting alone would seed it at the current turn
            # and nothing would be due yet.
            for i in range(25):
                state["touched"][f"finish subsystem {i}"] = 0
            lines = hook._idle_resurface_lines(
                archive, None, "an unrelated reply about something else entirely",
                now_turn=5, state=state)
            self.assertLessEqual(len(lines), 2)
            self.assertEqual(len(lines), 2)
            cooldown_records = [
                r for r in archive.read_events()
                if r.get("kind") == "action" and r.get("subject") == COOLDOWN_SUBJECT
            ]
            self.assertEqual(len(cooldown_records), 2)

    def test_a_crowded_out_candidate_writes_no_cooldown_record(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for i in range(5):
                archive.append("obligation", f"finish part {i}",
                               {"status": "open", "value": f"part {i} rollout"},
                               evidence=[])
            session = "crowd-session"
            state = hook._cooldown_turn_state(archive, session)
            for i in range(5):
                state["touched"][f"finish part {i}"] = 0
            hook._idle_resurface_lines(
                archive, None, "nothing relevant here", now_turn=5, state=state)
            cooldown_anchors = {
                (r.get("data") or {}).get("anchor")
                for r in archive.read_events()
                if r.get("kind") == "action" and r.get("subject") == COOLDOWN_SUBJECT
            }
            self.assertEqual(len(cooldown_anchors), 2)
            self.assertLessEqual(cooldown_anchors, {f"finish part {i}" for i in range(5)})


class IdleResurfaceTouchTests(unittest.TestCase):
    """S1-2: `touched_subjects` parsed out of `_open_obligations_touched`'s
    already-capped return value let a third touched anchor read as idle."""

    def test_a_third_touched_obligation_refreshes_its_last_touched_turn(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            subjects = ["rewrite parser tokenizer", "rewrite parser lexer",
                        "rewrite parser grammar"]
            for subject in subjects:
                archive.append("obligation", subject,
                               {"status": "open", "value": subject}, evidence=[])
            # `_open_obligations_touched` itself can name at most two of
            # these three (its own two-item cap) - confirm the fixture
            # actually exercises that cap before trusting what it implies
            # about the third.
            reply = ("Status: rewrite parser tokenizer done, rewrite parser "
                     "lexer done, rewrite parser grammar done this turn.")
            capped = hook._open_obligations_touched(archive, reply)
            self.assertLessEqual(len(capped), 2)

            session = "touch-session"
            state = hook._cooldown_turn_state(archive, session)
            for subject in subjects:
                state["touched"][subject] = 0
            lines = hook._idle_resurface_lines(
                archive, None, reply, now_turn=5, state=state)
            # All three were touched by the FULL reply vocabulary this
            # turn, so none of them is idle - not just the two `capped`
            # happens to name.
            self.assertEqual(lines, [])
            for subject in subjects:
                self.assertEqual(state["touched"][subject], 5)


class IdleResurfaceAskRenderTests(unittest.TestCase):
    """A resurfaced ask names its stated keyword phrase, the same
    rendering `_open_obligations_touched` already uses for a touched ask
    (field report 2026-09-03: a hash plus a sorted keyword bag is not
    actionable and trains dismissal) - never a bare `ask:<hex>`."""

    def test_a_resurfaced_ask_shows_its_keyword_phrase(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_request(
                archive, "please rename the launcher directory variable everywhere",
                session="ask-session")
            self.assertIsNotNone(record)
            anchor = record["subject"]
            session = "ask-render-session"
            state = hook._cooldown_turn_state(archive, session)
            state["touched"][anchor] = 0
            lines = hook._idle_resurface_lines(
                archive, "ask-session", "totally unrelated reply text",
                now_turn=5, state=state)
            self.assertEqual(len(lines), 1)
            self.assertIn("rename", lines[0])
            self.assertIn("launcher", lines[0])
            self.assertNotIn(f"'{anchor}'", lines[0])
            self.assertIn(f'--subject "{anchor}"', lines[0])


class ResurfacedSurvivesEarlierNoticesTests(unittest.TestCase):
    """B1 (final review): `record_resurfaced` burns the cooldown the
    moment `_idle_resurface_lines` returns a line - so once two OTHER
    notices already claim the two `notices[:2]` Stop-message slots, a
    plain `notices.append` buried the resurfaced line in the doctor-only
    tail while its cooldown kept ticking down anyway: the anchor went
    quiet for a turn it was never actually shown on. `notices.insert(0,
    ...)` keeps the line that already spent its cooldown in the slot that
    always survives the clip - proven here through a real Stop pass, not
    just the pure `_idle_resurface_lines` unit."""

    def test_a_stop_with_two_earlier_notices_still_shows_the_resurfaced_line(self) -> None:
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            # Earlier notice #1: three blocked --offline checks trip the
            # paid-iteration tripwire (`_tripwire_nudges`), at the
            # declared default ceiling of 3.
            for i in range(3):
                archive.append("attestation", f"check:paid-{i}", {
                    "status": "blocked", "session": "S-resurface",
                    "result": "exit 0: 2 connection attempt(s) under "
                              "--offline, first socket.getaddrinfo"})
            # Earlier notice #2: an open obligation this turn's reply
            # shares >=3 salient words with - `_open_obligations_touched`'s
            # "unfinished promises" line.
            archive.append("obligation", "rename the launcher directory",
                            {"status": "open",
                             "value": "rename launcher directory variable"},
                            evidence=[])
            # The resurfaced candidate: idle since turn 0 in the cooldown
            # sidecar, never mentioned by this turn's reply text.
            archive.append("obligation", "refactor the config loader",
                            {"status": "open",
                             "value": "refactor config loader module"},
                            evidence=[])
            (archive.root / hook._COOLDOWN_STATE_FILE).write_text(
                json.dumps({"session": "", "turn": 10,
                            "touched": {"refactor the config loader": 0}}),
                encoding="utf-8")

            environment = dict(os.environ)
            environment["GODMODE_STATE_HOME"] = str(state)
            done = subprocess.run(
                [sys.executable, str(HOOK), "stop", "--project", str(project)],
                input=json.dumps({
                    "session_id": "S-resurface",
                    # Not done-shaped: a done-shaped reply exits through the
                    # done-bar block, whose systemMessage is the unclipped
                    # join and never reaches the `notices[:2]` clip.
                    "lastAssistantMessage":
                        "I am still renaming the launcher directory "
                        "variable; more to do.",
                }),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=environment)
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(done.stdout)
            message = payload.get("systemMessage", "")
            # The resurfaced line keeps the FIRST slot, ahead of both
            # earlier notices - the exact ordering `notices.insert(0, …)`
            # guarantees and `notices.append(…)` would not.
            # The reply is not blocked: only the clipped systemMessage
            # comes back, so this assertion exercises the clip itself.
            self.assertEqual(set(payload), {"systemMessage"}, payload)
            self.assertTrue(
                message.startswith("godmode: idle and worth another look"),
                message)
            self.assertIn("refactor", message)
            self.assertIn("more in `godmode doctor`", message)

            cooldown_records = [
                r for r in archive.read_events()
                if r.get("kind") == "action" and r.get("subject") == COOLDOWN_SUBJECT
            ]
            self.assertEqual(len(cooldown_records), 1, cooldown_records)


if __name__ == "__main__":
    unittest.main()
