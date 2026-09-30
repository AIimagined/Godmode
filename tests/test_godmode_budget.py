"""godmode-budget: the shipped bundle and its flow, step by step.

The skill fronts `ceilings --spent`, `trends`, `roi --sessions` and `roi
--releases`, `benchmark`, `metrics` and one `remember --kind decision`.
Each step runs here on a bare non-git temp project - never the live
archive.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-budget"
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

    def test_the_ceiling_check_comes_first(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        self.assertTrue(commands[0].startswith("godmode ceilings --spent"), commands[0])


class FlowTests(unittest.TestCase):
    def test_a_breached_ceiling_is_named_and_the_series_states_its_gaps(self) -> None:
        with faces.isolated_project() as (project, _archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tokens": 100, "tool_calls": 10}), encoding="utf-8")
            code, within = run("ceilings", "--spent", "tokens=50,tool_calls=3")
            self.assertEqual(code, 0, within)
            self.assertEqual(within["verdict"], "within-ceilings")
            code, over = run("ceilings", "--spent", "tokens=500,tool_calls=3")
            self.assertEqual(over["verdict"], "over-ceiling", over)
            self.assertIn("tokens", json.dumps(over))
            code, series = run("trends", "--sessions", "5")
            self.assertEqual(code, 0, series)
            code, fold = run("roi", "--sessions", "5")
            self.assertEqual(code, 0, fold)
            self.assertNotIn("caused", json.dumps(fold).lower())


if __name__ == "__main__":
    unittest.main()
