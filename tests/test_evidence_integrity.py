"""Evidence-integrity detectors absorbed from a recorded lessons corpus.

Three classes, each recorded live before it was gated:

- An 865-test run piped through a 30-line tail lost its own summary line, so
  the count could not be verified without a full re-run (L-157/L-242/L-283).
- `sed -i` on source silently corrupts across escaping layers; four failures
  in one session (L-123/L-163).
- Models bold exactly the keywords a matcher anchors on, so a matcher that
  has never seen `**no evidence**` fires on plain text only (L-129).

Every detector test here carries its negative control: the planted violation
must be CAUGHT and the adjacent innocent form must PASS, or the guard is a
title with no assertion behind it (L-238/L-240).
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_mistakes import _prose  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    classify_action,
    evidence_pipe_advisory,
)


class EvidencePipeTests(unittest.TestCase):
    """A verdict-bearing run piped through a truncating filter is advised."""

    def test_test_run_piped_to_tail_is_flagged(self):
        advisory = evidence_pipe_advisory(
            "python -m unittest discover -s tests -v 2>&1 | tail -30")
        self.assertIsNotNone(advisory)
        self.assertIn("evidence-pipe", advisory)

    def test_pytest_piped_to_head_is_flagged(self):
        self.assertIsNotNone(evidence_pipe_advisory("pytest -q | head -5"))

    def test_powershell_select_object_last_is_flagged(self):
        # The exact command shape that lost the 865-test summary live.
        self.assertIsNotNone(evidence_pipe_advisory(
            "python -m unittest discover -s tests 2>&1 "
            "| Select-Object -Last 30"))

    def test_vitest_piped_to_grep_is_flagged(self):
        self.assertIsNotNone(
            evidence_pipe_advisory("npx vitest run | grep -i fail"))

    def test_capture_to_file_is_clean(self):
        # The honest form the advisory recommends must not itself be flagged.
        self.assertIsNone(evidence_pipe_advisory(
            "python -m unittest discover -s tests 2>&1 > full.log"))

    def test_plain_run_is_clean(self):
        self.assertIsNone(evidence_pipe_advisory("pytest -q"))

    def test_log_read_through_grep_is_clean(self):
        # Filtering a LOG is ordinary work; only verdict-bearing runners count.
        self.assertIsNone(evidence_pipe_advisory("cat build.log | grep error"))

    def test_filter_before_runner_is_clean(self):
        # The truncator must sit downstream of the runner to eat its verdict.
        self.assertIsNone(evidence_pipe_advisory(
            "grep -l TODO src/*.py | xargs pytest"))

    def test_godmodes_own_verdict_subcommands_are_covered(self):
        # Found by an adversarial pass: the runner regex covered
        # verify/gates/attest/precheck but missed selftest/scenarios/
        # mistakes/assess - every one of them equally verdict-bearing and
        # equally truncatable by the same pipe pattern.
        for sub in ("selftest", "scenarios", "mistakes", "assess"):
            self.assertIsNotNone(
                evidence_pipe_advisory(f"godmode {sub} | Select-Object -Last 5"),
                f"godmode {sub} should be a covered verdict runner")

    def test_godmodes_non_verdict_subcommands_stay_clean(self):
        # capabilities/inspect print data, not a pass/fail verdict; piping
        # them is ordinary work and must not be flagged.
        for sub in ("capabilities", "inspect"):
            self.assertIsNone(
                evidence_pipe_advisory(f"godmode {sub} | tail -5"),
                f"godmode {sub} should not be treated as a verdict runner")


class ScriptedSourceEditTests(unittest.TestCase):
    """In-place streamed regex edits are named, asked about, and explained."""

    def test_sed_in_place_is_named(self):
        verdict = classify_action("sed -i 's/old/new/' src/app.py")
        self.assertEqual(verdict["category"], "scripted-source-edit")
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["tier"], "R3")

    def test_perl_in_place_is_named(self):
        verdict = classify_action("perl -pi -e 's/old/new/' src/app.py")
        self.assertEqual(verdict["category"], "scripted-source-edit")

    def test_sed_long_flag_is_named(self):
        verdict = classify_action("sed --in-place 's/a/b/' config.yaml")
        self.assertEqual(verdict["category"], "scripted-source-edit")

    def test_sed_stream_read_is_not_flagged(self):
        # `sed -n '1,10p'` reads; only the in-place flag mutates.
        verdict = classify_action("sed -n '1,10p' src/app.py")
        self.assertNotEqual(verdict["category"], "scripted-source-edit")
        self.assertFalse(verdict["protected"])

    def test_naming_sed_inside_quotes_is_not_flagged(self):
        # Quoted spans are blanked before mutation patterns run.
        verdict = classify_action('echo "docs mention sed -i here"')
        self.assertNotEqual(verdict["category"], "scripted-source-edit")


class MarkdownNormalisationTests(unittest.TestCase):
    """Keyword matchers see through the emphasis models put on keywords."""

    def test_bold_is_stripped(self):
        self.assertEqual(_prose("**no evidence** of X"), "no evidence of X")

    def test_backticks_keep_content(self):
        self.assertEqual(_prose("`43 errors` today"), "43 errors today")

    def test_link_keeps_text_loses_target(self):
        self.assertEqual(
            _prose("see [the log](https://x.test/log)"), "see the log")

    def test_nested_emphasis_unwraps(self):
        self.assertEqual(_prose("***nothing found***"), "nothing found")

    def test_plain_text_is_untouched(self):
        text = "29 of 30 tests pass; the 30th is flaky"
        self.assertEqual(_prose(text), text)

    def test_multiplication_star_survives(self):
        # `3 * 4` is arithmetic, not emphasis; the pair rule needs closure.
        text = "spent 3 * 4 seconds"
        self.assertEqual(_prose(text), text)

    def test_detector_fires_through_bold(self):
        # End-to-end: emphasis INSIDE the phrase is the form that broke the
        # matcher - `no **evidence**` splits the literal the regex needs.
        # (Emphasis AROUND the whole phrase never broke it: `**` is a
        # non-word character, so `\b` held at both ends.) Planted, seen red.
        from godmode_runtime.godmode_mistakes import claim_from_a_sample
        records = [{
            "kind": "claim", "sequence": 1,
            "subject": "sweep result",
            "data": {"text": "no **evidence** anywhere in the tree"},
            "evidence": [],
        }]
        findings = claim_from_a_sample(records)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["detector"], "claim-from-a-sample")


class TheShapeThatActuallyFooledSomeone(unittest.TestCase):
    """2026-08-19: this advisory was right and nobody was listening.

    A full-suite run was reported GREEN on the strength of
    `python -m unittest discover -s tests 2>&1 | tail -4`. The pipeline's
    exit status is `tail`'s, so a red suite reported success, and one real
    defect rode that mistake for hours before an unpiped re-run found it.

    `evidence_pipe_advisory` already detected exactly this shape at the
    time. It never fired because the pre-tool hook was not wired into the
    host the work was happening in - the detector was correct and simply
    was not running. These pin the exact strings from that incident, so
    the detector cannot quietly stop covering the case that proved it
    matters, and pin the correct form as silent so the advisory stays
    actionable rather than something to tune out.
    """

    MASKED = (
        "python -m unittest discover -s tests 2>&1 | tail -4",
        'python -m unittest tests.test_gate_fast 2>&1 | grep -E "^(Ran|OK|FAILED)"',
        "python -m unittest discover -s tests 2>&1 | tail -5",
    )

    HONEST = (
        "python -m unittest discover -s tests > /tmp/suite.log 2>&1; echo EXIT=$?",
        "python -m unittest discover -s tests",
    )

    def test_every_masking_shape_from_the_incident_is_caught(self) -> None:
        for command in self.MASKED:
            with self.subTest(command=command):
                advisory = evidence_pipe_advisory(command)
                self.assertIsNotNone(advisory, command)
                self.assertIn("exit code", advisory)

    def test_capturing_to_a_file_and_reading_the_status_is_not_flagged(self) -> None:
        """The remedy the advisory names must itself be silent, or the
        advice is unfollowable."""
        for command in self.HONEST:
            with self.subTest(command=command):
                self.assertIsNone(evidence_pipe_advisory(command), command)


if __name__ == "__main__":
    unittest.main()
