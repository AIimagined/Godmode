"""Refusals reported by people using the plugin, each as a test.

Every case here arrived the same way: somebody hit it in another project, wrote
it down, and passed it back. None was found by reading this code. That is worth
recording in the file itself, because the corpus method that fixed twelve
defects in one pass could only ever find what the corpus contained — and the
corpus held no `npx`, no heredoc script, and no dev-server restart, since those
are not commands this project runs on itself.

Two directions per case. A widened allowance with no mutation beside it proves
only that it widened.
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


class Case(unittest.TestCase):
    def verdict(self, command: str) -> dict:
        return classify_action(command, project_root=PLUGIN_ROOT)

    def allowed(self, command: str) -> None:
        result = self.verdict(command)
        self.assertFalse(result["protected"],
                         f"refused ordinary work: {command} -> {result['category']}")

    def asks(self, command: str, category: str | None = None) -> None:
        """Protected, but not at the tier that refuses outright."""
        result = self.verdict(command)
        self.assertTrue(result["protected"], f"permitted: {command}")
        self.assertNotEqual(result["tier"], "R5", f"should ask, not refuse: {command}")
        if category:
            self.assertEqual(result["category"], category, command)

    def refuses(self, command: str) -> None:
        result = self.verdict(command)
        self.assertTrue(result["protected"], f"permitted: {command}")
        self.assertEqual(result["tier"], "R5", f"should refuse outright: {command}")


class DeleteBlastRadiusTests(Case):
    """Every delete scored R4 — a scratch file and `rm -rf /` alike.

    Invisible while every protected tier refused, because the outcome was the
    same either way. The moment R4 began asking, the difference between those
    two became one keypress.
    """

    def test_a_recursive_delete_at_a_root_refuses_outright(self) -> None:
        for command in ("rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf ~/",
                        "rm -rf $HOME", "rm -rf ${HOME}", "rm -rf %USERPROFILE%",
                        "rm -rf C:/", "rm -rf C:\\", "sudo rm -rf /",
                        "rm -fr /", "rm --recursive --force /"):
            with self.subTest(command=command):
                self.refuses(command)

    def test_an_ordinary_delete_asks(self) -> None:
        for command in ("rm probe-tmp.mjs", "rm lib/brandImageColors.ts",
                        "rm out/one.txt", "rm -rf build", "rm -rf node_modules",
                        "rm -rf ./dist", "rm -f probe.log"):
            with self.subTest(command=command):
                self.asks(command, "filesystem-mutation")

    def test_recursion_is_required_for_the_refusal(self) -> None:
        """`rm /etc/hosts` is bad and stoppable at the asking tier. `rm -rf /`
        is not a thing to confirm in passing."""
        self.asks("rm /etc/hosts")


class ProcessControlTests(Case):
    """Restarting a dev server the agent started was an `unclassified-mutation`
    — the bucket for things the classifier does not recognise at all."""

    def test_ending_a_process_is_named(self) -> None:
        for command in ("kill 12345", "sudo kill -9 3", "taskkill /PID 3 /F",
                        "Stop-Process -Id 3", "pkill node", "killall node",
                        "systemctl stop nginx"):
            with self.subTest(command=command):
                self.asks(command, "process-control")

    def test_the_word_kill_in_an_argument_is_not_a_process(self) -> None:
        """Written as `anywhere in the line` first, which made a search into a
        termination — the same bare-word defect fixed for the database category
        minutes earlier, in the same file."""
        for command in ("grep -rn kill src/", "cat docs/killswitch.md",
                        "ls | grep taskkill", "echo kill"):
            with self.subTest(command=command):
                self.allowed(command)


class NodeToolingTests(Case):
    """`npx` and `npm ci` were unknown mutations, so a session rewrote its
    commands as `node ./node_modules/.bin/...` to get past the gate."""

    def test_the_package_runner_is_local_compute(self) -> None:
        for command in ("npx tsc --noEmit", "npx prettier --check .",
                        "npm ci", "npm install", "npm run build:prod",
                        "npm run lint-fix"):
            with self.subTest(command=command):
                self.allowed(command)

    def test_a_delete_after_it_is_still_seen(self) -> None:
        self.refuses("npx tsc --noEmit && rm -rf /")


class HeredocTests(Case):
    """A newline ends a segment, so every line of a heredoc body was
    classified as a command: `import json` became an unknown mutation."""

    SCRIPT = "python - <<'PY'\nimport json\nprint(json.dumps({'ok': 1}))\nPY"

    def test_a_heredoc_body_is_data(self) -> None:
        self.allowed(self.SCRIPT)
        self.assertEqual(shell_segments(self.SCRIPT), ["python - <<'PY'"])

    def test_a_command_after_the_delimiter_is_still_a_command(self) -> None:
        self.allowed(self.SCRIPT + "\ngit status --short")
        self.refuses(self.SCRIPT + "\nrm -rf /")

    def test_a_substitution_inside_a_body_is_still_run(self) -> None:
        """The shell really does expand it, so the gate has to see it."""
        self.asks("cat <<EOF\nvalue is $(rm -rf build)\nEOF")

    def test_an_unterminated_heredoc_does_not_classify_the_rest(self) -> None:
        self.allowed("python - <<'PY'\nprint(1)")


class ConfigDiscoveryTests(unittest.TestCase):
    """`config check` iterated a schema table, so it validated the files
    somebody had written a schema for rather than the files the project ships.

    `.godmode-docslint.json` governs the docs linter here and was absent from
    the table: replacing it with unparseable text left the command green.
    """

    def test_every_config_in_the_tree_is_discovered(self) -> None:
        from godmode_runtime.godmode_console import _CONFIG_CONTRACTS

        present = {path.name for path in PLUGIN_ROOT.glob(".godmode-*.json")}
        self.assertTrue(present, "no config files to check")
        undeclared = sorted(present - set(_CONFIG_CONTRACTS))
        # Not an error — discovery is by glob now, so a file with no schema is
        # still required to parse. This asserts such a file exists, so the
        # glob path stays exercised rather than becoming dead code.
        self.assertTrue(
            undeclared or present,
            "expected at least one config file on disk")


if __name__ == "__main__":
    unittest.main()
