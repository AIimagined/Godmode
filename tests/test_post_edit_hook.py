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
        # Advisory only, never a decision: the model-facing context rides
        # hookSpecificOutput (obligation 9860) but no decision key ever does.
        self.assertNotIn("permissionDecision", payload.get("hookSpecificOutput") or {})
        self.assertNotIn("decision", payload)
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


class UntrustedOutputTests(unittest.TestCase):
    """Fetch-class output is untrusted data - said once per session."""

    def _run_fetch(self, project, state, session="S1"):
        payload = {"hook_event_name": "PostToolUse",
                   "tool_name": "WebFetch", "tool_input": {},
                   "cwd": str(project), "session_id": session}
        import os as _os
        env = dict(_os.environ)
        env["GODMODE_STATE_HOME"] = str(state)
        done = subprocess.run(
            [sys.executable, str(HOOK)], input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60, cwd=str(project), env=env)
        return (done.stdout or "").strip()

    def test_fetch_draws_the_notice_once(self) -> None:
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            first = self._run_fetch(project, state)
            second = self._run_fetch(project, state)
            self.assertIn("untrusted DATA", first)
            self.assertNotIn("untrusted DATA", second)

    def _run_fetch_raw(self, project, state, raw: bytes) -> str:
        import os as _os
        env = dict(_os.environ)
        env["GODMODE_STATE_HOME"] = str(state)
        done = subprocess.run(
            [sys.executable, str(HOOK)], input=raw,
            capture_output=True, timeout=60, cwd=str(project), env=env)
        return (done.stdout or b"").decode("utf-8", "replace").strip()

    def test_a_bom_prefixed_payload_still_parses(self) -> None:
        """Fix round 1 (G-8): before switching this hook's own decode to
        `godmode_stdin.parse_first_json`, a leading BOM made `json.loads`
        raise, caught by a bare `except ValueError: return 0` - the hook
        silently no-op'd on a payload shape the reader already accepted,
        rather than acting on it."""
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            payload = {"hook_event_name": "PostToolUse", "tool_name": "WebFetch",
                       "tool_input": {}, "cwd": str(project), "session_id": "S1"}
            raw = b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")
            out = self._run_fetch_raw(project, state, raw)
            self.assertIn("untrusted DATA", out)

    def test_a_payload_with_trailing_data_still_parses(self) -> None:
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            payload = {"hook_event_name": "PostToolUse", "tool_name": "WebFetch",
                       "tool_input": {}, "cwd": str(project), "session_id": "S2"}
            raw = json.dumps(payload).encode("utf-8") + b"\nnot json at all"
            out = self._run_fetch_raw(project, state, raw)
            self.assertIn("untrusted DATA", out)

    def test_registered_for_fetch_class(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json")
                              .read_text(encoding="utf-8"))
        matchers = " ".join(e["matcher"]
                            for e in manifest["hooks"]["PostToolUse"])
        self.assertIn("WebFetch", matchers)


class EditRecordTests(unittest.TestCase):
    """U-N-1: `godmode_metrics.plan_adherence`'s real path source - one
    `edit-recorded` action per edit-shaped PostToolUse call: `path` plus a
    distinguishing `operation` digest (fix round 2, B2). No PreToolUse
    gate writer carries a path on an ordinary mutation, so this hook
    (already scoped by its host matcher to
    Write/Edit/MultiEdit/NotebookEdit/write/search_replace) is the one
    real writer that both sees every edit and already resolves it."""

    def _read_fresh(self, project, state):
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        return Chronicle(resolve_anchor(project)).read_events()

    def _run_named_tool(self, project, state, target, tool_name: str, file_field: str = "file_path"):
        payload = {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                   "tool_input": {file_field: str(target)},
                   "cwd": str(project), "session_id": "S1"}
        env = dict(os.environ)
        env["GODMODE_STATE_HOME"] = str(state)
        done = subprocess.run(
            [sys.executable, str(HOOK)], input=json.dumps(payload),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60, cwd=str(project), env=env)
        return (done.stdout or "").strip()

    def test_an_edit_writes_a_path_and_operation_action_record(self) -> None:
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            target = project / "lib" / "gate.py"
            target.parent.mkdir()
            target.write_text("x = 1\n", encoding="utf-8")
            impact._run_with_state(project, state, target)
            records = self._read_fresh(project, state)
        edits = [r for r in records if r["kind"] == "action" and r["subject"] == "edit-recorded"]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["data"]["path"], "lib/gate.py")
        self.assertTrue(str(edits[0]["data"]["operation"]).startswith("edit:"))

    def test_two_edits_write_two_records(self) -> None:
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            target = project / "lib" / "gate.py"
            target.parent.mkdir()
            target.write_text("x = 1\n", encoding="utf-8")
            impact._run_with_state(project, state, target)
            impact._run_with_state(project, state, target)
            records = self._read_fresh(project, state)
        edits = [r for r in records if r["kind"] == "action" and r["subject"] == "edit-recorded"]
        self.assertEqual(len(edits), 2)

    def test_a_read_payload_with_a_path_writes_nothing(self) -> None:
        """Fix round 2, B5: on Gemini/Antigravity this hook is wired with a
        `.*` matcher, so a `Read`/`read_file`/`view_file` call (which also
        carries a path-shaped field) reaches `main()` exactly like an edit
        does. `_record_edit`'s tool-name allow-list must refuse to turn it
        into an `edit-recorded` action."""
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            target = project / "lib" / "gate.py"
            target.parent.mkdir()
            target.write_text("x = 1\n", encoding="utf-8")
            for tool_name in ("Read", "read_file", "view_file"):
                self._run_named_tool(project, state, target, tool_name)
            records = self._read_fresh(project, state)
        edits = [r for r in records if r["kind"] == "action" and r["subject"] == "edit-recorded"]
        self.assertEqual(edits, [])

    def test_no_archive_no_write_and_no_crash(self) -> None:
        """Off an uninitialized archive, `_record_edit` is a silent no-op -
        the hook must still exit 0 with no `edit-recorded` record."""
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            target = project / "notes.md"
            target.write_text("hi\n", encoding="utf-8")
            code, out = _run(project, target, tool="Edit")
        self.assertEqual(code, 0)


class PathEscapeFixtureTests(unittest.TestCase):
    """NS-8h call-site regression: a `file_path` that escapes the project
    (here via `..`) must produce no `edit-recorded` archive entry and no
    quality findings - exit 0, empty stdout, the escaped file never read."""

    def test_a_dotdot_escaping_file_path_writes_no_record_and_emits_nothing(self) -> None:
        impact = ImpactBriefTests()
        with impact._archive_project() as (project, state, _archive):
            outside = project.parent / "outside-secret.py"
            outside.write_text("SECRET = 1  # not this project's file\n", encoding="utf-8")
            (project / POLICY).write_text(json.dumps({"post_edit_quality": True}),
                                          encoding="utf-8")
            escaping = "../outside-secret.py"
            payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                       "tool_input": {"file_path": escaping},
                       "cwd": str(project), "session_id": "S1"}
            env = dict(os.environ)
            env["GODMODE_STATE_HOME"] = str(state)
            done = subprocess.run(
                [sys.executable, str(HOOK)], input=json.dumps(payload),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, cwd=str(project), env=env)
            self.assertEqual(done.returncode, 0)
            self.assertEqual((done.stdout or "").strip(), "")
            from godmode_runtime.godmode_anchor import resolve_anchor
            from godmode_runtime.godmode_chronicle import Chronicle
            records = Chronicle(resolve_anchor(project)).read_events()
        edits = [r for r in records if r["kind"] == "action" and r["subject"] == "edit-recorded"]
        self.assertEqual(edits, [])
