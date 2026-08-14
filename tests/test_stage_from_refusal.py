"""One-tap staged capability from the last refusal (U-E5).

The refusal at the R5 boundary already named the exact remedy - `godmode
authorize stage --operation <op>` - and asked the operator to retype it
byte-for-byte from a scrollback line. `--from-last-refusal` reads that same
operation back from the record the gate itself wrote, instead of the eye.
Nothing about the trust model moves: the password is still required, the
capability is still spent once, it still expires. Only the typing changes.

Every case here is driven through the real hook process (the way the host
drives it, per test_hook_end_to_end.py's own reasoning) rather than fed a
hand-written operation string, because the refusal record this unit reads
back is written by that same process.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = SCRIPTS / "godmode.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_errors import ArchiveError, AuthorizationError  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker, stage_from_refusal  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

PASSWORD = "correct horse battery staple"
FORCE_PUSH = "git push --force origin main"
HARD_RESET = "git reset --hard HEAD~3"
ASK_ONLY = "git commit -m 'a message'"


def _decide(project: Path, command: str) -> tuple[str, str]:
    """Run the hook exactly the way the host runs it and return (decision, reason)."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(project),
    }
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
    )
    body = (done.stdout or "").strip()
    if not body:
        return "allow", ""
    specific = json.loads(body).get("hookSpecificOutput") or {}
    return (str(specific.get("permissionDecision", "?")),
            str(specific.get("permissionDecisionReason", "")))


class RecordedRefusalStagesExactly(unittest.TestCase):
    """Case 1: a refusal recorded by the hook path stages EXACTLY that operation."""

    def test_stage_from_refusal_returns_the_exact_recorded_operation(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            decision, reason = _decide(project, FORCE_PUSH)
            self.assertEqual(decision, "deny", reason)
            staged = stage_from_refusal(archive)
        self.assertEqual(staged, FORCE_PUSH)


class StagedFromRefusalKeepsTheTokenContract(unittest.TestCase):
    """Case 2: spent once, expires - reusing the broker's own expiry pattern."""

    def test_a_capability_staged_from_a_refusal_is_spent_once(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            _decide(project, FORCE_PUSH)
            operation = stage_from_refusal(archive)
            broker.stage(operation, PASSWORD)
            self.assertIsNotNone(broker.consume_staged(FORCE_PUSH))
            self.assertIsNone(
                broker.consume_staged(FORCE_PUSH),
                "a capability staged from a refusal was spendable twice",
            )

    def test_a_capability_staged_from_a_refusal_expires(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            _decide(project, FORCE_PUSH)
            operation = stage_from_refusal(archive)
            broker.stage(operation, PASSWORD, ttl_seconds=10)
            data = broker._load()
            for entry in data["staged"]:
                entry["expires_at"] = 0
            broker._store(data)
            self.assertIsNone(broker.consume_staged(FORCE_PUSH))


class NothingToStage(unittest.TestCase):
    """Case 3: no refusal on record -> GodmodeError "nothing to stage"."""

    def test_no_refusal_on_record_refuses_with_nothing_to_stage(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(AuthorizationError) as ctx:
                stage_from_refusal(archive)
        self.assertIn("nothing to stage", str(ctx.exception))

    def test_an_ask_decision_leaves_nothing_to_stage(self) -> None:
        # Only the outright R5 refusal - the one that names "stage a
        # capability" as its own remedy - is recorded. An `ask` decision is
        # answered by the operator's own approve/deny click in the same
        # turn, so recording it as a stageable refusal would be misleading:
        # there is no operation here a staged token would ever be spent on.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            decision, _reason = _decide(project, ASK_ONLY)
            self.assertEqual(decision, "ask")
            with self.assertRaises(AuthorizationError):
                stage_from_refusal(archive)


class NthDisambiguates(unittest.TestCase):
    """Case 4: --nth 2 picks the second-latest refusal."""

    def test_nth_2_picks_the_second_latest_refusal(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _decide(project, FORCE_PUSH)
            _decide(project, HARD_RESET)
            self.assertEqual(stage_from_refusal(archive, nth=1), HARD_RESET)
            self.assertEqual(stage_from_refusal(archive, nth=2), FORCE_PUSH)

    def test_nth_past_the_recorded_refusals_has_nothing_to_stage(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _decide(project, FORCE_PUSH)
            with self.assertRaises(AuthorizationError):
                stage_from_refusal(archive, nth=2)


class EchoedBeforePasswordIsConsumed(unittest.TestCase):
    """Case 5: the staged op is echoed verbatim before the password is accepted."""

    def test_the_operation_is_echoed_even_when_the_password_is_wrong(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            _decide(project, FORCE_PUSH)
            done = subprocess.run(
                [sys.executable, str(GODMODE_CLI), "--project", str(project),
                 "authorize", "stage", "--from-last-refusal", "--password-stdin"],
                input="the wrong password\n", capture_output=True, text=True, timeout=30,
            )
        # The password was rejected - the capability must not have been staged.
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        # Yet the operation the CLI is about to authorize was already printed,
        # proving it was echoed before the (failing) password check ran.
        self.assertIn(FORCE_PUSH, done.stdout)


class RefusalReasonNamesTheRemedy(unittest.TestCase):
    """Case 6: the refusal reason carries the literal `!` remedy line."""

    def test_the_refusal_reason_contains_the_literal_stage_line(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _decision, reason = _decide(project, FORCE_PUSH)
        self.assertIn("! godmode authorize stage --from-last-refusal", reason)


class TamperedRefusalIsCaughtByTheExistingMonitor(unittest.TestCase):
    """Plant: tampering a refusal record's operation is caught by the archive's
    own hash-chain integrity check. The monitor is not rebuilt here - this
    test only pins that the coverage already extends to the new kind."""

    def test_tampering_a_refusal_records_operation_breaks_the_chain(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _decide(project, FORCE_PUSH)
            self.assertTrue(archive.verify()["valid"])

            refusal_path = archive.event_paths()[-1]
            payload = json.loads(refusal_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "refusal")
            payload["data"]["operation"] = "rm -rf /"
            refusal_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ArchiveError):
                archive.verify()


if __name__ == "__main__":
    unittest.main()
