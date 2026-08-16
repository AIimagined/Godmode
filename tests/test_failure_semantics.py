"""CX-5: failure semantics and truthful capability levels.

Binds `docs/superpowers/plans/2026-08-16-codex-compat.md`'s Task CX-5, its
Global Constraints, and Plan amendments 1-4 (amendment 3 carries the
five-level interception scale and receipt enrichment; amendment 2 carries
the mode table and capability digest; amendment 4 carries the doctrine
line). One class per contract point, named after the point it pins.

Doctrine, load-bearing for every test here as much as for the code:
**Silence from a failed verifier is never evidence of permission.**
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
GODMODE_CLI = PLUGIN_ROOT / "scripts" / "godmode.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, cmd_hooks  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError, AuthorizationError  # noqa: E402
from godmode_runtime.godmode_hostevent import parse_host_payload  # noqa: E402
from godmode_runtime.godmode_hookproof import (  # noqa: E402
    DEGRADE_REASON_MALFORMED_PAYLOAD,
    FAIL_OPEN_HOSTS,
    PROOF_MAX_TTL_SECONDS,
    RUNTIME_VERSION,
    SUBJECT_HOOK_DEGRADED,
    SUBJECT_PROOF,
    _auto_registration_grade,
    _expiry_out_of_bounds,
    _fully_enriched,
    _host_acknowledgement_from_registration,
    _pretool_timeout_ms,
    degraded_reason,
    interception_state,
    last_latency_check,
    record_hook_degradation,
    record_interception_proof,
    run_probe,
)
from godmode_runtime.godmode_invariants import (  # noqa: E402
    _PROOF_MAX_TTL_SECONDS as INVARIANTS_PROOF_MAX_TTL_SECONDS,
)
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    GATE_MODE_OBSERVE,
    POLICY_FILENAME,
    CapabilityBroker,
)
from test_godmode_runtime import isolated_project  # noqa: E402
from test_observe_mode import _decide, _enable_observe  # noqa: E402

PASSWORD = "correct-horse-local-only"  # godmode: allow-secret


def _git(*args: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=20, env=env,
    )


def _isolated_git_project():
    """A real, throwaway git repository with its own isolated godmode state."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            for args in (
                ["init", "-q"], ["config", "user.email", "t@t.invalid"],
                ["config", "user.name", "t"], ["checkout", "-q", "-b", "main"],
            ):
                result = _git(*args, cwd=project)
                assert result.returncode == 0, result.stderr
            (project / "README.md").write_text("x\n", encoding="utf-8")
            _git("add", "README.md", cwd=project)
            _git("commit", "-q", "-m", "initial", cwd=project)
            with mock.patch.dict(
                os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False,
            ):
                anchor = resolve_anchor(project)
                archive = Chronicle(anchor)
                archive.initialize()
                yield project, archive

    return _cm()


def token_body(token: str) -> dict:
    import base64
    encoded = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


# ---------------------------------------------------------------------------
# Contract point 1: the five-level interception scale.
# ---------------------------------------------------------------------------


class FiveLevelScaleTests(unittest.TestCase):
    def test_doctrine_line_is_present_verbatim(self) -> None:
        import godmode_runtime.godmode_hookproof as hookproof
        self.assertIn(
            "Silence from a failed verifier is never evidence of permission.",
            hookproof.__doc__,
        )

    def test_soft_registration_grades_soft(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertEqual(
                interception_state(archive, "gemini", registration="soft"), "SOFT")

    def test_partial_registration_with_no_proof_grades_partial(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertEqual(
                interception_state(archive, "cursor", registration="partial"), "PARTIAL")

    def test_unavailable_registration_with_no_proof_grades_unavailable(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            self.assertEqual(
                interception_state(archive, "unknown-host", registration="none"),
                "UNAVAILABLE",
            )

    def test_a_fresh_proof_expired_by_ttl_grades_degraded(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record_interception_proof(
                archive, host="claude", tool="Bash", request_id="n1", ttl_seconds=-100)
            self.assertEqual(
                interception_state(archive, "claude", registration="none"), "DEGRADED")
            self.assertEqual(degraded_reason(archive, "claude", registration="none"), "expired")

    def test_a_fresh_proof_with_a_version_mismatch_grades_degraded(self) -> None:
        # Fix round 1, C1(a): must carry ALL FIVE HARD-eligible fields (not
        # just `hook_version`/`expiry`) to even reach the drift comparison -
        # under the uniform enrichment rule, a record missing the other
        # three would grade PARTIAL, never reaching this check at all. An
        # in-bounds `expiry` (fix round 1, C1(b) - a far-future literal
        # would now be refused at append time; see
        # `ExpiryCeilingTests` below for that behavior specifically) and a
        # real, matching `trusted_hook_hash` isolate this test to the ONE
        # deliberate defect, `hook_version`.
        from datetime import datetime, timedelta, timezone as _tz
        from godmode_runtime.godmode_hookproof import _hash_file
        real_hash = _hash_file(PLUGIN_ROOT / "hooks" / "godmode_session_hook.py")
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append(
                "action", SUBJECT_PROOF,
                {
                    "host": "claude", "tool": "Bash", "request_id": "n1", "proof": True,
                    "hook_version": "0.0.1-not-the-running-version",
                    "trusted_hook_hash": real_hash,
                    "nonce_hash": hashlib.sha256(b"n1").hexdigest(),
                    "observed_decision": "deny",
                    "expiry": (datetime.now(_tz.utc) + timedelta(hours=1)).isoformat(),
                },
                evidence=[],
            )
            self.assertEqual(
                interception_state(archive, "claude", registration="none"), "DEGRADED")
            self.assertEqual(
                degraded_reason(archive, "claude", registration="none"), "version-drift")

    def test_a_fresh_proof_with_a_hash_mismatch_grades_degraded(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            # A real, different file's hash - never the real hook script's -
            # so `trusted_hook_hash` provably drifts from what a later read
            # of the actual hook file computes.
            decoy = Path(tempfile.mkdtemp()) / "decoy.py"
            decoy.write_text("not the hook\n", encoding="utf-8")
            record_interception_proof(
                archive, host="claude", tool="Bash", request_id="n1", hook_script=decoy)
            self.assertEqual(
                interception_state(archive, "claude", registration="none"), "DEGRADED")
            self.assertEqual(
                degraded_reason(archive, "claude", registration="none"), "hash-drift")

    def test_a_pre_cx5_minimal_record_caps_at_partial_never_hard(self) -> None:
        # Backward compatibility, stated honestly: the OLD CX-1 shape - no
        # expiry, no hash, nothing CX-5 can verify freshness/identity from -
        # still reads without error, and can never claim HARD again.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append(
                "action", SUBJECT_PROOF,
                {"host": "claude", "tool": "Bash", "request_id": "n1", "proof": True},
                evidence=[],
            )
            self.assertEqual(
                interception_state(archive, "claude", registration="none"), "PARTIAL")

    def test_the_reviewers_c1_forge_no_longer_grades_hard(self) -> None:
        # Fix round 1, C1(a) (Critical), red-first: the reviewer's exact
        # live repro - a hand-crafted record carrying `expiry` (and a fake
        # `host_acknowledgement: True`) while OMITTING `hook_version`/
        # `trusted_hook_hash`/`nonce_hash`/`observed_decision` entirely -
        # used to grade `HARD` forever, with no live hook subprocess
        # involved at all. Must now cap at `PARTIAL`, exactly like any
        # other incompletely-enriched record.
        from datetime import datetime, timedelta, timezone as _tz
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append(
                "action", SUBJECT_PROOF,
                {
                    "host": "claude", "tool": "Bash", "request_id": "forged",
                    "proof": True,
                    # In-bounds (fix round 1, C1(b) - a FAR-future expiry is
                    # its own, separately-tested refusal; ExpiryCeilingTests
                    # below) - isolates THIS test to C1(a)'s own defect,
                    # omitted fields, not a second one.
                    "expiry": (datetime.now(_tz.utc) + timedelta(hours=1)).isoformat(),
                    "host_acknowledgement": True,
                    # hook_version / trusted_hook_hash / nonce_hash /
                    # observed_decision all omitted on purpose - the exact
                    # reviewer repro.
                },
                evidence=[],
            )
            self.assertEqual(
                interception_state(archive, "claude", registration="none"), "PARTIAL")
            self.assertIsNone(degraded_reason(archive, "claude", registration="none"))

    def test_fully_enriched_helper_requires_every_field_individually(self) -> None:
        # Direct unit coverage of the gate itself: each of the five fields,
        # removed one at a time from an otherwise-complete dict, fails the
        # uniform-enrichment check on its own - no field is "load-bearing
        # enough to excuse the others," which was exactly the C1(a) gap.
        complete = {
            "expiry": "2099-01-01T00:00:00+00:00",
            "hook_version": "9.9.9",
            "trusted_hook_hash": "a" * 64,
            "nonce_hash": "b" * 64,
            "observed_decision": "deny",
        }
        self.assertTrue(_fully_enriched(dict(complete)))
        for field in complete:
            partial = dict(complete)
            del partial[field]
            self.assertFalse(_fully_enriched(partial), f"missing {field!r} should fail")
            partial_blank = dict(complete)
            partial_blank[field] = ""
            self.assertFalse(_fully_enriched(partial_blank), f"blank {field!r} should fail")


class ExpiryCeilingTests(unittest.TestCase):
    """Fix round 1, C1(b) (Critical): the absolute `PROOF_MAX_TTL_SECONDS`
    ceiling, at BOTH layers, red-first with the reviewer's exact year-9999
    repro at each.
    """

    def test_the_two_modules_own_copies_of_the_ceiling_stay_in_sync(self) -> None:
        # godmode_invariants.py deliberately keeps an independent copy
        # rather than importing godmode_hookproof.py (see both modules'
        # own comments on why) - pinned equal here so the two can never
        # silently drift apart.
        self.assertEqual(PROOF_MAX_TTL_SECONDS, INVARIANTS_PROOF_MAX_TTL_SECONDS)
        self.assertEqual(PROOF_MAX_TTL_SECONDS, 24 * 60 * 60)

    def test_append_layer_refuses_the_reviewers_year_9999_repro(self) -> None:
        # Red-first: `archive.append` itself must refuse a record whose
        # `expiry` is the reviewer's exact literal - the normal write path
        # can never even land this shape on disk.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "action", SUBJECT_PROOF,
                    {
                        "host": "claude", "tool": "Bash", "request_id": "n1",
                        "proof": True,
                        "expiry": "9999-12-31T23:59:59+00:00",
                    },
                    evidence=[],
                )

    def test_append_layer_accepts_an_in_bounds_expiry(self) -> None:
        # Negative control on the invariant itself: an honest, in-bounds
        # expiry must not be caught by the same check.
        from datetime import datetime, timedelta, timezone as _tz
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "action", SUBJECT_PROOF,
                {
                    "host": "claude", "tool": "Bash", "request_id": "n1",
                    "proof": True,
                    "expiry": (datetime.now(_tz.utc) + timedelta(hours=1)).isoformat(),
                },
                evidence=[],
            )
            self.assertTrue(record["data"]["proof"])

    def test_record_interception_proof_itself_never_trips_its_own_ceiling(self) -> None:
        # The shipped writer's own default TTL equals the ceiling exactly -
        # confirms the two are reconciled, not merely coincidentally close.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = record_interception_proof(
                archive, host="claude", tool="Bash", request_id="n1")
            self.assertTrue(record["data"]["proof"])

    def test_grading_layer_catches_a_hypothetical_record_that_slipped_in(self) -> None:
        # Red-first, the grading-layer half of the same order: a record
        # bearing the reviewer's exact out-of-bounds expiry that reached
        # disk SOME OTHER WAY (an older archive format, a hand-edited
        # file, a hypothetical future bug in the append-time check) must
        # still never grade above DEGRADED - written here via the
        # Chronicle's own low-level writer, bypassing `append()`'s
        # KIND_INVARIANTS call entirely, to simulate exactly that "already
        # on disk" scenario without asserting the append-time refusal a
        # second time.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            forged_data = {
                "host": "claude", "tool": "Bash", "request_id": "slipped-in",
                "proof": True,
                "hook_version": RUNTIME_VERSION,
                "trusted_hook_hash": "a" * 64,
                "nonce_hash": "b" * 64,
                "observed_decision": "deny",
                "expiry": "9999-12-31T23:59:59+00:00",
            }
            with archive.write_lock():
                count, tail_hash = archive._chain_tail()
                archive._write_record(
                    "action", SUBJECT_PROOF, forged_data, [],
                    sequence=count + 1, previous_hash=tail_hash,
                )
            self.assertEqual(
                interception_state(archive, "claude", registration="none"), "DEGRADED")
            self.assertEqual(
                degraded_reason(archive, "claude", registration="none"),
                "expiry-out-of-bounds",
            )

    def test_expiry_out_of_bounds_helper_directly(self) -> None:
        from datetime import datetime, timedelta, timezone as _tz
        recorded_at = datetime(2026, 1, 1, tzinfo=_tz.utc).isoformat()
        within = {
            "recorded_at": recorded_at,
            "data": {"expiry": (datetime(2026, 1, 1, tzinfo=_tz.utc)
                                + timedelta(hours=1)).isoformat()},
        }
        beyond = {
            "recorded_at": recorded_at,
            "data": {"expiry": "9999-12-31T23:59:59+00:00"},
        }
        self.assertFalse(_expiry_out_of_bounds(within))
        self.assertTrue(_expiry_out_of_bounds(beyond))


class KindInvariantsEnrichmentTests(unittest.TestCase):
    """KIND_INVARIANTS updated for enriched records, without weakening CX-1."""

    def test_a_minimal_pre_cx5_record_still_validates(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "action", SUBJECT_PROOF,
                {"host": "claude", "tool": "Bash", "request_id": "n1", "proof": True},
                evidence=[],
            )
            self.assertEqual(record["data"]["proof"], True)

    def test_the_original_cx1_required_fields_are_still_required(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "action", SUBJECT_PROOF,
                    {"host": "", "tool": "Bash", "request_id": "n1", "proof": True},
                    evidence=[],
                )

    def test_a_wrongly_typed_enrichment_field_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "action", SUBJECT_PROOF,
                    {"host": "claude", "tool": "Bash", "request_id": "n1", "proof": True,
                     "expiry": 12345},  # must be a string, not an int
                    evidence=[],
                )

    def test_a_wrongly_typed_host_acknowledgement_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(ArchiveError):
                archive.append(
                    "action", SUBJECT_PROOF,
                    {"host": "claude", "tool": "Bash", "request_id": "n1", "proof": True,
                     "host_acknowledgement": "yes"},  # must be bool/null
                    evidence=[],
                )


# ---------------------------------------------------------------------------
# Contract point 2: receipt enrichment.
# ---------------------------------------------------------------------------


class ReceiptEnrichmentTests(unittest.TestCase):
    def test_a_real_probe_writes_every_enriched_field(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch.dict(os.environ, {"GODMODE_HOST": "claude"}, clear=False):
                report = run_probe(project, archive, "claude")
            self.assertEqual(report["state"], "HARD")
            proof = archive.select(kind="action", subject=SUBJECT_PROOF, limit=1)[-1]
            data = proof["data"]
            for field in ("hook_version", "project_identity_hash", "nonce_hash",
                         "observed_decision", "expiry", "trusted_hook_hash"):
                self.assertIn(field, data)
            self.assertEqual(data["hook_version"], RUNTIME_VERSION)
            self.assertEqual(data["observed_decision"], "deny")


# ---------------------------------------------------------------------------
# Contract point 3: `hooks status` gains matched/invoked/honored/version/
# degraded_reason.
# ---------------------------------------------------------------------------


class HooksStatusHealthFieldsTests(unittest.TestCase):
    def test_status_reports_degraded_reason_when_degraded(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            record_interception_proof(
                archive, host="claude", tool="Bash", request_id="n1", ttl_seconds=-10)
            runtime = Runtime(anchor=anchor, archive=archive)
            import argparse
            args = argparse.Namespace(hooks_command="status", host="claude", git=False)
            result = cmd_hooks(args, runtime)
            self.assertEqual(result.payload["degraded_reason"], "expired")
            self.assertEqual(result.payload["honored"], True)
            self.assertEqual(result.payload["version"], RUNTIME_VERSION)
            self.assertTrue(result.payload["invoked"])

    def test_status_reports_unknown_honored_and_version_with_no_proof(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            runtime = Runtime(anchor=anchor, archive=archive)
            import argparse
            args = argparse.Namespace(hooks_command="status", host="some-unmatched-host",
                                      git=False)
            result = cmd_hooks(args, runtime)
            self.assertEqual(result.payload["honored"], "unknown")
            self.assertEqual(result.payload["version"], "unknown")
            self.assertFalse(result.payload["invoked"])
            self.assertIsNone(result.payload["degraded_reason"])


# ---------------------------------------------------------------------------
# Contract point 4: the mode table.
# ---------------------------------------------------------------------------


class ModeTableTests(unittest.TestCase):
    """One test per row, red-first framing kept in each docstring."""

    def test_row1_uninitialized_project_allows_ordinary_work_and_states_the_gap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            state = project / "state"
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": {"command": "git push --force origin main"},
                      "cwd": str(project)}
            done = subprocess.run(
                [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
                input=json.dumps(payload), capture_output=True, text=True,
                encoding="utf-8", timeout=60,
                env={**os.environ, "GODMODE_STATE_HOME": str(state)},
            )
            # Never a deny: an uninitialized project has no contract to
            # enforce, and ordinary work must proceed unimpeded.
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn('"deny"', done.stdout)
            self.assertNotIn('"permissionDecision"', done.stdout)

    def test_row2_degraded_hook_carries_a_visible_warning_in_the_brief_and_status(self) -> None:
        with isolated_project() as (project, state, anchor, archive):
            archive.initialize()
            record_interception_proof(archive, host="claude", tool="Bash", request_id="n1")
            # `_superseded_since` (hook-registered-but-now-untrusted/disabled)
            # is checked BEFORE session-anchor freshness, deliberately - the
            # session-start call below writes its own newer anchor, which
            # would otherwise mask an EXPIRY-based degradation back down to
            # merely PARTIAL (stale-by-session). A superseding record stays
            # DEGRADED regardless of session boundaries, which is the
            # faithful shape of this mode-table row: the hook was proven,
            # then something concrete said it broke.
            record_hook_degradation(archive, "claude", DEGRADE_REASON_MALFORMED_PAYLOAD)
            # A bare (non-Claude-shaped) session-start payload - the plain
            # `{"godmode": "context", "brief": ...}` shape, not Claude's
            # truncated `additionalContext` string, so the obligations dict
            # is directly inspectable here.
            done = subprocess.run(
                [sys.executable, str(HOOK), "session-start", "--project", str(project)],
                input=json.dumps({"cwd": str(project)}), capture_output=True, text=True,
                encoding="utf-8", timeout=60,
                env={**os.environ, "GODMODE_STATE_HOME": str(state), "GODMODE_HOST": "claude"},
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            brief = json.loads(done.stdout.strip())
            enforcement = brief["brief"]["obligations"]["enforcement"]
            self.assertEqual(enforcement["tool_call_interception"], "DEGRADED")
            self.assertIn("warning", enforcement)
            self.assertIn("DEGRADED", enforcement["warning"])
            runtime = Runtime(anchor=anchor, archive=archive)
            import argparse
            args = argparse.Namespace(hooks_command="status", host="claude", git=False)
            result = cmd_hooks(args, runtime)
            self.assertEqual(result.payload["verdict"], "DEGRADED")
            self.assertIsNotNone(result.payload["degraded_reason"])

    def test_row3_identity_mismatch_makes_no_continuity_claim_and_names_adopt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            env = {**os.environ, "GODMODE_STATE_HOME": str(state)}
            # Record something BEFORE the project becomes a git repository -
            # the archive lands at the salted, non-git identity.
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                anchor = resolve_anchor(project)
                pre_git_archive = Chronicle(anchor)
                pre_git_archive.initialize()
                pre_git_archive.append("checkpoint", "before git init", {}, evidence=[])
            for args in (["init", "-q"], ["config", "user.email", "t@t.invalid"],
                        ["config", "user.name", "t"]):
                assert _git(*args, cwd=project, env=env).returncode == 0
            (project / "f.txt").write_text("x\n", encoding="utf-8")
            _git("add", "f.txt", cwd=project, env=env)
            _git("commit", "-q", "-m", "c", cwd=project, env=env)

            # A bare (non-Claude-shaped) payload - no `hook_event_name` -
            # gets the plain `{"godmode": ...}` shape, not Claude's
            # additionalContext string, so the notice is directly
            # inspectable here.
            payload = {"cwd": str(project)}
            done = subprocess.run(
                [sys.executable, str(HOOK), "session-start", "--project", str(project)],
                input=json.dumps(payload), capture_output=True, text=True,
                encoding="utf-8", timeout=60, env=env,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            body = json.loads(done.stdout.strip())
            # No continuity claim: this must be the orphaned-archive notice,
            # never a populated continuity brief, and it must never carry
            # anything a test could mistake for a permission grant.
            self.assertEqual(body.get("godmode"), "orphaned-archive")
            self.assertIn("adopt", body.get("next_action", ""))
            self.assertNotIn("permissionDecision", json.dumps(body))
            self.assertNotIn('"allow": true', json.dumps(body).lower())

    def test_row4_malformed_payload_refuses_protected_and_records_degradation(self) -> None:
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            done = subprocess.run(
                [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
                input="{not valid json at all", capture_output=True, text=True,
                encoding="utf-8", timeout=60,
                env={**os.environ, "GODMODE_STATE_HOME": str(state), "GODMODE_HOST": "claude"},
            )
            # Protected classes refuse: exit 2 (deny/ask folded to deny for
            # a bare-operation shape with no operation text) or an explicit
            # deny in the JSON body - never silent, never allow.
            self.assertNotEqual(done.returncode, 0)
            degradations = archive.select(
                kind="action", subject=SUBJECT_HOOK_DEGRADED, limit=10)
            self.assertEqual(len(degradations), 1)
            self.assertEqual(
                degradations[0]["data"]["reason"], DEGRADE_REASON_MALFORMED_PAYLOAD)

    def test_row4_reads_are_unaffected_fast_path_still_silent(self) -> None:
        # Regression lock: a WELL-FORMED read-only tool call must still take
        # the zero-cost fast path (return 0, no archive touched at all) -
        # the CX-5 malformed-payload plumbing must not have slowed or
        # changed this untouched path.
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Read",
                      "tool_input": {"file_path": "x.txt"}, "cwd": str(project)}
            done = subprocess.run(
                [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
                input=json.dumps(payload), capture_output=True, text=True,
                encoding="utf-8", timeout=60,
                env={**os.environ, "GODMODE_STATE_HOME": str(state)},
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), "")
            self.assertEqual(
                archive.select(kind="action", subject=SUBJECT_HOOK_DEGRADED, limit=10), [])

    def test_row5_observe_mode_never_blocks_and_labels_would_have(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _enable_observe(project)
            result = _decide(project, "Bash", {"command": "git push --force origin main"})
            self.assertEqual(result["decision"], "allow")
            self.assertIsNotNone(result["system_message"])
            self.assertIn("OBSERVE MODE", result["system_message"])
            self.assertIn("would have been", result["system_message"].lower())


# ---------------------------------------------------------------------------
# Contract point 5: the capability digest.
# ---------------------------------------------------------------------------


class CapabilityDigestTests(unittest.TestCase):
    """Mechanism already exists in `CapabilityBroker`; pinned here, and
    extended with the one listed element that was missing (`branch`)."""

    def test_changed_operation_text_rejects(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            token = broker.issue("rm -rf build", PASSWORD, ttl_seconds=60)
            with self.assertRaises(AuthorizationError) as caught:
                broker.consume("rm -rf dist", token)
            self.assertIn("different operation", str(caught.exception))

    def test_changed_project_rejects(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            here = {"project_key": "aaa", "worktree": "w" * 64, "head": "h", "branch": "main"}
            token = broker.issue("rm -rf build", PASSWORD, ttl_seconds=60, context=here)
            elsewhere = dict(here, project_key="different-project")
            with self.assertRaises(AuthorizationError) as caught:
                broker.consume("rm -rf build", token, context=elsewhere)
            self.assertIn("another repository", str(caught.exception))

    def test_changed_branch_rejects(self) -> None:
        # CX-5 extension: two branches can share one HEAD commit, so `head`
        # alone cannot always tell a branch switch apart.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            here = {"project_key": "aaa", "worktree": "w" * 64, "head": "h", "branch": "main"}
            token = broker.issue("rm -rf build", PASSWORD, ttl_seconds=60, context=here)
            elsewhere = dict(here, branch="feature/x")
            with self.assertRaises(AuthorizationError) as caught:
                broker.consume("rm -rf build", token, context=elsewhere)
            self.assertIn("another branch", str(caught.exception))

    def test_changed_target_rejects_via_the_normalized_operation_digest(self) -> None:
        # "Target" is not a separate context field - a changed target
        # changes the normalized operation text, which changes the digest,
        # which is checked first and rejects on its own.
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            token = broker.issue("rm -rf target-a", PASSWORD, ttl_seconds=60)
            with self.assertRaises(AuthorizationError) as caught:
                broker.consume("rm -rf target-b", token)
            self.assertIn("different operation", str(caught.exception))

    def test_expiry_rejects(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            # Mint as though it were issued long ago (real `time.time()` at
            # consume time is unaffected), so the token's own `expires_at`
            # is already in the past without hand-forging the signature.
            with mock.patch("godmode_runtime.godmode_sentinel.time.time", return_value=1_000.0):
                token = broker.issue("rm -rf build", PASSWORD, ttl_seconds=10)
            with self.assertRaises(AuthorizationError) as caught:
                broker.consume("rm -rf build", token)
            self.assertIn("expired", str(caught.exception))

    def test_nonce_is_single_use(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            token = broker.issue("rm -rf build", PASSWORD, ttl_seconds=60)
            broker.consume("rm -rf build", token)
            with self.assertRaises(AuthorizationError) as caught:
                broker.consume("rm -rf build", token)
            self.assertIn("already been consumed", str(caught.exception))

    def test_capability_is_consumed_immediately_removing_it_from_the_staged_store(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage("rm -rf build", PASSWORD, ttl_seconds=60)
            data_before = json.loads(broker.path.read_text(encoding="utf-8"))
            self.assertEqual(len(data_before.get("staged", [])), 1)
            found = broker.consume_staged("rm -rf build")
            self.assertIsNotNone(found)
            data_after = json.loads(broker.path.read_text(encoding="utf-8"))
            self.assertEqual(data_after.get("staged", []), [])
            # Spent once: a second attempt at the SAME operation finds
            # nothing staged for it any more.
            self.assertIsNone(broker.consume_staged("rm -rf build"))

    def test_subagent_actor_never_widens_a_staged_capability_to_a_different_operation(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage("rm -rf build", PASSWORD, ttl_seconds=60)
            # A HostEvent carrying a subagent actor for a DIFFERENT operation
            # must not consume the capability staged for the first one -
            # matching stays exact-operation-digest only, regardless of who
            # (main agent or a named subagent) is asking.
            subagent_payload = {
                "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "rm -rf dist"}, "agentId": "subagent-7",
            }
            event = parse_host_payload(subagent_payload)
            self.assertEqual(event.actor, "subagent-7")
            found = broker.consume_staged(event.operation)
            self.assertIsNone(found)
            # The originally staged, exact operation is still there,
            # untouched by the subagent's unrelated attempt.
            found = broker.consume_staged("rm -rf build")
            self.assertIsNotNone(found)

    def test_the_hook_never_reads_actor_when_calling_the_broker(self) -> None:
        # Structural pin, per the order's own phrasing ("find how
        # subagent/session context reaches the broker and pin the
        # boundary"): the hook's broker call sites pass `operation` text
        # only - `event.actor` is captured on HostEvent (for provenance -
        # B5 delegation tracking) but never threaded into a capability
        # match, so a subagent identity can never widen what a staged
        # capability matches.
        source = HOOK.read_text(encoding="utf-8")
        self.assertIn("_broker(archive).consume_staged(operation)", source)
        self.assertIn('_broker(archive).consume(operation, str(submitted["capability"]))', source)
        # `event.actor` is captured (B5 delegation provenance) but never
        # threaded into either broker call - grep, not a mock, because a
        # future edit that DID start passing it would need to change this
        # literal source text to keep passing.
        self.assertNotIn(".actor", source)

    def test_no_broker_consume_call_site_anywhere_in_the_repo_threads_actor(self) -> None:
        # Fix round 1, I2 (Important): the prior version of this test only
        # grepped the session hook, but three OTHER real production call
        # sites of `CapabilityBroker.consume`/`.consume_staged` exist
        # (console's `authorize use`/`authorize stage --from-last-refusal`,
        # and the git-hook backstop) and were untouched by it - a future
        # change threading `event.actor`/`.actor` into any of THOSE would
        # not have been caught. This is a repo-wide structural pin: every
        # `.consume(`/`.consume_staged(` call site in the tracked source
        # tree (never `.git`/vendored output), and the line immediately
        # around it, is checked for the literal `.actor` never appearing on
        # the SAME call - the same "grep, not a mock" discipline as the
        # single-file version above, now covering the whole surface the
        # docstring/report actually claim it proves.
        import re

        call_pattern = re.compile(r"\.consume(?:_staged)?\(")
        sites: list[tuple[Path, int, str]] = []
        for path in sorted(PLUGIN_ROOT.rglob("*.py")):
            relative = path.relative_to(PLUGIN_ROOT)
            parts = relative.parts
            if any(part in (".git", "node_modules", "__pycache__") for part in parts):
                continue
            if parts[0] not in ("hooks", "scripts"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if call_pattern.search(line):
                    sites.append((relative, lineno, line))

        # A regression guard on the guard itself: if the known call sites
        # ever stop being found (a refactor renamed the method, moved the
        # file), this test must fail LOUD rather than silently pass with
        # zero sites checked.
        found_files = {p.as_posix() for p, _line, _text in sites}
        for expected in (
            "hooks/godmode_session_hook.py",
            "scripts/godmode_runtime/godmode_console.py",
            "scripts/godmode_runtime/godmode_githooks.py",
        ):
            self.assertIn(expected, found_files, f"expected a broker call site in {expected}")
        self.assertGreaterEqual(len(sites), 6, sites)

        for path, lineno, line in sites:
            self.assertNotIn(
                ".actor", line,
                f"{path}:{lineno} threads `.actor` into a broker call: {line!r}",
            )


# ---------------------------------------------------------------------------
# Contract point 6: sandbox approval metadata never satisfies godmode
# authorization, and vice versa. One test each direction.
# ---------------------------------------------------------------------------


class ApprovalContextIsolationTests(unittest.TestCase):
    def test_a_claimed_sandbox_approval_does_not_satisfy_godmode_authorization(self) -> None:
        # Direction 1: the host's own approval_context, however it claims
        # to read, never substitutes for a godmode capability.
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            payload = {
                "hook_event_name": "PreToolUse", "tool_name": "shell_command",
                "tool_input": {"command": "git push --force origin main"},
                "approvalContext": {"approved": True, "granted_by": "sandbox"},
                "cwd": str(project),
            }
            done = subprocess.run(
                [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
                input=json.dumps(payload), capture_output=True, text=True,
                encoding="utf-8", timeout=60,
                env={**os.environ, "GODMODE_STATE_HOME": str(state), "GODMODE_HOST": "codex"},
            )
            # A pretool decision's exit code is always 0 - the JSON body
            # carries the verdict (CX-2's dual-output contract) - so the
            # decision itself, not the exit code, is what this direction
            # must check.
            self.assertEqual(done.returncode, 0, done.stderr)
            body = json.loads(done.stdout.strip())
            self.assertEqual(
                body.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")

    def test_godmode_authorization_never_suppresses_the_hosts_own_approval_ask(self) -> None:
        # Direction 2: a godmode-authorized allow (a consumed capability)
        # never adds anything to the response that could tell a host to
        # skip its own separate approval flow - the response for an allowed
        # call stays exactly the ordinary silent/systemMessage-only shape.
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            broker.configure(PASSWORD)
            broker.stage("rm -rf build", PASSWORD, ttl_seconds=60)
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_input": {"command": "rm -rf build"}, "cwd": str(project)}
            done = subprocess.run(
                [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
                input=json.dumps(payload), capture_output=True, text=True,
                encoding="utf-8", timeout=60,
                env={**os.environ, "GODMODE_STATE_HOME": str(state)},
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            body = done.stdout.strip()
            lowered = body.lower()
            self.assertNotIn("approval", lowered)
            self.assertNotIn("sandbox", lowered)


# ---------------------------------------------------------------------------
# Contract point 7: per-host latency self-check.
# ---------------------------------------------------------------------------


class LatencySelfCheckTests(unittest.TestCase):
    def test_fail_open_hosts_are_grok_gemini_cursor(self) -> None:
        self.assertEqual(FAIL_OPEN_HOSTS, frozenset({"grok", "gemini", "cursor"}))

    def test_pretool_timeout_ms_reads_the_real_shipped_manifests(self) -> None:
        self.assertEqual(_pretool_timeout_ms("claude"), 3000)
        self.assertEqual(_pretool_timeout_ms("codex"), 3000)
        self.assertEqual(_pretool_timeout_ms("grok"), 8000)
        self.assertEqual(_pretool_timeout_ms("gemini"), 3000)
        self.assertEqual(_pretool_timeout_ms("cursor"), 3000)
        self.assertIsNone(_pretool_timeout_ms("no-such-host"))

    def test_run_probe_measures_and_persists_latency(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            report = run_probe(project, archive, "claude")
            self.assertEqual(report["state"], "HARD")
            self.assertIsInstance(report["latency_ms"], float)
            self.assertEqual(report["timeout_budget_ms"], 3000)
            record = last_latency_check(archive, "claude")
            self.assertIsNotNone(record)
            self.assertEqual(record["data"]["timeout_budget_ms"], 3000)

    def test_a_tiny_timeout_budget_trips_the_latency_warning(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch(
                "godmode_runtime.godmode_hookproof._pretool_timeout_ms", return_value=1,
            ):
                report = run_probe(project, archive, "claude")
            self.assertTrue(report["latency_warning"])
            record = last_latency_check(archive, "claude")
            self.assertTrue(record["data"]["warning"])

    def test_hooks_status_surfaces_fail_open_host_flag(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            runtime = Runtime(anchor=anchor, archive=archive)
            import argparse
            args = argparse.Namespace(hooks_command="status", host="grok", git=False)
            result = cmd_hooks(args, runtime)
            self.assertTrue(result.payload["fail_open_host"])

    def test_a_probe_timeout_is_distinguished_from_other_subprocess_failures(self) -> None:
        import subprocess as subprocess_module
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            with mock.patch(
                "godmode_runtime.godmode_hookproof.subprocess.run",
                side_effect=subprocess_module.TimeoutExpired(cmd="x", timeout=20),
            ):
                report = run_probe(project, archive, "claude")
            self.assertNotEqual(report["state"], "HARD")
            failures = archive.select(kind="action", subject="probe-failed", limit=5)
            self.assertEqual(failures[-1]["data"]["reason"], "timeout")

    def test_an_unexpected_exit_code_is_its_own_failure_reason(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            weird = subprocess.CompletedProcess(args=[], returncode=1, stdout="{}", stderr="")
            with mock.patch(
                "godmode_runtime.godmode_hookproof.subprocess.run", return_value=weird,
            ):
                report = run_probe(project, archive, "claude")
            self.assertNotEqual(report["state"], "HARD")
            failures = archive.select(kind="action", subject="probe-failed", limit=5)
            self.assertEqual(failures[-1]["data"]["reason"], "unexpected-exit")


if __name__ == "__main__":
    unittest.main()
