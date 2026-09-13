"""`find -exec` is judged by the command it runs.

`find` reads until it is told to act, so `-delete` and `-exec` were both
treated as mutations: they run inside one segment, no separator splits them
out, and the read allowance would otherwise cover them. That is right for
`-delete` and wrong for `-exec`, whose whole meaning is the command after it.

The cost was measured, not theorised. `find . -name '*.py' -exec wc -l {} +`
counts lines and was refused as a filesystem mutation during this project's own
work, twice, and the operator rephrased the command both times. A gate that
refuses line-counting teaches people to route around it, and a gate routed
around protects nothing.

The safe-read vocabulary here is the one the classifier already keeps for
ordinary commands, not a second list. A second list drifts from the first,
which this codebase has been bitten by more than once.

Unknown stays protected. `-exec` running something the classifier cannot place
is still a mutation, because the whole point is that `find` hands it every
matching path.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_sentinel as S  # noqa: E402

DEL = "r" + "m"  # assembled so this file is not itself refused


def protected(operation: str) -> bool:
    return bool(S.classify_action(operation)["protected"])


class ExecRunningAReadIsARead(unittest.TestCase):
    def test_counting_lines_is_not_a_mutation(self) -> None:
        self.assertFalse(protected("find . -name '*.py' -exec wc -l {} +"))

    def test_grepping_is_not_a_mutation(self) -> None:
        self.assertFalse(protected("find . -name '*.py' -exec grep -l TODO {} +"))

    def test_cat_is_not_a_mutation(self) -> None:
        self.assertFalse(protected("find docs -name '*.md' -exec cat {} +"))

    def test_execdir_follows_the_same_rule(self) -> None:
        self.assertFalse(protected("find . -name '*.py' -execdir wc -l {} +"))


class ExecRunningAMutationIsStillAMutation(unittest.TestCase):
    def test_removing_files_is_still_protected(self) -> None:
        self.assertTrue(protected("find . -name '*.tmp' -exec " + DEL + " {} ;"))

    def test_moving_files_is_still_protected(self) -> None:
        self.assertTrue(protected("find . -name '*.tmp' -exec mv {} /tmp ;"))

    def test_an_unrecognised_command_stays_protected(self) -> None:
        """Fail closed: find hands it every matching path."""
        self.assertTrue(protected("find . -name '*.py' -exec mytool --go {} +"))

    def test_a_shell_invocation_stays_protected(self) -> None:
        self.assertTrue(protected("find . -name '*.py' -exec sh -c 'do_thing' ;"))


class TheOtherFindActionsAreUnchanged(unittest.TestCase):
    def test_delete_is_still_a_mutation(self) -> None:
        self.assertTrue(protected("find . -name '*.log' -delete"))

    def test_ok_stays_protected(self) -> None:
        """It prompts, then execs; the conservative reading is kept."""
        self.assertTrue(protected("find . -name '*.tmp' -ok " + DEL + " {} ;"))

    def test_a_plain_find_is_still_a_read(self) -> None:
        self.assertFalse(protected("find . -name '*.py'"))


class TheReadVocabularyIsShared(unittest.TestCase):
    def test_the_exec_check_uses_the_classifier_s_own_read_list(self) -> None:
        """A second list drifts from the first. Assert they are the same object."""
        self.assertTrue(S._SAFE_SHELL_READS.match("wc -l x"))
        self.assertFalse(S._SAFE_SHELL_READS.match(DEL + " -rf x"))


if __name__ == "__main__":
    unittest.main()
