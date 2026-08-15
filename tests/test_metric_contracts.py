"""U-T3: anchored-metric contracts.

Numeric claims cite an output line matching a registered anchored pattern,
never a paraphrase. `register_metric_contract` declares a `^name:`-style
anchor as a `decision` record under subject `metric-contract:<name>`,
validated at registration: it must compile as a regex, stay under a length
cap, and clear a nested-quantifier shape scan.

That third check is not decorative. A review round demonstrated `re.compile`
plus a length cap alone do NOT refuse a catastrophic pattern: `(a+)+b`
compiles fine and is well under the length cap, yet hangs the interpreter
once matched against a crafted `line:` value at grading time - the length
cap bounds the ANCHOR's length, which says nothing about the length of the
text later matched against it. Two independent layers close this: the
registration-time shape scan (`CatastrophicPatternTests` below), and a hard
cap on the matched VALUE's length before any regex runs at grading time
(`GradingTimeValueCapTests`) - the second holding even for a shape the first
misses.

A claim naming a registered metric and a number is cross-checked against any
`line:<name>:<value>` citation it carries: a matching value stays verified,
a mismatched one is downgraded naming BOTH numbers, and a metric name that
was never registered gets no friction from this at all.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
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


class CatastrophicPatternTests(unittest.TestCase):
    """Layer 1: registration-time refusal of the named nested-quantifier
    shapes. `re.compile` + a length cap alone let `(a+)+b` through a review
    round - it compiles fine, is well under the length cap, and hangs the
    interpreter once matched against a crafted `line:` value at grading time
    (`re.compile("(a+)+b").match("a" * 28)` did not return within 8s on this
    codebase's own interpreter - not reproduced here as a test, since a slow
    test that must hang to prove a point is worse than the review's own
    isolated repro; what belongs in the suite is the refusal below)."""

    def test_registering_a_nested_quantifier_shape_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            with self.assertRaises(ArchiveError) as caught:
                register_metric_contract(archive, session, "val_bpb", "(a+)+b")
        self.assertIn("(a+)+", str(caught.exception))

    def test_every_named_shape_is_refused(self) -> None:
        shapes = ["(a+)+", "(a*)+", "(a+)*", "(a*)*", "(a+){2,5}", "(a{2,5})+"]
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            for index, shape in enumerate(shapes):
                with self.assertRaises(ArchiveError, msg=shape):
                    register_metric_contract(archive, session, f"m{index}", shape)

    def test_a_legitimate_anchor_still_registers(self) -> None:
        """The heuristic must not false-positive on ordinary patterns."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            record = register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
        self.assertEqual(record["data"]["anchor"], "^val_bpb:")

    def test_a_single_quantified_group_with_no_outer_quantifier_registers(self) -> None:
        """`(\\d+\\.\\d+)$` has a quantifier INSIDE a group but no quantifier
        AFTER the group - not the dangerous shape, must not be flagged."""
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            record = register_metric_contract(
                archive, session, "val_bpb", r"^val_bpb: (\d+\.\d+)$")
        self.assertEqual(record["data"]["anchor"], r"^val_bpb: (\d+\.\d+)$")


class GradingTimeValueCapTests(unittest.TestCase):
    """Layer 2: the matched `line:` value is length-capped before any regex
    runs, independent of layer 1 - holds even for a shape the registration-
    time scan misses."""

    def test_a_5000_char_value_is_handled_well_under_a_second(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            start = time.monotonic()
            out = record_claim(
                archive, project, session, "val_bpb improved to 3.21", "verified",
                cites=["line:val_bpb:" + ("9" * 5000)],
            )
            elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0, f"took {elapsed}s - the value cap did not hold")
        self.assertEqual(out["data"]["grade"], "hypothesis")

    def test_an_over_cap_value_citation_does_not_resolve(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            out = record_claim(
                archive, project, session, "the run completed", "verified",
                cites=["line:val_bpb:" + ("1" * 65)],
            )
        self.assertEqual(out["data"]["grade"], "hypothesis")
        self.assertIn("line:val_bpb:" + ("1" * 65), out["data"]["unresolved"])

    def test_a_value_at_exactly_the_cap_still_resolves(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "metrics")
            register_metric_contract(archive, session, "val_bpb", "^val_bpb:")
            value = "9" * 63 + "1"
            out = record_claim(
                archive, project, session, f"val_bpb improved to {value}", "verified",
                cites=[f"line:val_bpb:{value}"],
            )
        self.assertEqual(out["data"]["grade"], "verified")


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
