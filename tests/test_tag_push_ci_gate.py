"""A tag push is a release, and CI on the tagged commit is its proof.

0.3.20 (2026-09-08): main and the v0.3.20 tag were pushed on a local suite
that was green on one OS and one interpreter; the CI matrix then went red on
both Windows legs. The rule "CI green before the tag" lived in a maintainer
note, and nothing mechanical could refuse. This gate refuses a tag push
until a `ci` attestation with status `ran` names the tagged commit green, and
leaves the staged capability where it was so the retry after attesting
spends it.
"""
from __future__ import annotations

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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import open_session, record_step  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_release_gate import tag_push_refusal  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
PASSWORD = "correct-horse-local-only"  # godmode: allow-secret
TAG_PUSH = "git push origin refs/tags/v1.0.0"


def _git(project: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=project, capture_output=True,
                          text=True, timeout=60, check=True)
    return done.stdout.strip()


def _decide(project: Path, command: str) -> dict:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": str(project)}
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
    )
    body = (done.stdout or "").strip()
    if not body:
        return {"decision": "allow", "reason": ""}
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return {"decision": str(specific.get("permissionDecision") or "allow"),
            "reason": str(specific.get("permissionDecisionReason") or "")}


class TagPushCiGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        base = Path(self._temporary.name)
        self.project = base / "project"
        self.project.mkdir()
        self._env = mock.patch.dict(
            os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False)
        self._env.start()
        _git(self.project, "init", "-q")
        _git(self.project, "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-q", "--allow-empty", "-m", "first")
        _git(self.project, "tag", "v1.0.0")
        self.sha = _git(self.project, "rev-parse", "HEAD")
        self.archive = Chronicle(resolve_anchor(self.project))
        self.archive.initialize()
        self.broker = CapabilityBroker(self.archive)
        self.broker.configure(PASSWORD)
        self.session = open_session(self.archive, "test")

    def tearDown(self) -> None:
        self._env.stop()
        self._temporary.cleanup()

    def _attest_ci(self, sha: str) -> None:
        record_step(self.archive, self.session, "ci", "ran",
                    result=f"v1.0.0 {sha[:7]} green on every leg",
                    evidence=["https://example.invalid/actions/runs/1"],
                    project=self.project)

    def test_a_tag_push_without_a_ci_attestation_is_refused_naming_the_remedy(self) -> None:
        reason = tag_push_refusal(TAG_PUSH, self.project, self.archive)
        self.assertIsNotNone(reason)
        self.assertIn(self.sha[:7], reason)
        self.assertIn("godmode attest ci", reason)

    def test_a_ci_attestation_naming_the_tagged_commit_clears_the_push(self) -> None:
        self._attest_ci(self.sha)
        self.assertIsNone(tag_push_refusal(TAG_PUSH, self.project, self.archive))

    def test_a_ci_attestation_for_another_commit_does_not_count(self) -> None:
        self._attest_ci("0123456789abcdef0123456789abcdef01234567")
        self.assertIsNotNone(tag_push_refusal(TAG_PUSH, self.project, self.archive))

    def test_a_bare_tag_name_and_the_tag_keyword_are_tag_pushes(self) -> None:
        for form in ("git push origin v1.0.0", "git push origin tag v1.0.0",
                     "git push --tags origin"):
            self.assertIsNotNone(tag_push_refusal(form, self.project, self.archive), form)

    def test_a_ci_attestation_that_ran_red_does_not_count(self) -> None:
        record_step(self.archive, self.session, "ci", "ran",
                    result=f"v1.0.0 {self.sha[:7]} red on the Windows legs",
                    evidence=["https://example.invalid/actions/runs/2"], project=self.project)
        self.assertIsNotNone(tag_push_refusal(TAG_PUSH, self.project, self.archive))

    def test_a_branch_push_is_not_a_tag_push(self) -> None:
        self.assertIsNone(tag_push_refusal("git push origin HEAD:main", self.project, self.archive))

    def test_the_hook_refuses_a_staged_tag_push_and_keeps_the_capability(self) -> None:
        self.broker.stage(TAG_PUSH, PASSWORD, ttl_seconds=300)
        decision = _decide(self.project, TAG_PUSH)
        self.assertEqual(decision["decision"], "deny", decision)
        self.assertIn("godmode attest ci", decision["reason"])
        staged = json.loads(self.broker.path.read_text(encoding="utf-8")).get("staged", [])
        self.assertEqual(len(staged), 1, "the refusal must not spend the capability")
        self._attest_ci(self.sha)
        self.assertEqual(_decide(self.project, TAG_PUSH)["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
