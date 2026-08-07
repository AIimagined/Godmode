"""Can a developer still work with the gate on?

Nothing asked this before shipping. The pre-tool gate passed twelve unit tests
that each proved a refusal, and then denied `ls` in a live session — every
compound command, every pipe, every ordinary inspection fell through to
`unclassified-mutation` and failed closed. Failing closed on an unknown
mutation is right; applying it to `ls` makes the product unusable, which is the
approval-fatigue failure the threat model names.

So this file asserts the other half of the contract: the commands a working
session actually issues must pass, and the dangerous ones must still not.
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

# Lifted from one real session's command history, not imagined.
EVERYDAY_READ_ONLY = (
    "ls",
    "ls scripts/godmode_runtime",
    "ls -la assets/",
    "cat README.md",
    "head -30 CHANGELOG.md",
    "tail -5 CHANGELOG.md",
    "wc -l scripts/godmode.py",
    "grep -n 'def rank' scripts/godmode_runtime/godmode_corpus.py",
    "git status --short",
    "git log --oneline -5",
    "git diff --stat",
    "git show HEAD --stat",
    "python -m unittest discover -s tests",
    "python scripts/godmode.py --project . selftest --brief",
    "python -c \"print(1)\"",
    # Compound and piped forms: a pipeline of read-only parts is read-only.
    "ls scripts/godmode_runtime | head -3",
    "grep -rn TODO scripts | wc -l",
    "cat CHANGELOG.md | head -40",
    "git log --oneline -10 && git status --short",
    "cd scripts && ls",
)

STILL_PROTECTED = (
    "git push origin main",
    "git push --force",
    "git reset --hard HEAD~3",
    "git branch -D main",
    "git clean -fd",
    "rm -rf build",
    "DROP TABLE orders",
    # A safe head does not launder a dangerous tail.
    "git status && git push origin main",
    "ls | xargs rm",
    "cat notes.txt; rm -rf /tmp/x",
)


class EverydayCommandTests(unittest.TestCase):
    def test_a_working_session_is_not_blocked(self) -> None:
        blocked = [
            command for command in EVERYDAY_READ_ONLY
            if classify_action(command)["protected"]
        ]
        self.assertEqual(blocked, [], f"the gate would stop ordinary work: {blocked}")

    def test_everyday_commands_sit_at_the_two_lowest_tiers(self) -> None:
        """Reading is R0; running an interpreter is R1, because executing code
        is not reading it — the tier says so even though neither is gated."""
        for command in EVERYDAY_READ_ONLY:
            self.assertIn(classify_action(command)["tier"], ("R0", "R1"), command)

    def test_running_code_is_recorded_as_compute_not_as_a_read(self) -> None:
        verdict = classify_action("python -m unittest discover -s tests")
        self.assertFalse(verdict["protected"])
        self.assertEqual(verdict["tier"], "R1")
        self.assertEqual(verdict["category"], "local-compute-or-state")


class DangerousCommandTests(unittest.TestCase):
    def test_mutations_are_still_protected(self) -> None:
        allowed = [
            command for command in STILL_PROTECTED
            if not classify_action(command)["protected"]
        ]
        self.assertEqual(allowed, [], f"the gate would permit a mutation: {allowed}")

    def test_a_safe_prefix_cannot_launder_a_dangerous_tail(self) -> None:
        verdict = classify_action("git status && git push --force origin main")
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["tier"], "R5")

    def test_an_unknown_command_still_fails_closed(self) -> None:
        verdict = classify_action("frobnicate --all")
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["category"], "unclassified-mutation")


class FileEditTests(unittest.TestCase):
    """Editing a working file is the work; a per-write prompt is what makes an
    operator switch the gate off entirely."""

    def test_ordinary_edits_need_no_capability(self) -> None:
        for operation in ("write file scripts/godmode_runtime/godmode_corpus.py",
                          "edit file README.md",
                          "write file tests/test_new.py"):
            verdict = classify_action(operation)
            self.assertFalse(verdict["protected"], operation)
            self.assertEqual(verdict["tier"], "R2", operation)

    def test_edits_outside_ordinary_working_files_stay_protected(self) -> None:
        for operation in ("write file .git/config",
                          "edit file ../outside.txt",
                          "write file /etc/passwd",
                          "write file .env",
                          "write file secrets/id_rsa"):
            self.assertTrue(classify_action(operation)["protected"], operation)


class AssignmentTests(unittest.TestCase):
    def test_a_bare_assignment_changes_nothing(self) -> None:
        verdict = classify_action("P=/tmp/x")
        self.assertFalse(verdict["protected"])
        self.assertEqual(verdict["tier"], "R0")

    def test_an_assignment_is_judged_on_the_command_it_prefixes(self) -> None:
        self.assertFalse(classify_action("GODMODE_STATE_HOME=/tmp/s python -m unittest")["protected"])
        self.assertTrue(classify_action("FOO=bar rm -rf /tmp/x")["protected"])


class SegmentationTests(unittest.TestCase):
    def test_segments_split_on_every_shell_separator(self) -> None:
        from godmode_runtime.godmode_sentinel import shell_segments

        self.assertEqual(
            shell_segments("ls | head -3 && git status; cat x"),
            ["ls", "head -3", "git status", "cat x"])

    def test_quoted_separators_do_not_split(self) -> None:
        from godmode_runtime.godmode_sentinel import shell_segments

        self.assertEqual(shell_segments("grep 'a|b' file"), ["grep 'a|b' file"])


if __name__ == "__main__":
    unittest.main()
