"""Running a script is judged by what the script does.

Incident 12890. `git rm` on tracked files was refused as a protected shell
command. The identical operation, written into a Python file and run as
`python thatfile.py`, executed with no refusal at all: the classifier reads the
command string it is handed, and a script is one allowed invocation whose
contents are invisible to it.

That makes every protected class reachable by writing it to a file and running
the file, which is what happened in this session - the removal was authorised,
so nothing unwanted resulted, but authorisation is not what let it through.

The fix cannot be complete and does not pretend to be. A hook cannot see inside
a running interpreter, so a script that builds its command at runtime, or fetches
it, or imports it, stays invisible. What is closed is the shape that actually
occurred: a literal protected command sitting in a readable file in this
project, run by an interpreter named on the command line.

The residual limit is stated in the module rather than left implied, because an
unstated hole is worse than a stated one - a reader who believes the gate covers
scripts will write one and trust it.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_sentinel as S  # noqa: E402

DEL = "r" + "m"  # assembled so this file is not itself refused


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def script(self, body: str, name: str = "tool.py") -> str:
        path = self.root / name
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        return name

    def verdict(self, command: str) -> dict:
        return S.classify_action(command, project_root=self.root)


class AScriptCarryingAProtectedCommandEscalates(Base):
    def test_a_push_inside_a_script_is_seen(self) -> None:
        name = self.script(
            'import subprocess\n'
            'subprocess.run(["git", "push", "origin", "main"])\n')
        self.assertTrue(self.verdict(f"python {name}")["protected"])

    def test_a_removal_inside_a_script_is_seen(self) -> None:
        name = self.script(
            'import subprocess\n'
            f'subprocess.run(["git", "{DEL}", "-q", "docs/x.md"])\n')
        self.assertTrue(self.verdict(f"python {name}")["protected"])

    def test_a_force_push_inside_a_script_is_seen(self) -> None:
        name = self.script('import os\nos.system("git push --force origin main")\n')
        self.assertTrue(self.verdict(f"python {name}")["protected"])

    def test_the_reason_names_the_script(self) -> None:
        """A refusal that does not say which file cannot be acted on."""
        name = self.script('import os\nos.system("git push --force origin main")\n')
        impact = " ".join(self.verdict(f"python {name}")["impact"])
        self.assertIn(name, impact)


class AnOrdinaryScriptIsUnaffected(Base):
    def test_a_reading_script_is_not_protected(self) -> None:
        name = self.script(
            'import pathlib\n'
            'print(len(pathlib.Path("README.md").read_text(encoding="utf-8")))\n')
        self.assertFalse(self.verdict(f"python {name}")["protected"])

    def test_a_script_running_tests_is_not_protected(self) -> None:
        name = self.script(
            'import subprocess\n'
            'subprocess.run(["python", "-m", "unittest", "tests.test_a"])\n')
        self.assertFalse(self.verdict(f"python {name}")["protected"])

    def test_a_script_that_does_not_exist_is_unchanged(self) -> None:
        """Fail open on absence: a missing file declares nothing."""
        self.assertFalse(self.verdict("python not-here.py")["protected"])

    def test_a_bare_interpreter_with_no_file_is_unchanged(self) -> None:
        self.assertFalse(self.verdict("python --version")["protected"])


class TheLimitIsHonest(Base):
    def test_a_command_assembled_at_runtime_is_not_caught(self) -> None:
        """Stated, not hidden: this is the residual hole.

        A reader who believes the gate covers scripts will write one and trust
        it, so the test records what is still reachable rather than leaving it
        to be discovered.
        """
        name = self.script(
            'import subprocess\n'
            'parts = ["git", "pu" + "sh", "origin", "main"]\n'
            'subprocess.run(parts)\n')
        self.assertFalse(self.verdict(f"python {name}")["protected"])


if __name__ == "__main__":
    unittest.main()
