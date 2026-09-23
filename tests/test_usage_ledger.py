"""Host-reported usage becomes a record; the digest and ceilings read it.

Divergences from the brief, matching `test_subagent_scope.py`'s own notes on
the same boundary: `python -m scripts.godmode_runtime` names no runnable
entrypoint and would look for the `scripts` package under `cwd=project`
besides - the real CLI is `scripts/godmode.py`, invoked with `--project`
rather than by `cwd`. `status --digest` is also not a real flag: the digest
lives under `status remaining --digest` (`godmode_console.py`'s
`status_remaining` subparser).

A fresh, uninitialized archive records nothing at all
(`hooks/godmode_session_hook.py`'s own `if not archive.initialized(): ...
return 0` guard, ahead of every event branch) - `test_untrusted_marker.py`
and `test_session_log.py` both call `archive.initialize()` before driving
the hook for exactly this reason. This file needs one more step neither of
those does: `isolated_project()` resolves its anchor (and so its archive's
location) the instant it is entered, BEFORE this test body ever runs -
for a project with no `.git` yet, that resolves a non-git, state-home-keyed
archive path. `git init` then changes the project's identity out from
under it: every LATER anchor resolution (the hook and CLI subprocesses,
which each resolve fresh) sees a git repository and keys the archive under
`.git/godmode-state` instead - a different location than the one
`isolated_project()`'s own `archive` handle was bound to before `git init`
ran. Initializing that stale handle would write to a path the subprocesses
never look at, and read it back as "not initialized" forever after. Fixed
by re-resolving the anchor AFTER `git init`, and using that (git-identity)
archive for both `.initialize()` and every `read_events()` assertion below.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"


class UsageLedgerTests(unittest.TestCase):
    def _hook(self, event: str, project: Path, state: Path, payload: dict) -> subprocess.CompletedProcess:
        # The host is declared, not inherited: running inside Claude Code sets
        # CLAUDE_CODE_ENTRYPOINT, a clean CI runner does not (host read
        # "unknown" on the first Linux run, 2026-09-23).
        env = dict(os.environ, GODMODE_STATE_HOME=str(state), CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT),
                   CLAUDE_CODE_ENTRYPOINT="cli")
        return subprocess.run([sys.executable, "-I", "-B", str(HOOK), event], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=project, env=env)

    def _digest(self, project: Path, state: Path) -> dict:
        proc = subprocess.run(
            [sys.executable, "-B", str(GODMODE_CLI), "--project", str(project), "status", "remaining", "--digest"],
            capture_output=True, text=True, cwd=project,
            env=dict(os.environ, GODMODE_STATE_HOME=str(state)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # Fix round 1 (review, code quality S1): assert parsed state, not a
        # rendered substring - the prior `spend.line` field existed only to
        # make a substring match work against `json.dumps` output.
        return json.loads(proc.stdout)

    def _git_init(self, project: Path) -> Chronicle:
        subprocess.run(["git", "init", "-q"], cwd=project, check=True, capture_output=True)
        # See the module docstring: the archive's identity depends on
        # `.git` existing at resolution time, so it is re-resolved here,
        # after `git init`, to match what the hook/CLI subprocesses below
        # will each resolve fresh for themselves.
        archive = Chronicle(resolve_anchor(project))
        archive.initialize()
        return archive

    def test_usage_recorded_and_digest_shows_it(self) -> None:
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            payload = {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                       "usage": {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 900}}
            proc = self._hook("stop", project, state, payload)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            seen = [r for r in archive.read_events() if r.get("subject") == "usage-observed"]
            self.assertEqual(len(seen), 1, seen)
            self.assertEqual(seen[0]["data"]["input_tokens"], 1200)
            self.assertEqual(seen[0]["data"]["output_tokens"], 300)
            self.assertEqual(seen[0]["data"]["cache_read_tokens"], 900)
            self.assertEqual(seen[0]["data"]["host"], "claude")
            # No `total_tokens` in this payload, so it is derived as
            # input + output + cache_read (review S2's ruling).
            self.assertEqual(seen[0]["data"]["total_tokens"], 2400)
            self.assertIn("usage:stop:", seen[0]["data"]["operation"])
            digest = self._digest(project, state)
            self.assertEqual(digest["digest"]["spend"]["source"], "host")
            self.assertEqual(digest["digest"]["spend"]["tokens"], 2400)

    def test_no_usage_leaves_source_unavailable(self) -> None:
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            self._hook("stop", project, state, {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False})
            self.assertEqual([r for r in archive.read_events() if r.get("subject") == "usage-observed"], [])
            digest = self._digest(project, state)
            self.assertEqual(digest["digest"]["spend"]["source"], "unavailable")

    def test_a_stop_refire_records_nothing_a_second_time(self) -> None:
        """Review S1: Claude's documented Stop re-fire sends the SAME
        payload again with `stop_hook_active: true`. The usage write must
        sit past that re-fire check, or the same turn's tokens double."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            usage = {"input_tokens": 1200, "output_tokens": 300, "cache_read_input_tokens": 900}
            first = self._hook("stop", project, state,
                               {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False, "usage": usage})
            self.assertEqual(first.returncode, 0, first.stderr)
            refire = self._hook("stop", project, state,
                                {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": True, "usage": usage})
            self.assertEqual(refire.returncode, 0, refire.stderr)
            seen = [r for r in archive.read_events() if r.get("subject") == "usage-observed"]
            self.assertEqual(len(seen), 1, seen)

    def test_total_tokens_only_block_is_not_dropped(self) -> None:
        """Review S2: a host that reports only `total_tokens` (no split
        fields) must have that figure recorded, not silently zeroed."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            payload = {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                       "usage": {"total_tokens": 150000}}
            proc = self._hook("stop", project, state, payload)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            seen = [r for r in archive.read_events() if r.get("subject") == "usage-observed"]
            self.assertEqual(len(seen), 1, seen)
            self.assertEqual(seen[0]["data"]["total_tokens"], 150000)
            self.assertEqual(seen[0]["data"]["input_tokens"], 0)
            self.assertEqual(seen[0]["data"]["output_tokens"], 0)
            self.assertEqual(seen[0]["data"]["cache_read_tokens"], 0)

    def test_ceiling_reads_host_reported_tokens(self) -> None:
        """The brief's own interface line: `check_ceilings` counts tokens
        from usage records when the ceiling is set."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tokens": 100}), encoding="utf-8")
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            payload = {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                       "lastAssistantMessage": "continuing the work.",
                       "usage": {"input_tokens": 1200, "output_tokens": 300}}
            proc = self._hook("stop", project, state, payload)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            seen = [r for r in archive.read_events() if r.get("subject") == "usage-observed"]
            self.assertEqual(len(seen), 1, seen)
            self.assertEqual(seen[0]["data"]["total_tokens"], 1500)
            from godmode_runtime.godmode_guardrails import usage_ledger_totals, check_ceilings
            totals = usage_ledger_totals(archive)
            self.assertEqual(totals["total_tokens"], 1500)
            verdict = check_ceilings(project, {"tokens": totals["total_tokens"], "source": "host"})
            self.assertEqual(verdict["verdict"], "over-ceiling")
            # And the hook's own stdout names the same figure, not just the
            # library call above - the ceiling notice this call produced.
            self.assertIn("host-reported spend", proc.stdout)

    def test_ceiling_is_scoped_to_the_current_session_not_lifetime(self) -> None:
        """Review round 2, S4/N1: round 1 keyed session-scoping on
        `latest_session(archive)` (`kind="session"`, never written by any
        hook - `open_session` is the only writer, and no hook calls it), so
        it silently fell back to the archive's LIFETIME host total. Two
        real sessions in one project: the first spends far past a
        `tokens: 100` ceiling; the second spends only 10. The second
        session's Stop must not report an over-ceiling from the first
        session's spend."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            (project / ".godmode-ceilings.json").write_text(json.dumps({"tokens": 100}), encoding="utf-8")
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            first = self._hook("stop", project, state,
                               {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                                "lastAssistantMessage": "session one, done.",
                                "usage": {"input_tokens": 1200, "output_tokens": 300}})
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("host-reported spend", first.stdout)
            # A second real session-start writes a NEW `hook-session-anchor`
            # record, moving the boundary `usage_ledger_totals` windows by.
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            second = self._hook("stop", project, state,
                                {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                                 "lastAssistantMessage": "session two, done.",
                                 "usage": {"input_tokens": 6, "output_tokens": 4}})
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertNotIn("host-reported spend", second.stdout)
            from godmode_runtime.godmode_guardrails import usage_ledger_totals
            totals = usage_ledger_totals(archive)
            self.assertEqual(totals["total_tokens"], 10)
            self.assertEqual(totals["lifetime"]["total_tokens"], 1510)

    def test_stop_is_preferred_over_session_end_for_the_same_session(self) -> None:
        """Review round 2, N4: `_record_usage_observed` runs from both the
        Stop and the SessionEnd branch, so a host reporting usage at both
        boundaries for one session must not have both summed. Decided
        rule: Stop-family records win when any exist in the window."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            self._hook("stop", project, state,
                       {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                        "usage": {"input_tokens": 100, "output_tokens": 50}})
            self._hook("session-end", project, state,
                       {"hook_event_name": "SessionEnd", "cwd": str(project),
                        "usage": {"input_tokens": 900, "output_tokens": 900}})
            seen = [r for r in archive.read_events() if r.get("subject") == "usage-observed"]
            self.assertEqual(len(seen), 2, seen)  # both are recorded -
            from godmode_runtime.godmode_guardrails import usage_ledger_totals
            totals = usage_ledger_totals(archive)
            # - but only the Stop record's 150 counts, never Stop + SessionEnd.
            self.assertEqual(totals["total_tokens"], 150)
            self.assertEqual(totals["records"], 1)

    def test_session_end_counts_when_no_stop_exists_in_the_session(self) -> None:
        """Review round 2, N4's other half: a session that ends without a
        Stop (no Stop hook installed, or the session crashed first) must
        still get SessionEnd's own report, not zero."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            self._hook("session-end", project, state,
                       {"hook_event_name": "SessionEnd", "cwd": str(project),
                        "usage": {"input_tokens": 900, "output_tokens": 900}})
            from godmode_runtime.godmode_guardrails import usage_ledger_totals
            totals = usage_ledger_totals(archive)
            self.assertEqual(totals["total_tokens"], 1800)
            self.assertEqual(totals["records"], 1)

    def test_digest_for_an_older_session_reports_that_sessions_own_spend(self) -> None:
        """Final review S6 (Task 7/12 D2): every OTHER field in
        `session_digest` windows by the `--session` argument it was given,
        but `usage_ledger_totals` used to ignore that entirely and always
        window by the newest hook-session anchor - a digest asked about an
        OLDER session used to report the CURRENT session's host spend
        under `"source": "host"`. Two real sessions, `open_session`'s own
        `kind="session"` boundary (the same boundary `session_digest`'s own
        `session_start`/`session_end` resolves against): the older
        session's digest must report the older session's tokens, not the
        newer one's."""
        with isolated_project() as (project, _s, anchor, archive):
            archive.initialize()
            from godmode_runtime.godmode_attest import open_session
            from godmode_runtime.godmode_console import Runtime, session_digest

            first_session = open_session(archive, "session one")
            archive.append("action", "usage-observed", {
                "host": "claude", "event": "stop",
                "input_tokens": 1200, "output_tokens": 300, "cache_read_tokens": 0,
                "total_tokens": 1500, "operation": "usage:stop:aaaaaaaaaaaa",
            }, evidence=[])
            open_session(archive, "session two")
            archive.append("action", "usage-observed", {
                "host": "claude", "event": "stop",
                "input_tokens": 3, "output_tokens": 2, "cache_read_tokens": 0,
                "total_tokens": 5, "operation": "usage:stop:bbbbbbbbbbbb",
            }, evidence=[])

            runtime = Runtime(anchor=anchor, archive=archive)
            digest = session_digest(runtime, first_session, None)
            self.assertEqual(digest["spend"]["source"], "host")
            self.assertEqual(digest["spend"]["tokens"], 1500)

    def test_lifetime_stop_preference_is_scoped_per_session(self) -> None:
        """Final review Task 12 D1: `lifetime` used to apply
        `usage_records_preferring_stop` over the WHOLE archive's
        `usage-observed` records at once - so if ANY session ever wrote a
        Stop-family record, every OTHER, SessionEnd-only session's own
        usage was dropped from `lifetime` entirely, not merely
        de-duplicated within its own session. Session one ends via
        SessionEnd only (no Stop hook fires); session two reports at Stop.
        Both must count toward `lifetime`."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            self._hook("session-end", project, state,
                       {"hook_event_name": "SessionEnd", "cwd": str(project),
                        "usage": {"input_tokens": 900, "output_tokens": 900}})
            self._hook("session-start", project, state, {"hook_event_name": "SessionStart", "cwd": str(project)})
            self._hook("stop", project, state,
                       {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False,
                        "usage": {"input_tokens": 100, "output_tokens": 50}})
            from godmode_runtime.godmode_guardrails import usage_ledger_totals
            totals = usage_ledger_totals(archive)
            # Session one's 1800 (SessionEnd, no Stop in its own window) and
            # session two's 150 (Stop) must both survive into `lifetime`.
            self.assertEqual(totals["lifetime"]["total_tokens"], 1950)
            self.assertEqual(totals["lifetime"]["records"], 2)

    def test_pre_fix_record_without_total_tokens_is_derived_at_read_time(self) -> None:
        """Review round 2, N5: every record `eab0679` shipped carries no
        `total_tokens` field. Reading one must derive the figure, not read
        it as 0 and drop it from every total."""
        with isolated_project() as (project, state, _a, _stale_archive):
            archive = self._git_init(project)
            archive.append("action", "usage-observed", {
                "host": "claude", "event": "stop",
                "input_tokens": 100, "output_tokens": 50, "cache_read_tokens": 10,
                "operation": "usage:stop:deadbeef0000",
            }, evidence=[])
            from godmode_runtime.godmode_guardrails import usage_ledger_totals, usage_record_total
            record = [r for r in archive.read_events() if r.get("subject") == "usage-observed"][0]
            self.assertEqual(usage_record_total(record["data"]), 160)
            totals = usage_ledger_totals(archive)
            self.assertEqual(totals["total_tokens"], 160)


if __name__ == "__main__":
    unittest.main()
