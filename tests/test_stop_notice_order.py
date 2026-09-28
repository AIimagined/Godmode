"""Stop notices, refusal layout and degraded events: the hooks bundle.

A notice whose production already spent once-only state (a nag marker, a
nudge receipt, a resurface cooldown) is never clipped; a sentence that
echoes the hook's own feedback is not a completion claim; a pre-tool
refusal reads rule, detail, checklist; a degraded event still answers in
its own contract.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS = PLUGIN_ROOT / "hooks"
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (str(SCRIPTS), str(HOOKS), str(Path(__file__).parent)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import godmode_session_hook as hook  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class ClipTests(unittest.TestCase):
    def test_a_burned_line_survives_the_clip_wherever_it_sits(self) -> None:
        notices = [f"godmode: free {i}" for i in range(9)] + ["godmode: idle and worth another look"]
        shown = hook._clip_notices(notices, burned={"godmode: idle and worth another look"})
        self.assertEqual(shown[0], "godmode: idle and worth another look")
        self.assertEqual(shown[1], "godmode: free 0")
        self.assertEqual(shown[-1], "(8 more in `godmode doctor`)")

    def test_burned_lines_alone_may_exceed_the_cap(self) -> None:
        burned = {"nag", "nudge", "resurfaced"}
        shown = hook._clip_notices(["free", "nag", "nudge", "resurfaced"], burned=burned)
        self.assertEqual(shown, ["nag", "nudge", "resurfaced", "(1 more in `godmode doctor`)"])

    def test_nothing_burned_keeps_the_old_shape(self) -> None:
        self.assertEqual(hook._clip_notices(["a", "b", "c"], burned=set()),
                         ["a", "b", "(1 more in `godmode doctor`)"])
        self.assertEqual(hook._clip_notices(["a"], burned=set()), ["a"])


class HookEchoTests(unittest.TestCase):
    def test_a_sentence_echoing_the_hooks_feedback_is_not_a_done_claim(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            echoes = ("Godmode said the done-bar was passed by the previous reply.",
                      "godmode: the migration is complete and all tests pass.",
                      "The gate flagged the release as complete last turn.")
            for text in echoes:
                with self.subTest(text=text):
                    self.assertEqual(hook._unrecorded_done_claims(archive, text), [])
            found = hook._unrecorded_done_claims(
                archive, "The migration is complete and all tests pass.")
            self.assertEqual(len(found), 1, found)
            self.assertTrue(found[0].startswith("The migration is complete"))


class ThreeZoneReasonTests(unittest.TestCase):
    def test_a_refusal_reads_rule_detail_checklist(self) -> None:
        text = hook._three_zone_reason(
            "refused: git-history-or-remote (R4 - too high a risk tier). Run it yourself, "
            "or stage a capability for this exact command.")
        lines = text.splitlines()
        self.assertEqual(lines[0], "refused: git-history-or-remote (R4 - too high a risk tier).")
        self.assertIn("stage a capability", lines[1])
        self.assertEqual(lines[2], "Checklist:")
        self.assertTrue(all(line.startswith("- ") for line in lines[3:]))

    def test_a_single_sentence_is_left_alone(self) -> None:
        self.assertEqual(hook._three_zone_reason("no operation described"), "no operation described")


class DegradedEventTests(unittest.TestCase):
    def _exit(self, event: str) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(hook, "_ancillary_degraded_reported", True), \
                mock.patch.object(sys, "stdout", out):
            code = hook._degraded_exit([event])
        return code, out.getvalue().strip()

    def test_each_event_answers_in_its_own_contract(self) -> None:
        code, body = self._exit("session-start")
        self.assertEqual(code, 0)
        self.assertIn("No continuity brief", json.loads(body)["hookSpecificOutput"]["additionalContext"])
        code, body = self._exit("stop")
        self.assertEqual(code, 0)
        self.assertIn("degraded", json.loads(body)["systemMessage"])
        code, body = self._exit("pre-action")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(body.splitlines()[0])["hookSpecificOutput"]["permissionDecision"], "deny")
        code, body = self._exit("session-end")
        self.assertEqual((code, body), (0, ""))


if __name__ == "__main__":
    unittest.main()
