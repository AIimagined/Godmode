"""B4-G: the console error-exit contract, baseline redaction, and
scope-explicit status responses.

Field report (spec B4-8): three tools in one governed session reported
failure in the body while the exit code said success - `inspect` returned
PrivacyError and exited 0, `checkpoint` returned ArchiveError and exited 0.
That is the exact fail-open shape CX-5's doctrine forbids ("silence from a
failed verifier is never evidence of permission"), alive in the console.
The contract is enforced at the DISPATCHER, not per-command, so every
registered subcommand - including ones that do not exist yet - inherits it.

Exit vocabulary: 0 ok / 1 findings-red (a command that ran and found
problems) / 2 error (the command itself failed).

Second field finding (same spec): the privacy guard refused to persist a
baseline because one entry's PATH was secret-shaped, and since inspect had
no redaction mechanism, no baseline could ever exist for that project -
drift detection permanently unavailable. The refusal message named the
right remedy ("store evidence by hash or a redacted description"); the
inventory now DOES it, per entry, instead of refusing the whole snapshot.

Third (extension, field feedback 3): a `not-initialized` answer that does
not name the project it is answering about caused a confident wrong verdict
in the field. Every status-shaped response names its resolved project root.
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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import PrivacyError  # noqa: E402
from godmode_runtime.godmode_lens import (  # noqa: E402
    collect_inventory,
    inventory_diff,
    make_snapshot,
)

SECRET_NAME = "token=abcdefgh12345.txt"


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


def _quiet_main(argv: list[str]) -> int:
    """Run console.main with stdout/stderr captured."""
    with mock.patch.object(sys, "stdout", io.StringIO()), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        return console.main(argv)


def _leaf_commands(parser) -> list[list[str]]:
    """Every registered leaf command path, with dummy values for whatever
    each one requires - registry-driven so a newly added command is swept
    automatically, without this file naming it."""
    import argparse

    leaves: list[list[str]] = []

    def synth(sub) -> list[str]:
        extra: list[str] = []
        group_required = set()
        for group in sub._mutually_exclusive_groups:
            if group.required and group._group_actions:
                group_required.add(id(group._group_actions[0]))
        for action in sub._actions:
            if isinstance(action, argparse._SubParsersAction):
                continue
            value = None
            if action.choices:
                value = str(sorted(action.choices)[0])
            elif action.type is int:
                value = "1"
            elif action.type is float:
                value = "1.0"
            if not action.option_strings:  # positional
                if action.nargs in ("*", "?", argparse.REMAINDER):
                    continue
                extra.append(value or "dummy")
            elif action.required or id(action) in group_required:
                extra.append(action.option_strings[0])
                if not isinstance(action, (argparse._StoreTrueAction,
                                           argparse._StoreFalseAction,
                                           argparse._CountAction)):
                    extra.append(value or "dummy")
        return extra

    def walk(sub, path: list[str]) -> None:
        nested = [action for action in sub._actions
                  if isinstance(action, argparse._SubParsersAction)]
        if not nested:
            leaves.append(path + synth(sub))
            return
        for name, child in nested[0].choices.items():
            walk(child, path + [name])

    walk(parser, [])
    return leaves


class RegistryErrorSweepTests(unittest.TestCase):
    def test_every_registered_subcommand_exits_2_when_the_runtime_errors(self) -> None:
        """The sweep the spec asks for: force an error through EVERY
        registered subcommand and assert nonzero, uniformly. `_runtime`
        raising is the one seam every command shares before its handler
        runs, so this proves no command's plumbing can swallow a
        GodmodeError back to exit 0."""
        parser = console._build_parser()
        failures: list[str] = []
        for argv in _leaf_commands(parser):
            if argv[:1] == ["guide"]:
                continue  # early-returns static text before any runtime
            with mock.patch.object(console, "_runtime",
                                   side_effect=PrivacyError("forced")):
                try:
                    code = _quiet_main(argv)
                except SystemExit as exc:  # argparse rejected the dummy argv
                    self.fail(f"sweep argv invalid for {argv}: {exc}")
                if code != 2:
                    failures.append(f"{' '.join(argv)} -> {code}")
        self.assertEqual(failures, [])


class ErrorPayloadContractTests(unittest.TestCase):
    """A handler that RETURNS an error-shaped payload with exit 0 is the
    field defect verbatim; the dispatcher forces it nonzero."""

    def _dispatch_with_handler(self, handler) -> int:
        parser = console._build_parser()
        args = parser.parse_args(["version"])
        args.handler = handler
        dummy = mock.Mock()
        with mock.patch.object(console, "_runtime", return_value=dummy):
            return _quiet_main_args(args)

    def test_an_error_payload_with_exit_zero_is_forced_to_2(self) -> None:
        code = self._dispatch_with_handler(
            lambda a, r: console.CommandResult(
                {"error": "PrivacyError", "message": "forced"}, exit_code=0))
        self.assertEqual(code, 2)

    def test_a_clean_payload_keeps_exit_zero(self) -> None:
        code = self._dispatch_with_handler(
            lambda a, r: console.CommandResult({"ok": True}, exit_code=0))
        self.assertEqual(code, 0)

    def test_a_findings_red_exit_1_is_never_promoted(self) -> None:
        # 1 means "ran, found problems" - a defined vocabulary value the
        # contract must not rewrite (e.g. `index` returns IndexStale at 1).
        code = self._dispatch_with_handler(
            lambda a, r: console.CommandResult(
                {"error": "IndexStale", "message": "stale"}, exit_code=1))
        self.assertEqual(code, 1)

    def test_a_falsy_error_key_is_not_an_error(self) -> None:
        code = self._dispatch_with_handler(
            lambda a, r: console.CommandResult({"error": None, "ok": True},
                                               exit_code=0))
        self.assertEqual(code, 0)


def _quiet_main_args(args) -> int:
    """Dispatch pre-parsed args through the same finalization main uses."""
    with mock.patch.object(sys, "stdout", io.StringIO()), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        return console._dispatch(args)


class BaselineRedactionTests(unittest.TestCase):
    def test_a_secret_shaped_path_is_redacted_and_counted(self) -> None:
        with isolated_project() as (project, _state, anchor, _archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            (project / SECRET_NAME).write_text("body", encoding="utf-8")
            inventory = collect_inventory(project)
        paths = [entry["path"] for entry in inventory["entries"]]
        self.assertIn("app.py", paths)
        joined = json.dumps(inventory)
        self.assertNotIn(SECRET_NAME, joined, "cleartext persisted")
        self.assertEqual(inventory["redaction_count"], 1)
        redacted = [entry for entry in inventory["entries"]
                    if entry.get("redacted")]
        self.assertEqual(len(redacted), 1)
        entry = redacted[0]
        self.assertTrue(entry["path"].startswith("redacted:"))
        self.assertEqual(entry["length"], len(SECRET_NAME))
        self.assertIn("extension_class", entry)

    def test_the_snapshot_now_persists_where_it_refused_before(self) -> None:
        """The terminal state the field report named: `inspect` could never
        baseline this project. The redacted snapshot appends cleanly."""
        with isolated_project() as (project, _state, anchor, archive):
            (project / SECRET_NAME).write_text("body", encoding="utf-8")
            archive.initialize()
            snapshot = make_snapshot(anchor)
            record = archive.append("inventory", "repository-snapshot", snapshot)
        self.assertEqual(record["kind"], "inventory")
        self.assertNotIn(SECRET_NAME, json.dumps(record))

    def test_drift_detection_works_against_the_redacted_baseline(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / SECRET_NAME).write_text("v1", encoding="utf-8")
            before = collect_inventory(project)
            diff_same = inventory_diff(before, collect_inventory(project))
            (project / SECRET_NAME).write_text("v2-changed", encoding="utf-8")
            diff_changed = inventory_diff(before, collect_inventory(project))
        self.assertTrue(diff_same["clean"])
        self.assertFalse(diff_changed["clean"])
        self.assertEqual(len(diff_changed["changed"]), 1)
        self.assertTrue(diff_changed["changed"][0].startswith("redacted:"))

    def test_a_declared_exclusion_skips_the_entry_entirely(self) -> None:
        """Tighten-only: an exclusion narrows what persists (the entry is
        gone, counted in skipped), never widens what persists in clear."""
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            (project / "cred-dump.txt").write_text("x", encoding="utf-8")
            (project / ".godmode-privacy.json").write_text(
                json.dumps({"baseline_exclude": ["cred-*.txt"]}),
                encoding="utf-8")
            inventory = collect_inventory(project)
        paths = [entry["path"] for entry in inventory["entries"]]
        self.assertNotIn("cred-dump.txt", paths)
        # The config file itself still baselines - exclusion is explicit.
        self.assertIn(".godmode-privacy.json", paths)
        self.assertEqual(inventory["skipped"]["excluded"], 1)


class ScopeExplicitResponseTests(unittest.TestCase):
    """Every status-shaped response names the resolved project root it is
    answering about - scope ambiguity in a state-reporting tool is a
    correctness defect (field feedback 3)."""

    def _payload(self, argv: list[str], project: Path) -> dict:
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            console.main(["--project", str(project)] + argv)
        return json.loads(out.getvalue())

    def test_doctor_names_its_project(self) -> None:
        with isolated_project() as (project, _state, anchor, _archive):
            payload = self._payload(["doctor"], project)
            self.assertEqual(payload["project"], str(anchor.project_root))

    def test_config_check_names_its_project(self) -> None:
        with isolated_project() as (project, _state, anchor, _archive):
            payload = self._payload(["config", "check"], project)
            self.assertEqual(payload["project"], str(anchor.project_root))

    def test_not_initialized_refusals_name_the_project(self) -> None:
        with isolated_project() as (project, _state, anchor, _archive):
            err = io.StringIO()
            with mock.patch.object(sys, "stdout", io.StringIO()), \
                    mock.patch.object(sys, "stderr", err):
                code = console.main(["--project", str(project), "resume"])
            self.assertEqual(code, 2)
            message = json.loads(err.getvalue())["message"]
            self.assertIn(str(anchor.project_root), message)


if __name__ == "__main__":
    unittest.main()
