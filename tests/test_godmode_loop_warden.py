"""godmode-loop-warden: the shipped bundle and its flow, step by step.

The skill fronts `loop --preflight`, `loop declare`, `loop tick`, `loop
--transcript --episodes`, `loop --blame` and `loop close`. Each step runs
here on a bare non-git temp project - never the live archive.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-loop-warden"
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

    def test_the_cap_is_declared_before_any_tick(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        declare = next(i for i, c in enumerate(commands) if c.startswith("godmode loop declare"))
        tick = next(i for i, c in enumerate(commands) if c.startswith("godmode loop tick"))
        self.assertLess(declare, tick)


class FlowTests(unittest.TestCase):
    def test_a_capped_loop_refuses_a_tick_past_the_cap_and_closes_cut_off(self) -> None:
        with faces.isolated_project() as (project, archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            code, declared = run("loop", "declare", "retry-parse", "--max-iterations", "2",
                                 "--stop-when", "the parser test passes")
            self.assertEqual(code, 0, declared)
            self.assertEqual(run("loop", "tick", "retry-parse", "--note", "first")[0], 0)
            self.assertEqual(run("loop", "tick", "retry-parse", "--note", "second")[0], 0)
            code, refused = run("loop", "tick", "retry-parse", "--note", "third")
            self.assertNotEqual(code, 0, refused)
            tick = archive.read_events()[-1]
            code, closed = run("loop", "close", "retry-parse", "--outcome", "cut-off",
                               "--evidence", f"seq:{tick['sequence']}")
            self.assertEqual(code, 0, closed)
            self.assertEqual(closed["record"]["data"]["outcome"], "cut-off")

    def test_empty_ticks_escalate(self) -> None:
        with faces.isolated_project() as (project, _archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            self.assertEqual(run("loop", "declare", "stall", "--max-iterations", "9",
                                 "--stop-when", "the build is green")[0], 0)
            codes = [run("loop", "tick", "stall", "--empty")[0] for _ in range(4)]
            self.assertIn(1, codes, "consecutive empty iterations escalate with exit 1")


if __name__ == "__main__":
    unittest.main()
