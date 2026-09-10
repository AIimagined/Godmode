"""Field incident 2026-09-11: the stop gate named an ask as open while the
closure it prescribed answered "no open ask matches" - gate and archive
disagreed on the open set.

Two causes. A closure written from the command line is keyed on the
subject's digest and was applied to every record with that subject,
including an ask restated AFTER the closure, so a re-asked prompt was
"closed" before it was made. And the scope gate read the last 500 records
of every kind while the closure read the last 500 requests, so in a busy
session the two saw different request sets. A closure now closes only the
records that precede it, and both readers use the request-only window.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
TESTS = PLUGIN_ROOT / "tests"
for entry in (SCRIPTS, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_iteration import open_scope  # noqa: E402
from godmode_runtime.godmode_requests import digest, open_stated_requests, record_request  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

ASK = "please rename the transport module and keep the tests green"


def _hand_closure(archive, subject: str) -> None:
    """The record `remember --kind request --subject "ask:<hex>" --status closed` writes."""
    archive.append("request", subject, {"status": "closed", "digest": digest(subject), "source": "stated"},
                   evidence=[])


class ClosureOrderingTests(unittest.TestCase):
    def test_a_closure_does_not_close_an_ask_restated_after_it(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = record_request(archive, ASK, session="s1")
            subject = str(first["subject"])
            _hand_closure(archive, subject)
            self.assertEqual(open_stated_requests(archive.select(kind="request", limit=500)), [])
            record_request(archive, ASK, session="s2")
            still_open = open_stated_requests(archive.select(kind="request", limit=500))
            self.assertEqual([r["subject"] for r in still_open], [subject])
            _hand_closure(archive, subject)
            self.assertEqual(open_stated_requests(archive.select(kind="request", limit=500)), [])

    def test_the_scope_gate_and_the_closure_read_one_open_set(self) -> None:
        from godmode_runtime.godmode_console import _require_request_closure_target

        class _Runtime:
            def __init__(self, archive) -> None:
                self.archive = archive

        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            first = record_request(archive, ASK, session="s1")
            subject = str(first["subject"])
            _hand_closure(archive, subject)
            record_request(archive, ASK, session="s2")
            # A busy session: enough records of other kinds that a window
            # over every kind no longer reaches the closure above.
            for index in range(520):
                archive.append("action", "noise", {"n": index}, evidence=[])
            gate_names = [line for line in open_scope(archive, "s2")["asks"] if subject in line]
            self.assertEqual(len(gate_names), 1, gate_names)
            _require_request_closure_target(_Runtime(archive), subject)  # must not raise


if __name__ == "__main__":
    unittest.main()
