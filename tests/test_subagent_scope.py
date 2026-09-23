"""Subagent traffic is not operator scope.

Observed: 34 request records were minted from agent hand-back messages
in one session, and three subagents were blocked at SubagentStop over
asks the parent session owned. A hand-back is data about work done, not
an ask; a subagent's scope is its dispatch prompt.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Absolute, not relative (divergence from the brief): `run_hook` sets
# `cwd=project`, a fresh temp directory with no `hooks/` of its own - a
# path relative to the repo root only resolves by accident, from
# whichever directory happened to launch the suite. test_hook_end_to_end.py
# hits the same boundary and anchors the same way.
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"


def run_hook(event: str, payload: dict, project: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, GODMODE_STATE_HOME=str(project / ".state"), CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))
    return subprocess.run([sys.executable, "-I", "-B", str(HOOK), event], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=project, env=env)


def _history(project: Path, kind: str) -> list[dict]:
    # Divergence from the brief: `python -m scripts.godmode_runtime` names
    # no runnable entrypoint (that package has no `__main__.py`) and would
    # look for the `scripts` package under `cwd=project` besides. The real
    # CLI is `scripts/godmode.py`, and its project is named with `--project`
    # rather than by `cwd` (test_claim_calibration.py reads history the
    # same way, in-process; this stays a subprocess call to also exercise
    # the CLI's own argv parsing).
    out = subprocess.run([sys.executable, "-B", str(GODMODE_CLI), "--project", str(project),
                          "history", "--kind", kind, "--limit", "50"],
                         capture_output=True, text=True, cwd=project,
                         env=dict(os.environ, GODMODE_STATE_HOME=str(project / ".state")))
    # Fix round 1 (cheap item 3): a failing history read used to read back
    # as "0 open requests" - indistinguishable from a project that
    # genuinely has none, so a CLI regression could silently vacuous every
    # test in this module. The read's own exit code is asserted now.
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout).get("records", [])


def open_requests(project: Path) -> int:
    records = _history(project, "request")
    return sum(1 for r in records if (r.get("data") or {}).get("status") == "open")


def law_candidates(project: Path) -> list[dict]:
    """Every `lesson` record shaped like a correction/instruction candidate
    (`record_correction_candidate`/`record_instruction_candidate` both
    write kind "lesson", subject "correction:<hex>" or
    "instruction:<hex>")."""
    records = _history(project, "lesson")
    return [r for r in records
            if str(r.get("subject", "")).startswith(("correction:", "instruction:"))]


class SubagentScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        # Divergence from the brief: a bare session-start call left the
        # archive "not initialized" (confirmed by running the hook by hand
        # against a fresh project and reading its own stdout back), so
        # every later mint was a silent no-op against an archive that did
        # not exist yet. test_hook_end_to_end.py's setUpModule initializes
        # the same way (in-process there; the CLI here, since this module
        # already shells out for everything else).
        subprocess.run(
            [sys.executable, "-B", str(GODMODE_CLI), "--project", str(self.project), "init"],
            cwd=self.project, check=True, capture_output=True, text=True,
            env=dict(os.environ, GODMODE_STATE_HOME=str(self.project / ".state")))
        run_hook("session-start", {"hook_event_name": "SessionStart", "cwd": str(self.project)}, self.project)

    def test_hand_back_mints_no_ask(self) -> None:
        before = open_requests(self.project)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                   "prompt": "<agent-message from=\"abc123\">\n[Subagent hand-back] done: C:/x/report.md\n</agent-message>"}
        proc = run_hook("user-prompt", payload, self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(open_requests(self.project), before)

    def test_operator_prompt_still_mints_ask(self) -> None:
        before = open_requests(self.project)
        run_hook("user-prompt", {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                                 "prompt": "please add a retry to the uploader"}, self.project)
        self.assertEqual(open_requests(self.project), before + 1)

    def test_operator_prompt_quoting_a_relay_frame_still_mints_ask(self) -> None:
        """Fix round 1, Important item 1 (plan-mandated, coordinator ruling
        'tighten'): the earlier `_is_agent_relay` scanned the first THREE
        lines with `re.M`, so an operator prompt that merely quotes or
        describes a hand-back further down - not on its own opening line -
        was misclassified as the relay itself and its ask was dropped.
        Judged on the first non-blank line only, this stays an operator
        ask."""
        before = open_requests(self.project)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                   "prompt": "handle this handoff:\n<agent-message from=\"abc123\">\n"
                             "[Subagent hand-back] done: C:/x/report.md\n</agent-message>"}
        proc = run_hook("user-prompt", payload, self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(open_requests(self.project), before + 1)

    def test_relay_preceded_by_blank_lines_mints_no_ask(self) -> None:
        """The other half of Important item 1: a real relay envelope after
        leading blank lines must still be caught - the old "first three
        lines" window, applied to a prompt starting with blank lines,
        looked at the wrong three lines and missed it."""
        before = open_requests(self.project)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                   "prompt": "\n\n\n<agent-message from=\"abc123\">\n"
                             "[Subagent hand-back] done: C:/x/report.md\n</agent-message>"}
        proc = run_hook("user-prompt", payload, self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(open_requests(self.project), before)

    def test_relay_prompt_mints_no_law_candidate(self) -> None:
        """Fix round 1, cheap item 2: a hand-back is agent-authored, not an
        operator correcting or instructing anything, so it must not seed a
        `record_correction_candidate`/`record_instruction_candidate` law
        candidate either. The body below carries both triggers for real -
        two correction markers ("wrong", "missed") and an instruction
        marker with an imperative verb close behind it ("always run") - so
        this proves the guard suppresses them, not that the text never
        would have tripped them."""
        before = law_candidates(self.project)
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                   "prompt": "<agent-message from=\"abc123\">\n[Subagent hand-back] "
                             "the previous attempt was wrong and missed the edge case; "
                             "always run the tests again next time\n</agent-message>"}
        proc = run_hook("user-prompt", payload, self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(law_candidates(self.project), before)

    def test_subagent_stop_never_blocks_on_parent_asks(self) -> None:
        run_hook("user-prompt", {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                                 "prompt": "please add a retry to the uploader"}, self.project)
        transcript = self.project / "agent.jsonl"
        # Divergence from the brief: "done: report written" also trips
        # `_unrecorded_done_claims` (the THE DONE BAR gate), which for a
        # subagent is already advisory-only and masks the scope gate
        # entirely (`if scope_reason and not done_shaped`) - a false pass
        # that proved nothing about the scope gate itself. "Checkpoint
        # complete." matches the same completion vocabulary the scope gate
        # keys on but is filtered out of the done-bar detector by
        # `_PROCESS_SENTENCE` (bookkeeping language, not a claim about the
        # work) - confirmed by hand: before any fix, this payload printed
        # `{"decision": "block", ...SCOPE STILL OPEN...}` for a
        # `subagent-stop` event over the PARENT session's own open ask.
        transcript.write_text('{"type":"assistant","message":{"content":[{"type":"text","text":"Checkpoint complete."}]}}\n', encoding="utf-8")
        proc = run_hook("subagent-stop", {"hook_event_name": "SubagentStop", "cwd": str(self.project),
                                          "agent_transcript_path": str(transcript)}, self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("SCOPE STILL OPEN", proc.stdout + proc.stderr)
        self.assertNotIn('"decision": "block"', proc.stdout)

    def test_positive_control_the_parent_stop_still_blocks_on_the_same_scope(self) -> None:
        """Fix round 1, cheap item 3: the same archive and the same
        transcript text through the PARENT `stop` event must still block
        on `SCOPE STILL OPEN` - proof `_scope_block_reason` itself still
        fires and this module's assertions are not vacuously true (a
        `subagent-stop` guard that never gets exercised would pass
        `test_subagent_stop_never_blocks_on_parent_asks` for a reason that
        has nothing to do with the fix)."""
        run_hook("user-prompt", {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project),
                                 "prompt": "please add a retry to the uploader"}, self.project)
        transcript = self.project / "agent.jsonl"
        transcript.write_text('{"type":"assistant","message":{"content":[{"type":"text","text":"Checkpoint complete."}]}}\n', encoding="utf-8")
        proc = run_hook("stop", {"hook_event_name": "Stop", "cwd": str(self.project),
                                 "transcript_path": str(transcript)}, self.project)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SCOPE STILL OPEN", proc.stdout)
        self.assertIn('"decision": "block"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
