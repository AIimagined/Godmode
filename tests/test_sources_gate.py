"""S5: the required-sources counter gates, seeds, and answers pins.

Obligation 4094: the counter was a real measurement nothing refused on - a
session read "read 0 of 8 required sources" aloud and stepped past it. The
gate turns the first otherwise-allowed pre-tool call of a session into an
ask while a bound authority document is uncited, once per session, with two
escapes: cite it, or exempt it on the record.
Obligation 4097: `adopt --from-docs` seeds a late install with counts-only
records citing each bound document, so day one starts populated.
Obligation 4166: a state-is-a-gap claim is checked against the tests that
name its surface and the lessons ledger before it may grade verified.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_sources import (  # noqa: E402
    adopt_from_docs, guard_pin_reason, required_sources_view,
)
from godmode_runtime.godmode_attest import open_session, record_claim  # noqa: E402


def _bind(project: Path) -> None:
    (project / "GODMODE.md").write_text("# Guide\n- rule one\n", encoding="utf-8")


class ViewTests(unittest.TestCase):
    def test_an_uncited_source_is_unread(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            view = required_sources_view(project, archive)
        self.assertIn("GODMODE.md", view["unread"])
        self.assertGreaterEqual(view["documents"], 1)

    def test_a_cited_source_counts_read(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            archive.append("action", "read-doc", {}, evidence=["file:GODMODE.md"])
            view = required_sources_view(project, archive)
        self.assertNotIn("GODMODE.md", view["unread"])

    def test_an_exemption_silences_without_reading(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            archive.append(
                "decision", "sources-exemption:GODMODE.md",
                {"status": "active", "value": "generated file, no prose to read"},
                evidence=[])
            view = required_sources_view(project, archive)
        self.assertNotIn("GODMODE.md", view["unread"])
        self.assertIn("GODMODE.md", view["exempted"])

    def test_a_retired_exemption_no_longer_silences(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            archive.append("decision", "sources-exemption:GODMODE.md",
                           {"status": "active"}, evidence=[])
            archive.append("decision", "sources-exemption:GODMODE.md",
                           {"status": "retired"}, evidence=[])
            view = required_sources_view(project, archive)
        self.assertIn("GODMODE.md", view["unread"])


class AdoptFromDocsTests(unittest.TestCase):
    def test_adopts_each_bound_document_with_counts_only(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            result = adopt_from_docs(archive, project)
            records = [r for r in archive.read_events()
                       if str(r.get("subject", "")).startswith("adopted-doc:")]
        self.assertIn("GODMODE.md", result["adopted"])
        record = next(r for r in records
                      if r["subject"] == "adopted-doc:GODMODE.md")
        self.assertEqual(record["data"]["headings"], 1)
        self.assertEqual(record["data"]["bullets"], 1)
        self.assertIn("file:GODMODE.md", record["evidence"])
        # Counts and a digest only - never the document's prose.
        self.assertNotIn("rule one", str(record["data"]))

    def test_idempotent_while_the_digest_stands(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            adopt_from_docs(archive, project)
            second = adopt_from_docs(archive, project)
        self.assertEqual(second["adopted"], [])
        self.assertIn("GODMODE.md", second["unchanged"])

    def test_a_changed_document_is_readopted(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            adopt_from_docs(archive, project)
            (project / "GODMODE.md").write_text("# Guide v2\n", encoding="utf-8")
            third = adopt_from_docs(archive, project)
        self.assertIn("GODMODE.md", third["adopted"])

    def test_adoption_satisfies_the_counter(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _bind(project)
            adopt_from_docs(archive, project)
            view = required_sources_view(project, archive)
        self.assertNotIn("GODMODE.md", view["unread"])


class GuardPinTests(unittest.TestCase):
    def test_an_uncited_test_pin_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "foo.py").write_text("VALUE = 1\n", encoding="utf-8")
            tests = project / "tests"
            tests.mkdir()
            (tests / "test_foo.py").write_text(
                "# pins foo.py: the missing check is deliberate\n",
                encoding="utf-8")
            reason = guard_pin_reason(
                project, archive,
                "There is no validation anywhere in foo.py", ["file:foo.py"])
        self.assertIn("tests/test_foo.py", reason)
        self.assertIn("provenance", reason)

    def test_a_cited_pin_is_quiet(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "foo.py").write_text("VALUE = 1\n", encoding="utf-8")
            tests = project / "tests"
            tests.mkdir()
            (tests / "test_foo.py").write_text("# pins foo.py\n", encoding="utf-8")
            reason = guard_pin_reason(
                project, archive,
                "There is no validation anywhere in foo.py",
                ["file:foo.py", "file:tests/test_foo.py"])
        self.assertEqual(reason, "")

    def test_a_lesson_sharing_the_vocabulary_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append(
                "lesson", "checkpoint-subject-truncation",
                {"status": "active",
                 "generalized_guard": "checkpoint subject truncation stays "
                                      "under the record limit by design"},
                evidence=[])
            reason = guard_pin_reason(
                project, archive,
                "checkpoint subject truncation validation is absent", [])
        self.assertIn("lesson seq:", reason)

    def test_plain_prose_finds_no_pin(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            reason = guard_pin_reason(
                project, archive, "moved two functions around", [])
        self.assertEqual(reason, "")

    def test_record_claim_wires_the_pin_rung(self) -> None:
        # The ladder rung itself: an absence claim that clears every earlier
        # rung still downgrades when the pin lookup names one.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            session = open_session(archive, "pin-test")
            (project / "foo.py").write_text("VALUE = 1\n", encoding="utf-8")
            with mock.patch("godmode_runtime.godmode_attest._guard_pin_reason",
                            return_value="a pin already names this surface"), \
                 mock.patch("godmode_runtime.godmode_attest._probed_twice",
                            return_value=True), \
                 mock.patch("godmode_runtime.godmode_attest._cites_a_search",
                            return_value=True):
                record = record_claim(
                    archive, project, session,
                    "There is no validation anywhere in foo.py",
                    "verified", cites=["file:foo.py"])
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("pin", record["data"]["reason"])


class SourcesGateTests(unittest.TestCase):
    def _gate(self):
        import godmode_session_hook as hook
        return hook._sources_gate_reason

    def test_first_call_asks_and_second_is_silent(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            _bind(project)
            session = open_session(archive, "gate-test")
            gate = self._gate()
            first = gate(archive, anchor, session)
            second = gate(archive, anchor, session)
        self.assertIsNotNone(first)
        self.assertIn("GODMODE.md", first)
        self.assertIn("sources-exemption", first)
        self.assertIsNone(second)

    def test_quiet_when_every_source_is_cited(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            _bind(project)
            adopt_from_docs(archive, project)
            session = open_session(archive, "gate-read")
            gate = self._gate()
            self.assertIsNone(gate(archive, anchor, session))

    def test_no_session_never_gates(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            _bind(project)
            gate = self._gate()
            self.assertIsNone(gate(archive, anchor, None))


if __name__ == "__main__":
    unittest.main()
