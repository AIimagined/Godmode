"""godmode-replicate: the shipped bundle and its flow, step by step.

Plan 7 Task 14 (NS-9b): the skill fronts `parity --sources`, `read`,
`plant`, `verify`, `claim --verify`, `hooks status --matrix` and `privacy
--repo`. Each step runs here on a bare non-git temp project with a local
reference tree beside it - never the live archive.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _skill_faces as faces  # noqa: E402

NAME = "godmode-replicate"
SKILL_DIR = faces.skill_dir(NAME)

_REBUILD = "def quote_word(text):\n    return \"'\" + text.replace(\"'\", \"''\") + \"'\"\n"
_PIN = (
    "import unittest\n"
    "from quoting import quote_word\n\n"
    "class QuoteTests(unittest.TestCase):\n"
    "    def test_embedded_quote_is_doubled(self):\n"
    "        self.assertEqual(quote_word(\"a'b\"), \"'a''b'\")\n"
)
_WEAK_PIN = (
    "import unittest\n"
    "import quoting\n\n"
    "class QuoteTests(unittest.TestCase):\n"
    "    def test_module_imports(self):\n"
    "        self.assertTrue(hasattr(quoting, 'quote_word'))\n"
)


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

    def test_plant_precedes_verify_in_the_flow(self) -> None:
        commands = faces.flow_commands(SKILL_DIR)
        plant = next(i for i, c in enumerate(commands) if c.startswith("godmode plant"))
        verify = next(i for i, c in enumerate(commands) if c.startswith("godmode verify"))
        self.assertLess(plant, verify)


def _fixture(project: Path) -> tuple[Path, str]:
    ref = project.parent / "reference"
    ref.mkdir()
    (ref / "impl.py").write_text("def q(s):\n    return \"'\" + s.replace(\"'\", \"''\") + \"'\"\n",
                                 encoding="utf-8")
    (project / "quoting.py").write_text(_REBUILD, encoding="utf-8")
    command = f'"{sys.executable}" -m unittest test_quoting'
    return ref, command


class FlowTests(unittest.TestCase):
    def test_flow_in_order(self) -> None:
        with faces.isolated_project() as (project, _archive):
            run = lambda *a: faces.run(project, *a)  # noqa: E731
            ref, command = _fixture(project)
            (project / "test_quoting.py").write_text(_PIN, encoding="utf-8")
            self.assertEqual(run("session", "open")[0], 0)

            # Step 1: the reference is receipted and not surface-only.
            code, receipt = run("read", "--source", "quoting-ref", "--path", "impl.py",
                                "--root", str(ref), "--lines", "1-2")
            self.assertEqual(code, 0, receipt)
            receipt_seq = receipt["record"]["sequence"]
            code, depth = run("parity", "--sources")
            self.assertEqual(code, 0, depth)
            self.assertFalse(depth["sources"]["quoting-ref"]["surface_only"])

            # Step 3: the pinning test fails on a planted break; the file is restored.
            code, planted = run("plant", "quote-pin", "--command", command,
                                "--file", "quoting.py", "--replace", ".replace(",
                                "--with", ".strip() or (")
            self.assertEqual(code, 0, planted)
            self.assertTrue(planted["observed_failing"])
            self.assertEqual((project / "quoting.py").read_text(encoding="utf-8"), _REBUILD)

            # Step 4: attested green on the real rebuild.
            code, verified = run("verify", "quote-pin", "--command", command)
            self.assertEqual(code, 0, verified)
            self.assertTrue(verified["passed"])

            # Step 5: the claim cites the receipt by sequence plus the test, and holds.
            code, claim = run("claim", "quoting replicated from its reference",
                              "--grade", "verified", "--cite", f"seq:{receipt_seq}",
                              "--cite", f"cmd:{command}", "--verify")
            self.assertEqual(code, 0, claim)
            self.assertEqual(claim["grade"], "verified")
            code, matrix = run("hooks", "status", "--matrix")
            self.assertIn(code, (0, 1, 2), matrix)

            # Step 6: outside git the tracked-tree scan refuses rather than passing.
            code, scan = run("privacy", "--repo")
            self.assertNotEqual(code, 0, scan)

    def test_step3_a_pin_that_cannot_fail_is_not_counted(self) -> None:
        with faces.isolated_project() as (project, _archive):
            _ref, command = _fixture(project)
            (project / "test_quoting.py").write_text(_WEAK_PIN, encoding="utf-8")
            self.assertEqual(faces.run(project, "session", "open")[0], 0)
            code, planted = faces.run(project, "plant", "quote-pin", "--command", command,
                                      "--file", "quoting.py", "--replace", ".replace(",
                                      "--with", ".strip() or (")
            self.assertFalse(planted.get("observed_failing", False), planted)
            self.assertEqual((project / "quoting.py").read_text(encoding="utf-8"), _REBUILD)


if __name__ == "__main__":
    unittest.main()
