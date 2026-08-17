"""C1 round 4 (third independent security review, 2026-08-18): the review in
`.superpowers/sdd/2026-08-16-cx/task-secA-r3-review.md`, Criticals 1-6 and
I-1/I-2/I-3, plus adversarial axes this file adds itself.

Round 3 closed every round-2 Critical and deleted the wrapper table for
good, and 136 of its tests passed while six new Criticals were open. Finding
I-4 says why, and it is the reason this file exists in this shape: round 3's
`PopulationSweep` crossed WRAPPERS x NAMES x flag spellings - the three axes
already known - so no case in it carried a quoted flag, a ` --help` suffix,
or an intra-word-quoted name, and the sweep actively pinned the help-flag
path as CORRECT for benign shapes while it was a universal disarm for
dangerous ones.

The three axes added here are exactly the ones round 3's sweep could not
express:

1. ` --help`/` --version`/` --usage` appended to a payload. `_categorize`
   returned an unprotected read the moment that flag appeared ANYWHERE,
   above every check that can find code, so one token turned the whole
   classifier off - for the interpreter classes AND for `git push --force`,
   `git reset --hard` and `rm -rf /`. It predates all three rounds.
2. A QUOTED flag. Every inline-flag rule was a regex over raw text anchored
   `(?:^|\\s)-`; the shell removes the quote before `execve`, so
   `python "-c" "CODE"` runs exactly as `python -c CODE` and was R1.
3. An intra-word quote or backslash in the NAME. `p"y"thon` reaches the
   interpreter and was R0, because the basename comparison kept the quote
   characters.

All three are closed by reading `shlex` tokens instead of raw text, which is
what "matched as a prefix of its argv token" was supposed to mean in round
3 and did not.
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
    _INTERPRETER_FAMILY_PATTERNS,
    _KNOWN_INTERPRETER_BASENAME,
    _interpreter_family,
    classify_action,
)

FORCE = "import subprocess;subprocess.run(['git','push','--force'])"


class Case(unittest.TestCase):
    def assertProtected(self, command: str, *, min_tier: str = "R2") -> None:
        verdict = classify_action(command)
        self.assertTrue(verdict["protected"],
                        f"silently allowed: {command!r} -> {verdict}")
        self.assertGreaterEqual(verdict["tier"], min_tier,
                                f"{command!r} -> {verdict['tier']}, wanted >= {min_tier}")

    def assertUnprotected(self, command: str) -> None:
        verdict = classify_action(command)
        self.assertFalse(verdict["protected"],
                         f"over-tightened: {command!r} -> {verdict}")


class Critical1HelpFlagDisarm(Case):
    """A trailing help flag is not a help request.

    Every case below was `protected=False`, tier R0, category
    `read-only-inspection`, impact "a help or version banner" before this
    round - measured, not assumed. The reviewer executed two of them to
    confirm the payload actually runs: `python` and `bash` both stop option
    parsing at `-c` and hand the trailing `--version` to the program.
    """

    def test_python_payload_with_version_suffix(self) -> None:
        self.assertProtected(f'python -c "{FORCE}" --version', min_tier="R5")

    def test_python_payload_with_help_suffix(self) -> None:
        self.assertProtected(f'python -c "{FORCE}" --help', min_tier="R5")

    def test_python_payload_with_usage_suffix(self) -> None:
        self.assertProtected(f'python -c "{FORCE}" --usage', min_tier="R5")

    def test_wrapped_payload_with_help_suffix(self) -> None:
        self.assertProtected(f'sudo -E python -c "{FORCE}" --help', min_tier="R5")

    def test_form_c_with_help_suffix(self) -> None:
        self.assertProtected('su -c "git push --force" --help', min_tier="R5")

    def test_form_a_with_help_suffix(self) -> None:
        self.assertProtected('docker exec -it c python -c "import os" --help')

    def test_pwsh_with_help_suffix(self) -> None:
        self.assertProtected('pwsh -Command "Remove-Item x" --help')

    def test_shell_with_version_suffix(self) -> None:
        self.assertProtected('bash -c "git push --force" --version', min_tier="R5")

    def test_encoded_command_with_help_suffix(self) -> None:
        """Critical 6's second false sentence: the changelog promised every
        encoded-command shape sits at the R2 floor, and this one was R0."""
        self.assertProtected(
            'powershell -EncodedCommand ZwBpAHQAIABwAHUAcwBoAA== --help')

    def test_blast_radius_beyond_c1_forced_push(self) -> None:
        self.assertProtected('git push --force origin main --help', min_tier="R5")
        self.assertProtected('git push --force --help', min_tier="R5")

    def test_blast_radius_beyond_c1_history_rewrite(self) -> None:
        self.assertProtected('git reset --hard HEAD~5 --help', min_tier="R5")

    def test_blast_radius_beyond_c1_recursive_delete(self) -> None:
        self.assertProtected('rm -rf / --help', min_tier="R5")

    def test_help_suffix_does_not_disarm_the_unknowable_body_heads(self) -> None:
        self.assertProtected('eval "git push --force" --help', min_tier="R5")
        self.assertProtected('Invoke-Expression "git push --force" --help',
                             min_tier="R5")

    def test_help_suffix_does_not_disarm_cmd(self) -> None:
        self.assertProtected('cmd /c "git push --force" --help', min_tier="R5")


class Critical1MustStayABanner(Case):
    """The over-correction this fix must not make. Asking a command to
    explain itself is the one call whose entire purpose is to explain
    itself, and refusing it is the gate at its least credible."""

    def test_ordinary_banners(self) -> None:
        for command in ("git push --help", "python --version", "docker --help",
                        "npm --version", "pytest --help", "git --help",
                        "node --help", "ls --help", "tar --usage",
                        "git status --help", "pwsh --help", "cargo --version",
                        "foobar --version"):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_subcommand_banners_at_any_depth(self) -> None:
        for command in ("docker compose up --help", "kubectl get pods --help",
                        "gh pr create --help", "git remote add --help",
                        "npm run build --help", "aws s3 sync --help"):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_a_script_being_explained_is_still_a_banner(self) -> None:
        """`python scripts/godmode.py release --help` is the regression this
        flag was introduced to fix: refused at R4 for containing the word
        `release`. A path before the help flag must not disqualify it."""
        self.assertUnprotected("python scripts/godmode.py release --help")
        self.assertUnprotected("python manage.py migrate --help")
        self.assertUnprotected("./deploy.sh --help")


class Critical2QuotedFlag(Case):
    """Quoting the flag. Every one was `protected=False` before this round -
    R1 `local-compute-or-state` where the head was an interpreter, R0 where
    it was wrapped. Two were executed by the reviewer."""

    def test_python_quoted_flag(self) -> None:
        self.assertProtected(f'python "-c" "{FORCE}"', min_tier="R5")

    def test_python_single_quoted_flag(self) -> None:
        self.assertProtected("python '-c' 'import os'")

    def test_shells_quoted_flag(self) -> None:
        for command in ('bash "-c" "git push --force"',
                        'sh "-c" "git push --force"',
                        'bash "-lc" "git push --force"',
                        "zsh '-c' 'git push --force'"):
            with self.subTest(command):
                self.assertProtected(command, min_tier="R5")

    def test_node_and_perl_quoted_flag(self) -> None:
        self.assertProtected('node "-e" "require(1)"')
        self.assertProtected('perl "-e" "system(1)"')

    def test_pwsh_quoted_flag(self) -> None:
        self.assertProtected('pwsh "-Command" "Remove-Item x"')

    def test_wrapped_quoted_flag(self) -> None:
        self.assertProtected(f'sudo -E python "-c" "git push --force"',
                             min_tier="R5")

    def test_flag_split_by_quotes(self) -> None:
        self.assertProtected('python "-"c "import os"')
        self.assertProtected('python ""-c "import os"')

    def test_quoted_flag_crossed_with_every_wrapper(self) -> None:
        for wrapper in ("sudo -H", "env -u V", "timeout -k 10 5",
                        "docker exec -it c", "chroot /", "flock /tmp/l",
                        "nsenter --target 1", "xargs -I {}"):
            command = f'{wrapper} python "-c" "{FORCE}"'
            with self.subTest(command):
                self.assertProtected(command, min_tier="R5")

    def test_quoted_flag_inside_grouped_heads(self) -> None:
        self.assertProtected(f'( python "-c" "{FORCE}" )', min_tier="R5")
        self.assertProtected(f'{{ python "-c" "{FORCE}"; }}', min_tier="R5")

    def test_quoted_name_and_quoted_flag_together(self) -> None:
        self.assertProtected(f'sudo "python" "-c" "{FORCE}"', min_tier="R5")
        self.assertProtected('"bash" "-c" "git push --force"', min_tier="R5")


class Critical3IntraWordQuoting(Case):
    """A quote or a backslash INSIDE the name. The shell removes it and runs
    the interpreter; the basename comparison kept it and did not. All R0
    before this round; `p"y"thon -c` was executed by the reviewer."""

    def test_intra_word_double_quote(self) -> None:
        self.assertProtected('p"y"thon -cimport os')

    def test_intra_word_single_quote(self) -> None:
        self.assertProtected("p'y'thon -cimport os")

    def test_intra_word_backslash(self) -> None:
        self.assertProtected("pyth\\on -cimport os")

    def test_intra_word_quote_on_e_flag_interpreters(self) -> None:
        """The review's asymmetry note: form (c) reads `-c` only, so node,
        ruby and perl had no backstop here at all."""
        self.assertProtected('n"o"de -e"require(1)"')
        self.assertProtected('n"o"de -erequire(1)')
        self.assertProtected('r"u"by -e"puts 1"')

    def test_substitution_glued_to_the_front_of_a_name(self) -> None:
        self.assertProtected("$(echo p)ython -cimport os")

    def test_intra_word_quoting_crossed_with_wrappers(self) -> None:
        self.assertProtected('sudo -E p"y"thon -cimport os')
        self.assertProtected('docker exec -it c p"y"thon -c"import os"')
        self.assertProtected('b"a"sh -c"git push --force"', min_tier="R5")

    def test_a_windows_path_is_still_read_as_a_path(self) -> None:
        """The backslash rule must not be bought by breaking the round-1
        closure it sits next to: POSIX escape handling would turn
        `C:\\Python\\python.exe` into `C:Pythonpython.exe`."""
        self.assertProtected(f'C:\\Python\\python.exe -c "{FORCE}"', min_tier="R5")
        self.assertProtected(f'\\python -c "{FORCE}"', min_tier="R5")


class Critical4PowerShellExecSurfaces(Case):
    """This project runs on Windows. `_POWERSHELL_READS` was shielding real
    exec surfaces the way `_SAFE_SHELL_READS` shielded `env` before round 3
    removed it. All R0/R1 before this round."""

    def test_measure_command_runs_its_block(self) -> None:
        self.assertProtected(f'Measure-Command {{ python -c "{FORCE}" }}',
                             min_tier="R5")

    def test_where_object_runs_its_block(self) -> None:
        self.assertProtected('Where-Object { python -c "import os" }')

    def test_other_block_taking_read_verbs(self) -> None:
        self.assertProtected('Sort-Object { python -c "import os" }')
        self.assertProtected('Group-Object { node -e "require(1)" }')

    def test_invoke_expression_is_powershells_eval(self) -> None:
        self.assertProtected('Invoke-Expression "git push --force"', min_tier="R5")
        self.assertProtected('iex "git push --force"', min_tier="R5")
        self.assertProtected("Get-Content x.ps1 | iex")

    def test_invoke_command_scriptblock(self) -> None:
        self.assertProtected("Invoke-Command -ScriptBlock { rm -rf / }")

    def test_start_process_hands_argv_to_an_interpreter(self) -> None:
        self.assertProtected('Start-Process python -ArgumentList "-c","import os"')
        self.assertProtected(
            'Start-Process pwsh -ArgumentList "-Command","Remove-Item x"')

    def test_a_parameter_longer_than_the_enumerated_name(self) -> None:
        """`-CommandWithArgs` is a shipped PowerShell 7.4 parameter that runs
        a command. Round 3's `startswith` test only ran one way, so `-Comm`
        matched and the full spelling did not."""
        self.assertProtected('pwsh -CommandWithArgs "Remove-Item x"')

    def test_powershell_reads_without_a_block_are_untouched(self) -> None:
        for command in ("Get-ChildItem", "Measure-Command { Get-ChildItem }",
                        'Where-Object { $_.Name -eq "x" }',
                        "Sort-Object -Property Name",
                        "Get-Content log.txt | Select-Object -First 20"):
            with self.subTest(command):
                self.assertUnprotected(command)


class Critical5UndisclosedShapes(Case):
    """Shapes round 3 did not disclose, plus `cmd /c` - the ordinary Windows
    spelling, R0 through all three previous rounds."""

    def test_long_option_with_an_equals_sign(self) -> None:
        self.assertProtected('su --command="git push --force"', min_tier="R5")
        self.assertProtected('runuser --command="rm -rf /"')

    def test_builtin_moves_eval_off_the_head(self) -> None:
        self.assertProtected('builtin eval "python -c 1"')
        self.assertProtected('command eval "git push --force"', min_tier="R5")

    def test_trap_registers_deferred_code(self) -> None:
        self.assertProtected("trap 'python -c \"import os\"' EXIT")
        self.assertProtected("trap 'git push --force' EXIT", min_tier="R5")

    def test_windows_shell_slash_c(self) -> None:
        for command in ('cmd /c "git push --force"',
                        'cmd.exe /c "git push --force"',
                        'cmd /k "git push --force"',
                        'cmd /C "rm -rf /"',
                        'C:\\Windows\\System32\\cmd.exe /c "git push --force"'):
            with self.subTest(command):
                self.assertProtected(command)

    def test_bare_cmd_is_not_a_payload(self) -> None:
        """`cmd` joins the interpreter table for its `/c` form only. A bare
        console, and a `cmd` used as a placeholder head in a pipeline, keep
        the verdict they had."""
        self.assertUnprotected("cmd")
        self.assertUnprotected("cmd 2>&1 | grep x")


class Important1NoNewFalseRefusals(Case):
    """The twelve everyday commands round 3's prefix widening newly blocked,
    all at R2 `interpreter-opaque-inline`. An interpreter stops reading its
    own options at its first operand, so none of these is inline code."""

    def test_the_twelve_the_review_measured(self) -> None:
        for command in ("python app.py -config conf.yml", "python app.py -cfg x",
                        "python train.py -ckpt m.pt", "node server.js -port 3000",
                        "node cli.js -env prod", "node app.js -verbose",
                        "node build.js -production", "node tool.js -pretty",
                        "ruby app.rb -env prod", "ruby -Eutf-8 app.rb",
                        "ruby app.rb -Eutf-8", "perl script.pl -verbose"):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_ruby_dash_capital_e_is_an_encoding_not_an_eval(self) -> None:
        """Round 3 disclosed `ruby -Eutf-8` as an accepted over-ask. It was a
        wrong rule, not a necessary cost: `-E` is ruby's external-encoding
        flag. perl really does define both, and keeps both."""
        self.assertUnprotected("ruby -Eutf-8")
        self.assertProtected("ruby -e 'puts 1'")
        self.assertProtected("perl -E 'say 1'")
        self.assertProtected("perl -e 'print 1'")

    def test_the_brief_s_own_false_refusal_list(self) -> None:
        for command in ('tar -c "a.tar"', 'docker -c "ctx" ps',
                        "$(which python3) --version", "env > out.txt",
                        'python app.py --note " -c thing"'):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_flag_shaped_strings_after_a_script_are_the_scripts(self) -> None:
        for command in ("python -u train.py -ckpt m.pt",
                        "python -B app.py -config c.yml",
                        "node --inspect server.js -port 3000",
                        "ruby -w app.rb -Eutf-8"):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_an_option_argument_does_not_end_the_scan(self) -> None:
        """The other half of the operand rule: a flag that takes a separate
        argument is always immediately in front of it, so the argument is not
        an operand and the scan keeps going."""
        self.assertProtected(f'python -X utf8 -c "{FORCE}"', min_tier="R5")
        self.assertProtected(f'python -W ignore -c "{FORCE}"', min_tier="R5")
        self.assertProtected(f'python -X faulthandler -c "{FORCE}"', min_tier="R5")


class Important2ExecShapeRunsOnInterpreterHeads(Case):
    """The known-interpreter head used to return before the exec-shape scan,
    so form (a) never ran when the head was itself an interpreter whose own
    rule did not fire. All R1 before this round."""

    def test_a_runtime_launching_another_interpreter(self) -> None:
        self.assertProtected(f'bun x python -c "{FORCE}"', min_tier="R5")
        self.assertProtected(f'deno task python -c "{FORCE}"', min_tier="R5")
        self.assertProtected(f'node -r ./setup.js python -c "{FORCE}"',
                             min_tier="R5")


class Important3OneInterpreterEnumeration(Case):
    """Round 3 kept `_KNOWN_INTERPRETER_BASENAME` and four parallel
    `_*_LIKE` patterns describing the same fact, and had to add three names
    to both. A name in one and not the other resolves to a basename that
    falls through every branch of `_interpreter_opacity` - a silent allow no
    test would notice. Both are derived from one table now, and this asserts
    the property rather than the spelling."""

    def test_every_known_basename_has_a_family(self) -> None:
        names = ["python", "python3", "python3.11", "pypy", "pypy3", "jython",
                 "micropython", "py", "node", "bun", "deno", "ruby", "perl",
                 "pwsh", "powershell", "bash", "sh", "zsh", "ksh", "dash", "cmd"]
        for name in names:
            with self.subTest(name):
                self.assertTrue(_KNOWN_INTERPRETER_BASENAME.match(name), name)
                self.assertIsNotNone(_interpreter_family(name), name)

    def test_the_two_are_built_from_the_same_table(self) -> None:
        for family, alternatives in _INTERPRETER_FAMILY_PATTERNS:
            with self.subTest(family):
                self.assertIn(alternatives, _KNOWN_INTERPRETER_BASENAME.pattern)

    def test_an_unknown_name_has_no_family(self) -> None:
        for name in ("rscript", "php", "lua", "osascript", "foobar"):
            with self.subTest(name):
                self.assertIsNone(_interpreter_family(name))


class TokenizationFailsClosed(Case):
    """`_argv_tokens` returns `None` for an unbalanced quote, which is
    evidence the parse FAILED, not evidence of nothing. An unreadable line
    must not be a cheaper bypass than the ones this round closes."""

    def test_an_unclosed_quote_on_an_exec_shape_asks(self) -> None:
        self.assertProtected('python -c "unclosed payload')
        self.assertProtected('sudo python -c "unclosed')

    def test_an_escaped_quote_inside_an_argument_does_not_fail_closed(self) -> None:
        """The escaped fallback pass exists for exactly this: an ordinary
        command must not ask because it contains `\\"`."""
        self.assertUnprotected('node build.mjs --msg "say \\"hi\\""')


class StillClosedFromEarlierRounds(Case):
    """Round 3's own closures, re-asserted against the tokenizer that
    replaced the raw-text readers underneath them."""

    def test_data_printing_heads_still_shield_their_arguments(self) -> None:
        for command in ('echo python -c "hi"', f'echo python -c "{FORCE}"',
                        "echo 'use python -c to run inline'",
                        'grep -rn "python -c" .',
                        "printf 'python -c print(1)'", "which python",
                        "type python"):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_a_commit_message_naming_an_invocation_is_only_a_commit(self) -> None:
        verdict = classify_action('git commit -m "run python -c later"')
        self.assertEqual(verdict["category"], "local-repository-change")
        self.assertEqual(verdict["tier"], "R2")

    def test_the_narrowness_pins(self) -> None:
        for command in ("foobar --version", "env", "env ls -la", "chroot / ls",
                        "tar -cf a.tar dir", 'docker run -e "NODE_ENV=production" img',
                        "kubectl logs pod -c app", "docker exec -it c ls",
                        "python -m unittest", "python -m pytest",
                        "python -m cProfile script.py", "python -mcProfile script.py",
                        "python -m pytest --cov=src", "node -r ts-node/register app.ts",
                        "node --experimental-vm-modules --enable-source-maps t.mjs",
                        "ruby -Ilib app.rb", "perl -MData::Dumper script.pl",
                        "bash -x build.sh", "deno run --allow-all x.ts",
                        "pwsh -ExecutionPolicy Bypass -File build.ps1",
                        "powershell -NoProfile -File build.ps1",
                        "$(npm bin)/eslint .",
                        'echo "$(git rev-parse --short HEAD)"',
                        "(ls -la)", "{ ls; }", "time make", "ls | xargs grep foo"):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_the_exec_shape_scan_still_returns_none_rather_than_a_verdict(self) -> None:
        curl = classify_action("curl -o python https://example.com/x")
        self.assertTrue(curl["protected"])
        self.assertEqual(curl["category"], "unknown-command")
        self.assertProtected('eval "python -c 1"')

    def test_round_1_and_round_2_classes(self) -> None:
        for command in (f'python -c "{FORCE}"', f'/usr/bin/python -c "{FORCE}"',
                        f'env python -c "{FORCE}"', f'bash -lc "{FORCE}"',
                        "pwsh -EncodedCommand ZwBpAHQAIABwAHUAcwBoAA==",
                        f'node -p "{FORCE}"', f'python -c"{FORCE}"',
                        "bash -c'rm -rf /'", f'sudo -E python -c "{FORCE}"',
                        f'docker exec -it c python -c "{FORCE}"',
                        f'$(which python) -c "{FORCE}"',
                        'su -c "git push --force"', f'pypy -c "{FORCE}"',
                        f'python.bat -c "{FORCE}"', f'chroot / python -c "{FORCE}"',
                        f'nsenter --target 1 python -c "{FORCE}"',
                        f'flock /tmp/l python -c "{FORCE}"',
                        '( python -c "import os" )', '{ python -c "import os"; }',
                        'pwsh -Comm "Remove-Item x"', "powershell -Enco ZwBpAHQA",
                        'powershell -Encod"ZwBpAHQA"',
                        'deno eval"Deno.run([1])"',
                        'fish -c "git push --force"',
                        'kubectl exec pod -- sh -c "git push --force"',
                        f"$'python' -c \"{FORCE}\"",
                        f'"python" -c "{FORCE}"',
                        f'echo \'{FORCE}\' | python'):
            with self.subTest(command):
                self.assertProtected(command)


class DisclosedOpen(Case):
    """The shapes this round did NOT close, asserted rather than claimed.

    This class exists so the task report's "what I could not close" section
    is a measurement. If one of these starts being caught, this test fails
    and the report is updated - which is the opposite of the usual direction
    and is the point: an undisclosed hole and a stale disclosure are the same
    defect, and the round-3 review found both.
    """

    def test_interpreters_whose_inline_flag_is_not_dash_c(self) -> None:
        for command in ('Rscript -e "system(\'git push --force\')"',
                        'R -e "system(1)"', 'php -r "system(\'x\');"',
                        'lua -e "os.execute(1)"',
                        'osascript -e "do shell script 1"'):
            with self.subTest(command):
                self.assertUnprotected(command)

    def test_a_single_bare_word_after_dash_c_on_an_unresolved_head(self) -> None:
        self.assertUnprotected("su -cwhoami")
        self.assertUnprotected("runuser -cwhoami")

    def test_a_whole_command_line_inside_one_quoted_argument(self) -> None:
        self.assertUnprotected('mytool "python -c 1"')
        self.assertUnprotected("env -S \"python -c 'print(1)'\"")

    def test_dash_e_on_an_unresolved_head_is_not_evidence(self) -> None:
        self.assertUnprotected('npx tsx -e "require(1)"')
        self.assertUnprotected('mytool -e "code"')

    def test_program_text_of_a_data_printing_read_is_never_parsed(self) -> None:
        self.assertUnprotected('awk \'BEGIN{system("git push --force")}\'')
        self.assertUnprotected("sed -n 'e git push --force' f")
        self.assertUnprotected('sort --compress-program="python -c 1" f')

    def test_sourcing_a_script_file(self) -> None:
        """Left open deliberately: `source venv/bin/activate` is one of the
        most common commands an agent issues, and asking about it would cost
        more friction than the hole is worth."""
        self.assertUnprotected("source ./payload.sh")
        self.assertUnprotected(". ./payload.sh")

    def test_commands_this_module_does_not_classify_at_all(self) -> None:
        """`chmod 777 / --help` is R0 for the same reason `chmod 777 /` is
        R0 - `chmod` is not a classified mutation here. Naming it so the
        help-flag fix is not credited with a hole it never touched."""
        self.assertUnprotected("chmod 777 /")
        self.assertUnprotected("chmod 777 / --help")


class PopulationSweepNewAxes(Case):
    """A count over a cross product, not a list of examples - and the three
    axes are the ones round 3's sweep could not express (finding I-4).

    Each dangerous combination is a real interpreter invocation that runs the
    payload; each benign one is an ordinary command. Both counts are
    re-asserted on every run rather than quoted from a report.
    """

    WRAPPERS = ("", "sudo -E ", "env -u V ", "timeout -k 10 5 ",
                "docker exec -it c ", "chroot / ", "flock /tmp/l ",
                "nsenter --target 1 ")
    NAMES = ("python", '"python"', "p\"y\"thon", "p'y'thon", "/usr/bin/python3.11",
             "python.bat", "pypy3", "$'python'", "C:\\Py\\python.exe")
    FLAGS = ('-c "{p}"', '"-c" "{p}"', "'-c' '{p}'", '-c"{p}"', "-c'{p}'",
             '-Ic "{p}"', '"-Ic" "{p}"')
    SUFFIXES = ("", " --help", " --version", " --usage")

    def test_no_dangerous_combination_is_silently_allowed(self) -> None:
        payload = "import os"
        allowed = []
        checked = 0
        for wrapper in self.WRAPPERS:
            for name in self.NAMES:
                for flag in self.FLAGS:
                    for suffix in self.SUFFIXES:
                        command = f"{wrapper}{name} {flag.format(p=payload)}{suffix}"
                        checked += 1
                        if not classify_action(command)["protected"]:
                            allowed.append(command)
        self.assertGreater(checked, 2000)
        self.assertEqual(allowed, [], f"{len(allowed)} of {checked} silently allowed")

    def test_the_evidence_scan_survives_every_combination(self) -> None:
        """A forced push visible inside the payload must still reach R5 in
        every spelling - the tier is what `_decision_for` turns into a second
        confirmation, so losing it is a real loss even though the call still
        asks."""
        low = []
        for wrapper in self.WRAPPERS:
            for name in self.NAMES:
                for suffix in self.SUFFIXES:
                    command = f'{wrapper}{name} "-c" "{FORCE}"{suffix}'
                    if classify_action(command)["tier"] != "R5":
                        low.append(command)
        self.assertEqual(low, [], f"{len(low)} below R5")

    # Each head crossed with tails in its OWN language. `perl` paired with a
    # `.py` script is excluded on purpose rather than by accident: `perl
    # <anything> -config` is protected at R3 `scripted-source-edit` by a
    # pre-existing rule about perl's in-place editing, identically before and
    # after this round, and folding it in would make this sweep measure that
    # rule instead of the operand rule it exists to measure.
    BENIGN_BY_HEAD = {
        "python": ("app.py -config x", "train.py -ckpt m.pt",
                   "manage.py runserver", "-u app.py -cfg y",
                   "-B train.py -ckpt m.pt", "-m pytest --cov=src"),
        "node": ("server.js -port 3000", "cli.js -env prod", "app.js -verbose",
                 "build.js -production", "tool.js -pretty",
                 "--inspect server.js -port 3000"),
        "ruby": ("app.rb -env prod", "app.rb -Eutf-8", "-Eutf-8 app.rb",
                 "-Ilib app.rb", "-w app.rb -Eutf-8", "script.rb -config c"),
        "perl": ("script.pl -verbose", "-MData::Dumper script.pl"),
        "bash": ("build.sh --clean", "-x build.sh"),
        "deno": ("run --allow-all x.ts", "test --coverage"),
        "pwsh": ("-File build.ps1", "-NoProfile -File x.ps1"),
    }

    def test_no_benign_combination_is_over_asked(self) -> None:
        over = []
        checked = 0
        for head, tails in self.BENIGN_BY_HEAD.items():
            for tail in tails:
                for suffix in ("", " --help", " --version"):
                    command = f"{head} {tail}{suffix}"
                    checked += 1
                    if classify_action(command)["protected"]:
                        over.append(command)
        self.assertGreater(checked, 70)
        self.assertEqual(over, [], f"{len(over)} of {checked} over-asked")

    def test_banners_are_never_over_asked(self) -> None:
        over = []
        for head in ("git", "docker", "npm", "pytest", "node", "python",
                     "kubectl", "cargo", "gh", "terraform"):
            for flag in ("--help", "--version", "--usage"):
                command = f"{head} {flag}"
                if classify_action(command)["protected"]:
                    over.append(command)
        self.assertEqual(over, [], f"{len(over)} banners over-asked")


if __name__ == "__main__":
    unittest.main()
