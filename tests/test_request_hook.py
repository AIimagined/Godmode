"""The hook that records a request, run the way the host runs it.

The module can be right while nothing calls it. That is not hypothetical here:
obligation retirement worked and changed nothing for a release, because the
reviewer was handed a filtered record list. So this drives the real entry
point over a real archive in a temporary project, and asserts the record
landed - not that a function returns the right value.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_requests import review_requests  # noqa: E402


class RequestHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._holder = tempfile.TemporaryDirectory(prefix="godmode-prompt-hook-")
        self.project = Path(self._holder.name)
        self.state = self.project / "state"
        for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                        ["config", "user.name", "d"]):
            subprocess.run(["git", *command], cwd=self.project, capture_output=True)
        (self.project / "README.md").write_text("# t\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"],
                       cwd=self.project, capture_output=True)
        self._environment = dict(os.environ)
        os.environ["GODMODE_STATE_HOME"] = str(self.state)
        done = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
             "--project", str(self.project), "init"],
            capture_output=True, text=True, env=os.environ)
        # Asserted rather than assumed: the first version passed a flag `init`
        # does not take, argparse refused it, and every test below failed
        # against an uninitialised project for a reason none of them named.
        assert done.returncode == 0, f"init failed: {done.stderr or done.stdout}"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._environment)
        self._holder.cleanup()

    def _submit(self, prompt: str, tools_in_flight: int = 0) -> subprocess.CompletedProcess:
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": prompt,
                   "cwd": str(self.project), "session_id": "S-test",
                   "tools_in_flight": tools_in_flight}
        return subprocess.run(
            [sys.executable, str(HOOK), "user-prompt", "--project", str(self.project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            cwd=str(self.project), env=os.environ)

    def _requests(self) -> list[dict]:
        archive = Chronicle(resolve_anchor(str(self.project)))
        return [r for r in archive.read_events() if r.get("kind") == "request"]

    def test_the_hook_records_the_prompt(self) -> None:
        self._submit("check the marketplace documentation")
        records = self._requests()
        self.assertEqual(len(records), 1)
        self.assertIn("marketplace", records[0]["subject"])

    def test_the_hook_records_that_work_was_interrupted(self) -> None:
        self._submit("also check the readme", tools_in_flight=2)
        self.assertTrue(self._requests()[0]["data"]["interrupted_work"])

    def test_the_hook_is_silent(self) -> None:
        """It adds no context and blocks nothing. A ledger of asks that
        announced itself would be one more thing to answer beside the work
        already running."""
        done = self._submit("do the thing")
        self.assertEqual(done.returncode, 0)
        self.assertEqual((done.stdout or "").strip(), "")

    def test_a_repeated_prompt_records_once(self) -> None:
        self._submit("do the thing")
        self._submit("Do  the   thing")
        self.assertEqual(len(self._requests()), 1)

    def test_a_secret_shaped_prompt_does_not_break_the_turn(self) -> None:
        """The archive refuses it, and the operator's turn continues anyway."""
        done = self._submit("use this token " + "ghp_" + "a" * 32)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self._requests(), [])

    def test_the_recorded_request_reaches_the_reviewer(self) -> None:
        """The wiring, not the mechanism. Retirement was built correctly once
        and starved by a filtered record list, so the path from hook to review
        is asserted end to end."""
        self._submit("look at the marketplace docs", tools_in_flight=1)
        archive = Chronicle(resolve_anchor(str(self.project)))
        report = review_requests(archive.read_events())
        self.assertEqual(report["verdict"], "open-requests")
        self.assertEqual(report["findings"][0]["code"], "request-interrupted-work")

    def test_checkpoint_review_surfaces_it(self) -> None:
        self._submit("look at the marketplace docs", tools_in_flight=1)
        done = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "scripts" / "godmode.py"),
             "--project", str(self.project), "checkpoint", "--review"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, env=os.environ)
        report = json.loads(done.stdout)
        self.assertEqual(report["requests"]["verdict"], "open-requests")


if __name__ == "__main__":
    unittest.main()
