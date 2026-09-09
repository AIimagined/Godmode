"""Field reports 23-25 (2026-09-09): emissions carry data or nothing.

Replayed against the reporter's own archive and transcript before this
file was written: the turn-boundary ask nag fired on 34 of 42 real replies
and only a current-session filter brought it to 0; the auto-serve would
have closed asks on 41 of 42; the failure nudge named verbs and no
evidence; a checkpoint accepted "code-green" with no evidence; the resume
nudge ignored the project's own STATE.md; the observe advisory repeated
per call; a colon heading and a quoted number were read as claims.
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
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, PLUGIN_ROOT / "tests", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime import godmode_requests as requests  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_precheck import failure_nudge, prompt_shape_nudge  # noqa: E402
from godmode_runtime.godmode_requests import open_stated_requests, record_request  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


def _git(project: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=project, check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(project: Path) -> tuple[str, Chronicle]:
    """A committed git tree and the archive a CLI call on it resolves to
    (a git project keys its archive below .git, not the salted non-git
    home the fixture's archive uses)."""
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@example.invalid")
    _git(project, "config", "user.name", "t")
    (project / "engine.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (project / "caller.py").write_text("import engine\n", encoding="utf-8")
    _git(project, "add", "."); _git(project, "commit", "-q", "-m", "green")
    archive = Chronicle(resolve_anchor(project)); archive.initialize()
    return _git(project, "rev-parse", "HEAD")[:12], archive


def _quiet_main(argv: list[str]) -> tuple[int, dict]:
    with mock.patch.object(sys, "stdout", io.StringIO()) as out, \
            mock.patch.object(sys, "stderr", io.StringIO()):
        code = console.main(argv)
    text = out.getvalue().strip()
    try:
        payload = json.loads(text) if text.startswith("{") else {}
    except json.JSONDecodeError:
        payload = {}
    return code, payload


class AskNagScopeTests(unittest.TestCase):
    def test_an_ask_from_another_session_is_not_nagged(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "please rename the launcher directory variable everywhere", session="other-host-session")
            reply = "The launcher directory variable is renamed everywhere; please review."
            self.assertEqual(hook._open_obligations_touched(archive, reply, session_id="this-host-session"), [])

    def test_an_ask_from_this_session_is_nagged(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "please rename the launcher directory variable everywhere", session="this-host-session")
            reply = "Still working on the launcher directory variable; nothing renamed yet."
            touched = hook._open_obligations_touched(archive, reply, session_id="this-host-session")
            self.assertEqual(len(touched), 1)
            self.assertIn("operator ask", touched[0])

    def test_no_reply_closes_an_ask_by_word_overlap(self) -> None:
        self.assertFalse(hasattr(requests, "serve_requests"))
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_request(archive, "please rename the launcher directory variable", session="s")
            self.assertEqual(len(open_stated_requests(archive.select(kind="request", limit=50))), 1)


class FailureNudgeDataTests(unittest.TestCase):
    def test_the_failure_line_names_the_last_green_and_what_changed_since(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            head, archive = _repo(project)
            session = open_session(archive, "t")
            archive.append("attestation", "full-suite", {"session": session, "status": "ran", "result": "12 OK",
                                                          "worktree": {"head": head, "dirty": 0}}, evidence=[])
            (project / "engine.py").write_text("def run():\n    return 2\n", encoding="utf-8")
            text = failure_nudge(archive, "Traceback (most recent call last):\nValueError: x", session, project=project)
            self.assertIsNotNone(text)
            self.assertIn("full-suite", text)
            self.assertIn("engine.py", text)
            self.assertNotIn("`godmode error-pattern`", text)

    def test_with_no_attestation_the_line_says_so_and_names_the_dirty_files(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _head, archive = _repo(project)
            session = open_session(archive, "t")
            (project / "caller.py").write_text("import engine  # touched\n", encoding="utf-8")
            text = failure_nudge(archive, "exit code 1", session, project=project)
            self.assertIsNotNone(text)
            self.assertIn("no attested check", text)
            self.assertIn("caller.py", text)


class CheckpointEvidenceTests(unittest.TestCase):
    def test_changed_files_outside_any_attestation_are_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            head, archive = _repo(project)
            session = open_session(archive, "t")
            archive.append("attestation", "full-suite", {"session": session, "status": "ran", "result": "ok",
                                                          "worktree": {"head": head, "dirty": 0}}, evidence=[])
            (project / "engine.py").write_text("def run():\n    return 3\n", encoding="utf-8")
            code, payload = _quiet_main(["--project", str(project), "checkpoint", "handoff", "--status", "active"])
            self.assertEqual(code, 0)
            joined = " ".join(payload.get("advisories") or [])
            self.assertIn("engine.py", joined)
            self.assertIn("full-suite", joined)

    def test_a_green_worded_status_with_no_evidence_is_flagged(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _repo(project)
            code, payload = _quiet_main(["--project", str(project), "checkpoint", "handoff", "--status", "code-green, suite 3700/3700"])
            self.assertEqual(code, 0)
            joined = " ".join(payload.get("advisories") or [])
            self.assertIn("no evidence", joined)


class ResumeNudgeTests(unittest.TestCase):
    def test_the_resume_nudge_is_silent_when_the_project_keeps_a_resume_doc(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(prompt_shape_nudge(archive, "where are we on the migration?", "s1", resume_doc="STATE.md"))
            self.assertIsNotNone(prompt_shape_nudge(archive, "where are we on the migration?", "s2", resume_doc=None))


class ObserveAdvisoryOnceTests(unittest.TestCase):
    def test_the_observe_advisory_is_delivered_once_per_category_per_session(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            first = hook._observe_advisory_once(archive, "s1", "interpreter-opaque-inline", "OBSERVE MODE - would have asked")
            again = hook._observe_advisory_once(archive, "s1", "interpreter-opaque-inline", "OBSERVE MODE - would have asked")
            other = hook._observe_advisory_once(archive, "s1", "filesystem-mutation", "OBSERVE MODE - would have denied")
            self.assertEqual(first, "OBSERVE MODE - would have asked")
            self.assertIsNone(again)
            self.assertIsNotNone(other)


class DoneBarShapeTests(unittest.TestCase):
    def test_a_colon_heading_is_not_a_sentence(self) -> None:
        self.assertEqual(hook._reply_sentences("Fix alternatives ranked:\n\n1. Patch the wrapper.\n"), ["Patch the wrapper"])
        self.assertEqual(hook._reply_sentences("**Second opinion complete:**\n"), [])

    def test_a_quoted_number_is_reported_speech_not_a_claim(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            found = hook._unrecorded_claims(archive, 'Reviewer: "the regression touched 22 files and sat 2 days".')
            self.assertEqual(found, [])


class Report26Tests(unittest.TestCase):
    def test_atlas_closure_takes_the_documented_positional_files(self) -> None:
        parser = console._build_parser()
        args = parser.parse_args(["atlas", "closure", "lib/a.py", "lib/b.py"])
        self.assertEqual(args.changed_positional, ["lib/a.py", "lib/b.py"])
        flagged = parser.parse_args(["atlas", "closure", "--changed", "lib/a.py"])
        self.assertEqual(flagged.changed, ["lib/a.py"])

    def test_a_write_over_an_unread_tracked_file_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _repo(project)
            transcript = project / "t.jsonl"
            transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": str(project / "caller.py")}}]}}) + "\n",
                encoding="utf-8")
            submitted = {"transcript_path": str(transcript)}
            named = hook._write_without_read_advisory(submitted, "Write", [str(project / "engine.py")], project)
            self.assertIsNotNone(named)
            self.assertIn("engine.py", named)
            self.assertIn("never read", named)
            read_first = hook._write_without_read_advisory(submitted, "Write", [str(project / "caller.py")], project)
            self.assertIsNone(read_first)
            new_file = hook._write_without_read_advisory(submitted, "Write", [str(project / "fresh.py")], project)
            self.assertIsNone(new_file)


    def test_a_typescript_relative_import_resolves_to_a_dependent(self) -> None:
        from godmode_runtime.godmode_atlas import build, unfollowed_dependents
        with isolated_project() as (project, _s, _a, archive):
            (project / "lib").mkdir()
            (project / "lib" / "b.ts").write_text("export const b = 1;\n", encoding="utf-8")
            (project / "lib" / "a.ts").write_text("import { b } from './b';\nexport const a = b;\n", encoding="utf-8")
            (project / "app.tsx").write_text("import { a } from './lib/a';\nexport default a;\n", encoding="utf-8")
            atlas = build(project)
            report = unfollowed_dependents(atlas, ["lib/b.ts"])
            self.assertEqual(report["verdict"], "unfollowed-dependents")
            self.assertEqual([f["dependent"] for f in report["findings"]], ["lib/a.ts"])
            deeper = unfollowed_dependents(atlas, ["lib/b.ts"], depth=2)
            self.assertIn("app.tsx", [f["dependent"] for f in deeper["findings"]])

    def test_precheck_bounds_its_atlas_walk(self) -> None:
        from godmode_runtime import godmode_precheck as pre
        self.assertGreater(pre.PRECHECK_ATLAS_BUDGET_SECONDS, 0)
        seen = {}
        real = pre.__dict__.get("precheck")
        import godmode_runtime.godmode_atlas as atlas_mod
        original = atlas_mod.build
        def spy(project, suffixes=None, budget_seconds=None):
            seen["budget"] = budget_seconds
            return original(project, suffixes, budget_seconds)
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with mock.patch.object(atlas_mod, "build", spy):
                pre.precheck(project, archive, "emissions carry data")
        self.assertEqual(seen.get("budget"), pre.PRECHECK_ATLAS_BUDGET_SECONDS)


if __name__ == "__main__":
    unittest.main()
