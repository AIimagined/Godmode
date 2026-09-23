"""A project with no Godmode state costs its hooks next to nothing.

Field report 2026-09-23: in a project nobody ran `godmode init` in, a
host's own diagnostics recorded the pre-tool gate timing out on more than
half its calls and Stop/SessionEnd running past their timeouts, and advised
uninstalling the plugin. Every event loaded the archive, the classifier and
the anchor before discovering there was nothing to govern.

Pinned here:

1. Every session-hook event, run in an uninitialized directory (plain and
   git), exits 0, prints nothing, writes nothing, and never imports the
   runtime - read from `-X importtime`, the interpreter's own list.
2. The one message that path still gives - the not-initialized notice a
   Claude session hears at its start - is the full hook's own.
3. `godmode_initstate` finds an archive exactly where `resolve_anchor`
   puts one (plain directory, git checkout, subdirectory, linked worktree,
   and an archive stranded by a later `git init`), so the short-circuit can
   never answer "absent" for a project the full hook would govern.
4. Anything the early path is unsure of - a malformed pre-action payload -
   still reaches the full hook, which still refuses it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS = PLUGIN_ROOT / "hooks"
SESSION_HOOK = HOOKS / "godmode_session_hook.py"
# What the launcher runs for every session event (see run-hook.cmd).
SESSION_ENTRY = HOOKS / "godmode_session_entry.py"
SCRIPTS = (SESSION_ENTRY, SESSION_HOOK)
for _path in (PLUGIN_ROOT / "scripts", HOOKS, Path(__file__).parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import godmode_initstate as initstate  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from _host_env import scrubbed_env  # noqa: E402

EVENTS = ("stop", "session-start", "pre-compact", "session-end",
          "pre-action", "user-prompt", "subagent-stop")
HOST_EVENT = {"stop": "Stop", "session-start": "SessionStart", "pre-compact": "PreCompact",
              "session-end": "SessionEnd", "pre-action": "PreToolUse",
              "user-prompt": "UserPromptSubmit", "subagent-stop": "SubagentStop"}
# The modules the early path must never reach: the runtime package and
# everything heavy it pulls in.
FORBIDDEN_PREFIXES = ("godmode_runtime", "pathlib", "argparse", "hashlib", "subprocess")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env=scrubbed_env(GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
                                    GIT_AUTHOR_EMAIL="t@example.invalid",
                                    GIT_COMMITTER_NAME="t",
                                    GIT_COMMITTER_EMAIL="t@example.invalid"))


def _payload(event: str, cwd: Path) -> dict:
    body = {"session_id": "S-uninit", "transcript_path": str(cwd / "t.jsonl"),
            "cwd": str(cwd), "permission_mode": "default",
            "hook_event_name": HOST_EVENT[event]}
    if event == "pre-action":
        body.update(tool_name="Write", tool_input={"file_path": str(cwd / "x.txt"), "content": "x"})
    if event == "session-end":
        body["reason"] = "exit"
    return body


def _run_hook(event: str, payload: bytes, home: Path, cwd: Path,
              script: Path = SESSION_ENTRY) -> tuple[subprocess.CompletedProcess, set[str]]:
    done = subprocess.run(
        [sys.executable, "-X", "importtime", "-I", "-B", str(script), event],
        input=payload, capture_output=True, timeout=120, cwd=str(cwd),
        env=scrubbed_env(GODMODE_STATE_HOME=str(home)))
    imported = {line.rsplit("|", 1)[1].strip()
                for line in done.stderr.decode("utf-8", "replace").splitlines()
                if line.startswith("import time:") and "|" in line}
    return done, imported


def _tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


class UninitializedEarlyExitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="gm-uninit-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.home = self.base / "state"

    def _assert_silent_and_light(self, project: Path) -> None:
        for script in SCRIPTS:
            for event in EVENTS:
                with self.subTest(event=event, project=project.name, script=script.name):
                    body = _payload(event, project)
                    if event == "session-start":
                        body["hook_event_name"] = "startup"  # not a Claude session: silent too
                    done, imported = _run_hook(event, json.dumps(body).encode(), self.home,
                                               project, script)
                    self.assertEqual(done.returncode, 0, done.stderr[-600:])
                    self.assertEqual(done.stdout, b"")
                    heavy = sorted(m for m in imported if m.startswith(FORBIDDEN_PREFIXES)
                                   or m.startswith("godmode_") and m not in (
                                       "godmode_stdin", "godmode_initstate"))
                    self.assertEqual(heavy, [], "the early path imported the runtime")
                    self.assertIn("godmode_initstate", imported, "the early path did not run")
        self.assertEqual(_tree(self.home), [], "an uninitialized project wrote state")

    def test_a_plain_directory_costs_nothing_for_every_event(self) -> None:
        project = self.base / "plain"
        project.mkdir()
        self._assert_silent_and_light(project)

    def test_a_git_checkout_costs_nothing_for_every_event(self) -> None:
        project = self.base / "repo"
        project.mkdir()
        _git("init", "-q", cwd=project)
        (project / "sub").mkdir()
        self._assert_silent_and_light(project / "sub")

    def test_a_claude_session_still_hears_the_notice_at_its_start(self) -> None:
        project = self.base / "plain"
        project.mkdir()
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                done, imported = _run_hook("session-start",
                                           json.dumps(_payload("session-start", project)).encode(),
                                           self.home, project, script)
                self.assertEqual(done.returncode, 0, done.stderr[-600:])
                context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
                self.assertIn("NOT initialized", context)
                self.assertIn("godmode init", context)
                self.assertFalse(any(m.startswith("godmode_runtime") for m in imported))

    def test_a_malformed_pre_action_still_reaches_the_full_hook_and_is_refused(self) -> None:
        project = self.base / "plain"
        project.mkdir()
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                done, imported = _run_hook("pre-action", b"{not json", self.home, project, script)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr[-600:])
                self.assertTrue(any(m.startswith("godmode_runtime") for m in imported))

    def test_an_initialized_project_takes_the_full_path(self) -> None:
        project = self.base / "governed"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(self.home)}):
            from godmode_runtime.godmode_chronicle import Chronicle
            Chronicle(resolve_anchor(project)).initialize()
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                done, imported = _run_hook("session-end",
                                           json.dumps(_payload("session-end", project)).encode(),
                                           self.home, project, script)
                self.assertEqual(done.returncode, 0, done.stderr[-600:])
                last = json.loads(done.stdout.decode("utf-8").splitlines()[-1])
                self.assertTrue(last.get("stored"), done.stdout)
                self.assertIn("godmode_runtime.godmode_chronicle", imported)
                # Entered through the front door, the hook still writes as
                # the hook process (its own argv[0] and __main__.__file__).
                with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(self.home)}):
                    from godmode_runtime.godmode_chronicle import Chronicle
                    records = Chronicle(resolve_anchor(project)).read_events(verify=False)
                self.assertEqual(records[-1].get("writer"), "hook", records[-1])


class SessionEndStaysInsideTheExitBudgetTests(unittest.TestCase):
    """SessionEnd measures a small transcript at once and parks a large one
    for the next session start, which measures it (field report
    2026-09-23: the host cancels SessionEnd work still running at exit)."""

    def test_a_large_transcript_is_measured_at_the_next_session_start(self) -> None:
        base = Path(tempfile.mkdtemp(prefix="gm-defer-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        project, home = base / "p", base / "state"
        project.mkdir()
        transcript = base / "t.jsonl"
        line = json.dumps({"type": "user", "message": {"role": "user", "content": "x" * 900}})
        transcript.write_text((line + "\n") * 1400, encoding="utf-8")  # a little over 1 MiB
        from godmode_runtime.godmode_chronicle import Chronicle
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(home)}):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
        sidecar = Path(archive.root) / "godmode-deferred-measurements.json"

        def metrics() -> list:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(home)}):
                return [r for r in Chronicle(resolve_anchor(project)).read_events(verify=False)
                        if r.get("kind") == "metric"]

        end = _payload("session-end", project)
        end["transcript_path"] = str(transcript)
        done, _ = _run_hook("session-end", json.dumps(end).encode(), home, project)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        self.assertEqual(metrics(), [], "a large transcript was measured inside SessionEnd")
        self.assertTrue(sidecar.is_file())

        done, _ = _run_hook("session-start", json.dumps(_payload("session-start", project)).encode(),
                            home, project)
        self.assertEqual(done.returncode, 0, done.stderr[-600:])
        self.assertEqual(len(metrics()), 1)
        self.assertFalse(sidecar.exists())


class NonGitAnchorSpawnsNoGitTests(unittest.TestCase):
    def test_a_directory_with_no_git_above_it_resolves_without_git(self) -> None:
        from godmode_runtime import godmode_anchor
        base = Path(tempfile.mkdtemp(prefix="gm-nogit-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        if godmode_anchor.git_marker_above(base):
            self.skipTest("the temp directory sits inside a repository on this machine")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}):
            with mock.patch.object(godmode_anchor, "run_git") as spawned:
                anchor = godmode_anchor.resolve_anchor(base)
        spawned.assert_not_called()
        self.assertFalse(anchor.is_git)


class InitStateMatchesResolveAnchorTests(unittest.TestCase):
    """The helper answers ABSENT only where `resolve_anchor` would find no
    archive, and PRESENT the moment one exists where it looks."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="gm-initstate-"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        patcher = mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(self.base / "state")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_tracks_archive(self, requested: Path) -> None:
        state, root = initstate.project_state(str(requested))
        anchor = resolve_anchor(requested)
        self.assertEqual(state, initstate.ABSENT)
        self.assertEqual(root, anchor.project_root)
        Path(anchor.archive_root).mkdir(parents=True)
        self.assertEqual(initstate.project_state(str(requested))[0], initstate.PRESENT)
        shutil.rmtree(anchor.archive_root)
        self.assertEqual(initstate.project_state(str(requested))[0], initstate.ABSENT)

    def test_application_home_matches(self) -> None:
        from godmode_runtime.godmode_anchor import application_home
        self.assertEqual(initstate.application_home(), str(application_home()))

    def test_a_plain_directory(self) -> None:
        project = self.base / "plain"
        project.mkdir()
        resolve_anchor(project)  # creates the device salt, as any real use does
        self._assert_tracks_archive(project)

    def test_a_git_checkout_and_its_subdirectory(self) -> None:
        project = self.base / "repo"
        (project / "a" / "b").mkdir(parents=True)
        _git("init", "-q", cwd=project)
        self._assert_tracks_archive(project)
        self._assert_tracks_archive(project / "a" / "b")

    def test_a_linked_worktree(self) -> None:
        project = self.base / "repo"
        project.mkdir()
        _git("init", "-q", cwd=project)
        _git("commit", "-q", "--allow-empty", "-m", "root", cwd=project)
        _git("worktree", "add", "-q", str(self.base / "linked"), cwd=project)
        self._assert_tracks_archive(self.base / "linked")

    def test_an_archive_stranded_by_a_later_git_init_is_present(self) -> None:
        project = self.base / "became-git"
        project.mkdir()
        stranded = Path(resolve_anchor(project).archive_root)
        stranded.mkdir(parents=True)
        _git("init", "-q", cwd=project)
        self.assertEqual(initstate.project_state(str(project))[0], initstate.PRESENT)

    def test_doubt_is_unknown(self) -> None:
        self.assertEqual(initstate.project_state(str(self.base / "missing"))[0], initstate.UNKNOWN)
        project = self.base / "broken"
        project.mkdir()
        (project / ".git").write_text("gitdir: ../nowhere\n", encoding="utf-8")
        self.assertEqual(initstate.project_state(str(project))[0], initstate.UNKNOWN)
        with mock.patch.dict(os.environ, {"GIT_DIR": str(project)}):
            self.assertEqual(initstate.project_state(str(self.base))[0], initstate.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
