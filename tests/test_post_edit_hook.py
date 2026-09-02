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


class ImpactBriefTests(unittest.TestCase):
    """The recorded neighbors of an edited file, pushed at the edit moment
    - once per file per session, fail-silent."""

    def _archive_project(self):
        import tempfile
        from contextlib import contextmanager
        from unittest import mock
        import os as _os
        for entry in (str(PLUGIN_ROOT / "scripts"),):
            if entry not in sys.path:
                sys.path.insert(0, entry)
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle

        @contextmanager
        def ctx():
            with tempfile.TemporaryDirectory(prefix="gm-impact-") as tmp:
                base = Path(tmp)
                root = base / "p"
                root.mkdir()
                state = base / "state"
                with mock.patch.dict(_os.environ,
                                     {"GODMODE_STATE_HOME": str(state)},
                                     clear=False):
                    archive = Chronicle(resolve_anchor(root))
                    archive.initialize()
                    yield root, state, archive
        return ctx()

    def _run_with_state(self, project, state, target, session="S1"):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                   "tool_input": {"file_path": str(target)},
                   "cwd": str(project), "session_id": session}
        import os as _os
        env = dict(_os.environ)
        env["GODMODE_STATE_HOME"] = str(state)
        done = subprocess.run(
            [sys.executable, str(HOOK)], input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60, cwd=str(project), env=env)
        return (done.stdout or "").strip()

    def test_cited_file_surfaces_once_then_dedupes(self) -> None:
        with self._archive_project() as (project, state, archive):
            target = project / "lib" / "gate.py"
            target.parent.mkdir()
            target.write_text("x = 1\n", encoding="utf-8")
            archive.append("invariant", "the gate never fails open",
                           {"value": "wrap the header, not the gate"},
                           evidence=["file:lib/gate.py#L1"])
            first = self._run_with_state(project, state, target)
            self.assertIn("recorded fact", first)
            self.assertIn("lib/gate.py", first)
            second = self._run_with_state(project, state, target)
            self.assertNotIn("recorded fact", second)

    def test_uncited_file_is_silent(self) -> None:
        with self._archive_project() as (project, state, _archive):
            target = project / "lib" / "other.py"
            target.parent.mkdir()
            target.write_text("y = 2\n", encoding="utf-8")
            out = self._run_with_state(project, state, target)
            self.assertNotIn("recorded fact", out)
