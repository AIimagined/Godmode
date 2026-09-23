"""godmode-impact-gate: the shipped bundle and its flow, step by step.

Plan 7 Task 13 (NS-9): the skill fronts `scope --minimality`, `atlas graph
verify|rebuild`, `atlas closure`, `atlas --direction`, `fence audit`,
`precheck --changed`, `retest --run` and, as its named escape hatch,
`remember --kind decision --subject impact-accepted:<path>`. Each step runs
here on a bare non-git temp project - never the live archive.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-impact-gate"
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

    def test_graph_verify_precedes_closure_in_the_flow(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        verify = commands.index("godmode atlas graph verify")
        closure = next(i for i, c in enumerate(commands) if c.startswith("godmode atlas closure"))
        hatch = next(i for i, c in enumerate(commands) if "impact-accepted:" in c)
        retest = commands.index("godmode retest --run")
        self.assertLess(verify, closure)
        # The escape hatch is recorded only after every check that could fail.
        self.assertLess(closure, hatch)
        self.assertLess(retest, hatch)


def _write(project: Path, relative: str, body: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class FlowTests(unittest.TestCase):
    def test_flow_in_order(self) -> None:
        with faces.isolated_project() as (project, _archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            _write(project, "widget.py", "def widget():\n    return 1\n")
            _write(project, "user.py", "from widget import widget\n\ndef use():\n    return widget()\n")

            # Step 1: steps 6 and 7 refuse without a session.
            self.assertNotEqual(run("retest", "--run")[0], 0)
            self.assertEqual(run("session", "open")[0], 0)
            # Outside git, scope says so instead of guessing.
            code, scope = run("scope", "--minimality")
            self.assertEqual(code, 0, scope)
            self.assertEqual(scope["verdict"], "unavailable")

            # Step 2: no snapshot yet - verify refuses, then rebuild, then verify holds.
            code, unproven = run("atlas", "graph", "verify")
            self.assertEqual(code, 1, unproven)
            self.assertFalse(unproven["verified"])
            self.assertEqual(run("atlas", "graph", "rebuild")[0], 0)
            code, proven = run("atlas", "graph", "verify")
            self.assertEqual(code, 0, proven)

            # Step 3: the fan-out names the unfollowed dependent.
            code, closure = run("atlas", "closure", "--changed", "widget.py", "--depth", "2")
            self.assertEqual(code, 1, closure)
            self.assertIn("user.py", {f["dependent"] for f in closure["findings"]})

            # Step 5 and 6: fence and paired artifacts report, never block.
            code, fence = run("fence", "audit", "--changed", "widget.py")
            self.assertEqual(code, 0, fence)
            code, paired = run("precheck", "--about", "commit the widget edit",
                               "--changed", "widget.py")
            self.assertEqual(code, 0, paired)
            self.assertEqual(paired["paired_artifacts"]["verdict"], "paired-or-clean")

            # Step 7: the retests the closure refusal will demand.
            code, retest = run("retest", "--run")
            self.assertEqual(code, 0, retest)

            # Step 8: the escape hatch is a recorded, named decision.
            code, accepted = run("remember", "--kind", "decision",
                                 "--subject", "impact-accepted:widget.py",
                                 "--value", "user.py reads widget() unchanged; its value is stable",
                                 "--evidence", "seq:1")
            self.assertEqual(code, 0, accepted)
            self.assertEqual(accepted["record"]["subject"], "impact-accepted:widget.py")

    def test_step4_direction_names_a_reverse_import(self) -> None:
        with faces.isolated_project() as (project, _archive):
            _write(project, "hooks/__init__.py", "")
            _write(project, "hooks/entry.py", "VALUE = 1\n")
            _write(project, "scripts/godmode_runtime/__init__.py", "")
            _write(project, "scripts/godmode_runtime/core.py", "import hooks.entry\n")
            code, report = faces.run(project, "atlas", "--direction")
            self.assertEqual(code, 1, report)


if __name__ == "__main__":
    unittest.main()
