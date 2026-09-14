"""Mutation tests for the three oracle-tamper rules (`godmode_tamper`).

Each rule has fixtures that must fire and near misses that must not. The
blind-spot tests assert the detector stays silent on shapes it cannot see, so
a later change that starts catching one fails loudly and the documented limit
is updated instead of silently going stale.
"""
from __future__ import annotations

import difflib
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_tamper as T  # noqa: E402


def run_rules(files: dict[str, tuple[str | None, str | None]], ci_scripts=()) -> list[dict]:
    """Build a git-shaped unified diff from (old, new) pairs and run the rules."""
    chunks: list[str] = []
    for path, (old, new) in files.items():
        chunks.append(f"diff --git a/{path} b/{path}\n")
        chunks.extend(difflib.unified_diff(
            old.splitlines(True) if old is not None else [],
            new.splitlines(True) if new is not None else [],
            f"a/{path}" if old is not None else "/dev/null",
            f"b/{path}" if new is not None else "/dev/null",
            n=3))
    old_sources = {p: o for p, (o, _n) in files.items() if o is not None}
    new_sources = {p: n for p, (_o, n) in files.items() if n is not None}
    return T.tamper_findings("".join(chunks), old_sources.get, new_sources.get, ci_scripts=ci_scripts)


def rules(findings: list[dict]) -> list[str]:
    return [f["rule"] for f in findings]


CODE_OLD = "def total(items):\n    return sum(items)\n"
CODE_NEW = "def total(items):\n    return sum(items) + 0\n"
CODE = ("app/billing.py", CODE_OLD, CODE_NEW)

TEST_OLD = (
    "import unittest\n"
    "from app.billing import total\n"
    "\n"
    "\n"
    "class TotalTests(unittest.TestCase):\n"
    "    def test_total(self):\n"
    "        self.assertEqual(total([2, 3]), 5)\n"
    "        self.assertEqual(total([]), 0)\n"
    "\n"
    "    def test_items(self):\n"
    "        self.assertGreaterEqual(len([1, 2, 3]), 3)\n"
)


def with_code(test_new: str, test_old: str = TEST_OLD, code=CODE) -> dict:
    return {code[0]: (code[1], code[2]), "tests/test_billing.py": (test_old, test_new)}


class RuleOneTestWeakenedWithCode(unittest.TestCase):
    def test_removed_assertion_with_code_change_fires(self) -> None:
        new = TEST_OLD.replace("        self.assertEqual(total([]), 0)\n", "")
        found = run_rules(with_code(new))
        self.assertEqual(rules(found), [T.RULE_TEST_WEAKENED])
        self.assertEqual(found[0]["path"], "tests/test_billing.py")
        self.assertIn("app/billing.py", found[0]["detail"])

    def test_assert_equal_loosened_to_assert_in_fires(self) -> None:
        new = TEST_OLD.replace("self.assertEqual(total([2, 3]), 5)", "self.assertIn(total([2, 3]), (5, 6))")
        self.assertEqual(rules(run_rules(with_code(new))), [T.RULE_TEST_WEAKENED])

    def test_exact_loosened_to_regex_fires(self) -> None:
        new = TEST_OLD.replace("self.assertEqual(total([2, 3]), 5)", "self.assertRegex(str(total([2, 3])), r'\\d')")
        self.assertEqual(rules(run_rules(with_code(new))), [T.RULE_TEST_WEAKENED])

    def test_bare_equality_loosened_to_truthiness_fires(self) -> None:
        old = "from app.billing import total\n\n\ndef test_total():\n    assert total([2, 3]) == 5\n"
        new = "from app.billing import total\n\n\ndef test_total():\n    assert total([2, 3])\n"
        self.assertEqual(rules(run_rules(with_code(new, old))), [T.RULE_TEST_WEAKENED])

    def test_reduced_count_fires(self) -> None:
        new = TEST_OLD.replace("assertGreaterEqual(len([1, 2, 3]), 3)", "assertGreaterEqual(len([1, 2, 3]), 1)")
        self.assertEqual(rules(run_rules(with_code(new))), [T.RULE_TEST_WEAKENED])

    def test_skip_added_fires(self) -> None:
        new = TEST_OLD.replace("    def test_total(self):\n",
                               "    @unittest.skip('flaky')\n    def test_total(self):\n")
        self.assertEqual(rules(run_rules(with_code(new))), [T.RULE_TEST_WEAKENED])

    def test_expected_failure_and_xfail_added_fire(self) -> None:
        for marker in ("@unittest.expectedFailure", "@pytest.mark.xfail(reason='later')"):
            with self.subTest(marker=marker):
                new = TEST_OLD.replace("    def test_total(self):\n",
                                       f"    {marker}\n    def test_total(self):\n")
                self.assertEqual(rules(run_rules(with_code(new))), [T.RULE_TEST_WEAKENED])

    def test_unconditional_skip_call_in_a_test_body_fires(self) -> None:
        new = TEST_OLD.replace("    def test_total(self):\n",
                               "    def test_total(self):\n        self.skipTest('later')\n")
        self.assertEqual(rules(run_rules(with_code(new))), [T.RULE_TEST_WEAKENED])

    def test_near_miss_environment_conditioned_skip_does_not_fire(self) -> None:
        """Measured on this repository's history: platform- and tool-gated
        skips were most of the rule's hits and none weakened a test on the
        machine that has the tool."""
        variants = (
            TEST_OLD.replace("    def test_total(self):\n",
                             "    @unittest.skipUnless(sys.platform == 'win32', 'cmd only')\n"
                             "    def test_total(self):\n"),
            TEST_OLD.replace("    def test_total(self):\n",
                             "    @pytest.mark.skipif(shutil.which('node') is None, reason='no node')\n"
                             "    def test_total(self):\n"),
            TEST_OLD.replace("    def test_total(self):\n",
                             "    def test_total(self):\n        if shutil.which('node') is None:\n"
                             "            self.skipTest('node is not installed')\n"),
        )
        for new in variants:
            with self.subTest(new=new.splitlines()[5:8]):
                self.assertEqual(run_rules(with_code(new)), [])

    def test_deleted_test_function_fires(self) -> None:
        new = TEST_OLD.split("\n    def test_items(self):\n")[0] + "\n"
        found = run_rules(with_code(new))
        self.assertEqual(rules(found), [T.RULE_TEST_WEAKENED])
        self.assertIn("test_items", found[0]["detail"])

    def test_near_miss_test_gaining_assertions_does_not_fire(self) -> None:
        new = TEST_OLD.replace("        self.assertEqual(total([]), 0)\n",
                               "        self.assertEqual(total([]), 0)\n        self.assertEqual(total([1]), 1)\n")
        self.assertEqual(run_rules(with_code(new)), [])

    def test_near_miss_weakening_without_a_named_code_change_does_not_fire(self) -> None:
        new = TEST_OLD.replace("        self.assertEqual(total([]), 0)\n", "")
        unrelated = ("app/shipping.py", "RATE = 1\n", "RATE = 2\n")
        self.assertEqual(run_rules(with_code(new, code=unrelated)), [])

    def test_near_miss_moved_assertion_does_not_fire(self) -> None:
        new = TEST_OLD.replace("        self.assertEqual(total([]), 0)\n", "").replace(
            "        self.assertGreaterEqual(len([1, 2, 3]), 3)\n",
            "        self.assertGreaterEqual(len([1, 2, 3]), 3)\n        self.assertEqual(total([]), 0)\n")
        self.assertEqual(run_rules(with_code(new)), [])

    def test_near_miss_new_bound_inserted_before_an_updated_equality_does_not_fire(self) -> None:
        """Found on this repository's own history: a removed assertEqual was
        paired with an inserted assertLessEqual by position, not with the
        assertEqual that replaced it."""
        new = TEST_OLD.replace("        self.assertEqual(total([]), 0)\n",
                               "        self.assertLessEqual(total([]), 2)\n        self.assertEqual(total([]), 1)\n")
        self.assertEqual(run_rules(with_code(new)), [])

    def test_near_miss_renamed_test_function_does_not_fire(self) -> None:
        new = TEST_OLD.replace("def test_items(self):", "def test_item_count(self):")
        self.assertEqual(run_rules(with_code(new)), [])

    def test_near_miss_skip_text_inside_a_string_does_not_fire(self) -> None:
        new = TEST_OLD.replace("        self.assertEqual(total([]), 0)\n",
                               "        self.assertEqual(total([]), 0)\n"
                               "        note = '@unittest.skip is what the rule looks for'\n")
        self.assertEqual(run_rules(with_code(new)), [])

    def test_blind_spot_renamed_and_weakened_test_is_not_caught(self) -> None:
        """A renamed test whose assertion keeps its method but loses its
        meaning (compares the result with itself) is paired as a rename plus a
        same-strength rewrite. Documented in the module docstring."""
        new = TEST_OLD.replace("def test_total(self):", "def test_total_runs(self):").replace(
            "self.assertEqual(total([2, 3]), 5)", "self.assertEqual(total([2, 3]), total([2, 3]))")
        self.assertEqual(run_rules(with_code(new)), [])

    def test_blind_spot_code_reached_only_through_another_module_is_not_linked(self) -> None:
        """The link is by name: a test that imports `app.api`, which in turn
        calls the changed `app/billing.py`, is not tied to that change."""
        old = "from app.api import checkout\n\n\ndef test_checkout():\n    assert checkout([2, 3]) == 5\n"
        new = "from app.api import checkout\n\n\ndef test_checkout():\n    assert checkout([2, 3])\n"
        self.assertEqual(run_rules(with_code(new, old)), [])


WORKFLOW_OLD = (
    "name: ci\n"
    "on: workflow_dispatch\n"
    "jobs:\n"
    "  unit:\n"
    "    runs-on: ${{ matrix.os }}\n"
    "    strategy:\n"
    "      matrix:\n"
    "        os: [ubuntu-latest, windows-latest, macos-latest]\n"
    "        python:\n"
    "          - '3.11'\n"
    "          - '3.12'\n"
    "    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "      - run: echo starting\n"
    "      - name: Unit tests\n"
    "        run: python -m unittest discover -s tests\n"
    "  lint:\n"
    "    runs-on: ubuntu-latest\n"
    "    steps:\n"
    "      - run: |\n"
    "          python quality/checks/prepublication.py\n"
    "          python -m ruff check .\n"
)
WF = ".github/workflows/ci.yml"


class RuleTwoCiNodeDropped(unittest.TestCase):
    def _run(self, new: str | None) -> list[dict]:
        return run_rules({WF: (WORKFLOW_OLD, new)})

    def test_removed_job_fires(self) -> None:
        new = WORKFLOW_OLD.split("  lint:\n")[0]
        found = self._run(new)
        self.assertIn(T.RULE_CI_NODE_DROPPED, rules(found))
        job = [f for f in found if "lint" in f["detail"]][0]
        self.assertEqual(job["line"], 17)

    def test_removed_matrix_entry_fires(self) -> None:
        for old, new in (("windows-latest, ", ""), ("          - '3.12'\n", "")):
            with self.subTest(removed=old):
                found = self._run(WORKFLOW_OLD.replace(old, new))
                self.assertEqual(rules(found), [T.RULE_CI_NODE_DROPPED])
                self.assertIn("matrix", found[0]["detail"])

    def test_removed_test_run_step_fires(self) -> None:
        new = WORKFLOW_OLD.replace("      - name: Unit tests\n        run: python -m unittest discover -s tests\n", "")
        found = self._run(new)
        self.assertEqual(rules(found), [T.RULE_CI_NODE_DROPPED])
        self.assertIn("unittest", found[0]["detail"])

    def test_removed_line_from_block_run_fires(self) -> None:
        new = WORKFLOW_OLD.replace("          python -m ruff check .\n", "")
        self.assertEqual(rules(self._run(new)), [T.RULE_CI_NODE_DROPPED])

    def test_deleted_workflow_fires(self) -> None:
        self.assertIn(T.RULE_CI_NODE_DROPPED, rules(self._run(None)))

    def test_near_miss_renamed_job_does_not_fire(self) -> None:
        self.assertEqual(self._run(WORKFLOW_OLD.replace("  lint:\n", "  static-checks:\n")), [])

    def test_near_miss_added_matrix_entry_does_not_fire(self) -> None:
        self.assertEqual(self._run(WORKFLOW_OLD.replace("macos-latest]", "macos-latest, ubuntu-22.04]")), [])

    def test_near_miss_removed_non_test_step_does_not_fire(self) -> None:
        self.assertEqual(self._run(WORKFLOW_OLD.replace("      - run: echo starting\n", "")), [])

    def test_near_miss_step_moved_to_another_job_does_not_fire(self) -> None:
        new = WORKFLOW_OLD.replace("          python -m ruff check .\n", "").replace(
            "      - run: echo starting\n", "      - run: echo starting\n      - run: python -m ruff check .\n")
        self.assertEqual(self._run(new), [])


CHECKER_OLD = (
    "import sys\n"
    "\n"
    "\n"
    "def main():\n"
    "    problems = scan()\n"
    "    report(problems)\n"
    "    return 1 if problems else 0\n"
    "\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    sys.exit(main())\n"
)
CHECKER = "quality/checks/example_check.py"
SHELL_OLD = "#!/bin/sh\nset -e\npython -m unittest discover -s tests\nexit $?\n"


class RuleThreeCheckerNeutered(unittest.TestCase):
    def test_deleted_quality_checker_fires(self) -> None:
        found = run_rules({CHECKER: (CHECKER_OLD, None)})
        self.assertEqual(rules(found), [T.RULE_CHECKER_NEUTERED])

    def test_deleted_ci_invoked_script_fires(self) -> None:
        found = run_rules({"scripts/run_tests.sh": (SHELL_OLD, None)}, ci_scripts={"scripts/run_tests.sh"})
        self.assertEqual(rules(found), [T.RULE_CHECKER_NEUTERED])

    def test_exit_code_replaced_by_zero_fires(self) -> None:
        new = CHECKER_OLD.replace("sys.exit(main())", "sys.exit(0)")
        self.assertEqual(rules(run_rules({CHECKER: (CHECKER_OLD, new)})), [T.RULE_CHECKER_NEUTERED])

    def test_early_unconditional_exit_zero_fires(self) -> None:
        new = SHELL_OLD.replace("set -e\n", "set -e\nexit 0\n")
        found = run_rules({"scripts/run_tests.sh": (SHELL_OLD, new)}, ci_scripts={"scripts/run_tests.sh"})
        self.assertEqual(rules(found), [T.RULE_CHECKER_NEUTERED])

    def test_or_true_added_fires(self) -> None:
        new = SHELL_OLD.replace("discover -s tests\n", "discover -s tests || true\n")
        found = run_rules({"scripts/run_tests.sh": (SHELL_OLD, new)}, ci_scripts={"scripts/run_tests.sh"})
        self.assertEqual(rules(found), [T.RULE_CHECKER_NEUTERED])

    def test_continue_on_error_added_to_workflow_fires(self) -> None:
        new = WORKFLOW_OLD.replace("      - name: Unit tests\n",
                                   "      - name: Unit tests\n        continue-on-error: true\n")
        self.assertEqual(rules(run_rules({WF: (WORKFLOW_OLD, new)})), [T.RULE_CHECKER_NEUTERED])

    def test_near_miss_checker_gaining_a_check_does_not_fire(self) -> None:
        new = CHECKER_OLD.replace("    report(problems)\n",
                                  "    report(problems)\n    if not problems:\n        sys.exit(1)\n")
        self.assertEqual(run_rules({CHECKER: (CHECKER_OLD, new)}), [])

    def test_near_miss_exit_zero_in_a_help_branch_does_not_fire(self) -> None:
        new = CHECKER_OLD.replace("    problems = scan()\n",
                                  "    if '--help' in sys.argv:\n        print(__doc__)\n        sys.exit(0)\n"
                                  "    problems = scan()\n")
        self.assertEqual(run_rules({CHECKER: (CHECKER_OLD, new)}), [])

    def test_near_miss_unrelated_script_deleted_does_not_fire(self) -> None:
        self.assertEqual(run_rules({"scripts/one_off.py": (CHECKER_OLD, None)}), [])

    def test_near_miss_continue_on_error_false_does_not_fire(self) -> None:
        new = WORKFLOW_OLD.replace("      - name: Unit tests\n",
                                   "      - name: Unit tests\n        continue-on-error: false\n")
        self.assertEqual(run_rules({WF: (WORKFLOW_OLD, new)}), [])


class FindingShape(unittest.TestCase):
    def test_every_finding_names_rule_location_evidence_and_remedy(self) -> None:
        fixtures = [
            with_code(TEST_OLD.replace("        self.assertEqual(total([]), 0)\n", "")),
            {WF: (WORKFLOW_OLD, WORKFLOW_OLD.split("  lint:\n")[0])},
            {CHECKER: (CHECKER_OLD, CHECKER_OLD.replace("sys.exit(main())", "sys.exit(0)"))},
        ]
        seen = set()
        for files in fixtures:
            for finding in run_rules(files):
                seen.add(finding["rule"])
                with self.subTest(rule=finding["rule"]):
                    self.assertIn(finding["rule"], T.RULES)
                    self.assertIsInstance(finding["line"], int)
                    self.assertGreater(finding["line"], 0)
                    self.assertEqual(finding["location"], f"{finding['path']}:{finding['line']}")
                    self.assertTrue(finding["evidence"].strip())
                    self.assertTrue(any(l[:1] in "+-" for l in finding["evidence"].splitlines()))
                    self.assertTrue(finding["remedy"].strip())
                    self.assertFalse(finding["blocking"], "advisory only")
        self.assertEqual(seen, set(T.RULES))

    def test_blind_spots_are_listed_in_the_module_docstring(self) -> None:
        doc = T.__doc__ or ""
        self.assertIn("Blind spots", doc)
        for phrase in ("renamed", "another module"):
            self.assertIn(phrase, doc)


@contextmanager
def git_repo():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        (project / "app").mkdir(parents=True)
        (project / "tests").mkdir()
        (project / "app" / "billing.py").write_text(CODE_OLD, encoding="utf-8")
        (project / "tests" / "test_billing.py").write_text(TEST_OLD, encoding="utf-8")
        env = {"GODMODE_STATE_HOME": str(base / "state"), "GIT_CONFIG_GLOBAL": str(base / "gitconfig")}
        with mock.patch.dict(os.environ, env, clear=False):
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "core.autocrlf=false",
                   "-C", str(project)]
            subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
            subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "-m", "baseline"], check=True, capture_output=True)
            yield project, git


def _weaken(project: Path) -> None:
    (project / "app" / "billing.py").write_text(CODE_NEW, encoding="utf-8")
    (project / "tests" / "test_billing.py").write_text(
        TEST_OLD.replace("        self.assertEqual(total([]), 0)\n", ""), encoding="utf-8")


class ChangeSetFromGit(unittest.TestCase):
    def test_working_tree_against_head(self) -> None:
        with git_repo() as (project, _git):
            self.assertEqual(T.change_set_findings(project), [])
            _weaken(project)
            found = T.change_set_findings(project)
            self.assertEqual(rules(found), [T.RULE_TEST_WEAKENED])
            self.assertEqual(found[0]["line"], 8)

    def test_commit_range(self) -> None:
        with git_repo() as (project, git):
            _weaken(project)
            subprocess.run(git + ["commit", "-q", "-am", "weaken"], check=True, capture_output=True)
            self.assertEqual(rules(T.change_set_findings(project, "HEAD~1", "HEAD")), [T.RULE_TEST_WEAKENED])
            self.assertEqual(rules(T.change_set_findings(project, "HEAD~1..HEAD")), [T.RULE_TEST_WEAKENED])

    def test_surfaces_through_the_integrity_report_as_advisory(self) -> None:
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        from godmode_runtime.godmode_integrity import analyze

        with git_repo() as (project, _git):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            _weaken(project)
            report = analyze(archive, project, base="HEAD")
            ours = [f for f in report["findings"] if f.get("rule") == T.RULE_TEST_WEAKENED]
            self.assertEqual(len(ours), 1, report["findings"])
            self.assertEqual(ours[0]["monitor"], "oracle-tamper")
            self.assertFalse(ours[0]["blocking"])
            self.assertTrue(ours[0]["remedy"])

    def test_integrity_report_reads_a_commit_range(self) -> None:
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        from godmode_runtime.godmode_integrity import analyze

        with git_repo() as (project, git):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            _weaken(project)
            subprocess.run(git + ["commit", "-q", "-am", "weaken"], check=True, capture_output=True)
            clean = analyze(archive, project, base="HEAD")
            self.assertNotIn(T.RULE_TEST_WEAKENED, [f.get("rule") for f in clean["findings"]])
            report = analyze(archive, project, base="HEAD~1..HEAD")
            self.assertIn(T.RULE_TEST_WEAKENED, [f.get("rule") for f in report["findings"]])


if __name__ == "__main__":
    unittest.main()
