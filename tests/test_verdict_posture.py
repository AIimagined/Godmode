"""Executed-evidence bar for pass verdicts, and the dissent check.

A review that concludes PASS by reading alone is an opinion about
appearance. A verified claim whose text is a pass verdict needs a `cmd:`
citation - the thing was run, not admired. And a record window where no
check ever failed is not proof of flawless work; past a sample floor it
is evidence that no real check exists, and the doctor says so - as an
advisory, never a health flip.
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

from godmode_runtime.godmode_attest import (  # noqa: E402
    dissent_check,
    looks_like_pass_verdict,
    record_claim,
    resolve_claim,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class PassVerdictVocabularyTests(unittest.TestCase):
    def test_pass_verdicts_are_recognized(self) -> None:
        for text in (
            "review passed with no issues",
            "the code looks correct",
            "all checks pass",
            "no issues found in the diff",
        ):
            self.assertTrue(looks_like_pass_verdict(text)[0], text)

    def test_ordinary_claims_are_not(self) -> None:
        for text in (
            "the parser rejects empty input",
            "fixed the retry loop",
            "review found three problems",
        ):
            self.assertFalse(looks_like_pass_verdict(text)[0], text)


class ExecutedEvidenceBarTests(unittest.TestCase):
    def test_a_read_only_pass_verdict_downgrades(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "code.py").write_text("x = 1\n", encoding="utf-8")
            record = record_claim(
                archive, project, "S-test", "review passed with no issues",
                "verified", cites=["file:code.py"],
            )
            self.assertTrue(record["data"]["downgraded"])
            self.assertIn("run", record["data"]["reason"])

    def test_a_pass_verdict_with_an_executed_check_stands(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "code.py").write_text("x = 1\n", encoding="utf-8")
            record = record_claim(
                archive, project, "S-test", "review passed with no issues",
                "verified", cites=["file:code.py", "cmd:pytest -q"],
            )
            # The cmd citation clears THIS bar; other verified-grade
            # disciplines still apply to it independently.
            self.assertNotIn("run the thing", record["data"].get("reason", ""))


class DissentCheckTests(unittest.TestCase):
    def _all_pass(self, archive, project, n):
        (project / "README.md").write_text("x", encoding="utf-8")
        for i in range(n):
            claim = record_claim(archive, project, "S-test", f"claim {i}",
                                 "observed", confidence=0.9)
            resolve_claim(archive, project, "S-test", claim["sequence"],
                          "held", cites=["file:README.md"])

    def test_silence_below_the_sample_floor(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._all_pass(archive, project, 3)
            self.assertIsNone(dissent_check(archive))

    def test_an_all_pass_window_draws_the_advisory(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._all_pass(archive, project, 8)
            advisory = dissent_check(archive)
            self.assertIsNotNone(advisory)
            self.assertIn("no check has failed", advisory)

    def test_one_real_failure_keeps_it_silent(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self._all_pass(archive, project, 8)
            claim = record_claim(archive, project, "S-test", "risky",
                                 "observed", confidence=0.9)
            resolve_claim(archive, project, "S-test", claim["sequence"],
                          "failed", cites=["file:README.md"])
            self.assertIsNone(dissent_check(archive))


if __name__ == "__main__":
    unittest.main()
