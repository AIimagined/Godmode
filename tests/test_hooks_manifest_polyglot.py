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


    @unittest.skipUnless(sys.platform == "win32", "cmd.exe half")
    def test_cmd_half_keeps_the_hooks_exit_code_when_python_is_missing(self) -> None:
        """Field walk 2026-09-05 (obligation 9401): with no `python` on PATH
        and only the `py` launcher available, every hook exited 49 - the
        parse-time `%ERRORLEVEL%` inside the `if errorlevel 9009 ( ... )`
        block was 9009, truncated to a byte. A gate's exit 2 vanished.
        The launcher must return the hook's own exit code."""
        import os, shutil
        py = shutil.which("py")
        if not py:
            self.skipTest("py launcher not installed")
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        env = {**os.environ, "PATH": os.pathsep.join(
            [os.path.join(system_root, "System32"), system_root, os.path.dirname(py)])}
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(PLUGIN_ROOT / "hooks" / "run-hook.cmd"),
             "godmode_gate_fast.py"],
            input="not json", capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))
        self.assertNotIn("is not recognized", result.stderr + result.stdout)


    @unittest.skipUnless(sys.platform == "win32", "cmd.exe shim")
    def test_bin_shim_finds_an_interpreter_when_python_is_missing(self) -> None:
        """Eighth field report 2026-09-05: bin/godmode.cmd had the same
        python-only gap as the launcher's cmd half; bin/godmode probes
        python3/python/py. With only the py launcher on PATH the shim must
        still answer --version."""
        import os, shutil
        py = shutil.which("py")
        if not py:
            self.skipTest("py launcher not installed")
        system_root = os.environ.get("SystemRoot", "C:/Windows")
        env = {**os.environ, "PATH": os.pathsep.join(
            [os.path.join(system_root, "System32"), system_root, os.path.dirname(py)])}
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(PLUGIN_ROOT / "bin" / "godmode.cmd"), "--version"],
            capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertIn("Godmode", result.stdout)

    def test_launcher_runs_a_hook_end_to_end(self) -> None:
        result = subprocess.run(
            [str(PLUGIN_ROOT / "hooks" / "run-hook.cmd")
             if sys.platform == "win32" else "sh",
             *([] if sys.platform == "win32"
               else [str(PLUGIN_ROOT / "hooks" / "run-hook.cmd")]),
             "godmode_post_edit.py"],
            input="{}", capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)


class SharedCommandStringTests(unittest.TestCase):
    """Eighth field report 2026-09-05 (Grok 1.0.13, Windows): Grok runs a
    plugin hook's command string in PowerShell, and the shipped
    `"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" ...` shape parse-fails there
    (a quoted path in statement position needs `&`), so every hook
    fail-opened. The same string must run under sh (Claude, Codex, Grok on
    macOS) AND under pwsh (Grok on Windows), with the plugin root arriving
    only as an environment variable, exactly as the hosts pass it."""

    def _commands(self) -> list[str]:
        manifest = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        return [entry["command"] for groups in manifest["hooks"].values()
                for group in groups for entry in group["hooks"]]

    def _gate_command(self) -> str:
        gate = [c for c in self._commands() if "godmode_gate_fast.py" in c]
        self.assertEqual(len(gate), 1, gate)
        return gate[0]

    @staticmethod
    def _sh() -> str | None:
        """A POSIX sh: on PATH, or Git for Windows' bundled one beside git.exe
        (the release gate launches from PowerShell, where Git's usr/bin is
        not on PATH)."""
        import shutil
        found = shutil.which("sh")
        if found:
            return found
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "usr" / "bin" / "sh.exe"
            if candidate.is_file():
                return str(candidate)
        return None

    def test_every_shared_command_runs_under_sh(self) -> None:
        import os
        sh = self._sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)}
        for command in self._commands():
            with self.subTest(command=command):
                done = subprocess.run([sh, "-c", command], input="{}", capture_output=True,
                                      text=True, timeout=120, env=env)
                self.assertIn(done.returncode, (0, 2), (command, done.stderr[-400:]))
                self.assertNotIn("not found", done.stderr)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell host shape")
    def test_the_gate_command_denies_garbage_under_pwsh(self) -> None:
        import os, shutil
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            self.skipTest("no PowerShell on this machine")
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)}
        # Grok's runner (10-hooks.md, "Using variables in command"): on
        # Windows PowerShell known `$VAR`/`${VAR}` refs are rewritten to
        # `$env:VAR` before the string runs. Apply the same rewrite here;
        # everything else reaches pwsh verbatim.
        command = self._gate_command().replace("${CLAUDE_PLUGIN_ROOT}", "$env:CLAUDE_PLUGIN_ROOT")
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "git push --force origin main"},
                              "cwd": str(PLUGIN_ROOT)})
        done = subprocess.run([pwsh, "-NoProfile", "-Command", command],
                              input=payload, capture_output=True, text=True,
                              timeout=120, env=env)
        self.assertNotIn("ParserError", done.stderr, done.stderr[-600:])
        self.assertIn('"deny"', done.stdout, (done.stdout, done.stderr[-400:]))
        self.assertIn("R5", done.stdout)


if __name__ == "__main__":
    unittest.main()
