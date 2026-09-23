"""godmode-research: the shipped bundle and its flow, step by step.

Plan 7 Task 14 (NS-9b): the skill fronts `license check|attest`, `read`,
`upstream --path --skills|--dispose`, `parity --sources` and the `absorb:`
decision's two-verdict shape. Each step runs here on a bare non-git temp
project with a local reference tree beside it - never the live archive.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-research"
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

    def test_licence_comes_before_any_implementing_read(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        licence = next(i for i, c in enumerate(commands) if c.startswith("godmode license attest"))
        implementing = next(i for i, c in enumerate(commands)
                            if c.startswith("godmode read") and "<implementing file>" in c)
        self.assertLess(licence, implementing)


def _reference(base: Path) -> Path:
    ref = base / "reference"
    (ref / "src").mkdir(parents=True)
    (ref / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (ref / "README.md").write_text("# quoting\nQuotes shell words.\n", encoding="utf-8")
    (ref / "src" / "quote.py").write_text(
        "def quote(word):\n    return \"'\" + word.replace(\"'\", \"''\") + \"'\"\n",
        encoding="utf-8")
    return ref


class FlowTests(unittest.TestCase):
    def test_flow_in_order(self) -> None:
        with faces.isolated_project() as (project, _archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            ref = _reference(project.parent)

            # Step 1: licence first, receipted and classified.
            code, allowed = run("license", "check", "--operation", "survey quoting source")
            self.assertEqual(code, 0, allowed)
            code, _ = run("read", "--source", "quoting", "--path", "LICENSE", "--root", str(ref))
            self.assertEqual(code, 0)
            code, attested = run("license", "attest", "--repo", "quoting",
                                 "--classification", "permissive")
            self.assertEqual(code, 0, attested)

            # A surface-only reading so far: README next, then an adopt verdict is refused.
            code, _ = run("read", "--source", "quoting", "--path", "README.md", "--root", str(ref))
            self.assertEqual(code, 0)
            code, depth = run("parity", "--sources")
            self.assertEqual(code, 0, depth)
            self.assertEqual(depth["sources"]["quoting"]["files_opened"], 2)
            code, refused = run(
                "remember", "--kind", "decision", "--subject", "absorb:quoting 2026-09-23",
                "--value", "quotes words import_verdict: adopt behaviour_verdict: confirmed-dont",
                "--evidence", "receipt:quoting:README.md")
            self.assertNotEqual(code, 0, refused)
            self.assertIn("surface-only", str(refused))

            # Step 2: the tree pointer records nothing.
            code, pointer = run("upstream", "--path", str(ref), "--skills", "quote")
            self.assertEqual(code, 0, pointer)

            # Step 3 and 4: receipt the implementing file; the source is no longer surface-only.
            code, receipt = run("read", "--source", "quoting", "--path", "src/quote.py",
                                "--root", str(ref), "--lines", "1-2")
            self.assertEqual(code, 0, receipt)
            self.assertEqual(receipt["record"]["data"]["lines"], [1, 2])
            code, depth = run("parity", "--sources")
            self.assertEqual(code, 0, depth)
            self.assertFalse(depth["sources"]["quoting"]["surface_only"])
            self.assertGreaterEqual(depth["sources"]["quoting"]["files_opened"], 3)

            # Step 5: both verdicts, citing the implementing receipt, are accepted.
            code, accepted = run(
                "remember", "--kind", "decision", "--subject", "absorb:quoting 2026-09-23",
                "--value", "quotes words import_verdict: adopt behaviour_verdict: confirmed-dont",
                "--evidence", "receipt:quoting:src/quote.py")
            self.assertEqual(code, 0, accepted)

            # A decision missing its behaviour verdict is refused by name.
            code, half = run(
                "remember", "--kind", "decision", "--subject", "absorb:quoting 2026-09-24",
                "--value", "quotes words import_verdict: skip",
                "--evidence", "receipt:quoting:src/quote.py")
            self.assertNotEqual(code, 0, half)
            self.assertIn("behaviour_verdict", str(half))


if __name__ == "__main__":
    unittest.main()
