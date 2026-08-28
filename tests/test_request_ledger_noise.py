"""The request ledger recorded things nobody asked for.

`UserPromptSubmit` is the only input a host cannot reconstruct later, so
the hook records every prompt it receives. But the host delivers more than
typed asks through that door: a tool-permission prompt, a task-completion
notification, and a subagent's queued command all arrive prompt-shaped.

Measured on this archive: 44 open requests, of which the latency probes,
a `<task-notification>`, a `Hook PreToolUse:Bash requires confirmation`
prompt, four raw Bash command bodies and a box-drawing separator were
never asks at all. A ledger whose count is mostly noise is a ledger nobody
reviews - and this one had never been reviewed, across 34 handovers.

The predicate is shared by the recorder and the reviewer on purpose. Used
only at write time it would leave the existing noise in place forever;
used in both, the same rule cleans what is already stored and stops more
arriving.

Filtering is kept narrow and shape-based, because the cost of dropping a
real ask is much higher than the cost of carrying a stray line. Each
pattern below is a host envelope a person does not type.
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

from godmode_runtime.godmode_requests import (  # noqa: E402
    is_operator_ask,
    record_request,
    review_requests,
)
from test_godmode_runtime import isolated_project  # noqa: E402

# Every one of these is a real subject from this project's own ledger.
HOST_ENVELOPES = [
    "<task-notification> <task-id>bgim7zim8</task-id> <tool-use-id>toolu_01</tool-use-id>",
    "Hook PreToolUse:Bash requires confirmation for this command: "
    "release-or-external-write (R4) - touches a redirected write",
    "Bash command grep -n \"^- \\[ \\]\" docs/RELEASE-CHECKLIST.md | tail -8",
    "Bash command \u00b7 from the general-purpose agent SCRATCH=\"C:\\Users\"",
    "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
]

REAL_ASKS = [
    "anything else pending? i dont want surprise later",
    "correct the claim and fix everything",
    "yes minimality pass,",
    "complete",
    "can i make repo public?",
    # Deliberately adversarial: mentions a tool, still a person asking.
    "can you run the bash command that rebuilds the gate table?",
]


class PredicateTests(unittest.TestCase):
    def test_host_envelopes_are_not_operator_asks(self) -> None:
        for text in HOST_ENVELOPES:
            with self.subTest(text=text[:40]):
                self.assertFalse(is_operator_ask(text))

    def test_real_asks_survive(self) -> None:
        for text in REAL_ASKS:
            with self.subTest(text=text[:40]):
                self.assertTrue(is_operator_ask(text))

    def test_a_prompt_with_no_word_is_not_an_ask(self) -> None:
        self.assertFalse(is_operator_ask("---- ==== ...."))


class RecordingTests(unittest.TestCase):
    def test_a_host_envelope_is_not_stored(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            stored = record_request(archive, HOST_ENVELOPES[0])
            self.assertIsNone(stored)

    def test_a_real_ask_is_still_stored(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertIsNotNone(record_request(archive, "make the repo public"))


class ReviewTests(unittest.TestCase):
    def test_envelopes_already_in_the_ledger_stop_being_reported(self) -> None:
        """Retroactive by design - the noise is already written.

        A predicate used only at write time would leave every existing
        envelope in the open count forever, which is the state that made
        this ledger unreviewable in the first place.
        """
        records = [
            {"kind": "request", "sequence": 1, "subject": HOST_ENVELOPES[0],
             "data": {"status": "open", "digest": "a", "keywords": ["task"]}},
            {"kind": "request", "sequence": 2, "subject": "make the repo public",
             "data": {"status": "open", "digest": "b", "keywords": ["repo"]}},
        ]
        findings = review_requests(records)["findings"]
        self.assertEqual([f["sequence"] for f in findings], [2])


class LongPromptClosureTests(unittest.TestCase):
    """A long request could not be closed from the command line at all.

    The stored `digest` is taken from the full flattened prompt while the
    `subject` is truncated to `SUBJECT_LIMIT`. `_closed_digests` digests
    the subject as a fallback so that retyping the line is enough - but
    for any prompt longer than the limit the two digests can never be
    equal, so the closure landed and changed nothing.

    Same failure shape the module's own docstring describes for the
    original digest-only matching: the mechanism exists, the report tells
    the reader to use it, and using it does nothing.
    """

    def test_a_digest_subject_can_still_be_closed(self) -> None:
        from godmode_runtime.godmode_requests import digest

        long_prompt = "please review " + ("the release checklist line by line " * 12)
        full = digest(" ".join(long_prompt.split()))
        subject = "ask:" + full[:12]   # what the ledger shows (2026-08-28)
        records = [
            {"kind": "request", "sequence": 1, "subject": subject,
             "data": {"status": "open", "digest": full, "keywords": ["release"]}},
            # The closure a person writes: it carries the subject they can
            # see - the digest prefix - never the full digest they cannot.
            {"kind": "request", "sequence": 2, "subject": subject,
             "data": {"status": "answered"}},
        ]
        self.assertEqual(review_requests(records)["findings"], [])


if __name__ == "__main__":
    unittest.main()
