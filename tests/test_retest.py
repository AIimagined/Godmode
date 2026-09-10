"""`godmode retest`: the tests that pin a changed file, as one command."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_retest import commands, pinning_tests, retest_plan  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
                   check=True, capture_output=True, timeout=60)


class RetestTests(unittest.TestCase):
    def test_tests_that_name_a_changed_file_are_one_command_per_runner(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _git(project, "init", "-q")
            (project / "src").mkdir(); (project / "tests").mkdir(); (project / "lib").mkdir()
            (project / "src" / "retry.py").write_text("def retry():\n    return 1\n", encoding="utf-8")
            (project / "src" / "other.py").write_text("x = 1\n", encoding="utf-8")
            (project / "tests" / "test_retry.py").write_text("from src.retry import retry\n", encoding="utf-8")
            (project / "tests" / "test_far.py").write_text("import json\n", encoding="utf-8")
            (project / "lib" / "brief.ts").write_text("export const a = 1;\n", encoding="utf-8")
            (project / "lib" / "brief.test.ts").write_text("import { a } from './brief';\n", encoding="utf-8")
            (project / "package.json").write_text('{"devDependencies": {"vitest": "1"}}', encoding="utf-8")
            _git(project, "add", "-A"); _git(project, "commit", "-q", "-m", "baseline")
            (project / "src" / "retry.py").write_text("def retry():\n    return 2\n", encoding="utf-8")
            (project / "src" / "other.py").write_text("x = 2\n", encoding="utf-8")
            (project / "lib" / "brief.ts").write_text("export const a = 2;\n", encoding="utf-8")
            plan = retest_plan(project, "HEAD")
            self.assertEqual(sorted(plan["pinned"]), ["lib/brief.test.ts", "tests/test_retry.py"])
            runners = {c["runner"]: c for c in plan["commands"]}
            self.assertEqual(runners["unittest"]["command"], "python -m unittest tests.test_retry")
            self.assertEqual(runners["vitest"]["command"], "npx vitest run lib/brief.test.ts")
            self.assertEqual(plan["unpinned"], ["src/other.py"])

    def test_a_changed_test_pins_itself(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            _git(project, "init", "-q")
            (project / "tests").mkdir()
            (project / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
            _git(project, "add", "-A"); _git(project, "commit", "-q", "-m", "b")
            (project / "tests" / "test_a.py").write_text("x = 2\n", encoding="utf-8")
            self.assertEqual(list(pinning_tests(project, ["tests/test_a.py"])), ["tests/test_a.py"])
            self.assertEqual(commands(project, {"tests/test_a.py": ["tests/test_a.py"]})[0]["command"],
                             "python -m unittest tests.test_a")


if __name__ == "__main__":
    unittest.main()
