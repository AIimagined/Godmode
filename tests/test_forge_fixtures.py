"""C-23: the skill generator writes expected-output fixtures per platform.

A forged skill already carries routing cases and behaviour assertions in
`godmode-evals.json`. What it lacked was a per-host statement of what the
skill is expected to produce when triggered - the thing a host's own eval
runner compares against. One fixture per known host, seeded from the
proposal's positive triggers and assertions, and `validate_skill` counts
them so a skill missing a host's fixture is not `valid`.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_forge import (  # noqa: E402
    FIXTURE_HOSTS, SkillProposal, forge_skill, validate_skill,
)


def _proposal() -> SkillProposal:
    return SkillProposal(
        name="release-observer",
        purpose="Summarize release evidence: without mutating repository state",
        gap_evidence="Two release reviews lacked one repeatable evidence summary.",
        repeated_uses=2,
        positive_triggers=(
            "a release review needs a bounded evidence summary",
            "a version handoff needs fresh verification",
        ),
        negative_triggers=(
            "the user asks to publish a release",
            "the user only asks for the current version number",
        ),
        assertions=(
            "The result lists the inspected version and verification evidence",
        ),
    )


class ForgeFixtureTests(unittest.TestCase):
    def test_one_expected_output_fixture_per_known_host(self) -> None:
        self.assertGreaterEqual(len(FIXTURE_HOSTS), 3)
        with tempfile.TemporaryDirectory() as temporary:
            skill = forge_skill(Path(temporary), _proposal())
            for host in FIXTURE_HOSTS:
                path = skill / "fixtures" / host / "expected.json"
                self.assertTrue(path.is_file(), f"no fixture for {host}")
                fixture = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(fixture["host"], host)
                self.assertEqual(fixture["skill"], "release-observer")
                # One case per positive trigger; every case states what the
                # skill is expected to produce, not merely that it fires.
                self.assertEqual(len(fixture["cases"]), 2)
                for case in fixture["cases"]:
                    self.assertTrue(case["trigger"])
                    self.assertEqual(case["expected"], list(_proposal().assertions))

    def test_validate_counts_fixtures_and_refuses_a_missing_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = forge_skill(Path(temporary), _proposal())
            self.assertEqual(validate_skill(skill)["fixture_hosts"], len(FIXTURE_HOSTS))
            (skill / "fixtures" / FIXTURE_HOSTS[0] / "expected.json").unlink()
            with self.assertRaises(Exception) as caught:
                validate_skill(skill)
            self.assertIn("fixture", str(caught.exception).lower())


if __name__ == "__main__":
    unittest.main()
