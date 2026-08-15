"""godmode guide + init's next-steps + a grouped top-level help.

The CLI had 80 flat subcommands and a silent init: a human's first session
was README-or-nothing while agents got routed by skills (routing, working
contract, entry sequence). guide is architecturally different from every
other command - static prose, no project data - so main() prints it
directly rather than routing it through the CommandResult/JSON pipeline
every data-bearing command uses; init's next-steps stay IN that pipeline
(payload["next"]) because init's output is real per-project data that
programmatic callers may parse.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))


def _run(*args: str) -> str:
    return subprocess.run(
        [sys.executable, "scripts/godmode.py", *args],
        capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout


class GuideTests(unittest.TestCase):
    def test_guide_orients_a_first_session(self) -> None:
        out = _run("guide")
        for needle in ("init", "resume", "authorize setup", "doctor",
                      "irreversible"):
            self.assertIn(needle, out)

    def test_guide_fits_one_screen_of_attention(self) -> None:
        # An orientation page that scrolls is a README, and one exists.
        self.assertLessEqual(len(_run("guide").splitlines()), 60)

    def test_guide_is_plain_text_not_json(self) -> None:
        out = _run("guide")
        stripped = out.strip()
        self.assertFalse(stripped.startswith("{"))
        self.assertFalse(stripped.startswith("["))

    def test_guide_needs_no_project_and_no_archive(self) -> None:
        # Run from a directory this repo never initialized - the guide must
        # still work, proving it touches no per-project state.
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            result = subprocess.run(
                [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
                 "--project", raw, "guide"],
                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("GODMODE IN FIVE COMMANDS", result.stdout)


class TopLevelHelpTests(unittest.TestCase):
    def test_top_help_names_where_to_start(self) -> None:
        out = _run("--help")
        self.assertIn("guide", out)
        self.assertIn("Start here", out)


class InitNextStepsTests(unittest.TestCase):
    def test_ordinary_init_carries_next_steps(self) -> None:
        from test_godmode_runtime import isolated_project
        from godmode_runtime.godmode_console import Runtime, cmd_init
        import argparse
        with isolated_project() as (_project, _s, anchor, archive):
            result = cmd_init(argparse.Namespace(roles=False),
                              Runtime(anchor=anchor, archive=archive))
        self.assertIn("next", result.payload)
        joined = " ".join(result.payload["next"])
        self.assertIn("guide", joined)
        self.assertIn("resume", joined)

    def test_next_steps_are_valid_json_through_the_real_cli(self) -> None:
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            result = subprocess.run(
                [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
                 "--project", raw, "init"],
                capture_output=True, text=True)
        payload = json.loads(result.stdout)
        self.assertIn("next", payload)


if __name__ == "__main__":
    unittest.main()
