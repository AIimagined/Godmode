"""C-9: the done-bar's own checks carry a reviewer/builder role.

Reviewer checks (uncited-claim, unattested-hard-rule, reworded-done) stand
for a fact; nothing here gives them an escape hatch, and `active_escalation`
returns None for one unconditionally, by construction, never by an absent
record. Builder checks (scope-still-open, open-operator-asks, style) accept
a recorded reason for a few turns - `godmode governance escalate <check>
--reason "<why>"` writes it, and the Stop hook skips that one check while
it stands, printing the reason instead of nagging or blocking.

Three layers, cheapest first: the module's own rules (in-process, no
subprocess), the CLI's `governance --checks` / `governance escalate`
wiring, and the Stop hook actually skipping `scope-still-open` for a
session that escalated it (a positive control proves the same payload
still blocks without the escalation - the same shape
`test_subagent_scope.py` uses to prove its own guard is not vacuous).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_attest import latest_session  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_donebar import (  # noqa: E402
    BUILDER,
    DONE_BAR_CHECKS,
    REVIEWER,
    active_escalation,
    checks_table,
    escalate,
    live_escalations,
    note_turn,
)
from test_godmode_runtime import isolated_project  # noqa: E402


def _open_session(archive) -> str:
    archive.append("session", "open", {"status": "open"})
    return latest_session(archive) or ""


class CheckTableTests(unittest.TestCase):
    def test_the_interface_names_exactly_these_six_checks(self) -> None:
        self.assertEqual(DONE_BAR_CHECKS, {
            "uncited-claim": REVIEWER,
            "unattested-hard-rule": REVIEWER,
            "reworded-done": REVIEWER,
            "scope-still-open": BUILDER,
            "open-operator-asks": BUILDER,
            "style": BUILDER,
        })

    def test_checks_table_carries_every_check_and_its_role(self) -> None:
        table = checks_table()
        self.assertEqual({row["check"]: row["role"] for row in table},
                         DONE_BAR_CHECKS)

    def test_checks_table_names_which_checks_are_actually_gated(self) -> None:
        # N-style: `style` and `unattested-hard-rule` have no live
        # Stop-hook detector at all - escalating either is accepted and
        # recorded but changes nothing at Stop. The table says so rather
        # than leaving a reader to discover it by escalating.
        table = {row["check"]: row["gated"] for row in checks_table()}
        self.assertEqual(table, {
            "uncited-claim": True,
            "unattested-hard-rule": False,
            "reworded-done": True,
            "scope-still-open": True,
            "open-operator-asks": True,
            "style": False,
        })


class EscalationGuardrailTests(unittest.TestCase):
    def test_a_reviewer_check_cannot_be_escalated(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            for check in ("uncited-claim", "unattested-hard-rule", "reworded-done"):
                with self.subTest(check=check):
                    with self.assertRaises(ArchiveError) as ctx:
                        escalate(archive, check, reason="operator agreed")
                    self.assertIn(check, str(ctx.exception))
                    self.assertIn("reviewer check and cannot be escalated",
                                 str(ctx.exception))

    def test_an_unknown_check_is_refused(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            with self.assertRaises(ArchiveError):
                escalate(archive, "not-a-real-check", reason="operator agreed")

    def test_escalation_needs_a_reason(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            with self.assertRaises(ArchiveError):
                escalate(archive, "scope-still-open", reason="   ")

    def test_a_reviewer_check_never_reads_an_escalation_even_if_one_exists(self) -> None:
        # A raw append cannot be reached through `escalate()` (it refuses
        # a reviewer check), so this constructs the record by hand - the
        # point is that `active_escalation` still answers None, because it
        # never even looks past the role for a reviewer check.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = _open_session(archive)
            archive.append("decision", "escalate:uncited-claim",
                           {"reason": "operator agreed", "session": session,
                            "expires_turns": 3})
            self.assertIsNone(active_escalation(archive, "uncited-claim"))


class EscalationLifecycleTests(unittest.TestCase):
    def test_a_builder_escalation_is_active_for_the_current_session(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            escalate(archive, "scope-still-open", reason="operator agreed to defer")
            self.assertEqual(
                active_escalation(archive, "scope-still-open"),
                "operator agreed to defer")

    def test_a_new_session_anchor_retires_a_prior_escalation(self) -> None:
        # S1 (fix round 1): matching is bound to the hook's own session
        # anchor (`godmode_hookproof._session_anchor_sequence`), the same
        # mechanism Plan 6 Task 12 built for the identical "no live
        # session id to match against" problem. An escalation written
        # before the CURRENT anchor is stale, whatever its turn count
        # says - a new session starting must retire someone else's
        # unrelated three-turn grace, not extend it indefinitely.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            escalate(archive, "scope-still-open", reason="operator agreed to defer")
            _open_session(archive)  # a new session anchor
            self.assertIsNone(active_escalation(archive, "scope-still-open"))

    def test_an_escalation_expires_after_three_turns(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            session = _open_session(archive)
            escalate(archive, "open-operator-asks", reason="already triaged")
            # Turns 1 and 2: still active.
            for _ in range(2):
                self.assertEqual(
                    active_escalation(archive, "open-operator-asks"),
                    "already triaged")
                note_turn(archive, session)
            # Turn 3: the third tick lands; the count it leaves behind
            # (3) meets `expires_turns` (3), so this same read is the
            # last one that still sees it.
            self.assertEqual(
                active_escalation(archive, "open-operator-asks"),
                "already triaged")
            note_turn(archive, session)
            # Turn 4: expired.
            self.assertIsNone(active_escalation(archive, "open-operator-asks"))

    def test_with_no_session_ever_opened_the_anchor_falls_back_project_wide(self) -> None:
        # S1's stated fallback (matches Task 12's D3 for the identical
        # anchor): an anchor of 0 - no `kind="session"` record and no
        # `hook-session-anchor` action, i.e. no session-start hook ever
        # ran and `session open` was never called - means there is
        # nothing to be stale relative to, so today's match (any
        # escalation on record, turn count only) still applies.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            escalate(archive, "scope-still-open", reason="operator agreed to defer")
            self.assertEqual(
                active_escalation(archive, "scope-still-open"),
                "operator agreed to defer")

    def test_live_escalations_answers_several_checks_in_one_pass(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            escalate(archive, "scope-still-open", reason="deferred to next release")
            self.assertEqual(
                live_escalations(archive, ("scope-still-open", "open-operator-asks",
                                          "uncited-claim", "not-a-real-check")),
                {"scope-still-open": "deferred to next release"})

    def test_style_has_no_stop_hook_gate_of_its_own(self) -> None:
        # Divergence, recorded rather than hidden: the brief's six checks
        # include "style", but no Stop-hook detector in this repository
        # ever raises a style-shaped block or notice - there is nothing
        # for an escalation to skip. `escalate`/`active_escalation` still
        # work for it structurally (it is a builder check), so a project
        # that later grows a real style gate only has to make it read
        # this same table; nothing here refuses "style" as a name.
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            _open_session(archive)
            record = escalate(archive, "style", reason="known trailing whitespace, filed")
            self.assertEqual(record["data"]["reason"],
                             "known trailing whitespace, filed")
            self.assertEqual(active_escalation(archive, "style"),
                             "known trailing whitespace, filed")


# --- CLI wiring: `godmode governance --checks` / `governance escalate` ---

def _run_cli(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GODMODE_STATE_HOME=str(project / ".state"))
    return subprocess.run(
        [sys.executable, "-B", str(GODMODE_CLI), "--project", str(project), *args],
        capture_output=True, text=True, cwd=project, env=env)


class GovernanceCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True,
                       capture_output=True)
        out = _run_cli(self.project, "init")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_governance_checks_prints_the_role_table(self) -> None:
        out = _run_cli(self.project, "governance", "--checks")
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout)
        table = {row["check"]: row["role"] for row in payload["checks"]}
        self.assertEqual(table, DONE_BAR_CHECKS)

    def test_escalating_a_builder_check_is_recorded(self) -> None:
        out = _run_cli(self.project, "governance", "escalate", "scope-still-open",
                       "--reason", "operator agreed to defer")
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["escalated"], "scope-still-open")
        self.assertEqual(payload["reason"], "operator agreed to defer")
        self.assertEqual(payload["expires_turns"], 3)

    def test_escalating_a_reviewer_check_exits_2_naming_the_rule(self) -> None:
        out = _run_cli(self.project, "governance", "escalate", "uncited-claim",
                       "--reason", "operator agreed")
        self.assertEqual(out.returncode, 2)
        combined = out.stdout + out.stderr
        self.assertIn("uncited-claim", combined)
        self.assertIn("reviewer check and cannot be escalated", combined)

    def test_escalating_an_unknown_check_exits_2(self) -> None:
        out = _run_cli(self.project, "governance", "escalate", "not-a-real-check",
                       "--reason", "operator agreed")
        self.assertEqual(out.returncode, 2)


# --- Stop hook: a builder check is actually skipped when escalated ---

def run_hook(event: str, payload: dict, project: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, GODMODE_STATE_HOME=str(project / ".state"))
    return subprocess.run([sys.executable, "-I", "-B", str(HOOK), event],
                         input=json.dumps(payload), capture_output=True,
                         text=True, cwd=project, env=env)


class StopHookEscalationTests(unittest.TestCase):
    """Mirrors `test_subagent_scope.py`'s own setup: an open ask minted
    through `user-prompt`, then a Stop reply whose wording trips the
    completion vocabulary ("Checkpoint complete.") without also tripping
    the separate done-bar claim gate - `_PROCESS_SENTENCE` filters that
    exact sentence out as bookkeeping language, not a claim about the
    work, which is what keeps `scope_reason` (not `done_shaped`) the one
    thing deciding whether this Stop blocks."""

    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True,
                       capture_output=True)
        env = dict(os.environ, GODMODE_STATE_HOME=str(self.project / ".state"))
        subprocess.run([sys.executable, "-B", str(GODMODE_CLI), "--project",
                        str(self.project), "init"], cwd=self.project, check=True,
                       capture_output=True, text=True, env=env)
        run_hook("session-start",
                 {"hook_event_name": "SessionStart", "cwd": str(self.project)},
                 self.project)
        run_hook("user-prompt",
                 {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                  "prompt": "please add a retry to the uploader"},
                 self.project)
        self.transcript = self.project / "agent.jsonl"
        self.transcript.write_text(
            '{"type":"assistant","message":{"content":'
            '[{"type":"text","text":"Checkpoint complete."}]}}\n',
            encoding="utf-8")

    def _stop(self) -> subprocess.CompletedProcess:
        return run_hook("stop", {"hook_event_name": "Stop", "cwd": str(self.project),
                                 "transcript_path": str(self.transcript)},
                        self.project)

    def test_without_an_escalation_the_stop_still_blocks(self) -> None:
        # Positive control (the same reasoning `test_subagent_scope.py`
        # names): proves the fixture actually reaches the scope gate, so
        # the escalation test below is not vacuously true.
        proc = self._stop()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SCOPE STILL OPEN", proc.stdout)
        self.assertIn('"decision": "block"', proc.stdout)

    def test_an_escalated_scope_check_passes_and_prints_the_reason(self) -> None:
        env = dict(os.environ, GODMODE_STATE_HOME=str(self.project / ".state"))
        escalated = subprocess.run(
            [sys.executable, "-B", str(GODMODE_CLI), "--project", str(self.project),
             "governance", "escalate", "scope-still-open",
             "--reason", "operator agreed to defer"],
            cwd=self.project, capture_output=True, text=True, env=env)
        self.assertEqual(escalated.returncode, 0, escalated.stderr)

        proc = self._stop()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("SCOPE STILL OPEN", proc.stdout)
        self.assertNotIn('"decision": "block"', proc.stdout)
        self.assertIn("scope-still-open escalated", proc.stdout)
        self.assertIn("operator agreed to defer", proc.stdout)


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GODMODE_STATE_HOME=str(project / ".state"))
    return subprocess.run(
        [sys.executable, "-B", str(GODMODE_CLI), "--project", str(project), *args],
        cwd=project, capture_output=True, text=True, env=env)


def _escalate_cli(project: Path, check: str, reason: str) -> subprocess.CompletedProcess:
    return _cli(project, "governance", "escalate", check, "--reason", reason)


class OpenOperatorAsksStopHookTests(unittest.TestCase):
    """S3 (fix round 1): escalating `open-operator-asks` must SKIP the
    check, not defer its nag by one turn and quietly spend the
    once-per-session nag budget on the way out. An obligation record
    shares its salient (>=5 letter) words with the Stop reply text -
    `_open_obligations_touched`'s own match bar - and the reply carries
    none of `_COMPLETION_VOCAB` so `scope_reason` never also fires,
    keeping this test isolated to the one check under test."""

    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True,
                       capture_output=True)
        out = _cli(self.project, "init")
        self.assertEqual(out.returncode, 0, out.stderr)
        run_hook("session-start",
                 {"hook_event_name": "SessionStart", "cwd": str(self.project)},
                 self.project)
        recorded = _cli(self.project, "remember", "--kind", "obligation",
                        "--subject", "retry logic uploader",
                        "--value", "add exponential backoff retry logic")
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.transcript = self.project / "agent.jsonl"
        self.transcript.write_text(
            '{"type":"assistant","message":{"content":'
            '[{"type":"text","text":'
            '"The retry logic module for the uploader now retries with backoff."}]}}\n',
            encoding="utf-8")

    def _stop(self) -> subprocess.CompletedProcess:
        return run_hook("stop", {"hook_event_name": "Stop", "cwd": str(self.project),
                                 "transcript_path": str(self.transcript)},
                        self.project)

    def test_without_an_escalation_the_obligation_is_named(self) -> None:
        proc = self._stop()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("unfinished", proc.stdout)
        self.assertIn("retry logic uploader", proc.stdout)

    def test_an_escalated_ask_check_is_skipped_every_turn_it_stays_live(self) -> None:
        escalated = _escalate_cli(self.project, "open-operator-asks",
                                  "already triaged, tracked elsewhere")
        self.assertEqual(escalated.returncode, 0, escalated.stderr)

        # Two turns, not one: if the escalated turn still spent the
        # once-per-session nag budget (the S3 regression), the SECOND
        # stop would fall silent instead of naming the escalation again.
        for _ in range(2):
            proc = self._stop()
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("unfinished promises", proc.stdout)
            self.assertIn("open-operator-asks escalated", proc.stdout)
            self.assertIn("already triaged, tracked elsewhere", proc.stdout)


class DoneBarTurnRegressionTests(unittest.TestCase):
    """S2 (fix round 1): the done-bar's own per-Stop turn tick must be
    inert to every detector that reasons about repeated or unattested
    action - an ordinary session that stops several times with a live
    escalation is not a loop and not unattested work. Five stops, each
    with the escalation freshly live (so `note_turn` ticks every time),
    is the shape the review measured as broken before this fix: three
    stops read as a blocking loop, five as a watchdog anomaly."""

    def test_five_stops_with_a_live_escalation_stay_clean(self) -> None:
        project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, project, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=project, check=True,
                       capture_output=True)
        out = _cli(project, "init")
        self.assertEqual(out.returncode, 0, out.stderr)
        run_hook("session-start",
                 {"hook_event_name": "SessionStart", "cwd": str(project)}, project)
        transcript = project / "agent.jsonl"
        transcript.write_text(
            '{"type":"assistant","message":{"content":'
            '[{"type":"text","text":"Checkpoint complete."}]}}\n',
            encoding="utf-8")
        for _ in range(5):
            escalated = _escalate_cli(project, "scope-still-open", "operator agreed to defer")
            self.assertEqual(escalated.returncode, 0, escalated.stderr)
            proc = run_hook("stop", {"hook_event_name": "Stop", "cwd": str(project),
                                     "transcript_path": str(transcript)}, project)
            self.assertEqual(proc.returncode, 0, proc.stderr)

        loop_report = _cli(project, "loop")
        self.assertEqual(loop_report.returncode, 0, loop_report.stdout + loop_report.stderr)
        watchdog_report = _cli(project, "watchdog")
        self.assertEqual(watchdog_report.returncode, 0,
                         watchdog_report.stdout + watchdog_report.stderr)


if __name__ == "__main__":
    unittest.main()
