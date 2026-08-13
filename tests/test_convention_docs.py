"""A detector whose input convention nobody knows is a dead gate.

Absorbed 2026-08-13 alongside the M18-M22 mistake detectors: the evidence
prefixes they read (searched:, control:, second:, population:) and the
absorption-verdict record shape (import_verdict/behaviour_verdict) needed to
be taught somewhere an operator or agent actually looks - claim --help and
the two skills that route to this territory.

Researching this surfaced a real bug the docs would otherwise have shipped
false: `_citation_resolves`'s fallback was a bare `return False`, so citing
searched:/control:/second: (the exact vocabulary the docs teach) silently
downgraded a claim - punishing the evidence discipline the detectors exist
to reward. Fixed alongside the docs; pinned here, not just narrated.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402

PREFIXES = ("searched:", "control:", "second:", "scanned:", "population:",
           "file:", "cmd:", "rec:")


class ConventionDocsTests(unittest.TestCase):
    def test_claim_help_names_every_prefix(self) -> None:
        out = subprocess.run(
            [sys.executable, "scripts/godmode.py", "claim", "--help"],
            capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout
        for prefix in PREFIXES:
            self.assertIn(prefix, out, f"claim --help does not teach {prefix}")

    def test_investigation_skill_names_the_absence_protocol(self) -> None:
        text = (PLUGIN_ROOT / "skills" / "godmode-investigation" /
                "SKILL.md").read_text(encoding="utf-8")
        for needle in ("control:", "second:", "searched:", "M21",
                      "cmd:", "downgrade"):
            self.assertIn(needle, text)

    def test_governance_skill_names_the_absorption_verdicts(self) -> None:
        text = (PLUGIN_ROOT / "skills" / "godmode-governance" /
                "SKILL.md").read_text(encoding="utf-8")
        for needle in ("absorb:", "import_verdict", "behaviour_verdict",
                      "upstream_verdicts"):
            self.assertIn(needle, text)


class CitationResolutionTests(unittest.TestCase):
    """The real bug the docs research caught: these prefixes must resolve."""

    def test_a_searched_citation_resolves(self) -> None:
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            rec = record_claim(
                archive, project, "S-test", "the guard rejects bad input",
                "verified", cites=["searched:rg dead_ref lib/ -> 0 hits"])
        self.assertNotIn("citation does not resolve",
                         rec["data"].get("reason", ""))

    def test_a_control_citation_resolves(self) -> None:
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            rec = record_claim(
                archive, project, "S-test", "the guard rejects bad input",
                "verified", cites=["control:rg live_ref lib/ -> 14 hits"])
        self.assertNotIn("citation does not resolve",
                         rec["data"].get("reason", ""))

    def test_a_second_citation_resolves(self) -> None:
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            rec = record_claim(
                archive, project, "S-test", "the guard rejects bad input",
                "verified", cites=["second:manual walkthrough confirmed it"])
        self.assertNotIn("citation does not resolve",
                         rec["data"].get("reason", ""))

    def test_a_scanned_citation_resolves(self) -> None:
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            rec = record_claim(
                archive, project, "S-test", "the guard rejects bad input",
                "verified", cites=["scanned:all 40 call sites in lib/"])
        self.assertNotIn("citation does not resolve",
                         rec["data"].get("reason", ""))

    def test_garbage_after_the_prefix_still_fails(self) -> None:
        # The plausibility floor still applies - a real prefix does not
        # launder an empty or control-character remainder into a resolved
        # citation.
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            rec = record_claim(
                archive, project, "S-test", "the guard rejects bad input",
                "verified", cites=["searched:\x01\x02"])
        self.assertIn("citation does not resolve", rec["data"].get("reason", ""))

    def test_an_unrelated_prefix_still_fails(self) -> None:
        from godmode_runtime.godmode_attest import record_claim
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            rec = record_claim(
                archive, project, "S-test", "the guard rejects bad input",
                "verified", cites=["invented:not a real prefix"])
        self.assertIn("citation does not resolve", rec["data"].get("reason", ""))


if __name__ == "__main__":
    unittest.main()
