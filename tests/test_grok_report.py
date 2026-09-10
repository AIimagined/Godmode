"""The Grok host report (0.3.25, 2026-09-10): reads in the transcript count
toward required sources with case folded on Windows; a repository without
git is a doctor finding; the constitution is detected before the walk;
resume carries one screen of scalars; session open leads with the reach."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from test_godmode_runtime import isolated_project  # noqa: E402


class RequiredSourceReadTests(unittest.TestCase):
    def test_a_read_in_the_transcript_counts_and_case_folds_on_windows(self) -> None:
        from godmode_runtime.godmode_sources import transcript_reads

        with isolated_project() as (project, _s, _a, _archive):
            (project / "AGENTS.md").write_text("rules\n", encoding="utf-8")
            spelled = "Agents.md" if os.name == "nt" else "AGENTS.md"
            transcript = project / "t.jsonl"
            transcript.write_text("\n".join(json.dumps(e) for e in [
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": str(project / spelled)}}]}},
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": "sed -n 1,20p AGENTS.md"}}]}},
            ]) + "\n", encoding="utf-8")
            reads = transcript_reads(transcript, project)
            expected = "agents.md" if os.name == "nt" else "AGENTS.md"
            self.assertIn(expected, reads)

    def test_the_view_keeps_each_required_documents_own_spelling(self) -> None:
        from godmode_runtime.godmode_sources import required_sources_view

        with isolated_project() as (project, _s, _a, archive):
            (project / "CLAUDE.md").write_text("# rules\n", encoding="utf-8")
            view = required_sources_view(project, archive)
            self.assertIn("CLAUDE.md", view["unread"], view)
            self.assertNotIn("claude.md", view["unread"])
            transcript = project / "t.jsonl"
            transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "1", "name": "Read",
                 "input": {"file_path": str(project / ("Claude.md" if os.name == "nt" else "CLAUDE.md"))}}]}}) + "\n",
                encoding="utf-8")
            after = required_sources_view(project, archive, transcript_path=transcript)
            self.assertNotIn("CLAUDE.md", after["unread"], after)


class GitlessDoctorTests(unittest.TestCase):
    def test_doctor_names_a_repository_without_git(self) -> None:
        import io
        from unittest import mock

        from godmode_runtime import godmode_console as console

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                console.main(["--project", str(project), "--json", "doctor"])
            payload = json.loads(out.getvalue())
            codes = [i.get("code") for i in payload.get("issues", [])]
            self.assertIn("not-a-git-repository", codes, payload.get("issues"))


class ConstitutionDetectTests(unittest.TestCase):
    def test_the_constitution_is_detected_before_the_capped_walk(self) -> None:
        from godmode_runtime.godmode_detect import detect_repo

        with isolated_project() as (project, _s, _a, _archive):
            (project / ".specify" / "memory").mkdir(parents=True)
            (project / ".specify" / "memory" / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
            (project / "specs" / "001-login").mkdir(parents=True)
            (project / "specs" / "001-login" / "spec.md").write_text("# Spec\n", encoding="utf-8")
            kinds = [(d.get("kind"), d.get("value")) for d in detect_repo(project)]
            self.assertIn(("constitution", ".specify/memory/constitution.md"), kinds)
            self.assertIn(("spec", "specs/001-login/spec.md"), kinds)


class ResumeScalarsTests(unittest.TestCase):
    def test_resume_leads_with_goal_dirty_obligations_and_next(self) -> None:
        import io
        from unittest import mock

        from godmode_runtime import godmode_console as console

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            archive.append("plan", "ship the login flow", {"status": "active", "steps": [
                {"text": "write the migration note", "status": "pending"}]}, evidence=[])
            archive.append("checkpoint", "cp", {"status": "active", "next": ["run the perimeter"]}, evidence=[])
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                console.main(["--project", str(project), "--json", "resume"])
            payload = json.loads(out.getvalue())
            self.assertEqual(payload.get("goal"), "ship the login flow")
            self.assertEqual(payload.get("current_step"), "write the migration note")
            self.assertEqual(payload.get("next"), "run the perimeter")
            self.assertIn("dirty", payload)


class HandshakeReachTests(unittest.TestCase):
    def test_session_open_leads_with_the_reach(self) -> None:
        import io
        from unittest import mock

        from godmode_runtime import godmode_console as console

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                console.main(["--project", str(project), "--json", "session", "open"])
            payload = json.loads(out.getvalue())
            self.assertIn("reach", payload)
            self.assertIn("pre-tool gate", payload["reach"])


if __name__ == "__main__":
    unittest.main()
