"""godmode-ci: the shipped bundle and its flow.

The skill fronts `precheck`, `changelog check`, `precheck --preflight`
(with `--dirty` and shards), `selftest`, `grid`, `version --reconcile`,
`hooks probe` and `retest --run`. The bundle checks run here; the preflight
order itself is proven in tests/test_preflight_order.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-ci"
SKILL_DIR = faces.skill_dir(NAME)


class BundleTests(unittest.TestCase):
    def test_bundle_validates_and_lints(self) -> None:
        faces.assert_bundle(self, SKILL_DIR)

    def test_openai_yaml_is_hand_finished(self) -> None:
        faces.assert_openai_yaml_hand_finished(self, SKILL_DIR)

    def test_every_flow_verb_and_flag_exists(self) -> None:
        faces.assert_flow_verbs_exist(self, SKILL_DIR)

    def test_behaviour_assertions_are_read_only(self) -> None:
        faces.assert_assertions_read_only(self, SKILL_DIR)

    def test_routes_home_and_rejects_its_near_negatives(self) -> None:
        faces.assert_routes_cleanly(self, NAME)

    def test_forges_in_a_bare_temp_project(self) -> None:
        faces.assert_forges(self, SKILL_DIR)

    def test_cheap_gates_precede_the_preflight(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        precheck = next(i for i, c in enumerate(commands) if c.startswith("godmode precheck --about"))
        fragments = next(i for i, c in enumerate(commands) if c.startswith("godmode changelog check"))
        preflight = next(i for i, c in enumerate(commands) if c.startswith("godmode precheck --preflight"))
        self.assertLess(precheck, preflight)
        self.assertLess(fragments, preflight)


if __name__ == "__main__":
    unittest.main()
