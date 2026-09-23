"""Three agentic metrics are exact ratios over chronicle records; no judge, no
estimate - and every record the fixtures seed matches a REAL writer's shape
(no `gate`/`tier`/`path` field invented that no writer actually emits).
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_metrics import metrics  # noqa: E402
from godmode_runtime.godmode_trends import trends_report  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _approve_plan(archive, editable: str = "src/**") -> None:
    # `declared_fence` (and this metric's own `_fence_from`) only fences the
    # most recently APPROVED plan's `contract.editable` field - an OPEN plan
    # is a proposal, not an enforceable boundary
    # (godmode_fence.py:_latest_approved_editable). `editable` carries a
    # real glob ("src/**"), not a bare prefix - the fence matcher
    # (`godmode_fence._matches`) is segment-aware, not a `str.startswith`.
    archive.append("plan", "fixture plan", {
        "state": "approved", "session": "S1",
        "contract": {"editable": editable},
    })


def _edit(archive, path: str) -> None:
    # Exact shape `hooks/godmode_post_edit.py::_record_edit` writes: `path`
    # plus a distinguishing `operation` digest (fix round 2, B2 - every
    # edit used to share the subject `edit-recorded`, so the watchdog's
    # `data["operation"]`-first digest read three DIFFERENT edits as the
    # same operation repeated; a short hash prefix of the path fixes it,
    # the same remedy `agent-relay-seen` already uses for its own prompt).
    # No PreToolUse gate writer carries a path on an ordinary mutation -
    # only a deletion pre-check does, a different, narrower gate.
    archive.append("action", "edit-recorded", {
        "path": path,
        "operation": "edit:" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:12],
    }, evidence=[])


def _gate_asked(archive, category: str = "worktree-file-mutation", tier: str = "R2") -> None:
    # Exact shape `hooks/godmode_session_hook.py` (~:3724-3730) writes for a
    # cleared enforce-mode ask - `tier`/`category`/`tool`/`permission_mode`.
    # No `gate` key: that field is written only by the auto-silenced allow
    # paths (`ask_only`, inline-interpreter clearance), never by the
    # ask/capability idiom `tool_selection` actually means (see
    # `godmode_roi.py`'s own tally, which matches on subject alone).
    archive.append("action", "gate-asked", {
        "tier": tier, "category": category, "tool": "Bash", "permission_mode": "default",
    }, evidence=[])


def _capability_consumed(archive, category: str = "local-repository-change") -> None:
    # Exact shape `CapabilityBroker.consume` writes (godmode_sentinel.py
    # ~:5256-5263) for a call a minted capability authorised - also a
    # `_PROTECTED_ATTEMPT_SUBJECTS` member, and also carries no `gate`/
    # `tier` key.
    archive.append("action", "capability-consumed", {
        "category": category,
        "operation_digest": "1" * 64,
        "capability_digest": "2" * 64,
    }, evidence=[])


def _refusal(archive, category: str = "git-history-or-remote", tier: str = "R5") -> None:
    # Exact shape `record_refusal` writes for a denied protected call.
    archive.append("refusal", category, {
        "operation": "git push --force", "operation_truncated": False,
        "operation_digest": "0" * 64, "tool": "Bash", "tier": tier, "category": category,
    }, evidence=[])


def _ask(archive, digest: str, status: str) -> None:
    # Exact shape `godmode_requests.record_request`/closure writes.
    archive.append("request", f"ask:{digest}", {"digest": digest, "status": status}, evidence=[])


def seed(archive) -> None:
    _approve_plan(archive)
    # 20 edit-recorded actions (the plan-adherence sample floor): 15 inside
    # src/**, 5 outside -> 0.75, a real ratio at the minimum sample size.
    for i in range(15):
        _edit(archive, f"src/file_{i}.py")
    for i in range(5):
        _edit(archive, f"docs/file_{i}.md")
    _gate_asked(archive)                                                       # 2 protected attempts,
    _capability_consumed(archive)                                              # both real subjects
    for _ in range(2):                                                        # 2 refusals
        _refusal(archive)
    _ask(archive, "aaaa", "open")
    _ask(archive, "aaaa", "done")   # CLOSED_STATUSES member, not the literal "closed"


class AgenticMetricsTests(unittest.TestCase):
    def test_exact_ratios(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            seed(archive)
            report = metrics(archive, project, window=500)["metrics"]
            self.assertEqual(report["plan_adherence"]["value"], 0.75)        # 15 of 20 pathed edits inside src/**
            self.assertEqual(report["plan_adherence"]["meets_target"], False)  # 0.75 < target 0.9, a real reading
            # 2 refusals / (2 + 1 gate-asked + 1 capability-consumed protected attempts)
            self.assertEqual(report["tool_selection"]["value"], 0.5)
            self.assertIsNone(report["tool_selection"]["meets_target"])      # informational, never flips verdict
            # 20 edit-recorded + 1 gate-asked + 1 capability-consumed = 22 actions / 1 closed ask
            # (status "done", a CLOSED_STATUSES member, not the literal "closed")
            self.assertEqual(report["execution_efficiency"]["value"], 22.0)
            self.assertIsNone(report["execution_efficiency"]["meets_target"])

    def test_no_plan_active_is_none(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            for i in range(20):
                _edit(archive, f"src/file_{i}.py")
            report = metrics(archive, project, window=500)["metrics"]
            self.assertIsNone(report["plan_adherence"]["value"])
            self.assertEqual(report["plan_adherence"]["basis"], "no plan was active")

    def test_plan_active_zero_pathed_edits_names_both_counts(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _approve_plan(archive)
            _gate_asked(archive)  # an action record, but not `edit-recorded` - no pathed edit
            report = metrics(archive, project, window=500)["metrics"]
            self.assertIsNone(report["plan_adherence"]["value"])
            self.assertEqual(report["plan_adherence"]["basis"], "0 of 0 pathed edits while a plan was active")

    def test_a_below_floor_sample_reads_insufficient_data_not_below_target(self) -> None:
        """3-of-4 pathed edits looks like a strong below-target signal, but
        four edits is not a sample - the metric must report insufficient
        data (and never turn the overall verdict to `below-target` on this
        account) below its 20-edit floor."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _approve_plan(archive)
            for i in range(3):
                _edit(archive, f"src/file_{i}.py")
            _edit(archive, "docs/outside.md")
            report = metrics(archive, project, window=500)["metrics"]
            entry = report["plan_adherence"]
            self.assertIsNone(entry["value"])
            self.assertEqual(entry["confidence"], "insufficient-data")
            self.assertIsNone(entry["meets_target"])
            self.assertIn("3 of 4 pathed edits", entry["basis"])
            self.assertIn("sample floor", entry["basis"])

    def test_trends_rows_present(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            seed(archive)
            report = trends_report(archive, sessions=5)
            names = {row["metric"] for row in report.get("agentic", [])}
            self.assertTrue({"plan_adherence", "tool_selection", "execution_efficiency"} <= names, report)
            by_name = {row["metric"]: row for row in report["agentic"]}
            self.assertEqual(by_name["plan_adherence"]["value"], 0.75)
            self.assertEqual(by_name["tool_selection"]["value"], 0.5)
            self.assertEqual(by_name["execution_efficiency"]["value"], 22.0)
            self.assertTrue(all(row["version"] for row in report["agentic"]))


if __name__ == "__main__":
    unittest.main()
