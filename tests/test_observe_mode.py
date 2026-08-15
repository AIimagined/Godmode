"""Observe mode + ROI digest (U-E7).

A gate profile where every detector and gate keeps classifying exactly as it
always did, but a deny/ask never reaches the host as a block: it becomes an
archive record (`refusal`, `observed: True`) and a `systemMessage` advisory
instead. Entry is a single, explicit, validated policy-file edit
(`.godmode-authorization-policy.json`'s `gate_mode: "observe"`) - never
reachable through `init --profile`, never silent, and never something a
malformed value can back into.

Every case here drives the real hook process, the way `test_hook_end_to_end.py`
and `test_stage_from_refusal.py` do, because the conversion this unit adds
lives at the bottom of `godmode_session_hook.py`'s pre-tool boundary - a
`classify_action` call alone would never see it.
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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_assess import assess  # noqa: E402
from godmode_runtime.godmode_errors import AuthorizationError  # noqa: E402
from godmode_runtime.godmode_profile import PROFILE_NAMES, apply_profile  # noqa: E402
from godmode_runtime.godmode_roi import (  # noqa: E402
    CAUSAL_DENYLIST, render_digest, render_roi, roi_digest, roi_report,
)
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    GATE_MODE_OBSERVE, POLICY_FILENAME, local_authorization_policy,
    stage_from_refusal,
)
from test_godmode_runtime import isolated_project  # noqa: E402
from test_hook_end_to_end import GIT_ASK_NOW, MUST_DENY  # noqa: E402

FORCE_PUSH = "git push --force origin main"
ASK_TIER = "rm -rf build"


def _enable_observe(project: Path) -> None:
    (project / POLICY_FILENAME).write_text(
        json.dumps({"gate_mode": GATE_MODE_OBSERVE}), encoding="utf-8"
    )


def _decide(project: Path, tool: str, tool_input: dict) -> dict:
    """Run the hook exactly as the host runs it. Returns a shape covering all
    three possible outcomes: an unmarked allow, an allow carrying a
    `systemMessage`, or a `deny`/`ask` `permissionDecision`."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": str(project),
    }
    done = subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
    )
    body = (done.stdout or "").strip()
    if not body:
        return {"decision": "allow", "reason": "", "system_message": None}
    parsed = json.loads(body)
    specific = parsed.get("hookSpecificOutput")
    if specific:
        return {
            "decision": str(specific.get("permissionDecision", "?")),
            "reason": str(specific.get("permissionDecisionReason", "")),
            "system_message": None,
        }
    return {"decision": "allow", "reason": "",
            "system_message": parsed.get("systemMessage")}


def _session_start(project: Path) -> dict:
    payload = {"hook_event_name": "SessionStart", "cwd": str(project)}
    done = subprocess.run(
        [sys.executable, str(HOOK), "session-start", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, cwd=str(project),
    )
    return json.loads((done.stdout or "").strip())


class R5UnderObserveIsAllowedAndRecorded(unittest.TestCase):
    """Red-first: R5 op under observe -> allowed at the host boundary, a
    `refusal` record with `observed: True` is written, and an advisory
    `systemMessage` names what would have happened."""

    def test_force_push_allowed_recorded_and_advised_under_observe(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            result = _decide(project, "Bash", {"command": FORCE_PUSH})

            self.assertEqual(result["decision"], "allow")
            self.assertIsNotNone(result["system_message"])
            self.assertIn("OBSERVE MODE", result["system_message"])
            self.assertIn("denied", result["system_message"])

            records = archive.select(kind="refusal", limit=10)
            self.assertEqual(len(records), 1)
            data = records[0]["data"]
            self.assertIs(data["observed"], True)
            self.assertEqual(data["would_have"], "deny")
            self.assertEqual(data["operation"], FORCE_PUSH)

    def test_the_same_op_under_normal_mode_still_denies(self) -> None:
        """Green control: no policy file at all, the same command, the same
        project shape - the only variable that changed above was the policy."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            result = _decide(project, "Bash", {"command": FORCE_PUSH})
            self.assertEqual(result["decision"], "deny")
            records = archive.select(kind="refusal", limit=10)
            self.assertEqual(len(records), 1)
            self.assertNotIn("observed", records[0]["data"])


class AskTierAlsoConvertsUnderObserve(unittest.TestCase):
    """Not only the outright R5 refusal - an ordinary `ask` converts too."""

    def test_an_ask_tier_op_is_allowed_and_recorded_as_would_have_asked(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            result = _decide(project, "Bash", {"command": ASK_TIER})

            self.assertEqual(result["decision"], "allow")
            self.assertIsNotNone(result["system_message"])
            self.assertIn("OBSERVE MODE", result["system_message"])
            self.assertIn("asked about", result["system_message"])

            records = archive.select(kind="refusal", limit=10)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["data"]["would_have"], "ask")

    def test_the_same_op_under_normal_mode_still_asks(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            result = _decide(project, "Bash", {"command": ASK_TIER})
            self.assertEqual(result["decision"], "ask")
            # An `ask` decision writes no refusal record even outside observe
            # mode - only the outright R5 deny path does (see
            # test_stage_from_refusal.py::NothingToStage).
            self.assertEqual(archive.select(kind="refusal", limit=10), [])


class PlantEveryBlockedCommandInTheCorpusConvertsUnderObserve(unittest.TestCase):
    """Plant: a blocking path reachable under observe is red. Every command
    `test_hook_end_to_end.py` proves the gate must deny or ask about is run
    again here, under observe, and none of them may reach the host as a
    block - if a single check were left out of the conversion (a future
    refactor that adds a new way to set `preview["allow"] = False` without
    routing it through the single point `_apply_observe_mode` sits at), the
    missed command shows up here as a `deny`/`ask` and fails this test."""

    def test_the_full_must_deny_and_ask_corpus_is_silent_under_observe(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            leaked = []
            for label, tool, tool_input in MUST_DENY + GIT_ASK_NOW:
                result = _decide(project, tool, tool_input)
                if result["decision"] != "allow":
                    leaked.append((label, result["decision"]))
            self.assertEqual(leaked, [],
                             f"a blocking decision reached the host under observe: {leaked}")


class ObserveEntryAnnouncedAtSessionStart(unittest.TestCase):
    """Tighten-only interaction: observe is a loosening, so it must be loud.
    A session opened under it is told so in the same brief every session
    reads, not only at the moment a call would have been blocked."""

    def test_session_start_brief_announces_observe_mode(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            brief = _session_start(project)
            context = brief["hookSpecificOutput"]["additionalContext"]
            self.assertIn("OBSERVE mode", context)
            self.assertIn("nothing will be blocked", context)

    def test_session_start_brief_is_silent_about_observe_in_normal_mode(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            brief = _session_start(project)
            context = brief["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("OBSERVE mode", context)


class StageFromRefusalNeverStagesAnObservedRefusal(unittest.TestCase):
    """U-E7 decision, pinned: an `observed: True` refusal is never stageable
    by default. Nothing was actually blocked when it was written, so there
    is no live escalation for a staged capability to answer."""

    def test_only_an_observed_refusal_on_record_has_nothing_to_stage(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            _decide(project, "Bash", {"command": FORCE_PUSH})
            with self.assertRaises(AuthorizationError) as ctx:
                stage_from_refusal(archive)
            self.assertIn("nothing to stage", str(ctx.exception))

    def test_nth_skips_past_an_observed_refusal_to_the_real_one_behind_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            # A real refusal lands first...
            _decide(project, "Bash", {"command": FORCE_PUSH})
            # ...then the policy flips to observe and a second refusal lands
            # advisory-only.
            _enable_observe(project)
            _decide(project, "Bash", {"command": "git reset --hard HEAD~3"})

            self.assertEqual(len(archive.select(kind="refusal", limit=10)), 2)
            # nth=1 (the most recent STAGEABLE one) reaches past the observed
            # record straight to the real one.
            self.assertEqual(stage_from_refusal(archive, nth=1), FORCE_PUSH)
            with self.assertRaises(AuthorizationError):
                stage_from_refusal(archive, nth=2)


class RoiExcludesObservedRefusalsFromRealDenialCounts(unittest.TestCase):
    """`roi_report`'s `gate.denied` counts real enforcement outcomes only -
    an observed refusal must never inflate it."""

    def test_observed_refusals_do_not_fold_into_gate_denied(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _decide(project, "Bash", {"command": FORCE_PUSH})  # real deny
            _enable_observe(project)
            _decide(project, "Bash", {"command": "git reset --hard HEAD~3"})
            _decide(project, "Bash", {"command": ASK_TIER})

            report = roi_report(archive, sessions=None)
            self.assertEqual(report["gate"]["denied"], 1)

            digest = roi_digest(archive, sessions=None)
            self.assertEqual(digest["would_have_denied"], 1)
            self.assertEqual(digest["would_have_asked"], 1)
            self.assertTrue(all(b.startswith("seq:") for b in digest["basis"]))


class DigestRendersWithZeroCausalVocabulary(unittest.TestCase):
    """Same causal-denylist discipline as U-E1's `render_roi` - extended to
    `render_digest`."""

    def test_digest_never_claims_savings_or_prevention(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            _decide(project, "Bash", {"command": FORCE_PUSH})
            _decide(project, "Bash", {"command": ASK_TIER})
            text = render_digest(roi_digest(archive, sessions=None))
            for word in CAUSAL_DENYLIST:
                self.assertNotIn(word, text.lower())
            self.assertIn("would-have-denied", text)
            self.assertIn("would-have-asked", text)

    def test_roi_render_also_stays_causal_free_when_observed_refusals_exist(self) -> None:
        """Extends the U-E1 denylist coverage: an archive that mixes real and
        observed refusals must not leak a causal word into either report."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _decide(project, "Bash", {"command": FORCE_PUSH})
            _enable_observe(project)
            _decide(project, "Bash", {"command": "git reset --hard HEAD~3"})
            text = render_roi(roi_report(archive, sessions=None))
            for word in CAUSAL_DENYLIST:
                self.assertNotIn(word, text.lower())


class AssessSurfacesTheObservePostureExplicitly(unittest.TestCase):
    def test_assess_reports_gate_mode_observe_with_a_finding(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            report = assess(project, archive=archive)
            self.assertEqual(report["gate_mode"], GATE_MODE_OBSERVE)
            codes = [f["code"] for f in report["findings"]]
            self.assertIn("gate-observe-mode", codes)

    def test_assess_reports_enforce_when_no_policy_is_present(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            report = assess(project, archive=archive)
            self.assertEqual(report["gate_mode"], "enforce")
            codes = [f["code"] for f in report["findings"]]
            self.assertNotIn("gate-observe-mode", codes)


class MalformedGateModeRefusesLoudRatherThanEnteringObserve(unittest.TestCase):
    """A typo must not silently loosen enforcement - `gate_mode` is
    validated to exactly one legal spelling, and anything else raises."""

    def test_local_authorization_policy_raises_on_an_unrecognised_value(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / POLICY_FILENAME).write_text(
                json.dumps({"gate_mode": "observd"}), encoding="utf-8"
            )
            with self.assertRaises(AuthorizationError):
                local_authorization_policy(archive)

    def test_the_hook_degrades_a_malformed_gate_mode_to_enforcement_not_observe(self) -> None:
        """The broad GodmodeError handler around the hook's own decision
        degrades to *allow everything* - so a malformed `gate_mode` must
        never reach it un-caught, and the call still has to deny R5 the
        same way test_hook_end_to_end.py's malformed-policy case does for
        approval_required."""
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / POLICY_FILENAME).write_text(
                json.dumps({"gate_mode": "observd"}), encoding="utf-8"
            )
            result = _decide(project, "Bash", {"command": FORCE_PUSH})
            self.assertEqual(result["decision"], "deny")


class InitProfileNeverTouchesGateMode(unittest.TestCase):
    """`init --profile` stays an enforcement-only path - observe mode has
    exactly one door in, and this is not it (godmode_profile.py's own
    module docstring names the same decision)."""

    def test_no_profile_ever_writes_or_reports_gate_mode(self) -> None:
        for profile in PROFILE_NAMES:
            with isolated_project() as (project, _state, _anchor, _archive):
                result = apply_profile(project, profile)
                self.assertNotIn("gate_mode", result)
                policy_path = project / POLICY_FILENAME
                if policy_path.exists():
                    on_disk = json.loads(policy_path.read_text(encoding="utf-8"))
                    self.assertNotIn("gate_mode", on_disk)


if __name__ == "__main__":
    unittest.main()
