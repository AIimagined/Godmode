"""Depth of the work-item schema (S19) and the handover/doc-trigger contracts (S20).

These tests exist because a status store that accepts any shape of item cannot
refuse a hollow one: a story too large to verify, a bug closed without a cause,
a blocked item that names no blocker. Each test pins one refusal or one derived
field so the schema stays load-bearing rather than decorative.
"""

from __future__ import annotations

from contextlib import contextmanager
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

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_reconcile import record_triggers  # noqa: E402
from godmode_runtime.godmode_status import handover, items, record_item  # noqa: E402


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


class WorkItemSchemaTests(unittest.TestCase):
    """S19: the work-item schema refuses hollow items and flags oversized ones."""

    def test_story_at_eight_points_records_split_recommended(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_item(archive, "S-1", "one giant story", "active",
                                 item_type="story", points=8)
            self.assertIn("split-recommended", record["data"]["findings"])
            # The finding reports; it never blocks the write.
            self.assertEqual(items(archive)["S-1"]["state"], "active")

    def test_thirteen_point_story_recommends_a_spike_first(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = record_item(archive, "S-2", "epic in disguise", "proposed",
                                 item_type="story", points=13)
            self.assertIn("spike-first-recommended", record["data"]["findings"])

    def test_off_scale_points_and_unknown_type_are_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                record_item(archive, "S-3", "four pointer", "active", points=4)
            with self.assertRaises(ArchiveError):
                record_item(archive, "S-3", "mislabelled", "active", item_type="task")

    def test_verified_with_acceptance_requires_evidence(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "S-4", "wire the adapter", "active",
                        item_type="story", acceptance="adapter round-trips a record")
            with self.assertRaises(ArchiveError) as caught:
                record_item(archive, "S-4", "wire the adapter", "verified")
            self.assertIn("evidence", str(caught.exception))
            done = record_item(archive, "S-4", "wire the adapter", "verified",
                               evidence=["file:adapter.py#L10"])
            self.assertEqual(done["data"]["state"], "verified")

    def test_bug_close_requires_root_cause_or_incident_citation(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "B-1", "session drops", "active", item_type="bug")
            with self.assertRaises(ArchiveError) as caught:
                record_item(archive, "B-1", "session drops", "closed")
            self.assertIn("root_cause", str(caught.exception))
            closed = record_item(archive, "B-1", "session drops", "closed",
                                 root_cause="token clock skew on refresh")
            self.assertEqual(closed["data"]["root_cause"], "token clock skew on refresh")

    def test_bug_verify_accepts_an_incident_record_as_evidence(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            incident = archive.append("incident", "prod-session-drop", {"value": "outage"})
            record_item(archive, "B-2", "session drops", "active", item_type="bug")
            done = record_item(archive, "B-2", "session drops", "verified",
                               evidence=[f"seq:{incident['sequence']}"])
            self.assertEqual(done["data"]["state"], "verified")

    def test_blocked_requires_the_exact_missing_dependency(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError) as caught:
                record_item(archive, "S-5", "needs the schema", "blocked")
            self.assertIn("blocked_on", str(caught.exception))
            blocked = record_item(archive, "S-5", "needs the schema", "blocked",
                                  blocked_on="S-4 adapter schema")
            self.assertEqual(blocked["data"]["blocked_on"], "S-4 adapter schema")


class HandoverContractTests(unittest.TestCase):
    """S20.1: handover carries repository, objective, splits, and remaining points."""

    def test_handover_includes_remaining_story_points(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_item(archive, "open-a", "still going", "active",
                        item_type="story", points=5)
            record_item(archive, "done-b", "finished", "verified",
                        item_type="story", points=3, evidence=["file:done.py"])
            view = handover(archive, project)
            self.assertEqual(view["remaining_story_points"], 5)
            self.assertIn("done-b", view["verified_completed"])
            self.assertIn("open-a", view["unverified"])
            # The pre-existing contract keys survive the extension.
            for key in ("checkpoint", "remaining", "remaining_count",
                        "complete_over", "items", "verdict"):
                self.assertIn(key, view)

    def test_handover_carries_anchor_objective_invariants_and_changes(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            archive.append("plan", "ship the adapter",
                           {"state": "approved", "session": "S-x", "contract": {}})
            archive.append("invariant", "tokens must expire", {"value": "v"},
                           evidence=["file:auth.py"])
            archive.append("change", "wire adapter",
                           {"session": "S-x", "files": ["adapter.py", "io.py"]})
            view = handover(archive, project, session="S-x", anchor=anchor)
            self.assertEqual(view["objective"], "ship the adapter")
            self.assertEqual(view["repository"]["branch"], anchor.branch)
            self.assertIn("head", view["repository"])
            self.assertIn("worktree", view["repository"])
            self.assertEqual([e["subject"] for e in view["protected_invariants"]],
                             ["tokens must expire"])
            self.assertEqual(view["changed_files"], ["adapter.py", "io.py"])

    def test_handover_without_anchor_keeps_repository_empty(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            view = handover(archive, project)
            self.assertIsNone(view["repository"])
            self.assertIsNone(view["objective"])


class RecordTriggerTests(unittest.TestCase):
    """S20: record-based doc triggers report which counterpart records are absent."""

    def test_change_without_checkpoint_is_flagged(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("change", "edit io layer", {"files": ["io.py"]})
            report = record_triggers(archive)
            rules = [entry["rule"] for entry in report["missing"]]
            self.assertIn("change-requires-checkpoint", rules)
            self.assertEqual(report["verdict"], "documentation-missing")
            archive.append("checkpoint", "io layer staged", {"status": "green"})
            settled = record_triggers(archive)
            self.assertEqual(settled["verdict"], "reconciled")
            self.assertIn("change-requires-checkpoint",
                          [entry["rule"] for entry in settled["satisfied"]])

    def test_bug_close_without_guard_and_incident_without_lesson_report(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "B-9", "flaky retry", "active", item_type="bug")
            record_item(archive, "B-9", "flaky retry", "closed",
                        root_cause="unbounded retry loop")
            archive.append("incident", "prod-retry-storm", {"value": "storm"})
            report = record_triggers(archive)
            rules = [entry["rule"] for entry in report["missing"]]
            self.assertIn("bug-close-requires-guard", rules)
            self.assertIn("incident-requires-lesson", rules)
            archive.append("lesson", "bound every retry", {"value": "v"})
            settled = record_triggers(archive)
            self.assertEqual(settled["verdict"], "reconciled")

    def test_decision_reversal_must_cite_the_earlier_decision(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            first = archive.append("decision", "storage engine", {"value": "sqlite"})
            archive.append("decision", "storage engine", {"value": "jsonl"})
            report = record_triggers(archive)
            self.assertIn("decision-reversal-requires-citation",
                          [entry["rule"] for entry in report["missing"]])
            archive.append("decision", "storage engine", {"value": "jsonl"},
                           evidence=[f"seq:{first['sequence']}"])
            settled = record_triggers(archive, base_sequence=2)
            self.assertNotIn("decision-reversal-requires-citation",
                             [entry["rule"] for entry in settled["missing"]])

    def test_base_sequence_bounds_the_window(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            archive.append("change", "old change", {"files": ["a.py"]})
            head = archive.latest()["sequence"]
            report = record_triggers(archive, base_sequence=head)
            self.assertEqual(report["verdict"], "reconciled")
            self.assertEqual(report["missing"], [])


if __name__ == "__main__":
    unittest.main()
