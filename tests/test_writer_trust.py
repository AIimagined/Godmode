"""Writer trust and single-writer-per-subject (0.3.28 Plan 5 Task 5: NS-8k + NS-11h).

WHY: every record now names its writer (`agent | operator | checker | hook`) and a
trust rank derived from it, so `status` can prefer a persistent human correction
over a later, lower-trust write, and so a subject a subagent did not create cannot
be closed out from under the agent that owns it. A pre-existing archive (sealed
before `writer` existed) must keep verifying unmodified - the record hash covers
only whatever keys were actually present when it was sealed.

Fix round 1 (task-5-review.md): `derive_writer` is now a PURE function - it reads
no environment variable and never prompts (F0/F1). `operator` requires BOTH
`as_operator=True` and `operator_verified=True`, both resolved by the CALLER
(the console) before this is ever invoked; `checker` requires an explicit `role`
argument, resolved by `Chronicle.append` from a CHRONICLED session record
(`Chronicle._chronicled_session_role`), never a bare environment variable read
directly. The single-writer close guard now matches the full terminal-status set
shared with `godmode_status.py` (`CLOSING_STATUSES`, F2) and exempts a confirmed
`operator`/declared `checker` from the refusal. The status trust order only
breaks a genuine contradiction, never a same-status update (F3). The hook-process
check is anchored to the plugin's own installed `hooks/` directory, not a bare
basename (F4).

Fix round 2 (task-5-rereview.md, B1): `checker` was still self-declarable -
`session open --role checker` chronicled the role with no verification at all,
and `_chronicled_session_role` cross-checked a bare `GODMODE_SESSION_ROLE`
claim against the archive's LATEST `session` record, not the caller's own.
Both are closed together: `session open --role checker` now requires operator
verification through the exact `--as-operator` path every other operator
write uses, the granted record carries `role_granted_by: "operator"` and
`writer: "operator"` on itself, and `_chronicled_session_role` accepts
`checker` only from the ONE record named by `GODMODE_SESSION` (a session id,
never a role claim) whose own grant checks out - `GODMODE_SESSION_ROLE` is
retired.
"""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_chronicle import (  # noqa: E402
    CLOSING_STATUSES,
    Chronicle,
    TRUST_ORDER,
    _atomic_json,
    _record_hash,
    anchor_fingerprint,
    derive_writer,
    record_trust,
    record_writer,
    writer_fingerprint,
)
from godmode_runtime.godmode_console import (  # noqa: E402
    _confirm_operator_interactively,
    main as console_main,
)
from godmode_runtime.godmode_constants import SCHEMA_VERSION  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError, GodmodeError  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker  # noqa: E402
from godmode_runtime import godmode_status  # noqa: E402

PASSWORD = "correct horse battery staple"


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


def _run(project: Path, *argv: str, stdin: str | None = None) -> tuple[int, dict]:
    """One CLI round trip, JSON in, JSON out - `console_main` in-process
    (F0's required CLI-flag-reaches-`_append` coverage)."""
    out = io.StringIO()
    stdin_ctx = (
        mock.patch.object(sys, "stdin", io.StringIO(stdin))
        if stdin is not None else contextlib.nullcontext()
    )
    with stdin_ctx, contextlib.redirect_stdout(out):
        code = console_main(["--project", str(project), "--json", *argv])
    text = out.getvalue().strip()
    return code, (json.loads(text) if text else {})


def _run_err(project: Path, *argv: str, stdin: str | None = None) -> tuple[int, str]:
    """Like `_run`, but for a call expected to fail: `GodmodeError` payloads
    print to stderr (`godmode_console.main`), not stdout, so a refusal's
    remedy text has to be read from there."""
    out = io.StringIO()
    stdin_ctx = (
        mock.patch.object(sys, "stdin", io.StringIO(stdin))
        if stdin is not None else contextlib.nullcontext()
    )
    with stdin_ctx, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = console_main(["--project", str(project), "--json", *argv])
    return code, out.getvalue().strip()


def _clean_writer_env():
    """Context manager clearing every env var `derive_writer`'s callers
    read, so a test starts from the undeclared-agent default regardless of
    what the outer test process happens to have set."""
    return mock.patch.dict(
        os.environ,
        {
            "GODMODE_AS_OPERATOR": "",
            "GODMODE_SESSION_ROLE": "",
            "GODMODE_SESSION": "",
            "GODMODE_OPERATOR_PASSWORD_VERIFIED": "",
            "GODMODE_AGENT_ID": "",
        },
    )


class DerivationTests(unittest.TestCase):
    """`derive_writer` is a PURE function (fix round 1, F0/F1): every input
    is an explicit argument, never an environment variable, and it never
    prompts."""

    def test_default_is_agent(self) -> None:
        with _clean_writer_env():
            self.assertEqual(derive_writer(), "agent")

    def test_hook_process_identity_wins_over_every_other_claim(self) -> None:
        # Hook-agnostic in the other direction too: even a session claiming
        # operator/checker reads as `hook` when the process itself is one of
        # the two hook entrypoints.
        hook_path = str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
        with mock.patch.object(sys, "argv", [hook_path, "pre-action"]):
            self.assertEqual(
                derive_writer(role="checker", as_operator=True, operator_verified=True),
                "hook",
            )

    def test_gate_fast_entrypoint_is_also_a_hook(self) -> None:
        gate_path = str(PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py")
        with mock.patch.object(sys, "argv", [gate_path, "pre-action"]):
            self.assertEqual(derive_writer(), "hook")

    def test_checker_from_declared_role_argument(self) -> None:
        with _clean_writer_env():
            self.assertEqual(derive_writer(role="checker"), "checker")

    def test_as_operator_flag_alone_is_not_enough(self) -> None:
        # The flag is a claim, not a credential: with no `operator_verified`
        # supplied by the caller, this is `agent`, unconditionally.
        with _clean_writer_env():
            self.assertEqual(derive_writer(as_operator=True), "agent")

    def test_operator_requires_both_the_flag_and_the_callers_verification(self) -> None:
        with _clean_writer_env():
            self.assertEqual(derive_writer(as_operator=True, operator_verified=True), "operator")
            # Verification without the claim is not a write-as-operator either.
            self.assertEqual(derive_writer(as_operator=False, operator_verified=True), "agent")

    def test_trust_ordering_is_operator_gt_checker_gt_hook_gt_agent(self) -> None:
        self.assertGreater(TRUST_ORDER["operator"], TRUST_ORDER["checker"])
        self.assertGreater(TRUST_ORDER["checker"], TRUST_ORDER["hook"])
        self.assertGreater(TRUST_ORDER["hook"], TRUST_ORDER["agent"])


class EnvVarsNoLongerMintTrustTests(unittest.TestCase):
    """F1: the environment variables the review found minting trust for
    free are inert on `derive_writer` - it does not read any of them.
    `GODMODE_SESSION_ROLE` was fix round 1's one legitimate path back in,
    through the archive (`Chronicle._chronicled_session_role`) rather than
    this pure function; fix round 2 (B1) retired that env var entirely -
    `GODMODE_SESSION` (a session id, never a role claim, see
    `SessionRoleChronicleTests`) replaced it, and the OLD name is now
    checked here as fully inert, not merely inert on this function."""

    def test_as_operator_env_var_alone_does_not_mint_operator(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_AS_OPERATOR": "1"}):
            self.assertEqual(derive_writer(), "agent")

    def test_operator_password_verified_env_var_alone_does_not_mint_operator(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_OPERATOR_PASSWORD_VERIFIED": "1"}):
            self.assertEqual(derive_writer(as_operator=True), "agent")

    def test_session_role_env_var_alone_does_not_mint_checker_on_derive_writer(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_SESSION_ROLE": "checker"}):
            self.assertEqual(derive_writer(), "agent")

    def test_retired_session_role_env_var_mints_nothing_through_the_archive_either(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session_id = open_session(archive, "s", role="checker", operator_verified=True)
            with mock.patch.dict(os.environ, {"GODMODE_SESSION_ROLE": "checker"}):
                os.environ.pop("GODMODE_SESSION", None)
                record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "agent")
            # Naming the checker session correctly, through the CURRENT
            # env var, still works - the retirement removed one name, not
            # the mechanism.
            with mock.patch.dict(os.environ, {"GODMODE_SESSION": session_id}):
                record = archive.append("decision", "subject2", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "checker")


class InteractiveOperatorConfirmationTests(unittest.TestCase):
    """F0: the TTY y/N fallback for an operator who has not run `authorize
    setup` moved to the console (`_confirm_operator_interactively`), driven
    BEFORE `Chronicle.append` is ever entered - `derive_writer` itself
    never prompts, so nothing can block while holding the write lock."""

    def test_a_confirmed_yes_is_true(self) -> None:
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="y"):
            self.assertTrue(_confirm_operator_interactively())

    def test_a_declined_prompt_is_false(self) -> None:
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="n"):
            self.assertFalse(_confirm_operator_interactively())

    def test_non_interactive_never_prompts_and_is_false(self) -> None:
        with mock.patch("sys.stdin.isatty", return_value=False):
            self.assertFalse(_confirm_operator_interactively())


class CapabilityBrokerConfirmOperatorTests(unittest.TestCase):
    """F0: `--as-operator`'s password path reuses the existing broker
    (`CapabilityBroker.confirm_operator`) rather than a second check."""

    def test_confirm_operator_reuses_the_password_store(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            self.assertTrue(broker.confirm_operator(PASSWORD))
            self.assertFalse(broker.confirm_operator("the wrong password"))


class CLIAsOperatorFlagTests(unittest.TestCase):
    """F0: `--as-operator` actually reaches `_append` -> `Chronicle.append`
    through the console, verified against the password broker; the record
    itself now names its `writer` (F5), so this is checkable end to end."""

    def test_as_operator_with_the_right_password_lands_as_operator(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "op-write",
                "--value", "x", "--as-operator", "--password-stdin",
                stdin=f"{PASSWORD}\n",
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["record"]["writer"], "operator")
            self.assertEqual(payload["record"]["trust"], TRUST_ORDER["operator"])

    def test_as_operator_with_the_wrong_password_lands_as_agent(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "op-write",
                "--value", "x", "--as-operator", "--password-stdin",
                stdin="the wrong password\n",
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["record"]["writer"], "agent")

    def test_without_as_operator_the_flag_is_moot(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, payload = _run(
                project, "remember", "--kind", "decision", "--subject", "plain-write",
                "--value", "x",
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["record"]["writer"], "agent")


class SessionRoleChronicleTests(unittest.TestCase):
    """Fix round 2 (B1): `checker` is OPERATOR-GRANTED, never self-declared,
    and only ever inherited by the process that actually opened that exact
    session. Round 1's `GODMODE_SESSION_ROLE` re-read the archive's LATEST
    `session` record - attributable to *some* `session open --role
    checker` call, but not gated on anything, and not necessarily THIS
    process's own session. `GODMODE_SESSION` (the session id, not a role
    claim) plus the operator grant on the named record close both holes."""

    def test_no_session_env_var_mints_nothing(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            open_session(archive, "s", role="checker", operator_verified=True)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GODMODE_SESSION", None)
                record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "agent")

    def test_an_unverified_checker_session_mints_nothing_even_when_named(self) -> None:
        # The exact hole the round-1 rereview found load-bearing: a bare
        # `session open --role checker` with NO operator verification
        # behind it must not become `checker` even for the process that
        # opened it and names it correctly.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session_id = open_session(archive, "s", role="checker")
            with mock.patch.dict(os.environ, {"GODMODE_SESSION": session_id}):
                record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "agent")

    def test_a_verified_checker_session_named_by_its_own_id_mints_checker(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            session_id = open_session(archive, "s", role="checker", operator_verified=True)
            with mock.patch.dict(os.environ, {"GODMODE_SESSION": session_id}):
                record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "checker")

    def test_a_checker_session_named_by_a_different_session_id_grants_nothing(self) -> None:
        # A genuinely verified checker session exists in the archive, but
        # THIS process names a different (non-checker) session as its own -
        # merely existing in the same archive is not enough; the caller
        # must be the one that session actually belongs to.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            open_session(archive, "checker-session", role="checker", operator_verified=True)
            other_session_id = open_session(archive, "plain-session", role="agent")
            with mock.patch.dict(os.environ, {"GODMODE_SESSION": other_session_id}):
                record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "agent")

    def test_a_genuinely_granted_checker_session_named_by_another_agent_grants_nothing(self) -> None:
        # Fix round 3 (B1-residual): round 2 closed "names a record that
        # fails the grant checks" but left open "names a record that PASSES
        # them but belongs to someone else." Here the session really is
        # checker, really is role_granted_by=operator, really is
        # writer=operator - it is simply owned by a different agent_id, so
        # this caller must still get `agent`, never `checker`.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-owner"}, clear=False):
                session_id = open_session(archive, "s", role="checker", operator_verified=True)
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-thief", "GODMODE_SESSION": session_id}):
                record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "agent")

    def test_session_open_role_checker_through_the_cli_chronicles_and_mints_checker(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            with mock.patch.dict(os.environ, {}, clear=False):
                opened_code, opened = _run(
                    project, "session", "open", "--role", "checker", "--label", "s",
                    "--as-operator", "--password-stdin", stdin=f"{PASSWORD}\n")
                self.assertEqual(opened_code, 0, opened)
                self.assertEqual(opened["role"], "checker")
                code, payload = _run(
                    project, "remember", "--kind", "decision", "--subject", "s2", "--value", "x")
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["record"]["writer"], "checker")

    def test_session_open_role_checker_without_operator_verification_is_refused(self) -> None:
        # No broker configured, no TTY (unittest's stdin is not one) - the
        # interactive y/N fallback resolves False, so this must refuse with
        # a remedy rather than silently minting `checker` or falling back
        # to `agent` some other way.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {}, clear=False):
                code, text = _run_err(project, "session", "open", "--role", "checker", "--label", "s")
                self.assertNotEqual(code, 0, text)
                self.assertIn("operator", text.lower())
                # And the refusal actually refused: no session-scoped
                # checker trust exists for a later write to inherit.
                code2, payload = _run(
                    project, "remember", "--kind", "decision", "--subject", "s2", "--value", "x")
                self.assertEqual(code2, 0, payload)
                self.assertEqual(payload["record"]["writer"], "agent")

    def test_session_open_role_checker_with_the_wrong_password_is_refused(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)
            with mock.patch.dict(os.environ, {}, clear=False):
                code, text = _run_err(
                    project, "session", "open", "--role", "checker", "--label", "s",
                    "--as-operator", "--password-stdin", stdin="the wrong password\n")
                self.assertNotEqual(code, 0, text)


class FourProcessForeignCloseScenarioTests(unittest.TestCase):
    """Reproduces the round-1 rereview's B1 scenario end to end: a parent
    creates an obligation, a per-agent-id subagent is refused closing it
    directly, the SAME subagent cannot manufacture `checker` trust for
    itself with an unverified `session open --role checker`, and only a
    genuinely operator-verified checker session (a DIFFERENT process,
    naming its OWN session id) can close it on the parent's behalf.

    Fix round 3 (B1-residual, rereview round 2) adds a fifth process: one
    that never opened any session, but reads the archive's own history (an
    ordinary read-only verb) to learn process 2's genuinely operator-granted
    session id and exports THAT. The grant is real; it simply was not made
    to this caller, so it must mint nothing here either."""

    def test_foreign_close_refused_then_unverified_checker_refused_then_verified_checker_succeeds(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            CapabilityBroker(archive).configure(PASSWORD)

            # Process 1: the parent creates the obligation.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}, clear=False):
                code, payload = _run(
                    project, "remember", "--kind", "obligation", "--subject", "dep:owned-by-parent",
                    "--value", "owned by parent")
            self.assertEqual(code, 0, payload)

            # Process 2: a subagent's foreign close is refused outright.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-subagent"}, clear=False):
                code, text = _run_err(
                    project, "remember", "--kind", "obligation", "--subject", "dep:owned-by-parent",
                    "--value", "owned by parent", "--status", "done")
                self.assertNotEqual(code, 0, text)
                self.assertIn("different agent", text.lower())

                # Process 2 (same agent id): `session open --role checker`
                # with NO operator verification is refused with a remedy,
                # and buys the subagent nothing.
                opened_code, opened_text = _run_err(
                    project, "session", "open", "--role", "checker", "--label", "sneaky")
                self.assertNotEqual(opened_code, 0, opened_text)

                code, text = _run_err(
                    project, "remember", "--kind", "obligation", "--subject", "dep:owned-by-parent",
                    "--value", "owned by parent", "--status", "done")
                self.assertNotEqual(code, 0, text)

                # Now WITH a fake-verified password path, the same subagent
                # process legitimately becomes checker, and the close lands
                # - because the operator granted it, not because it asked.
                opened_code, opened = _run(
                    project, "session", "open", "--role", "checker", "--label", "verified",
                    "--as-operator", "--password-stdin", stdin=f"{PASSWORD}\n")
                self.assertEqual(opened_code, 0, opened)
                code, payload = _run(
                    project, "remember", "--kind", "obligation", "--subject", "dep:owned-by-parent",
                    "--value", "owned by parent", "--status", "done")
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["record"]["writer"], "checker")

            # Process 3: a DIFFERENT agent id, in a DIFFERENT process, with
            # no session of its own - inherits nothing from process 2's
            # checker session, verified or not.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-bystander"}, clear=False):
                os.environ.pop("GODMODE_SESSION", None)
                code, payload = _run(
                    project, "remember", "--kind", "obligation", "--subject", "dep:bystander-owned",
                    "--value", "bystander's own")
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["record"]["writer"], "agent")

            # Process 5 (fix round 3, B1-residual): a DIFFERENT agent again,
            # but this one does not merely stay silent about process 2's
            # session - it goes looking. `history` is an ordinary read-only
            # verb, and it hands back every session record's `record_hash`,
            # so the id process 2 was granted is not a secret. This process
            # never ran `session open` itself; it just exports the id it
            # read.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-thief"}, clear=False):
                code, history = _run(project, "history", "--kind", "session", "--json")
                self.assertEqual(code, 0, history)
                granted = next(
                    record for record in history["records"]
                    if record["data"].get("role") == "checker"
                    and record["data"].get("role_granted_by") == "operator"
                )
                os.environ["GODMODE_SESSION"] = f"S-{granted['record_hash'][:12]}"
                try:
                    # The grant is genuine and operator-issued - but it was
                    # issued to process 2, not to this one. Naming it buys
                    # nothing: the foreign close is refused exactly as
                    # process 2's very first, sessionless attempt was.
                    code, text = _run_err(
                        project, "remember", "--kind", "obligation", "--subject", "dep:owned-by-parent",
                        "--value", "owned by parent", "--status", "done")
                    self.assertNotEqual(code, 0, text)
                    self.assertIn("different agent", text.lower())

                    # And it is not merely refused as a close - the stolen
                    # id never reads as `checker` at all, even on a
                    # non-closing write this agent is otherwise free to
                    # make.
                    code, payload = _run(
                        project, "remember", "--kind", "obligation", "--subject", "dep:thief-owned",
                        "--value", "not the parent's")
                    self.assertEqual(code, 0, payload)
                    self.assertEqual(payload["record"]["writer"], "agent")
                finally:
                    os.environ.pop("GODMODE_SESSION", None)


class HookEntrypointAnchoredTests(unittest.TestCase):
    """F4: matching a hook script's bare basename anywhere on disk used to
    be enough to read as `hook` - a candidate entrypoint must now resolve
    inside the plugin's own installed `hooks/` directory."""

    def test_a_same_named_file_outside_the_plugins_hooks_directory_is_not_a_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _clean_writer_env():
            spoofed = str(Path(tmp) / "godmode_gate_fast.py")
            with mock.patch.object(sys, "argv", [spoofed, "pre-action"]):
                self.assertEqual(derive_writer(), "agent")

    def test_the_real_plugin_hooks_directory_still_reads_as_hook(self) -> None:
        hook_path = str(PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py")
        with mock.patch.object(sys, "argv", [hook_path, "pre-action"]):
            self.assertEqual(derive_writer(), "hook")


class RecordWriterFieldTests(unittest.TestCase):
    def test_append_stamps_writer_and_trust_on_every_record(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append("decision", "subject", {"value": "x"}, evidence=[])
            self.assertEqual(record["writer"], "agent")
            self.assertEqual(record["trust"], TRUST_ORDER["agent"])

    def test_operator_write_is_stamped_operator(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "decision", "subject", {"value": "x"}, evidence=[],
                as_operator=True, operator_verified=True,
            )
            self.assertEqual(record["writer"], "operator")
            self.assertEqual(record["trust"], TRUST_ORDER["operator"])


class SecretScanOnWriteTests(unittest.TestCase):
    def test_seeded_secret_refuses_the_write_and_names_the_field(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(GodmodeError) as ctx:
                archive.append(
                    "decision", "subject",
                    {"value": "AKIAABCDEFGHIJKLMNOP"}, evidence=[],
                )
            message = str(ctx.exception)
            self.assertIn("$.data.value", message)
            # The remedy is named, not merely the refusal.
            self.assertIn("redacted", message)
            self.assertEqual(len(archive.event_paths()), 0)


class SingleWriterPerSubjectTests(unittest.TestCase):
    def test_a_foreign_fingerprint_cannot_close_a_subject_the_creator_can(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                archive.append(
                    "obligation", "dep:ship-the-thing",
                    {"value": "ship the thing", "status": "open"}, evidence=[],
                )
            # A different actor (the coordinator/subagent case) may not close it.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-subagent"}):
                with self.assertRaises(ArchiveError) as ctx:
                    archive.append(
                        "obligation", "dep:ship-the-thing",
                        {"value": "ship the thing", "status": "closed"}, evidence=[],
                    )
                self.assertIn("dep:ship-the-thing", str(ctx.exception))
            # The creator can.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                record = archive.append(
                    "obligation", "dep:ship-the-thing",
                    {"value": "ship the thing", "status": "closed"}, evidence=[],
                )
                self.assertEqual(record["data"]["status"], "closed")

    def test_foreign_actor_may_still_request_or_claim_against_it(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                archive.append(
                    "request", "ask:review-this",
                    {"value": "review this", "status": "open"}, evidence=[],
                )
            # `request`/`claim` stay collaborative: another actor may close
            # (or otherwise append against) one it did not create.
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-subagent"}):
                record = archive.append(
                    "request", "ask:review-this",
                    {"value": "review this", "status": "closed"}, evidence=[],
                )
                self.assertEqual(record["data"]["status"], "closed")

    def test_hook_agnostic_the_check_is_fingerprint_not_role(self) -> None:
        # A hook process writing on behalf of the SAME underlying actor that
        # created the subject is not a "foreign" close - the comparison is
        # `agent_id`, never the `writer` role a process happens to carry.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                archive.append(
                    "obligation", "dep:same-actor",
                    {"value": "same actor", "status": "open"}, evidence=[],
                )
                hook_path = str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
                with mock.patch.object(sys, "argv", [hook_path, "pre-action"]):
                    record = archive.append(
                        "obligation", "dep:same-actor",
                        {"value": "same actor", "status": "closed"}, evidence=[],
                    )
                self.assertEqual(record["writer"], "hook")
                self.assertEqual(record["data"]["status"], "closed")


class SingleWriterTerminalSetTests(unittest.TestCase):
    """F2: the guard matches the FULL terminal set `status.remaining()`
    treats as closed (`CLOSING_STATUSES` - `closed`/`met`/`done`/`retired`),
    not only the literal "closed" string, and exempts a confirmed
    `operator`/declared `checker` from the refusal (NS-8k human override)."""

    def test_every_closing_status_is_refused_for_a_foreign_agent(self) -> None:
        for status in sorted(CLOSING_STATUSES):
            with self.subTest(status=status), isolated_project() as (_project, _state, _anchor, archive):
                archive.initialize()
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                    archive.append(
                        "obligation", "dep:many-doors", {"value": "v", "status": "open"}, evidence=[])
                with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-subagent"}):
                    with self.assertRaises(ArchiveError):
                        archive.append(
                            "obligation", "dep:many-doors", {"value": "v", "status": status}, evidence=[])

    def test_a_confirmed_operator_may_close_a_subject_it_did_not_create(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                archive.append(
                    "obligation", "dep:foreign", {"value": "v", "status": "open"}, evidence=[])
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-subagent"}):
                record = archive.append(
                    "obligation", "dep:foreign", {"value": "v", "status": "closed"}, evidence=[],
                    as_operator=True, operator_verified=True,
                )
            self.assertEqual(record["writer"], "operator")
            self.assertEqual(record["data"]["status"], "closed")

    def test_a_declared_checker_may_close_a_subject_it_did_not_create(self) -> None:
        # Fix round 2 (B1): this exercises only the DOWNSTREAM consequence
        # of already being `checker` - the `role="checker"` kwarg passed
        # straight to `Chronicle.append` here is the same low-level escape
        # hatch `as_operator=True, operator_verified=True` already is a few
        # tests up, never how a real caller becomes `checker` (that is
        # gated at `session open --role checker`, tested end to end in
        # `FourProcessForeignCloseScenarioTests` and
        # `SessionRoleChronicleTests`). The exemption itself is safe now
        # that `checker` cannot be self-declared.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-parent"}):
                archive.append(
                    "obligation", "dep:foreign-checker", {"value": "v", "status": "open"}, evidence=[])
            with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": "agent-subagent"}):
                record = archive.append(
                    "obligation", "dep:foreign-checker", {"value": "v", "status": "closed"}, evidence=[],
                    role="checker",
                )
            self.assertEqual(record["writer"], "checker")
            self.assertEqual(record["data"]["status"], "closed")


class StatusTrustOrderingTests(unittest.TestCase):
    def test_status_prefers_a_higher_trust_record_for_the_same_subject(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            subject = "dep:contested"
            archive.append(
                "obligation", subject, {"value": "do it", "status": "open"}, evidence=[],
            )
            # A persistent operator correction: closed for good.
            archive.append(
                "obligation", subject, {"value": "do it", "status": "closed"}, evidence=[],
                as_operator=True, operator_verified=True,
            )
            # A later, lower-trust agent record tries to reopen it - a
            # genuine contradiction (differing status), so the higher-trust
            # incumbent survives.
            archive.append(
                "obligation", subject, {"value": "do it", "status": "open"}, evidence=[],
            )
            report = godmode_status.remaining(archive, project)
            ids = [entry["id"] for entry in report["remaining"] if entry["source"] == "obligation"]
            self.assertNotIn(
                subject, ids,
                "a later, lower-trust agent record silently overrode an "
                "operator's persistent correction",
            )

    def test_equal_trust_still_prefers_the_most_recent_record(self) -> None:
        # The common case (every writer is `agent`) must behave exactly as
        # before: plain recency, never frozen by the first record written.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            subject = "dep:ordinary"
            archive.append(
                "obligation", subject, {"value": "do it", "status": "open"}, evidence=[],
            )
            archive.append(
                "obligation", subject, {"value": "do it", "status": "closed"}, evidence=[],
            )
            report = godmode_status.remaining(archive, project)
            ids = [entry["id"] for entry in report["remaining"] if entry["source"] == "obligation"]
            self.assertNotIn(subject, ids)

    def test_agent_updates_its_own_obligation_after_a_hook_record(self) -> None:
        # F3: trust only breaks a CONTRADICTION. A hook-written record
        # (trust 1) must not permanently shadow the owning agent's own
        # later, SAME-STATUS update (trust 0) - that update contradicts
        # nothing, so it wins by recency exactly as an all-agent history
        # would.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            subject = "dep:same-actor-refresh"
            hook_path = str(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
            with mock.patch.object(sys, "argv", [hook_path, "pre-action"]):
                archive.append(
                    "obligation", subject, {"value": "do it", "status": "open"}, evidence=[],
                )
            archive.append(
                "obligation", subject, {"value": "do it (updated)", "status": "open"}, evidence=[],
            )
            report = godmode_status.remaining(archive, project)
            entries = [entry for entry in report["remaining"]
                       if entry["source"] == "obligation" and entry["id"] == subject]
            self.assertEqual(len(entries), 1, entries)
            self.assertIn("updated", entries[0]["detail"])


class LegacyArchiveStillVerifiesTests(unittest.TestCase):
    def test_a_record_sealed_before_writer_existed_still_verifies(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            identifier = uuid.uuid4().hex
            legacy_record = {
                "schema_version": SCHEMA_VERSION,
                "project_key": anchor.project_key,
                "sequence": 1,
                "record_id": identifier,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "anchor_fingerprint": anchor_fingerprint(anchor),
                "agent": writer_fingerprint(),
                # No "writer"/"trust" keys at all - the exact pre-Task-5 shape.
                "kind": "decision",
                "subject": "legacy-subject",
                "data": {"value": "predates writer trust"},
                "evidence": [],
                "previous_hash": None,
            }
            legacy_record["record_hash"] = _record_hash(legacy_record)
            destination = archive.events / f"{1:012d}-{identifier}.godmode.json"
            _atomic_json(destination, legacy_record)
            archive._write_chain_anchor(1, legacy_record["record_hash"])
            archive._write_head(1, legacy_record["record_hash"])

            outcome = archive.verify()
            self.assertTrue(outcome["valid"], outcome.get("message"))
            self.assertTrue(outcome["ok"], outcome.get("message"))

            stored = archive.read_events()[0]
            self.assertNotIn("writer", stored)
            self.assertEqual(record_writer(stored), "agent")
            self.assertEqual(record_trust(stored), TRUST_ORDER["agent"])

            # A fresh append onto the legacy record still chains cleanly and
            # carries the new field going forward.
            appended = archive.append("decision", "new-subject", {"value": "after"}, evidence=[])
            self.assertEqual(appended["writer"], "agent")
            self.assertTrue(archive.verify()["valid"])


if __name__ == "__main__":
    unittest.main()
