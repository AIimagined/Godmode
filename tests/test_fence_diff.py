"""Every changed line in a finished diff, traced to the fence that authorised it.

`fence_verdict` catches an edit at the boundary - the moment a tool announces a
`file_path`. It says nothing about a shell command that rewrote a file in
passing, or an edit made in a session where the hook never ran. So the same
question is asked of the result: `git diff --unified=0 HEAD`, parsed hunk by
hunk, partitioned by fence membership.

A hunk that only removes lines gets asked a different question again - not
"was this touched", but "whose code was this to remove" - and a line carrying
a debug tag gets asked a third, independent of any fence at all: it should
never have been left behind in a change claimed complete.
"""

from __future__ import annotations

import io
from contextlib import contextmanager, redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_fence import (  # noqa: E402
    completion_audit, declared_fence, declared_tag_patterns,
)
from godmode_runtime.godmode_plan import CONTRACT_FIELDS, approve, specify, start  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


SPEC = {"objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n"}


def _approved_plan(archive, editable: str | None) -> None:
    specify(archive, "S-1", "narrow the rotation fix", SPEC)
    contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
    contract["accept"] = "cmd:x"
    if editable is not None:
        contract["editable"] = editable
    start(archive, "S-1", "narrow the rotation fix", contract)
    approve(archive, "S-1")


def _run_git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(project), check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30,
    )


def _init_repo(project: Path, files: dict[str, str | bytes]) -> None:
    """A real git history: init, an identity, one commit holding the starting
    state, so the diff parser runs against actual `git diff` output rather
    than a hand-built fixture pretending to be one.

    A `bytes` value writes the file binary (used by the binary-diff tests -
    `\x00` in the content is what makes git itself treat the file as binary
    and switch its diff output to the no-hunk-header `Binary files ... differ`
    shape)."""
    _run_git(project, "init", "-q")
    _run_git(project, "config", "user.email", "fence-test@example.com")
    _run_git(project, "config", "user.name", "Fence Test")
    for relative, content in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        _run_git(project, "add", relative)
    _run_git(project, "commit", "-q", "-m", "initial")


class OutOfFenceHunkTests(unittest.TestCase):
    def test_an_edit_to_an_unfenced_file_names_it_with_a_hunk_count(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n", "b.py": "b = 1\n"})
            _approved_plan(archive, "a.py")
            (project / "a.py").write_text("a = 2\n", encoding="utf-8")
            (project / "b.py").write_text("b = 2\n", encoding="utf-8")
            report = completion_audit(archive, project)
        out_of_fence = [f for f in report["findings"] if f["kind"] == "out-of-fence-hunk"]
        self.assertEqual(len(out_of_fence), 1, report["findings"])
        self.assertEqual(out_of_fence[0]["path"], "b.py")
        self.assertEqual(out_of_fence[0]["hunks"], 1)

    def test_the_in_fence_file_raises_nothing_of_its_own(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n", "b.py": "b = 1\n"})
            _approved_plan(archive, "a.py")
            (project / "a.py").write_text("a = 2\n", encoding="utf-8")
            (project / "b.py").write_text("b = 2\n", encoding="utf-8")
            report = completion_audit(archive, project)
        self.assertNotIn("a.py", [f["path"] for f in report["findings"]])


class BinaryDiffTests(unittest.TestCase):
    """`git diff --unified=0` emits no `@@ ... @@` header for a binary file -
    only `Binary files a/X and b/X differ` - so a hunk-only parse has to
    notice that line explicitly, or an out-of-fence binary write is not
    flagged, just never seen."""

    def test_an_unfenced_binary_change_names_the_file_and_reads_binary(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n", "b.bin": b"\x00\x01original-bytes"})
            _approved_plan(archive, "a.py")
            (project / "b.bin").write_bytes(b"\x00\x01changed-bytes-here-now")
            report = completion_audit(archive, project)
        out_of_fence = [f for f in report["findings"] if f["path"] == "b.bin"]
        self.assertEqual(len(out_of_fence), 1, report["findings"])
        self.assertEqual(out_of_fence[0]["kind"], "out-of-fence-hunk")
        self.assertEqual(out_of_fence[0]["hunks"], "binary")

    def test_a_fenced_binary_change_is_clean(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"b.bin": b"\x00\x01original-bytes"})
            _approved_plan(archive, "b.bin")
            (project / "b.bin").write_bytes(b"\x00\x01changed-bytes-here-now")
            report = completion_audit(archive, project)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "every-hunk-traces")


class UnauthorizedDeletionTests(unittest.TestCase):
    def test_a_pure_deletion_in_an_unfenced_file_is_its_own_finding_kind(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n", "c.py": "line1\nline2\nline3\n"})
            _approved_plan(archive, "a.py")
            (project / "c.py").write_text("line1\nline3\n", encoding="utf-8")
            report = completion_audit(archive, project)
        by_path = [f for f in report["findings"] if f["path"] == "c.py"]
        self.assertEqual([f["kind"] for f in by_path], ["unauthorized-deletion"], report["findings"])

    def test_the_remedy_says_mention_dont_delete(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n", "c.py": "line1\nline2\nline3\n"})
            _approved_plan(archive, "a.py")
            (project / "c.py").write_text("line1\nline3\n", encoding="utf-8")
            report = completion_audit(archive, project)
        finding = next(f for f in report["findings"] if f["kind"] == "unauthorized-deletion")
        self.assertIn("mention", finding["remedy"].lower())
        self.assertIn("not yours to remove", finding["remedy"].lower())
        self.assertEqual(finding["path"], "c.py")

    def test_a_deletion_inside_a_fenced_file_is_clean(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "line1\nline2\nline3\n"})
            _approved_plan(archive, "a.py")
            (project / "a.py").write_text("line1\nline3\n", encoding="utf-8")
            report = completion_audit(archive, project)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "every-hunk-traces")


class InstrumentationResidueTests(unittest.TestCase):
    def test_a_debug_tagged_line_is_caught_and_named_by_file_and_line(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n"})
            _approved_plan(archive, "a.py")
            (project / "a.py").write_text(
                "a = 1\nprint('[DEBUG-trace] here')\n", encoding="utf-8")
            report = completion_audit(archive, project)
        residue = [f for f in report["findings"] if f["kind"] == "instrumentation-residue"]
        self.assertEqual(len(residue), 1, report["findings"])
        self.assertEqual(residue[0]["path"], "a.py")
        self.assertEqual(residue[0]["line"], 2)
        self.assertIn("a.py:2", residue[0]["detail"])

    def test_a_debug_tag_is_caught_even_when_the_file_is_outside_the_fence(self) -> None:
        """Independent of the fence question: the sweep looks at every added
        line, not only the ones landing where the plan already said it may."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n", "b.py": "b = 1\n"})
            _approved_plan(archive, "a.py")
            (project / "b.py").write_text(
                "b = 1\nprint('[DEBUG-x]')\n", encoding="utf-8")
            report = completion_audit(archive, project)
        kinds = [f["kind"] for f in report["findings"] if f["path"] == "b.py"]
        self.assertIn("instrumentation-residue", kinds)


class UndeclaredFenceTests(unittest.TestCase):
    def test_no_declared_fence_reads_everything_clean(self) -> None:
        """Undeclared means unenforced, the same rule `fence_verdict` already
        keeps: a fence nobody wrote cannot fence anything, so the fence-shaped
        findings stay silent rather than refusing every project that predates
        this gate."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "line1\nline2\n"})
            _approved_plan(archive, None)
            (project / "a.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
            report = completion_audit(archive, project)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["verdict"], "every-hunk-traces")

    def test_no_declared_fence_still_reports_what_it_examined(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "line1\nline2\n"})
            _approved_plan(archive, None)
            (project / "a.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
            report = completion_audit(archive, project)
        self.assertEqual(report["changes_examined"], 1)
        self.assertIsNone(report["fence"])

    def test_no_declared_fence_still_catches_a_debug_tag(self) -> None:
        """Locks in Adjudication A: the debug-tag sweep is not one of the
        fence-shaped checks that fails open when nothing is declared - it is
        its own, unconditional question, asked of every added line regardless
        of whether any plan ever declared an editable set at all."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n"})
            _approved_plan(archive, None)
            (project / "a.py").write_text(
                "a = 1\nprint('[DEBUG-trace] here')\n", encoding="utf-8")
            report = completion_audit(archive, project)
        residue = [f for f in report["findings"] if f["kind"] == "instrumentation-residue"]
        self.assertEqual(len(residue), 1, report["findings"])
        self.assertEqual(residue[0]["path"], "a.py")
        self.assertEqual(residue[0]["line"], 2)
        # And still nothing fence-shaped, since nothing was declared.
        self.assertNotIn("out-of-fence-hunk", [f["kind"] for f in report["findings"]])
        self.assertNotIn("unauthorized-deletion", [f["kind"] for f in report["findings"]])


class TagPatternExtensionTests(unittest.TestCase):
    def test_the_default_tag_patterns_include_debug(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, None)
            self.assertIn("[DEBUG-", declared_tag_patterns(archive))

    def test_a_fence_declaration_can_add_its_own_tag_pattern(self) -> None:
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "a.py, tag:[SCRATCH-")
            patterns = declared_tag_patterns(archive)
        self.assertIn("[DEBUG-", patterns)
        self.assertIn("[SCRATCH-", patterns)

    def test_a_declared_tag_pattern_is_caught_in_the_diff_too(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _init_repo(project, {"a.py": "a = 1\n"})
            _approved_plan(archive, "a.py, tag:[SCRATCH-")
            (project / "a.py").write_text(
                "a = 1\nprint('[SCRATCH-note]')\n", encoding="utf-8")
            report = completion_audit(archive, project)
        residue = [f for f in report["findings"] if f["kind"] == "instrumentation-residue"]
        self.assertEqual(len(residue), 1, report["findings"])
        self.assertEqual(residue[0]["tag"], "[SCRATCH-")

    def test_a_tag_prefixed_entry_is_not_treated_as_a_path_pattern(self) -> None:
        """`declared_fence` extends the same shared reading of the field
        rather than a parallel parser growing its own rules: a `tag:` entry
        is not a glob some file is expected to match."""
        with isolated_project() as (_project, _s, _a, archive):
            archive.initialize()
            _approved_plan(archive, "a.py, tag:[SCRATCH-")
            self.assertEqual(declared_fence(archive), ["a.py"])


@contextmanager
def _git_repo_project(files: dict[str, str]):
    """A project that is already a git repo before godmode ever resolves its
    anchor.

    `main()` re-resolves the anchor fresh on every CLI invocation, from the
    project's git status at that moment - the same field-report regression
    `test_godmode_runtime.py` guards elsewhere: a project that becomes a git
    repo after the archive was created reads as a different identity, and
    `isolated_project()` resolves its anchor immediately on entry, before a
    test gets a chance to `git init` inside it. Doing the `git init` first,
    outside that fixture, is what keeps every anchor resolution in a CLI
    test - this one and the CLI's own - looking at the same identity.
    """
    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        _init_repo(project, files)
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            yield project, archive


class ConsoleWiringTests(unittest.TestCase):
    """The CLI surface `fence audit --complete` actually reaches the audit."""

    @staticmethod
    def _run(project: Path, *argv: str) -> tuple[dict, int]:
        from godmode_runtime.godmode_console import main

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--project", str(project), *argv])
        return json.loads(buffer.getvalue()), code

    def test_fence_audit_complete_reports_an_out_of_fence_hunk_and_fails(self) -> None:
        with _git_repo_project({"a.py": "a = 1\n", "b.py": "b = 1\n"}) as (project, archive):
            archive.initialize()
            _approved_plan(archive, "a.py")
            (project / "b.py").write_text("b = 2\n", encoding="utf-8")
            payload, code = self._run(project, "fence", "audit", "--complete")
        self.assertEqual(code, 1)
        self.assertTrue(any(f["kind"] == "out-of-fence-hunk" for f in payload["findings"]))

    def test_fence_audit_complete_on_a_clean_tree_exits_zero(self) -> None:
        with _git_repo_project({"a.py": "a = 1\n"}) as (project, archive):
            archive.initialize()
            _approved_plan(archive, "a.py")
            (project / "a.py").write_text("a = 2\n", encoding="utf-8")
            payload, code = self._run(project, "fence", "audit", "--complete")
        self.assertEqual(code, 0)
        self.assertEqual(payload["findings"], [])


if __name__ == "__main__":
    unittest.main()
