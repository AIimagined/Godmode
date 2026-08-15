"""U-B2: protected-evaluator hash pins - never optimize the instrument.

Anything may be optimized except the measuring instrument. A pin names a
file (normally the evaluator/grader a change is judged against) and freezes
it two ways: an Edit/Write payload targeting a pinned path is denied at the
hook, before the fence even gets a look, and a plain write that reaches the
file some other way (a shell command the hook does not gate, an edit made
while the hook was disabled, a human's own text editor) is caught after the
fact by the integrity monitor's pin-drift check.

Pin records are archived (hash-chained, `kind="pin"`), which is authoritative;
`.godmode-protected.json` is a convenience view nothing here ever reads back
to decide anything - only compared against, by the monitor, to catch a
hand-edit that tried to unpin (or forge a pin) outside `protect`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_console import Runtime, cmd_protect  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError, AuthorizationError  # noqa: E402
from godmode_runtime.godmode_integrity import pin_drift  # noqa: E402
from godmode_runtime.godmode_plan import CONTRACT_FIELDS, approve, specify, start  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker,
    PIN_POLICY_FILENAME,
    classify_action,
    pin_evaluator,
    pinned_evaluators,
    unpin_evaluator,
    unpin_operation_text,
)
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"
SPEC = {"objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n"}


def _write_evaluator(project: Path, body: str = "def score():\n    return 1\n") -> Path:
    target = project / "evaluator.py"
    target.write_text(body, encoding="utf-8")
    return target


class PinStoreTests(unittest.TestCase):
    """Pin/unpin records land in the archive, and fold correctly."""

    def test_pinning_records_the_files_own_hash(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            import hashlib
            expected = hashlib.sha256(target.read_bytes()).hexdigest()
            result = pin_evaluator(archive, project, "evaluator.py")
            self.assertEqual(result["sha256"], expected)
            self.assertEqual(pinned_evaluators(archive), {"evaluator.py": expected})

    def test_the_convenience_view_is_written(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            view = json.loads((project / PIN_POLICY_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(view["evaluators"][0]["path"], "evaluator.py")

    def test_unpinning_removes_it_from_the_fold(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            unpin_evaluator(archive, project, "evaluator.py")
            self.assertEqual(pinned_evaluators(archive), {})

    def test_pinning_a_nonexistent_file_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(AuthorizationError):
                pin_evaluator(archive, project, "does-not-exist.py")

    def test_unpinning_something_not_pinned_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(AuthorizationError):
                unpin_evaluator(archive, project, "evaluator.py")

    def test_pinning_outside_the_project_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(AuthorizationError):
                pin_evaluator(archive, project, "../outside.py")


class RecordShapeInvariantTests(unittest.TestCase):
    """godmode_invariants._pin_invariants: a malformed pin record is refused
    at write time, not left to silently enforce nothing."""

    def test_a_pin_record_with_no_digest_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("pin", "evaluator:x.py", {"action": "pin", "path": "x.py"})

    def test_a_pin_record_with_a_malformed_digest_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "pin", "evaluator:x.py",
                    {"action": "pin", "path": "x.py", "sha256": "not-hex"},
                )

    def test_an_unrecognised_action_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append("pin", "evaluator:x.py", {"action": "freeze", "path": "x.py"})

    def test_an_unpin_record_needs_no_digest(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record = archive.append("pin", "evaluator:x.py", {"action": "unpin", "path": "x.py"})
            self.assertEqual(record["kind"], "pin")


class ClassifyIntegrationTests(unittest.TestCase):
    """`_categorize`'s edit branch: a pin outranks everything else that
    branch checks, and only the pinned path is affected."""

    def test_editing_a_pinned_file_is_a_hard_protected_category(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                f"write file {target}", project_root=project, archive=archive)
            self.assertTrue(verdict["protected"])
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")
            self.assertEqual(verdict["tier"], "R5")
            self.assertIn("pinned evaluator", " ".join(verdict["impact"]))

    def test_a_redirected_write_at_a_pinned_path_is_caught_too(self) -> None:
        """Not only the host's own Edit/Write - a shell redirect at the same
        path is the same act, judged the same way."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                "echo cheat > evaluator.py", project_root=project, archive=archive)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")

    def test_a_non_pinned_neighbor_is_unaffected(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            other = project / "other.py"
            other.write_text("x = 1\n", encoding="utf-8")
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                f"write file {other}", project_root=project, archive=archive)
            self.assertFalse(verdict["protected"])
            self.assertEqual(verdict["category"], "worktree-file-mutation")

    def test_with_no_archive_a_pinned_edit_reads_as_ordinary(self) -> None:
        """A pin can only be enforced where its ledger is reachable - the
        same fail-open-to-ordinary-classification shape every other
        archive-free `classify_action` call already has."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(f"write file {target}", project_root=project)
            self.assertEqual(verdict["category"], "worktree-file-mutation")

    def test_unpin_operation_text_classifies_as_protected_r5(self) -> None:
        verdict = classify_action(unpin_operation_text("evaluator.py"))
        self.assertTrue(verdict["protected"])
        self.assertEqual(verdict["category"], "evaluator-unpin")
        self.assertEqual(verdict["tier"], "R5")


class HookDenialTests(unittest.TestCase):
    """The real PreToolUse payload, driven through the real hook process -
    the same crossing test_hook_end_to_end.py's own module docstring argues
    for: a case only passes here by working the way it will in a session."""

    def setUp(self) -> None:
        self._holder = tempfile.TemporaryDirectory(prefix="godmode-pin-hook-")
        self.project = Path(self._holder.name)
        for command in (["init", "-q"], ["config", "user.email", "d@e.invalid"],
                        ["config", "user.name", "d"]):
            subprocess.run(["git", *command], cwd=self.project, capture_output=True)
        self.evaluator = self.project / "evaluator.py"
        self.evaluator.write_text("def score():\n    return 1\n", encoding="utf-8")
        self.other = self.project / "other.py"
        self.other.write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.project, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"],
                       cwd=self.project, capture_output=True)
        self._environment = dict(os.environ)
        self.state = self.project.parent / (self.project.name + "-state")
        os.environ["GODMODE_STATE_HOME"] = str(self.state)
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / "godmode.py"),
             "--project", str(self.project), "init"],
            capture_output=True, text=True, env=os.environ)
        assert done.returncode == 0, f"init failed: {done.stderr or done.stdout}"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._environment)
        self._holder.cleanup()

    def _pin(self, path: str) -> None:
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / "godmode.py"),
             "--project", str(self.project), "protect", "--pin", path],
            capture_output=True, text=True, env=os.environ)
        assert done.returncode == 0, f"pin failed: {done.stderr or done.stdout}"

    def _decide(self, tool: str, file_path: Path) -> tuple[str, str]:
        payload = {
            "hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"file_path": str(file_path)}, "cwd": str(self.project),
        }
        done = subprocess.run(
            [sys.executable, str(HOOK), "pre-action", "--project", str(self.project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            cwd=str(self.project), env=os.environ,
        )
        body = (done.stdout or "").strip()
        if not body:
            return "allow", ""
        specific = json.loads(body).get("hookSpecificOutput") or {}
        return (str(specific.get("permissionDecision", "?")),
                str(specific.get("permissionDecisionReason", "")))

    def test_a_write_at_a_pinned_path_is_denied_naming_the_pin(self) -> None:
        self._pin("evaluator.py")
        decision, reason = self._decide("Write", self.evaluator)
        self.assertEqual(decision, "deny")
        self.assertIn("pinned evaluator", reason)

    def test_an_edit_at_a_pinned_path_is_denied_too(self) -> None:
        self._pin("evaluator.py")
        decision, reason = self._decide("Edit", self.evaluator)
        self.assertEqual(decision, "deny")
        self.assertIn("pinned evaluator", reason)

    def test_a_non_pinned_neighbor_still_allows(self) -> None:
        self._pin("evaluator.py")
        decision, _reason = self._decide("Write", self.other)
        self.assertEqual(decision, "allow")

    def test_a_pin_outranks_an_otherwise_allowing_fence(self) -> None:
        """An approved plan whose editable set covers the pinned file would
        allow the edit on fence grounds alone - the pin still denies it
        first, because `_categorize`'s edit branch checks pins before the
        hook ever reaches the fence."""
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle

        self._pin("evaluator.py")
        anchor = resolve_anchor(str(self.project))
        archive = Chronicle(anchor)
        specify(archive, "S-1", "widen the fence", SPEC)
        contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
        contract["accept"] = "cmd:x"
        contract["editable"] = "**"
        start(archive, "S-1", "widen the fence", contract)
        approve(archive, "S-1")

        decision, reason = self._decide("Write", self.evaluator)
        self.assertEqual(decision, "deny")
        self.assertIn("pinned evaluator", reason)


class CapabilityGateTests(unittest.TestCase):
    """Unpin is the operation that can defeat a pin, and is gated exactly
    like every other R5 operation - `godmode_console.cmd_protect`."""

    def _runtime(self, project, archive):
        from godmode_runtime.godmode_anchor import resolve_anchor
        return Runtime(anchor=resolve_anchor(project), archive=archive)

    def test_unpin_without_a_capability_is_refused(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            runtime = self._runtime(project, archive)
            result = cmd_protect(
                argparse.Namespace(pin=None, unpin="evaluator.py", list=False, capability=None),
                runtime,
            )
            self.assertNotEqual(result.exit_code, 0)
            self.assertFalse(result.payload["unpinned"])
            self.assertIn("evaluator.py", pinned_evaluators(archive),
                         "a refused unpin must leave the pin in force")

    def test_unpin_via_a_staged_capability_is_allowed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage(unpin_operation_text("evaluator.py"), PASSWORD)
            runtime = self._runtime(project, archive)
            result = cmd_protect(
                argparse.Namespace(pin=None, unpin="evaluator.py", list=False, capability=None),
                runtime,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.payload["unpinned"])
            self.assertEqual(pinned_evaluators(archive), {})

    def test_unpin_via_an_explicit_capability_is_allowed(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            token = broker.issue(unpin_operation_text("evaluator.py"), PASSWORD)
            runtime = self._runtime(project, archive)
            result = cmd_protect(
                argparse.Namespace(pin=None, unpin="evaluator.py", list=False, capability=token),
                runtime,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(pinned_evaluators(archive), {})

    def test_pinning_needs_no_capability(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            runtime = self._runtime(project, archive)
            result = cmd_protect(
                argparse.Namespace(pin="evaluator.py", unpin=None, list=False, capability=None),
                runtime,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.payload["pinned"])

    def test_list_reports_current_pins(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            runtime = self._runtime(project, archive)
            result = cmd_protect(
                argparse.Namespace(pin=None, unpin=None, list=True, capability=None),
                runtime,
            )
            self.assertEqual([e["path"] for e in result.payload["evaluators"]],
                             ["evaluator.py"])


class IntegrityMonitorTests(unittest.TestCase):
    """godmode_integrity.pin_drift: the half of U-B2 that catches a write
    the hook never saw."""

    def test_a_clean_pin_produces_no_findings(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            self.assertEqual(pin_drift(archive, project), [])

    def test_an_out_of_band_mutation_is_a_blocking_finding_naming_the_pin(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            # A plain filesystem write - not through any host tool, not
            # through the hook.
            (project / "evaluator.py").write_text("def score():\n    return 999\n",
                                                   encoding="utf-8")
            findings = pin_drift(archive, project)
            self.assertEqual(len(findings), 1)
            self.assertTrue(findings[0]["blocking"])
            self.assertEqual(findings[0]["path"], "evaluator.py")

    def test_a_deleted_pinned_file_is_a_blocking_finding(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            target.unlink()
            findings = pin_drift(archive, project)
            self.assertTrue(any(f["blocking"] for f in findings))

    def test_a_hand_edit_removing_a_pin_from_the_view_is_caught(self) -> None:
        """Tighten-only: a worktree edit to `.godmode-protected.json` that
        REMOVES a pin is itself caught, because the fold from the archive
        still says the file is pinned and the view no longer agrees."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            (project / PIN_POLICY_FILENAME).write_text(
                json.dumps({"evaluators": []}), encoding="utf-8")
            findings = pin_drift(archive, project)
            self.assertTrue(
                any(f["path"] == PIN_POLICY_FILENAME and f["blocking"] for f in findings))

    def test_a_hand_added_pin_in_the_view_is_also_caught(self) -> None:
        """The archive is authoritative in both directions: the view
        disagreeing with it at all is what is noticed, not only a removal."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            (project / PIN_POLICY_FILENAME).write_text(
                json.dumps({"evaluators": [
                    {"path": "evaluator.py", "sha256": "0" * 64},
                    {"path": "forged.py", "sha256": "1" * 64},
                ]}), encoding="utf-8")
            findings = pin_drift(archive, project)
            self.assertTrue(
                any(f["path"] == PIN_POLICY_FILENAME and f["blocking"] for f in findings))

    def test_no_pins_means_no_drift_work_at_all(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            self.assertEqual(pin_drift(archive, project), [])


if __name__ == "__main__":
    unittest.main()
