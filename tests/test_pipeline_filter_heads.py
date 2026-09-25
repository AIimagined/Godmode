"""Pipeline filters, read the same way by the gate and by claim grading.

A filter at the end of a pipeline decides the exit code the shell reports,
so a claim graded on that exit code is graded on the filter (`filter_head`).
The same filters, run as the gate sees them, must stay free when they only
reshape output - and must never hide what they do beyond that: `tee` writes
the files it names, `xargs` runs a command.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_attest import falsifiable, filter_head  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "godmode_gate_fast_filters", PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py")
fast = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fast)


def verdict(command: str, tool: str | None = None) -> dict:
    return classify_action(command, project_root=PLUGIN_ROOT, tool_name=tool)


class ClaimGradingTests(unittest.TestCase):
    def test_a_reshaping_tail_is_the_filter(self) -> None:
        for command, head in (("python -m unittest | tee log.txt", "tee"),
                              ("make test | nl", "nl"),
                              ("make test | column -t", "column"),
                              ("make test | rev", "rev"),
                              ("Invoke-Pester | Select-Object -Last 3", "select-object"),
                              ("Invoke-Pester | Out-String", "out-string")):
            with self.subTest(command=command):
                self.assertEqual(filter_head(command), head)
                self.assertFalse(falsifiable(command))

    def test_xargs_is_judged_by_the_command_it_runs(self) -> None:
        self.assertIsNone(filter_head("git ls-files | xargs python -m pytest"))
        self.assertEqual(filter_head("git ls-files | xargs -n1 grep -l TODO"), "grep")
        self.assertEqual(filter_head("git ls-files | xargs"), "echo")


class GateTests(unittest.TestCase):
    def test_reshaping_pipelines_stay_free(self) -> None:
        for command, tool in (("cat notes.md | nl | column -t | rev", None),
                              ("git log --oneline | tee log.txt", None),
                              ("Get-ChildItem | Sort-Object Name | Select-Object -First 3 "
                               "| Out-String", "PowerShell")):
            with self.subTest(command=command):
                self.assertFalse(verdict(command, tool)["protected"])

    def test_tee_is_judged_as_the_write_it_is(self) -> None:
        for command, tool in (("cat f | tee /etc/hosts", None),
                              ("cat f | tee -a ~/.bashrc", None),
                              ("Get-ChildItem | Tee-Object -FilePath C:/Windows/x.txt",
                               "PowerShell")):
            with self.subTest(command=command):
                self.assertTrue(verdict(command, tool)["protected"])
        self.assertFalse(verdict("cat f | tee /dev/null")["protected"])

    def test_xargs_is_judged_as_the_command_it_runs(self) -> None:
        self.assertEqual(verdict("ls | xargs -n1 $'git' push --force")["tier"], "R5")
        self.assertTrue(verdict("ls | xargs -I {} rm {}")["protected"])
        self.assertFalse(verdict("ls | xargs wc -l")["protected"])

    def test_the_fast_path_takes_the_plain_filters_and_not_tee_or_xargs(self) -> None:
        table = fast._load_table()
        def fast_verdict(command: str) -> str:
            return fast.fast_verdict({"tool_name": "Bash", "tool_input": {"command": command}},
                                     table)
        self.assertEqual(fast_verdict("cat notes.md | nl | column -t"), "allow")
        self.assertEqual(fast_verdict("cat notes.md | tee out.txt"), "escalate")
        self.assertEqual(fast_verdict("ls | xargs rm"), "escalate")


if __name__ == "__main__":
    unittest.main()
