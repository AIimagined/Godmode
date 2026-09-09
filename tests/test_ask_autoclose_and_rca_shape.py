"""Asks close themselves when served, nags fire once, and a failure names
the RCA verbs (obligations 10117, 10116).

Twenty-first field report: "the ask obligations nag repeatedly" and "zero
help on the RCA". A stated request whose keywords the reply covers is
served, and the closure is written by the runtime at Stop; an open
obligation the turn touched is named once per session, not at every stop;
an investigation-shaped prompt and a failed tool run both name the verbs
that exist for root-cause work.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))

from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_precheck import failure_nudge, prompt_shape_nudge  # noqa: E402
from godmode_runtime.godmode_requests import (  # noqa: E402
    open_stated_requests, record_request,
)
from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_session_hook import _nag_once  # noqa: E402


class NoAutoServeTests(unittest.TestCase):
    """Field reports 23-25 (2026-09-09): the keyword-overlap closure this class
    used to prove would have closed an ask on 41 of 42 real replies. An ask
    now closes by hand or leaves the turn boundary with its session."""

    def test_a_reply_that_covers_the_ask_does_not_close_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "t")
            record_request(archive, "please rename the launcher directory variable", session=session)
            self.assertEqual(len(open_stated_requests(archive.select(kind="request", limit=50))), 1)
            archive.append("checkpoint", "Done: the launcher directory variable is renamed.",
                           {"status": "active", "next": []}, evidence=[])
            self.assertEqual(len(open_stated_requests(archive.select(kind="request", limit=50))), 1)
            self.assertEqual([r for r in archive.select(kind="request", limit=50)
                              if (r.get("data") or {}).get("status") == "served"], [])

    def test_the_runtime_closure_is_gone(self) -> None:
        from godmode_runtime import godmode_requests
        self.assertFalse(hasattr(godmode_requests, "serve_requests"))
        self.assertTrue(hasattr(godmode_requests, "open_stated_requests"))

    def test_a_hand_closure_still_closes(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record = record_request(archive, "please rename the launcher directory variable", session="s")
            archive.append("request", record["subject"],
                           {"digest": record["data"]["digest"], "status": "closed", "value": "done"})
            self.assertEqual(open_stated_requests(archive.select(kind="request", limit=50)), [])


class NagOnceTests(unittest.TestCase):
    def test_a_touched_obligation_is_named_once_per_session(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            first = _nag_once(archive, "s1", ["cut the release once green", "widen the census"])
            self.assertEqual(first, ["cut the release once green", "widen the census"])
            second = _nag_once(archive, "s1", ["cut the release once green", "a new one"])
            self.assertEqual(second, ["a new one"])
            # A new session starts fresh.
            self.assertEqual(_nag_once(archive, "s2", ["cut the release once green"]),
                             ["cut the release once green"])


class RcaShapeTests(unittest.TestCase):
    def test_an_investigation_shaped_prompt_names_the_rca_verbs(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            text = prompt_shape_nudge(archive, "why did the suite fail on the Windows leg? do a root cause analysis", "s1")
            self.assertIsNotNone(text)
            for verb in ("mistakes", "error-pattern", "incident", "differential", "verify"):
                self.assertIn(verb, text)

    def test_a_failed_tool_run_names_the_record_once_per_session(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            output = "Traceback (most recent call last):\n  File x\nValueError: boom\nexit 1"
            text = failure_nudge(archive, output, "s1")
            self.assertIsNotNone(text)
            self.assertIn("attested check", text)
            self.assertNotIn("`godmode error-pattern`", text)
            self.assertIsNone(failure_nudge(archive, output, "s1"))
            self.assertIsNone(failure_nudge(archive, "all good, exit 0", "s2"))


if __name__ == "__main__":
    unittest.main()
