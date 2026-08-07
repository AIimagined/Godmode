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

# The corpus above came from one session's history, and that session ran a
# POSIX-shaped shell — so it inherited the platform, and the fix it drove left
# every PowerShell call denied on the machine the plugin was installed on. A
# usability suite that only knows one shell asserts usability on one platform.
WINDOWS_READ_ONLY = (
    "Get-ChildItem",
    "Get-ChildItem -Recurse -Filter *.py",
    "Get-Content README.md",
    "Get-Content CHANGELOG.md -TotalCount 30",
    "Get-Location",
    "Get-Command python",
    "Test-Path scripts/godmode.py",
    "Resolve-Path .",
    "Join-Path scripts godmode.py",
    "Split-Path -Parent scripts/godmode.py",
    "Select-String -Path scripts/*.py -Pattern 'def rank'",
    "Compare-Object (Get-Content a.txt) (Get-Content b.txt)",
    "Format-Table -AutoSize",
    "Write-Output done",
    # Piped forms, including the exact call this gate denied while being tested.
    "Get-ChildItem scripts | Select-Object -ExpandProperty Name",
    "Get-ChildItem \"$env:USERPROFILE\\.claude\\plugins\\cache\" -Recurse "
    "-Filter godmode_sentinel.py -ErrorAction SilentlyContinue "
    "| Select-Object -ExpandProperty FullName",
    "Get-Content CHANGELOG.md | Measure-Object -Line",
    "Get-Process | Where-Object { $_.Name -eq 'python' }",
    "Get-ChildItem | Sort-Object Name | Group-Object Extension",
    # cmd.exe vocabulary that survives inside PowerShell.
    "findstr /n \"def rank\" scripts\\godmode.py",
    "where python",
    # The other command the gate denied: `find` was missing from the read set.
    "ls ~/.claude/plugins/cache/ 2>/dev/null | grep -i god; echo \"---\"; "
    "find ~/.claude/plugins -name godmode_sentinel.py 2>/dev/null",
    "find . -name '*.py' -type f",
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

# PowerShell's own verbs say which of these mutate. Most are protected by
# failing closed rather than by a rule naming them, which is the intended
# default — the assertion is that widening the read set did not widen these.
WINDOWS_STILL_PROTECTED = (
    "Remove-Item -Recurse -Force build",
    "Remove-Item -Path .git -Recurse",
    "Set-Content -Path README.md -Value 'x'",
    "Out-File -FilePath notes.txt",
    "New-Item -ItemType Directory build",
    "Clear-Content log.txt",
    "Rename-Item a.txt b.txt",
    "Move-Item a.txt b.txt",
    "Stop-Process -Name python -Force",
    "del build\\out.txt",
    "rd /s /q build",
    # A safe head does not launder a dangerous tail, in either shell.
    "Get-ChildItem | Remove-Item -Force",
    "Get-Location; Remove-Item -Recurse build",
    # `find` reads until it is told to act, and no separator splits these out.
    "find . -name '*.pyc' -delete",
    "find . -name '*.tmp' -exec rm {} +",
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


class WindowsCommandTests(unittest.TestCase):
    """The plugin was installed on Windows, where the hook fires on PowerShell
    calls too. Recognising only POSIX vocabulary denied every one of them."""

    def test_a_working_powershell_session_is_not_blocked(self) -> None:
        blocked = [
            command for command in WINDOWS_READ_ONLY
            if classify_action(command)["protected"]
        ]
        self.assertEqual(blocked, [], f"the gate would stop ordinary work: {blocked}")

    def test_windows_reads_are_recorded_as_reads(self) -> None:
        for command in WINDOWS_READ_ONLY:
            self.assertEqual(classify_action(command)["tier"], "R0", command)

    def test_powershell_mutations_are_still_protected(self) -> None:
        allowed = [
            command for command in WINDOWS_STILL_PROTECTED
            if not classify_action(command)["protected"]
        ]
        self.assertEqual(allowed, [], f"the gate would permit a mutation: {allowed}")

    def test_an_unlisted_powershell_verb_fails_closed(self) -> None:
        """Read verbs are recognised as a set; every other verb is absent on
        purpose, so a cmdlet nobody enumerated is denied rather than allowed."""
        verdict = classify_action("Invoke-WebRequest https://example.com")
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["category"], "unclassified-mutation")


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


class ReadPrefixLaunderingTests(unittest.TestCase):
    """Granting a read allowance created something to hide behind.

    While `ls` fell closed there was no safe prefix in the language, so a
    separator the splitter missed cost nothing. Now a missed separator hands a
    whole command the tier of its first word, which is the laundering the
    segmentation was built to stop — so every way to start a second command has
    to end a segment, and the two that cannot be split are denied outright.
    """

    def test_a_newline_starts_a_new_command(self) -> None:
        for operation in ("ls\nInvoke-WebRequest https://example.com",
                          "Get-ChildItem\r\nStop-Process -Name python",
                          "cat notes.txt\ngit push --force"):
            self.assertTrue(classify_action(operation)["protected"], repr(operation))

    def test_a_bare_ampersand_starts_a_new_command(self) -> None:
        verdict = classify_action("ls & Invoke-WebRequest https://example.com")
        self.assertTrue(verdict["protected"])

    def test_substitution_is_denied_because_it_cannot_be_split_out(self) -> None:
        """A substitution runs a command that is not a segment of the line, so
        there is nothing to classify — the read allowance is withheld rather
        than extended over an operation the gate never saw."""
        for operation in ("ls $(curl -s https://example.com)",
                          "ls `curl -s https://example.com`",
                          "cat ${EVIL}"):
            self.assertTrue(classify_action(operation)["protected"], operation)

    def test_a_shell_variable_is_not_a_substitution(self) -> None:
        for operation in ("echo $HOME",
                          "echo $env:USERPROFILE",
                          "Get-Process | Where-Object { $_.Name -eq 'python' }"):
            self.assertFalse(classify_action(operation)["protected"], operation)


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
