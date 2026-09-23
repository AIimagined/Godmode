"""`ask_only` at the pre-tool boundary, run exactly as the host runs it.

A category outside the list at R2/R3 is allowed with an `action` record
naming the silence; a listed category still asks; R4 still asks and R5
still denies whatever the list says.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_sentinel import POLICY_FILENAME  # noqa: E402
from _host_env import scrubbed_environment  # noqa: E402

_HOST_ENV = None


def setUpModule() -> None:
    """Fix round 1 (NS-10k, task-14-review.md B1): `_decide`/`_decide_reason`
    spread `os.environ` into the hook subprocess, and a CI runner's own `CI`
    silently flips `test_r4_still_asks_whatever_the_list_says` (and every
    other bare-mode assertion in this module) onto the unattended row - the
    exact defect that read green locally and red only in Actions. Every
    test here now runs from a scrubbed, pinned-attended environment."""
    global _HOST_ENV
    _HOST_ENV = scrubbed_environment()
    _HOST_ENV.start()


def tearDownModule() -> None:
    if _HOST_ENV is not None:
        _HOST_ENV.stop()


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-askhook-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        (root / "notes.md").write_text("x\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.append("session", "open", {"status": "open"})
            # `git checkout -- <file>` classifies as git-history-or-remote (R3),
            # so that is the listed category the second test exercises.
            (root / POLICY_FILENAME).write_text(
                json.dumps({"ask_only": ["worktree-discard", "git-history-or-remote"]}),
                encoding="utf-8")
            yield root, archive


def _decide(project: Path, tool: str, tool_input: dict, permission_mode: str | None = None) -> str:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input, "cwd": str(project)}
    if permission_mode:
        payload["permission_mode"] = permission_mode
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        env={**os.environ, "GODMODE_STATE_HOME": os.environ["GODMODE_STATE_HOME"]},
    )
    body = (done.stdout or "").strip()
    if not body:
        return "allow"
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return str(specific.get("permissionDecision", "allow"))


def _decide_reason(project: Path, tool: str, tool_input: dict,
                    permission_mode: str) -> tuple[str, str]:
    """Same call as `_decide`, but returning the reason text too - needed
    only by the Task 6 (G-2) test below, which pins the auto-mode refusal's
    own wording rather than just its decision."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input, "cwd": str(project),
               "permission_mode": permission_mode}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        env={**os.environ, "GODMODE_STATE_HOME": os.environ["GODMODE_STATE_HOME"]},
    )
    body = (done.stdout or "").strip()
    if not body:
        return "allow", ""
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return (str(specific.get("permissionDecision", "allow")),
            str(specific.get("permissionDecisionReason", "")))


class NoHumanAskModeTests(unittest.TestCase):
    """2026-09-10: a hook's ask in auto mode is answered by the host, not a
    person; three releases pushed with no password. A would-ask folds to
    deny in auto, dontAsk, and bypassPermissions, with the stage remedy."""

    def test_a_push_is_denied_not_asked_when_no_human_answers(self) -> None:
        with _project() as (root, archive):
            for mode in ("auto", "dontAsk", "bypassPermissions"):
                with self.subTest(mode=mode):
                    self.assertEqual(_decide(root, "Bash", {"command": "git push origin main"}, permission_mode=mode),
                                     "deny")
            refusals = [r for r in archive.read_events(verify=False) if r["kind"] == "refusal"]
            self.assertGreaterEqual(len(refusals), 3)

    def test_a_push_still_asks_when_a_human_answers(self) -> None:
        with _project() as (root, archive):
            for mode in ("default", "plan", "acceptEdits", None):
                with self.subTest(mode=mode):
                    self.assertEqual(_decide(root, "Bash", {"command": "git push origin main"}, permission_mode=mode),
                                     "ask")
            asked = [r for r in archive.read_events(verify=False)
                     if r["kind"] == "action" and r["subject"] == "gate-asked"]
            self.assertTrue(asked)
            self.assertIn(asked[-1]["data"].get("permission_mode"), ("acceptEdits", "unknown", "default", "plan"))

    def test_the_auto_mode_refusal_names_a_command_that_actually_resolves(self) -> None:
        # Task 6 (G-2): the observed refusal named `godmode authorize stage
        # --from-last-refusal` and told the operator to type it "with a
        # leading '!'" - neither works where it's read (bare `godmode` is
        # not on PATH; a bare `!` is a PowerShell parser error). The rest
        # of the sentence - "the host is in <mode> mode..." - is unchanged.
        with _project() as (root, _archive):
            decision, reason = _decide_reason(
                root, "Bash", {"command": "git push origin main"}, "auto")
        self.assertEqual(decision, "deny", reason)
        self.assertIn("the host is in auto mode", reason)
        launcher = (PLUGIN_ROOT / "bin" / "godmode").as_posix()
        self.assertIn(f'! "{launcher}" authorize stage --from-last-refusal', reason)
        cmd_launcher = PLUGIN_ROOT / "bin" / "godmode.cmd"
        if os.name == "nt":
            self.assertIn(f'& "{cmd_launcher}" authorize stage --from-last-refusal', reason)


class AskOnlyHookTests(unittest.TestCase):
    def test_an_unlisted_r2_ask_is_allowed_and_recorded_as_silenced(self) -> None:
        with _project() as (root, archive):
            decision = _decide(root, "Bash", {"command": "node -e \"require('fs').writeFileSync('x', '1')\""})
            silenced = [r for r in archive.read_events(verify=False)
                        if r.get("kind") == "action"
                        and (r.get("data") or {}).get("silenced_by") == "ask_only"]
        self.assertEqual(decision, "allow")
        self.assertEqual(len(silenced), 1, "the silence must leave a record")
        self.assertEqual(silenced[0]["data"]["category"], "interpreter-opaque-inline")

    def test_a_listed_category_still_asks(self) -> None:
        with _project() as (root, _archive):
            decision = _decide(root, "Bash", {"command": "git checkout -- notes.md"})
        self.assertEqual(decision, "ask")

    def test_r4_still_asks_whatever_the_list_says(self) -> None:
        with _project() as (root, _archive):
            decision = _decide(root, "Bash", {"command": "rm -rf build"})
        self.assertEqual(decision, "ask")


if __name__ == "__main__":
    unittest.main()
