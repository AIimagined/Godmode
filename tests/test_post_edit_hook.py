"""Per-edit quality feedback, opt-in, advisory, and silent when off.

Absorbed 2026-08-27 from an upstream post-edit diagnostics hook, in this
runtime's shape. A PostToolUse hook on Write/Edit runs the docs lint or
the swallow scan over the one file just written and returns the findings
as a `systemMessage`. It never blocks - PostToolUse cannot, and quality is
a proposal here as everywhere. It is opt-in: with no `post_edit_quality`
in the policy the script exits at once with nothing on stdout, so a
project that did not ask pays one interpreter start and no more.
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
HOOK = PLUGIN_ROOT / "hooks" / "godmode_post_edit.py"
POLICY = ".godmode-authorization-policy.json"


def _run(project: Path, file_path: Path, tool: str = "Write") -> tuple[int, str]:
    payload = {"hook_event_name": "PostToolUse", "tool_name": tool,
               "tool_input": {"file_path": str(file_path)}, "cwd": str(project)}
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60, cwd=str(project))
    return done.returncode, (done.stdout or "").strip()


class PostEditHookTests(unittest.TestCase):
    def test_registered_on_post_tool_use_for_write_and_edit(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = manifest["hooks"]["PostToolUse"]
        self.assertTrue(any("godmode_post_edit.py" in json.dumps(e) for e in entries))
        matcher = next(e["matcher"] for e in entries if "godmode_post_edit.py" in json.dumps(e))
        for tool in ("Write", "Edit"):
            self.assertIn(tool, matcher)

    def test_off_by_default_says_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            doc = project / "notes.md"
            doc.write_text("See C:\\Users\\someone\\x\n", encoding="utf-8")
            code, out = _run(project, doc)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_on_it_reports_the_edited_file_s_findings_as_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / POLICY).write_text(json.dumps({"post_edit_quality": True}), encoding="utf-8")
            doc = project / "notes.md"
            doc.write_text("See C:\\Users\\someone\\x for it.\n\nTODO finish\n", encoding="utf-8")
            code, out = _run(project, doc, tool="Edit")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertNotIn("hookSpecificOutput", payload)  # advisory only, never a decision
        self.assertIn("local-path", payload["systemMessage"])
        self.assertIn("notes.md", payload["systemMessage"])

    def test_on_a_python_file_the_swallow_scan_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / POLICY).write_text(json.dumps({"post_edit_quality": True}), encoding="utf-8")
            src = project / "mod.py"
            src.write_text("def f():\n    try:\n        g()\n    except Exception:\n        pass\n",
                           encoding="utf-8")
            code, out = _run(project, src)
        self.assertEqual(code, 0)
        self.assertIn("mod.py", json.loads(out)["systemMessage"])

    def test_a_clean_file_says_nothing_even_when_on(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / POLICY).write_text(json.dumps({"post_edit_quality": True}), encoding="utf-8")
            doc = project / "clean.md"
            doc.write_text("# Clean\n\nNothing to flag here.\n", encoding="utf-8")
            code, out = _run(project, doc)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
