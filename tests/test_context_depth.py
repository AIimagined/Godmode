from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_lens import (  # noqa: E402
    capacity_checkpoint_due,
    collect_inventory,
    detect_context_issues,
    make_snapshot,
    why,
)


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


class StalenessInputTests(unittest.TestCase):
    def test_stale_lock_file_fires_stale_lock_issue(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            archive.initialize()
            archive.append("inventory", "baseline", make_snapshot(anchor), evidence=[])
            lock = archive.root / "godmode-write.lock"
            lock.write_text("12345\n", encoding="utf-8")
            eleven_minutes_ago = time.time() - 11 * 60
            os.utime(lock, (eleven_minutes_ago, eleven_minutes_ago))
            issues = detect_context_issues(
                anchor, archive.read_events(), None, archive=archive
            )
            codes = {issue["code"] for issue in issues}
            self.assertIn("stale-lock", codes)

    def test_fresh_lock_file_stays_silent(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            archive.initialize()
            archive.append("inventory", "baseline", make_snapshot(anchor), evidence=[])
            lock = archive.root / "godmode-write.lock"
            lock.write_text("12345\n", encoding="utf-8")
            issues = detect_context_issues(
                anchor, archive.read_events(), None, archive=archive
            )
            codes = {issue["code"] for issue in issues}
            self.assertNotIn("stale-lock", codes)

    def test_mtime_regression_fires_clock_or_restore_anomaly(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            archive.initialize()
            archive.append("inventory", "baseline", make_snapshot(anchor), evidence=[])
            current = collect_inventory(project)
            for entry in current["entries"]:
                if entry["path"] == "app.py":
                    entry["mtime_ns"] -= 5_000_000_000
            issues = detect_context_issues(anchor, archive.read_events(), current)
            codes = {issue["code"] for issue in issues}
            self.assertIn("clock-or-restore-anomaly", codes)

    def test_unchanged_mtimes_stay_silent(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            archive.initialize()
            archive.append("inventory", "baseline", make_snapshot(anchor), evidence=[])
            current = collect_inventory(project)
            issues = detect_context_issues(anchor, archive.read_events(), current)
            codes = {issue["code"] for issue in issues}
            self.assertNotIn("clock-or-restore-anomaly", codes)


class CapacityTriggerTests(unittest.TestCase):
    def test_signal_fires_above_eighty_percent_of_budget(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "layout", {"choice": "flat"}, evidence=["seq:0"])
            signal = capacity_checkpoint_due(archive, token_budget=60)
            self.assertTrue(signal["due"])
            self.assertEqual(signal["budget"], 60)
            self.assertGreater(signal["estimated_tokens"], int(60 * 0.8))
            self.assertIn("detail", signal)

    def test_a_recent_checkpoint_covers_the_signal(self) -> None:
        # Field report 2026-09-04: past 80% the signal re-fired on every call
        # after the checkpoint it asked for had been written.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "layout", {"choice": "flat"}, evidence=["seq:0"])
            archive.append("checkpoint", "handoff", {"summary": "state saved"},
                           evidence=["seq:1"])
            signal = capacity_checkpoint_due(archive, token_budget=60)
            self.assertGreater(signal["estimated_tokens"], int(60 * 0.8))
            self.assertFalse(signal["due"])
            self.assertIn("covers", signal["detail"])

    def test_signal_stays_quiet_under_a_generous_budget(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "layout", {"choice": "flat"}, evidence=["seq:0"])
            signal = capacity_checkpoint_due(archive, token_budget=100_000)
            self.assertFalse(signal["due"])
            self.assertEqual(signal["budget"], 100_000)
            self.assertLessEqual(signal["estimated_tokens"], int(100_000 * 0.8))


class WhyTests(unittest.TestCase):
    def _seed(self, archive: Chronicle) -> None:
        archive.initialize()
        archive.append(
            "decision", "storage-layout",
            {"reason": "keep app.py flat instead of packaged"}, evidence=["seq:1"],
        )
        archive.append(
            "invariant", "app.py-single-writer", {"value": "one writer"}, evidence=[]
        )
        archive.append(
            "change", "refactor-io",
            {"files": ["app.py", "other.py"], "status": "open"}, evidence=[],
        )
        archive.append(
            "checkpoint", "io-race",
            {"status": "green", "detail": "app.py write race resolved"},
            evidence=["test:io"],
        )
        archive.append(
            "lesson", "flush-first", {"insight": "app.py buffers need flushing"}, evidence=[]
        )
        archive.append("decision", "palette", {"reason": "pick blue"}, evidence=[])

    def test_returns_matching_records_per_category_case_insensitively(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            self._seed(archive)
            answer = why(anchor, archive, "APP.PY")
            self.assertEqual(
                [item["subject"] for item in answer["decisions"]], ["storage-layout"]
            )
            self.assertEqual(
                [item["subject"] for item in answer["invariants"]],
                ["app.py-single-writer"],
            )
            self.assertEqual(
                [item["subject"] for item in answer["dependencies"]], ["refactor-io"]
            )
            self.assertEqual(
                sorted(item["subject"] for item in answer["fixes"]),
                ["flush-first", "io-race"],
            )
            for category in ("decisions", "fixes", "dependencies", "invariants"):
                for item in answer[category]:
                    self.assertIn("sequence", item)
                    self.assertIn("recorded_at", item)
                    self.assertTrue(item["evidence"])

    def test_unmatched_topic_returns_present_and_empty_categories(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            self._seed(archive)
            answer = why(anchor, archive, "zzz-not-in-any-record")
            for category in ("decisions", "fixes", "dependencies", "invariants"):
                self.assertIn(category, answer)
                self.assertEqual(answer[category], [])

    def test_uninitialized_archive_returns_empty_answer(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            answer = why(anchor, archive, "app.py")
            for category in ("decisions", "fixes", "dependencies", "invariants"):
                self.assertEqual(answer[category], [])


if __name__ == "__main__":
    unittest.main()
