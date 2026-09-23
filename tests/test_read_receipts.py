"""I-2: read receipts for research depth.

"read" meant README seven times in one day with nothing to show what was
actually opened. `godmode read` records the path, the line range, and a
digest of the slice - so an absorb decision that says adopt or extend can be
made to cite something that was actually read, not merely a directory that
was listed.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_absorb import validate_absorb  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_receipts import (  # noqa: E402
    receipts_for,
    record_receipt,
    sources_report,
    surface_only,
)
from godmode_runtime import godmode_console as console  # noqa: E402


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


def _write(root: Path, relative: str, content: str) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


class RecordReceiptTests(unittest.TestCase):
    def test_whole_file_digest_matches_sha256_of_content(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/thing.py", "line one\nline two\nline three\n")
            record = record_receipt(archive, str(project), "sample-source", "src/thing.py")
            self.assertEqual(record["kind"], "receipt")
            self.assertEqual(record["subject"], "sample-source:src/thing.py")
            data = record["data"]
            self.assertEqual(data["source"], "sample-source")
            self.assertEqual(data["path"], "src/thing.py")
            self.assertIsNone(data["lines"])
            expected = hashlib.sha256(
                "line one\nline two\nline three".encode("utf-8")
            ).hexdigest()
            self.assertEqual(data["digest"], expected)

    def test_line_range_records_slice_digest_and_range(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/thing.py", "a\nb\nc\nd\ne\n")
            record = record_receipt(
                archive, str(project), "sample-source", "src/thing.py", lines=(2, 3))
            data = record["data"]
            self.assertEqual(data["lines"], [2, 3])
            expected = hashlib.sha256("b\nc".encode("utf-8")).hexdigest()
            self.assertEqual(data["digest"], expected)

    def test_path_outside_project_without_root_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            outside = project.parent / "elsewhere"
            _write(outside, "secret.py", "print('nope')\n")
            with self.assertRaises(ArchiveError):
                record_receipt(archive, str(project), "sample-source",
                                str(outside / "secret.py"))

    def test_path_outside_project_with_matching_root_is_recorded(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            outside = project.parent / "vendor-source"
            _write(outside, "lib/core.py", "def core():\n    return 1\n")
            record = record_receipt(
                archive, str(project), "sample-source",
                str(outside / "lib" / "core.py"), root=str(outside))
            self.assertEqual(record["data"]["source"], "sample-source")

    def test_path_outside_the_given_root_is_still_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            outside = project.parent / "vendor-source"
            somewhere_else = project.parent / "unrelated"
            _write(somewhere_else, "file.py", "x = 1\n")
            outside.mkdir()
            with self.assertRaises(ArchiveError):
                record_receipt(
                    archive, str(project), "sample-source",
                    str(somewhere_else / "file.py"), root=str(outside))

    def test_missing_file_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_receipt(archive, str(project), "sample-source", "src/does-not-exist.py")


class ReceiptsForAndSurfaceOnlyTests(unittest.TestCase):
    def test_receipts_for_filters_by_source_only(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/a.py", "a = 1\n")
            _write(project, "src/b.py", "b = 1\n")
            record_receipt(archive, str(project), "sample-source", "src/a.py")
            record_receipt(archive, str(project), "other-source", "src/b.py")
            mine = receipts_for(archive, "sample-source")
            self.assertEqual(len(mine), 1)
            self.assertEqual(mine[0]["data"]["path"], "src/a.py")

    def test_surface_only_true_when_every_path_is_readme_or_docs(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "README.md", "# hello\n")
            _write(project, "docs/guide.md", "guide\n")
            record_receipt(archive, str(project), "sample-source", "README.md")
            record_receipt(archive, str(project), "sample-source", "docs/guide.md")
            self.assertTrue(surface_only(receipts_for(archive, "sample-source")))

    def test_surface_only_false_when_a_source_path_is_present(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "README.md", "# hello\n")
            _write(project, "src/core.py", "def core():\n    pass\n")
            record_receipt(archive, str(project), "sample-source", "README.md")
            record_receipt(archive, str(project), "sample-source", "src/core.py")
            self.assertFalse(surface_only(receipts_for(archive, "sample-source")))

    def test_surface_only_false_for_no_receipts(self) -> None:
        self.assertFalse(surface_only([]))


class ValidateAbsorbReceiptCiteTests(unittest.TestCase):
    def test_receipt_cite_of_a_source_path_satisfies_adopt(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/core.py", "def core():\n    pass\n")
            record_receipt(archive, str(project), "sample-source", "src/core.py")
            gaps = validate_absorb(
                "import_verdict: adopt. behaviour_verdict: unverified.",
                ["receipt:sample-source:src/core.py"],
                archive,
            )
            self.assertEqual(gaps, [])

    def test_receipt_cite_of_a_readme_only_is_refused_surface_only(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "README.md", "# hello\n")
            record_receipt(archive, str(project), "sample-source", "README.md")
            gaps = validate_absorb(
                "import_verdict: adopt. behaviour_verdict: unverified.",
                ["receipt:sample-source:README.md"],
                archive,
            )
            self.assertIn("surface-only", gaps)

    def test_receipt_cite_with_no_archive_does_not_satisfy_adopt(self) -> None:
        # Backward-compatible default: an omitted archive settles nothing new.
        gaps = validate_absorb(
            "import_verdict: adopt. behaviour_verdict: unverified.",
            ["receipt:sample-source:src/core.py"],
        )
        self.assertIn("adopt_or_extend_needs_source_cite", gaps)


class ConsoleWiringTests(unittest.TestCase):
    def test_godmode_read_verb_appends_a_receipt(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/core.py", "def core():\n    pass\n")
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            args = console._build_parser().parse_args([
                "read", "--source", "sample-source", "--path", "src/core.py"])
            result = console.cmd_read(args, runtime)
            self.assertEqual(result.payload["record"]["kind"], "receipt")
            self.assertEqual(result.payload["record"]["data"]["path"], "src/core.py")

    def test_godmode_read_with_lines_flag(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/core.py", "a\nb\nc\nd\n")
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            args = console._build_parser().parse_args([
                "read", "--source", "sample-source", "--path", "src/core.py",
                "--lines", "2-3"])
            result = console.cmd_read(args, runtime)
            self.assertEqual(result.payload["record"]["data"]["lines"], [2, 3])

    def test_remember_absorb_decision_citing_source_receipt_persists_verdicts(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/core.py", "def core():\n    pass\n")
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            read_args = console._build_parser().parse_args([
                "read", "--source", "sample-source", "--path", "src/core.py"])
            console.cmd_read(read_args, runtime)
            remember_args = console._build_parser().parse_args([
                "remember", "--kind", "decision", "--subject", "absorb:widget",
                "--value", "import_verdict: adopt. behaviour_verdict: unverified.",
                "--evidence", "receipt:sample-source:src/core.py"])
            console.cmd_remember(remember_args, runtime)
            record = archive.read_events()[-1]
            self.assertEqual(record["data"].get("import_verdict"), "adopt")

    def test_remember_absorb_decision_citing_readme_only_receipt_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "README.md", "# hello\n")
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            read_args = console._build_parser().parse_args([
                "read", "--source", "sample-source", "--path", "README.md"])
            console.cmd_read(read_args, runtime)
            remember_args = console._build_parser().parse_args([
                "remember", "--kind", "decision", "--subject", "absorb:widget",
                "--value", "import_verdict: adopt. behaviour_verdict: unverified.",
                "--evidence", "receipt:sample-source:README.md"])
            with self.assertRaises(ArchiveError) as ctx:
                console.cmd_remember(remember_args, runtime)
            self.assertIn("surface-only", str(ctx.exception))

    def test_parity_sources_reports_files_opened_and_surface_only(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/core.py", "def core():\n    pass\n")
            _write(project, "README.md", "# hello\n")
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            for source, path in (
                ("sample-source", "src/core.py"),
                ("docs-only-source", "README.md"),
            ):
                args = console._build_parser().parse_args([
                    "read", "--source", source, "--path", path])
                console.cmd_read(args, runtime)
            args = console._build_parser().parse_args(["parity", "--sources"])
            result = console.cmd_parity(args, runtime)
            sources = result.payload["sources"]
            self.assertEqual(sources["sample-source"]["files_opened"], 1)
            self.assertFalse(sources["sample-source"]["surface_only"])
            self.assertEqual(sources["docs-only-source"]["files_opened"], 1)
            self.assertTrue(sources["docs-only-source"]["surface_only"])

    def test_sources_report_direct_call_matches_console(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/core.py", "def core():\n    pass\n")
            record_receipt(archive, str(project), "sample-source", "src/core.py")
            report = sources_report(archive)
            self.assertEqual(report["sources"]["sample-source"]["files_opened"], 1)


if __name__ == "__main__":
    unittest.main()
