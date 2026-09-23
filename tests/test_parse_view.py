"""G-5: one parse of a command under its own shell's rules, then one classifier.

Every test here names a reading a shell really performs. The fail-open ones
(`FailOpenUnderPowerShell`, `CmdHasNoSingleQuotes`, `FastPathEscalates`) were
reproduced as `allow` before this change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for extra in (SCRIPTS, HOOKS, PLUGIN_ROOT / "scripts" / "dev", Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_parseview as pv  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action, shell_segments  # noqa: E402
import godmode_gate_fast as fast  # noqa: E402
import corpus_differential  # noqa: E402
from _host_env import scrubbed_env  # noqa: E402

CORPUS = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "gate_corpus.json")
                    .read_text(encoding="utf-8"))
TABLE = json.loads((HOOKS / "gate_table.json").read_text(encoding="utf-8"))

BS = "\\"
PUSH_AFTER_BACKSLASH = 'Get-Content "C:' + BS + "dir" + BS + '"; git push --force origin main'


def decision(operation: str, **kwargs) -> str:
    verdict = classify_action(operation, project_root=PLUGIN_ROOT, **kwargs)
    if not verdict["protected"]:
        return "allow"
    return "refuse" if verdict["tier"] == "R5" else "ask"


class BashIsTheIdentity(unittest.TestCase):
    """The zero-flip guarantee: Bash text is never rewritten, and the view's
    segments are the classifier's own segments."""

    def test_lowering_bash_changes_no_corpus_row(self) -> None:
        for row in CORPUS:
            self.assertEqual(pv.lower(row["operation"], pv.BASH), row["operation"])

    def test_view_segments_are_the_classifier_segments(self) -> None:
        for row in CORPUS:
            view = pv.parse(row["operation"], pv.BASH)
            self.assertEqual([s.text for s in view.segments],
                             shell_segments(row["operation"]), row["operation"][:80])

    def test_view_carries_heads_argv_and_operators(self) -> None:
        view = pv.parse('git status && echo "a b" | wc -l', pv.BASH)
        self.assertEqual(view.heads, ("git", "echo", "wc"))
        self.assertEqual(view.segments[1].argv, ("echo", "a b"))
        self.assertEqual([s.operator for s in view.segments], [None, "&&", "|"])

    def test_an_unclosed_quote_has_no_argv(self) -> None:
        self.assertIsNone(pv.parse('echo "open', pv.BASH).segments[0].argv)

    def test_unknown_dialect_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            pv.parse("ls", "fish")


class FailOpenUnderPowerShell(unittest.TestCase):
    """Read with Bash's rules each of these hid a force-push inside what
    looked like one quoted string, and was allowed."""

    def assert_push_is_seen(self, operation: str) -> None:
        view = pv.parse(operation, pv.POWERSHELL)
        self.assertIn("git", view.heads, view)
        self.assertEqual(decision(operation, tool_name="PowerShell"), "refuse")

    def test_a_backslash_is_literal_so_the_string_closes(self) -> None:
        self.assertEqual(decision(PUSH_AFTER_BACKSLASH), "allow")  # Bash's reading
        self.assert_push_is_seen(PUSH_AFTER_BACKSLASH)
        self.assertEqual(pv.parse(PUSH_AFTER_BACKSLASH, pv.POWERSHELL).segments[0].argv,
                         ("Get-Content", "C:" + BS + "dir" + BS))

    def test_a_backslash_before_a_separator_does_not_escape_it(self) -> None:
        self.assert_push_is_seen("Get-ChildItem ." + BS + "src" + BS + ";git push --force")

    def test_a_here_string_holds_its_quotes(self) -> None:
        self.assert_push_is_seen("cat @'\na'\"\n'@; git push --force; cat \"x\"")

    def test_a_here_string_opens_only_at_a_token_start(self) -> None:
        """Review B1: `x@'` is the word `x@` and an ordinary string; the
        mid-token opener must not swallow the push."""
        for quote in ("'", '"'):
            with self.subTest(quote=quote):
                self.assert_push_is_seen(f"echo x@{quote}\ny{quote}@; git push --force")

    def test_a_here_string_opens_after_an_equals_or_a_comma(self) -> None:
        """Review round 2, F1: the B1 fix must not stop `$x=@'` or `1,@'`
        opening a here-string, whose body quote is literal."""
        for prefix in ("$x=", "1,"):
            with self.subTest(prefix=prefix):
                view = pv.parse(prefix + "@'\nit's fine\n'@; Write-Host $x", pv.POWERSHELL)
                self.assertEqual(view.heads[-1], "Write-Host")
        self.assertEqual(decision("$x=@'\nit's fine\n'@; Write-Host $x",
                                  tool_name="PowerShell"), "allow")

    def test_a_typographic_quote_closes_a_string(self) -> None:
        self.assert_push_is_seen('cat "a“; git push --force; cat ”x"')

    def test_a_subexpression_inside_a_string_stays_live(self) -> None:
        self.assertEqual(decision('git commit -m "x$(git push --force)"',
                                  tool_name="PowerShell"), "refuse")

    def test_an_unclosed_subexpression_still_fails_closed(self) -> None:
        verdict = classify_action('echo "a $(git push', project_root=PLUGIN_ROOT,
                                  tool_name="PowerShell")
        self.assertEqual(verdict["category"], "unparsed-substitution")

    def test_a_quote_inside_a_comment_does_not_swallow_the_next_line(self) -> None:
        view = pv.parse("ls # don't\ngit push --force", pv.POWERSHELL)
        self.assertEqual(view.heads, ("ls", "git"))


class BashComments(unittest.TestCase):
    """Review H1, the Bash half: a word-start `#` is a comment to the end of
    the line, so a quote in it opens nothing."""

    def test_a_quote_in_a_comment_does_not_hide_the_next_line(self) -> None:
        self.assertEqual(shell_segments("ls # don't\ngit push --force"),
                         ["ls # don't", "git push --force"])
        self.assertEqual(decision("ls # don't\ngit push --force"), "refuse")

    def test_an_escaped_space_does_not_start_a_comment(self) -> None:
        # `ls \ #` passes the word ` #` to ls; the `;` still separates.
        command = "ls " + BS + " #; git push --force"
        self.assertEqual(shell_segments(command)[-1], "git push --force")
        self.assertEqual(decision(command), "refuse")

    def test_a_hash_inside_a_word_is_not_a_comment(self) -> None:
        self.assertEqual(shell_segments('echo "x"#y; git push'), ['echo "x"#y', "git push"])
        self.assertEqual(shell_segments("git log --grep=#12; ls"), ["git log --grep=#12", "ls"])


class QuotedHeads(unittest.TestCase):
    """Review H2-parse: the command word is classified as the view resolves
    it, so quoting the name does not hide the command."""

    PUSHES = ("'git' push --force", '"git" push --force', "g" + BS + "it push --force",
              "& 'git' push --force", '&"git" push --force')

    def test_each_quoted_head_is_refused_under_both_shells(self) -> None:
        for operation in self.PUSHES:
            for tool in ("Bash", "PowerShell"):
                with self.subTest(operation=operation, tool=tool):
                    self.assertEqual(decision(operation, tool_name=tool), "refuse")

    def test_a_path_head_is_read_by_its_program_name(self) -> None:
        """Review round 2, F3."""
        for operation in ("'/usr/bin/git' push --force",
                          '& "C:/Program Files/git.exe" push --force',
                          "C:/tools/git.exe push --force"):
            for tool in ("Bash", "PowerShell"):
                with self.subTest(operation=operation, tool=tool):
                    self.assertEqual(decision(operation, tool_name=tool), "refuse")
        self.assertEqual(pv.head_readings("'/usr/bin/git' push"), ["git push"])
        self.assertEqual(decision("'/usr/bin/git' status"), "allow")

    def test_the_resolution_itself(self) -> None:
        self.assertEqual(pv.resolved_head("'git' push"), "git push")
        self.assertEqual(pv.resolved_head("& 'git' push"), "git push")
        self.assertIsNone(pv.resolved_head("git push"))
        self.assertIsNone(pv.resolved_head('"$(which python)" -c x'))
        self.assertIsNone(pv.resolved_head("'open push"))
        self.assertIsNone(pv.resolved_head('"C:/Program Files/git.exe" push'))

    def test_the_digest_is_still_the_submitted_text(self) -> None:
        verdict = classify_action("'git' status", project_root=PLUGIN_ROOT)
        self.assertEqual(verdict["operation_digest"],
                         hashlib.sha256(b"'git' status").hexdigest())
        self.assertFalse(verdict["protected"])


class BacktickIsAnEscapeUnderPowerShell(unittest.TestCase):
    """The false refusals: PowerShell's escape character read as a Bash
    command substitution."""

    def test_an_escaped_newline_in_a_string_is_a_read(self) -> None:
        self.assertEqual(decision('Write-Host "done`n"'), "ask")
        self.assertEqual(decision('Write-Host "done`n"', tool_name="PowerShell"), "allow")

    def test_escaped_quotes_inside_a_string(self) -> None:
        view = pv.parse('git log --format="%h `"x`""', pv.POWERSHELL)
        self.assertEqual(view.segments[0].argv, ("git", "log", '--format=%h "x"'))
        self.assertEqual(decision('git log --format="%h `"x`""', tool_name="PowerShell"), "allow")

    def test_a_backtick_line_continuation_joins_the_line(self) -> None:
        view = pv.parse("git status `\n  --short", pv.POWERSHELL)
        self.assertEqual(view.heads, ("git",))

    def test_doubled_single_quotes_are_one_quote(self) -> None:
        view = pv.parse("echo 'it''s'", pv.POWERSHELL)
        self.assertEqual(view.segments[0].argv, ("echo", "it's"))


class CmdHasNoSingleQuotes(unittest.TestCase):
    def test_a_single_quote_does_not_hide_the_ampersand(self) -> None:
        operation = "echo 'a & git push --force'"
        self.assertEqual(decision(operation), "allow")  # Bash's reading
        self.assertEqual(pv.parse(operation, pv.CMD).heads, ("echo", "git"))
        self.assertEqual(decision(operation, tool_name="cmd"), "refuse")

    def test_a_caret_escapes_the_ampersand(self) -> None:
        self.assertEqual(pv.parse("echo x ^& y", pv.CMD).heads, ("echo",))

    def test_a_dollar_paren_is_literal_text(self) -> None:
        self.assertEqual(pv.parse("echo $(x)", pv.CMD).segments[0].argv, ("echo", "$(x)"))


class OneVerdictAcrossTools(unittest.TestCase):
    def test_the_same_command_reaches_the_same_verdict(self) -> None:
        for operation in ("git commit -m x", "git status", "git push --force origin main",
                          "ls -la | wc -l"):
            bash = classify_action(operation, project_root=PLUGIN_ROOT, tool_name="Bash")
            pwsh = classify_action(operation, project_root=PLUGIN_ROOT, tool_name="PowerShell")
            self.assertEqual(bash, pwsh, operation)

    def test_the_digest_is_of_the_text_as_submitted(self) -> None:
        verdict = classify_action(PUSH_AFTER_BACKSLASH, project_root=PLUGIN_ROOT,
                                  tool_name="PowerShell")
        self.assertEqual(verdict["operation_digest"],
                         hashlib.sha256(PUSH_AFTER_BACKSLASH.encode()).hexdigest())


class DialectForTool(unittest.TestCase):
    def test_declared_shells(self) -> None:
        self.assertEqual(pv.dialect_for_tool("Bash", "win32"), pv.BASH)
        self.assertEqual(pv.dialect_for_tool("PowerShell", "linux"), pv.POWERSHELL)
        self.assertEqual(pv.dialect_for_tool("cmd"), pv.CMD)
        self.assertEqual(pv.dialect_for_tool("build.cmd"), pv.CMD)
        self.assertEqual(pv.dialect_for_tool(None), pv.BASH)
        self.assertEqual(pv.dialect_for_tool("SomethingElse"), pv.BASH)

    def test_grok_and_other_undeclared_shell_tools(self) -> None:
        for tool in ("run_terminal_command", "shell_command", "run_command"):
            self.assertEqual(pv.dialect_for_tool(tool, "linux"), pv.BASH)
            self.assertEqual(pv.dialect_for_tool(tool, "win32"), pv.DIALECT_EITHER)

    def test_either_dialect_keeps_the_stricter_reading(self) -> None:
        self.assertEqual(decision(PUSH_AFTER_BACKSLASH, dialect=pv.DIALECT_EITHER), "refuse")
        self.assertEqual(decision("git status", dialect=pv.DIALECT_EITHER), "allow")

    def test_grok_on_windows_reaches_the_powershell_reading(self) -> None:
        with mock.patch.object(pv.sys, "platform", "win32"):
            self.assertEqual(decision(PUSH_AFTER_BACKSLASH, tool_name="run_terminal_command"),
                             "refuse")


def payload(command: str, tool: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"command": command}}


class FastPathEscalates(unittest.TestCase):
    """The fast gate reads with Bash's rules and imports nothing; a
    PowerShell command it could misread goes to the full hook."""

    def test_the_backslash_case_is_not_fast_allowed(self) -> None:
        command = 'cat "a' + BS + '"; git push --force'
        self.assertEqual(fast.fast_verdict(payload(command, "Bash"), TABLE), "allow")
        self.assertEqual(fast.fast_verdict(payload(command, "PowerShell"), TABLE), "escalate")

    def test_other_divergent_shapes_escalate(self) -> None:
        for command in ("cat @'\na'\"\n'@; git push --force; cat \"x\"",
                        'cat "a“; git push --force; cat ”x"',
                        "cat (git push --force)", "cat @(git push --force)"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command, "PowerShell"), TABLE),
                                 "escalate")

    def test_comments_and_line_breaks_escalate(self) -> None:
        """Review H1: the fast path allowed these while the full hook
        refused, and the fast allow short-circuits the full hook."""
        cases = (("ls # don't\ngit push --force", "PowerShell"),
                 ("ls <# ' #> ; git push --force", "PowerShell"),
                 ("ls # don't\ngit push --force", "Bash"),
                 ("ls # c; rm -rf /", "Bash"),
                 ("git status\ngit log", "Bash"))
        for command, tool in cases:
            with self.subTest(command=command, tool=tool):
                self.assertEqual(fast.fast_verdict(payload(command, tool), TABLE), "escalate")
        with mock.patch.object(fast.sys, "platform", "win32"):
            self.assertEqual(fast.fast_verdict(
                payload("ls <# ' #> ; git push --force", "run_terminal_command"), TABLE),
                "escalate")

    def test_ordinary_powershell_reads_stay_fast(self) -> None:
        for command in ("git status", "ls -la", "cat src" + BS + "a.txt", "git log --oneline"):
            with self.subTest(command=command):
                self.assertEqual(fast.fast_verdict(payload(command, "PowerShell"), TABLE),
                                 "allow")

    def test_undeclared_shell_tools_escalate_only_on_windows(self) -> None:
        command = 'cat "a' + BS + '"; git push --force'
        with mock.patch.object(fast.sys, "platform", "win32"):
            self.assertEqual(fast.fast_verdict(payload(command, "run_terminal_command"), TABLE),
                             "escalate")
        with mock.patch.object(fast.sys, "platform", "linux"):
            self.assertEqual(fast.fast_verdict(payload(command, "run_terminal_command"), TABLE),
                             "allow")

    def test_the_fast_tool_sets_match_the_parse_view(self) -> None:
        for tool in fast._SHELL_TOOLS:
            self.assertIn(tool, pv.SHELL_TOOL_DIALECTS, tool)
            for platform in ("win32", "linux"):
                with mock.patch.object(fast.sys, "platform", platform):
                    may_be_pwsh = pv.POWERSHELL in pv.dialects_to_read(
                        pv.dialect_for_tool(tool, platform))
                    self.assertEqual(fast._may_be_powershell(tool), may_be_pwsh,
                                     (tool, platform))


class TheHookPassesTheToolName(unittest.TestCase):
    """End to end through the real gate script, in a throwaway governed
    project (not a git repository, its own state home): the full hook must
    hand the tool name to the classifier, or the PowerShell reading never
    happens."""

    def test_powershell_push_after_a_backslash_is_denied(self) -> None:
        import os
        import tempfile

        command = 'cat "a' + BS + '"; git push --force origin main'
        with tempfile.TemporaryDirectory(prefix="godmode-parseview-") as raw:
            project, state = Path(raw) / "project", Path(raw) / "state"
            project.mkdir()
            old = os.environ.get("GODMODE_STATE_HOME")
            os.environ["GODMODE_STATE_HOME"] = str(state)
            try:
                from godmode_runtime.godmode_anchor import resolve_anchor
                from godmode_runtime.godmode_chronicle import Chronicle
                Chronicle(resolve_anchor(project)).initialize()
            finally:
                if old is None:
                    os.environ.pop("GODMODE_STATE_HOME", None)
                else:
                    os.environ["GODMODE_STATE_HOME"] = old
            outputs = {}
            for tool in ("Bash", "PowerShell"):
                body = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                                   "tool_input": {"command": command},
                                   "cwd": str(project)})
                done = subprocess.run(
                    [sys.executable, str(HOOKS / "godmode_gate_fast.py")], input=body,
                    capture_output=True, text=True, timeout=120, cwd=str(project),
                    env=scrubbed_env(GODMODE_STATE_HOME=str(state)))
                outputs[tool] = done.stdout
        self.assertNotIn('"deny"', outputs["Bash"], outputs["Bash"])
        self.assertIn('"deny"', outputs["PowerShell"], outputs["PowerShell"])


class HookCommandsParseUnderPowerShell(unittest.TestCase):
    """Grok on Windows runs each shared hook command in PowerShell; one that
    does not parse fails its hook open. A dry parse, nothing executed."""

    def test_every_shared_hook_command_parses(self) -> None:
        pwsh = shutil.which("pwsh")
        if not pwsh:
            self.skipTest("pwsh is not installed here")
        manifest = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
        commands = sorted({hook["command"] for blocks in manifest["hooks"].values()
                           for block in blocks for hook in block["hooks"]})
        self.assertTrue(commands)
        # Grok rewrites `${VAR}` to `$env:VAR` before PowerShell sees it.
        probes = [command.replace("${CLAUDE_PLUGIN_ROOT}", "$env:CLAUDE_PLUGIN_ROOT")
                  for command in commands]
        script = ("foreach ($c in ($env:GODMODE_PARSE_PROBE | ConvertFrom-Json)) { "
                  "$errs = $null; "
                  "[void][System.Management.Automation.Language.Parser]::ParseInput("
                  "$c, [ref]$null, [ref]$errs); "
                  "foreach ($e in $errs) { $c + ' :: ' + $e.Message } }")
        done = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=120,
            env=scrubbed_env(GODMODE_PARSE_PROBE=json.dumps(probes)))
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        self.assertEqual(done.stdout.strip(), "", f"ParserError: {done.stdout}")

    def test_the_dry_parse_does_catch_a_parser_error(self) -> None:
        """The probe must be able to fail: the 0.3.18 shape (a quoted path
        in statement position) is a ParserError."""
        pwsh = shutil.which("pwsh")
        if not pwsh:
            self.skipTest("pwsh is not installed here")
        bad = '"$env:CLAUDE_PLUGIN_ROOT/hooks/run-hook.cmd" godmode_gate_fast.py'
        script = ("$errs = $null; "
                  "[void][System.Management.Automation.Language.Parser]::ParseInput("
                  "$env:GODMODE_PARSE_PROBE, [ref]$null, [ref]$errs); $errs.Count")
        done = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=120,
            env=scrubbed_env(GODMODE_PARSE_PROBE=bad))
        self.assertGreater(int(done.stdout.strip() or 0), 0, done.stdout)


class CorpusDifferential(unittest.TestCase):
    def test_flips_are_explained_only_by_a_by_design_note(self) -> None:
        rows = [{"operation": "a", "class": "by-design", "note": "why"},
                {"operation": "b", "class": "by-design"},
                {"operation": "c", "class": "FP1", "note": "why"},
                {"operation": "d", "class": "by-design"}]
        answers = iter([["allow", "allow", "allow", "ask"], ["ask", "ask", "ask", "ask"]])
        with mock.patch.object(corpus_differential, "materialise",
                               side_effect=lambda sha, into: into), \
                mock.patch.object(corpus_differential, "decisions",
                                  side_effect=lambda parent, rows: next(answers)):
            report = corpus_differential.differential("base", "head", rows)
        self.assertEqual([f["operation"] for f in report["flips"]], ["a", "b", "c"])
        self.assertEqual([f["explained"] for f in report["flips"]], [True, False, False])
        self.assertEqual(report["unexplained"], 2)

    def test_a_commit_against_itself_has_no_flips(self) -> None:
        try:
            head = corpus_differential._git("rev-parse", "HEAD").strip()
        except (subprocess.CalledProcessError, OSError):
            self.skipTest("no git history here")
        rows = [{"operation": "git status", "class": "by-design"},
                {"operation": "git push --force origin main", "class": "by-design"}]
        report = corpus_differential.differential(head, head, rows)
        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["flips"], [])


if __name__ == "__main__":
    unittest.main()
