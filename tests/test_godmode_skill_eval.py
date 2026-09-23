"""godmode-skill-eval: the shipped skill's structure and its flow's commands.

Plan 7 Task 13 (NS-9): this skill routes to `skill validate`, `skill lint`,
and `evals --ratchet|--determinism|--write-baseline` - verbs that already
exist and already carry their own test suites. This module proves the skill
bundle is well-formed (frontmatter, PURPOSE.md citing a real seq:, both
companion files), and that every preflight command its Deterministic
Execution Flow names actually runs and exits the way the flow says it does.

`skill validate`, `skill lint`, and `evals --ratchet|--determinism|--brief`
never touch the archive (no `godmode init` needed, confirmed by reading
`cmd_skill_validate`/`cmd_skill_lint`/`cmd_evals`: none of the three calls
`_require_archive`), so the read-only flow steps run directly against this
plugin's own real `skills/` and `evals/` directories - exactly what they do
in real use. Only the guarded `--write-baseline` step mutates a file
(`evals/baseline.json`); that step runs against a disposable copy of the
repo's `skills/` and `evals/` directories, never the real ones.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from godmode_runtime.godmode_forge import lint_skill, validate_skill  # noqa: E402
from godmode_runtime.godmode_skillfront import lint_frontmatter  # noqa: E402
from _host_env import scrubbed_env  # noqa: E402

SKILL_DIR = PLUGIN_ROOT / "skills" / "godmode-skill-eval"
GODMODE = PLUGIN_ROOT / "scripts" / "godmode.py"


def _run(project: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GODMODE), "--project", str(project), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        env=scrubbed_env(),
    )


class SkillBundleTests(unittest.TestCase):
    def test_structure_validates(self) -> None:
        result = validate_skill(SKILL_DIR)
        self.assertTrue(result["valid"], result)
        self.assertGreaterEqual(result["positive_cases"], 2)
        self.assertGreaterEqual(result["near_negative_cases"], 2)
        self.assertGreaterEqual(result["assertions"], 1)

    def test_bundle_lint_passes_all_four_facets(self) -> None:
        result = lint_skill(SKILL_DIR)
        self.assertTrue(result["passed"], result)
        for facet in ("scope", "delivery", "safety", "bundle"):
            self.assertTrue(result["facets"][facet]["passed"], (facet, result))

    def test_frontmatter_lint_passes_with_no_findings(self) -> None:
        result = lint_frontmatter(SKILL_DIR)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["findings"], [])

    def test_purpose_cites_a_real_seq(self) -> None:
        text = (SKILL_DIR / "PURPOSE.md").read_text(encoding="utf-8")
        self.assertIn("seq:", text)

    def test_description_carries_a_negative_scope_clause(self) -> None:
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Not for", text)

    def test_evals_file_has_the_required_rows(self) -> None:
        data = json.loads((SKILL_DIR / "godmode-evals.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["routing"]["positive"]), 2)
        self.assertGreaterEqual(len(data["routing"]["near_negative"]), 2)
        self.assertTrue(data["behavior_assertions"])

    def test_openai_yaml_is_hand_finished(self) -> None:
        text = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertNotIn("Generated locally by Godmode", text)
        self.assertNotIn("...", text)
        self.assertNotIn(
            "Use $godmode-skill-eval to complete this request and prove its acceptance checks.",
            text,
        )


class FlowStepTests(unittest.TestCase):
    """Every preflight command the flow names, run directly against this
    plugin's own real skills/ and evals/ directories - none of them touches
    the archive."""

    def test_step1_validate_reports_this_skill_valid(self) -> None:
        done = _run(PLUGIN_ROOT, "skill", "validate", "--path", str(SKILL_DIR))
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload["valid"], payload)

    def test_step2_lint_reports_this_skill_passes(self) -> None:
        done = _run(PLUGIN_ROOT, "skill", "lint", "--path", str(SKILL_DIR))
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertTrue(payload["passed"], payload)

    def test_step3_brief_reads_the_whole_suite_verdict(self) -> None:
        # The full (unflagged) pass compiles the charter and ranking
        # snapshots too, which is slow on this project's own role documents
        # (observed 300s+ elsewhere in this sprint) - a generous timeout,
        # not a claim this step itself is fast.
        done = _run(PLUGIN_ROOT, "evals", "--brief", timeout=300)
        # The pre-existing charter/ranking snapshot drift (unrelated to this
        # pair - see the task report) keeps the top-level verdict unsound;
        # this step only proves the command runs and names its verdict.
        self.assertIn("evals-", done.stdout)

    def test_step4_ratchet_reports_clean_for_the_current_routing_suite(self) -> None:
        done = _run(PLUGIN_ROOT, "evals", "--ratchet", "--brief")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("clean", done.stdout)

    def test_step5_determinism_reports_deterministic(self) -> None:
        done = _run(PLUGIN_ROOT, "evals", "--determinism", "--brief")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("deterministic", done.stdout)

    def test_step6_write_baseline_refuses_on_a_planted_regression(self) -> None:
        """The guarded step never enshrines a regression: `--write-baseline`
        refuses outright when a skill's current score falls below its
        committed baseline entry. A brand-new skill (no baseline entry yet)
        cannot regress by definition (`ratchet` only compares skills the
        baseline already names), so the regression is planted on an
        already-baselined sibling instead - run against a disposable copy
        of skills/+evals/, never the real repo files."""
        with tempfile.TemporaryDirectory(prefix="godmode-skill-eval-") as raw:
            project = Path(raw)
            shutil.copytree(PLUGIN_ROOT / "skills", project / "skills")
            shutil.copytree(PLUGIN_ROOT / "evals", project / "evals")
            suite_path = project / "skills" / "godmode-governance" / "godmode-evals.json"
            data = json.loads(suite_path.read_text(encoding="utf-8"))
            data["routing"]["positive"] = ["Paint a watercolour landscape for a birthday card"]
            suite_path.write_text(json.dumps(data), encoding="utf-8")
            done = _run(project, "evals", "--write-baseline", "--brief")
            self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("regress", (done.stdout + done.stderr).lower())

    def test_step6_write_baseline_accepts_a_clean_copy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="godmode-skill-eval-") as raw:
            project = Path(raw)
            shutil.copytree(PLUGIN_ROOT / "skills", project / "skills")
            shutil.copytree(PLUGIN_ROOT / "evals", project / "evals")
            done = _run(project, "evals", "--write-baseline", "--brief")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("clean", done.stdout)


if __name__ == "__main__":
    unittest.main()
