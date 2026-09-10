"""Field report 27 (2026-09-10): a grep exiting 0 was graded as proof of a
suite run; a closure typed with the ask's words closed nothing and was
accepted silently; a docs-privacy pass got no help from a tool that reads
the repo. Each con is a behaviour here, failing against 0.3.22.
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
for extra in (SCRIPTS, PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import executed_predicates, filter_head, open_session  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_requests import open_stated_requests, record_request  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=project, check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(project: Path, files: dict[str, str] | None = None) -> tuple[str, Chronicle]:
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "t@example.invalid")
    _git(project, "config", "user.name", "t")
    for name, body in (files or {"engine.py": "def run():\n    return 1\n"}).items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(project, "add", "."); _git(project, "commit", "-q", "-m", "green")
    archive = Chronicle(resolve_anchor(project)); archive.initialize()
    return _git(project, "rev-parse", "HEAD")[:12], archive


def _main(argv: list[str]) -> tuple[int, dict]:
    with mock.patch.object(sys, "stdout", io.StringIO()) as out, \
            mock.patch.object(sys, "stderr", io.StringIO()) as err:
        code = console.main(argv)
    text = out.getvalue().strip() or err.getvalue().strip()
    try:
        return code, (json.loads(text) if text.startswith("{") else {"raw": text})
    except json.JSONDecodeError:
        return code, {"raw": text}


class FilterIsNotTheRunTests(unittest.TestCase):
    def test_filter_heads_are_recognised(self) -> None:
        self.assertEqual(filter_head("cmd:grep -c OK suite.log"), "grep")
        self.assertEqual(filter_head("cmd:python -m unittest 2>&1 | tail -3"), "tail")
        self.assertEqual(filter_head("cmd:cd lib; rg passed out.txt"), "rg")
        self.assertIsNone(filter_head("cmd:python -m unittest"))
        self.assertIsNone(filter_head("cmd:npx vitest run"))

    def test_a_green_filter_does_not_compose_verified(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            head, archive = _repo(project)
            session = open_session(archive, "t")
            for command in ("cmd:grep -c OK suite.log", "cmd:python -m unittest"):
                archive.append("attestation", "check", {"session": session, "status": "ran",
                                                        "result": "exit 0", "worktree": {"head": head, "dirty": 0}},
                               evidence=[command])
            filtered = executed_predicates(archive, project, ["cmd:grep -c OK suite.log"])
            self.assertEqual(filtered["grade"], "observed")
            self.assertEqual(filtered["filter_head"], "grep")
            real = executed_predicates(archive, project, ["cmd:python -m unittest"])
            self.assertEqual(real["grade"], "verified")


class ClosureRefusalTests(unittest.TestCase):
    def test_a_closure_naming_no_open_ask_is_refused_with_the_open_list(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_request(archive, "the image video is still blank at the end of the studio", session="s")
            code, payload = _main(["--project", str(project), "remember", "--kind", "request",
                                   "--subject", "ask: video still blank at the end", "--status", "closed"])
            self.assertEqual(code, 2)
            message = json.dumps(payload)
            self.assertIn(record["subject"], message)
            self.assertIn("video", message)
            self.assertEqual(len(open_stated_requests(archive.select(kind="request", limit=50))), 1)

    def test_the_paste_ready_closure_closes(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record = record_request(archive, "the image video is still blank at the end", session="s")
            code, _payload = _main(["--project", str(project), "remember", "--kind", "request",
                                    "--subject", record["subject"], "--status", "closed"])
            self.assertEqual(code, 0)
            self.assertEqual(open_stated_requests(archive.select(kind="request", limit=50)), [])


class RepoPrivacyTests(unittest.TestCase):
    def test_tracked_files_are_scanned_for_emails_home_paths_and_size(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _repo(project, {
                "docs/notes.md": "Contact someone@corp-internal.io for access.\nBuilt at C:\\Users\\alice\\Documents\\x\nServer 10.1.2.3\ntoken ghp_abcdefghijklmnopqrstuvwxyz0123\n",
                "docs/ok.md": "Mail noreply@github.com or you@example.com; path C:\\Users\\<user>\\x; version 1.2.3.4\nUse a password manager; the secret: rotate keys often.\n",
                "assets/blob.bin": "x" * 3000,
            })
            code, payload = _main(["--project", str(project), "privacy", "--repo", "--large-bytes", "1000"])
            self.assertEqual(code, 1)
            kinds = {f["kind"] for f in payload["findings"]}
            self.assertEqual(kinds, {"email", "home-path", "ip-address", "secret-shape"})
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123", json.dumps(payload))
            paths = {f["path"] for f in payload["findings"]}
            self.assertEqual(paths, {"docs/notes.md"})
            self.assertNotIn("someone@corp-internal.io", json.dumps(payload))
            self.assertEqual([f["path"] for f in payload["large_files"]], ["assets/blob.bin"])

    def test_a_clean_tree_is_clean(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _repo(project, {"README.md": "Nothing personal here.\n"})
            code, payload = _main(["--project", str(project), "privacy", "--repo"])
            self.assertEqual(code, 0)
            self.assertEqual(payload["verdict"], "clean")


class NumbersInCitedLinesTests(unittest.TestCase):
    def test_a_number_bearing_claim_needs_its_numbers_in_the_window(self) -> None:
        from godmode_runtime.godmode_attest import _position_support
        with isolated_project() as (project, _s, _a, archive):
            (project / "notes.md").write_text("suite tests: 12 passed\nnothing else\n", encoding="utf-8")
            self.assertEqual(_position_support(project, "file:notes.md#L1", "the suite ran 3384 tests"), "unsupported")
            self.assertEqual(_position_support(project, "file:notes.md#L1", "the suite ran 12 tests"), "corroborated")
            self.assertEqual(_position_support(project, "file:notes.md#L1", "the suite tests passed"), "corroborated")


class ExternalVerdictTests(unittest.TestCase):
    def _transcript(self, project: Path, tool_inputs: list[dict]) -> dict:
        import godmode_session_hook as hook  # noqa: F401
        lines = [{"type": "user", "message": {"content": "look at https://github.com/acme/widget and tell me what to borrow"}}]
        for data in tool_inputs:
            lines.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": data}]}})
        path = project / "t.jsonl"
        path.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        return {"transcript_path": str(path)}

    def test_a_verdict_on_a_readme_only_repo_is_named(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
        import godmode_session_hook as hook
        with isolated_project() as (project, _s, _a, archive):
            submitted = self._transcript(project, [{"command": "gh api repos/acme/widget/readme --jq .content"}])
            notices = hook._external_verdict_nudge(submitted, "Verdict: widget's cite-checker is worth borrowing.")
            self.assertEqual(len(notices), 1)
            self.assertIn("acme/widget", notices[0])
            self.assertIn("0 source files", notices[0])

    def test_a_verdict_after_reading_source_is_silent(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
        import godmode_session_hook as hook
        with isolated_project() as (project, _s, _a, archive):
            submitted = self._transcript(project, [
                {"command": "gh api repos/acme/widget/readme --jq .content"},
                {"command": "gh api repos/acme/widget/contents/src/check.py --jq .content"}])
            self.assertEqual(hook._external_verdict_nudge(submitted, "Verdict: widget's checker is worth borrowing."), [])
            self.assertEqual(hook._external_verdict_nudge(submitted, "Unrelated status line with no repo named."), [])


class Report28Tests(unittest.TestCase):
    def test_a_ledger_process_sentence_is_not_a_done_claim(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
        import godmode_session_hook as hook
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(hook._unrecorded_done_claims(archive, "Checkpoint complete. Claim recorded on the ledger."), [])
            self.assertEqual(len(hook._unrecorded_done_claims(archive, "The migration is complete.")), 1)

    def test_a_lesson_takes_its_guard_as_the_value(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code, _payload = _main(["--project", str(project), "remember", "--kind", "lesson",
                                    "--subject", "answer did not land", "--guard", "lead with the number"])
            self.assertEqual(code, 0)
            lesson = archive.select(kind="lesson", limit=1)[-1]
            self.assertEqual(lesson["data"]["value"], "lead with the number")
            self.assertEqual(lesson["data"]["generalized_guard"], "lead with the number")


class CommandWrittenTreeTests(unittest.TestCase):
    def test_files_changed_by_a_command_are_named_apart_from_edits(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
        import godmode_session_hook as hook
        with isolated_project() as (project, _s, _a, archive):
            head, archive = _repo(project, {"a.md": "1", "b.md": "1", "c.md": "1", "d.md": "1"})
            sha = _git(project, "rev-parse", "HEAD")
            (archive.root / hook._TURN_BASELINE).write_text(json.dumps({"sha": sha, "sequence": 0, "session": "s"}), encoding="utf-8")
            for name in ("a.md", "b.md", "c.md", "d.md"):
                (project / name).write_text("rewritten", encoding="utf-8")
            transcript = project.parent / "t.jsonl"
            transcript.write_text("\n".join(json.dumps(l) for l in [
                {"type": "user", "message": {"content": "sync the skills"}},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": str(project / "a.md")}}]}},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python sync.py"}}]}},
            ]) + "\n", encoding="utf-8")
            note = hook._turn_diff_nudge(archive, project, {"transcript_path": str(transcript), "session_id": "s"})
            self.assertIsNotNone(note)
            self.assertIn("3 of them were written by a command", note)
            self.assertIn("b.md", note)
            self.assertNotIn("a.md, b.md, c.md, d.md) -", note.split(";")[1])


if __name__ == "__main__":
    unittest.main()
