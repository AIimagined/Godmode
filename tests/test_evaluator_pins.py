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
    pin_file_digest,
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


class MoveCopyTests(unittest.TestCase):
    """Fix-round-1, Critical: `mv`/`cp` were absent from the mutation
    vocabulary entirely - no `_ACTION_PATTERNS` entry, no redirect, no
    `_TOOL_FILE_EDIT` match - so they fell through to the read-only default
    at R0, and an agent could overwrite (or rename away) a pinned
    evaluator's content with zero confirmation. Red-first: these are the
    review's own three exact commands, reproduced live at the classify
    level here and through the real hook subprocess in `HookDenialTests`.
    """

    def test_renaming_a_pinned_file_away_is_the_pin_denial(self) -> None:
        """The source argument, not only the destination: `mv` does not
        leave the source behind the way `cp` does, so a pinned evaluator
        renamed away is the same defeat as one overwritten."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                "mv evaluator.py evaluator_renamed.py",
                project_root=project, archive=archive)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")
            self.assertTrue(verdict["protected"])
            self.assertEqual(verdict["tier"], "R5")

    def test_overwriting_a_pinned_file_via_mv_is_the_pin_denial(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            (project / "malicious.py").write_text("def score():\n    return 999\n",
                                                   encoding="utf-8")
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                "mv malicious.py evaluator.py", project_root=project, archive=archive)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")
            self.assertTrue(verdict["protected"])

    def test_overwriting_a_pinned_file_via_cp_is_the_pin_denial(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            (project / "malicious.py").write_text("def score():\n    return 999\n",
                                                   encoding="utf-8")
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                "cp malicious.py evaluator.py", project_root=project, archive=archive)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")
            self.assertTrue(verdict["protected"])

    def test_an_ordinary_mv_between_two_unpinned_files_is_unaffected(self) -> None:
        """Green control: renaming or copying unrelated files stays
        ordinary, unprotected work - a pin must not turn every `mv`/`cp`
        into a confirmation."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            (project / "unpinned_a.py").write_text("a = 1\n", encoding="utf-8")
            verdict = classify_action(
                "mv unpinned_a.py unpinned_b.py", project_root=project, archive=archive)
            self.assertFalse(verdict["protected"])
            self.assertEqual(verdict["category"], "worktree-file-mutation")

    def test_an_ordinary_cp_stays_unaffected_too(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            (project / "unpinned_a.py").write_text("a = 1\n", encoding="utf-8")
            verdict = classify_action(
                "cp unpinned_a.py unpinned_b.py", project_root=project, archive=archive)
            self.assertFalse(verdict["protected"])

    def test_cat_on_a_pinned_file_is_still_r0(self) -> None:
        """Green control named explicitly in the fix instructions: reading a
        pinned file is not writing it."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                "cat evaluator.py", project_root=project, archive=archive)
            self.assertEqual(verdict["tier"], "R0")
            self.assertFalse(verdict["protected"])

    def test_a_target_directory_form_escalates_rather_than_guesses(self) -> None:
        """`mv -t DIR src1 src2` moves the destination out of its usual
        trailing position; this classifier does not parse which file inside
        DIR each source lands on, so it asks by name instead of reading the
        (unparsed) command as safe."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            verdict = classify_action(
                "mv -t dest a.py b.py", project_root=project, archive=archive)
            self.assertTrue(verdict["protected"])
            self.assertEqual(verdict["category"], "unknown-command")

    def test_a_help_flag_is_not_read_as_a_real_move(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            verdict = classify_action("mv --help", project_root=project, archive=archive)
            self.assertFalse(verdict["protected"])

    def test_a_quoted_destination_is_still_read_correctly(self) -> None:
        """`segment.tokens` (quote-BLANKED by `_executable_text`) would drop
        a quoted argument entirely, however short - `_move_copy_arguments`
        reads from the untouched segment text via `shlex` instead, so this
        is not misread as having only one positional argument (which would
        make the classifier read the wrong token as "last")."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            verdict = classify_action(
                'mv malicious.py "evaluator.py"', project_root=project, archive=archive)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")

    def test_a_quoted_argument_containing_a_space_does_not_break_positional_counting(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "a source.py").write_text("x = 1\n", encoding="utf-8")
            verdict = classify_action(
                'mv "a source.py" dest.py', project_root=project, archive=archive)
            self.assertFalse(verdict["protected"])
            self.assertEqual(verdict["category"], "worktree-file-mutation")

    def test_move_item_and_copy_item_are_recognised_too(self) -> None:
        """The PowerShell spellings, case-insensitively - the same style as
        every other `mv`/`cp` counterpart this module already recognises."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            (project / "malicious.py").write_text("bad", encoding="utf-8")
            pin_evaluator(archive, project, "evaluator.py")
            for command in ("Move-Item malicious.py evaluator.py",
                           "Copy-Item malicious.py evaluator.py"):
                with self.subTest(command=command):
                    verdict = classify_action(command, project_root=project, archive=archive)
                    self.assertEqual(verdict["category"], "pinned-evaluator-mutation")

    def test_mv_and_cp_never_fast_allow(self) -> None:
        """Part (b) of the fix: `mv`/`cp` are not floor commands, so the
        fast gate must escalate them to the full hook rather than fast-
        allowing - proven directly against the real fast-gate module and
        the checked-in table, not assumed from "they are not on the list"."""
        import importlib.util

        fast_gate_path = PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py"
        spec = importlib.util.spec_from_file_location("godmode_gate_fast_pins", fast_gate_path)
        fast = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(fast)
        table = json.loads((PLUGIN_ROOT / "hooks" / "gate_table.json").read_text(encoding="utf-8"))
        for command in ("mv evaluator.py evaluator_renamed.py",
                        "mv malicious.py evaluator.py",
                        "cp malicious.py evaluator.py"):
            with self.subTest(command=command):
                payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": command}}
                self.assertEqual(fast.fast_verdict(payload, table), "escalate")


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
        (self.project / "malicious.py").write_text("def score():\n    return 999\n",
                                                    encoding="utf-8")
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

    def _decide_bash(self, command: str) -> tuple[str, str]:
        payload = {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": str(self.project),
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

    def test_the_reviews_three_exact_commands_now_deny_naming_the_pin(self) -> None:
        """Fix-round-1, Critical, red-first: these three commands, run
        through the real hook subprocess exactly as the review did, were
        `exit 0, no output` (silent allow) before this fix - `mv`/`cp` had
        no entry anywhere in the mutation vocabulary."""
        self._pin("evaluator.py")
        for command in ("mv evaluator.py evaluator_renamed.py",
                        "mv malicious.py evaluator.py",
                        "cp malicious.py evaluator.py"):
            with self.subTest(command=command):
                decision, reason = self._decide_bash(command)
                self.assertIn(decision, ("deny", "ask"), command)
                self.assertIn("pinned evaluator", reason, command)

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


class ProjectRootThreadingTests(unittest.TestCase):
    """Fix-round-1, Minor 2: `CapabilityBroker._classify` must judge an
    operation against the archive's OWN project, not the process's current
    working directory - otherwise a broker opened for project A, invoked
    while the process happens to be sitting somewhere else entirely, would
    classify (and therefore stage/consume capabilities for) a path resolved
    against the wrong tree. No test in the repository ever set `cwd !=
    project_root` before this fix; this is that test.

    Host tool calls carry an ABSOLUTE `file_path` (documented at length
    elsewhere in `godmode_sentinel.py`), so that is the shape exercised
    here - a bare relative filename happens to resolve to the same pin key
    under either root and would not tell the two cases apart.
    """

    def test_classify_resolves_against_the_brokers_project_not_cwd(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            broker = CapabilityBroker(archive)

            with tempfile.TemporaryDirectory(prefix="godmode-elsewhere-") as elsewhere:
                original_cwd = os.getcwd()
                os.chdir(elsewhere)
                try:
                    verdict = broker._classify(f"write file {target}")
                finally:
                    os.chdir(original_cwd)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")
            self.assertTrue(verdict["protected"])

    def test_without_the_fix_the_same_call_would_miss_the_pin(self) -> None:
        """Isolates the regression directly: `classify_action` given the
        archive but no `project_root` (the pre-fix call shape `_classify`
        used to make) resolves the absolute path against `cwd` instead and
        never finds the pin - proving this is a real behavioural
        difference, not a test that would pass either way."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")

            with tempfile.TemporaryDirectory(prefix="godmode-elsewhere-") as elsewhere:
                original_cwd = os.getcwd()
                os.chdir(elsewhere)
                try:
                    verdict = classify_action(f"write file {target}", archive=archive)
                finally:
                    os.chdir(original_cwd)
            self.assertNotEqual(verdict["category"], "pinned-evaluator-mutation")
            self.assertFalse(verdict["protected"])

    def test_consume_staged_also_resolves_against_the_brokers_project(self) -> None:
        """End to end through the public surface `godmode_console.cmd_protect`
        and the hook actually use, not only `_classify` in isolation."""
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            target = _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            operation = f"write file {target}"
            broker.stage(operation, PASSWORD)

            with tempfile.TemporaryDirectory(prefix="godmode-elsewhere-") as elsewhere:
                original_cwd = os.getcwd()
                os.chdir(elsewhere)
                try:
                    verdict = broker.consume_staged(operation)
                finally:
                    os.chdir(original_cwd)
            self.assertIsNotNone(verdict)
            self.assertEqual(verdict["category"], "pinned-evaluator-mutation")


class HashCapTests(unittest.TestCase):
    """Fix-round-1, Minor 3: `pin_evaluator` and `pin_drift` hash a pinned
    file's content the same size-capped, streamed way `godmode_lens.py`'s
    own inventory sweep already does for this exact operation, rather than
    an unconditional `read_bytes()`."""

    def test_pin_file_digest_respects_the_cap(self) -> None:
        import godmode_runtime.godmode_sentinel as sentinel_module

        with isolated_project() as (project, _s, _a, _archive):
            target = _write_evaluator(project)
            original_cap = sentinel_module.MAX_HASH_BYTES
            sentinel_module.MAX_HASH_BYTES = 3
            try:
                self.assertIsNone(pin_file_digest(target))
            finally:
                sentinel_module.MAX_HASH_BYTES = original_cap
            # Green control: under the (restored) real cap, an ordinary
            # small file still hashes normally.
            self.assertIsNotNone(pin_file_digest(target))

    def test_pinning_an_oversized_file_is_refused_rather_than_loaded_whole(self) -> None:
        import godmode_runtime.godmode_sentinel as sentinel_module

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            original_cap = sentinel_module.MAX_HASH_BYTES
            sentinel_module.MAX_HASH_BYTES = 3
            try:
                with self.assertRaises(AuthorizationError):
                    pin_evaluator(archive, project, "evaluator.py")
            finally:
                sentinel_module.MAX_HASH_BYTES = original_cap

    def test_drift_on_an_oversized_pinned_file_is_a_blocking_finding_not_a_crash(self) -> None:
        import godmode_runtime.godmode_sentinel as sentinel_module

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            _write_evaluator(project)
            pin_evaluator(archive, project, "evaluator.py")
            original_cap = sentinel_module.MAX_HASH_BYTES
            sentinel_module.MAX_HASH_BYTES = 3
            try:
                findings = pin_drift(archive, project)
            finally:
                sentinel_module.MAX_HASH_BYTES = original_cap
            self.assertEqual(len(findings), 1)
            self.assertTrue(findings[0]["blocking"])
            self.assertEqual(findings[0]["path"], "evaluator.py")


if __name__ == "__main__":
    unittest.main()
