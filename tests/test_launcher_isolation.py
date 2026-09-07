"""The launcher starts every hook interpreter isolated.

Sweep 2026-09-07 (a planning plugin in the research ledger): its hook interpreters
imported a repository's own hashlib.py or secrets.py with the hook's
privileges because the working directory led sys.path. Godmode runs hooks
as script files, so the working directory never led its path; what was
still open was the environment - a PYTHONPATH, PYTHONSTARTUP-class variable
or user site reaching the hook. `-I -B` closes that (and writes no
byte-code into the plugin cache). Obligation 9866.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PLUGIN_ROOT / "hooks" / "run-hook.cmd"
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import HOST_MARKERS  # noqa: E402

POISON = "raise SystemExit('poisoned json module imported by a godmode hook')\n"


def _sh() -> str | None:
    found = shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parent.parent / "usr" / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _run(argv: list[str], poison_dir: Path, payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment.pop("GODMODE_PYTHON", None)
    environment["PYTHONPATH"] = str(poison_dir)
    environment["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    return subprocess.run(argv, input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=120, cwd=str(cwd), env=environment)


class IsolatedInterpreterTests(unittest.TestCase):
    def _payload(self, cwd: Path) -> dict:
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "git status"}, "cwd": str(cwd)}

    def test_sh_half_ignores_a_poisoned_pythonpath(self) -> None:
        sh = _sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        with tempfile.TemporaryDirectory() as temporary:
            poison = Path(temporary) / "poison"
            poison.mkdir()
            (poison / "json.py").write_text(POISON, encoding="utf-8")
            done = _run([sh, str(LAUNCHER), "godmode_gate_fast.py"], poison,
                        self._payload(Path(temporary)), Path(temporary))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("poisoned", done.stderr + done.stdout)

    @unittest.skipUnless(os.name == "nt", "cmd half runs on Windows only")
    def test_cmd_half_ignores_a_poisoned_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            poison = Path(temporary) / "poison"
            poison.mkdir()
            (poison / "json.py").write_text(POISON, encoding="utf-8")
            done = _run(["cmd", "/c", str(LAUNCHER), "godmode_gate_fast.py"], poison,
                        self._payload(Path(temporary)), Path(temporary))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("poisoned", done.stderr + done.stdout)

    def test_the_fast_gate_escalates_isolated_too(self) -> None:
        """The fast gate re-spawns the full hook; that child must carry the
        same flags or the isolation ends at the first escalation."""
        sh = _sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        with tempfile.TemporaryDirectory() as temporary:
            poison = Path(temporary) / "poison"
            poison.mkdir()
            (poison / "json.py").write_text(POISON, encoding="utf-8")
            done = _run([sh, str(LAUNCHER), "godmode_gate_fast.py"], poison,
                        {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "git push --force origin main"},
                         "cwd": temporary}, Path(temporary))
        self.assertNotIn("poisoned", done.stderr + done.stdout)


if __name__ == "__main__":
    unittest.main()
