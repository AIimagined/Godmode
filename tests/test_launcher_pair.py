"""R-3/R-3a: the launcher template pair is generated, never hand-edited.

`hooks/run-hook.cmd` (the polyglot sh+cmd entry) and `hooks/run-hook.sh` (a
plain POSIX sibling for hosts whose manifest wants a bare `.sh`) both come
from templates in `scripts/godmode_runtime/godmode_launchers.py`. This test
is the "generate -> compare bytes" acceptance check the plan names: it
renders both templates and diffs them against the committed tree, and it
proves `godmode bindings --write`/`--check` (the one place a caller
actually regenerates them) drive the same templates, not a second copy.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_launchers as launchers  # noqa: E402
from godmode_runtime import godmode_bindings as bindings  # noqa: E402
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import scrubbed_env  # noqa: E402


class LauncherTemplateByteIdentityTests(unittest.TestCase):
    """Generate -> compare bytes, for both templates, against the tree."""

    def test_cmd_launcher_matches_the_committed_polyglot_byte_for_byte(self) -> None:
        on_disk = (PLUGIN_ROOT / "hooks" / "run-hook.cmd").read_bytes()
        rendered = launchers.render("cmd").encode("utf-8")
        self.assertEqual(on_disk, rendered)

    def test_sh_launcher_matches_the_committed_posix_sibling_byte_for_byte(self) -> None:
        on_disk = (PLUGIN_ROOT / "hooks" / "run-hook.sh").read_bytes()
        rendered = launchers.render("sh").encode("utf-8")
        self.assertEqual(on_disk, rendered)

    def test_both_launchers_are_lf_only(self) -> None:
        for name in ("cmd", "sh"):
            with self.subTest(name=name):
                self.assertNotIn(b"\r\n", launchers.render(name).encode("utf-8"))

    def test_unknown_template_name_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            launchers.render("ps1")

    def test_both_committed_launchers_are_executable_in_git(self) -> None:
        for path in ("hooks/run-hook.cmd", "hooks/run-hook.sh"):
            with self.subTest(path=path):
                mode = subprocess.run(
                    ["git", "ls-files", "-s", path],
                    capture_output=True, text=True, cwd=PLUGIN_ROOT).stdout
                self.assertTrue(mode.startswith("100755"), f"{path}: {mode}")

    def test_cmd_sh_half_and_sh_launcher_share_identical_code_lines(self) -> None:
        """B2 (task-3-review.md): the cheap floor named alongside the shared
        `_SH_BODY` constant - strip `.cmd`'s `:; ` sh-half prefix from the
        `hook="$1"; shift` .. `exit 0` window and diff it line-for-line
        against the same window in `.sh`. This is deliberately independent
        of `godmode_launchers.py`'s internals (it reads the committed files,
        not `render()`), so a future hand-edit to either file that
        reintroduces the B1-class divergence (the two copies of this logic
        drifting apart) fails here even if someone bypasses the generator.
        """
        def code_window(lines: list[str], prefix: str = "") -> list[str]:
            collected: list[str] = []
            collecting = False
            for raw in lines:
                line = raw[len(prefix):] if prefix and raw.startswith(prefix) else raw
                if not collecting and line == 'hook="$1"; shift':
                    collecting = True
                if collecting:
                    collected.append(line)
                    if line == "exit 0":
                        break
            return collected

        cmd_lines = (PLUGIN_ROOT / "hooks" / "run-hook.cmd").read_text(encoding="utf-8").splitlines()
        sh_lines = (PLUGIN_ROOT / "hooks" / "run-hook.sh").read_text(encoding="utf-8").splitlines()

        cmd_code = code_window(cmd_lines, prefix=":; ")
        sh_code = code_window(sh_lines)

        self.assertTrue(cmd_code, "did not find the hook=.../exit 0 window in run-hook.cmd")
        self.assertTrue(sh_code, "did not find the hook=.../exit 0 window in run-hook.sh")
        self.assertEqual(cmd_code, sh_code)


class PolyglotShHalfParsesTests(unittest.TestCase):
    """Every sh line of the polyglot carries a `:; ` prefix, which a
    multi-line `case` cannot take (`:;   /*) ;;` is a syntax error) - found
    while adding the interpreter cache (2026-09-23). The prefixed sh half,
    exactly as committed, must parse."""

    def test_the_prefixed_sh_half_parses(self) -> None:
        sh = ShLauncherRunsEndToEndTests._sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        lines = (PLUGIN_ROOT / "hooks" / "run-hook.cmd").read_text(encoding="utf-8").splitlines()
        end = lines.index(":; exit 0")
        with tempfile.TemporaryDirectory() as temp:
            half = Path(temp) / "sh-half.sh"
            half.write_text("\n".join(lines[:end + 1]) + "\n", encoding="utf-8", newline="\n")
            done = subprocess.run([sh, "-n", str(half)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)


class LauncherRegenerationTests(unittest.TestCase):
    """`godmode bindings --write`/`--check` regenerate both from one source."""

    def _fresh_project(self) -> Path:
        temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "packaging").mkdir()
        shutil.copy(PLUGIN_ROOT / "packaging" / "hosts.json", temp / "packaging" / "hosts.json")
        return temp

    def test_write_launchers_regenerates_both_files_byte_identical_to_the_tree(self) -> None:
        project = self._fresh_project()
        result = launchers.write_launchers(project)
        self.assertEqual(sorted(result["written"]), ["hooks/run-hook.cmd", "hooks/run-hook.sh"])
        for relative in ("hooks/run-hook.cmd", "hooks/run-hook.sh"):
            with self.subTest(relative=relative):
                self.assertEqual((project / relative).read_bytes(),
                                 (PLUGIN_ROOT / relative).read_bytes())

    def test_rerunning_write_launchers_is_a_byte_stable_no_op(self) -> None:
        project = self._fresh_project()
        launchers.write_launchers(project)
        second = launchers.write_launchers(project)
        self.assertEqual(second["written"], [])
        self.assertEqual(second["unchanged"], len(launchers.LAUNCHERS))

    def test_launchers_check_reports_missing_then_current(self) -> None:
        project = self._fresh_project()
        before = {entry["launcher"]: entry["state"] for entry in launchers.check(project)}
        self.assertEqual(before, {"cmd": "missing", "sh": "missing"})
        launchers.write_launchers(project)
        after = {entry["launcher"]: entry["state"] for entry in launchers.check(project)}
        self.assertEqual(after, {"cmd": "current", "sh": "current"})

    def test_launchers_check_reports_drifted_after_a_hand_edit(self) -> None:
        # N1 (task-3-review.md): the "missing" -> "current" pair above never
        # exercises `check()`'s third state - a byte mismatch against an
        # already-present file.
        project = self._fresh_project()
        launchers.write_launchers(project)
        (project / "hooks" / "run-hook.sh").write_bytes(b"#!/bin/sh\necho hand-edited\n")
        after = {entry["launcher"]: entry["state"] for entry in launchers.check(project)}
        self.assertEqual(after, {"cmd": "current", "sh": "drifted"})

    def test_bindings_write_includes_the_launcher_pair_and_bindings_check_agrees(self) -> None:
        project = self._fresh_project()
        result = bindings.write(project)
        self.assertIn("hooks/run-hook.cmd", result["written"])
        self.assertIn("hooks/run-hook.sh", result["written"])
        report = bindings.check(project)
        launcher_rows = [row for row in report["hosts"] if row.get("kind") == "launcher"]
        self.assertEqual(len(launcher_rows), 2)
        self.assertTrue(all(row["state"] == "current" for row in launcher_rows), launcher_rows)

    def test_the_repository_itself_is_current_against_the_generator(self) -> None:
        # The tree this test runs against must already be what the
        # generator would produce - the whole point of "regenerated, never
        # hand-edited" is that a stray hand-edit shows up here as drift.
        report = bindings.check(PLUGIN_ROOT)
        launcher_rows = [row for row in report["hosts"] if row.get("kind") == "launcher"]
        self.assertEqual(len(launcher_rows), 2)
        self.assertTrue(all(row["state"] == "current" for row in launcher_rows), launcher_rows)


class ShLauncherRunsEndToEndTests(unittest.TestCase):
    """The generated `.sh` actually dispatches a hook, the way a host would
    invoke it - not just a byte comparison against the template."""

    @staticmethod
    def _sh() -> str | None:
        found = shutil.which("sh")
        if found:
            return found
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "usr" / "bin" / "sh.exe"
            if candidate.is_file():
                return str(candidate)
        return None

    def test_sh_launcher_runs_a_hook_end_to_end(self) -> None:
        sh = self._sh()
        if not sh:
            self.skipTest("no POSIX sh on this machine")
        # `.as_posix()`, not `str()`: this test drives a real hook dispatch
        # end to end and wants root resolution to succeed unconditionally,
        # independent of which `case` branch fires. The backslash branch
        # (`*\\*`) is pinned on its own, with a genuine backslash-bearing
        # `$0`, by tests.test_launcher_root_fallback.BackslashRootGuardTests
        # (task-3 review B1) - see that test for the fix and its evidence.
        result = subprocess.run(
            [sh, (PLUGIN_ROOT / "hooks" / "run-hook.sh").as_posix(), "godmode_post_edit.py"],
            input="{}", capture_output=True, text=True, timeout=60,
            env=scrubbed_env())
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
