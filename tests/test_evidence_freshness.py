"""Evidence from an earlier session is a memory, not an observation.

A failure taxonomy built from real coding-agent incidents lists reading an old
log as current evidence, and separately proving absence from a single probe that
found nothing. Both are the same move: treating a record of having looked once
as a standing fact.

A command citation already resolves only when an attestation records the run —
anyone can write the words, and only a run leaves the record. But it resolved
against a run from any session, at any distance in the past, so a claim made
today could rest on a command executed a fortnight ago against a tree that has
since changed.

And an absence claim could rest on one probe. A search that finds nothing is
evidence about where it looked; a second, different probe is what turns that
into a fact about what exists.
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

from godmode_runtime.godmode_attest import record_claim, record_step  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class FreshnessTests(unittest.TestCase):
    def test_a_command_run_this_session_supports_a_claim(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_step(archive, "now", "ran the check", "ran",
                        result="ok", evidence=["cmd:pytest -q"])
            record = record_claim(archive, project, "now",
                                  "the suite passes", "verified",
                                  cites=["cmd:pytest -q"])
        self.assertEqual(record["data"]["grade"], "verified")

    def test_a_command_run_in_an_earlier_session_does_not(self) -> None:
        """The record proves it ran once, not that it holds now."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_step(archive, "yesterday", "ran the check", "ran",
                        result="ok", evidence=["cmd:pytest -q"])
            record = record_claim(archive, project, "today",
                                  "the suite passes", "verified",
                                  cites=["cmd:pytest -q"])
        self.assertEqual(record["data"]["grade"], "hypothesis")
        self.assertIn("session", record["data"]["reason"])

    def test_the_reason_says_what_would_fix_it(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_step(archive, "yesterday", "ran it", "ran",
                        result="ok", evidence=["cmd:pytest -q"])
            record = record_claim(archive, project, "today", "the suite passes",
                                  "verified", cites=["cmd:pytest -q"])
        self.assertIn("run it again", record["data"]["reason"])


class AbsenceProbeTests(unittest.TestCase):
    """A search that found nothing is evidence about where it looked."""

    def test_one_probe_does_not_prove_absence(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_step(archive, "now", "searched", "empty",
                        result="no hits", evidence=["cmd:grep -r poster ."])
            record = record_claim(archive, project, "now",
                                  "no poster cache exists anywhere", "verified",
                                  cites=["cmd:grep -r poster ."])
        self.assertEqual(record["data"]["grade"], "hypothesis")

    def test_a_second_different_probe_does(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for command in ("cmd:grep -r poster .", "cmd:curl -s /api/poster"):
                record_step(archive, "now", "probed", "ran",
                            result="checked", evidence=[command])
            record = record_claim(
                archive, project, "now", "no poster cache exists anywhere",
                "verified",
                cites=["cmd:grep -r poster .", "cmd:curl -s /api/poster"])
        self.assertEqual(record["data"]["grade"], "verified")

    def test_an_ordinary_claim_needs_only_one_command(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_step(archive, "now", "ran", "ran", result="ok",
                        evidence=["cmd:pytest -q"])
            record = record_claim(archive, project, "now", "the suite passes",
                                  "verified", cites=["cmd:pytest -q"])
        self.assertEqual(record["data"]["grade"], "verified")


if __name__ == "__main__":
    unittest.main()
