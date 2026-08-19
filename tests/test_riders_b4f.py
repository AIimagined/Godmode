"""B4-7 riders: flat lesson ledger, edit-count checkpoint trigger, dogfood
restore-on-next-run.

Three small mechanisms with one shape in common: each turns a habit that
lived in an operator's head (write the lesson down, checkpoint before the
diff gets huge, put the repo back after a killed test run) into a mechanical
one.
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

from test_godmode_runtime import isolated_project  # noqa: E402


def _console_json(project: Path, argv: list[str]) -> dict:
    from godmode_runtime import godmode_console as console
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out):
        code = console.main(["--project", str(project)] + argv)
    return {"exit_code": code, **json.loads(out.getvalue())}


class LessonsFlatLedger(unittest.TestCase):
    """B4-7 rider 2: `godmode lessons add|list` - typed records into the
    chronicle, no daemon, no database; bare `lessons` keeps the existing
    promote-or-retire pipeline untouched."""

    def test_add_writes_a_lesson_record_and_list_reads_it_back(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            added = _console_json(project, [
                "lessons", "add", "quote the regex, not the shell",
                "--guard", "always single-quote sed programs in bash",
            ])
            self.assertEqual(added["exit_code"], 0)
            listed = _console_json(project, ["lessons", "list"])
            self.assertEqual(listed["exit_code"], 0)
            rows = listed["lessons"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["subject"], "quote the regex, not the shell")
            self.assertEqual(rows[0]["status"], "open")
            self.assertIn("single-quote", rows[0]["generalized_guard"])

    def test_bare_lessons_still_runs_the_pipeline(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            payload = _console_json(project, ["lessons"])
            self.assertEqual(payload["exit_code"], 0)
            # the pipeline report's own signature keys, not the ledger's rows
            self.assertIn("verdict", payload)
            self.assertIn("promoted", payload)

    def test_list_is_bounded(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            for i in range(7):
                _console_json(project, ["lessons", "add", f"lesson-{i}",
                                        "--guard", "g"])
            listed = _console_json(project, ["lessons", "list", "--limit", "3"])
            self.assertEqual(len(listed["lessons"]), 3)
            self.assertEqual(listed["lessons"][-1]["subject"], "lesson-6")


class EditCountCheckpointTrigger(unittest.TestCase):
    """B4-7 rider 1: N tracked-file mutations since the last checkpoint =>
    an advisory; with the policy declared, an auto-checkpoint (chronicled).
    Threshold is policy-tunable tighten-only: it can be lowered, never
    raised past the default."""

    def _mutate(self, project: Path, name: str) -> dict:
        import importlib
        observe = importlib.import_module("test_observe_mode")
        return observe._decide(project, "Write",
                               {"file_path": str(project / name),
                                "content": "x"})

    def test_the_counter_ticks_and_the_advisory_lands_at_the_threshold(self) -> None:
        from godmode_runtime.godmode_guardrails import mutations_since_checkpoint
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"checkpoint_every": 3}), encoding="utf-8")
            messages = []
            for i in range(3):
                result = self._mutate(project, f"f{i}.txt")
                if result["system_message"]:
                    messages.append(result["system_message"])
            self.assertEqual(mutations_since_checkpoint(archive), 3)
            self.assertTrue(any("checkpoint" in m for m in messages),
                            messages)

    def test_the_threshold_clamps_tighten_only(self) -> None:
        from godmode_runtime.godmode_guardrails import checkpoint_trigger_policy
        with isolated_project() as (project, _state, anchor, archive):
            archive.initialize()
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"checkpoint_every": 500}), encoding="utf-8")
            threshold, auto = checkpoint_trigger_policy(Path(anchor.project_root))
            self.assertEqual(threshold, 20)  # never looser than the default
            self.assertFalse(auto)

    def test_a_declared_policy_auto_checkpoints_and_resets(self) -> None:
        from godmode_runtime.godmode_guardrails import mutations_since_checkpoint
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / ".godmode-authorization-policy.json").write_text(
                json.dumps({"checkpoint_every": 2, "auto_checkpoint": True}),
                encoding="utf-8")
            self._mutate(project, "a.txt")
            self._mutate(project, "b.txt")
            checkpoints = [r for r in archive.select(kind="checkpoint", limit=50)
                           if r["subject"] == "auto-checkpoint"]
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(checkpoints[0]["data"]["mutations"], 2)
            self.assertEqual(mutations_since_checkpoint(archive), 0)

    def test_a_manual_checkpoint_resets_the_counter(self) -> None:
        from godmode_runtime.godmode_guardrails import mutations_since_checkpoint
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            self._mutate(project, "a.txt")
            self.assertEqual(mutations_since_checkpoint(archive), 1)
            done = _console_json(project, [
                "checkpoint", "--summary", "midpoint", "--status", "steady",
                "--next", "carry on"])
            self.assertEqual(done["exit_code"], 0)
            self.assertEqual(mutations_since_checkpoint(archive), 0)

    def test_a_read_only_call_never_ticks_the_counter(self) -> None:
        import importlib
        observe = importlib.import_module("test_observe_mode")
        from godmode_runtime.godmode_guardrails import mutations_since_checkpoint
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            observe._decide(project, "Bash", {"command": "git status"})
            self.assertEqual(mutations_since_checkpoint(archive), 0)


class DogfoodRestoreOnNextRun(unittest.TestCase):
    """B4-7 rider 3 (CX-5's parked M1): an EXTERNAL kill of the test process
    bypasses every in-process finally - so the NEXT run heals. The plant
    harness writes a byte-snapshot registry to disk before any plant; the
    next run's setUp restores whatever a dead run left planted."""

    def test_a_stale_registry_is_restored_and_cleared(self) -> None:
        from test_capability_register import restore_from_registry
        import base64
        probe = PLUGIN_ROOT / "tests" / ".dogfood-selfheal-probe.txt"
        registry = PLUGIN_ROOT / ".dogfood-restore.json"
        try:
            probe.write_text("PLANTED - a killed run left this", encoding="utf-8")
            registry.write_text(json.dumps({
                "tests/.dogfood-selfheal-probe.txt":
                    base64.b64encode(b"original bytes").decode("ascii"),
            }), encoding="utf-8")
            healed = restore_from_registry(PLUGIN_ROOT)
            self.assertEqual(healed, ["tests/.dogfood-selfheal-probe.txt"])
            self.assertEqual(probe.read_bytes(), b"original bytes")
            self.assertFalse(registry.exists())
        finally:
            probe.unlink(missing_ok=True)
            registry.unlink(missing_ok=True)

    def test_no_registry_means_nothing_to_heal(self) -> None:
        from test_capability_register import restore_from_registry
        registry = PLUGIN_ROOT / ".dogfood-restore.json"
        self.assertFalse(registry.exists(),
                         "a real stale registry is present - investigate "
                         "before running tests that would clear it")
        self.assertEqual(restore_from_registry(PLUGIN_ROOT), [])


if __name__ == "__main__":
    unittest.main()
