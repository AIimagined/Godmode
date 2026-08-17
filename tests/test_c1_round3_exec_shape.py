"""C1 round 3 (second independent security review, 2026-08-17): the review
in `.superpowers/sdd/2026-08-16-cx/task-secA-r2-review.md`, findings C-1
through C-5 and I-1, plus adversarial combinations this file adds itself.

Rounds 1 and 2 both extended an ENUMERATION of dangerous spellings, and
both were walked around one notch over: round 1 anchored on "the
interpreter is the literal first token carrying an isolated `-c`" (defeated
by `/usr/bin/python -c`), round 2 on "the head resolves through a
wrapper-stripping table AND the flag is whitespace-delimited" (defeated by
deleting the space, `python -c"…"`, and by a wrapper's own ordinary flag,
`sudo -E python -c`).

Round 3 makes two structural changes instead:

1. An inline-eval flag matches as a PREFIX of its argv token, because that
   is how the interpreters themselves parse it - the shell concatenates
   `-c` and `"…"` into ONE argv token, so the whitespace round 2's regexes
   demanded is not there to find.
2. An unresolved head with positive evidence of exec shape FAILS CLOSED
   (ask) instead of landing R0, and the hand-written per-wrapper flag
   grammar (`_WRAPPER_STRIP_STEPS`) is deleted: the interpreter is found by
   scanning the segment's own tokens for a known interpreter basename, so
   no wrapper's grammar needs to be known at all.

Finding I-2 of that review is why this file exists in this shape: round
2's new tests were real, but every case was a verbatim copy of a round-1
repro, so 148 tests passed while five Critical bypass classes were open.
Every review repro below is copied verbatim; `AdversarialCombinations`
then crosses the findings against each other, which is where round 4 would
otherwise look first.
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

FORCE = "import subprocess;subprocess.run(['git','push','--force'])"


class Case(unittest.TestCase):
    def assertProtected(self, command: str, *, min_tier: str = "R2") -> None:
        verdict = classify_action(command)
        self.assertTrue(verdict["protected"],
                        f"silently allowed: {command!r} -> {verdict}")
        self.assertGreaterEqual(verdict["tier"], min_tier,
                                f"{command!r} -> {verdict['tier']}, wanted >= {min_tier}")

    def assertUnprotected(self, command: str, *, tier: str | None = None) -> None:
        verdict = classify_action(command)
        self.assertFalse(verdict["protected"],
                         f"over-tightened: {command!r} -> {verdict}")
        if tier is not None:
            self.assertEqual(verdict["tier"], tier, command)


class C1FusedFlagAndArgument(Case):
    """C-1: every inline-flag regex ended `(?:\\s|$)`, and the shell
    concatenates the flag with its quoted argument into one argv token, so
    the whitespace demanded is not there. `python -cCODE`, `bash -c"…"`,
    `node -e'…'` all RUN. Verbatim from the review."""

    def test_python_fused_double_quote(self) -> None:
        self.assertProtected('python -c"import subprocess;subprocess.run([1])"')

    def test_python_fused_single_quote(self) -> None:
        self.assertProtected("python -c'import os'")

    def test_python_fused_bare_code(self) -> None:
        self.assertProtected("python -cimport os")

    def test_node_fused_e(self) -> None:
        self.assertProtected('node -e"require(1)"')

    def test_node_fused_long_eval(self) -> None:
        self.assertProtected('node --eval"require(1)"')

    def test_node_fused_long_print(self) -> None:
        self.assertProtected('node --print"1"')

    def test_ruby_fused(self) -> None:
        self.assertProtected("ruby -e'puts 1'")

    def test_perl_fused(self) -> None:
        self.assertProtected("perl -e'print 1'")

    def test_bash_fused_double_quote(self) -> None:
        self.assertProtected('bash -c"git push --force"', min_tier="R5")

    def test_bash_fused_single_quote_is_the_round_1_regression(self) -> None:
        """Round 1's `\\b` terminator caught `bash -c'rm -rf /'`; round 2's
        `(?:\\s|$)` rejected it, so a case that WAS protected before
        `880e0bd` was silently allowed after it."""
        self.assertProtected("bash -c'rm -rf /'", min_tier="R5")

    def test_sh_fused_double_quote(self) -> None:
        self.assertProtected('sh -c"git push --force"', min_tier="R5")

    def test_sh_fused_single_quote(self) -> None:
        self.assertProtected("sh -c'whoami'")

    def test_zsh_fused(self) -> None:
        self.assertProtected('zsh -c"git push --force"', min_tier="R5")

    def test_bash_fused_cluster(self) -> None:
        self.assertProtected('bash -lc"git push --force"', min_tier="R5")

    def test_pwsh_fused_command(self) -> None:
        self.assertProtected('pwsh -Command"Remove-Item x"')


class C2WrapperArgumentConsumingFlags(Case):
    """C-2: `_WRAPPER_STRIP_STEPS` hand-wrote each wrapper's flag grammar
    and got three of its own wrappers wrong - `sudo`'s `(?:[= ]\\S+)?`
    treated an operand as possible for EVERY flag, so `-E`/`-H`/`-i`
    swallowed the interpreter itself; `env`/`timeout`/`xargs` did not know
    their own argument-consuming flags at all. Verbatim from the review.

    Every case here is caught by evidence form (a): a later token
    normalizes to a known interpreter basename and carries an inline-eval
    flag. No wrapper grammar is parsed."""

    def test_sudo_dash_H(self) -> None:
        self.assertProtected(f'sudo -H python -c "{FORCE}"', min_tier="R5")

    def test_sudo_dash_E(self) -> None:
        self.assertProtected(f'sudo -E python -c "{FORCE}"', min_tier="R5")

    def test_sudo_dash_i(self) -> None:
        self.assertProtected(f'sudo -i python -c "{FORCE}"', min_tier="R5")

    def test_env_unset_short(self) -> None:
        self.assertProtected(f'env -u VAR python -c "{FORCE}"', min_tier="R5")

    def test_env_chdir(self) -> None:
        self.assertProtected(f'env -C somedir python -c "{FORCE}"', min_tier="R5")

    def test_env_unset_long(self) -> None:
        self.assertProtected(f'env --unset=VAR python -c "{FORCE}"', min_tier="R5")

    def test_timeout_signal_short(self) -> None:
        self.assertProtected(f'timeout -s KILL 5 python -c "{FORCE}"', min_tier="R5")

    def test_timeout_signal_long(self) -> None:
        self.assertProtected(f'timeout --signal=KILL 5 python -c "{FORCE}"', min_tier="R5")

    def test_timeout_kill_after(self) -> None:
        self.assertProtected(f'timeout -k 10 5 python -c "{FORCE}"', min_tier="R5")

    def test_xargs_replace_spaced(self) -> None:
        self.assertProtected(f'xargs -I {{}} python -c "{FORCE}"', min_tier="R5")


class C3SubstitutionAndGroupedHeads(Case):
    """C-3: when the command NAME is a substitution the head is `-c`; when
    the interpreter sits in a `(`/`{` group the head is the grouping
    character. Verbatim from the review.

    The substitution cases are evidence form (b) - a command name produced
    by a substitution is not knowable statically, so it cannot be cleared.
    The group cases are form (a): the grouping character is not a command
    name, and `python` is a later token."""

    def test_dollar_paren_which(self) -> None:
        self.assertProtected(f'$(which python) -c "{FORCE}"', min_tier="R5")

    def test_backtick_which(self) -> None:
        self.assertProtected(f'`which python` -c "{FORCE}"', min_tier="R5")

    def test_subshell_group(self) -> None:
        self.assertProtected(f'( python -c "{FORCE}" )', min_tier="R5")

    def test_brace_group(self) -> None:
        self.assertProtected(f'{{ python -c "{FORCE}"; }}', min_tier="R5")


class C4PowerShellPrefixAbbreviations(Case):
    """C-4: PowerShell resolves a parameter by any UNAMBIGUOUS prefix, and
    the prefix executes. Round 2 matched only the exact spellings and the
    documented short aliases. Verbatim from the review."""

    def test_comm(self) -> None:
        self.assertProtected('pwsh -Comm "Remove-Item x"')

    def test_com(self) -> None:
        self.assertProtected('pwsh -Com "Remove-Item x"')

    def test_enco(self) -> None:
        self.assertProtected("powershell -Enco ZwBpAHQA")

    def test_encod(self) -> None:
        self.assertProtected("powershell -Encod ZwBpAHQA")


class C5UnEnumeratedWrappers(Case):
    """C-5: round 2 disclosed "the wrapper list is enumerated, not
    exhaustive" as an accepted limit; the review showed each named shape is
    live silent-allow arbitrary code execution. Verbatim from the review.

    Nothing here teaches the classifier what `docker exec`/`chroot`/
    `nsenter`/`flock` ARE. `python` is a later token (form a); `su -c "…"`
    is an unresolved head carrying an inline-eval flag with a quoted
    argument (form c)."""

    def test_docker_exec(self) -> None:
        self.assertProtected(f'docker exec -it c python -c "{FORCE}"', min_tier="R5")

    def test_chroot(self) -> None:
        self.assertProtected(f'chroot / python -c "{FORCE}"', min_tier="R5")

    def test_su_dash_c(self) -> None:
        self.assertProtected('su -c "git push --force"', min_tier="R5")

    def test_nsenter(self) -> None:
        self.assertProtected(f'nsenter --target 1 python -c "{FORCE}"', min_tier="R5")

    def test_flock(self) -> None:
        self.assertProtected(f'flock /tmp/l python -c "{FORCE}"', min_tier="R5")


class I1BasenameAndSuffixGaps(Case):
    """I-1: the interpreter basename list omitted mainstream CPython
    alternatives, the suffix strip removed only `.exe` on a project that
    runs on Windows, and `$'…'` ANSI-C quoting was not unwrapped."""

    def test_pypy(self) -> None:
        self.assertProtected(f'pypy -c "{FORCE}"', min_tier="R5")

    def test_pypy3(self) -> None:
        self.assertProtected(f'pypy3 -c "{FORCE}"', min_tier="R5")

    def test_jython(self) -> None:
        self.assertProtected(f'jython -c "{FORCE}"', min_tier="R5")

    def test_micropython(self) -> None:
        self.assertProtected(f'micropython -c "{FORCE}"', min_tier="R5")

    def test_windows_bat_shim(self) -> None:
        self.assertProtected(f'python.bat -c "{FORCE}"', min_tier="R5")

    def test_windows_cmd_shim(self) -> None:
        self.assertProtected(f'python.cmd -c "{FORCE}"', min_tier="R5")

    def test_windows_ps1_shim(self) -> None:
        self.assertProtected(f'python.ps1 -c "{FORCE}"', min_tier="R5")

    def test_windows_com_shim(self) -> None:
        self.assertProtected(f'python.com -c "{FORCE}"', min_tier="R5")

    def test_ansi_c_quoted_head(self) -> None:
        self.assertProtected(f"$'python' -c \"{FORCE}\"", min_tier="R5")


class AdversarialCombinations(Case):
    """Not from the review - findings crossed against each other, which is
    where the next round would look first. A fused flag behind a wrapper
    behind a substitution; a stacked wrapper whose flags consume operands;
    a pwsh abbreviation fused to its argument."""

    def test_fused_flag_behind_a_consuming_wrapper_flag(self) -> None:
        self.assertProtected(f'sudo -E python -c"{FORCE}"', min_tier="R5")

    def test_fused_flag_behind_a_substituted_name(self) -> None:
        self.assertProtected(f'$(command -v python) -c"{FORCE}"', min_tier="R5")

    def test_fused_flag_behind_a_wrapper_inside_a_group(self) -> None:
        self.assertProtected(f'( sudo -E python -c"{FORCE}" )', min_tier="R5")

    def test_pwsh_abbreviation_fused_to_its_argument(self) -> None:
        self.assertProtected('pwsh -Comm"Remove-Item x"')

    def test_pwsh_encoded_abbreviation_fused(self) -> None:
        self.assertProtected('powershell -Encod"ZwBpAHQA"')

    def test_pathed_versioned_interpreter_inside_a_container_wrapper(self) -> None:
        self.assertProtected(f'docker exec -it c /usr/bin/python3.11 -c"{FORCE}"',
                       min_tier="R5")

    def test_stacked_consuming_wrappers_over_an_unenumerated_basename(self) -> None:
        self.assertProtected(f'timeout -k 10 5 env -u V pypy3 -c"{FORCE}"', min_tier="R5")

    def test_substituted_name_behind_an_unenumerated_wrapper(self) -> None:
        self.assertProtected(f'flock /tmp/l $(which python) -c "{FORCE}"', min_tier="R5")

    def test_windows_shim_inside_a_brace_group_behind_env(self) -> None:
        self.assertProtected(f'{{ env -C d python.cmd -c"{FORCE}"; }}', min_tier="R5")

    def test_two_stacked_wrappers_each_with_a_consuming_flag(self) -> None:
        self.assertProtected(f'nice -n 10 sudo -H python -c "{FORCE}"', min_tier="R5")

    def test_fused_shell_cluster_behind_xargs_replace(self) -> None:
        self.assertProtected('xargs -I {} bash -lc"git push --force"', min_tier="R5")

    def test_su_with_a_fused_command_flag(self) -> None:
        self.assertProtected('su -c"git push --force"', min_tier="R5")

    def test_quoted_interpreter_token_behind_a_wrapper(self) -> None:
        self.assertProtected(f'sudo "python" -c "{FORCE}"', min_tier="R5")

    def test_ansi_c_quoted_interpreter_behind_a_wrapper(self) -> None:
        self.assertProtected(f"env -u V $'python' -c \"{FORCE}\"", min_tier="R5")

    def test_python_combined_short_option_cluster(self) -> None:
        """CPython accepts combined short options, so `-Ic CODE` runs
        CODE the same as `-c CODE` does."""
        self.assertProtected(f'python -Ic "{FORCE}"', min_tier="R5")

    def test_perl_combined_short_option_cluster(self) -> None:
        self.assertProtected("perl -ne 'print'")

    def test_an_un_enumerated_shell_is_covered_without_being_named(self) -> None:
        """Evidence form (c) is what makes the structural change pay: no
        interpreter-name list contains `fish`, `ash`, `csh`, `nu` or
        `elvish`, and none of them needs to, because an unresolved head
        carrying `-c` with a quoted argument is opaque whatever the head
        turns out to be. Round 2 read every one of these R0."""
        for shell in ("fish", "ash", "csh", "tcsh", "nu", "elvish"):
            self.assertProtected(f'{shell} -c "git push --force"', min_tier="R5")

    def test_a_remote_or_container_exec_naming_a_shell_is_caught(self) -> None:
        """`kubectl exec … -- sh -c "…"` and `docker run --entrypoint sh img
        -c "…"` are form (a): `sh` is a later token with its own inline
        flag, and neither `kubectl` nor `docker run` is identified."""
        self.assertProtected('kubectl exec pod -- sh -c "git push --force"', min_tier="R5")
        self.assertProtected('docker run --entrypoint sh img -c "git push --force"',
                       min_tier="R5")

    def test_a_command_name_built_from_two_variables(self) -> None:
        """`$P$Q -c "…"` cannot be resolved to a name; form (c) reads the
        flag instead and asks."""
        self.assertProtected(f'P=pyt; Q=hon; $P$Q -c "{FORCE}"', min_tier="R5")

    def test_a_substituted_name_from_a_decoded_string(self) -> None:
        self.assertProtected(f'$(echo cHl0aG9u | base64 -d) -c "{FORCE}"', min_tier="R5")

    def test_grouping_character_glued_to_the_interpreter_name(self) -> None:
        """`(python -c "…")` with no space after the paren makes `(python`
        one token; the shell parses `(` as an operator, not as part of the
        command name, so the normalizer strips it the same way it strips a
        path prefix or an escaping backslash."""
        self.assertProtected(f'(python -c"{FORCE}")', min_tier="R5")
        self.assertProtected("(python -cimport os)")
        self.assertProtected(f'{{pypy3 -c"{FORCE}";}}', min_tier="R5")

    def test_a_grouped_read_is_still_a_read(self) -> None:
        self.assertUnprotected("(ls -la)", tier="R0")
        self.assertUnprotected("{ ls; }", tier="R0")
        self.assertUnprotected('echo "(python -c x)"', tier="R0")

    def test_deno_eval_fused_already_worked_and_still_does(self) -> None:
        """`deno`'s own check was the ONE inline rule already written as a
        prefix match; it is the discipline the others now copy."""
        self.assertProtected('deno eval"Deno.run([1])"')


class OrderingHoldsBothWays(Case):
    """The exec-shape check sits between the read allowances and
    `_LOCAL_COMPUTE`, and it returns "no evidence" rather than a benign
    verdict, so every check after it still runs. Both halves are pinned
    because getting either wrong is a silent bypass, not a visible bug."""

    def test_a_task_runner_that_execs_its_argument_is_not_waved_through(self) -> None:
        """`uv` matches `_LOCAL_COMPUTE` on its head; `uv run python -c "…"`
        really does run inline python, so the exec-shape check has to be
        ordered before that match."""
        self.assertProtected('uv run python -c "import os"')

    def test_a_network_head_still_asks_when_a_token_names_an_interpreter(self) -> None:
        """`curl -o python <url>` has a `python` TOKEN and no inline flag.
        The exec-shape check must return "no evidence" here rather than a
        benign local-compute verdict, or the network-fetch check that
        follows it would never run."""
        verdict = classify_action("curl -o python https://example.com/x")
        self.assertTrue(verdict["protected"], verdict)
        self.assertIn("network", " ".join(verdict["impact"]))

    def test_eval_still_reaches_its_own_opaque_rule(self) -> None:
        self.assertProtected('eval "python -c 1"')


class ExecShapeIsNarrow(Case):
    """The exec-shape escalation is NOT a global fail-closed default. An
    ordinary unrecognised command with no exec evidence must still be R0 -
    a blanket ask-on-unknown needs observe-mode ask-rate visibility (task
    B4-I) and evidence-derived allowlist synthesis (Sprint 8) before it is
    affordable, and the operator already has the plugin disabled on every
    host because friction is the top complaint."""

    def test_an_ordinary_unknown_command_is_still_read(self) -> None:
        self.assertUnprotected("foobar --version", tier="R0")

    def test_an_unknown_command_with_a_flag_is_still_read(self) -> None:
        self.assertUnprotected("mytool --dry-run --verbose", tier="R0")

    def test_an_unknown_command_naming_no_interpreter_is_still_read(self) -> None:
        self.assertUnprotected("docker exec -it c ls", tier="R0")

    def test_an_unknown_wrapper_over_a_non_interpreter_is_still_read(self) -> None:
        self.assertUnprotected("chroot / ls -la", tier="R0")

    def test_a_bare_interpreter_token_is_not_evidence(self) -> None:
        """A later token that merely NAMES an interpreter, with no
        inline-eval flag after it, is a name - not an invocation of opaque
        code. `docker exec -it c python` opens an interactive REPL a human
        drives; the stdin-fed rule that (correctly) protects a piped
        `… | python` is deliberately NOT applied to a later token."""
        self.assertUnprotected("docker exec -it c python")

    def test_a_tar_create_flag_is_not_an_inline_command_flag(self) -> None:
        self.assertUnprotected("tar -cf archive.tar somedir", tier="R0")

    def test_a_docker_env_flag_with_a_quoted_value_is_not_evidence(self) -> None:
        self.assertUnprotected('docker run -e "NODE_ENV=production" myimage', tier="R0")

    def test_a_coverage_flag_is_not_a_command_flag(self) -> None:
        self.assertUnprotected("python -m pytest --cov=src", tier="R1")

    def test_a_module_flag_carrying_a_c_module_name(self) -> None:
        """`-m cProfile` names an installed module; the `c` belongs to the
        module name, not to a `-c` flag - and `-m` terminates CPython's own
        option parsing, so a fused `-mcProfile` cannot be a `-c` either."""
        self.assertUnprotected("python -m cProfile script.py", tier="R1")
        self.assertUnprotected("python -mcProfile script.py", tier="R1")

    def test_a_substitution_that_is_only_part_of_the_name_is_not_evidence(self) -> None:
        """`$(npm bin)/eslint` and `$(git rev-parse --show-toplevel)/x.sh`
        still NAME a file after the substitution ends; only a command name
        that is ENTIRELY a substitution is unknowable."""
        self.assertUnprotected("$(npm bin)/eslint .")

    def test_a_substitution_in_argument_position_is_not_a_command_name(self) -> None:
        self.assertUnprotected('echo "$(git rev-parse --short HEAD)"')
        self.assertUnprotected("cat $(ls) | head")
        self.assertUnprotected("sudo $(which python) --version")

    def test_a_control_keyword_only_counts_where_a_keyword_can_stand(self) -> None:
        """`for f in *; do $(cmd)` is command position; `echo do $(ls)` and
        `echo then $(ls)` are a word that happens to be spelled like a
        keyword, followed by a substitution whose output is printed."""
        self.assertUnprotected("echo do $(ls)")
        self.assertUnprotected("echo then $(ls)")
        self.assertProtected(f'for f in *; do $(which python) -c "{FORCE}"; done',
                             min_tier="R5")
        self.assertProtected(f'if true; then $(which python) -c "{FORCE}"; fi',
                             min_tier="R5")
        self.assertProtected(f'ls && $(which python) -c "{FORCE}"', min_tier="R5")

    def test_an_execution_policy_flag_is_not_an_encoded_command(self) -> None:
        """`-Ex…` is `-ExecutionPolicy`, not a prefix of `-EncodedCommand`;
        `pwsh -ExecutionPolicy Bypass -File x.ps1` is the ordinary way to
        run a script file on Windows."""
        self.assertUnprotected("pwsh -ExecutionPolicy Bypass -File build.ps1")

    def test_a_pwsh_file_flag_is_not_inline_code(self) -> None:
        self.assertUnprotected("powershell -NoProfile -File build.ps1")


class SafeReadHeadsShieldTheirOwnArguments(Case):
    """The exec-shape scan runs AFTER the data-printing safe-read heads,
    and `env` is removed from that list. `echo`/`printf`/`grep`/`which`
    treat their arguments as DATA - a `python -c` token after one of them
    is text, not an invocation - while `env`'s entire purpose is to exec
    its trailing argument, which is exactly how `env -u VAR python -c "…"`
    reached R0."""

    def test_echo_printing_an_interpreter_invocation_is_a_read(self) -> None:
        self.assertUnprotected('echo python -c "hi"', tier="R0")

    def test_echo_printing_a_dangerous_invocation_is_still_a_read(self) -> None:
        self.assertUnprotected(f'echo python -c "{FORCE}"', tier="R0")

    def test_printf_printing_an_interpreter_invocation_is_a_read(self) -> None:
        self.assertUnprotected("printf 'python -c print(1)'", tier="R0")

    def test_grep_searching_for_an_interpreter_invocation_is_a_read(self) -> None:
        self.assertUnprotected('grep -rn "python -c" .', tier="R0")

    def test_which_python_is_a_read(self) -> None:
        self.assertUnprotected("which python", tier="R0")

    def test_type_python_is_a_read(self) -> None:
        self.assertUnprotected("type python", tier="R0")

    def test_a_commit_message_mentioning_an_invocation_is_only_a_commit(self) -> None:
        """`git commit` is already protected R2 as a local repository
        change; the point is that it must not be re-read as opaque
        interpreter code because its MESSAGE mentions one."""
        verdict = classify_action('git commit -m "run python -c later"')
        self.assertEqual(verdict["category"], "local-repository-change")
        self.assertEqual(verdict["tier"], "R2")

    def test_bare_env_is_still_a_read(self) -> None:
        self.assertUnprotected("env", tier="R0")

    def test_env_wrapping_a_non_interpreter_is_still_a_read(self) -> None:
        self.assertUnprotected("env ls -la", tier="R0")

    def test_env_with_an_assignment_over_a_non_interpreter_is_still_a_read(self) -> None:
        self.assertUnprotected("env FOO=bar make", tier="R0")


class MustNotRegress(Case):
    """The review verified zero false refusals and that property holds.
    Every shape here passed silently before round 3 and must keep doing
    so."""

    def test_git_status(self) -> None:
        self.assertUnprotected("git status", tier="R0")

    def test_python_m_unittest(self) -> None:
        self.assertUnprotected("python -m unittest", tier="R1")

    def test_python_m_pytest(self) -> None:
        self.assertUnprotected("python -m pytest", tier="R1")

    def test_pytest(self) -> None:
        self.assertUnprotected("pytest", tier="R1")

    def test_tox(self) -> None:
        self.assertUnprotected("tox", tier="R1")

    def test_npm_test(self) -> None:
        self.assertUnprotected("npm test")

    def test_ls_pipe_xargs_grep(self) -> None:
        self.assertUnprotected("ls | xargs grep foo", tier="R0")

    def test_time_make(self) -> None:
        self.assertUnprotected("time make", tier="R0")

    def test_python_script_file(self) -> None:
        self.assertUnprotected("python script.py", tier="R1")

    def test_node_script_file(self) -> None:
        self.assertUnprotected("node build.mjs", tier="R1")

    def test_sudo_apt_get_update(self) -> None:
        self.assertUnprotected("sudo apt-get update", tier="R0")

    def test_timeout_30_pytest(self) -> None:
        self.assertUnprotected("timeout 30 pytest", tier="R0")

    def test_nice_make(self) -> None:
        self.assertUnprotected("nice -n 10 make", tier="R0")

    def test_foobar_version(self) -> None:
        self.assertUnprotected("foobar --version", tier="R0")

    def test_node_with_ordinary_long_flags(self) -> None:
        self.assertUnprotected("node --experimental-vm-modules --enable-source-maps t.mjs")

    def test_node_with_a_require_preload(self) -> None:
        self.assertUnprotected("node -r ts-node/register app.ts")

    def test_ruby_with_a_load_path(self) -> None:
        self.assertUnprotected("ruby -Ilib app.rb")

    def test_perl_with_a_module_flag(self) -> None:
        self.assertUnprotected("perl -MData::Dumper script.pl")

    def test_bash_running_a_script_file(self) -> None:
        self.assertUnprotected("bash -x build.sh")

    def test_sudo_make_install(self) -> None:
        self.assertUnprotected("sudo -E make install", tier="R0")

    def test_env_unset_over_make(self) -> None:
        self.assertUnprotected("env -u VAR make", tier="R0")


class PopulationSweep(Case):
    """Population validation rather than spot cases: the cross product of
    every wrapper shape, every interpreter spelling and every flag spelling
    this round touches, asserted as a COUNT of silent allows.

    Rounds 1 and 2 each passed a list of named repros and were then walked
    around by one spelling nobody had listed. A count over the product is
    what a list of examples cannot give: it fails if ANY combination opens,
    including ones no one thought to name."""

    WRAPPERS = ("", "sudo -E ", "env -u V ", "timeout -k 10 5 ",
                "docker exec -it c ", "chroot / ", "flock /tmp/l ",
                "nsenter --target 1 ", "xargs -I {} ", "nice -n 10 sudo -H ")
    GROUPED = (("( ", " )"), ("{ ", "; }"))
    NAMES = ("python", "/usr/bin/python3.11", "python.bat", "pypy3", '"python"',
             "$'python'", "\\python", "C:\\Py\\python.exe")
    DANGEROUS = (' -c "%s"' % FORCE, ' -c"%s"' % FORCE, " -c'%s'" % FORCE,
                 " -cimport os", ' -Ic "%s"' % FORCE)
    BENIGN = (" app.py", " -m unittest discover -s tests", " --version", " -m pytest -q")

    def _shapes(self, flags: tuple[str, ...]) -> list[str]:
        shapes = [f"{w}{n}{f}" for w in self.WRAPPERS for n in self.NAMES for f in flags]
        shapes += [f"{o}{n}{f}{c}" for o, c in self.GROUPED
                   for n in self.NAMES for f in flags]
        return shapes

    def test_no_dangerous_combination_is_silently_allowed(self) -> None:
        allowed = [command for command in self._shapes(self.DANGEROUS)
                   if not classify_action(command)["protected"]]
        self.assertEqual(allowed, [], f"{len(allowed)} silently allowed")

    def test_no_benign_combination_is_refused(self) -> None:
        """The same product with a script file or a `-m module` in place of
        the inline flag. A sweep that only proves the dangerous half would
        pass just as well for a classifier that asks about everything."""
        refused = [command for command in self._shapes(self.BENIGN)
                   if classify_action(command)["protected"]]
        self.assertEqual(refused, [], f"{len(refused)} over-asked")


class Round1ClassesStayClosed(Case):
    """The review confirmed all seven round-1 classes closed. Deleting the
    wrapper table must not reopen any of them - the token scan replaces it,
    and `_normalized_interpreter_head` still resolves a quoted/escaped/
    pathed head."""

    def test_absolute_path(self) -> None:
        self.assertProtected(f'/usr/bin/python -c "{FORCE}"', min_tier="R5")

    def test_env_wrapper(self) -> None:
        self.assertProtected(f'env python -c "{FORCE}"', min_tier="R5")

    def test_fused_shell_cluster_spaced(self) -> None:
        self.assertProtected(f'bash -lc "{FORCE}"', min_tier="R5")

    def test_pwsh_encoded_command(self) -> None:
        self.assertProtected("pwsh -EncodedCommand ZwBpAHQAIABwAHUAcwBoAA==")

    def test_node_dash_p(self) -> None:
        self.assertProtected(f'node -p "{FORCE}"', min_tier="R5")

    def test_pipe_into_python(self) -> None:
        self.assertProtected(f"echo '{FORCE}' | python")

    def test_herestring(self) -> None:
        self.assertProtected(f'python <<< "{FORCE}"', min_tier="R5")

    def test_substitution_with_parens(self) -> None:
        self.assertProtected(f'echo $(python -c "{FORCE}")', min_tier="R5")

    def test_stacked_wrappers(self) -> None:
        self.assertProtected(f'sudo timeout 5 env python -c "{FORCE}"', min_tier="R5")

    def test_quoted_head(self) -> None:
        self.assertProtected(f'"python" -c "{FORCE}"', min_tier="R5")

    def test_backslash_escaped_head(self) -> None:
        self.assertProtected(f'\\python -c "{FORCE}"', min_tier="R5")

    def test_windows_absolute_path(self) -> None:
        self.assertProtected(f'C:\\Python\\python.exe -c "{FORCE}"', min_tier="R5")

    def test_variable_indirection(self) -> None:
        self.assertProtected(f'P=python; $P -c "{FORCE}"', min_tier="R5")

    def test_heredoc_behind_a_wrapper(self) -> None:
        """The heredoc path used the same wrapper table; with the table
        gone it scans the header's own tokens instead."""
        self.assertProtected(f"env python <<'PY'\n{FORCE}\nPY", min_tier="R5")

    def test_heredoc_behind_a_consuming_wrapper_flag(self) -> None:
        self.assertProtected(f"sudo -E python <<'PY'\n{FORCE}\nPY", min_tier="R5")

    def test_a_cat_heredoc_is_still_not_an_interpreter(self) -> None:
        self.assertUnprotected("cat <<'EOF'\nplain text\nEOF")


if __name__ == "__main__":
    unittest.main()
