"""An ask the operator made once, which leaves no artefact anywhere else.

Every other thing this runtime governs leaves something behind: a command
leaves a run, a fix leaves a commit, a conclusion leaves a claim that must cite
one. A request leaves the agent's recollection, and in a long session that is
what degrades while the work continues.

The failure has a specific shape. An input arriving while the agent is already
running a tool is handed over beside a tool result; the cheapest part gets
answered and the rest is carried in the agent's head. Afterwards nobody can
point at what was dropped, because there was never a list.

It cannot be reconstructed either, which is why the record is written live.
Measured against a real 9,777-event transcript: the host's "sent a new message
while you were working" notice appears twice in the whole file, once because
the agent quoted it, and zero of 113 human inputs carry a timestamp inside a
tool call's span, because the stored time is delivery rather than typing.
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
    digest, record_request, render, review_requests, summarise,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class Ledger:
    """The archive, with only what this module needs from it."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def read_events(self) -> list[dict]:
        return self.records

    def append(self, kind: str, subject: str, data: dict,
               evidence: list[str]) -> dict:
        record = {"kind": kind, "subject": subject, "data": data,
                  "sequence": len(self.records) + 1, "evidence": evidence}
        self.records.append(record)
        return record

    def close(self, identifier: str) -> None:
        self.append("request", "closed", {"digest": identifier,
                                          "status": "closed"}, [])

    def review(self, answered: str = "") -> dict:
        return review_requests(self.records, answered)


class RecordingTests(unittest.TestCase):
    def test_a_request_is_recorded(self) -> None:
        ledger = Ledger()
        record = record_request(ledger, "publish the release page")
        self.assertIsNotNone(record)
        self.assertEqual(record["kind"], "request")
        self.assertEqual(record["data"]["status"], "open")

    def test_an_empty_prompt_records_nothing(self) -> None:
        self.assertIsNone(record_request(Ledger(), "   \n  "))

    def test_the_same_ask_retyped_is_the_same_ask(self) -> None:
        """A ledger that counts a repeated prompt twice reports a backlog the
        operator does not have."""
        ledger = Ledger()
        record_request(ledger, "check the release page")
        self.assertIsNone(record_request(ledger, "Check the   release   page"))
        self.assertEqual(len(ledger.records), 1)

    def test_a_different_ask_is_a_different_record(self) -> None:
        ledger = Ledger()
        record_request(ledger, "check the release page")
        record_request(ledger, "rewrite the author identity")
        self.assertEqual(len(ledger.records), 2)

    def test_a_long_prompt_is_summarised_not_stored_whole(self) -> None:
        """The host already keeps a transcript; a second copy is a second
        thing to leak."""
        long_prompt = "please " + ("verify the gate " * 60)
        record = record_request(Ledger(), long_prompt)
        self.assertLessEqual(len(record["subject"]), 161)
        self.assertTrue(record["subject"].endswith("…"))

    def test_the_digest_ignores_case_and_spacing_only(self) -> None:
        self.assertEqual(digest("Do The Thing"), digest("do  the thing"))
        self.assertNotEqual(digest("do the thing"), digest("do the other thing"))

    def test_a_short_prompt_is_kept_verbatim(self) -> None:
        self.assertEqual(summarise("  push   it  "), "push it")


class InterruptionTests(unittest.TestCase):
    """The fact that cannot be recovered later, so it is recorded now."""

    def test_an_input_arriving_mid_task_is_marked(self) -> None:
        record = record_request(Ledger(), "also check the readme",
                                tools_in_flight=3)
        self.assertTrue(record["data"]["interrupted_work"])
        self.assertEqual(record["data"]["tools_in_flight"], 3)

    def test_an_input_between_turns_is_not(self) -> None:
        record = record_request(Ledger(), "also check the readme")
        self.assertFalse(record["data"]["interrupted_work"])

    def test_interruptions_are_reported_first(self) -> None:
        """They are the ones nothing else would surface."""
        ledger = Ledger()
        record_request(ledger, "rewrite the author identity")
        record_request(ledger, "also look at the marketplace docs",
                       tools_in_flight=2)
        findings = ledger.review()["findings"]
        self.assertEqual(findings[0]["code"], "request-interrupted-work")
        self.assertIn("already running", findings[0]["detail"])


class ReviewTests(unittest.TestCase):
    def test_an_unanswered_request_is_reported(self) -> None:
        ledger = Ledger()
        record_request(ledger, "look at the marketplace documentation")
        report = ledger.review("I fixed the gate and pushed the release")
        self.assertEqual(report["verdict"], "open-requests")
        self.assertEqual(len(report["findings"]), 1)

    def test_a_request_the_session_visibly_answered_is_not(self) -> None:
        ledger = Ledger()
        record_request(ledger, "publish the release page")
        report = ledger.review(
            "I published the release page and verified it against the tag")
        self.assertEqual(report["verdict"], "no-open-requests", report)

    def test_every_finding_is_a_question(self) -> None:
        """Findings, never closures: the same contract as obligations, for the
        same reason - an agent that could close its own requests would close
        them the way it currently forgets them."""
        ledger = Ledger()
        record_request(ledger, "check the marketplace docs", tools_in_flight=1)
        for finding in ledger.review()["findings"]:
            self.assertIn("question", finding)
            self.assertNotIn("closed", finding)

    def test_closing_a_request_stops_it_being_reported(self) -> None:
        ledger = Ledger()
        record = record_request(ledger, "check the marketplace docs")
        self.assertTrue(ledger.review()["findings"])
        ledger.close(record["data"]["digest"])
        self.assertEqual(ledger.review()["findings"], [])

    def test_closing_one_leaves_the_others(self) -> None:
        ledger = Ledger()
        first = record_request(ledger, "check the marketplace docs")
        record_request(ledger, "rewrite the author identity")
        ledger.close(first["data"]["digest"])
        findings = ledger.review()["findings"]
        self.assertEqual(len(findings), 1)
        self.assertIn("author identity", findings[0]["request"])

    def test_the_report_states_what_it_examined(self) -> None:
        """So an empty report cannot be read as `nothing was examined`."""
        ledger = Ledger()
        record_request(ledger, "one thing")
        record_request(ledger, "another thing")
        report = ledger.review()
        self.assertEqual(report["requests_seen"], 2)
        self.assertEqual(report["verdict"], "open-requests")

    def test_a_session_with_no_requests_says_so(self) -> None:
        report = Ledger().review()
        self.assertEqual(report["verdict"], "no-open-requests")
        self.assertEqual(report["requests_seen"], 0)
        self.assertIn("none look unanswered", render(report))

    def test_the_render_names_how_to_close_one(self) -> None:
        ledger = Ledger()
        record_request(ledger, "check the marketplace docs")
        self.assertIn("--kind request", render(ledger.review()))


class ArchiveContractTests(unittest.TestCase):
    """Against the real archive, not the stand-in."""

    def test_request_is_a_kind_the_archive_accepts(self) -> None:
        """The census learned this the hard way: a surface recorded under a
        kind the archive cannot hold is impossible, not merely unused."""
        from godmode_runtime.godmode_constants import EVENT_KINDS

        self.assertIn("request", EVENT_KINDS)

    def test_a_request_survives_a_real_append_and_read(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "check the marketplace docs",
                           tools_in_flight=2)
            report = review_requests(archive.read_events())
        self.assertEqual(report["requests_seen"], 1)
        self.assertEqual(report["findings"][0]["code"], "request-interrupted-work")

    def test_a_secret_shaped_prompt_is_refused_by_the_archive(self) -> None:
        """A prompt is exactly where a pasted token turns up, and a ledger of
        asks is not worth a store of credentials. The append path runs the
        same secret scan every record runs; the hook swallows the refusal so
        the operator's turn continues."""
        from godmode_runtime.godmode_sentinel import PrivacyError

        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            leaked = "ghp_" + "a" * 32
            with self.assertRaises(PrivacyError):
                record_request(archive, f"use this token {leaked}")


if __name__ == "__main__":
    unittest.main()
