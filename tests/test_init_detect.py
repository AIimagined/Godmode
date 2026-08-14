"""`godmode init --detect`: a starter charter from repo evidence.

A brand-new project stares at an empty charter with no idea what belongs in
it. Detection reads the repo's own facts - manifest scripts, CI workflow
commands, `.gitignore` build markers, a migrations directory, the default
branch - and proposes one SOFT candidate rule per fact, each carrying the
evidence that produced it. Detection never gets to gate anything on its own
guess: promotion to a binding rule is a human decision made in the charter
document itself, so every line detection writes stays SOFT, and a repo that
already has a charter gets a report instead of a rewrite.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_detect import (  # noqa: E402
    FILE_CAP, detect_repo, soft_rule_text,
)
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class Detection(unittest.TestCase):
    def test_node_repo_detects_test_command_with_provenance(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "package.json").write_text(
                '{"scripts": {"test": "vitest run", "lint": "eslint ."}}',
                encoding="utf-8",
            )
            found = {d["kind"]: d for d in detect_repo(project)}
            self.assertEqual(found["test-command"]["value"], "npm test")
            self.assertIn("package.json", found["test-command"]["source"])

    def test_python_repo_detects_unittest_or_pytest(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "pyproject.toml").write_text(
                "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
            )
            kinds = {d["kind"] for d in detect_repo(project)}
            self.assertIn("test-command", kinds)

    def test_gitignored_build_dir_becomes_generated_dir_candidate(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / ".gitignore").write_text("dist/\n.env\n", encoding="utf-8")
            values = {d["value"] for d in detect_repo(project) if d["kind"] == "generated-dir"}
            self.assertIn("dist/", values)
            self.assertNotIn(".env", values)

    def test_empty_repo_detects_nothing_cleanly(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            self.assertEqual(detect_repo(project), [])

    def test_file_cap_is_reported_on_a_large_repo(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            for index in range(FILE_CAP + 50):
                (project / f"file{index}.txt").write_text("x", encoding="utf-8")
            stats: dict = {}
            detect_repo(project, stats=stats)
            self.assertEqual(stats["files_scanned"], FILE_CAP)
            self.assertTrue(stats["capped"])
            self.assertEqual(stats["cap"], FILE_CAP)


class NeverHard(unittest.TestCase):
    """The hard-coded refusal: detection may only ever emit SOFT."""

    def test_forcing_hard_is_refused(self) -> None:
        detection = {"kind": "test-command", "value": "pytest", "source": "pyproject.toml"}
        with self.assertRaises(GodmodeError):
            soft_rule_text(detection, enforcement="HARD")

    def test_default_emission_is_soft_and_never_hard(self) -> None:
        detection = {"kind": "test-command", "value": "pytest", "source": "pyproject.toml"}
        text = soft_rule_text(detection)
        self.assertIn("SOFT", text)
        self.assertNotIn("HARD", text)


class InitIntegration(unittest.TestCase):
    @staticmethod
    def _run(project: Path, *argv: str) -> dict:
        from godmode_runtime.godmode_console import main

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["--project", str(project), *argv])
        payload = json.loads(buffer.getvalue())
        return exit_code, payload

    def test_detect_writes_soft_rules_never_hard(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "package.json").write_text(
                '{"scripts": {"test": "vitest run", "lint": "eslint ."}}',
                encoding="utf-8",
            )
            exit_code, payload = self._run(project, "init", "--detect")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["detect"]["mode"], "created")

            written = (project / "GODMODE.md").read_text(encoding="utf-8")
            self.assertEqual(written.count("HARD"), 0)
            rule_lines = [line for line in written.splitlines() if line.startswith("- ")]
            self.assertTrue(rule_lines, written)
            for line in rule_lines:
                self.assertIn("(detected: ", line)
                self.assertIn("SOFT", line)

    def test_existing_charter_untouched_report_only(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            original = "# Existing operating guide\n\nSome existing guidance.\n"
            (project / "GODMODE.md").write_text(original, encoding="utf-8")
            (project / "package.json").write_text(
                '{"scripts": {"test": "vitest run"}}', encoding="utf-8"
            )
            exit_code, payload = self._run(project, "init", "--detect")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["detect"]["mode"], "report")
            self.assertGreater(len(payload["detect"]["candidates"]), 0)
            self.assertEqual(
                (project / "GODMODE.md").read_text(encoding="utf-8"), original
            )

    def test_file_cap_reported(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            for index in range(FILE_CAP + 50):
                (project / f"file{index}.txt").write_text("x", encoding="utf-8")
            exit_code, payload = self._run(project, "init", "--detect")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["detect"]["files_scanned"], FILE_CAP)
            self.assertTrue(payload["detect"]["capped"])

    def test_empty_repo_writes_honest_stub(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            exit_code, payload = self._run(project, "init", "--detect")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["detect"]["mode"], "stub")
            self.assertEqual(payload["detect"]["note"], "nothing detected")
            written = (project / "GODMODE.md").read_text(encoding="utf-8")
            self.assertEqual(written.count("HARD"), 0)

    def test_init_without_detect_flag_writes_nothing(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "package.json").write_text(
                '{"scripts": {"test": "vitest run"}}', encoding="utf-8"
            )
            exit_code, payload = self._run(project, "init")
            self.assertEqual(exit_code, 0)
            self.assertNotIn("detect", payload)
            self.assertFalse((project / "GODMODE.md").exists())


if __name__ == "__main__":
    unittest.main()
