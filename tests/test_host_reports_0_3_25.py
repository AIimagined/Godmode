"""Field reports on 0.3.25 from three hosts, 2026-09-10.

opencode: `quality` took two minutes against one second for `integrity`;
seven spec files bound to roles read "competing-authority"; the wired
`.agents/hooks.json` path is this machine's; a `git init` after godmode's
init left the records to be found by hand. Codex (sandboxed): every archive
write failed under a protected `.git`; the charter compiled one document and
did not say what the linked constitution and specs were; the tool's own
clone inside the project was read as the project. A docs/ tree with 21
handovers and a 300 KB SSOT drew no doc-sprawl line because the detector
looked at the root only.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, PLUGIN_ROOT / "tests", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PRIMACY = "# Spec\n\nThis document is the single source of truth for its domain.\n"


def _run(argv: list[str], project: Path) -> tuple[int, dict]:
    out = io.StringIO()
    with redirect_stdout(out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console.main(["--project", str(project)] + argv)
    return code, json.loads(out.getvalue())


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)


class NestedCloneTests(unittest.TestCase):
    def test_the_tool_clone_is_not_the_project(self) -> None:
        from godmode_runtime.godmode_constants import IGNORED_DIRECTORY_NAMES
        from godmode_runtime.godmode_docslint import _PRIVATE_PARTS
        from godmode_runtime.godmode_status import _SKIP_DIRS, authority_claims

        self.assertIn(".godmode-repo", IGNORED_DIRECTORY_NAMES)
        self.assertIn(".godmode-repo", _PRIVATE_PARTS)
        self.assertIn(".godmode-repo", _SKIP_DIRS)
        with isolated_project() as (project, _s, _a, _archive):
            nested = project / ".godmode-repo" / "docs"
            nested.mkdir(parents=True)
            (nested / "GUIDE.md").write_text(PRIMACY, encoding="utf-8")
            (project / "SPEC.md").write_text(PRIMACY, encoding="utf-8")
            paths = [entry["path"] for entry in authority_claims(project)]
        self.assertEqual(paths, ["SPEC.md"])


class DeclaredAuthorityTests(unittest.TestCase):
    def _roles(self, project: Path, files: list[str]) -> None:
        custom = {f"spec-{index}": {"paths": [name]} for index, name in enumerate(files)}
        (project / ".godmode-roles.json").write_text(
            json.dumps({"custom": custom}), encoding="utf-8")

    def test_bound_claimants_are_declared_not_competing(self) -> None:
        from godmode_runtime.godmode_status import survey

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for name in ("SPEC-A.md", "SPEC-B.md", "SPEC-C.md"):
                (project / name).write_text(PRIMACY, encoding="utf-8")
            self._roles(project, ["SPEC-A.md", "SPEC-B.md", "SPEC-C.md"])
            report = survey(archive, project)
        self.assertEqual(report["verdict"], "declared-authorities", report)
        self.assertEqual(report["authority_claims"]["declared"], 3)
        self.assertEqual(report["authority_claims"]["unbound"], [])

    def test_an_unbound_claimant_competes_and_is_named(self) -> None:
        from godmode_runtime.godmode_assess import assess
        from godmode_runtime.godmode_status import survey

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for name in ("SPEC-A.md", "SPEC-B.md", "NOTES.md"):
                (project / name).write_text(PRIMACY, encoding="utf-8")
            self._roles(project, ["SPEC-A.md", "SPEC-B.md"])
            report = survey(archive, project)
            assessed = assess(project, archive=archive)
        self.assertEqual(report["verdict"], "competing-authority", report)
        self.assertEqual(report["authority_claims"]["unbound"], ["NOTES.md"])
        codes = {finding["code"] for finding in assessed["findings"]}
        self.assertIn("competing-authority", codes)
        detail = next(f for f in assessed["findings"] if f["code"] == "competing-authority")
        self.assertIn("NOTES.md", json.dumps(detail))


class AntigravityHookPathTests(unittest.TestCase):
    def test_a_dead_path_under_the_godmode_key_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / ".agents").mkdir()
            dead = "C:/elsewhere/.godmode-repo/hooks/run-hook.cmd godmode_gate_fast.py"
            (project / ".agents" / "hooks.json").write_text(json.dumps({
                "godmode": {"enabled": True, "PreToolUse": [
                    {"matcher": ".*", "hooks": [{"type": "command", "command": dead, "timeout": 8}]}]},
            }), encoding="utf-8")
            _code, payload = _run(["doctor", "--host", "antigravity"], project)
        issues = " ".join(payload.get("issues") or [])
        self.assertIn("does not exist", issues, payload)
        self.assertIn("C:/elsewhere/.godmode-repo/hooks/run-hook.cmd", issues)

    def test_the_wired_note_says_the_path_is_this_machines(self) -> None:
        from godmode_runtime.godmode_host_manifests import build_antigravity_fragment

        note = build_antigravity_fragment()["_note"]
        self.assertIn("this machine's path", note)
        self.assertIn("hooks status names a dead path", note)


class GitInitRelinkTests(unittest.TestCase):
    def test_init_relinks_records_git_init_stranded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                code, first = _run(["init"], project)
                self.assertEqual(code, 0, first)
                _code, _ = _run(["remember", "--kind", "decision", "--subject", "d1",
                                 "--value", "before git"], project)
                _git(project, "init", "-q")
                code, doctor = _run(["doctor"], project)
                codes = {issue["code"] for issue in doctor.get("issues", [])}
                self.assertIn("archive-predates-git-init", codes, doctor)
                code, second = _run(["init"], project)
                self.assertEqual(code, 0, second)
                self.assertIn("adopted", second, second)
                self.assertIn("relinked", second["next_action"])
                _code, third = _run(["init"], project)
                self.assertNotIn("orphaned_archive", third, third)
                _code, history = _run(["history", "--limit", "5"], project)
        self.assertIn("d1", json.dumps(history))


class QualityCostTests(unittest.TestCase):
    def test_minimality_is_deferred_unless_deep(self) -> None:
        from godmode_runtime.godmode_quality import quality_report

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            fast = quality_report(project, archive)
            deep = quality_report(project, archive, deep=True)
        self.assertEqual(fast["sources"], ["docs", "swallow"])
        self.assertIn("minimality", fast["deferred"])
        self.assertEqual(sorted(fast["timings_seconds"]), ["docs", "swallow"])
        self.assertEqual(deep["sources"], ["docs", "swallow", "minimality"])
        self.assertIn("minimality", deep["timings_seconds"])
        self.assertNotIn("deferred", deep)

    def test_the_console_takes_deep(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _code, payload = _run(["quality", "--deep"], project)
        self.assertIn("minimality", payload["sources"])


class UnwritableGitMetadataTests(unittest.TestCase):
    def test_a_first_archive_under_a_protected_git_dir_lives_in_application_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            _git(project, "init", "-q")
            home = base / "state"
            real_access = os.access

            def refused(path, mode, *args, **kwargs):
                if mode == os.W_OK and Path(path).name == ".git":
                    return False
                return real_access(path, mode, *args, **kwargs)

            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(home)}, clear=False), \
                    mock.patch("godmode_runtime.godmode_anchor.os.access", side_effect=refused):
                anchor = resolve_anchor(project)
                self.assertTrue(anchor.is_git)
                self.assertTrue(Path(anchor.archive_root).is_relative_to(home), anchor.archive_root)
                archive = Chronicle(anchor)
                archive.initialize()
                archive.append("decision", "d1", {"value": "written"})
                code, doctor = _run(["doctor"], project)
            codes = {issue["code"] for issue in doctor.get("issues", [])}
        self.assertIn("archive-in-application-data", codes, doctor)

    def test_an_existing_git_archive_is_left_where_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            _git(project, "init", "-q")
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                first = resolve_anchor(project)
                Chronicle(first).initialize()
                with mock.patch("godmode_runtime.godmode_anchor.os.access", return_value=False):
                    again = resolve_anchor(project)
            self.assertEqual(again.archive_root, first.archive_root)


class CharterLinksTests(unittest.TestCase):
    def test_linked_documents_no_role_binds_are_named(self) -> None:
        from godmode_runtime.godmode_charter import compile_charter

        with isolated_project() as (project, _s, _a, _archive):
            (project / "docs").mkdir()
            (project / "docs" / "constitution.md").write_text("# Constitution\n- MUST keep tests green\n",
                                                               encoding="utf-8")
            (project / "GODMODE.md").write_text(
                "# Guide\n- Follow the [constitution](docs/constitution.md#rules) and "
                "[the site](https://example.invalid/x.md).\n", encoding="utf-8")
            report = compile_charter(project)
        self.assertEqual(report["linked_not_compiled"], ["docs/constitution.md"], report)


class DocSprawlUnderDocsTests(unittest.TestCase):
    def test_handovers_under_docs_count(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            docs = project / "docs"
            docs.mkdir()
            for index in range(6):
                (docs / f"HANDOVER-2026-09-0{index + 1}-x.md").write_text(
                    "# h\n" + "- item\n" * 400, encoding="utf-8")
            (docs / "SPRINT-SSOT.md").write_text("# s\n" + "- item\n" * 2000, encoding="utf-8")
            hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "session-start", "--project", str(project)],
                input="{}", capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=dict(os.environ))
            brief = json.loads(done.stdout).get("brief") or {}
        sprawl = brief.get("doc_sprawl") or {}
        self.assertEqual(sprawl.get("files"), 7, brief)
        self.assertTrue(str(sprawl.get("largest", "")).startswith("docs/SPRINT-SSOT.md"), sprawl)


class InventoryCountTests(unittest.TestCase):
    def test_the_inventory_count_matches_the_registry(self) -> None:
        import re

        text = (PLUGIN_ROOT / "docs" / "FEATURE-INVENTORY.md").read_text(encoding="utf-8")
        stated = int(re.search(r"(\d+) numbered capability statements", text).group(1))
        registry = json.loads((PLUGIN_ROOT / "capabilities.json").read_text(encoding="utf-8"))
        entries = registry if isinstance(registry, list) else registry.get("capabilities", [])
        self.assertEqual(stated, len(entries))


if __name__ == "__main__":
    unittest.main()
