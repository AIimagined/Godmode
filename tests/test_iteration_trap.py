"""Iteration controls (2026-09-10): a done claim with declared scope still
open is blocked with the list; a command that failed three times against
an unchanged tree is asked about before the fourth run; spend is measured
from the host transcript, not self-reported; a commit-score plateau and a
stall streak are named at Stop; a closed ask never rides the next prompt;
a pending list with numbers is not a claim.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_iteration as it  # noqa: E402
from godmode_runtime.godmode_requests import record_request  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


def _transcript(path: Path, entries: list[dict]) -> str:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return str(path)


def _bash(tool_id: str, command: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}]}}


def _result(tool_id: str, text: str) -> dict:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}


class OpenScopeTests(unittest.TestCase):
    def test_open_asks_steps_and_criteria_are_listed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "add the retry wrapper and its test", session="host-1")
            record_request(archive, "an ask from another session", session="host-2")
            archive.append("plan", "release 1.2", {"status": "active", "steps": [
                {"text": "wire the wrapper", "status": "done"}, {"text": "write the migration note", "status": "pending"}],
                "obligations": []}, evidence=[])
            archive.append("criterion", "criterion:retry-wrapper", {"task": "retry-wrapper", "text": "x", "late": False,
                                                                    "advisories": [], "session": "s"}, evidence=[])
            scope = it.open_scope(archive, "host-1")
            self.assertEqual(len(scope["asks"]), 1)
            self.assertIn("retry", scope["asks"][0])
            self.assertEqual(scope["steps"], ["plan step 'write the migration note' still pending"])
            self.assertEqual(len(scope["criteria"]), 1)
            self.assertIn("criterion:retry-wrapper", scope["criteria"][0])
            self.assertEqual(len(it.scope_items(scope)), 3)

    def test_a_done_reply_with_open_scope_is_blocked_by_the_hook(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "add the retry wrapper and its test", session="host-1")
            reason = hook._scope_block_reason(archive, "Everything is complete and deployed.", "host-1")
            self.assertIsNotNone(reason)
            self.assertIn("retry", reason)
            self.assertIn("ask:", reason)
            self.assertIsNone(hook._scope_block_reason(archive, "Still working on the wrapper.", "host-1"))
            self.assertIsNone(hook._scope_block_reason(archive, "Everything is complete.", "host-9"))


class MeasuredSpendTests(unittest.TestCase):
    def test_usage_is_summed_from_assistant_messages(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            path = _transcript(project / "t.jsonl", [
                {"type": "assistant", "message": {"usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 5, "cache_read_input_tokens": 900}}},
                {"type": "assistant", "message": {"usage": {"input_tokens": 50, "output_tokens": 30}}},
                {"type": "user", "message": {"content": "hi"}},
            ])
            spent = it.measured_spend(path)
            self.assertEqual(spent["tokens"], 205)
            self.assertEqual(spent["messages"], 2)
            self.assertEqual(spent["source"], "measured")
            self.assertEqual(it.measured_spend(None)["source"], "unavailable")


class RepeatFailureTests(unittest.TestCase):
    def test_three_failures_without_an_edit_are_counted(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            cmd = "python -m unittest tests.test_x"
            path = _transcript(project / "t.jsonl", [
                _bash("1", cmd), _result("1", "FAILED (failures=1)"),
                _bash("2", cmd), _result("2", "exit code 1"),
                _bash("3", cmd), _result("3", "Traceback (most recent call last):\nAssertionError"),
            ])
            seen = it.repeat_failures(path, cmd)
            self.assertEqual(seen["failures"], 3)
            self.assertFalse(seen["mutated_since_last_failure"])
            self.assertEqual(it.repeat_failures(path, "python -m unittest tests.test_y")["failures"], 0)

    def test_an_edit_between_failures_resets_the_repeat(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            cmd = "npm test"
            path = _transcript(project / "t.jsonl", [
                _bash("1", cmd), _result("1", "FAILED"),
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "e", "name": "Edit", "input": {"file_path": "x.py"}}]}},
                _bash("2", cmd), _result("2", "FAILED"),
            ])
            seen = it.repeat_failures(path, cmd)
            self.assertEqual(seen["failures"], 2)
            self.assertFalse(seen["mutated_since_last_failure"])
            self.assertIsNone(hook._repeat_failure_ask({"transcript_path": path}, cmd))
            path3 = _transcript(project / "t3.jsonl", [_bash(str(i), cmd) if i % 2 else _result(str(i - 1), "FAILED") for i in range(1, 8)])
            ask = hook._repeat_failure_ask({"transcript_path": path3}, cmd)
            self.assertIsNotNone(ask)
            self.assertIn("3 time", ask)


class PlateauTests(unittest.TestCase):
    def test_a_scored_branch_that_stopped_improving_is_a_plateau(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=project, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=project, check=True)
            for i, score in enumerate([0.5, 0.7, 0.9, 0.85, 0.88, 0.9, 0.89]):
                (project / "f.txt").write_text(str(i), encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=project, check=True)
                subprocess.run(["git", "commit", "-q", "-m", f"try {i} | score = {score}"], cwd=project, check=True)
            found = it.commit_score_plateau(project, window=12, streak=4)
            self.assertIsNotNone(found)
            self.assertEqual(found["best_before"], 0.9)
            self.assertEqual(found["streak"], 4)
            (project / "f.txt").write_text("win", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=project, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "breakthrough | score = 0.95"], cwd=project, check=True)
            self.assertIsNone(it.commit_score_plateau(project, window=12, streak=4))


class ClosedAskEchoTests(unittest.TestCase):
    def test_a_closed_ask_is_dropped_from_the_parked_echo(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_request(archive, "ship the retry wrapper", session="s")
            line = f"operator ask 'ship the retry wrapper' - close with `godmode remember --kind request --subject \"{record['subject']}\" --status closed` once served"
            kept = hook._still_open_obligation_lines(archive, [line, "standing duty: report - part of this task's definition of done"])
            self.assertEqual(len(kept), 2)
            archive.append("request", record["subject"], {"digest": record["data"]["digest"], "status": "closed", "value": "done"}, evidence=[])
            kept = hook._still_open_obligation_lines(archive, [line, "standing duty: report - part of this task's definition of done"])
            self.assertEqual(kept, ["standing duty: report - part of this task's definition of done"])


class PendingListTests(unittest.TestCase):
    def test_a_pending_list_with_numbers_is_not_a_claim(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(hook._unrecorded_claims(archive, "Pending from you: 555345 for the 10-file commit, and the push word."), [])
            self.assertEqual(len(hook._unrecorded_claims(archive, "The commit carries 10 files and 3384 tests passed.")), 1)


if __name__ == "__main__":
    unittest.main()
