"""The gate driven the way the host drives it.

Four defects reached a released build this session, and every one was invisible
to the suite for the same reason: the tests fed `classify_action` operation
strings written by hand, and the host sends something else. PowerShell was
denied because the corpus was POSIX. Shell loops were denied because the corpus
had none. Every file edit was denied because the corpus used relative paths
while the host always sends an absolute `file_path` — an allowance that read as
correct and could never fire.

Testing one layer below the boundary is how all four passed. This file crosses
it: a real PreToolUse payload goes into the hook process and the decision comes
back out, so a case can only pass here by working the way it will work in a
session.

An empty response is an allow — the hook stays silent unless it has something
to say.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"

# (label, tool, tool_input) drawn from what a working session actually issues.
MUST_ALLOW = (
    ("edit a project file", "Edit",
     {"file_path": str(PLUGIN_ROOT / "tests" / "test_hook_end_to_end.py")}),
    ("write a project file", "Write", {"file_path": str(PLUGIN_ROOT / "notes.md")}),
    ("plain listing", "Bash", {"command": "ls"}),
    ("piped compound read", "Bash",
     {"command": "ls scripts | head -3 && git status --short"}),
    ("shell loop", "Bash", {"command": "for f in *.md; do wc -l $f; done"}),
    ("conditional", "Bash", {"command": "if [ -f README.md ]; then cat README.md; fi"}),
    ("powershell read", "PowerShell",
     {"command": "Get-ChildItem | Select-Object -ExpandProperty Name"}),
    ("run the suite", "Bash", {"command": "python -m unittest discover -s tests"}),
    ("read a file", "Read", {"file_path": str(PLUGIN_ROOT / "README.md")}),
)

MUST_DENY = (
    ("edit inside the git directory", "Edit", {"file_path": str(PLUGIN_ROOT / ".git" / "config")}),
    ("write outside the tree", "Write", {"file_path": str(PLUGIN_ROOT.parent / "outside.txt")}),
    ("force push", "Bash", {"command": "git push --force origin main"}),
    ("recursive delete", "Bash", {"command": "rm -rf build"}),
    ("a delete inside a loop", "Bash", {"command": "for f in *; do rm -rf $f; done"}),
    ("safe head, dangerous tail", "Bash", {"command": "git status && git push origin main"}),
)


def _decide(tool: str, tool_input: dict) -> tuple[str, str]:
    """Run the hook as the host runs it and return (decision, reason)."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": str(PLUGIN_ROOT),
    }
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(PLUGIN_ROOT)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(PLUGIN_ROOT),
    )
    body = (done.stdout or "").strip()
    if not body:
        return "allow", ""
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return (str(specific.get("permissionDecision", "?")),
            str(specific.get("permissionDecisionReason", "")))


class WorkingSessionTests(unittest.TestCase):
    def test_the_host_can_still_do_ordinary_work(self) -> None:
        blocked = [label for label, tool, payload in MUST_ALLOW
                   if _decide(tool, payload)[0] != "allow"]
        self.assertEqual(blocked, [], f"the gate would stop a working session: {blocked}")


class ProtectedOperationTests(unittest.TestCase):
    def test_protected_operations_are_still_refused(self) -> None:
        allowed = [label for label, tool, payload in MUST_DENY
                   if _decide(tool, payload)[0] != "deny"]
        self.assertEqual(allowed, [], f"the gate would permit a mutation: {allowed}")


class RefusalMessageTests(unittest.TestCase):
    """A refusal has to name a remedy the reader can perform.

    It used to say a one-use capability was required. No host tool call carries
    a field a capability could travel in, so that remedy did not exist and the
    message sent the operator looking for a token they had no way to supply.
    """

    def test_the_refusal_does_not_promise_an_unreachable_capability(self) -> None:
        _decision, reason = _decide("Bash", {"command": "rm -rf build"})
        self.assertNotIn("requires an exact one-use", reason)

    def test_the_refusal_names_what_actually_unblocks_it(self) -> None:
        _decision, reason = _decide("Bash", {"command": "rm -rf build"})
        self.assertTrue(reason, "a denial with no reason is not actionable")
        self.assertRegex(reason, r"(?i)yourself|narrower|disable")

    def test_the_refusal_names_the_category_that_triggered_it(self) -> None:
        _decision, reason = _decide("Bash", {"command": "git push --force origin main"})
        self.assertIn("git-history-or-remote", reason)


if __name__ == "__main__":
    unittest.main()
