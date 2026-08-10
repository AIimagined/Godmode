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
    # Everything v0.2.5 unblocked, asserted where the host will hit it rather
    # than only against the classifier. Each of these was refused by a shipped
    # build while the suite of the day reported green.
    ("stage changes", "Bash", {"command": "git add -A"}),
    ("commit", "Bash", {"command": "git commit -m 'a message'"}),
    ("name a protected command in an argument", "Bash",
     {"command": 'grep "git push" CHANGELOG.md'}),
    ("input redirect", "Bash", {"command": "wc -l < README.md"}),
    ("descriptor duplication", "Bash", {"command": "python -m unittest discover -s tests 2>&1"}),
    ("substitution over a read", "Bash", {"command": "echo $(git rev-parse HEAD)"}),
    ("redirect inside the tree", "Bash", {"command": "echo hello > scratch.txt"}),
)

MUST_DENY = (
    ("edit inside the git directory", "Edit", {"file_path": str(PLUGIN_ROOT / ".git" / "config")}),
    ("write outside the tree", "Write", {"file_path": str(PLUGIN_ROOT.parent / "outside.txt")}),
    ("force push", "Bash", {"command": "git push --force origin main"}),
    ("recursive delete", "Bash", {"command": "rm -rf build"}),
    ("a delete inside a loop", "Bash", {"command": "for f in *; do rm -rf $f; done"}),
    ("safe head, dangerous tail", "Bash", {"command": "git status && git push origin main"}),
    # The line each v0.2.5 relaxation stopped at.
    ("amend rewrites history", "Bash", {"command": "git commit --amend"}),
    ("a quoted script is still unrecognised", "Bash", {"command": 'bash -c "rm -rf /"'}),
    ("a substitution that destroys", "Bash", {"command": "echo $(rm -rf build)"}),
    ("a redirect out of the tree", "Bash", {"command": "echo x > ../outside.txt"}),
    ("discarding working changes", "Bash", {"command": "git checkout -- ."}),
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
    def test_protected_operations_never_proceed_silently(self) -> None:
        """`deny` or `ask` — never `allow`.

        The gate emitted only `deny`, for everything protected, on the
        reasoning that a host tool call carries no field a capability could
        travel in and so there is no in-session approval. The premise is true
        and the conclusion is not: the host takes `ask`, and asking *is* an
        in-session approval. What must hold is that a protected operation never
        runs without somebody saying so — not that it always stops dead.
        """
        proceeded = [label for label, tool, payload in MUST_DENY
                     if _decide(tool, payload)[0] not in {"deny", "ask"}]
        self.assertEqual(proceeded, [],
                         f"the gate would permit a mutation: {proceeded}")

    def test_the_irreversible_ones_still_stop_dead(self) -> None:
        """R5 is the tier for damage no later command undoes, and a one-key
        confirmation is the wrong shape for it."""
        for label, tool, payload in (
            ("force push", "Bash", {"command": "git push --force origin main"}),
            ("hard reset", "Bash", {"command": "git reset --hard HEAD~3"}),
            ("drop a table", "Bash", {"command": "DROP TABLE orders"}),
            # `psql -c 'DROP TABLE orders'` is deliberately absent: its SQL is
            # quoted, quoted spans are blanked before the patterns run, and it
            # classifies as an unknown mutation rather than a database one. It
            # is still stopped — as a question rather than a refusal, with the
            # whole command shown — which is the honest limit of reading a
            # shell line without executing it.
        ):
            with self.subTest(label=label):
                decision, _reason = _decide(tool, payload)
                self.assertEqual(decision, "deny", label)


class RefusalMessageTests(unittest.TestCase):
    """A refusal has to name a remedy the reader can perform.

    It used to say a one-use capability was required. No host tool call carries
    a field a capability could travel in, so that remedy did not exist and the
    message sent the operator looking for a token they had no way to supply.
    """

    def test_the_refusal_does_not_promise_an_unreachable_capability(self) -> None:
        _decision, reason = _decide("Bash", {"command": "rm -rf build"})
        self.assertNotIn("requires an exact one-use", reason)

    def test_a_question_reads_as_a_question(self) -> None:
        """`rm -rf build` is protected but recoverable, so it asks. The text
        beside the command should say what is at stake, not what the tool has
        decided on the operator's behalf."""
        decision, reason = _decide("Bash", {"command": "rm -rf build"})
        self.assertEqual(decision, "ask")
        self.assertTrue(reason, "a prompt with no reason is not actionable")
        self.assertIn("Approve to run it", reason)
        self.assertIn("filesystem-mutation", reason)

    def test_an_outright_refusal_still_names_what_unblocks_it(self) -> None:
        decision, reason = _decide(
            "Bash", {"command": "git push --force origin main"})
        self.assertEqual(decision, "deny")
        self.assertRegex(reason, r"(?i)yourself|narrower|authorize stage")

    def test_the_refusal_names_the_category_that_triggered_it(self) -> None:
        _decision, reason = _decide("Bash", {"command": "git push --force origin main"})
        self.assertIn("git-history-or-remote", reason)

    def test_the_refusal_names_the_remedy_the_hook_actually_honours(self) -> None:
        """Twenty lines above the message, a staged capability is consumed and
        the call proceeds. The message was written before that shipped and
        still said no in-session approval existed - denying its own remedy."""
        _decision, reason = _decide(
            "Bash", {"command": "git push --force origin main"})
        self.assertIn("authorize stage", reason)
        self.assertIn("git push --force origin main", reason,
                      "the operator has to retype the command exactly")

    def test_the_refusal_does_not_recommend_removing_the_guard(self) -> None:
        """Offering that as a remedy is the likeliest advice to be taken and
        the worst, and it was offered because the real remedy went unmentioned."""
        _decision, reason = _decide("Bash", {"command": "rm -rf build"})
        self.assertNotIn("disable the plugin", reason)


if __name__ == "__main__":
    unittest.main()
