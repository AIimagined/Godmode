"""C-3 + NS-10i: hook errors never reach the host, proven per event.

Every event `hooks/godmode_session_hook.py` serves does ancillary
bookkeeping (a record write, a nudge, brief building) beside its actual
answer to the host. That bookkeeping must be best-effort: an internal
failure in it degrades the hook - exit 0, one `godmode: degraded -
ancillary-failed` line on stderr, and a `hook-degraded` record on the
archive - and never a crash the host has to explain to an operator. The
one exception is `pre-action`'s own gate decision: a record write raising
there must still leave the decision `deny`, never fold a bookkeeping
failure into a silent allow.

In-process harness throughout: the hook module is imported directly (not
shelled out to), stdin is an `io.StringIO`, and `Chronicle.append` is
patched with a SELECTIVE failure - it raises `OSError("disk")` for every
write except the one `record_hook_degradation` itself makes (matched by
subject), which goes through to the real method. Patching `Chronicle.
append` wholesale (an earlier version of this file did exactly that)
proves the crash never happens but cannot prove the record gets written -
`record_hook_degradation` writes through the very method the test broke,
so the record would be silently absent in exactly the scenario this test
claims to cover. The selective patch lets every ancillary write fail while
leaving the degradation record's own write real. A control case with
nothing patched, run for every event, proves the degraded line is not
printed when nothing actually failed.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
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
from godmode_runtime.godmode_hookproof import (  # noqa: E402
    DEGRADE_REASON_ANCILLARY, SUBJECT_HOOK_DEGRADED)
import godmode_session_hook as hook  # noqa: E402
import godmode_post_edit  # noqa: E402

DEGRADED_LINE = f"godmode: degraded — {DEGRADE_REASON_ANCILLARY}"

# The real `Chronicle.append`, captured before any patching, so the
# selective wrapper below can still perform the one write it lets through.
_REAL_APPEND = Chronicle.append


def _append_unless_degradation(self, kind, subject, data, *, evidence=None, dedupe=False):
    """Every ancillary write fails; the hook's own degradation record does
    not. `subject` is always the caller's own literal/constant (`kind`,
    `subject`, `data` are all positional at every real call site in this
    repository) - `record_hook_degradation` is the one caller that passes
    `SUBJECT_HOOK_DEGRADED`, so this is a precise selector, not a guess."""
    if subject == SUBJECT_HOOK_DEGRADED:
        return _REAL_APPEND(self, kind, subject, data, evidence=evidence, dedupe=dedupe)
    raise OSError("disk")


def _project():
    base = Path(tempfile.mkdtemp(prefix="godmode-never-raises-"))
    project = base / "project"
    project.mkdir(parents=True)
    return base, project


def _run(event: str, payload: dict, project: Path, *, patch_append: bool) -> tuple[int, str, str]:
    """`(returncode, stdout, stderr)` for one in-process hook call."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))))
        stack.enter_context(mock.patch.object(sys, "stdout", out))
        stack.enter_context(mock.patch.object(sys, "stderr", err))
        if patch_append:
            stack.enter_context(mock.patch.object(Chronicle, "append", new=_append_unless_degradation))
        stack.enter_context(mock.patch.dict(os.environ, {"GODMODE_HOST": "claude"}, clear=False))
        code = hook.main([event, "--project", str(project)])
    return code, out.getvalue(), err.getvalue()


def _degraded_records(archive: Chronicle) -> list[dict]:
    return archive.select(kind="action", subject=SUBJECT_HOOK_DEGRADED, limit=1000)


# Real event names this hook's argparse serves, read from the hook module
# itself (`hooks/godmode_session_hook.py::main`'s `choices=[...]`) rather
# than assumed - the brief's own list of eight names one ("post-action")
# this hook does not actually have an event for, and spells another
# ("user-prompt-submit") differently than the real `user-prompt`. The real
# list is seven.
REAL_EVENTS = ("session-start", "user-prompt", "pre-action", "stop",
              "subagent-stop", "session-end", "pre-compact")

# One payload per real event, minimal but enough to reach that event's own
# canonical ancillary write (see `task-1-report.md` for which write each
# one is). Shared by the crash/degrade matrix and the per-event control.
_NON_ACTION_PAYLOADS = {
    "session-start": {
        "hook_event_name": "SessionStart", "cwd": "{project}",
        "session_id": "s1",
    },
    "user-prompt": {
        "hook_event_name": "UserPromptSubmit", "cwd": "{project}",
        "session_id": "s1",
        "prompt": "please investigate why the retry breaker test keeps failing and fix the root cause",
    },
    "stop": {
        "hook_event_name": "Stop", "cwd": "{project}", "session_id": "s1",
        "usage": {"input_tokens": 5, "output_tokens": 5},
    },
    "subagent-stop": {
        "hook_event_name": "SubagentStop", "cwd": "{project}", "session_id": "s1",
        "usage": {"input_tokens": 5, "output_tokens": 5},
    },
    "session-end": {
        "hook_event_name": "SessionEnd", "cwd": "{project}", "session_id": "s1",
    },
    "pre-compact": {
        "hook_event_name": "PreCompact", "cwd": "{project}", "session_id": "s1",
        "trigger": "manual",
    },
}

_PRE_ACTION_PAYLOAD = {
    "hook_event_name": "PreToolUse", "cwd": "{project}",
    "session_id": "s1", "tool_name": "Bash",
    "tool_input": {"command": "git push --force origin main"},
}


def _payloads_for(project: Path) -> dict[str, dict]:
    payloads = {
        event: {**shape, "cwd": str(project)}
        for event, shape in _NON_ACTION_PAYLOADS.items()
    }
    payloads["pre-action"] = {**_PRE_ACTION_PAYLOAD, "cwd": str(project)}
    return payloads


class HookNeverRaisesTests(unittest.TestCase):
    def test_every_real_event_is_in_the_hooks_own_argparse(self) -> None:
        # Pins the divergence from the brief's assumed eight: this asserts
        # against the hook's actual argparse `choices`, not a hand-copied
        # list, so a future event rename fails here first.
        import argparse
        parser_events: list[str] | None = None
        original_add_argument = argparse.ArgumentParser.add_argument

        def _capture(self, *args, **kwargs):  # noqa: ANN001
            nonlocal parser_events
            if args and args[0] == "event":
                parser_events = list(kwargs.get("choices") or [])
            return original_add_argument(self, *args, **kwargs)

        with mock.patch.object(argparse.ArgumentParser, "add_argument", _capture), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            try:
                hook.main(["--help"])
            except SystemExit:  # godmode: swallow-ok: argparse's own --help exit; only its captured choices matter here
                pass
        self.assertEqual(sorted(parser_events or []), sorted(REAL_EVENTS))

    def test_each_event_degrades_with_a_record_instead_of_crashing(self) -> None:
        base, project = _project()
        try:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                payloads = _payloads_for(project)

                for event in REAL_EVENTS:
                    if event == "pre-action":
                        continue
                    with self.subTest(event=event):
                        before = len(_degraded_records(archive))
                        code, _out, err = _run(event, payloads[event], project, patch_append=True)
                        self.assertEqual(code, 0, err)
                        lines = [line for line in err.splitlines() if line.strip()]
                        self.assertEqual(lines, [DEGRADED_LINE], err)
                        after = _degraded_records(archive)
                        self.assertEqual(len(after), before + 1, after)
                        self.assertEqual(after[-1]["data"]["reason"], DEGRADE_REASON_ANCILLARY)

                # `pre-action` is the one event whose bookkeeping failure
                # must never touch the decision: a protected command still
                # denies while the refusal record it tries to write raises
                # - and that raise still produces a real degradation record
                # (this is the one write the selective patch lets through).
                with self.subTest(event="pre-action"):
                    before = len(_degraded_records(archive))
                    code, out, err = _run("pre-action", payloads["pre-action"], project, patch_append=True)
                    self.assertEqual(code, 0, err)
                    body = json.loads(out.strip())
                    decision = (body.get("hookSpecificOutput") or {}).get("permissionDecision")
                    self.assertEqual(decision, "deny", body)
                    lines = [line for line in err.splitlines() if line.strip()]
                    self.assertEqual(lines, [DEGRADED_LINE], err)
                    after = _degraded_records(archive)
                    self.assertEqual(len(after), before + 1, after)
                    self.assertEqual(after[-1]["data"]["reason"], DEGRADE_REASON_ANCILLARY)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_control_nothing_patched_prints_no_degraded_line(self) -> None:
        base, project = _project()
        try:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                payloads = _payloads_for(project)
                for event in REAL_EVENTS:
                    with self.subTest(event=event):
                        code, _out, err = _run(event, payloads[event], project, patch_append=False)
                        self.assertEqual(code, 0, err)
                        self.assertNotIn("degraded", err)
                self.assertEqual(_degraded_records(archive), [])
        finally:
            shutil.rmtree(base, ignore_errors=True)


class ReadPathNeverRaisesTests(unittest.TestCase):
    """The never-raise contract covers READS, not only writes (B1).

    `HookNeverRaisesTests` above patches `Chronicle.append` and nothing
    else, so every read in every event succeeds there; and its `pre-compact`
    payload carries no `summary`, which is the one shape the PreCompact
    branch's auto fallback short-circuits. A regression that lived entirely
    in "PreCompact WITH a host summary, over an archive whose contents are
    damaged" therefore passed straight between the two: the summary-carrying
    payload reached a fold that assumed every record's `data` is a mapping,
    and `raise SystemExit(main())` had no outer guard to turn the resulting
    `AttributeError` into anything but a traceback in the host.

    Both cases below fail on `0c1390f` and are the reason this cannot
    recur: one damages a record on disk (the read succeeds, the record is
    the wrong shape), one breaks the read itself.
    """

    _SUMMARY_PAYLOAD = {
        "hook_event_name": "PreCompact", "session_id": "s1",
        "trigger": "manual", "summary": "compacting now",
    }

    def test_pre_compact_with_a_host_summary_over_a_damaged_record_exits(self) -> None:
        # The review's own reproduction, verbatim: two real records, the
        # second one's `data` rewritten on disk to a list with its
        # `record_hash` left stale, and a PreCompact payload that carries a
        # summary. On `0c1390f` this raises `AttributeError: 'list' object
        # has no attribute 'get'` out of `main()`, and
        # `raise SystemExit(main())` hands that to the host as a traceback.
        # The old hook degraded instead - exit 2, the chain break named on
        # stdout - and that is the behaviour being restored here.
        base, project = _project()
        try:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                archive.append("decision", "retry-policy", {"value": "back off twice"})
                archive.append("decision", "cache-policy", {"value": "write through"})
                paths = sorted(archive.events.glob("*.godmode.json"))
                self.assertTrue(paths, "no record files were written")
                damaged = json.loads(paths[-1].read_text(encoding="utf-8"))
                damaged["data"] = ["not", "a", "mapping"]
                paths[-1].write_text(json.dumps(damaged, ensure_ascii=False), encoding="utf-8")

                payload = {**self._SUMMARY_PAYLOAD, "cwd": str(project)}
                try:
                    code, out, err = _run("pre-compact", payload, project, patch_append=False)
                except Exception as error:  # noqa: BLE001  # godmode: swallow-ok: the assertion IS that nothing reaches here
                    self.fail(f"the hook raised into the host: {error!r}")
                self.assertEqual(code, 2, f"out={out!r} err={err!r}")
                self.assertNotIn("Traceback", err)
                self.assertIn("chain broken", err)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def _run_with_patched_unverified_read(self, project: Path, replacement):
        """One PreCompact call in which ONLY the extraction's own
        `read_events(verify=False)` is replaced - every verified read the
        rest of the hook makes goes through untouched, so the checkpoint
        still gets written and the assertion is about the extraction alone.
        """
        real_read = Chronicle.read_events

        def _read(self, *args, **kwargs):  # noqa: ANN001
            if kwargs.get("verify") is False:
                return replacement()
            return real_read(self, *args, **kwargs)

        payload = {**self._SUMMARY_PAYLOAD, "cwd": str(project)}
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))))
            stack.enter_context(mock.patch.object(sys, "stdout", out))
            stack.enter_context(mock.patch.object(sys, "stderr", err))
            stack.enter_context(mock.patch.dict(os.environ, {"GODMODE_HOST": "claude"}, clear=False))
            stack.enter_context(mock.patch.object(Chronicle, "read_events", new=_read))
            try:
                code = hook.main(["pre-compact", "--project", str(project)])
            except Exception as error:  # noqa: BLE001  # godmode: swallow-ok: the assertion IS that nothing reaches here
                self.fail(f"the hook raised into the host: {error!r}")
        return code, out.getvalue(), err.getvalue()

    def test_a_non_mapping_data_in_the_extraction_window_is_summarised_past(self) -> None:
        # The same wrong record shape, reached through the extraction's own
        # read so the hook gets all the way to its checkpoint write: the
        # damaged record is skipped, the healthy one is still extracted,
        # and nothing raises.
        base, project = _project()
        try:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                records = [
                    {"sequence": 1, "kind": "decision", "subject": "retry-policy",
                     "data": {"value": "back off twice"}},
                    {"sequence": 2, "kind": "decision", "subject": "damaged",
                     "data": ["not", "a", "mapping"]},
                    {"sequence": 3, "kind": "invariant", "subject": "clock",
                     "data": {"value": {"skew": "bounded"}}},
                ]
                code, out, err = self._run_with_patched_unverified_read(
                    project, lambda: [dict(record) for record in records])
                self.assertEqual(code, 0, f"out={out!r} err={err!r}")
                stored = archive.select(kind="checkpoint", limit=10)
                self.assertTrue(stored, "no checkpoint was written")
                extracted = stored[-1]["data"]["extracted"]
                self.assertEqual(
                    [entry["subject"] for entry in extracted["decisions"]],
                    ["retry-policy", "damaged"])
                self.assertIsNone(extracted["decisions"][1]["value"])
                # A non-string value stays machine-readable JSON, not a repr.
                self.assertEqual(extracted["facts"][0]["value"], '{"skew": "bounded"}')
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_an_extraction_read_that_raises_degrades_the_block_not_the_checkpoint(self) -> None:
        base, project = _project()
        try:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()

                def _boom():
                    raise OSError("disk")

                code, out, err = self._run_with_patched_unverified_read(project, _boom)
                self.assertEqual(code, 0, f"out={out!r} err={err!r}")
                stored = archive.select(kind="checkpoint", limit=10)
                self.assertTrue(stored, "no checkpoint was written")
                extracted = stored[-1]["data"]["extracted"]
                self.assertEqual(extracted["decisions"], [])
                self.assertTrue(extracted["degraded"])
        finally:
            shutil.rmtree(base, ignore_errors=True)


def _boom_read(self, *args, **kwargs):  # noqa: ANN001
    """Every archive read raises, however it was called."""
    raise OSError("unreadable archive")


def _run_entry(event: str, payload: dict, project: Path, *,
               patch_read: bool = False, patch_append: bool = False,
               ) -> tuple[int | None, str, str, str | None]:
    """One in-process call through the PROCESS entry point (`hook.run`, what
    `raise SystemExit(...)` invokes) rather than through `main` directly -
    the outer guard is the thing under test, and calling `main` walks
    straight past it. Returns `(code, stdout, stderr, raised)`; `raised` is
    the repr of anything that escaped, which is always the failure."""
    out, err = io.StringIO(), io.StringIO()
    code: int | None = None
    raised: str | None = None
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))))
        stack.enter_context(mock.patch.object(sys, "stdout", out))
        stack.enter_context(mock.patch.object(sys, "stderr", err))
        stack.enter_context(mock.patch.dict(os.environ, {"GODMODE_HOST": "claude"}, clear=False))
        if patch_read:
            stack.enter_context(mock.patch.object(Chronicle, "read_events", new=_boom_read))
        if patch_append:
            stack.enter_context(mock.patch.object(Chronicle, "append", new=_append_unless_degradation))
        try:
            code = hook.run([event, "--project", str(project)])
        except BaseException as error:  # noqa: BLE001  # godmode: swallow-ok: the assertion IS that nothing reaches here
            raised = repr(error)
    return code, out.getvalue(), err.getvalue(), raised


class EntryPointNeverRaisesTests(unittest.TestCase):
    """C-3/NS-10i fix round 2: reads, not only writes, and the entry point.

    `HookNeverRaisesTests` patches `Chronicle.append` and leaves every READ
    working, so an archive that cannot be read at all - a permission
    change, a half-synced directory, a disk giving `OSError` - was never
    exercised for most events. It escaped: with every read raising,
    `main()` still propagates out of session-start (the brief), pre-action
    and pre-compact (`latest_session`) and session-end (`_session_counts`),
    and `raise SystemExit(main())` had no guard between that and the host.

    These cases drive the real entry point (`hook.run`) with reads failing,
    and with reads AND writes failing, for every event the hook serves.
    """

    def setUp(self) -> None:
        self.base, self.project = _project()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self._env = mock.patch.dict(
            os.environ, {"GODMODE_STATE_HOME": str(self.base / "state")}, clear=False)
        self._env.start()
        self.addCleanup(self._env.stop)
        self.archive = Chronicle(resolve_anchor(self.project))
        self.archive.initialize()
        # Declared work in flight, so session-end/pre-compact reach the
        # interrupted-intent capture instead of returning early.
        self.archive.append("checkpoint", "cp",
                            {"value": "v", "next": ["finish the fold"]})
        self.payloads = _payloads_for(self.project)
        self.payloads["pre-compact"] = {**self.payloads["pre-compact"],
                                        "summary": "compacting now"}

    def _assert_answered_the_host(self, event: str, code, out: str, err: str,
                                  raised: str | None) -> None:
        self.assertIsNone(raised, f"the hook raised into the host: {raised}")
        self.assertNotIn("Traceback", err)
        if event == "pre-action":
            # M7: a gate that could not be evaluated denies. A crash in the
            # evaluator must never become a silent allow.
            self.assertEqual(code, 2, f"out={out!r} err={err!r}")
            body = json.loads(out.strip().splitlines()[-1])
            decision = (body.get("hookSpecificOutput") or {}).get("permissionDecision")
            self.assertEqual(decision, "deny", body)
        else:
            self.assertEqual(code, 0, f"out={out!r} err={err!r}")

    def test_every_event_survives_an_archive_whose_every_read_raises(self) -> None:
        for event in REAL_EVENTS:
            with self.subTest(event=event):
                before = len(_degraded_records(self.archive))
                code, out, err, raised = _run_entry(
                    event, self.payloads[event], self.project, patch_read=True)
                self._assert_answered_the_host(event, code, out, err, raised)
                # Never silent, and never doubled: at most one degradation
                # record and at most one degraded line per hook call, whether
                # the report came from an inner guard or from the outer one.
                delta = len(_degraded_records(self.archive)) - before
                self.assertLessEqual(delta, 1, f"{event}: {delta} degradation records")
                self.assertLessEqual(
                    len([line for line in err.splitlines() if "degraded" in line]), 1, err)

    def test_the_events_that_would_crash_report_the_degradation(self) -> None:
        """The four reads-only crash paths, named: session-start's brief,
        pre-action's and pre-compact's `latest_session`, session-end's
        `_session_counts`. Each must leave a `hook-degraded` record behind -
        an outer guard that exits 0 and says nothing is a silent swallow."""
        for event in ("session-start", "pre-action", "session-end", "pre-compact"):
            with self.subTest(event=event):
                before = len(_degraded_records(self.archive))
                code, out, err, raised = _run_entry(
                    event, self.payloads[event], self.project, patch_read=True)
                self._assert_answered_the_host(event, code, out, err, raised)
                after = _degraded_records(self.archive)
                self.assertEqual(len(after), before + 1, after)
                self.assertIn("degraded", err)

    def test_every_event_survives_reads_and_writes_that_both_raise(self) -> None:
        for event in REAL_EVENTS:
            with self.subTest(event=event):
                code, out, err, raised = _run_entry(
                    event, self.payloads[event], self.project,
                    patch_read=True, patch_append=True)
                self._assert_answered_the_host(event, code, out, err, raised)

    def test_an_unexpected_failure_anywhere_in_main_degrades_instead_of_propagating(self) -> None:
        """The guard's own contract, independent of any particular read: a
        `main` that raises something nobody anticipated still answers the
        host."""
        with mock.patch.object(hook, "main", side_effect=RuntimeError("nobody expected this")):
            for event in REAL_EVENTS:
                with self.subTest(event=event):
                    code, out, err, raised = _run_entry(
                        event, self.payloads[event], self.project)
                    self._assert_answered_the_host(event, code, out, err, raised)

    def test_the_guard_lets_an_explicit_exit_through(self) -> None:
        """`SystemExit` is a decision, not a failure - argparse's own
        `--help`/usage exit must not be turned into a degraded 0."""
        with mock.patch.object(hook, "main", side_effect=SystemExit(3)):
            with mock.patch.object(sys, "stderr", io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    hook.run(["stop"])
        self.assertEqual(ctx.exception.code, 3)


class PostEditHookNeverRaisesTests(unittest.TestCase):
    """C-3 names Stop/PostToolUse; PostToolUse-for-edits is served by a
    different script (`hooks/godmode_post_edit.py`), not
    `godmode_session_hook.py`. Its one archive write (`_record_edit`) was
    already `except Exception`-guarded before this task - no crash path
    existed - but nothing proved it. This does."""

    def test_an_edit_whose_record_write_fails_still_exits_0_with_no_traceback(self) -> None:
        base, project = _project()
        try:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
                archive = Chronicle(resolve_anchor(project))
                archive.initialize()
                payload = {
                    "hook_event_name": "PostToolUse", "cwd": str(project),
                    "session_id": "s1", "tool_name": "Write",
                    "tool_input": {"file_path": str(project / "notes.md")},
                }
                out, err = io.StringIO(), io.StringIO()
                with contextlib.ExitStack() as stack:
                    stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))))
                    stack.enter_context(mock.patch.object(sys, "stdout", out))
                    stack.enter_context(mock.patch.object(sys, "stderr", err))
                    stack.enter_context(mock.patch.object(Chronicle, "append", side_effect=OSError("disk")))
                    code = godmode_post_edit.main()
                self.assertEqual(code, 0, err.getvalue())
                self.assertEqual(err.getvalue(), "")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
