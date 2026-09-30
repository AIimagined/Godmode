"""Godmode's own launcher, invoked by its quoted absolute path, is Godmode.

The refusal hint prints `"C:/.../bin/godmode" authorize stage ...` and
the plugin's read and bookkeeping verbs are typed the same way; on
2026-09-28 the installed gate refused `"<path>/godmode" checkpoint ...`
and `"<path>/godmode" precheck --about ...` as an unknown command (R3).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

LAUNCHER = 'C:/Users/x/.claude/plugins/cache/aiimagined/godmode/0.3.31/bin/godmode'


class LauncherPathHeadTests(unittest.TestCase):
    def test_bookkeeping_verbs_by_quoted_path_are_local(self) -> None:
        for command in (
            f'"{LAUNCHER}" checkpoint "F0 built; unknown-after-&& R1 (gate refuses git add)" '
            '--next "operator commits; start F2"',
            f'"{LAUNCHER}" precheck --about "0.3.32 friction fixes F2 to F8"',
            f'"{LAUNCHER}" status',
            f'& "{LAUNCHER}.cmd" resume --refresh',
            f'python "{PLUGIN_ROOT.as_posix()}/scripts/godmode.py" brief',
        ):
            with self.subTest(command=command):
                verdict = classify_action(command, project_root=PLUGIN_ROOT)
                self.assertFalse(verdict["protected"], verdict)
                self.assertIn(verdict["tier"], ("R0", "R1"), verdict)

    def test_the_protected_verbs_stay_protected_by_path_too(self) -> None:
        for command in (
            f'"{LAUNCHER}" authorize stage --from-last-refusal',
            f'"{LAUNCHER}" config set uninitialized off',
            f'"{LAUNCHER}" protect --unpin docs/evaluator.md',
        ):
            with self.subTest(command=command):
                self.assertTrue(classify_action(command, project_root=PLUGIN_ROOT)["protected"])


if __name__ == "__main__":
    unittest.main()
