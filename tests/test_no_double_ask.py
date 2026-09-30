"""One password, one answer: a spent staging is an explicit allow.

0.3.31 (2026-09-25..27): the operator staged a push with the password,
Godmode spent the staging and stayed silent, and the host's own permission
layer asked (or, in auto mode, refused) the same push again. The hook now
says `allow` out loud exactly when it spends a password-backed staging,
and only then - an ordinary allow stays silent, an ordinary ask stays an
ask, and auto mode still folds an unanswered ask to deny.
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
from godmode_runtime.godmode_hostevent import render_spent_allow  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from _host_env import scrubbed_environment  # noqa: E402

PASSWORD = "correct horse battery staple"
PUSH = "git push origin main"
_HOST_ENV = None


def setUpModule() -> None:
    global _HOST_ENV
    _HOST_ENV = scrubbed_environment()
    _HOST_ENV.start()


def tearDownModule() -> None:
    if _HOST_ENV is not None:
        _HOST_ENV.stop()


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-spentallow-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        (root / "notes.md").write_text("x\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.append("session", "open", {"status": "open"})
            yield root, archive


def _hook(project: Path, command: str, permission_mode: str) -> dict:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": str(project),
               "permission_mode": permission_mode}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
        env={**os.environ, "GODMODE_STATE_HOME": os.environ["GODMODE_STATE_HOME"]},
    )
    body = (done.stdout or "").strip()
    return json.loads(body) if body else {}


def _decision(body: dict) -> str | None:
    return (body.get("hookSpecificOutput") or {}).get("permissionDecision")


class SpentStagingTests(unittest.TestCase):
    def test_a_spent_staging_is_an_explicit_allow_in_auto_mode(self) -> None:
        with _project() as (root, archive):
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(PUSH, PASSWORD)
            body = _hook(root, PUSH, "auto")
            self.assertEqual(_decision(body), "allow", body)
            self.assertIn("staged capability", body["hookSpecificOutput"]["permissionDecisionReason"])
            # Spent: the same push without a fresh staging is refused again.
            self.assertEqual(_decision(_hook(root, PUSH, "auto")), "deny")

    def test_an_ordinary_ask_never_becomes_an_allow(self) -> None:
        with _project() as (root, _archive):
            body = _hook(root, PUSH, "default")
            self.assertEqual(_decision(body), "ask")
            self.assertIn("30 minutes", body["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertEqual(_decision(_hook(root, PUSH, "auto")), "deny")

    def test_a_local_reversible_ask_reaches_the_host_in_auto_mode(self) -> None:
        # R2 goes to the host's classifier as an ask; R3+ still folds to deny.
        with _project() as (root, _archive):
            self.assertEqual(_decision(_hook(root, "git commit -m x", "auto")), "ask")
            self.assertEqual(_decision(_hook(root, "git commit --amend", "auto")), "deny")

    def test_an_ordinary_allow_stays_silent(self) -> None:
        with _project() as (root, _archive):
            self.assertIsNone(_decision(_hook(root, "git status", "auto")))


class RenderSpentAllowTests(unittest.TestCase):
    def test_every_host_gets_its_own_allow_key(self) -> None:
        self.assertEqual(render_spent_allow("claude", "PreToolUse", "r")["hookSpecificOutput"]
                         ["permissionDecision"], "allow")
        self.assertEqual(render_spent_allow("antigravity", "PreToolUse", "r"),
                         {"decision": "allow", "reason": "r"})
        self.assertEqual(render_spent_allow("cursor", "PreToolUse", "r")["permission"], "allow")
        grok = render_spent_allow("grok", "PreToolUse", "r")
        self.assertEqual((grok["decision"], grok["hookSpecificOutput"]["permissionDecision"]),
                         ("allow", "allow"))


if __name__ == "__main__":
    unittest.main()
