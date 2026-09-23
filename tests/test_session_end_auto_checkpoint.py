"""Session end writes a dated checkpoint even when nobody wrote one.

Field report (2026-08-27, another project): the continuity brief showed a
checkpoint from 08-16 while the project's own state file was at 08-24,
because nothing in that project's ritual writes a godmode checkpoint. Two
gaps behind that. Claude's hooks.json never registered PreCompact or
SessionEnd, so the session-end branch never ran on Claude Code at all;
and when it does run, the host's SessionEnd payload carries no summary,
so the branch declined to write anything. Now: both events are wired, and
a session end with no summary writes a counts-only checkpoint that says
it is automatic - not a handover, but dated today.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS = PLUGIN_ROOT / "hooks"
for entry in (SCRIPTS, HOOKS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-end-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.append("action", "edit", {"operation": "edit a.py", "gate": "allow"})
            yield root, archive


class SessionEndCheckpointTests(unittest.TestCase):
    def test_claude_manifest_registers_precompact_and_sessionend(self) -> None:
        manifest = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
        for event, arg in (("PreCompact", "pre-compact"), ("SessionEnd", "session-end")):
            self.assertIn(event, manifest["hooks"])
            self.assertIn(arg, json.dumps(manifest["hooks"][event]))

    def test_session_end_without_a_summary_writes_an_auto_checkpoint(self) -> None:
        with _project() as (root, archive):
            payload = json.dumps({"session_id": "s1", "hook_event_name": "SessionEnd",
                                  "cwd": str(root)})
            out = io.StringIO()
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", out):
                code = hook.main(["session-end", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(code, 0)
        self.assertEqual(len(checkpoints), 1, out.getvalue())
        data = checkpoints[0]["data"]
        self.assertTrue(data["auto"])
        self.assertEqual(data["status"], "auto")
        self.assertEqual(data["counts"].get("action"), 1)
        self.assertNotIn("edit a.py", json.dumps(checkpoints[0]))

    def test_a_summary_still_writes_a_real_checkpoint(self) -> None:
        with _project() as (root, archive):
            payload = json.dumps({"summary": "shipped the thing", "status": "done",
                                  "cwd": str(root)})
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main(["session-end", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(checkpoints[0]["subject"], "shipped the thing")
        self.assertNotIn("auto", checkpoints[0]["data"])


class PreCompactExtractedCheckpointTests(unittest.TestCase):
    """NS-11a: PreCompact must not fall silent the way it did before this -
    a compaction with no host-supplied summary now writes an auto checkpoint
    carrying the decisions/facts extracted since the last one, not just
    counts (`_session_counts` alone, session-end's own fallback)."""

    def test_precompact_without_a_summary_writes_an_extracted_auto_checkpoint(self) -> None:
        with _project() as (root, archive):
            archive.append(
                "decision", "storage-choice",
                {"value": "sqlite for now", "status": "active"}, evidence=["seq:1"],
            )
            archive.append(
                "invariant", "single-writer",
                {"value": "one writer per subject"}, evidence=[],
            )
            payload = json.dumps({"session_id": "s1", "hook_event_name": "PreCompact",
                                  "cwd": str(root)})
            out = io.StringIO()
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", out):
                code = hook.main(["pre-compact", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(code, 0)
        self.assertEqual(len(checkpoints), 1, out.getvalue())
        data = checkpoints[0]["data"]
        self.assertTrue(data["auto"])
        extracted = data["extracted"]
        self.assertEqual(
            [item["subject"] for item in extracted["decisions"]], ["storage-choice"])
        self.assertEqual(extracted["decisions"][0]["value"], "sqlite for now")
        self.assertEqual(
            [item["subject"] for item in extracted["facts"]], ["single-writer"])
        # Never the raw edit action - the extraction is bounded to
        # decisions/facts, exactly like `_session_counts` is bounded to
        # numbers only.
        self.assertNotIn("edit a.py", json.dumps(checkpoints[0]))

    def test_precompact_with_a_summary_still_carries_extracted_facts(self) -> None:
        with _project() as (root, archive):
            archive.append(
                "decision", "storage-choice",
                {"value": "sqlite for now", "status": "active"}, evidence=["seq:1"],
            )
            payload = json.dumps({"summary": "about to compact", "cwd": str(root)})
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main(["pre-compact", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(checkpoints[0]["subject"], "about to compact")
        self.assertNotIn("auto", checkpoints[0]["data"])
        self.assertEqual(
            [item["subject"] for item in checkpoints[0]["data"]["extracted"]["decisions"]],
            ["storage-choice"])

    def test_the_bound_keeps_the_newest_and_says_what_it_dropped(self) -> None:
        # B2: the bound used to keep the FIRST twenty decisions since the
        # last checkpoint and discard every later one in silence, which
        # inverts what a compaction checkpoint is for - the recent window
        # is the one about to be destroyed. Twenty-five decisions in; the
        # newest twenty out, and `omitted` says five were left behind.
        with _project() as (root, archive):
            for index in range(25):
                archive.append("decision", f"topic-{index:02d}", {"value": f"v{index}"})
            payload = json.dumps({"session_id": "s1", "hook_event_name": "PreCompact",
                                  "cwd": str(root)})
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", io.StringIO()):
                code = hook.main(["pre-compact", "--project", str(root)])
            checkpoints = [r for r in archive.read_events() if r["kind"] == "checkpoint"]
        self.assertEqual(code, 0)
        extracted = checkpoints[0]["data"]["extracted"]
        subjects = [item["subject"] for item in extracted["decisions"]]
        self.assertEqual(len(subjects), 20)
        self.assertEqual(subjects[0], "topic-05")
        self.assertEqual(subjects[-1], "topic-24")
        self.assertEqual(extracted["omitted"], {"decisions": 5, "facts": 0})

    def test_the_summarised_sequences_are_cited_where_the_forget_pass_looks(self) -> None:
        # M3: `godmode_forget._collect_citations` reads a record's evidence
        # lists and its own top-level strings, and nothing else - the
        # extraction's sequences are ints nested three levels down under
        # `data`, so `protected_sequences` could not see one of them and a
        # checkpoint's own facts were unprotected by construction. The
        # checkpoint now restates them as `seq:` cites.
        from godmode_runtime.godmode_forget import protected_sequences
        with _project() as (root, archive):
            decision = archive.append("decision", "storage-choice", {"value": "sqlite"})
            invariant = archive.append("invariant", "single-writer", {"value": "one"})
            payload = json.dumps({"summary": "about to compact", "cwd": str(root)})
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main(["pre-compact", "--project", str(root)])
            records = archive.read_events()
        checkpoint = [r for r in records if r["kind"] == "checkpoint"][0]
        summarised = {decision["sequence"], invariant["sequence"]}
        self.assertTrue(summarised <= set(protected_sequences(records)))
        self.assertTrue(
            summarised <= {int(item.split(":")[1]) for item in checkpoint["evidence"]})


class ExtractedFactsSurviveForgettingTests(unittest.TestCase):
    """M3, end to end: what a checkpoint summarised is still resolvable
    after a forget pass rotates the hot tier.

    The interaction the coordinator flagged: `checkpoint` is protected from
    expiry, but that protects the checkpoint RECORD, not the records it
    points at. Before this fix the pointers were invisible to
    `_collect_citations`, so the protection stopped at the checkpoint's own
    door: give a summarised kind a TTL and its sequences rotate to cold
    with no refusal and no dangling-cite error. `_run_pass` below gives
    `decision` a TTL for the length of the test - the cheapest way to ask
    "what happens the day a semantic kind expires" without waiting for the
    day it does.
    """

    def test_a_checkpoints_citations_still_resolve_after_a_rotation(self) -> None:
        from godmode_runtime import godmode_forget
        from godmode_runtime.godmode_fingerprint import require_seq_cite
        with _project() as (root, archive):
            decision = archive.append("decision", "storage-choice", {"value": "sqlite"})
            payload = json.dumps({"summary": "about to compact", "cwd": str(root)})
            with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
                    mock.patch.object(sys, "stdout", io.StringIO()):
                hook.main(["pre-compact", "--project", str(root)])
            # The day a semantic kind gains a TTL, arrived early: `decision`
            # made episodic and expiring, and a `now` far enough ahead that
            # every record in this archive is past its retention. Nothing on
            # disk is edited, so the chain the pass verifies stays intact.
            ttl = {**godmode_forget.TTL_DAYS, "decision": 1}
            with mock.patch.object(godmode_forget, "TTL_DAYS", ttl), \
                    mock.patch.object(godmode_forget, "EPISODIC_KINDS", frozenset(ttl)):
                report = godmode_forget.forget(archive, now="2099-01-01T00:00:00+00:00")
            expired = report["expire"]["eligible"]
            self.assertNotIn(decision["sequence"], expired, report["expire"])
            # The pass really did rotate (the session's own `action` record
            # went), so the decision's survival is the citation protecting
            # it, not the pass declining to run.
            self.assertTrue(report["expire"]["rotated"], report["expire"])
            # And the cite the checkpoint carries still names a hot record.
            require_seq_cite(archive, f"seq:{decision['sequence']}")


if __name__ == "__main__":
    unittest.main()
