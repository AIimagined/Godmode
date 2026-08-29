"""CX-4: the git-hook enforcement backstop.

Every other boundary this product ships (CX-1/CX-2/CX-3) fires only while a
specific host is driving the terminal. This one writes real project-local
git hooks that call back into `godmode guard --git-hook <name>` and fail
closed at git's own chokepoint - independent of whatever (or nothing) drove
git. Tests here run REAL git repositories and REAL git subprocesses; nothing
is mocked at the git boundary, because a mocked git is exactly the kind of
"empty stdout read as allow" harness lesson CX's own design doc names as the
failure to never repeat.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import main as cli_main  # noqa: E402
from godmode_runtime.godmode_githooks import (  # noqa: E402
    HASH_PREFIX,
    HOOK_NAMES,
    KNOWN_BYPASS,
    MARKER_PREFIX,
    POLICY_KEY,
    _canonical_body,
    _hook_file_state,
    _hook_script,
    evaluate_git_hook,
    git_hooks_install,
    git_hooks_status,
    git_hooks_uninstall,
    run_git_verify,
)
from godmode_runtime.godmode_hookproof import SUBJECT_UNINSTALLED, interception_state  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker, POLICY_FILENAME  # noqa: E402

GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"


def _git(*args: str, cwd: Path, timeout: int = 20, env: dict | None = None,
         ) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True,
        timeout=timeout, env=env,
    )


def _init_repo(project: Path) -> None:
    project.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@t.invalid"],
        ["config", "user.name", "t"],
        # Pin the branch name: `git init`'s own default varies by machine
        # config (`master` here), and every push-related test below assumes
        # `main`. Safe on an unborn repo - it only renames the symbolic ref.
        ["checkout", "-q", "-b", "main"],
    ):
        result = _git(*args, cwd=project)
        assert result.returncode == 0, result.stderr


def _commit(project: Path, name: str, content: str) -> str:
    (project / name).write_text(content, encoding="utf-8")
    _git("add", name, cwd=project)
    committed = _git("commit", "-q", "-m", f"commit {name}:{content}", cwd=project)
    assert committed.returncode == 0, committed.stderr
    return _git("rev-parse", "HEAD", cwd=project).stdout.strip()


@contextmanager
def isolated_git_project():
    """A real, throwaway git repository with its own isolated godmode state."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        _init_repo(project)
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            archive.initialize()
            yield project, archive


def _declare_policy(project: Path) -> None:
    (project / POLICY_FILENAME).write_text(
        json.dumps({POLICY_KEY: True}), encoding="utf-8")


def _cli(project: Path, state_home: Path, *args: str, input_text: str | None = None,
          cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GODMODE_STATE_HOME"] = str(state_home)
    return subprocess.run(
        [sys.executable, str(GODMODE_CLI), "--project", str(project), "--json", *args],
        capture_output=True, text=True, cwd=str(cwd or project), env=env, timeout=60,
        input=input_text,
    )


class HookScriptContentTests(unittest.TestCase):
    def test_script_shebang_marker_and_hash_header(self) -> None:
        content = _hook_script("pre-push", Path("/opt/godmode/scripts/godmode.py"))
        lines = content.splitlines()
        self.assertEqual(lines[0], "#!/bin/sh")
        self.assertTrue(any(line.startswith(f"{MARKER_PREFIX} pre-push") for line in lines))
        self.assertTrue(any(line.startswith(HASH_PREFIX) for line in lines))

    def test_python3_is_tried_before_python_and_neither_found_fails_closed(self) -> None:
        content = _hook_script("pre-commit", Path("/opt/godmode/scripts/godmode.py"))
        self.assertIn("command -v python3", content)
        self.assertIn("PYTHON=python3", content)
        self.assertIn("PYTHON=python", content)
        self.assertIn("exit 1", content)
        self.assertNotIn("$env:", content)
        self.assertNotIn("Get-Content", content)

    def test_windows_path_with_spaces_is_forward_slashed_and_quoted(self) -> None:
        windows_path = Path(r"C:\Users\a user\Program Files\godmode\scripts\godmode.py")
        content = _hook_script("pre-push", windows_path)
        self.assertIn('"C:/Users/a user/Program Files/godmode/scripts/godmode.py"', content)
        self.assertNotIn("\\Users\\a user", content)

    def test_hash_changes_with_hook_name_or_path(self) -> None:
        one = _hook_script("pre-push", Path("/a/godmode.py"))
        two = _hook_script("pre-commit", Path("/a/godmode.py"))
        three = _hook_script("pre-push", Path("/b/godmode.py"))
        self.assertNotEqual(one, two)
        self.assertNotEqual(one, three)


class KnownBypassDisclosureTests(unittest.TestCase):
    """Fix round 1, I1: `--no-verify` must be disclosed everywhere the
    feature describes itself, not just in prose a reader has to go find."""

    def test_module_constant_names_no_verify(self) -> None:
        self.assertIn("--no-verify", KNOWN_BYPASS)

    def test_status_git_surfaces_the_same_disclosure(self) -> None:
        with isolated_git_project() as (project, archive):
            status = git_hooks_status(archive, project)
            self.assertIn("--no-verify", status["known_bypass"])

    def test_docs_disclose_the_bypass(self) -> None:
        docs = (PLUGIN_ROOT / "hooks" / "GODMODE_HOOKS.md").read_text(encoding="utf-8")
        self.assertIn("--no-verify", docs)

    def test_changelog_fragment_discloses_the_bypass(self) -> None:
        # The fragment lives in changelog.d/ until a release merges it into
        # CHANGELOG.md; the disclosure must survive the merge, so whichever
        # of the two holds it is the one read.
        fragment_path = PLUGIN_ROOT / "changelog.d" / "cx4-githooks.added.md"
        text = (fragment_path.read_text(encoding="utf-8") if fragment_path.exists()
                else (PLUGIN_ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertIn("--no-verify", text)


class InstallRefusalTests(unittest.TestCase):
    def test_install_refuses_without_declared_policy(self) -> None:
        with isolated_git_project() as (project, archive):
            report = git_hooks_install(archive, project)
            self.assertFalse(report["declared"])
            self.assertEqual(report["installed"], [])
            self.assertIn(POLICY_FILENAME, report["reason"])
            self.assertIn(POLICY_KEY, report["reason"])
            for name in HOOK_NAMES:
                self.assertFalse((project / ".git" / "hooks" / name).exists())

    def test_declaring_afterward_makes_install_available_ratchet_tighten_only(self) -> None:
        with isolated_git_project() as (project, archive):
            refused = git_hooks_install(archive, project)
            self.assertFalse(refused["declared"])
            _declare_policy(project)
            report = git_hooks_install(archive, project)
            self.assertTrue(report["declared"])
            self.assertEqual(set(report["installed"]), set(HOOK_NAMES))
            # Ratchet: removing the key afterward must not un-declare it.
            (project / POLICY_FILENAME).write_text(json.dumps({}), encoding="utf-8")
            still = git_hooks_install(archive, project)
            self.assertTrue(still["declared"])


class InstallFailureReportingTests(unittest.TestCase):
    """M6 (external audit): `declared: True` used to be the CLI's only exit
    -code signal, so an unresolvable hooks directory or a swallowed `chmod`
    failure both reported success (`declared: True`, exit 0) with nothing
    actually installed or executable."""

    def test_an_unresolvable_hooks_directory_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "not-a-git-repo"
            project.mkdir()
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
            ):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                _declare_policy(project)
                report = git_hooks_install(archive, project)
        self.assertTrue(report["declared"])
        self.assertFalse(report["ok"],
                         "an unresolvable hooks directory reported success")
        self.assertEqual(report["installed"], [])

    def test_the_cli_exits_nonzero_on_an_unresolvable_hooks_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "not-a-git-repo"
            project.mkdir()
            state_home = base / "state"
            _cli(project, state_home, "init")
            _declare_policy(project)
            result = _cli(project, state_home, "hooks", "install", "--git")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["declared"])
        self.assertFalse(payload["ok"])

    def test_a_swallowed_chmod_failure_is_reported_not_hidden(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            with mock.patch.object(Path, "chmod", side_effect=OSError("denied")):
                report = git_hooks_install(archive, project)
        self.assertFalse(report["ok"], "a chmod failure was silently reported as success")
        self.assertEqual(set(report["chmod_failed"]), set(HOOK_NAMES))
        # Still written to disk - the file itself is not lost, only not yet
        # executable - `installed` still names it so a caller can tell
        # "written, not executable" apart from "never written at all".
        self.assertEqual(set(report["installed"]), set(HOOK_NAMES))


class InstallWritesHooksTests(unittest.TestCase):
    def test_install_writes_all_four_hooks_with_marker_and_executable(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            report = git_hooks_install(archive, project)
            self.assertEqual(set(report["installed"]), set(HOOK_NAMES))
            hooks_dir = project / ".git" / "hooks"
            for name in HOOK_NAMES:
                path = hooks_dir / name
                self.assertTrue(path.is_file(), name)
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("#!/bin/sh"), name)
                self.assertIn(f"{MARKER_PREFIX} {name}", text)
                self.assertIn(HASH_PREFIX, text)
                if os.name != "nt":
                    # Windows/NTFS has no POSIX execute bit to observe here;
                    # git for Windows runs hooks via shebang regardless, and
                    # the real `git push` test elsewhere already proves the
                    # installed hook actually runs on this platform.
                    mode = path.stat().st_mode
                    self.assertTrue(mode & 0o111, f"{name} is not executable: {oct(mode)}")

    def test_reinstall_over_its_own_hook_is_an_ordinary_update(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            second = git_hooks_install(archive, project)
            self.assertEqual(set(second["installed"]), set(HOOK_NAMES))
            self.assertEqual(second["skipped_foreign"], [])


class TamperDetectionTests(unittest.TestCase):
    """Fix round 1, C1: `hooks status --git` must catch a hand-edit even
    when the editor never touches the hash header line - the reviewer's
    own live repro, run here directly against the fixed mechanism."""

    def test_canonical_body_excludes_only_the_hash_line(self) -> None:
        text = "#!/bin/sh\n# godmode-git-hook: pre-push\n# godmode-hook-hash: deadbeef\nexit 0\n"
        self.assertEqual(_canonical_body(text),
                          "#!/bin/sh\n# godmode-git-hook: pre-push\nexit 0")

    def test_a_freshly_installed_hook_is_self_consistent(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            path = project / ".git" / "hooks" / "pre-push"
            self.assertEqual(_hook_file_state(path, "pre-push")["state"], "godmode")

    def test_the_reviewers_exact_tamper_is_now_caught(self) -> None:
        # Live repro from the review: `sed -i 's/exit \$?/exit 0  # tampered:
        # always allow/'` - edits the body, never touches the header line.
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            path = project / ".git" / "hooks" / "pre-push"
            before = _hook_file_state(path, "pre-push")
            self.assertEqual(before["state"], "godmode")
            original = path.read_text(encoding="utf-8")
            self.assertIn("exit $?", original)
            tampered = original.replace("exit $?", "exit 0  # tampered: always allow")
            path.write_text(tampered, encoding="utf-8")
            after = _hook_file_state(path, "pre-push")
            self.assertEqual(after["state"], "godmode-modified")
            # The header's OWN claimed hash is untouched by the edit - the
            # old, defective comparison (recomputed from name+path alone)
            # would have matched it anyway. The recorded hash is unchanged...
            self.assertEqual(after["hash"], before["hash"])
            # ...but `hooks status --git` (which reads the file, not the
            # header's own say-so) now disagrees with it.
            status = git_hooks_status(archive, project)
            self.assertEqual(status["hooks"]["pre-push"]["state"], "godmode-modified")

    def test_a_whitespace_only_edit_is_still_modified_byte_honestly(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            path = project / ".git" / "hooks" / "pre-push"
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            self.assertEqual(_hook_file_state(path, "pre-push")["state"], "godmode-modified")

    def test_a_regenerated_identical_reinstall_still_reads_godmode(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            git_hooks_install(archive, project)  # reinstall: fresh header + fresh hash
            path = project / ".git" / "hooks" / "pre-push"
            self.assertEqual(_hook_file_state(path, "pre-push")["state"], "godmode")

    def test_a_missing_hash_line_is_modified_not_godmode(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            path = project / ".git" / "hooks" / "pre-push"
            text = path.read_text(encoding="utf-8")
            stripped = "\n".join(
                line for line in text.splitlines() if not line.startswith(HASH_PREFIX)) + "\n"
            path.write_text(stripped, encoding="utf-8")
            state = _hook_file_state(path, "pre-push")
            self.assertEqual(state["state"], "godmode-modified")
            self.assertIsNone(state["hash"])


class SampleFileTests(unittest.TestCase):
    def test_sample_files_are_never_read_as_installed(self) -> None:
        with isolated_git_project() as (project, archive):
            hooks_dir = project / ".git" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)
            for name in HOOK_NAMES:
                sample = hooks_dir / f"{name}.sample"
                sample.write_text("#!/bin/sh\n# a git-shipped sample, never installed\n",
                                   encoding="utf-8")
            status = git_hooks_status(archive, project)
            for name in HOOK_NAMES:
                self.assertEqual(status["hooks"][name]["state"], "absent")
                self.assertTrue((hooks_dir / f"{name}.sample").is_file())

            _declare_policy(project)
            report = git_hooks_install(archive, project)
            # Samples are not "foreign" and not overwritten - install writes
            # the real hook name alongside the untouched .sample.
            self.assertEqual(set(report["installed"]), set(HOOK_NAMES))
            self.assertEqual(report["skipped_foreign"], [])
            for name in HOOK_NAMES:
                sample_text = (hooks_dir / f"{name}.sample").read_text(encoding="utf-8")
                self.assertIn("never installed", sample_text)


class ForeignHookTests(unittest.TestCase):
    def test_a_pre_existing_foreign_hook_is_never_overwritten(self) -> None:
        with isolated_git_project() as (project, archive):
            hooks_dir = project / ".git" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)
            foreign_path = hooks_dir / "pre-commit"
            foreign_content = "#!/bin/sh\necho 'a human wrote this'\nexit 0\n"
            foreign_path.write_text(foreign_content, encoding="utf-8")

            _declare_policy(project)
            report = git_hooks_install(archive, project)
            self.assertIn("pre-commit", report["skipped_foreign"])
            self.assertNotIn("pre-commit", report["installed"])
            self.assertEqual(foreign_path.read_text(encoding="utf-8"), foreign_content)
            # The other three, uncontested, still install.
            self.assertEqual(set(report["installed"]), set(HOOK_NAMES) - {"pre-commit"})

            status = git_hooks_status(archive, project)
            self.assertEqual(status["hooks"]["pre-commit"]["state"], "foreign")

    def test_uninstall_never_removes_a_foreign_hook(self) -> None:
        with isolated_git_project() as (project, archive):
            hooks_dir = project / ".git" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)
            foreign_path = hooks_dir / "pre-rebase"
            foreign_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            _declare_policy(project)
            git_hooks_install(archive, project)
            git_hooks_uninstall(archive, project)
            self.assertTrue(foreign_path.is_file())


class UninstallTests(unittest.TestCase):
    def test_uninstall_removes_godmode_hooks_and_chronicles_a_counts_only_event(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            before = len(archive.select(kind="action", subject=SUBJECT_UNINSTALLED, limit=50))
            result = git_hooks_uninstall(archive, project)
            self.assertEqual(result["removed_count"], len(HOOK_NAMES))
            for name in HOOK_NAMES:
                self.assertFalse((project / ".git" / "hooks" / name).exists())
            records = archive.select(kind="action", subject=SUBJECT_UNINSTALLED, limit=50)
            self.assertEqual(len(records), before + 1)
            data = records[-1]["data"]
            self.assertEqual(data["host"], "git")
            self.assertEqual(data["removed_count"], len(HOOK_NAMES))
            # Counts-only: no hook names, no paths in the chronicled record.
            self.assertNotIn("pre-push", json.dumps(data))

    def test_ratchet_keeps_the_declaration_visible_after_uninstall(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            git_hooks_install(archive, project)
            result = git_hooks_uninstall(archive, project)
            self.assertTrue(result["declared_still_visible"])
            # Even with the policy file itself removed afterward.
            (project / POLICY_FILENAME).unlink()
            status = git_hooks_status(archive, project)
            self.assertTrue(status["declared"])


class PrePushBlockingTests(unittest.TestCase):
    """The one scenario the spec names explicitly: local behind/diverged
    remote, asserted at both the hook-script layer and a real `git push`.

    `project` (from `isolated_git_project`) is used directly as the
    diverging work tree - its archive is already initialized AT project's
    own resolved identity, the same identity a real `git push` subprocess
    (CWD=project) independently resolves. A separate, never-initialized
    directory would report "not initialized" to the hook and silently
    allow everything - the exact silent-pass shape CX-1's own fix round
    already named and fixed once; not repeating it here.
    """

    def _diverge_history(self, project: Path):
        base = project.parent
        remote = base / "remote.git"
        _git("init", "-q", "--bare", str(remote), cwd=base)
        commit_a = _commit(project, "file.txt", "a")
        _git("remote", "add", "origin", str(remote), cwd=project)
        pushed = _git("push", "-q", "-u", "origin", "main", cwd=project)
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        commit_b = _commit(project, "file.txt", "b")
        pushed = _git("push", "-q", "origin", "main", cwd=project)
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        # Diverge: local main forgets B and adds a different commit C.
        _git("reset", "-q", "--hard", commit_a, cwd=project)
        commit_c = _commit(project, "file.txt", "c")
        return remote, commit_b, commit_c

    def test_pre_push_hook_script_exits_nonzero_and_a_real_push_also_fails(self) -> None:
        with isolated_git_project() as (project, archive):
            remote, commit_b, commit_c = self._diverge_history(project)
            _declare_policy(project)
            report = git_hooks_install(archive, project)
            self.assertIn("pre-push", report["installed"])

            hook_path = project / ".git" / "hooks" / "pre-push"
            stdin_text = f"refs/heads/main {commit_c} refs/heads/main {commit_b}\n"
            # Antigravity field report 2026-08-29: a pure-Windows host
            # without Git Bash has no `sh` on PATH (WinError 2). The hook
            # still runs inside git's own bundled shell during a real push -
            # the direct invocation below is the only part that needs one.
            import shutil
            shell = shutil.which("sh") or shutil.which("bash")
            if shell is None:
                self.skipTest("no POSIX shell on PATH; the real-push half "
                              "of this contract runs in git's bundled shell")
            direct = subprocess.run(
                [shell, str(hook_path)], input=stdin_text, capture_output=True,
                text=True, cwd=str(project), env=os.environ.copy(), timeout=30,
            )
            self.assertNotEqual(direct.returncode, 0, direct.stderr)

            remote_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
            real_push = _git("push", "origin", "main", cwd=project, env=os.environ.copy())
            self.assertNotEqual(real_push.returncode, 0, real_push.stdout + real_push.stderr)
            remote_after = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
            self.assertEqual(remote_before, remote_after)
            self.assertEqual(remote_after, commit_b)

    def test_evaluate_git_hook_reports_block_with_honest_detection_note(self) -> None:
        with isolated_git_project() as (project, archive):
            remote, commit_b, commit_c = self._diverge_history(project)
            _declare_policy(project)
            stdin_text = f"refs/heads/main {commit_c} refs/heads/main {commit_b}\n"
            report = evaluate_git_hook(archive, project, "pre-push", stdin_text)
            self.assertEqual(report["verdict"], "block")
            self.assertTrue(report["protected"])
            self.assertIn("CANNOT see the --force", report["detects"])

    def test_staged_capability_is_the_escape_valve(self) -> None:
        with isolated_git_project() as (project, archive):
            remote, commit_b, commit_c = self._diverge_history(project)
            _declare_policy(project)
            operation = "git push --force origin refs/heads/main:refs/heads/main"
            broker = CapabilityBroker(archive)
            broker.configure("correct horse battery staple")
            broker.stage(operation, "correct horse battery staple")

            stdin_text = f"refs/heads/main {commit_c} refs/heads/main {commit_b}\n"
            report = evaluate_git_hook(archive, project, "pre-push", stdin_text)
            self.assertEqual(report["verdict"], "allow")
            self.assertTrue(report.get("capability_consumed"))

    def test_no_ref_updates_on_stdin_allows(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-push", "")
            self.assertEqual(report["verdict"], "allow")
            self.assertEqual(report["ref_updates"], 0)

    def test_ordinary_push_is_also_protected_when_no_capability_staged(self) -> None:
        # Reuses the SAME classifier the interactive gate already answers
        # through - a plain `git push` is protected there too, so the
        # backstop's coverage is not a second, narrower list.
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            zero = "0" * 40
            fake_sha = "1" * 40
            stdin_text = f"refs/heads/topic {fake_sha} refs/heads/topic {zero}\n"
            report = evaluate_git_hook(archive, project, "pre-push", stdin_text)
            self.assertEqual(report["verdict"], "block")
            self.assertTrue(report["protected"])

    def test_undeclared_policy_never_blocks_pre_push(self) -> None:
        with isolated_git_project() as (project, archive):
            remote, commit_b, commit_c = self._diverge_history(project)
            # Policy NOT declared.
            stdin_text = f"refs/heads/main {commit_c} refs/heads/main {commit_b}\n"
            report = evaluate_git_hook(archive, project, "pre-push", stdin_text)
            self.assertEqual(report["verdict"], "allow")
            self.assertFalse(report["policy_declared"])


class MalformedStdinTests(unittest.TestCase):
    """Fix round 1, C2: malformed/unreadable pre-push stdin must never be
    folded into "nothing to push" - the plan's Global Constraint ("silence
    is never permission") applied to this hook's own input parsing."""

    # The reviewer's exact live repro: a 5-field line.
    HOSTILE_LINE = (
        "refs/heads/main abc123 refs/heads/main def456 extra-garbage-field\n"
    )

    def test_reviewers_hostile_line_is_refused_under_declared_policy(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-push", self.HOSTILE_LINE)
            self.assertEqual(report["verdict"], "block")
            self.assertEqual(report["category"], "malformed-git-hook-input")
            self.assertIn("malformed-stdin", report["reason"])

    def test_genuinely_empty_stdin_is_allowed_regardless_of_policy(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-push", "")
            self.assertEqual(report["verdict"], "allow")
            self.assertEqual(report["ref_updates"], 0)

    def test_malformed_stdin_without_declared_policy_is_advisory_allow(self) -> None:
        with isolated_git_project() as (project, archive):
            # Policy NOT declared.
            report = evaluate_git_hook(archive, project, "pre-push", self.HOSTILE_LINE)
            self.assertEqual(report["verdict"], "allow")
            self.assertFalse(report["policy_declared"])
            self.assertIn("malformed-stdin", report["reason"])
            self.assertIn("advisory-only", report["reason"])

    def test_unreadable_stdin_none_also_fails_closed_under_policy(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-push", None)
            self.assertEqual(report["verdict"], "block")
            self.assertEqual(report["category"], "malformed-git-hook-input")

    def test_malformed_input_is_chronicled_counts_only(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            evaluate_git_hook(archive, project, "pre-push", self.HOSTILE_LINE)
            records = archive.select(
                kind="action", subject="git-hook-malformed-input", limit=10)
            self.assertEqual(len(records), 1)
            data = records[0]["data"]
            self.assertEqual(data["host"], "git")
            self.assertNotIn("abc123", json.dumps(data))
            self.assertNotIn("extra-garbage-field", json.dumps(data))

    def test_cli_guard_git_hook_refuses_the_hostile_line_under_policy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "proj"
            state_home = base / "state"
            _init_repo(project)
            _cli(project, state_home, "init")
            _declare_policy(project)
            result = _cli(project, state_home, "guard", "--git-hook", "pre-push",
                          input_text=self.HOSTILE_LINE)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "block")
            self.assertEqual(payload["category"], "malformed-git-hook-input")


class PreCommitInspectionFailureTests(unittest.TestCase):
    """H2 (external audit, missed by CX-4's own review): `godmode_githooks.
    _staged_paths` converted a nonzero `git diff --cached --name-only` into
    `[]`, which `_evaluate_pre_commit` then read as "no staged changes" -
    allow, exit 0, every pinned-file check and capability consumption
    skipped, on a commit this hook never actually inspected."""

    @staticmethod
    def _corrupt_index(project: Path) -> None:
        # The audit's own reproducible shape: `git diff --cached --name-
        # only` failing for a real, git-verifiable reason (not a mock) - a
        # truncated index file git refuses to read.
        (project / "a.txt").write_text("x", encoding="utf-8")
        _git("add", "a.txt", cwd=project)
        (project / ".git" / "index").write_bytes(b"garbage-not-an-index")

    def test_a_corrupted_index_fails_closed_under_declared_policy(self) -> None:
        with isolated_git_project() as (project, archive):
            self._corrupt_index(project)
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-commit", "")
            self.assertEqual(report["verdict"], "block")
            self.assertEqual(report["category"], "inspection-failed")

    def test_a_corrupted_index_without_declared_policy_is_advisory_allow(self) -> None:
        with isolated_git_project() as (project, archive):
            self._corrupt_index(project)
            # Policy NOT declared.
            report = evaluate_git_hook(archive, project, "pre-commit", "")
            self.assertEqual(report["verdict"], "allow")
            self.assertFalse(report["policy_declared"])
            self.assertIn("inspection-failed", report["reason"])
            self.assertIn("advisory-only", report["reason"])

    def test_inspection_failure_is_chronicled_counts_only(self) -> None:
        with isolated_git_project() as (project, archive):
            self._corrupt_index(project)
            _declare_policy(project)
            evaluate_git_hook(archive, project, "pre-commit", "")
            records = archive.select(
                kind="action", subject="git-hook-inspection-failed", limit=10)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["host"], "git")

    def test_cli_guard_git_hook_refuses_a_corrupted_index_under_policy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "proj"
            state_home = base / "state"
            _init_repo(project)
            _cli(project, state_home, "init")
            self._corrupt_index(project)
            _declare_policy(project)
            result = _cli(project, state_home, "guard", "--git-hook", "pre-commit")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "block")
            self.assertEqual(payload["category"], "inspection-failed")


class PreCommitPreRebasePostCheckoutTests(unittest.TestCase):
    def test_pre_commit_blocks_staging_a_pinned_evaluator(self) -> None:
        with isolated_git_project() as (project, archive):
            from godmode_runtime.godmode_sentinel import pin_evaluator

            evaluator = project / "evaluator.py"
            evaluator.write_text("def score(): return 1\n", encoding="utf-8")
            _git("add", "evaluator.py", cwd=project)
            _git("commit", "-q", "-m", "add evaluator", cwd=project)
            pin_evaluator(archive, project, "evaluator.py")

            evaluator.write_text("def score(): return 2\n", encoding="utf-8")
            _git("add", "evaluator.py", cwd=project)

            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-commit", "")
            self.assertEqual(report["verdict"], "block")
            self.assertEqual(report["category"], "pinned-evaluator-mutation")

    def test_pre_commit_allows_ordinary_staged_files(self) -> None:
        with isolated_git_project() as (project, archive):
            (project / "notes.md").write_text("hello\n", encoding="utf-8")
            _git("add", "notes.md", cwd=project)
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-commit", "")
            self.assertEqual(report["verdict"], "allow")

    def test_pre_rebase_is_protected_uniformly_under_declared_policy(self) -> None:
        with isolated_git_project() as (project, archive):
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "pre-rebase", "")
            self.assertEqual(report["verdict"], "block")
            self.assertTrue(report["protected"])

    def test_pre_rebase_allows_when_undeclared(self) -> None:
        with isolated_git_project() as (project, archive):
            report = evaluate_git_hook(archive, project, "pre-rebase", "")
            self.assertEqual(report["verdict"], "allow")

    def test_post_checkout_detects_pinned_tamper_but_states_it_cannot_undo(self) -> None:
        with isolated_git_project() as (project, archive):
            from godmode_runtime.godmode_sentinel import pin_evaluator

            evaluator = project / "evaluator.py"
            evaluator.write_text("def score(): return 1\n", encoding="utf-8")
            _git("add", "evaluator.py", cwd=project)
            _git("commit", "-q", "-m", "add evaluator", cwd=project)
            pin_evaluator(archive, project, "evaluator.py")

            # Simulate a checkout that changed the pinned file's content.
            evaluator.write_text("def score(): return 999\n", encoding="utf-8")

            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "post-checkout", "")
            self.assertEqual(report["verdict"], "block")
            self.assertEqual(report["tampered_pinned_count"], 1)
            self.assertIn("cannot undo", report["detects"])

    def test_post_checkout_allows_when_pinned_content_matches(self) -> None:
        with isolated_git_project() as (project, archive):
            from godmode_runtime.godmode_sentinel import pin_evaluator

            evaluator = project / "evaluator.py"
            evaluator.write_text("def score(): return 1\n", encoding="utf-8")
            _git("add", "evaluator.py", cwd=project)
            _git("commit", "-q", "-m", "add evaluator", cwd=project)
            pin_evaluator(archive, project, "evaluator.py")
            _declare_policy(project)
            report = evaluate_git_hook(archive, project, "post-checkout", "")
            self.assertEqual(report["verdict"], "allow")


class VerifyTests(unittest.TestCase):
    def test_verify_writes_a_host_git_proof_and_flips_interception_state_hard(self) -> None:
        with isolated_git_project() as (project, archive):
            self.assertEqual(interception_state(archive, "git"), "UNAVAILABLE")
            report = run_git_verify(archive)
            self.assertEqual(report["state"], "HARD")
            self.assertEqual(report["host"], "git")
            self.assertEqual(interception_state(archive, "git"), "HARD")


class GuardCliGitHookTests(unittest.TestCase):
    """The console wiring itself: `godmode guard --git-hook` and
    `godmode hooks install|status|verify --git`, exercised as real
    subprocesses the way an installed hook script actually calls them."""

    def test_guard_requires_operation_or_git_hook(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            completed = _cli(project, project / "state", "guard")
            self.assertNotEqual(completed.returncode, 0)

    def test_cli_git_hook_status_install_uninstall_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "proj"
            state_home = base / "state"
            _init_repo(project)
            init = _cli(project, state_home, "init")
            self.assertEqual(init.returncode, 0, init.stderr)

            refused = _cli(project, state_home, "hooks", "install", "--git")
            self.assertEqual(refused.returncode, 1)
            self.assertFalse(json.loads(refused.stdout)["declared"])

            _declare_policy(project)
            installed = _cli(project, state_home, "hooks", "install", "--git")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            payload = json.loads(installed.stdout)
            self.assertEqual(set(payload["installed"]), set(HOOK_NAMES))

            status = _cli(project, state_home, "hooks", "status", "--git")
            self.assertEqual(status.returncode, 0)
            status_payload = json.loads(status.stdout)
            self.assertTrue(status_payload["declared"])
            for name in HOOK_NAMES:
                self.assertEqual(status_payload["hooks"][name]["state"], "godmode")

            uninstalled = _cli(project, state_home, "hooks", "install", "--git", "--uninstall")
            self.assertEqual(uninstalled.returncode, 0)
            for name in HOOK_NAMES:
                self.assertFalse((project / ".git" / "hooks" / name).exists())

    def test_cli_guard_git_hook_pre_push_allow_with_empty_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "proj"
            state_home = base / "state"
            _init_repo(project)
            _cli(project, state_home, "init")
            _declare_policy(project)
            result = _cli(project, state_home, "guard", "--git-hook", "pre-push",
                          input_text="")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "allow")

    def test_cli_verify_git_writes_proof(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "proj"
            state_home = base / "state"
            _init_repo(project)
            _cli(project, state_home, "init")
            result = _cli(project, state_home, "hooks", "verify", "--git")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "HARD")
            self.assertEqual(payload["host"], "git")


if __name__ == "__main__":
    unittest.main()
