"""C1 round 2 (independent security review, 2026-08-17): the seven bypass
classes the review's own `.superpowers/sdd/2026-08-16-cx/task-secA-review.md`
lists verbatim, each reproduced here as a test - every command below is
copied from that file, not paraphrased.

Round 1 anchored every check to the interpreter being the literal FIRST
SHELL TOKEN carrying a specific inline flag. The review proved that anchor
defeated by a path prefix, any of eleven wrapper commands, a quoted or
escaped head, a fused shell flag, several real alternate eval flags,
PowerShell's encoded-command flag, a piped/herestring/stdin-fed payload,
and a `$()` substitution containing parentheses. This file pins the fix in
both directions: every one of the seven classes must now be protected, and
the over-tightening controls (script files, `-m <module>`, `npm test`,
`git status`, `pytest`, `tox`) must stay exactly as unprotected as before.
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

FORCE_PUSH_PY = "import subprocess;subprocess.run(['git','push','--force'])"


class Case(unittest.TestCase):
    def protected(self, command: str, *, min_tier: str = "R2") -> None:
        verdict = classify_action(command)
        self.assertTrue(verdict["protected"],
                        f"silently allowed: {command!r} -> {verdict}")
        self.assertGreaterEqual(verdict["tier"], min_tier,
                                f"{command!r} -> {verdict['tier']}, wanted >= {min_tier}")

    def unprotected(self, command: str, *, tier: str | None = None) -> None:
        verdict = classify_action(command)
        self.assertFalse(verdict["protected"],
                         f"over-tightened: {command!r} -> {verdict}")
        if tier is not None:
            self.assertEqual(verdict["tier"], tier, command)


class C1PathAndWrapperPrefix(Case):
    """The review's C-1: any token before the interpreter used to defeat
    detection entirely, reading R0 - worse than round 1's own R1."""

    def test_absolute_path(self) -> None:
        self.protected(f'/usr/bin/python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_env_wrapper(self) -> None:
        self.protected(f'env python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_env_dash_s(self) -> None:
        self.protected(f'env -S python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_command_wrapper(self) -> None:
        self.protected(f'command python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_timeout_wrapper(self) -> None:
        self.protected(f'timeout 5 python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_nohup_wrapper(self) -> None:
        self.protected(f'nohup python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_stdbuf_wrapper(self) -> None:
        self.protected(f'stdbuf -oL python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_time_wrapper(self) -> None:
        self.protected(f'time python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_xargs_wrapper(self) -> None:
        self.protected(f'xargs python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_relative_path(self) -> None:
        self.protected(f'./python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_quoted_head(self) -> None:
        self.protected(f'"python" -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_backslash_escaped_head(self) -> None:
        self.protected(f'\\python -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_windows_absolute_path(self) -> None:
        self.protected(f'C:\\Python\\python.exe -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_variable_indirection(self) -> None:
        self.protected(f'P=python; $P -c "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_stacked_wrappers(self) -> None:
        """Not in the review's own list, but the same class generalised -
        wrappers stack (`sudo timeout 5 env python -c "…"`), and each one
        must strip in turn."""
        self.protected(f'sudo timeout 5 env python -c "{FORCE_PUSH_PY}"', min_tier="R5")


class C2CombinedShellFlags(Case):
    """The review's C-2: `_c\\b` required an isolated `-c` token; a fused
    cluster containing `c` (`-lc`, `-ic`, `-xc`, `-cx`) was missed."""

    def test_bash_lc(self) -> None:
        self.protected('bash -lc "git push --force origin main"', min_tier="R5")

    def test_sh_lc(self) -> None:
        self.protected('sh -lc "git push --force"', min_tier="R5")

    def test_zsh_ic(self) -> None:
        self.protected('zsh -ic "rm -rf /"', min_tier="R5")

    def test_bash_ic(self) -> None:
        self.protected('bash -ic "git push --force"', min_tier="R5")

    def test_sh_xc(self) -> None:
        self.protected('sh -xc "git push --force"', min_tier="R5")

    def test_sh_cx(self) -> None:
        self.protected('sh -cx "git push --force"', min_tier="R5")

    def test_contrast_unfused_still_caught(self) -> None:
        """The forms the review says already worked stay working."""
        self.protected(f'sh -c "{FORCE_PUSH_PY}"', min_tier="R5")
        self.protected(f'bash -o pipefail -c "{FORCE_PUSH_PY}"', min_tier="R5")


class C3PowerShellEncodedCommand(Case):
    """The review's C-3: only `-Command`/`-c` were recognised;
    `-EncodedCommand`/`-enc`/`-e`/`-ec` (the standard base64 obfuscation)
    were not. Never decoded and judged - opaque by definition."""

    def test_encoded_command_pwsh(self) -> None:
        self.protected("pwsh -EncodedCommand ZwBpAHQA")

    def test_encoded_command_powershell(self) -> None:
        self.protected("powershell -EncodedCommand ZwBpAHQAIABwAHUAcwBoAA==")

    def test_enc_abbreviation(self) -> None:
        self.protected("powershell -enc ZwBpAHQA")

    def test_e_abbreviation(self) -> None:
        self.protected("pwsh -e ZwBpAHQA")

    def test_ec_abbreviation(self) -> None:
        self.protected("pwsh -ec ZwBpAHQA")


class C4AlternateEvalFlags(Case):
    """The review's C-4: node's `-p`/`--print`/`-pe` genuinely evaluate an
    expression; deno's inline-code form is the `eval` subcommand. Neither
    was in the round-1 flag list."""

    def test_node_dash_p(self) -> None:
        self.protected(
            "node -p \"require('child_process').execSync('git push --force')\"",
            min_tier="R5")

    def test_node_dash_dash_print(self) -> None:
        self.protected('node --print "1"')

    def test_node_pe(self) -> None:
        self.protected('node -pe "1"')

    def test_deno_eval_subcommand(self) -> None:
        self.protected('deno eval "Deno.run([\'git\',\'push\',\'--force\'])"',
                        min_tier="R5")


class C5PipeToInterpreter(Case):
    """The review's C-5: a payload fed on stdin from an earlier segment
    carries no flag on the interpreter's own segment, so it read as bare
    local compute."""

    def test_echo_pipe_python(self) -> None:
        self.protected(f"echo '{FORCE_PUSH_PY}' | python")

    def test_cat_pipe_python(self) -> None:
        self.protected("cat payload.py | python")

    def test_echo_pipe_python_dash(self) -> None:
        self.protected("echo 'import os' | python -")

    def test_contrast_cat_pipe_sh_no_network_backstop(self) -> None:
        """`curl … | sh` was already protected via the network-fetch head,
        not via interpreter detection - a purely LOCAL pipe into `sh` had
        no such backstop before this fix."""
        self.protected("cat x.sh | sh")


class C6HerestringAndStdinRedirect(Case):
    """The review's C-6: `<<<` is not the `_HEREDOC` heredoc form, and a
    stdin redirect is input, not the heredoc shape either."""

    def test_herestring(self) -> None:
        self.protected(f'python <<< "{FORCE_PUSH_PY}"', min_tier="R5")

    def test_dev_stdin(self) -> None:
        self.protected("python /dev/stdin < payload.py")

    def test_dash_stdin_redirect(self) -> None:
        self.protected("python - < payload.py")


class C7ParenthesisedSubstitution(Case):
    """The review's C-7: `\\$\\((?P<paren>[^()]*)\\)` cannot span a
    parenthesised body, and almost every real interpreter payload
    (`.run(...)`, `print(...)`, `execSync(...)`) is one - the outer
    command read R0 with the inner payload never even reaching a
    classifier call."""

    def test_paren_bearing_force_push(self) -> None:
        self.protected(f'echo $(python -c "{FORCE_PUSH_PY}")', min_tier="R5")

    def test_paren_bearing_harmless(self) -> None:
        self.protected('echo $(python -c "print(1)")')

    def test_contrast_no_parens_already_worked(self) -> None:
        self.protected('echo $(python -c "import os")')

    def test_unterminated_substitution_fails_closed(self) -> None:
        """A `$(` that never closes is a parse FAILURE, not "nothing
        found here" - new `unparsed-substitution` category."""
        verdict = classify_action('echo $(python -c "print(1"')
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["category"], "unparsed-substitution")


class OverTighteningControls(Case):
    """The coordinator's explicit re-verification list: every one of these
    must stay exactly as unprotected as before either round of this fix."""

    def test_python_dash_m_unittest(self) -> None:
        self.unprotected("python -m unittest tests.test_x", tier="R1")

    def test_python_dash_m_pytest(self) -> None:
        self.unprotected("python -m pytest -q", tier="R1")

    def test_python_dash_m_http_server(self) -> None:
        self.unprotected("python -m http.server", tier="R1")

    def test_script_file(self) -> None:
        self.unprotected("python script.py", tier="R1")

    def test_node_script_file(self) -> None:
        self.unprotected("node build.mjs", tier="R1")

    def test_npm_test(self) -> None:
        self.unprotected("npm test")

    def test_git_status(self) -> None:
        self.unprotected("git status", tier="R0")

    def test_pytest_bare(self) -> None:
        self.unprotected("pytest", tier="R1")

    def test_tox_bare(self) -> None:
        self.unprotected("tox", tier="R1")

    def test_bare_env_still_reads(self) -> None:
        """`env` alone (no wrapped command) is still an ordinary read -
        the wrapper-stripping fix must not tighten the harmless case it
        is named after."""
        self.unprotected("env", tier="R0")

    def test_env_wrapping_a_non_interpreter_is_unaffected(self) -> None:
        self.unprotected("env ls -la", tier="R0")


if __name__ == "__main__":
    unittest.main()
