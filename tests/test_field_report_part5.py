"""The RCA pass (2026-09-10 afternoon): temporary state is noticed without
being declared; a red-to-green flip with several edits between is named
as unattributed; the external-verdict nudge counts local reads of the
project's own repository and names what was read."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


def _transcript(path: Path, entries: list[dict]) -> str:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return str(path)


def _tool(tool_id: str, name: str, payload: dict) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": payload}]}}


def _result(tool_id: str, text: str) -> dict:
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": text}]}}


def _user(text: str) -> dict:
    return {"type": "user", "message": {"content": text}}


class TemporaryStateTests(unittest.TestCase):
    def test_a_stopped_server_a_port_and_an_update_are_named_until_restored(self) -> None:
        from godmode_runtime.godmode_oracle import unrestored_temporaries

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            open_ = _transcript(project / "a.jsonl", [
                _tool("1", "PowerShell", {"command": "Stop-Process -Name node -Force"}),
                _tool("2", "PowerShell", {"command": "npx next start -p 3001"}),
                _tool("3", "Bash", {"command": "psql -c \"UPDATE users SET role='admin' WHERE id=7\""}),
                _tool("4", "Bash", {"command": "git stash"}),
            ])
            kinds = [t["kind"] for t in unrestored_temporaries(open_)]
            self.assertEqual(sorted(kinds), ["data", "process", "process", "worktree"], kinds)
            notices, _ = hook._iteration_notices(archive, project, {"transcript_path": open_})
            hit = [n for n in notices if "temporary state" in n]
            self.assertEqual(len(hit), 1, notices)
            self.assertIn("--owes", hit[0])
            self.assertTrue(any(r["subject"] == "would-have-required-restore"
                                for r in archive.select(kind="action", limit=20)))
            restored = _transcript(project / "b.jsonl", [
                _tool("1", "PowerShell", {"command": "Stop-Process -Name node -Force"}),
                _tool("2", "PowerShell", {"command": "npx next start -p 3001"}),
                _tool("3", "Bash", {"command": "psql -c \"UPDATE users SET role='admin' WHERE id=7\""}),
                _tool("4", "Bash", {"command": "git stash"}),
                _tool("5", "Bash", {"command": "psql -c \"UPDATE users SET role='user' WHERE id=7\""}),
                _tool("6", "PowerShell", {"command": "taskkill /F /PID 4242"}),
                _tool("7", "Bash", {"command": "git stash pop"}),
                _tool("8", "PowerShell", {"command": "npm run dev"}),
            ])
            self.assertEqual(unrestored_temporaries(restored), [])


class UnattributedFlipTests(unittest.TestCase):
    def test_a_flip_with_three_edits_between_is_named_and_one_edit_is_not(self) -> None:
        from godmode_runtime.godmode_oracle import unattributed_flips

        with isolated_project() as (project, _s, _a, _archive):
            many = _transcript(project / "a.jsonl", [
                _tool("r1", "Bash", {"command": "npx vitest run"}), _result("r1", "FAIL src/x.test.ts\n1 failed"),
                _tool("e1", "Edit", {"file_path": "src/a.ts"}), _tool("e2", "Edit", {"file_path": "src/b.ts"}),
                _tool("e3", "Write", {"file_path": "src/c.ts"}),
                _tool("r2", "Bash", {"command": "npx vitest run"}), _result("r2", "Tests 12 passed"),
            ])
            flips = unattributed_flips(many)
            self.assertEqual(len(flips), 1, flips)
            self.assertEqual(flips[0]["files"], ["a.ts", "b.ts", "c.ts"])
            one = _transcript(project / "b.jsonl", [
                _tool("r1", "Bash", {"command": "npx vitest run"}), _result("r1", "FAIL src/x.test.ts"),
                _tool("e1", "Edit", {"file_path": "src/a.ts"}),
                _tool("r2", "Bash", {"command": "npx vitest run"}), _result("r2", "Tests 12 passed"),
            ])
            self.assertEqual(unattributed_flips(one), [])


class LocalReadsCountTests(unittest.TestCase):
    def test_reading_the_projects_own_files_counts_as_reading_its_repository(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/acme/widgets.git"], cwd=project, check=True)
            (project / "docs").mkdir()
            (project / "docs" / "RCA.md").write_text("x", encoding="utf-8")
            reply = "The root cause in acme/widgets is not the cache; the report does not support it."
            unread = _transcript(project / "a.jsonl", [_user("look at https://github.com/acme/widgets please")])
            notices = hook._external_verdict_nudge({"transcript_path": unread}, reply, project)
            self.assertEqual(len(notices), 1, notices)
            read = _transcript(project / "b.jsonl", [
                _user("look at https://github.com/acme/widgets please"),
                _tool("1", "Read", {"file_path": str(project / "docs" / "RCA.md")}),
            ])
            self.assertEqual(hook._external_verdict_nudge({"transcript_path": read}, reply, project), [])
            only_readme = _transcript(project / "c.jsonl", [
                _user("look at https://github.com/acme/other please"),
                _tool("1", "Bash", {"command": "gh api repos/acme/other/contents/README.md"}),
            ])
            notices = hook._external_verdict_nudge({"transcript_path": only_readme},
                                                   "acme/other is not worth absorbing.", project)
            self.assertEqual(len(notices), 1)
            self.assertIn("only readme.md", notices[0].lower())


if __name__ == "__main__":
    unittest.main()
