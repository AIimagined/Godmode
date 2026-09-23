"""NS-12e: pattern records.

Recurring failure modes as records that ACCUMULATE. The archive is
append-only, so a second sighting of the same subject cannot rewrite the
first pattern record - `remember --kind pattern` on an existing subject
writes a NEW record whose `occurrences` carries the whole history so far,
never a duplicate. `history --kind pattern` is the unfolded evolution log
(every occurrence as its own record); `index patterns` is the folded index
(one row per subject, latest wins). A preflight finding whose `class`
names a pattern's `subject` gets that pattern's workaround folded into its
detail, so a recurring failure class is not rediscovered from scratch.
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

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_mistakes import (  # noqa: E402
    FAILURE_CLASSES,
    list_patterns,
    record_pattern,
)
from godmode_runtime.godmode_preflight import pattern_workaround_findings  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _run(project: Path, argv: list[str]) -> int:
    with mock.patch.object(sys, "stdout", io.StringIO()), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        return console.main(["--project", str(project), *argv])


def _payload(project: Path, argv: list[str]) -> dict:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        console.main(["--project", str(project), *argv])
    return json.loads(out.getvalue())


class PatternCreateTests(unittest.TestCase):
    def test_remember_pattern_creates_a_record_with_one_occurrence(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code = _run(project, [
                "remember", "--kind", "pattern", "--subject", "windows-path-quote",
                "--value", "quote paths before shlex on windows",
                "--class", "malformed-invocation", "--occurrence", "seq:1",
            ])
            self.assertEqual(code, 0)
            records = [r for r in archive.read_events() if r["kind"] == "pattern"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["occurrences"], [1])
            self.assertEqual(records[0]["data"]["class"], "malformed-invocation")
            self.assertEqual(records[0]["data"]["workaround"],
                             "quote paths before shlex on windows")
            self.assertEqual(records[0]["subject"], "windows-path-quote")

    def test_an_off_list_class_is_refused_with_the_list(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as caught:
                record_pattern(archive, "some-subject", "workaround", "vibes")
            self.assertIn(FAILURE_CLASSES[0], str(caught.exception))

    def test_missing_class_flag_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            code = _run(project, [
                "remember", "--kind", "pattern", "--subject", "no-class",
                "--value", "workaround", "--occurrence", "seq:1",
            ])
            self.assertEqual(code, 2)
            self.assertEqual([r for r in archive.read_events() if r["kind"] == "pattern"], [])


class PatternAppendNotDuplicateTests(unittest.TestCase):
    def test_a_second_occurrence_on_the_same_subject_appends_not_duplicates(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(_run(project, [
                "remember", "--kind", "pattern", "--subject", "flaky-retry-x",
                "--value", "retry with backoff", "--class", "environment-failure",
                "--occurrence", "seq:1",
            ]), 0)
            self.assertEqual(_run(project, [
                "remember", "--kind", "pattern", "--subject", "flaky-retry-x",
                "--value", "retry with backoff, longer this time",
                "--class", "environment-failure", "--occurrence", "seq:2",
            ]), 0)
            records = [r for r in archive.read_events()
                       if r["kind"] == "pattern" and r["subject"] == "flaky-retry-x"]
            self.assertEqual(len(records), 2, "each occurrence is its own record - the "
                              "evolution log, never an overwrite")
            self.assertEqual(records[-1]["data"]["occurrences"], [1, 2])

    def test_a_different_subject_never_shares_the_occurrence_list(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(_run(project, [
                "remember", "--kind", "pattern", "--subject", "subject-a",
                "--value", "fix a", "--class", "goal-misread", "--occurrence", "seq:1",
            ]), 0)
            self.assertEqual(_run(project, [
                "remember", "--kind", "pattern", "--subject", "subject-b",
                "--value", "fix b", "--class", "goal-misread", "--occurrence", "seq:2",
            ]), 0)
            subjects = {r["subject"]: r["data"]["occurrences"]
                        for r in archive.read_events() if r["kind"] == "pattern"}
            self.assertEqual(subjects, {"subject-a": [1], "subject-b": [2]})


class PatternRaceTests(unittest.TestCase):
    """Fix round 1 (review finding 1): the occurrence fold in `record_pattern`
    happens outside `archive.write_lock()` (nesting it would stall on
    `append`'s own, non-reentrant lock), so two same-subject calls whose
    folds interleave with each other's appends must never lose an
    occurrence. Simulated deterministically - wall-clock free - by making
    `archive.append` itself write the "concurrent" record on its first
    call, before the call under test's own write lands, so the interloper's
    sequence falls strictly between the fold's high-water mark and this
    call's own append.
    """

    def test_a_concurrent_same_subject_write_between_the_fold_and_the_append_is_not_lost(
        self,
    ) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            real_append = archive.append
            injected = {"done": False}

            def racing_append(kind, subject, data, **kwargs):
                if kind == "pattern" and not injected["done"]:
                    injected["done"] = True
                    # A second `record_pattern` call for the same subject
                    # that folded the same (empty) prior state as this one
                    # and landed its own append first - the exact race the
                    # review's finding 1 describes.
                    real_append(
                        "pattern", subject,
                        {"workaround": "concurrent fix",
                         "class": "environment-failure", "occurrences": [2]},
                    )
                return real_append(kind, subject, data, **kwargs)

            with mock.patch.object(archive, "append", side_effect=racing_append):
                record_pattern(
                    archive, "race-subject", "first fix", "environment-failure",
                    occurrence=1,
                )

            rows = {row["subject"]: row for row in list_patterns(archive)}
            self.assertEqual(
                rows["race-subject"]["occurrences"], [1, 2],
                "the interloper's occurrence must survive as a merged, "
                "superseding record - not be dropped by the race")
            history = [r for r in archive.read_events()
                       if r["kind"] == "pattern" and r["subject"] == "race-subject"]
            # Evolution log: the interloper's record, this call's own
            # (incomplete) fold result, and the merge supersede - all three
            # kept, never rewritten.
            self.assertEqual(len(history), 3)
            self.assertEqual(history[-1]["data"]["occurrences"], [1, 2])

    def test_a_retried_remember_with_identical_payload_does_not_grow_the_chain(
        self,
    ) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = record_pattern(
                archive, "retry-subject", "retry with backoff",
                "environment-failure", occurrence=1,
            )
            second = record_pattern(
                archive, "retry-subject", "retry with backoff",
                "environment-failure", occurrence=1,
            )
            self.assertTrue(second.get("deduplicated"))
            history = [r for r in archive.read_events()
                       if r["kind"] == "pattern" and r["subject"] == "retry-subject"]
            self.assertEqual(len(history), 1, "an exact retry (same subject, "
                              "class, workaround, occurrence) must not grow "
                              "the chain")
            self.assertEqual(first["sequence"], history[0]["sequence"])


class PatternHistoryTests(unittest.TestCase):
    def test_history_kind_pattern_lists_every_occurrence_record(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for seq in (1, 2):
                self.assertEqual(_run(project, [
                    "remember", "--kind", "pattern", "--subject", "recurring-x",
                    "--value", "workaround", "--class", "capability-gap",
                    "--occurrence", f"seq:{seq}",
                ]), 0)
            payload = _payload(project, ["history", "--kind", "pattern"])
            self.assertEqual(len(payload["records"]), 2)
            self.assertTrue(all(r["kind"] == "pattern" for r in payload["records"]))


class PatternIndexTests(unittest.TestCase):
    def test_index_patterns_folds_to_the_latest_per_subject(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            for seq in (1, 2, 3):
                self.assertEqual(_run(project, [
                    "remember", "--kind", "pattern", "--subject", "recurring-y",
                    "--value", "later workaround", "--class", "underspecified-ask",
                    "--occurrence", f"seq:{seq}",
                ]), 0)
            payload = _payload(project, ["index", "patterns"])
            rows = payload["patterns"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["subject"], "recurring-y")
            self.assertEqual(rows[0]["occurrence_count"], 3)
            self.assertEqual(rows[0]["occurrences"], [1, 2, 3])
            self.assertEqual(rows[0]["workaround"], "later workaround")


class PreflightPatternMappingTests(unittest.TestCase):
    def test_a_finding_whose_class_matches_a_pattern_subject_gets_the_workaround(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_pattern(archive, "malformed-invocation",
                           "quote windows paths before shlex",
                           "malformed-invocation", occurrence=1)
            findings = [{"check": "some-check", "class": "malformed-invocation",
                        "detail": "a shlex parse failed"}]
            pattern_workaround_findings(findings, archive)
            self.assertIn("quote windows paths before shlex", findings[0]["detail"])

    def test_a_finding_with_no_matching_pattern_is_untouched(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            findings = [{"check": "some-check", "class": "environment-failure",
                        "detail": "the host broke"}]
            pattern_workaround_findings(findings, archive)
            self.assertEqual(findings[0]["detail"], "the host broke")


class PatternInvariantTests(unittest.TestCase):
    def test_a_pattern_with_no_class_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("pattern", "no-class-subject",
                               {"workaround": "w", "occurrences": [1]})

    def test_a_pattern_with_no_occurrences_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("pattern", "no-occurrences-subject",
                               {"workaround": "w", "class": "goal-misread", "occurrences": []})

    def test_a_pattern_with_a_non_positive_occurrence_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("pattern", "bad-occurrence-subject",
                               {"workaround": "w", "class": "goal-misread",
                                "occurrences": [0]})


if __name__ == "__main__":
    unittest.main()
