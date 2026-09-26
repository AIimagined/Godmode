"""Command words that are not written as a plain name.

A lookalike name, a variable, an expression, `Start-Process`, a
pseudo-terminal wrapper, an ANSI-C string, a quoted flag: each used to read
as an unrecognised command, which the classifier's no-evidence default
allows. Each is now read as the command it runs, or judged opaque when the
text cannot name it. The corpus (`tests/fixtures/gate_corpus.json`) carries
the per-form catches and near-misses; this module pins what the corpus
cannot express - the cmd dialect, the dialect-dependent reading of a bare
variable, and the fast path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_parseview as pv  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "godmode_gate_fast_head_forms", PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py")
fast = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fast)
TABLE = fast._load_table()


def decision(command: str, **kwargs) -> str:
    verdict = classify_action(command, project_root=PLUGIN_ROOT, **kwargs)
    if not verdict["protected"]:
        return "allow"
    return "refuse" if verdict["tier"] == "R5" else "ask"


def payload(command: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}}


class CmdDialectTests(unittest.TestCase):
    """A shell tool whose shell is undeclared may be cmd on Windows."""

    def test_an_undeclared_shell_on_windows_is_read_as_cmd_too(self) -> None:
        self.assertIn(pv.CMD, pv.dialects_to_read(pv.dialect_for_tool("shell_command", "win32")))
        self.assertEqual(pv.dialects_to_read(pv.dialect_for_tool("shell_command", "linux")),
                         (pv.BASH,))

    def test_a_single_quoted_separator_splits_under_cmd(self) -> None:
        """cmd reads `'` as an ordinary character, so the push runs."""
        command = "echo 'a & git push --force'"
        self.assertEqual(decision(command), "allow")
        self.assertEqual(decision(command, dialect=pv.DIALECT_EITHER), "refuse")

    def test_an_ordinary_read_stays_free_in_every_reading(self) -> None:
        self.assertEqual(decision("git status", dialect=pv.DIALECT_EITHER), "allow")


class VariableHeadTests(unittest.TestCase):
    def test_bash_runs_a_bare_variable(self) -> None:
        self.assertEqual(decision("$EDITOR notes.md"), "ask")
        self.assertEqual(decision('"$TOOL" status'), "ask")

    def test_powershell_runs_a_variable_only_through_a_call(self) -> None:
        self.assertEqual(decision("$x", tool_name="PowerShell"), "allow")
        self.assertEqual(decision("$x -eq 1", tool_name="PowerShell"), "allow")
        self.assertEqual(decision("& $x", tool_name="PowerShell"), "ask")
        self.assertEqual(decision("$a = 1; & $x status", tool_name="PowerShell"), "ask")

    def test_an_expression_target_is_opaque_unless_it_names_the_command(self) -> None:
        self.assertEqual(decision("& (Resolve-Path x) y", tool_name="PowerShell"), "ask")
        self.assertEqual(decision("& (gcm git) reset --hard", tool_name="PowerShell"), "refuse")

    def test_a_default_value_is_read_and_the_variable_stays_opaque(self) -> None:
        self.assertEqual(decision('"${GIT:-git}" status'), "ask")
        self.assertEqual(decision("${GIT:-git} push --force"), "refuse")


class StartProcessTests(unittest.TestCase):
    def test_the_launched_command_is_judged(self) -> None:
        self.assertEqual(decision("Start-Process -FilePath git -ArgumentList 'reset','--hard'",
                                  tool_name="PowerShell"), "refuse")
        self.assertEqual(decision("saps git 'push --force'", tool_name="PowerShell"), "refuse")

    def test_a_redirected_output_is_a_write(self) -> None:
        self.assertEqual(decision("Start-Process x -RedirectStandardOutput /etc/hosts",
                                  tool_name="PowerShell"), "ask")

    def test_an_ordinary_launch_stays_free(self) -> None:
        self.assertEqual(decision("Start-Process -FilePath python -ArgumentList 'app.py'",
                                  tool_name="PowerShell"), "allow")


class WrapperTests(unittest.TestCase):
    def test_readings_nest(self) -> None:
        self.assertEqual(decision("winpty $'git' push --force"), "refuse")
        self.assertEqual(decision("winpty git \"push\" \"--force\""), "refuse")

    def test_every_pty_wrapper_around_an_operator_verb_asks(self) -> None:
        for command in ("unbuffer godmode session open --as-operator",
                        "script -qc 'godmode branches --record --as-operator' /dev/null",
                        "script -q -c 'godmode law retire x --as-operator'",
                        "expect -c 'spawn godmode x --as-operator'"):
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT)
                self.assertTrue(verdict["protected"], verdict)
                self.assertGreaterEqual(verdict["tier"], "R4")

    def test_an_abbreviated_operator_flag_under_a_wrapper_asks(self) -> None:
        for command in ('script -qc "godmode lesson add x --as-op" /dev/null',
                        "unbuffer godmode skill retire --name x --as-o"):
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT)
                self.assertTrue(verdict["protected"], verdict)
                self.assertGreaterEqual(verdict["tier"], "R4")

    def test_session_and_socket_wrappers_around_an_operator_verb_ask(self) -> None:
        for command in ('tmux new -d "godmode lesson add x --as-operator"',
                        "screen -dm godmode lesson add x --as-operator",
                        "socat - EXEC:'godmode lesson add x --as-operator',pty",
                        "ssh -t host godmode lesson add x --as-operator",
                        "setsid godmode lesson add x --as-operator"):
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT)
                self.assertTrue(verdict["protected"], verdict)
                self.assertGreaterEqual(verdict["tier"], "R4")

    def test_the_cli_refuses_an_abbreviated_long_option(self) -> None:
        from godmode_runtime.godmode_console import _build_parser
        parser = _build_parser()
        self.assertFalse(parser.allow_abbrev)
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parser.parse_args(["skill", "retire", "--name", "x", "--reason", "y", "--as-op"])
        args = parser.parse_args(["skill", "retire", "--name", "x", "--reason", "y",
                                  "--as-operator"])
        self.assertTrue(args.as_operator)

    def test_dot_sourcing_a_script_runs_it_as_a_script(self) -> None:
        self.assertIn("bash ./x.sh", pv.command_readings(". ./x.sh"))
        self.assertIn("pwsh ./x.ps1", pv.command_readings(". ./x.ps1"))


class LookalikeTests(unittest.TestCase):
    def test_the_name_not_the_path_decides(self) -> None:
        self.assertEqual(pv.lookalike_head("gіt status"), "gіt")
        self.assertIsNone(pv.lookalike_head("/home/josé/bin/git status"))
        self.assertIsNone(pv.lookalike_head('"déjà vu"'))


class FastPathTests(unittest.TestCase):
    def test_non_ascii_escalates_in_every_dialect(self) -> None:
        self.assertEqual(fast.fast_verdict(payload("lѕ -la"), TABLE), "escalate")
        self.assertEqual(fast.fast_verdict(payload("ls -la"), TABLE), "escalate")
        self.assertEqual(fast.fast_verdict(payload("ls -la"), TABLE), "allow")

    def test_a_possible_cmd_shell_escalates_on_cmd_syntax(self) -> None:
        for command in ("cat 'x & git push --force'", "ls %X%", "ls ^& git push"):
            with self.subTest(command=command):
                with mock.patch.object(fast.sys, "platform", "win32"):
                    self.assertEqual(
                        fast.fast_verdict(payload(command, "shell_command"), TABLE), "escalate")
        with mock.patch.object(fast.sys, "platform", "win32"):
            self.assertEqual(fast.fast_verdict(payload("git status", "shell_command"), TABLE),
                             "allow")


class DirectoryChangeTests(unittest.TestCase):
    """A relative path is read from the directory an earlier `cd` moved to.

    `cd .git && echo x >> config` writes `.git/config`; judged from the
    project root, `config` read as an ordinary working file."""

    def test_a_write_after_a_directory_change_is_judged_where_it_lands(self) -> None:
        for command, tool, full_path in (
                ("cd .git && echo x >> config", None, "echo x >> .git/config"),
                ("cd .git; printf x >> config", None, "printf x >> .git/config"),
                ("pushd .git && echo x >> config", None, "echo x >> .git/config"),
                ("cd .git\necho x >> config", None, "echo x >> .git/config"),
                ("cd .git/hooks && echo x > pre-commit", None, "echo x > .git/hooks/pre-commit"),
                ("sl .git; echo x >> config", "PowerShell", "echo x >> .git/config"),
                ("Set-Location .git; Add-Content config 'x'", "PowerShell",
                 "Add-Content .git/config 'x'")):
            with self.subTest(command=command):
                kwargs = {"tool_name": tool} if tool else {}
                moved = classify_action(command, project_root=PLUGIN_ROOT, **kwargs)
                direct = classify_action(full_path, project_root=PLUGIN_ROOT, **kwargs)
                self.assertTrue(moved["protected"], command)
                self.assertEqual(moved["category"], direct["category"], command)

    def test_an_unresolvable_directory_change_asks(self) -> None:
        self.assertEqual(decision("cd $x && echo x >> config"), "ask")
        self.assertEqual(decision("cd .. && echo x > notes.txt"), "ask")

    def test_a_return_to_the_root_or_a_move_inside_the_tree_stays_allowed(self) -> None:
        for command in ("cd .git && cd .. && echo x >> README.md",
                        "pushd .git && popd && echo x >> README.md",
                        "cd docs && echo x >> notes.txt",
                        "cd .git && git status"):
            with self.subTest(command=command):
                self.assertEqual(decision(command), "allow")


if __name__ == "__main__":
    unittest.main()
