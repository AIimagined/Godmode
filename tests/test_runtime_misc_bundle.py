"""Cross-session timelines merge with named conflicts; the skill-impact
floor is skill-wide; the CI fire step reads a deny by its stdout."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (str(SCRIPTS), str(SCRIPTS / "dev"), str(Path(__file__).parent)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from godmode_runtime.godmode_session_log import command_digest, merge_timelines  # noqa: E402
from godmode_runtime.godmode_skillimpact import best_recorded_score, record_impact  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _transcript(path: Path, turns: list[tuple[str, str, bool]]) -> Path:
    """`turns`: (kind, command, is_error) - kind `run` is a shell call, `edit` a Write."""
    lines: list[str] = []
    for index, (kind, command, is_error) in enumerate(turns):
        tool_id = f"t{index}"
        if kind == "edit":
            lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": tool_id, "name": "Write", "input": {"file_path": "x"}}]}}))
            lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_id}]}}))
            continue
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}]}}))
        lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error}]}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class MergeTimelineTests(unittest.TestCase):
    def test_sessions_merge_with_distinct_turns_and_a_named_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = _transcript(Path(tmp) / "a.jsonl", [("run", "pytest -q", True)])
            b = _transcript(Path(tmp) / "b.jsonl", [("run", "pytest -q", False),
                                                    ("edit", "", False),
                                                    ("run", "ruff .", False)])
            merged = merge_timelines([a, b])
            digest = command_digest("pytest -q")
            turns = [turn for turn, _ in merged["commands"][digest]]
            self.assertEqual(len(turns), len(set(turns)), "turns stay distinct across sessions")
            self.assertEqual(merged["conflicts"], [digest], "red in one session, green in the next, nothing changed between")
            self.assertEqual(merged["duplicates"], 0)
            self.assertEqual(len(merged["sources"]), 2)
            self.assertEqual(len(merged["mutation_turns"]), 1)

    def test_a_copied_transcript_counts_as_duplicates_not_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = _transcript(Path(tmp) / "a.jsonl", [("run", "pytest -q", True)])
            merged = merge_timelines([a, a])
            self.assertEqual(merged["duplicates"], 1)
            self.assertEqual(merged["conflicts"], [])


class SkillWideFloorTests(unittest.TestCase):
    def test_the_floor_is_the_best_any_file_of_the_skill_recorded(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record_impact(archive, "skills/demo/SKILL.md", "a" * 64, 0.4, 0.7, "accepted")
            record_impact(archive, "skills/demo/scripts/run.py", "b" * 64, 0.7, 0.9, "accepted")
            record_impact(archive, "skills/other/SKILL.md", "c" * 64, 0.1, 0.95, "accepted")
            self.assertEqual(best_recorded_score(archive, "skills/demo/SKILL.md"), 0.9)
            self.assertEqual(best_recorded_score(archive, "skills/demo/godmode-evals.json"), 0.9)
            self.assertEqual(best_recorded_score(archive, "skills/other/SKILL.md"), 0.95)


class FireStepTests(unittest.TestCase):
    def test_a_deny_with_a_non_zero_exit_is_a_deny(self) -> None:
        import gen_host_ci_jobs as gen
        body = "\n".join(gen.FIRE_BODY_LINES)
        self.assertIn('godmode_gate_fast.py) || true', body)
        self.assertIn('grep -q \'"deny"\'', body)
        self.assertNotIn("hook exited non-zero", body)


if __name__ == "__main__":
    unittest.main()
