"""NS-10k: the unattended gating tier.

An "ask" is a question, and a question needs someone on the other end to
answer it. A session with no operator present cannot answer one - so this
tier applies a stricter row instead of a silent allow or an unanswerable
ask: the outright-refuse floor drops one tier (R4 joins R5), a staged
capability's lifetime halves, and `--without-preflight` (the operator's own
say-so to skip a green preflight) has no meaning with nobody there to say
so.

Detection (`attended()`) is read in a fixed order - an explicit
`GODMODE_ATTENDED` override, then `CI`, then a host payload's own
`permission_mode` (fix round 1: the one "no human answers" signal already
live on a Claude Code payload today), then its `session_type`, then an
interactive TTY - and the default when none of those resolve is
**attended**, on purpose: piping a payload over stdin is how every host
invokes a hook whether or not an operator is watching, so its absence
alone proves nothing. This is what keeps every pre-existing corpus fixture
and hook test - none of which touch any of these signals - on the attended
row, unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOKS_DIR = PLUGIN_ROOT / "hooks"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker, attended, classify_action, explain_policy,
    halved_ttl_seconds, policy_row, refuse_outright_tiers,
)
from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402
from _host_env import scrubbed_env, scrubbed_environment  # noqa: E402

# Loaded the same way tests/test_field_report_27.py reaches hook internals -
# a hook script is not a package member, so a plain `import` needs the
# hooks directory on `sys.path` first.
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
import godmode_session_hook as hook  # noqa: E402

PASSWORD = "correct horse battery staple"
# A real category the corpus already pins at R4 (godmode_sentinel's
# `_TIER_BY_CATEGORY["filesystem-mutation"] == "R4"`): a `find` action that
# actually mutates. Attended, this asks; unattended, the lowered floor
# refuses it outright.
FILESYSTEM_MUTATION = 'find . -name "*.tmp" -delete'

_ATTENDED_ENV = "GODMODE_ATTENDED"


def _clear_signals():
    """A context that removes every ambient attended/unattended signal, so
    a test of one source is not accidentally decided by another (e.g. a
    real CI runner's own `CI` env var, or this shell's own TTY state)."""
    return mock.patch.dict(os.environ, {}, clear=False)


class AttendedDetectionTests(unittest.TestCase):
    """Each source, in isolation, and the one rule about their order: an
    explicit override always wins."""

    def test_env_override_true(self) -> None:
        with mock.patch.dict(os.environ, {_ATTENDED_ENV: "1"}, clear=False):
            os.environ.pop("CI", None)
            self.assertTrue(attended())

    def test_env_override_false(self) -> None:
        with mock.patch.dict(os.environ, {_ATTENDED_ENV: "0"}, clear=False):
            self.assertFalse(attended())

    def test_env_override_accepts_common_spellings(self) -> None:
        for value in ("false", "No", "OFF", ""):
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: value}, clear=False):
                self.assertFalse(attended(), value)
        for value in ("1", "true", "Yes", "on"):
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: value}, clear=False):
                self.assertTrue(attended(), value)

    def test_ci_means_unattended(self) -> None:
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            self.assertFalse(attended())

    def test_env_override_wins_over_ci(self) -> None:
        with mock.patch.dict(os.environ, {"CI": "true", _ATTENDED_ENV: "1"}, clear=False):
            self.assertTrue(attended())

    def test_permission_mode_auto_is_unattended(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            self.assertFalse(attended(permission_mode="auto"))

    def test_permission_mode_dont_ask_is_unattended(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            self.assertFalse(attended(permission_mode="dontAsk"))

    def test_permission_mode_bypass_permissions_is_unattended(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            self.assertFalse(attended(permission_mode="bypassPermissions"))

    def test_an_ask_capable_permission_mode_falls_through(self) -> None:
        """`default`, `plan`, `acceptEdits` still prompt a person - none of
        them are evidence either way, so this falls to the attended
        default, same as an unrecognised `session_type` does."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            for mode in ("default", "plan", "acceptEdits", "", None):
                with self.subTest(mode=mode):
                    self.assertTrue(attended(permission_mode=mode))

    def test_env_override_wins_over_permission_mode(self) -> None:
        with mock.patch.dict(os.environ, {_ATTENDED_ENV: "1"}, clear=False):
            os.environ.pop("CI", None)
            self.assertTrue(attended(permission_mode="auto"))

    def test_ci_wins_over_permission_mode(self) -> None:
        """CI is checked before permission_mode; an ask-capable mode cannot
        pull a CI run back to attended."""
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            self.assertFalse(attended(permission_mode="default"))

    def test_permission_mode_wins_over_session_type(self) -> None:
        """Placed below the env override and above the TTY check (task-14
        fix round 1): pinned here ahead of `session_type` so a host that
        sends both never has an interactive-sounding session_type paper
        over a permission mode nobody can actually answer through."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            self.assertFalse(attended(session_type="interactive", permission_mode="auto"))

    def test_permission_mode_wins_over_an_interactive_probe(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            with mock.patch(
                    "godmode_runtime.godmode_sentinel._stdin_is_interactive",
                    return_value=True):
                self.assertFalse(attended(permission_mode="auto"))

    def test_session_type_background_is_unattended(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            self.assertFalse(attended(session_type="background"))
            self.assertFalse(attended(session_type="Scheduled"))

    def test_session_type_interactive_is_attended(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            self.assertTrue(attended(session_type="interactive"))

    def test_ci_wins_over_session_type(self) -> None:
        with mock.patch.dict(os.environ, {"CI": "true"}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            self.assertFalse(attended(session_type="interactive"))

    def test_an_unrecognised_session_type_falls_through_to_tty(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            with mock.patch(
                    "godmode_runtime.godmode_sentinel._stdin_is_interactive",
                    return_value=False):
                # Nothing resolves it either way - the documented default.
                self.assertTrue(attended(session_type="some-unknown-label"))

    def test_no_signal_at_all_defaults_attended(self) -> None:
        """The safety property every pre-existing gate test relies on: a
        hook invoked the ordinary way (piped stdin, no host session_type,
        no CI) never becomes unattended by accident."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            with mock.patch(
                    "godmode_runtime.godmode_sentinel._stdin_is_interactive",
                    return_value=False):
                self.assertTrue(attended())

    def test_an_interactive_probe_is_a_positive_signal(self) -> None:
        """B2 (fix round 1): the vacuous `test_a_real_tty_is_attended` - it
        patched raw `sys.stdin.isatty()`/`sys.stdout.isatty()` while the old
        code returned `True` from both branches unconditionally, so it could
        never fail regardless of what it patched. `attended()` now reads
        the module's own `_stdin_is_interactive()` (Windows-correct, unlike
        raw `isatty()` which lies for a redirected NUL) - patching THAT and
        asserting it was actually called is what makes this test able to
        fail if the call is ever removed or reverted to the raw probe."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            with mock.patch(
                    "godmode_runtime.godmode_sentinel._stdin_is_interactive",
                    return_value=True) as probe:
                self.assertTrue(attended())
                probe.assert_called_once()

    def test_a_non_interactive_probe_falls_through_to_the_default(self) -> None:
        """The other half of B2's "patches `_stdin_is_interactive` both
        ways": a non-interactive probe is not a negative signal (a host's
        own subprocess pipe is never a TTY even when a human IS driving
        it) - it falls through to the same attended default, but the probe
        must still have been consulted."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            os.environ.pop("CI", None)
            with mock.patch(
                    "godmode_runtime.godmode_sentinel._stdin_is_interactive",
                    return_value=False) as probe:
                self.assertTrue(attended())
                probe.assert_called_once()


class CIAloneFlipsTheRealHookToUnattendedTests(unittest.TestCase):
    """B1 (fix round 1, task-14-review.md): `CI` set to anything non-empty,
    with no `GODMODE_ATTENDED` override, must resolve to the unattended row
    wherever the hook or the broker actually reads `attended()` - the exact
    defect that flipped this repo's own suite red in GitHub Actions
    (`.github/workflows/godmode-verify.yml` sets `CI=true` for every step,
    unscrubbed) while every local run stayed green (no developer shell
    carries `CI`). `tests/_host_env.py` now scrubs `CI` for the harness
    itself; this test proves the row `attended()` resolves to when `CI` IS
    present is the correct one. Verified together with:
    `CI=1 python -m unittest tests.test_hook_end_to_end
    tests.test_ask_only_hook tests.test_sentinel_depth
    tests.test_unattended_tier`.
    """

    def test_ci_alone_refuses_r4_outright_and_halves_a_fresh_ttl(self) -> None:
        with mock.patch.dict(os.environ, {"CI": "1"}, clear=False):
            os.environ.pop(_ATTENDED_ENV, None)
            # The decision: R4 (filesystem-mutation) joins the refuse-
            # outright floor - an ask nobody is there to answer becomes a
            # deny, exactly what `tests/test_hook_end_to_end.py`'s
            # `test_a_question_reads_as_a_question` and
            # `tests/test_ask_only_hook.py`'s
            # `test_r4_still_asks_whatever_the_list_says` used to silently
            # flip under an unscrubbed `CI=true`.
            verdict = classify_action(FILESYSTEM_MUTATION, project_root=PLUGIN_ROOT)
            self.assertFalse(hook.attended(None, None))
            self.assertEqual(
                hook._decision_for(verdict, hook.attended(None, None)), "deny")
            # The lifetime: a fresh capability mints at half the requested
            # TTL - `tests/test_sentinel_depth.py`'s
            # `test_policy_ttl_clamps_to_60_and_900` /
            # `test_without_a_policy_the_default_ttl_stays_current` used to
            # silently halve under the same unscrubbed `CI=true`.
            with isolated_project() as (_project, _state, _anchor, archive):
                archive.initialize()
                broker = CapabilityBroker(archive)
                broker.configure(PASSWORD)
                with mock.patch("godmode_runtime.godmode_sentinel.time.time",
                                 return_value=1_700_000_000.0):
                    broker.stage("git push origin main", PASSWORD, ttl_seconds=100)
                data = broker._load()  # noqa: SLF001
                entry = data["staged"][-1]
                self.assertEqual(entry["expires_at"], 1_700_000_050)


class ScrubbedEnvironmentCIOverrideTests(unittest.TestCase):
    """R2 (fix round 2, task-14-rereview.md): `scrubbed_env`/
    `scrubbed_environment` used to pin `GODMODE_ATTENDED=1` unconditionally
    and apply `extra` on top of it, so `scrubbed_environment(CI="1")` still
    carried the pin alongside the requested `CI=1` - and `attended()` reads
    `GODMODE_ATTENDED` first, so the override silently lost. That made
    `tests/_host_env.py`'s own documented escape hatch ("a test that
    specifically wants the unattended row passes `CI=\"1\"` ... as `extra`")
    false, and was "the next vacuous test waiting to happen" (the review's
    words) exactly because nothing exercised it. This does."""

    def test_scrubbed_env_with_ci_extra_has_no_attended_pin(self) -> None:
        environment = scrubbed_env(CI="1")
        self.assertEqual(environment.get("CI"), "1")
        self.assertNotIn("GODMODE_ATTENDED", environment)

    def test_scrubbed_environment_ci_extra_yields_the_unattended_row(self) -> None:
        with scrubbed_environment(CI="1"):
            self.assertFalse(hook.attended(None, None))
            verdict = classify_action(FILESYSTEM_MUTATION, project_root=PLUGIN_ROOT)
            self.assertEqual(
                hook._decision_for(verdict, hook.attended(None, None)), "deny")

    def test_scrubbed_environment_explicit_godmode_attended_extra_still_wins(self) -> None:
        """The pin is dropped only when `extra` itself names one of the two
        attendance signals - an explicit `GODMODE_ATTENDED` override in
        `extra` must still resolve to what it asks for, not to `CI`'s
        absence."""
        with scrubbed_environment(GODMODE_ATTENDED="0"):
            self.assertFalse(hook.attended(None, None))
        with scrubbed_environment(GODMODE_ATTENDED="1"):
            self.assertTrue(hook.attended(None, None))

    def test_scrubbed_environment_with_no_extra_is_still_attended(self) -> None:
        """The common case - no `extra` at all - must be unaffected by the
        fix: still pinned attended, `CI` still absent."""
        with scrubbed_environment():
            self.assertTrue(hook.attended(None, None))
            self.assertNotIn("CI", os.environ)


class LowerAskThresholdTests(unittest.TestCase):
    """A real category the classifier already pins at R4: attended asks,
    unattended refuses outright - the ask threshold one tier lower."""

    def test_the_category_is_r4_and_protected_regardless_of_attendance(self) -> None:
        verdict = classify_action(FILESYSTEM_MUTATION, project_root=PLUGIN_ROOT)
        self.assertEqual(verdict["tier"], "R4")
        self.assertTrue(verdict["protected"])

    def test_attended_asks(self) -> None:
        verdict = classify_action(FILESYSTEM_MUTATION, project_root=PLUGIN_ROOT)
        self.assertEqual(hook._decision_for(verdict, True), "ask")

    def test_unattended_refuses_outright(self) -> None:
        verdict = classify_action(FILESYSTEM_MUTATION, project_root=PLUGIN_ROOT)
        self.assertEqual(hook._decision_for(verdict, False), "deny")

    def test_r5_still_refuses_outright_either_way(self) -> None:
        verdict = classify_action("git push --force origin main", project_root=PLUGIN_ROOT)
        self.assertEqual(verdict["tier"], "R5")
        self.assertEqual(hook._decision_for(verdict, True), "deny")
        self.assertEqual(hook._decision_for(verdict, False), "deny")

    def test_an_ordinary_worktree_edit_still_only_asks_either_way(self) -> None:
        """R2 is untouched by the lowered floor - only R4 joins R5."""
        verdict = classify_action("echo hello > notes.txt", project_root=PLUGIN_ROOT)
        self.assertEqual(verdict["tier"], "R2")
        self.assertEqual(hook._decision_for(verdict, True), "ask")
        self.assertEqual(hook._decision_for(verdict, False), "ask")

    def test_refuse_outright_tiers_match_the_row(self) -> None:
        self.assertEqual(refuse_outright_tiers(True), frozenset({"R5"}))
        self.assertEqual(refuse_outright_tiers(False), frozenset({"R4", "R5"}))

    def test_default_call_site_stays_attended(self) -> None:
        """Every pre-existing call to `_decision_for(preview)` (one
        argument) must keep exactly the old behaviour."""
        verdict = classify_action(FILESYSTEM_MUTATION, project_root=PLUGIN_ROOT)
        self.assertEqual(hook._decision_for(verdict), "ask")


class HalvedExpiryTests(unittest.TestCase):
    """Pure arithmetic - no clock at all, fabricated or otherwise."""

    def test_half_of_a_normal_ttl(self) -> None:
        self.assertEqual(halved_ttl_seconds(300), 150)

    def test_an_odd_ttl_floors_down(self) -> None:
        self.assertEqual(halved_ttl_seconds(101), 50)

    def test_never_reaches_zero(self) -> None:
        self.assertEqual(halved_ttl_seconds(1), 1)
        self.assertEqual(halved_ttl_seconds(0), 1)


class StagedCapabilityHalvedInUnattendedTests(unittest.TestCase):
    """The wiring: `CapabilityBroker.issue`/`stage` actually consult
    `attended()`, checked against a FABRICATED clock (`time.time` patched
    to a fixed value) - never a real sleep, never a tolerance window."""

    def test_attended_keeps_the_full_ttl(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "1"}, clear=False), \
                 mock.patch("godmode_runtime.godmode_sentinel.time.time",
                            return_value=1_700_000_000.0):
                broker.stage("git push origin main", PASSWORD, ttl_seconds=100)
            data = broker._load()  # noqa: SLF001
            entry = data["staged"][-1]
            self.assertEqual(entry["expires_at"], 1_700_000_100)

    def test_unattended_halves_the_ttl(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "0"}, clear=False), \
                 mock.patch("godmode_runtime.godmode_sentinel.time.time",
                            return_value=1_700_000_000.0):
                broker.stage("git push origin main", PASSWORD, ttl_seconds=100)
            data = broker._load()  # noqa: SLF001
            entry = data["staged"][-1]
            self.assertEqual(entry["expires_at"], 1_700_000_050)


class PolicyRowTests(unittest.TestCase):
    """`policy_row` - the one function both the broker and
    `operator --policy` read, so they can never disagree."""

    def test_unattended_row_halves_ttl_and_widens_refuse_outright(self) -> None:
        effective = {"capability_ttl_seconds": 300}
        attended_row = policy_row(effective, True)
        unattended_row = policy_row(effective, False)
        self.assertEqual(attended_row["capability_ttl_seconds"], 300)
        self.assertEqual(unattended_row["capability_ttl_seconds"], 150)
        self.assertEqual(attended_row["refuse_outright_tiers"], ["R5"])
        self.assertEqual(unattended_row["refuse_outright_tiers"], ["R4", "R5"])
        self.assertEqual(attended_row["without_preflight"], "allowed")
        self.assertEqual(unattended_row["without_preflight"], "refused")

    def test_falls_back_to_the_default_ttl_when_unset(self) -> None:
        row = policy_row({}, True)
        self.assertEqual(row["capability_ttl_seconds"], 300)


class ExplainPolicyRowsTests(unittest.TestCase):
    """`operator --policy` names both rows and which one is active."""

    def test_both_rows_are_named(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "1"}, clear=False):
                report = explain_policy(archive)
        self.assertIn("attended", report["rows"])
        self.assertIn("unattended", report["rows"])
        self.assertEqual(
            report["rows"]["unattended"]["capability_ttl_seconds"],
            halved_ttl_seconds(report["rows"]["attended"]["capability_ttl_seconds"]),
        )

    def test_active_row_follows_attended(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "1"}, clear=False):
                self.assertEqual(explain_policy(archive)["active_row"], "attended")
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "0"}, clear=False):
                self.assertEqual(explain_policy(archive)["active_row"], "unattended")


class WithoutPreflightRefusedUnattendedTests(unittest.TestCase):
    """`authorize stage --without-preflight` needs an operator's own say-so
    to accept a red preflight - the unattended row has nobody to say so."""

    def _args(self, **overrides):
        base = dict(
            operation="git push origin main",
            from_last_refusal=False,
            nth=1,
            ttl=None,
            password_stdin=False,
            without_preflight="testing the refusal",
        )
        base.update(overrides)

        @dataclass
        class _Args:
            operation: str
            from_last_refusal: bool
            nth: int
            ttl: int | None
            password_stdin: bool
            without_preflight: str | None

        return _Args(**base)

    def test_refused_unattended(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            archive.initialize()
            runtime = console.Runtime(anchor=anchor, archive=archive)
            args = self._args()
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "0"}, clear=False):
                with self.assertRaises(ArchiveError) as ctx:
                    console.cmd_authorize_stage(args, runtime)
            self.assertIn("unattended", str(ctx.exception))

    def test_available_attended(self) -> None:
        """Attended, the same call reaches past the NS-10k check (and fails
        later, on the preflight/password path this test does not set up) -
        proving the refusal above is this tier's own, not a pre-existing
        failure that would fire either way."""
        with isolated_project() as (project, _state, anchor, archive):
            archive.initialize()
            runtime = console.Runtime(anchor=anchor, archive=archive)
            args = self._args()
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "1"}, clear=False):
                with self.assertRaises(Exception) as ctx:
                    console.cmd_authorize_stage(args, runtime)
            self.assertNotIn("unattended tier", str(ctx.exception))

    def test_without_the_flag_unattended_is_unaffected(self) -> None:
        """The NS-10k check only fires when `--without-preflight` is
        actually passed - an ordinary stage is not refused for being
        unattended by itself."""
        with isolated_project() as (project, _state, anchor, archive):
            archive.initialize()
            runtime = console.Runtime(anchor=anchor, archive=archive)
            args = self._args(without_preflight=None)
            with mock.patch.dict(os.environ, {_ATTENDED_ENV: "0"}, clear=False):
                with self.assertRaises(Exception) as ctx:
                    console.cmd_authorize_stage(args, runtime)
            self.assertNotIn("unattended tier", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
