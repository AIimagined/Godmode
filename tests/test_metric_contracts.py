"""U-T3: anchored-metric contracts.

Numeric claims cite an output line matching a registered anchored pattern,
never a paraphrase. `register_metric_contract` declares a `^name:`-style
anchor as a `decision` record under subject `metric-contract:<name>`,
validated at registration: it must compile as a regex and stay under a
length cap (the E49-absorbed unsafe-pattern idea - `re.compile` plus a
length cap is the whole defense at this scale).

A claim naming a registered metric and a number is cross-checked against any
`line:<name>:<value>` citation it carries: a matching value stays verified,
a mismatched one is downgraded naming BOTH numbers, and a metric name that
was never registered gets no friction from this at all.
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

from test_godmode_runtime import isolated_project  # noqa: E402

from godmode_runtime.godmode_attest import (  # noqa: E402
    open_session,
    record_claim,
    register_metric_contract,
)
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402


class RegistrationTests(unittest.TestCase):
    def test_registering_a_contract_records_a_decision(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            record = register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
        self.assertEqual(record["kind"], "decision")
        self.assertEqual(record["subject"], "metric-contract:val_bpb")
        self.assertEqual(record["data"]["anchor"], "^val_bpb:")

    def test_an_empty_name_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            with self.assertRaises(ArchiveError):
                register_metric_contract(archive, session, "   ", "^val_bpb:")

    def test_an_invalid_regex_anchor_is_refused(self) -> None:
        """`re.compile` try - half the declared defense."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            with self.assertRaises(ArchiveError):
                register_metric_contract(archive, session, "val_bpb", "^val_bpb(")

    def test_an_over_long_anchor_is_refused(self) -> None:
        """The length cap - the other half of the declared defense."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            with self.assertRaises(ArchiveError):
                register_metric_contract(archive, session, "val_bpb", "a" * 201)

    def test_an_empty_anchor_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            with self.assertRaises(ArchiveError):
                register_metric_contract(archive, session, "val_bpb", "")


class CitationTests(unittest.TestCase):
    def test_a_claim_citing_the_matching_anchored_line_resolves(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            record = record_claim(
                archive, project, session, "val_bpb improved to 3.21", "verified",
                cites=["line:val_bpb:3.21"],
            )
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertFalse(record["data"]["downgraded"])

    def test_a_mismatched_cited_value_downgrades_naming_both_numbers(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            record = record_claim(
                archive, project, session, "val_bpb improved to 3.21", "verified",
                cites=["line:val_bpb:3.19"],
            )
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertTrue(record["data"]["downgraded"])
        self.assertIn("3.21", record["data"]["reason"])
        self.assertIn("3.19", record["data"]["reason"])

    def test_an_unregistered_metric_name_is_untouched(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            record = record_claim(
                archive, project, session, "throughput improved to 500", "verified",
                cites=["line:val_bpb:3.21"],
            )
        self.assertEqual(record["data"]["grade"], "verified")
        self.assertFalse(record["data"]["downgraded"])

    def test_a_line_citation_for_a_name_never_registered_does_not_resolve(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            record = record_claim(
                archive, project, session, "the run completed", "verified",
                cites=["line:val_loss:0.9"],
            )
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("line:val_loss:0.9", record["data"]["unresolved"])

    def test_a_line_citation_that_does_not_match_the_anchor_shape_does_not_resolve(self) -> None:
        """The name is registered; the reconstructed "name:value" text still
        has to match the anchor's own shape - a resolving name is not a
        free pass for whatever value shape follows it."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb=")
            record = record_claim(
                archive, project, session, "the run completed", "verified",
                cites=["line:val_bpb:3.21"],
            )
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("line:val_bpb:3.21", record["data"]["unresolved"])

    def test_markdown_emphasis_around_the_metric_name_is_still_recognised(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            record = record_claim(
                archive, project, session, "**val_bpb** improved to 3.21", "verified",
                cites=["line:val_bpb:3.19"],
            )
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("3.21", record["data"]["reason"])
        self.assertIn("3.19", record["data"]["reason"])

    def test_a_re_registered_anchor_supersedes_the_earlier_one(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", r"^val_bpb:0\.")
            register_metric_contract(archive, session, "val_bpb", r"^val_bpb:3\.")
            matches_new_anchor = record_claim(
                archive, project, session, "val_bpb improved to 3.21", "verified",
                cites=["line:val_bpb:3.21"],
            )
            no_longer_matches_old_shape = record_claim(
                archive, project, session, "the run completed", "verified",
                cites=["line:val_bpb:0.50"],
            )
        self.assertEqual(matches_new_anchor["data"]["grade"], "verified")
        self.assertEqual(no_longer_matches_old_shape["data"]["grade"], "hypothesis")


if __name__ == "__main__":
    unittest.main()
