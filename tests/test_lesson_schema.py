"""NS-10j (0.3.28 Plan 5 Task 2): a lesson's structured schema.

`root_cause`, `correction`, `reflection`, `guard` (stored as
`generalized_guard`), `falsifier` (stored as `refuted_by`) - a lesson
missing any of the five is written as `status: candidate`, never refused.
Opting into the schema at all is what `remember --kind lesson` reads: a
plain `--guard`-only lesson (enforce predicates, standing guards - the
pre-existing advisory shape Task 4 and the earlier sprints already ship
and test) is untouched by this rule.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_console import main as console_main  # noqa: E402
from godmode_runtime.godmode_lessons import (  # noqa: E402
    missing_structured_fields, normalize_lesson_write,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _console_json(project: Path, argv: list[str]) -> dict:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
        code = console_main(["--project", str(project)] + argv)
    return {"exit_code": code, **json.loads(out.getvalue())}


_ALL_FIELDS = {
    "root_cause": "the check ran before the file existed",
    "correction": "create the file first, then run the check",
    "reflection": "any ordering-sensitive check needs its precondition named",
    "generalized_guard": "verify the precondition before running the check",
    "refuted_by": "the check passes even when the precondition is absent",
}


class MissingFieldsTests(unittest.TestCase):
    def test_a_complete_lesson_is_missing_nothing(self) -> None:
        self.assertEqual(missing_structured_fields(dict(_ALL_FIELDS)), [])

    def test_a_blank_field_counts_as_missing(self) -> None:
        data = dict(_ALL_FIELDS)
        data["reflection"] = "   "
        self.assertEqual(missing_structured_fields(data), ["reflection"])

    def test_missing_fields_are_named_by_their_spec_name_not_the_archive_key(self) -> None:
        data = dict(_ALL_FIELDS)
        del data["generalized_guard"]
        del data["refuted_by"]
        self.assertEqual(sorted(missing_structured_fields(data)), ["falsifier", "guard"])


class NormalizeWriteTests(unittest.TestCase):
    def test_incomplete_lesson_is_forced_to_candidate(self) -> None:
        data = {"status": "active", "generalized_guard": "g"}
        normalize_lesson_write(data)
        self.assertEqual(data["status"], "candidate")

    def test_complete_lesson_keeps_its_requested_status(self) -> None:
        data = {"status": "active", **_ALL_FIELDS}
        normalize_lesson_write(data)
        self.assertEqual(data["status"], "active")

    def test_incomplete_lesson_overrides_an_explicit_active_status(self) -> None:
        # "never refused at candidate stage": the write still succeeds, but
        # an incomplete lesson does not get to claim `active` just by
        # asking for it.
        data = {"status": "active", "generalized_guard": "g",
                "root_cause": "x", "correction": "y"}
        normalize_lesson_write(data)
        self.assertEqual(data["status"], "candidate")


class RememberCliTests(unittest.TestCase):
    def test_incomplete_structured_lesson_becomes_candidate_via_cli(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            result = _console_json(project, [
                "remember", "--kind", "lesson", "--subject", "ordering-check",
                "--value", "v", "--guard", _ALL_FIELDS["generalized_guard"],
                "--root-cause", _ALL_FIELDS["root_cause"],
                # --correction, --reflection, --falsifier all omitted.
            ])
            self.assertEqual(result["exit_code"], 0)
            lessons = [r for r in archive.read_events() if r["kind"] == "lesson"]
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["data"]["status"], "candidate")

    def test_complete_structured_lesson_via_cli_defaults_active(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            result = _console_json(project, [
                "remember", "--kind", "lesson", "--subject", "ordering-check",
                "--value", "v",
                "--guard", _ALL_FIELDS["generalized_guard"],
                "--root-cause", _ALL_FIELDS["root_cause"],
                "--correction", _ALL_FIELDS["correction"],
                "--reflection", _ALL_FIELDS["reflection"],
                "--falsifier", _ALL_FIELDS["refuted_by"],
            ])
            self.assertEqual(result["exit_code"], 0)
            lessons = [r for r in archive.read_events() if r["kind"] == "lesson"]
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["data"]["status"], "active")
        self.assertEqual(lessons[0]["data"]["refuted_by"], _ALL_FIELDS["refuted_by"])

    def test_legacy_guard_only_lesson_is_untouched_by_the_schema_rule(self) -> None:
        # No --root-cause/--correction/--reflection/--falsifier at all: the
        # pre-existing advisory shape (enforce predicates, standing guards)
        # never opts into NS-10j's completeness rule.
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            result = _console_json(project, [
                "remember", "--kind", "lesson", "--subject", "advisory-only",
                "--value", "v", "--guard", "quote every path",
            ])
            self.assertEqual(result["exit_code"], 0)
            lessons = [r for r in archive.read_events() if r["kind"] == "lesson"]
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["data"]["status"], "active")
        self.assertNotIn("root_cause", lessons[0]["data"])


if __name__ == "__main__":
    unittest.main()
