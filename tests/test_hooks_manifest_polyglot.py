"""The hook launcher works where the interpreter name differs.

Field report 2026-09-03: all eight hooks declared bare `python`; stock
macOS ships only python3, so every hook died silently. The polyglot
launcher resolves the interpreter per platform and execs, preserving
exit codes; hooks.json routes every command through it.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class PolyglotLauncherTests(unittest.TestCase):
    def test_every_hook_routes_through_the_launcher(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json")
                              .read_text(encoding="utf-8"))
        for event, blocks in manifest["hooks"].items():
            for block in blocks:
                for hook in block["hooks"]:
                    self.assertIn("run-hook.cmd", hook["command"],
                                  f"{event}: {hook['command']}")
                    self.assertNotRegex(hook["command"], r"^python ",
                                        f"{event} still bare-python")

    def test_launcher_is_lf_only_and_executable_in_git(self) -> None:
        raw = (PLUGIN_ROOT / "hooks" / "run-hook.cmd").read_bytes()
        self.assertNotIn(b"\r\n", raw, "sh half breaks under CRLF")
        mode = subprocess.run(
            ["git", "ls-files", "-s", "hooks/run-hook.cmd"],
            capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout
        self.assertTrue(mode.startswith("100755"),
                        f"needs the exec bit for sh fallback: {mode}")

    def test_sh_half_prefers_python3(self) -> None:
        text = (PLUGIN_ROOT / "hooks" / "run-hook.cmd").read_text(
            encoding="utf-8")
        self.assertIn("for py in python3 python py", text)
        self.assertIn("exec ", text)
        self.assertIn("GODMODE_PYTHON", text)

    def test_cmd_half_is_label_free(self) -> None:
        text = (PLUGIN_ROOT / "hooks" / "run-hook.cmd").read_text(
            encoding="utf-8")
        cmd_half = text.split("@echo off", 1)[1]
        self.assertNotIn("goto", cmd_half.lower())
        self.assertNotRegex(cmd_half, r"(?m)^:[a-z]")

    def test_launcher_runs_a_hook_end_to_end(self) -> None:
        result = subprocess.run(
            [str(PLUGIN_ROOT / "hooks" / "run-hook.cmd")
             if sys.platform == "win32" else "sh",
             *([] if sys.platform == "win32"
               else [str(PLUGIN_ROOT / "hooks" / "run-hook.cmd")]),
             "godmode_post_edit.py"],
            input="{}", capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
