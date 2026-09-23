"""NS-12c: the eval harness can withhold what the project has learned.

A routing score taken with this project's lessons and compiled law in the
subject's brief measures the skill plus every correction the project has
already paid for. Withhold that layer and what is left is the skill. These
tests pin three things: the withholding is real (a skill carried by a
recorded correction scores lower without it), the two modes are recorded and
compared separately (neither can be held against, or overwrite, the other),
and the layer withheld is genuinely the lessons-and-law layer of the brief
rather than a filename this module happens to know.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_evals  # noqa: E402
from godmode_runtime.godmode_corpus import MEMORY_ROLES, build_brief  # noqa: E402


def _write_suite(root: Path, skill: str, description: str,
                 positive: list[str], near_negative: list[str],
                 assertions: list | None = None) -> None:
    directory = root / "skills" / skill
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: {description}\n---\n\n# {skill}\n",
        encoding="utf-8",
    )
    (directory / "godmode-evals.json").write_text(
        json.dumps({
            "schema": godmode_evals.EVAL_SCHEMA,
            "skill": skill,
            "routing": {"positive": positive, "near_negative": near_negative},
            "behavior_assertions": assertions if assertions is not None else [],
        }),
        encoding="utf-8",
    )


def _carried_by_memory(root: Path) -> None:
    """Two skills, and one `alpha` prompt whose wording belongs to `beta`.

    Nothing in alpha's own description or other prompt reaches that wording,
    so on the skill text alone it routes to beta. A single recorded guard
    naming alpha carries it home - which is exactly the kind of score the
    withheld mode exists to strip back out.
    """
    _write_suite(
        root, "alpha", "Tune telescope optics and tracking mounts.",
        ["Tune the telescope optics before the viewing night.",
         "Reconcile the quarterly balances before the invoice audit closes."],
        [],
    )
    _write_suite(
        root, "beta", "Compile quarterly balances for each invoice audit.",
        ["Compile the quarterly balances for the invoice audit."],
        [],
    )
    (root / "GODMODE-CODE-OF-LAW.md").write_text(
        "# Law\n\n## Law 1 - reach for alpha on balance work\n"
        "Guard: alpha handles reconcile quarterly balances invoice audit closes.\n",
        encoding="utf-8",
    )


class MemoryCarriesRoutingTests(unittest.TestCase):
    def test_a_guard_that_names_a_skill_lifts_it_and_withholding_drops_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _carried_by_memory(root)

            with_memory = godmode_evals.routing_scores(root)
            withheld = godmode_evals.routing_scores(root, withhold_memory=True)

        self.assertEqual(with_memory["alpha"]["score"], 1.0, with_memory)
        self.assertEqual(with_memory["alpha"]["positive_hit"], 2)
        # Withheld, the prompt the guard carried routes to the sibling whose
        # own words it uses: one of two positives, and a score to match.
        self.assertEqual(withheld["alpha"]["positive_hit"], 1, withheld)
        self.assertEqual(withheld["alpha"]["score"], 0.5, withheld)
        self.assertLess(withheld["alpha"]["score"], with_memory["alpha"]["score"])

    def test_the_report_names_which_skills_the_memory_layer_spoke_about(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _carried_by_memory(root)
            with_memory = godmode_evals.run_routing_evals(root)
            withheld = godmode_evals.run_routing_evals(root, withhold_memory=True)

        self.assertEqual(with_memory["memory_named_skills"], ["alpha"])
        self.assertFalse(with_memory["withhold_memory"])
        self.assertEqual(withheld["memory_named_skills"], [])
        self.assertTrue(withheld["withhold_memory"])

    def test_a_namespace_word_is_not_a_reference_to_the_skill_that_owns_it(self) -> None:
        # `gm` is a skill AND the prefix `gm-audit` extends. Prose that says
        # "gm" is spelling the command, not naming the umbrella skill, so it
        # must not hand the umbrella the memory layer as vocabulary.
        self.assertEqual(godmode_evals._referable_skill_names(["gm", "gm-audit"]), ["gm-audit"])
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_suite(root, "gm", "Route a request to the skill that fits it.",
                         ["Which skill should handle this request?"], [])
            _write_suite(root, "gm-audit", "Compile quarterly balances for each invoice audit.",
                         ["Compile the quarterly balances for the invoice audit."], [])
            (root / "GODMODE-CODE-OF-LAW.md").write_text(
                "Guard: run gm remember before closing quarterly balances "
                "on any invoice audit.\n", encoding="utf-8")

            with_memory = godmode_evals.run_routing_evals(root)
            withheld = godmode_evals.run_routing_evals(root, withhold_memory=True)

        self.assertEqual(with_memory["memory_named_skills"], [])
        self.assertEqual(
            godmode_evals._route_table(with_memory), godmode_evals._route_table(withheld),
            "a line that only spells the command must change no route")

    def test_this_project_is_measured_in_both_modes(self) -> None:
        # The committed baseline carries a block per mode, and this project
        # holds its floor in each of them. Reading one mode never falls back
        # to the other, so a clean verdict here is a real comparison twice.
        for withhold in (False, True):
            report = godmode_evals.ratchet(PLUGIN_ROOT, withhold_memory=withhold)
            self.assertEqual(report["verdict"], "clean", report)
            self.assertEqual(report["withhold_memory"], withhold)
            self.assertIsNotNone(report["baseline"], report)
            self.assertIn("godmode-host-sync", report["baseline"])


class DualBaselineTests(unittest.TestCase):
    ROW = {"score": 1.0, "positive_total": 2, "negative_total": 2}

    def _scores(self, score: float) -> dict[str, dict[str, float | int]]:
        return {"alpha": {**self.ROW, "score": score}}

    def test_each_mode_reads_only_its_own_block(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            godmode_evals._write_baseline(root, self._scores(1.0), withhold_memory=False)
            godmode_evals._write_baseline(root, self._scores(0.5), withhold_memory=True)

            kept = godmode_evals._read_baseline(root)
            ablated = godmode_evals._read_baseline(root, withhold_memory=True)

        self.assertEqual(kept["alpha"]["score"], 1.0)
        self.assertEqual(ablated["alpha"]["score"], 0.5)

    def test_a_write_in_one_mode_leaves_the_other_block_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            godmode_evals._write_baseline(root, self._scores(1.0), withhold_memory=False)
            godmode_evals._write_baseline(root, self._scores(0.25), withhold_memory=True)
            godmode_evals._write_baseline(root, self._scores(0.75), withhold_memory=True)

            self.assertEqual(godmode_evals._read_baseline(root)["alpha"]["score"], 1.0)
            self.assertEqual(
                godmode_evals._read_baseline(root, withhold_memory=True)["alpha"]["score"], 0.75)
            blocks = godmode_evals._baseline_blocks(root)

        self.assertEqual([block["withhold_memory"] for block in blocks], [False, True])

    def test_a_mode_with_no_block_reads_as_no_baseline_not_the_other_block(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            godmode_evals._write_baseline(root, self._scores(1.0), withhold_memory=False)
            self.assertIsNotNone(godmode_evals._read_baseline(root))
            self.assertIsNone(godmode_evals._read_baseline(root, withhold_memory=True))

    def test_the_ratchet_compares_like_with_like(self) -> None:
        # A withheld run scoring 0.5 against a withheld floor of 0.5 is clean;
        # held against the with-memory floor of 1.0 it would read as a
        # regression, which is the comparison this mode must never make.
        def by_mode(project, withhold_memory=False):
            return self._scores(0.5 if withhold_memory else 1.0)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            godmode_evals._write_baseline(root, self._scores(1.0), withhold_memory=False)
            godmode_evals._write_baseline(root, self._scores(0.5), withhold_memory=True)
            with mock.patch.object(godmode_evals, "routing_scores", side_effect=by_mode):
                kept = godmode_evals.ratchet(root)
                ablated = godmode_evals.ratchet(root, withhold_memory=True)

        self.assertEqual(kept["verdict"], "clean", kept)
        self.assertEqual(ablated["verdict"], "clean", ablated)
        self.assertEqual(ablated["baseline"]["alpha"], 0.5)

    def test_a_regression_inside_one_mode_is_still_a_regression(self) -> None:
        def by_mode(project, withhold_memory=False):
            return self._scores(0.25 if withhold_memory else 1.0)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            godmode_evals._write_baseline(root, self._scores(1.0), withhold_memory=False)
            godmode_evals._write_baseline(root, self._scores(0.5), withhold_memory=True)
            with mock.patch.object(godmode_evals, "routing_scores", side_effect=by_mode):
                ablated = godmode_evals.ratchet(root, write=True, withhold_memory=True)
            # Refused: the file still holds the floor it held before.
            self.assertEqual(
                godmode_evals._read_baseline(root, withhold_memory=True)["alpha"]["score"], 0.5)

        self.assertEqual(ablated["verdict"], "regression", ablated)


class WithheldBriefTests(unittest.TestCase):
    def test_the_brief_drops_the_memory_roles_and_names_them(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "docs").mkdir()
            (root / "GODMODE.md").write_text(
                "# Guide\n\nHow this project builds and releases.\n", encoding="utf-8")
            (root / "docs" / "LESSONS.md").write_text(
                "# Lessons\n\nA recorded correction about release order.\n", encoding="utf-8")
            (root / "GODMODE-CODE-OF-LAW.md").write_text(
                "# Law\n\nGuard: never release without a fragment.\n", encoding="utf-8")

            full = build_brief(root, "release order", 4000)
            ablated = build_brief(root, "release order", 4000, withhold_memory=True)

        paths = {Path(entry["path"]).name for entry in full["context"]}
        self.assertIn("LESSONS.md", paths)
        self.assertIn("GODMODE-CODE-OF-LAW.md", paths)

        ablated_paths = {Path(entry["path"]).name for entry in ablated["context"]}
        self.assertEqual(ablated_paths, {"GODMODE.md"})
        self.assertEqual(sorted(ablated["withheld_roles"]), sorted(MEMORY_ROLES))
        self.assertNotIn("withheld_roles", full,
                         "an ordinary brief keeps the shape every host already reads")

    def test_a_behaviour_probe_is_told_which_mode_it_runs_under(self) -> None:
        probe = ("python -c \"import os; "
                 "print(os.environ.get('GODMODE_WITHHOLD_MEMORY', 'absent'))\"")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_suite(
                root, "alpha", "Report the mode the harness runs under.", [], [],
                assertions=[{"assert": "the probe sees the withheld mode",
                             "check": {"command": probe, "expect_contains": "1"}}],
            )
            ablated = godmode_evals.run_behavior_assertions(root, withhold_memory=True)
            ordinary = godmode_evals.run_behavior_assertions(root)

        self.assertEqual(ablated["skills"]["alpha"]["passed"], 1, ablated)
        self.assertTrue(ablated["withhold_memory"])
        self.assertEqual(ordinary["skills"]["alpha"]["failed"], 1, ordinary)
        self.assertIn("absent", ordinary["skills"]["alpha"]["assertions"][0]["observed"])

    def test_the_ranking_snapshot_is_not_diffed_across_modes(self) -> None:
        report = godmode_evals.ranking_snapshot(PLUGIN_ROOT, withhold_memory=True)
        self.assertEqual(report["verdict"], "ranking-mode-withheld", report)
        self.assertEqual(report["diffs"], [])
        self.assertTrue(report["withheld_roles"], report)


class CommandSurfaceTests(unittest.TestCase):
    def test_the_flag_is_on_the_verb(self) -> None:
        from godmode_runtime.godmode_console import _build_parser

        args = _build_parser().parse_args(["evals", "--withhold-memory", "--ratchet"])
        self.assertTrue(args.withhold_memory)
        self.assertFalse(_build_parser().parse_args(["evals"]).withhold_memory)

    def test_a_withheld_run_cannot_freeze_the_with_memory_fixtures(self) -> None:
        from godmode_runtime.godmode_console import cmd_evals
        from godmode_runtime.godmode_errors import ArchiveError

        runtime = types.SimpleNamespace(
            anchor=types.SimpleNamespace(project_root=str(PLUGIN_ROOT)))
        args = argparse.Namespace(write_snapshots=True, withhold_memory=True)
        with self.assertRaises(ArchiveError) as caught:
            cmd_evals(args, runtime)
        self.assertIn("--withhold-memory", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
