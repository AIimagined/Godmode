"""What the gate did to the commands this project actually ran.

Every previous defect in this classifier was found the same way: a human hit a
refusal in the middle of real work and said so. That is a slow oracle and an
expensive one, and it only ever surfaces the refusal someone happened to meet.

So the corpus was taken from the transcripts instead - every Bash, PowerShell
and file-edit call this project has made - and classified in bulk. Of 1,419
distinct commands the gate refused 506, and 74 of those named no mutation of
any kind. Twelve distinct defects were behind them, and one of the twelve ran
the other way: `echo pwned > ~/.bashrc` was **permitted**, because `~` is not a
path this process expands, so the target was joined to the project root and
passed containment. The gate approved a write to the user's shell profile on
the grounds that it was inside the working tree.

The transcripts are not shipped and this test does not read them - they are
private, and a test that depends on one machine's history proves nothing
anywhere else. What is kept is the distilled case for each defect, in both
directions: the read that must be allowed, and the mutation that must not be,
which is the only way a widened allowance can be shown not to have widened too
far.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import (  # noqa: E402
    classify_action, shell_segments,
)

PROJECT = PLUGIN_ROOT


class GateCase(unittest.TestCase):
    def allowed(self, command: str) -> None:
        verdict = classify_action(command, project_root=PROJECT)
        self.assertFalse(verdict["protected"],
                         f"refused a read: {command} -> {verdict['category']}")

    def refused(self, command: str, category: str | None = None) -> None:
        verdict = classify_action(command, project_root=PROJECT)
        self.assertTrue(verdict["protected"], f"permitted a mutation: {command}")
        if category:
            self.assertEqual(verdict["category"], category, command)


class UnexpandedPathTests(GateCase):
    """The one that failed open.

    `_contained` joined a relative-looking target to the project root. `~` and
    `$HOME` are not relative - the shell expands them somewhere else entirely -
    so the check answered a question about a path that would never exist.
    """

    def test_a_write_to_the_home_directory_is_not_inside_the_tree(self) -> None:
        self.refused("echo pwned > ~/.bashrc", "worktree-file-mutation")

    def test_a_variable_target_is_not_resolvable_and_so_not_contained(self) -> None:
        self.refused("echo x > $HOME/.profile", "worktree-file-mutation")
        self.refused("echo x > ${OUT}/report.txt", "worktree-file-mutation")

    def test_a_windows_variable_target_is_not_contained(self) -> None:
        self.refused("echo x > %APPDATA%/evil.txt", "worktree-file-mutation")

    def test_an_editor_call_on_an_unexpanded_path_is_refused(self) -> None:
        self.refused("write file ~/.ssh/authorized_keys")

    def test_a_literal_path_inside_the_tree_still_works(self) -> None:
        """The fix must not make ordinary writing protected."""
        self.allowed("echo hello > notes.txt")


class NullDeviceTests(GateCase):
    """Discarding output is not writing a file."""

    def test_writing_to_the_null_device_is_not_a_mutation(self) -> None:
        self.allowed("python scripts/godmode.py integrity > /dev/null")
        self.allowed("make build >/dev/null 2>&1")
        self.allowed("python x.py > NUL")

    def test_a_real_path_outside_the_tree_is_still_refused(self) -> None:
        self.refused("python x.py > /etc/passwd", "worktree-file-mutation")


class GitGlobalOptionTests(GateCase):
    """`git -C path log` is a log."""

    def test_a_read_keeps_its_classification_through_a_global_option(self) -> None:
        self.allowed("git -C /some/repo log --oneline -1")
        self.allowed("git -c core.pager=cat log -1")
        self.allowed("git --no-pager diff")

    def test_a_mutation_keeps_its_classification_too(self) -> None:
        """Before the fix this was refused as an unknown - the right answer
        for the wrong reason, which stops being right when the fallback
        changes. It should be refused as what it is."""
        self.refused("git -C /some/repo push origin main", "git-history-or-remote")

    def test_a_forced_push_still_escalates_through_a_global_option(self) -> None:
        verdict = classify_action("git -C /repo push --force origin main",
                                  project_root=PROJECT)
        self.assertEqual(verdict["tier"], "R5")

    def test_pointing_git_at_other_binaries_is_not_a_mere_option(self) -> None:
        """`--exec-path` changes what runs, not where it runs."""
        self.refused("git --exec-path=/tmp/evil status")


class GitReadSubcommandTests(GateCase):
    """The subcommand list was written from memory and missed most of it."""

    READS = (
        "git rev-list --count v0.2.6..HEAD",
        "git ls-files --error-unmatch README.md",
        "git ls-tree HEAD",
        "git ls-remote --heads origin",
        "git describe --tags",
        "git blame README.md",
        "git cat-file -p HEAD",
        "git shortlog -sn",
        "git for-each-ref --format=%(refname)",
        "git show-ref --tags",
        "git merge-base main HEAD",
        "git check-ignore -v build",
        "git count-objects -v",
        "git grep -n needle",
    )

    def test_the_reads_are_reads(self) -> None:
        for command in self.READS:
            with self.subTest(command=command):
                self.allowed(command)

    def test_merge_base_is_not_a_merge(self) -> None:
        """The word boundary after `merge` falls inside the hyphen, so a
        read reported as history mutation."""
        self.allowed("git merge-base main HEAD")
        self.refused("git merge main", "git-history-or-remote")

    def test_the_plumbing_that_writes_still_fails_closed(self) -> None:
        for command in ("git update-ref refs/heads/main HEAD",
                        "git commit-tree -m x HEAD^{tree}",
                        "git hash-object -w file.txt",
                        "git reflog delete HEAD@{1}",
                        "git config user.email evil@example.invalid"):
            with self.subTest(command=command):
                self.refused(command)


class HelpFlagTests(GateCase):
    """A banner describing an operation is not the operation."""

    def test_asking_a_command_to_explain_itself_is_a_read(self) -> None:
        self.allowed("gh --help")
        self.allowed("python scripts/godmode.py release --help")
        self.allowed("git push --help")
        self.allowed("graphify --version")

    def test_a_help_flag_does_not_excuse_a_redirect_beside_it(self) -> None:
        """The flag stops the command from acting; it does not stop the
        shell from writing where the output goes."""
        self.refused("curl --help > ~/.bashrc", "worktree-file-mutation")

    def test_a_help_flag_does_not_excuse_a_second_command(self) -> None:
        self.refused("gh --help && rm -rf build", "filesystem-mutation")

    def test_single_letter_forms_are_not_trusted(self) -> None:
        """`sort -h` sorts and `du -h` formats; one letter means whatever
        each tool decided, so only the long forms count."""
        verdict = classify_action("gh -h", project_root=PROJECT)
        self.assertTrue(verdict["protected"])


class ForgeReadTests(GateCase):
    """`gh auth status` prints who you are and was an unknown mutation."""

    def test_the_read_verbs_are_reads(self) -> None:
        for command in ("gh auth status", "gh repo view AIimagined/Godmode --json name",
                        "gh run list --limit 5", "gh pr view 12",
                        "gh release list", "gh workflow list"):
            with self.subTest(command=command):
                self.allowed(command)

    def test_the_write_verbs_are_not(self) -> None:
        for command in ("gh release create v0.3.0", "gh pr merge 12 --squash",
                        "gh repo delete AIimagined/Godmode", "gh pr close 12",
                        "gh secret set TOKEN"):
            with self.subTest(command=command):
                self.refused(command)

    def test_the_api_default_is_a_read(self) -> None:
        self.allowed("gh api repos/x/y/contents")
        self.allowed("gh api -X GET repos/x/y/pulls")

    def test_the_api_becomes_a_write_through_a_flag_not_a_word(self) -> None:
        for command in ("gh api -X POST repos/x/y/releases",
                        "gh api --method DELETE repos/x/y/labels/bug",
                        "gh api repos/x/y/issues -f title=oops",
                        "gh api repos/x/y/issues --input body.json"):
            with self.subTest(command=command):
                self.refused(command)


class GodmodeOwnReadTests(GateCase):
    """The tool built so release state would be read rather than remembered,
    refused at R4 by the gate shipped beside it for containing `release`."""

    def test_comparing_release_state_is_a_read(self) -> None:
        self.allowed("python scripts/godmode.py --project . release --published v0.2.5")

    def test_the_allowance_does_not_generalise_to_other_words(self) -> None:
        self.refused("python manage.py migrate", "database-mutation")
        self.refused("python deploy.py --publish", "release-or-external-write")


class PowerShellAssignmentTests(GateCase):
    """Every PowerShell script that opened by naming a path was an unknown
    mutation from its first line."""

    def test_a_literal_assignment_changes_nothing(self) -> None:
        self.allowed('$d = "C:\\Users\\x\\docs"')
        self.allowed("$env:GODMODE_STATE_HOME = 'C:\\temp\\state'")

    def test_the_rest_of_the_script_is_still_judged(self) -> None:
        self.allowed('$d = "C:\\x"; Get-ChildItem $d')
        self.refused('$d = "C:\\x"; Remove-Item $d -Recurse', "filesystem-mutation")

    def test_an_assignment_whose_value_is_a_command_keeps_the_command(self) -> None:
        """Stripping a prefix off `$d = Remove-Item x` would judge the
        remainder and lose the verb, which is how a laundering path gets
        built by accident."""
        self.refused("$d = Remove-Item C:\\x")


class EnvironmentBindingTests(GateCase):
    """Pointing a test at its own state directory was a protected operation."""

    def test_an_ordinary_binding_is_bookkeeping(self) -> None:
        self.allowed('export GODMODE_STATE_HOME="/tmp/state"')
        self.allowed("unset GODMODE_STATE_HOME")

    def test_a_variable_that_changes_what_runs_is_not(self) -> None:
        for command in ('export PATH="/evil:$PATH"', "export LD_PRELOAD=/tmp/x.so",
                        "export PYTHONPATH=/tmp", "export GIT_SSH=/tmp/x",
                        "export BASH_ENV=/tmp/rc", "export NODE_OPTIONS=--require=/tmp/x"):
            with self.subTest(command=command):
                self.refused(command)

    def test_a_binding_cannot_carry_a_command(self) -> None:
        self.refused("export A=1 && rm -rf x", "filesystem-mutation")


class QuotedSeparatorTests(GateCase):
    """A search reported as a mutation because its regex contained a quote."""

    COMMAND = 'grep -nE "^_CHECKS|\\"code\\":|def check_" scripts/x.py | head -20'

    def test_an_escaped_quote_does_not_end_the_string(self) -> None:
        self.assertEqual(
            shell_segments(self.COMMAND),
            ['grep -nE "^_CHECKS|\\"code\\":|def check_" scripts/x.py', "head -20"])

    def test_the_search_is_a_read(self) -> None:
        self.allowed(self.COMMAND)

    def test_an_escaped_separator_still_cannot_hide_a_mutation(self) -> None:
        """Not splitting on `\\;` matches what the shell does - it passes a
        literal semicolon and starts no second command - and the mutation is
        still visible in the text either way."""
        self.refused("ls \\; rm -rf /")
        self.refused('echo "a\\" ; rm -rf /"')

    def test_an_unescaped_separator_still_splits(self) -> None:
        self.assertEqual(shell_segments("ls; rm -rf x"), ["ls", "rm -rf x"])
        self.refused("ls; rm -rf x", "filesystem-mutation")


class StillClosedTests(GateCase):
    """The refusals that are the design working, kept so a later widening has
    to argue with a test rather than with a memory."""

    def test_an_unknown_binary_fails_closed(self) -> None:
        for command in ("wsl --list --verbose", "graphify clone https://example.invalid/x",
                        "codex plugin add godmode"):
            with self.subTest(command=command):
                self.refused(command)

    def test_a_powershell_script_block_is_not_read_by_its_verb(self) -> None:
        """`ForEach-Object { … }` runs whatever the block contains."""
        self.refused("ForEach-Object { Remove-Item x }")

    def test_the_worst_part_of_a_pipeline_still_decides(self) -> None:
        self.refused("git status && git push --force origin main")


if __name__ == "__main__":
    unittest.main()
