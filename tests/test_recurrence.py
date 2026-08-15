"""U-E10: recurring-ask mining.

The request ledger (`godmode_requests`) already records every prompt as it
arrives. This module folds that ledger across sessions and reports a
normalized term set that recurred often enough to be worth a charter rule -
never writing one itself. These tests seed the ledger through the real
`record_request` writer (not a hand-built fixture) so the mining folds the
same record shape production writes.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_recurrence import (  # noqa: E402
    DEFAULT_THRESHOLD,
    mine_recurring_asks,
    render,
)
from godmode_runtime.godmode_requests import record_request  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _ask(archive, text: str, session: str) -> None:
    record_request(archive, text, session=session)


class ThresholdMet(unittest.TestCase):
    """3-session fixture, the same ask repeated a little differently each
    time: a candidate with per-session refs."""

    def test_a_repeated_ask_in_three_sessions_is_a_candidate(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _ask(archive, "please add dark mode support", session="S-1")
            _ask(archive, "add dark mode support please", session="S-2")
            _ask(archive, "please add dark mode support", session="S-3")

            report = mine_recurring_asks(archive)

            self.assertEqual(report["verdict"], "candidates-found", report)
            self.assertEqual(len(report["candidates"]), 1, report)
            candidate = report["candidates"][0]
            self.assertEqual(candidate["sessions"], 3)
            self.assertIn("dark", candidate["terms"])
            self.assertIn("mode", candidate["terms"])
            self.assertEqual(len(candidate["refs"]), 3)
            self.assertTrue(all(r.startswith("seq:") for r in candidate["refs"]))
            self.assertIn("asked in 3 sessions", candidate["note"])
            self.assertIn("SOFT rule candidate", candidate["note"])

    def test_the_default_threshold_is_three(self) -> None:
        self.assertEqual(DEFAULT_THRESHOLD, 3)

    def test_threshold_is_flag_tunable(self) -> None:
        """Two sessions clear a threshold of 2, even though they would not
        clear the default of 3."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _ask(archive, "rotate the deploy keys", session="S-1")
            _ask(archive, "rotate the deploy keys", session="S-2")

            default_report = mine_recurring_asks(archive)
            self.assertEqual(default_report["verdict"], "insufficient-data", default_report)

            tuned_report = mine_recurring_asks(archive, threshold=2)
            self.assertEqual(tuned_report["verdict"], "candidates-found", tuned_report)
            self.assertEqual(tuned_report["candidates"][0]["sessions"], 2)


class BelowThreshold(unittest.TestCase):
    """2-session ask, sitting beside enough other sessions that the ledger
    itself is not short: the cluster stays below threshold and is absent."""

    def test_an_ask_in_only_two_sessions_is_not_reported(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _ask(archive, "please rename the release branch", session="S-1")
            _ask(archive, "please rename the release branch", session="S-2")
            # A third, unrelated session keeps the ledger from reading as
            # short overall - the absence below is about this one cluster
            # missing the bar, not about there being too little data to judge.
            _ask(archive, "audit the billing webhook", session="S-3")

            report = mine_recurring_asks(archive)

            self.assertEqual(report["verdict"], "no-candidates", report)
            self.assertEqual(report["candidates"], [])
            self.assertEqual(report["sessions_seen"], 3)


class InsufficientData(unittest.TestCase):
    def test_an_empty_ledger_states_insufficient_data(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            report = mine_recurring_asks(archive)
            self.assertEqual(report["verdict"], "insufficient-data", report)
            self.assertEqual(report["sessions_seen"], 0)
            self.assertEqual(report["requests_seen"], 0)
            self.assertIn("0 distinct session", report["note"])

    def test_a_short_ledger_states_insufficient_data_with_the_count(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _ask(archive, "add a status page", session="S-1")
            report = mine_recurring_asks(archive)
            self.assertEqual(report["verdict"], "insufficient-data", report)
            self.assertEqual(report["sessions_seen"], 1)
            self.assertIn("1 distinct session", report["note"])

    def test_render_states_insufficient_data_honestly(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            text = render(mine_recurring_asks(archive))
            self.assertIn("Insufficient data", text)


class ContentFree(unittest.TestCase):
    """Counts and normalized terms only - a request can contain anything, and
    the report must never repeat its wording back."""

    def test_sentinel_sentence_structure_never_reaches_the_report(self) -> None:
        sentinel_phrase = "must never be echoed verbatim in this exact clause"
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(
                    archive,
                    f"SENTINEL_PROSE_MARKER_998877 {sentinel_phrase}",
                    session=session,
                )

            report = mine_recurring_asks(archive)
            rendered = render(report)
            dumped = json.dumps(report)

            # The bag-of-words reduction is allowed to surface individual
            # terms; the original sentence - order and adjacency - is not.
            self.assertNotIn(sentinel_phrase, rendered)
            self.assertNotIn(sentinel_phrase, dumped)
            # Nor does the original casing survive: only lowercased terms do.
            self.assertNotIn("SENTINEL_PROSE_MARKER_998877", rendered)
            self.assertNotIn("SENTINEL_PROSE_MARKER_998877", dumped)

    def test_a_candidate_carries_only_terms_and_refs(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please migrate the queue worker", session=session)
            candidate = mine_recurring_asks(archive)["candidates"][0]
            self.assertEqual(set(candidate.keys()), {"terms", "sessions", "refs", "note"})


class ProposalOnly(unittest.TestCase):
    """Same shape as `init --detect`: a candidate, never a written rule."""

    def test_mining_writes_nothing_to_the_archive(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please add a retry queue", session=session)
            before = len(archive.read_events())
            mine_recurring_asks(archive)
            after = len(archive.read_events())
            self.assertEqual(before, after)

    def test_the_render_names_it_a_proposal(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please add a retry queue", session=session)
            text = render(mine_recurring_asks(archive))
            self.assertIn("Proposals only", text)
            self.assertIn("nothing here writes a charter rule", text)


class ArchiveContractTests(unittest.TestCase):
    """Against the real CLI, not just the module function."""

    def test_the_recurring_subcommand_is_registered(self) -> None:
        from godmode_runtime.godmode_console import _build_parser

        parsed = _build_parser().parse_args(["recurring", "--threshold", "2"])
        self.assertEqual(parsed.threshold, 2)

    def test_the_recurring_command_runs_end_to_end(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please add a retry queue", session=session)

            from godmode_runtime.godmode_console import main

            exit_code = main(["--project", str(project), "--json", "recurring"])
            self.assertEqual(exit_code, 0)

    def test_a_request_without_a_session_id_is_not_attributed(self) -> None:
        """A record with no session cannot support a cross-session claim, so
        it must not silently inflate one cluster's session count."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "add a status page")  # no session=
            record_request(archive, "add a status page")
            record_request(archive, "add a status page")
            report = mine_recurring_asks(archive)
            self.assertEqual(report["verdict"], "insufficient-data", report)
            self.assertEqual(report["sessions_seen"], 0)
            self.assertEqual(report["requests_without_session"], 3)


class SessionlessExclusionStated(unittest.TestCase):
    """Minor from review round 1: the exclusion must be stated in the report,
    not left for a reader to infer from a count mismatch."""

    def test_the_count_is_in_the_report_dict(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please add a retry queue", session=session)
            record_request(archive, "no session on this one")  # no session=
            report = mine_recurring_asks(archive)
            self.assertEqual(report["verdict"], "candidates-found", report)
            self.assertEqual(report["requests_without_session"], 1)

    def test_the_count_is_named_in_render(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please add a retry queue", session=session)
            record_request(archive, "no session on this one")  # no session=
            text = render(mine_recurring_asks(archive))
            self.assertIn("Requests with no session on record: 1", text)
            self.assertIn("excluded", text)


class OpaqueTermRedaction(unittest.TestCase):
    """IMPORTANT from review round 1: a generic high-entropy token, matching
    none of the upstream secret scanner's curated vendor shapes, must not
    reach the report verbatim. Defense in depth lives inside this module -
    `_display_term` - because the upstream gate was never built to catch
    this shape of input.

    Red-first: this is the reviewer's own demonstrated leak, reproduced
    verbatim as the fixture.
    """

    # The reviewer's exact adversarial probe: a 40-character token with no
    # vendor prefix, no separators, and no dictionary shape - proven in the
    # review to survive `enforce_private_payload` and reach the archive.
    _GENERIC_TOKEN = "j8f2kd9s71ndkalpqmz8x7bv3wnfg5tq2hjrkl0p"

    def test_the_reviewers_token_is_redacted_to_a_shape_marker(self) -> None:
        assert len(self._GENERIC_TOKEN) == 40, "fixture drifted from the review"
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, self._GENERIC_TOKEN, session=session)

            report = mine_recurring_asks(archive)
            rendered = render(report)
            dumped = json.dumps(report)

            self.assertEqual(report["verdict"], "candidates-found", report)
            self.assertIn("<token:40ch>", rendered)
            self.assertIn("<token:40ch>", dumped)
            self.assertEqual(report["candidates"][0]["terms"], ["<token:40ch>"])

    def test_the_raw_token_never_appears_in_rendered_text_or_json(self) -> None:
        """The exact assertion the review asked for: grep count zero."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, self._GENERIC_TOKEN, session=session)

            report = mine_recurring_asks(archive)
            rendered = render(report)
            dumped = json.dumps(report)

            occurrences = rendered.count(self._GENERIC_TOKEN) + dumped.count(self._GENERIC_TOKEN)
            self.assertEqual(occurrences, 0, "the raw token must never appear in output")

    def test_ordinary_words_are_the_green_control_displayed_unchanged(self) -> None:
        """The redaction must be selective: a real word, even a longish
        compound one, is not mistaken for a token."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, "please migrate the queue worker", session=session)

            candidate = mine_recurring_asks(archive)["candidates"][0]
            self.assertIn("queue", candidate["terms"])
            self.assertIn("worker", candidate["terms"])
            self.assertIn("migrate", candidate["terms"])
            self.assertFalse(any(t.startswith("<token:") for t in candidate["terms"]))

    def test_a_short_alphanumeric_id_is_not_falsely_flagged(self) -> None:
        """Below the length floor, a short mixed-alnum term (a real ticket ID,
        say) is not treated as opaque - the predicate only fires on genuinely
        long, unworded strings."""
        from godmode_runtime.godmode_recurrence import _looks_opaque

        self.assertFalse(_looks_opaque("ABC123"))
        self.assertFalse(_looks_opaque("sha256"))

    def test_clustering_still_keys_on_the_raw_term_not_the_display_form(self) -> None:
        """Two different opaque tokens of the same length must not silently
        merge into one cluster just because they display identically."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            other_token = "z9q1wm4kd0xltbap2vhn7rfg8sc6yj3eou5tqk1nx"  # 41 chars
            self.assertNotEqual(len(other_token), len(self._GENERIC_TOKEN))
            for session in ("S-1", "S-2", "S-3"):
                _ask(archive, self._GENERIC_TOKEN, session=session)
            for session in ("S-4", "S-5", "S-6"):
                _ask(archive, other_token, session=session)

            report = mine_recurring_asks(archive)
            self.assertEqual(report["verdict"], "candidates-found", report)
            self.assertEqual(len(report["candidates"]), 2, report)


if __name__ == "__main__":
    unittest.main()
