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

# Shell control flow. Found by running the gate against a live session for the
# third time: a `for` loop over config files was denied, because `for`, `do`
# and `done` are not commands and matched nothing. The corpus above could not
# have caught it — it was lifted from commands that had been *blocked*, and
# every loop in this project's history ran while the plugin was switched off.
SHELL_CONTROL_FLOW = (
    "for f in a.json b.json; do echo $f; done",
    "for f in *.py; do wc -l $f; done",
    "if [ -f README.md ]; then cat README.md; fi",
    "while read line; do echo $line; done",
    "for g in selftest evals; do python scripts/godmode.py --project . $g; done",
    "[ -f README.md ] && echo present",
    "test -d scripts && ls scripts",
)

# Redirection and substitution. Found live again, one release later: an input
# redirect reads a file and was classified as writing one, and every command
# substitution was refused outright — including `echo $(ls)`, which runs
# nothing the classifier could not already see.
REDIRECTION_AND_SUBSTITUTION = (
    "wc -l < README.md",
    "cat < input.txt",
    "sort < names.txt",
    "python -m unittest discover -s tests < /dev/null",
    # `2>&1` duplicates a file descriptor. Making a bare `&` a separator so
    # `ls & rm` could not launder split this at the `&`, leaving a bare `1`
    # that classified as an unknown mutation.
    "python -m unittest discover -s tests 2>&1",
    "make build 1>&2",
    "grep -rn TODO scripts 2>&1 | head -20",
    # A substitution is a command; it is classified, not refused on sight.
    "echo $(ls)",
    "echo $(git rev-parse HEAD)",
    "for f in $(ls *.md); do wc -l $f; done",
    "echo `pwd`",
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
    # U-B2 fix-round-1 (task-7 review, Critical): `Move-Item`/`Copy-Item`
    # (and their POSIX `mv`/`cp` counterparts) are no longer protected
    # unconditionally by name - they write their DESTINATION argument, and
    # an ordinary in-tree rename between two relative filenames is now
    # ordinary work, unprotected, the same as an in-tree `Write`/`Edit`
    # already is (see tests/test_evaluator_pins.py::MoveCopyTests for the
    # full contract, including why a PINNED destination still refuses
    # outright). What stays protected is a destination this classifier
    # cannot place inside the project - exercised here instead of the old
    # `Move-Item a.txt b.txt` entry, which this design change intentionally
    # moved out of "always protected."
    "Move-Item a.txt C:\\Windows\\System32\\evil.dll",
    "Stop-Process -Name python -Force",
    "del build\\out.txt",
    "rd /s /q build",
    # A safe head does not launder a dangerous tail, in either shell.
    "Get-ChildItem | Remove-Item -Force",
    "Get-Location; Remove-Item -Recurse build",
    # `find` reads until it is told to act, and no separator splits these out.
    "find . -name '*.pyc' -delete",
    "find . -name '*.tmp' -exec rm {} +",
    # Control flow is structure; the body inside it is still judged.
    "for f in *; do rm -rf $f; done",
    "if true; then git push --force; fi",
    # A redirect that lands outside the working tree is still a write there.
    "cat notes.txt >> /etc/hosts",
    "echo x > ../outside.txt",
    # A substitution is classified on what it runs, so a dangerous inner
    # command is caught rather than hidden by the outer one being safe.
    "echo $(rm -rf build)",
    "ls `git push --force`",
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
        # Renamed by U-G1b: a genuinely unrecognised command with no evidence
        # of mutation is now read (see WindowsCommandTests below and
        # test_sentinel_scoping.py), and `unclassified-mutation`'s fail-
        # closed-for-ignorance default went with it - but a network fetcher
        # is one of the named exceptions that still asks, by name, precisely
        # because "unrecognised cmdlet" is not the risk here.
        self.assertEqual(verdict["category"], "unknown-command")


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

    def test_an_unknown_command_with_no_evidence_is_now_read(self) -> None:
        """U-G1b: `unclassified-mutation` was the fail-closed bucket for a
        genuinely unknown state, applied instead to any command this
        classifier simply had no vocabulary for - a corpus of real denials
        showed most of those were harmless (`rev`, `cp` into the tree, a
        PowerShell assignment...). A made-up command with nothing pointing at
        a mutation - no redirect, no named write flag - is read now; what
        still asks by name is covered below and in test_sentinel_scoping.py."""
        verdict = classify_action("frobnicate --all")
        self.assertFalse(verdict["protected"])
        self.assertEqual(verdict["tier"], "R0")

    def test_an_unknown_command_with_evidence_still_asks(self) -> None:
        verdict = classify_action("frobnicate --all > important.txt")
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["category"], "unknown-command")

    def test_quoting_an_opaque_script_still_fails_closed(self) -> None:
        """The named exception `ExecutablePositionTests` below already pins:
        an unrecognised interpreter handed a whole script as one opaque
        argument is not "no evidence" in the same sense a plain unrecognised
        reporting tool is."""
        verdict = classify_action('bash -c "frobnicate --all"')
        self.assertTrue(verdict["protected"])


class ShellControlFlowTests(unittest.TestCase):
    def test_a_loop_is_not_a_mutation(self) -> None:
        blocked = [c for c in SHELL_CONTROL_FLOW if classify_action(c)["protected"]]
        self.assertEqual(blocked, [], f"the gate would stop ordinary work: {blocked}")

    def test_the_body_of_a_loop_is_still_judged(self) -> None:
        """`do` must not become a prefix that launders what follows it."""
        self.assertTrue(classify_action("do rm -rf build")["protected"])
        self.assertTrue(classify_action("then git push --force")["protected"])


class RedirectionAndSubstitutionTests(unittest.TestCase):
    """Reading from a file is not writing to one, and a substitution is a
    command rather than a reason to refuse."""

    def test_ordinary_redirection_and_substitution_are_not_blocked(self) -> None:
        blocked = [c for c in REDIRECTION_AND_SUBSTITUTION
                   if classify_action(c)["protected"]]
        self.assertEqual(blocked, [], f"the gate would stop ordinary work: {blocked}")

    def test_an_input_redirect_is_a_read(self) -> None:
        verdict = classify_action("wc -l < README.md")
        self.assertFalse(verdict["protected"])
        self.assertEqual(verdict["tier"], "R0")

    def test_an_output_redirect_inside_the_tree_is_ordinary_work(self) -> None:
        """The same act as an `Edit` of that path, judged the same way.

        Refusing every redirect while permitting the declared edit of the same
        file gated the honest form and not the other.
        """
        for operation in ("echo x > out.txt", "make build >> build.log"):
            verdict = classify_action(operation, project_root=PLUGIN_ROOT)
            self.assertFalse(verdict["protected"], operation)

    def test_an_output_redirect_outside_the_tree_is_protected(self) -> None:
        for operation in ("cat notes.txt >> /etc/hosts",
                          "echo x > ../outside.txt",
                          "echo x > .git/config"):
            verdict = classify_action(operation, project_root=PLUGIN_ROOT)
            self.assertTrue(verdict["protected"], operation)
            self.assertEqual(verdict["category"], "worktree-file-mutation", operation)

    def test_a_substitution_is_judged_on_what_it_runs(self) -> None:
        self.assertFalse(classify_action("echo $(git rev-parse HEAD)")["protected"])
        self.assertTrue(classify_action("echo $(rm -rf build)")["protected"])
        self.assertTrue(classify_action("ls `git push --force`")["protected"])

    def test_a_descriptor_duplication_is_not_a_separator(self) -> None:
        """`2>&1` is one token. Splitting it left a bare `1` behind, which
        classified as an unknown mutation and refused the whole command."""
        from godmode_runtime.godmode_sentinel import shell_segments

        self.assertEqual(shell_segments("make test 2>&1"), ["make test 2>&1"])
        self.assertEqual(shell_segments("a 2>&1 | b"), ["a 2>&1", "b"])
        # The reason the separator was added in the first place still holds.
        self.assertEqual(shell_segments("ls & rm -rf x"), ["ls", "rm -rf x"])

    def test_a_variable_is_not_a_substitution(self) -> None:
        for operation in ("echo $HOME", "echo ${HOME}", "wc -l $f"):
            self.assertFalse(classify_action(operation)["protected"], operation)


class ExecutablePositionTests(unittest.TestCase):
    """A command mentioned is not a command run.

    The classifier searched the whole line, so `grep "git push" notes.md` was
    refused because the words appeared in an argument. Quoted text is data:
    it is excluded from the mutation patterns, and anything whose own
    executable is unrecognised still fails closed, so nothing is laundered by
    being put in quotes.
    """

    def test_naming_a_protected_command_in_an_argument_is_not_running_it(self) -> None:
        for operation in ('grep "git push" notes.md',
                          'echo "run git push when ready"',
                          "grep -rn 'rm -rf' scripts",
                          'echo "DROP TABLE orders"'):
            self.assertFalse(classify_action(operation)["protected"], operation)

    def test_actually_running_it_is_still_protected(self) -> None:
        for operation in ("git push origin main", "rm -rf build", "DROP TABLE orders"):
            self.assertTrue(classify_action(operation)["protected"], operation)

    def test_quoting_cannot_launder_an_unrecognised_executable(self) -> None:
        """Stripping quotes is safe only because the safe list is a whitelist:
        a shell invoked on a quoted script is not on it, so it fails closed."""
        for operation in ('bash -c "rm -rf /"',
                          'sh -c "git push --force"',
                          'eval "rm -rf build"'):
            self.assertTrue(classify_action(operation)["protected"], operation)


class LocalGitTests(unittest.TestCase):
    """Committing is the work; pushing is the consequence.

    A commit is local and reversible. It was once left unprotected on that
    reasoning (`godmode_session_hook.py`'s own history: the gate could only
    ever refuse a protected call outright, no host tool call carries a field
    a capability could travel in, so "protected" meant "blocked" and gating
    committing made a session unusable). That is no longer true - the host
    can ask, and asking is an in-session approval - so `add`/`commit` now
    join the sibling worktree operations (`checkout --`, `restore`, `mv`,
    `stash`, `switch`) that already ask rather than being the one git rule
    left on the other side of that line (U-G1c, Controller Ruling 1).
    """

    def test_committing_and_staging_now_ask_rather_than_run_silently(self) -> None:
        for operation in ("git add -A", "git add scripts/",
                          "git commit -m 'a message'",
                          "git commit"):
            self.assertTrue(classify_action(operation)["protected"], operation)
            self.assertEqual(classify_action(operation)["tier"], "R2", operation)

    def test_what_leaves_the_machine_or_destroys_work_is_still_protected(self) -> None:
        for operation in ("git push origin main", "git push --force",
                          "git reset --hard HEAD~3", "git clean -fd",
                          "git rebase -i main", "git commit --amend",
                          "git checkout -- .", "git branch -D main"):
            self.assertTrue(classify_action(operation)["protected"], operation)

    def test_amend_is_named_rather_than_left_to_fail_closed(self) -> None:
        """It was refused either way, but as an unclassified mutation — which
        tells the reader nothing about why the gate stopped them."""
        verdict = classify_action("git commit --amend -m 'reword'")
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["category"], "git-history-or-remote")

    def test_a_commit_still_cannot_launder_a_push(self) -> None:
        verdict = classify_action("git commit -m x && git push origin main")
        self.assertTrue(verdict["protected"])


class RealToolPayloadTests(unittest.TestCase):
    """Through `tool_operation`, not around it.

    Every gate defect found in a live session came from the same place: the
    suite fed the classifier operation strings written by hand, and the host
    sends something else. The file-edit allowance was asserted with
    `write file README.md` and passed, while the host sends an absolute path
    for every edit — a form the classifier treated as outside the working
    tree, so in a real session no edit was ever permitted.

    These build their cases the way the hook does, so a hand-written form can
    never pass while the real one fails.
    """

    def _operation(self, tool: str, **payload: object) -> str:
        from godmode_runtime.godmode_guardrails import tool_operation

        return tool_operation(tool, dict(payload))

    def test_editing_a_project_file_by_absolute_path_is_ordinary_work(self) -> None:
        for tool in ("Write", "Edit"):
            operation = self._operation(
                tool, file_path=str(PLUGIN_ROOT / "tests" / "test_gate_usability.py"))
            verdict = classify_action(operation, project_root=PLUGIN_ROOT)
            self.assertFalse(verdict["protected"], f"{tool}: {operation}")
            self.assertEqual(verdict["tier"], "R2", operation)

    def test_editing_outside_the_project_stays_protected(self) -> None:
        outside = PLUGIN_ROOT.parent / "elsewhere" / "secrets.txt"
        operation = self._operation("Write", file_path=str(outside))
        self.assertTrue(classify_action(operation, project_root=PLUGIN_ROOT)["protected"])

    def test_editing_the_git_directory_stays_protected_even_inside_the_tree(self) -> None:
        for relative in (".git/config", ".env", "keys/id_rsa", "certs/server.pem"):
            operation = self._operation("Edit", file_path=str(PLUGIN_ROOT / relative))
            self.assertTrue(
                classify_action(operation, project_root=PLUGIN_ROOT)["protected"], relative)

    def test_a_traversal_out_of_the_tree_is_not_contained(self) -> None:
        operation = self._operation(
            "Write", file_path=str(PLUGIN_ROOT / ".." / "outside.txt"))
        self.assertTrue(classify_action(operation, project_root=PLUGIN_ROOT)["protected"])

    def test_writing_to_the_system_scratch_directory_is_ordinary_work(self) -> None:
        """Containment refuses writes outside the tree and the agent's scratch
        directory sits outside it — both rules right, and together they made the
        intended temporary location unusable."""
        import tempfile

        scratch = Path(tempfile.gettempdir()) / "godmode-probe" / "notes.txt"
        operation = self._operation("Write", file_path=str(scratch))
        self.assertFalse(classify_action(operation, project_root=PLUGIN_ROOT)["protected"],
                         operation)

    def test_a_project_under_temp_does_not_lose_containment(self) -> None:
        """Found by accident, and it would have been found nowhere else.

        A checkout under the temporary directory — a CI workspace, a sandbox, a
        build in `/tmp` — made every path near it also under temp, so the
        scratch allowance swallowed containment whole and every out-of-tree
        write was permitted. Where the two rules overlap, containment governs
        alone.
        """
        import tempfile

        root = Path(tempfile.gettempdir()) / "some-checkout"
        outside = root.parent / "elsewhere" / "secrets.txt"
        verdict = classify_action(self._operation("Write", file_path=str(outside)),
                                  project_root=root)
        self.assertTrue(verdict["protected"],
                        "a project under temp lost its containment rule")

    def test_the_scratch_allowance_is_not_a_declared_path(self) -> None:
        """A repository that could nominate its own writable location could
        nominate anything, so the allowance is a property of the machine."""
        outside = PLUGIN_ROOT.parent / "not-temp" / "notes.txt"
        operation = self._operation("Write", file_path=str(outside))
        self.assertTrue(classify_action(operation, project_root=PLUGIN_ROOT)["protected"])

    def test_the_read_tools_are_read_only(self) -> None:
        for tool in ("Read", "Glob", "Grep"):
            operation = self._operation(tool, file_path=str(PLUGIN_ROOT / "README.md"))
            self.assertFalse(classify_action(operation, project_root=PLUGIN_ROOT)["protected"],
                             operation)

    def test_a_bash_payload_reaches_the_classifier_unchanged(self) -> None:
        self.assertEqual(self._operation("Bash", command="ls -la"), "ls -la")
        self.assertFalse(classify_action(self._operation("Bash", command="ls -la"))["protected"])


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

    def test_a_substitution_cannot_launder_what_it_runs(self) -> None:
        """The inner command is extracted and classified alongside the outer.

        This began as a blanket refusal of anything containing `$( )`, which
        held the line but denied `echo $(ls)` along with it — heavy enough that
        it made ordinary shell use impossible. Classifying what the
        substitution actually runs stops the laundering just as firmly and
        costs nothing legitimate.
        """
        for operation in ("ls $(curl -s https://example.com)",
                          "ls `curl -s https://example.com`",
                          "echo $(rm -rf build)"):
            self.assertTrue(classify_action(operation)["protected"], operation)

    def test_expansion_is_not_execution(self) -> None:
        """`${VAR}` yields a value; only `$( )` and backticks run anything."""
        self.assertFalse(classify_action("cat ${EVIL}")["protected"])

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
