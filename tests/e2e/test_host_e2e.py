"""CX-6: the end-to-end scenario suite.

Runs on every CI/local run WITHOUT any live host binary present - the hook
subprocess itself IS the system under test (`tests/e2e/harness.py`'s module
docstring). Every scenario here is asserted on the FOUR-PLANE checklist:
hook exit code, decision envelope, simulated host interpretation, and a real
filesystem/git side effect - never on a single layer read in isolation.

Live-host verification (a REAL Codex/Grok binary calling this plugin) is a
separate, explicitly operator-run layer: `tests/e2e/test_codex_e2e.py`,
gated by `GODMODE_E2E_CODEX=1`/`GODMODE_E2E_GROK=1`, skipped cleanly
otherwise.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import harness as h  # noqa: E402

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_githooks import (  # noqa: E402
    POLICY_KEY, git_hooks_install)
from godmode_runtime.godmode_hookproof import (  # noqa: E402
    SUBJECT_PROOF, SUBJECT_UNINSTALLED, degraded_reason, interception_state,
    record_interception_proof, run_probe)
from godmode_runtime.godmode_plan import CONTRACT_FIELDS, approve, specify, start  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker, POLICY_FILENAME)

PASSWORD = "correct horse battery staple e2e"


def _declare_git_backstop(project: Path) -> None:
    (project / POLICY_FILENAME).write_text(
        json.dumps({POLICY_KEY: True}), encoding="utf-8")


def _approved_fence(archive: Chronicle, editable: str) -> None:
    specify(archive, "S-E2E", "e2e-scoped change", {
        "objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n"})
    contract = {field: "x" for field in CONTRACT_FIELDS if field != "editable"}
    contract["accept"] = "cmd:x"
    contract["editable"] = editable
    start(archive, "S-E2E", "e2e-scoped change", contract)
    approve(archive, "S-E2E")


# ---------------------------------------------------------------------------
# 1. Read-only fast path.
# ---------------------------------------------------------------------------


class ReadOnlyFastPathTests(unittest.TestCase):
    """The fast gate (`hooks/godmode_gate_fast.py`) never spawns the full
    hook for a vetted read-only head - proven here by TIMING, since the
    fast path and the escalate-then-allow path both end up printing nothing
    and exiting 0 from the outside; only latency tells them apart, which is
    also exactly what the plan's own perf contract wants measured.
    """

    def test_a_read_only_command_takes_the_fast_path_and_records_latency(self) -> None:
        with h.e2e_repo() as repo:
            payload = h.claude_shell("git status", str(repo.project))
            result = h.run_hook(payload, repo, host="claude", fast=True)
            # M1 (review, Minor): `git status` genuinely has no filesystem/git
            # footprint to check either way - a read never changes state, so
            # there is nothing independent for plane 4 to inspect. Unlike
            # every other scenario in this file, `verify_side_effect` below
            # cannot check real, external state; it re-reads plane 3's own
            # `decision` value, which makes it structurally unable to
            # disagree with plane 3 - a tautology, not independent evidence.
            # This is the ONE scenario where the harness's own "positive
            # evidence, not silence" promise does not apply, and it is
            # documented here rather than left to look like every other
            # scenario's real check.
            report = h.four_plane_check(
                "read-only-fast-path", "claude", result, expect="allow",
                on_allow=lambda: None,
                verify_side_effect=lambda decision: decision == "allow",
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.envelope, {})
            self.assertLess(report.latency_seconds, 5.0, "one warm subprocess call")

    def test_the_fast_path_is_materially_faster_than_a_full_escalation(self) -> None:
        with h.e2e_repo() as repo:
            fast_samples = h.timed(
                lambda: h.run_hook(h.claude_shell("git status", str(repo.project)),
                                   repo, host="claude", fast=True),
                repeats=5,
            )
            escalate_samples = h.timed(
                lambda: h.run_hook(h.claude_shell("git push --force origin main", str(repo.project)),
                                   repo, host="claude", fast=True),
                repeats=5,
            )
            self.assertLess(h.median(fast_samples), h.median(escalate_samples),
                            "a table lookup must beat a full classify+archive round trip")


# ---------------------------------------------------------------------------
# 2. Normal edit allowed.
# ---------------------------------------------------------------------------


class NormalEditAllowedTests(unittest.TestCase):
    def test_an_ordinary_in_tree_edit_is_allowed_and_the_file_actually_changes(self) -> None:
        with h.e2e_repo() as repo:
            target = repo.project / "notes.md"
            target.write_text("before\n", encoding="utf-8")
            payload = h.claude_edit(str(target), str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                target.write_text("after\n", encoding="utf-8")

            def _verify(decision: str) -> bool:
                if decision == "allow":
                    return target.read_text(encoding="utf-8") == "after\n"
                return target.read_text(encoding="utf-8") == "before\n"

            report = h.four_plane_check("normal-edit", "claude", result, expect="allow",
                                        on_allow=_apply, verify_side_effect=_verify)
            self.assertEqual(report.host_decision, "allow")
            self.assertTrue(report.side_effect_verified)


# ---------------------------------------------------------------------------
# 3. Out-of-scope edit denied (the plan-declared fence).
# ---------------------------------------------------------------------------


class OutOfScopeEditDeniedTests(unittest.TestCase):
    def test_an_edit_outside_the_declared_fence_never_lands(self) -> None:
        with h.e2e_repo() as repo:
            _approved_fence(repo.archive, "src/auth/**")
            outside = repo.project / "src" / "billing" / "invoice.py"
            outside.parent.mkdir(parents=True, exist_ok=True)
            outside.write_text("baseline\n", encoding="utf-8")
            payload = h.claude_edit(str(outside), str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                outside.write_text("mutated\n", encoding="utf-8")

            def _verify(decision: str) -> bool:
                expected = "mutated\n" if decision == "allow" else "baseline\n"
                return outside.read_text(encoding="utf-8") == expected

            report = h.four_plane_check("out-of-scope-edit", "claude", result, expect="blocked",
                                        on_allow=_apply, verify_side_effect=_verify)
            self.assertNotEqual(report.host_decision, "allow")
            self.assertTrue(report.side_effect_verified)

    def test_an_edit_inside_the_declared_fence_still_proceeds(self) -> None:
        with h.e2e_repo() as repo:
            _approved_fence(repo.archive, "src/auth/**")
            inside = repo.project / "src" / "auth" / "session.py"
            inside.parent.mkdir(parents=True, exist_ok=True)
            inside.write_text("baseline\n", encoding="utf-8")
            payload = h.claude_edit(str(inside), str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                inside.write_text("mutated\n", encoding="utf-8")

            def _verify(decision: str) -> bool:
                expected = "mutated\n" if decision == "allow" else "baseline\n"
                return inside.read_text(encoding="utf-8") == expected

            report = h.four_plane_check("in-scope-edit", "claude", result, expect="allow",
                                        on_allow=_apply, verify_side_effect=_verify)
            self.assertEqual(report.host_decision, "allow")
            self.assertTrue(report.side_effect_verified)


# ---------------------------------------------------------------------------
# 4. Protected-command denial table: force-push, hard reset, destructive fs,
#    recursive external delete, database drop. One reusable shape, one real
#    fixture per row - Plan amendment 2's "database drop, recursive external
#    delete" rows folded in alongside the plan's own named scenarios.
# ---------------------------------------------------------------------------


class ProtectedCommandDenialTests(unittest.TestCase):
    def test_force_push_is_denied_and_the_remote_ref_never_moves(self) -> None:
        with h.e2e_repo(with_remote=True) as repo:
            baseline = h.remote_ref(repo.remote)
            h.commit_file(repo.project, "file.txt", "local-only-change\n", env=repo.env())
            payload = h.claude_shell("git push --force origin main", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                pushed = h.git("push", "--force", "origin", "main",
                               cwd=repo.project, env=repo.env())
                self.assertEqual(pushed.returncode, 0, pushed.stderr)

            def _verify(decision: str) -> bool:
                current = h.remote_ref(repo.remote)
                if decision == "allow":
                    return current == h.head_of(repo.project)
                return current == baseline

            h.four_plane_check("force-push", "claude", result, expect="blocked",
                               on_allow=_apply, verify_side_effect=_verify)

    def test_hard_reset_is_denied_and_head_never_moves(self) -> None:
        with h.e2e_repo() as repo:
            baseline = h.head_of(repo.project)
            h.commit_file(repo.project, "file.txt", "second\n", env=repo.env())
            payload = h.claude_shell("git reset --hard " + baseline, str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                reset = h.git("reset", "--hard", baseline, cwd=repo.project, env=repo.env())
                self.assertEqual(reset.returncode, 0, reset.stderr)

            def _verify(decision: str) -> bool:
                current = h.head_of(repo.project)
                return current == baseline if decision == "allow" else current != baseline

            h.four_plane_check("hard-reset", "claude", result, expect="blocked",
                               on_allow=_apply, verify_side_effect=_verify)

    def test_a_recursive_delete_is_denied_and_the_directory_still_exists(self) -> None:
        with h.e2e_repo() as repo:
            build = repo.project / "build"
            build.mkdir()
            (build / "artifact.bin").write_text("keep-me", encoding="utf-8")
            payload = h.claude_shell("rm -rf build", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                shutil.rmtree(build)

            def _verify(decision: str) -> bool:
                if decision == "allow":
                    return not build.exists()
                return build.is_dir() and (build / "artifact.bin").read_text(
                    encoding="utf-8") == "keep-me"

            report = h.four_plane_check(
                "destructive-fs-rm-rf", "claude", result, expect="blocked",
                on_allow=_apply, verify_side_effect=_verify)
            self.assertNotEqual(report.host_decision, "allow")
            self.assertTrue(report.side_effect_verified)

    def test_a_recursive_delete_outside_the_tree_is_denied_and_the_target_survives(self) -> None:
        with h.e2e_repo() as repo:
            external = repo.project.parent / "sibling-project"
            external.mkdir()
            (external / "keep.txt").write_text("do-not-touch", encoding="utf-8")
            payload = h.claude_shell(f"rm -rf {external}", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _apply() -> None:
                shutil.rmtree(external)

            def _verify(decision: str) -> bool:
                if decision == "allow":
                    return not external.exists()
                return external.is_dir() and (external / "keep.txt").read_text(
                    encoding="utf-8") == "do-not-touch"

            report = h.four_plane_check(
                "recursive-external-delete", "claude", result, expect="blocked",
                on_allow=_apply, verify_side_effect=_verify)
            self.assertNotEqual(report.host_decision, "allow")
            self.assertTrue(report.side_effect_verified)

    def test_a_database_drop_is_denied_and_the_table_still_has_its_rows(self) -> None:
        with h.e2e_repo() as repo:
            db_path = repo.project / "app.db"
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, sku TEXT)")
            connection.execute("INSERT INTO orders (sku) VALUES ('widget-1')")
            connection.commit()
            connection.close()
            payload = h.claude_shell("DROP TABLE orders", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")

            def _drop() -> None:
                conn = sqlite3.connect(db_path)
                conn.execute("DROP TABLE orders")
                conn.commit()
                conn.close()

            def _verify(decision: str) -> bool:
                conn = sqlite3.connect(db_path)
                try:
                    if decision == "allow":
                        tables = conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
                        ).fetchall()
                        return tables == []
                    rows = conn.execute("SELECT sku FROM orders").fetchall()
                    return rows == [("widget-1",)]
                finally:
                    conn.close()

            h.four_plane_check("database-drop", "claude", result, expect="blocked",
                               on_allow=_drop, verify_side_effect=_verify)


# ---------------------------------------------------------------------------
# 5. Force-push, verified across every documented host dialect, with the
#    git-level backstop (CX-4) installed too - genuine defense-in-depth,
#    not only the pre-tool boundary's own opinion.
# ---------------------------------------------------------------------------


class ForcePushFourPlaneAllHostsTests(unittest.TestCase):
    """The scenario named explicitly in the report: force-push, all four
    planes, every documented host dialect that can carry a shell command
    (Claude/Codex/Grok/Cursor/Gemini), PLUS an independent real `git push`
    attempt against the installed CX-4 backstop, which must refuse it
    regardless of what any pre-tool boundary said."""

    def _diverge(self, repo: h.E2ERepo):
        commit_b = h.commit_file(repo.project, "file.txt", "b", env=repo.env())
        pushed = h.git("push", "-q", "origin", "main", cwd=repo.project, env=repo.env())
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        h.git("reset", "-q", "--hard", h.head_of(repo.project, "HEAD~1"),
              cwd=repo.project, env=repo.env())
        commit_c = h.commit_file(repo.project, "file.txt", "c", env=repo.env())
        return commit_b, commit_c

    def test_force_push_denied_on_every_host_dialect_four_planes_each(self) -> None:
        reports = {}
        for host, builder in h.HOST_SHELL_BUILDERS.items():
            with h.e2e_repo(with_remote=True) as repo:
                commit_b, _commit_c = self._diverge(repo)
                payload = builder("git push --force origin main", str(repo.project))
                result = h.run_hook(payload, repo, host=host)

                def _apply(repo=repo) -> None:
                    pushed = h.git("push", "--force", "origin", "main",
                                   cwd=repo.project, env=repo.env())
                    self.assertEqual(pushed.returncode, 0, pushed.stderr)

                def _verify(decision: str, repo=repo, commit_b=commit_b) -> bool:
                    current = h.remote_ref(repo.remote)
                    if decision == "allow":
                        return current == h.head_of(repo.project)
                    return current == commit_b

                report = h.four_plane_check(
                    "force-push-all-hosts", host, result, expect="blocked",
                    on_allow=_apply, verify_side_effect=_verify)
                reports[host] = report
        self.assertEqual(set(reports), set(h.HOST_SHELL_BUILDERS))
        for host, report in reports.items():
            with self.subTest(host=host):
                # R5 (force-push) is refused outright by `_decision_for` -
                # never `ask`, on any host, so every dialect's own
                # interpretation must read `deny` here, not just "blocked".
                self.assertEqual(report.host_decision, "deny")

    def test_force_push_denied_and_the_independent_git_backstop_also_refuses_it(self) -> None:
        """Defense in depth: even setting the pre-tool boundary's verdict
        aside, a REAL `git push --force` against the CX-4-installed pre-push
        hook must fail on its own, independently."""
        with h.e2e_repo(with_remote=True) as repo:
            # Diverge FIRST, on ordinary pushes, before the backstop is
            # installed - the installed pre-push hook protects EVERY push
            # under a declared policy (not only force ones), so installing
            # it earlier would block the ordinary pushes this fixture needs
            # to set up the divergence itself.
            commit_b, _commit_c = self._diverge(repo)
            _declare_git_backstop(repo.project)
            report = git_hooks_install(repo.archive, repo.project)
            self.assertIn("pre-push", report["installed"])

            payload = h.claude_shell("git push --force origin main", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")
            host_decision = h.interpret("claude", result)
            self.assertEqual(host_decision, "deny")

            # Plane 4, independently: attempt the RAW git push regardless of
            # the pre-tool verdict - the git-level backstop must refuse it
            # on its own, at git's own chokepoint.
            remote_before = h.remote_ref(repo.remote)
            real_push = h.git("push", "--force", "origin", "main",
                              cwd=repo.project, env=repo.env())
            self.assertNotEqual(real_push.returncode, 0, real_push.stdout + real_push.stderr)
            remote_after = h.remote_ref(repo.remote)
            self.assertEqual(remote_before, remote_after)
            self.assertEqual(remote_after, commit_b)


# ---------------------------------------------------------------------------
# 6. Orchestrated (functions.exec-wrapped) Codex call reaches the gate once
#    and denies.
# ---------------------------------------------------------------------------


class OrchestratedCallTests(unittest.TestCase):
    def test_a_functions_exec_wrapped_force_push_reaches_the_gate_once_and_denies(self) -> None:
        with h.e2e_repo(with_remote=True) as repo:
            baseline = h.remote_ref(repo.remote)
            payload = h.codex_orchestrated_shell(
                "git push --force origin main", str(repo.project), request_id="orc-1")
            result = h.run_hook(payload, repo, host="codex")

            def _apply() -> None:
                pushed = h.git("push", "--force", "origin", "main",
                               cwd=repo.project, env=repo.env())
                self.assertEqual(pushed.returncode, 0, pushed.stderr)

            def _verify(decision: str) -> bool:
                current = h.remote_ref(repo.remote)
                return current == baseline if decision != "allow" else current != baseline

            report = h.four_plane_check(
                "orchestrated-force-push", "codex", result, expect="blocked",
                on_allow=_apply, verify_side_effect=_verify)
            # "Reaches the gate exactly once": one subprocess call, one
            # decision - never zero (unwrap must succeed) and never twice
            # (nothing anywhere re-dispatches the unwrapped call).
            self.assertIsNotNone(report)
            events = h.reopen_archive(repo).select(kind="refusal", limit=10)
            probe_records = [e for e in events if e["subject"] not in ("unrecognized-tool",)]
            self.assertEqual(len(probe_records), 1,
                             "the orchestrated call must classify exactly once")


# ---------------------------------------------------------------------------
# 7. Staged capability: consumed exactly once, expired rejected, replayed
#    rejected.
# ---------------------------------------------------------------------------


class StagedCapabilityScenarioTests(unittest.TestCase):
    def _broker(self, repo: h.E2ERepo) -> CapabilityBroker:
        broker = CapabilityBroker(repo.archive)
        broker.configure(PASSWORD)
        return broker

    def test_a_staged_capability_is_consumed_exactly_once(self) -> None:
        with h.e2e_repo() as repo:
            broker = self._broker(repo)
            operation = "git push --force origin main"
            broker.stage(operation, PASSWORD)
            payload = h.claude_shell(operation, str(repo.project))

            first = h.run_hook(payload, repo, host="claude")
            self.assertEqual(h.interpret("claude", first), "allow",
                             "the staged capability must authorize the first attempt")

            # No re-stage: the second identical call must find nothing
            # staged and fall back to the ordinary deny path.
            second = h.run_hook(payload, repo, host="claude")
            self.assertEqual(h.interpret("claude", second), "deny",
                             "a spent staged capability must never authorize a second call")

    def test_an_expired_staged_capability_is_rejected(self) -> None:
        with h.e2e_repo() as repo:
            broker = self._broker(repo)
            operation = "git push --force origin main"
            broker.stage(operation, PASSWORD, ttl_seconds=60)
            # Directly age the staged entry past its own expiry - the
            # public `stage()` API refuses a TTL under 10s, so an
            # already-expired capability cannot be minted through it; this
            # is the harness reaching into the SAME on-disk store
            # `consume_staged` itself reads, not a second, parallel model
            # of it.
            data = json.loads(broker.path.read_text(encoding="utf-8"))
            for entry in data["staged"]:
                entry["expires_at"] = int(time.time()) - 3600
            broker.path.write_text(json.dumps(data), encoding="utf-8")

            payload = h.claude_shell(operation, str(repo.project))
            result = h.run_hook(payload, repo, host="claude")
            self.assertEqual(h.interpret("claude", result), "deny",
                             "an expired staged capability must never authorize the call")

    def test_a_consumed_token_replayed_directly_against_the_broker_is_rejected(self) -> None:
        """Replay defense at the layer that actually enforces it
        (`CapabilityBroker.consume`'s nonce ledger) - a real host tool call
        carries no capability field to replay (documented in
        `hooks/godmode_session_hook.py`'s own refusal text), so this
        exercises the SAME production method the bare/host-neutral payload
        path calls, directly, rather than pretending a field a host would
        never send is part of any dialect's contract.
        """
        with h.e2e_repo() as repo:
            broker = self._broker(repo)
            operation = "git reset --hard HEAD~5"
            token = broker.issue(operation, PASSWORD)
            first = broker.consume(operation, token)
            self.assertTrue(first["protected"])
            from godmode_runtime.godmode_errors import GodmodeError
            with self.assertRaises(GodmodeError):
                broker.consume(operation, token)


# ---------------------------------------------------------------------------
# 8. Disabled hook => interception_state not HARD.
# ---------------------------------------------------------------------------


class DisabledHookScenarioTests(unittest.TestCase):
    def test_a_hook_with_no_proof_at_all_never_grades_hard(self) -> None:
        with h.e2e_repo() as repo:
            self.assertNotEqual(interception_state(repo.archive, "claude"), "HARD")

    def test_a_proven_hook_later_marked_uninstalled_downgrades_off_hard(self) -> None:
        with h.e2e_repo() as repo:
            record_interception_proof(repo.archive, host="claude", tool="Bash",
                                      request_id="n1")
            repo.archive.append("action", SUBJECT_UNINSTALLED, {"host": "claude"}, evidence=[])
            self.assertNotEqual(
                interception_state(repo.archive, "claude", registration="none"), "HARD")
            self.assertEqual(
                interception_state(repo.archive, "claude", registration="none"), "DEGRADED")

        # Real side effect layer: a protected op still fails closed while
        # disabled - never a silent allow because the hook is "off."
        with h.e2e_repo() as repo:
            record_interception_proof(repo.archive, host="claude", tool="Bash",
                                      request_id="n2")
            repo.archive.append("action", SUBJECT_UNINSTALLED, {"host": "claude"}, evidence=[])
            payload = h.claude_shell("git push --force origin main", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")
            self.assertEqual(h.interpret("claude", result), "deny")


# ---------------------------------------------------------------------------
# 9. Tampered hook file => godmode-modified + DEGRADED path.
# ---------------------------------------------------------------------------


class TamperedHookFileScenarioTests(unittest.TestCase):
    """Exercises the REAL `record_interception_proof`/`interception_state`
    hash-drift mechanism against a PRIVATE COPY of the shipped hook script,
    never the real checked-out file in this worktree - genuinely modifying
    and re-hashing a byte-identical copy proves the same mechanism without
    any risk of corrupting the actual repository this session is running
    from if an assertion fails mid-test.
    """

    def test_a_byte_edited_hook_copy_degrades_a_previously_hard_proof(self) -> None:
        with h.e2e_repo() as repo:
            copy_path = repo.project.parent / "hook_copy.py"
            shutil.copyfile(h.HOOK, copy_path)

            record_interception_proof(
                repo.archive, host="claude", tool="Bash", request_id="tamper-1",
                hook_script=copy_path)
            self.assertEqual(
                interception_state(repo.archive, "claude", hook_script=copy_path,
                                   registration="partial"),
                "HARD")

            with copy_path.open("a", encoding="utf-8") as handle:
                handle.write("\n# godmode-modified: this byte changes the file's hash\n")

            self.assertEqual(
                interception_state(repo.archive, "claude", hook_script=copy_path,
                                   registration="partial"),
                "DEGRADED")
            self.assertEqual(
                degraded_reason(repo.archive, "claude", hook_script=copy_path,
                                registration="partial"),
                "hash-drift")

    def test_a_protected_operation_still_refuses_while_degraded(self) -> None:
        with h.e2e_repo() as repo:
            copy_path = repo.project.parent / "hook_copy.py"
            shutil.copyfile(h.HOOK, copy_path)
            record_interception_proof(
                repo.archive, host="claude", tool="Bash", request_id="tamper-2",
                hook_script=copy_path)
            with copy_path.open("a", encoding="utf-8") as handle:
                handle.write("\n# tampered\n")
            self.assertEqual(
                interception_state(repo.archive, "claude", hook_script=copy_path,
                                   registration="partial"),
                "DEGRADED")

            # R5 (force-push, never `ask`) - a deterministic `deny` makes
            # this assertion unambiguous about what "still refuses" means.
            payload = h.claude_shell("git push --force origin main", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")
            self.assertEqual(h.interpret("claude", result), "deny",
                             "a degraded proof state must never relax an unrelated call's "
                             "own real-time classification")


# ---------------------------------------------------------------------------
# 9b. Upgrade hash change (version drift) - plan-named row, distinct from
#     TamperedHookFileScenarioTests' byte-hash tamper: `_version_drifted`
#     fires when a proof's own `hook_version` no longer matches the
#     currently-running RUNTIME_VERSION (a legitimate upgrade happened
#     since the proof was written), never when the file's bytes changed.
#     `record_interception_proof` always stamps the CURRENT RUNTIME_VERSION
#     (no override parameter - by design, an honest write can never lie
#     about its own version), so this scenario simulates the SAME thing an
#     upgrade does: a record on disk whose `hook_version` field no longer
#     matches what is running now, built from a real proof's own real
#     fields (never a synthetic shape none of the CX-1/CX-5 invariants
#     would accept).
# ---------------------------------------------------------------------------


class VersionDriftScenarioTests(unittest.TestCase):
    """Review order I1(a): the plan names 'upgrade hash change' twice (the
    original CX-6 step and amendment 2) and it was absent from the shipped
    suite - `_version_drifted` and `_hash_drifted` are deliberately
    distinct code paths in `godmode_hookproof.py` with distinct
    `degraded_reason` strings, and only the hash-drift path had e2e
    coverage before this fix round."""

    def _stale_version_record(self, repo: h.E2ERepo) -> dict:
        fresh = record_interception_proof(
            repo.archive, host="claude", tool="Bash", request_id="version-drift")
        self.assertEqual(interception_state(repo.archive, "claude"), "HARD",
                         "the baseline proof must itself be HARD before staling it")
        # A real record's real fields, with ONLY `hook_version` mutated to
        # name an older release than the one now running - simulating an
        # upgrade that happened after this proof was originally minted,
        # never a byte-for-byte file edit (that is TamperedHookFileScenario
        # Tests' own, separate scenario).
        stale_data = dict(fresh["data"])
        stale_data["hook_version"] = "0.0.1-simulated-pre-upgrade"
        return repo.archive.append("action", SUBJECT_PROOF, stale_data, evidence=[])

    def test_a_stale_hook_version_degrades_a_previously_hard_proof(self) -> None:
        with h.e2e_repo() as repo:
            self._stale_version_record(repo)
            self.assertEqual(interception_state(repo.archive, "claude"), "DEGRADED")
            self.assertEqual(degraded_reason(repo.archive, "claude"), "version-drift")

    def test_a_protected_operation_still_refuses_through_the_real_hook_while_version_drifted(
        self,
    ) -> None:
        with h.e2e_repo() as repo:
            self._stale_version_record(repo)
            self.assertEqual(interception_state(repo.archive, "claude"), "DEGRADED")

            # R5 (force-push, never `ask`) - a deterministic `deny` makes
            # this assertion unambiguous, driven through the REAL hook
            # subprocess (not a direct `degraded_reason` call) - the same
            # discipline TamperedHookFileScenarioTests already applies to
            # the hash-drift path.
            payload = h.claude_shell("git push --force origin main", str(repo.project))
            result = h.run_hook(payload, repo, host="claude")
            self.assertEqual(h.interpret("claude", result), "deny",
                             "version-drift must never relax an unrelated call's own "
                             "real-time classification")


# ---------------------------------------------------------------------------
# 9c. Identity-mismatch explicit state - plan-named row (amendment 2): an
#     archive stranded at a NON-git identity (recorded before `git init`)
#     resolves to a DIFFERENT anchor once the project becomes a real git
#     repository. The mode table's own row: no continuity claim, and a
#     protected operation is still refused - never read as allow - through
#     the real hook subprocess, at both the session-start and pre-tool
#     boundaries.
# ---------------------------------------------------------------------------


class IdentityMismatchScenarioTests(unittest.TestCase):
    """Review order I1(b). Modeled on `tests/test_failure_semantics.py::
    ModeTableTests.test_row3_identity_mismatch_makes_no_continuity_claim_
    and_names_adopt`, extended here with a real bare remote and a real
    pre-tool force-push through `four_plane_check` - CX-5's own test stops
    at the session-start notice; this scenario is CX-6's job specifically
    (the real-subprocess, four-plane proof layer), which is why the plan
    assigns this row to CX-6 by name."""

    def _stranded_project(self) -> h.E2ERepo:
        base = Path(tempfile.mkdtemp())
        project = base / "project"
        project.mkdir()
        state = base / "state"
        # Record something BEFORE the project becomes a git repository - the
        # archive lands at the salted, non-git identity, exactly like CX-5's
        # own repro.
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            pre_git_archive = Chronicle(resolve_anchor(project))
            pre_git_archive.initialize()
            pre_git_archive.append("checkpoint", "before git init", {}, evidence=[])
        h.init_repo(project)
        repo = h.E2ERepo(project=project, state=state)
        h.commit_file(project, "seed.txt", "seed\n", env=repo.env())
        remote = base / "remote.git"
        h.git("init", "-q", "--bare", str(remote), cwd=base)
        h.git("remote", "add", "origin", str(remote), cwd=project, env=repo.env())
        pushed = h.git("push", "-q", "-u", "origin", "main", cwd=project, env=repo.env())
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        repo.remote = remote
        return repo

    def test_session_start_reports_orphaned_archive_never_a_continuity_claim(self) -> None:
        repo = self._stranded_project()
        done = subprocess.run(
            [sys.executable, str(h.HOOK), "session-start", "--project", str(repo.project)],
            input=json.dumps({"cwd": str(repo.project)}), capture_output=True, text=True,
            encoding="utf-8", timeout=60, env=repo.env(),
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout.strip())
        self.assertEqual(body.get("godmode"), "orphaned-archive")
        self.assertIn("adopt", body.get("next_action", ""))
        self.assertNotIn("permissionDecision", done.stdout)
        self.assertNotIn('"allow": true', done.stdout.lower())

    def test_a_protected_operation_is_still_refused_never_read_as_allow(self) -> None:
        repo = self._stranded_project()
        baseline = h.remote_ref(repo.remote)
        payload = h.claude_shell("git push --force origin main", str(repo.project))
        result = h.run_hook(payload, repo, host="claude")

        def _apply() -> None:
            pushed = h.git("push", "--force", "origin", "main",
                           cwd=repo.project, env=repo.env())
            self.assertEqual(pushed.returncode, 0, pushed.stderr)

        def _verify(decision: str) -> bool:
            current = h.remote_ref(repo.remote)
            return current == baseline if decision != "allow" else current != baseline

        report = h.four_plane_check(
            "identity-mismatch-protected-op", "claude", result, expect="blocked",
            on_allow=_apply, verify_side_effect=_verify)
        self.assertNotEqual(report.host_decision, "allow")


# ---------------------------------------------------------------------------
# 10. Malformed hook response => the TEST fails closed, never infers allow.
# ---------------------------------------------------------------------------


class MalformedHookResponseScenarioTests(unittest.TestCase):
    """Two distinct malformed shapes: a malformed INPUT payload (CX-5's own
    concern - the real hook subprocess must degrade, never crash into a
    silent allow), and a malformed/garbage OUTPUT reading (this harness's
    OWN interpretation layer must never read garbage as allow, whatever
    produced it)."""

    def test_malformed_input_payload_degrades_and_still_refuses_a_protected_op(self) -> None:
        with h.e2e_repo() as repo:
            completed = subprocess.run(
                [sys.executable, str(h.HOOK), "pre-action", "--project", str(repo.project)],
                input="{not valid json at all", capture_output=True, text=True,
                encoding="utf-8", timeout=60, cwd=str(repo.project), env=repo.env(host="claude"),
            )
            # A malformed, non-pretool-shaped payload takes the bare/exit-code
            # contract - never a crash, and the protected class beneath it
            # (proven separately below) never opens up because parsing failed.
            self.assertIn(completed.returncode, (0, 2))

            events = h.reopen_archive(repo).select(kind="action", subject="hook-health-degraded",
                                                    limit=5)
            self.assertTrue(events, "a malformed payload must record its own health signal")

    def test_the_harnesss_own_interpreter_never_reads_a_garbage_response_as_allow(self) -> None:
        """Claude/Cursor/Codex have a documented, deterministic exit-code
        contract - an exit code outside it is never inferred as permission.

        Grok/Gemini are the deliberate EXCEPTION, not a bug in this
        interpreter: Addendum 6's own live probe finding is that a real
        Grok host FAILS OPEN on any exit code it does not recognise - which
        is exactly why `godmode_hostevent.render_decision` never emits exit
        3 (or anything but 0/2) anywhere in this codebase (`EXIT 3 REMOVED`,
        both call sites' own comments). Simulating that fail-open honestly
        here is what makes this harness able to catch a REGRESSION (a
        future change that reintroduces an unrecognised exit code) - an
        interpreter that quietly reported "deny" instead would hide the
        exact danger CX-2 fixed.
        """
        garbage = h.HookResult(returncode=17, stdout="not json{{{", stderr="",
                               envelope={}, latency_seconds=0.001)
        for host in ("claude", "cursor", "codex"):
            with self.subTest(host=host):
                decision = h.interpret(host, garbage)
                self.assertNotEqual(decision, "allow",
                                    f"{host}: an unrecognised exit code with no parseable "
                                    "body must never be read as permission")
        for host in ("grok", "gemini"):
            with self.subTest(host=host):
                self.assertEqual(
                    h.interpret(host, garbage), "allow",
                    f"{host} fails OPEN on an unrecognised exit code (Addendum 6's own "
                    "live finding) - this interpreter must keep simulating that risk "
                    "honestly, not hide it, which is exactly why godmode's own hook "
                    "never emits an exit code outside {0, 2} anywhere")

    def test_four_plane_check_itself_refuses_to_pass_a_garbage_response_as_allow(self) -> None:
        garbage = h.HookResult(returncode=17, stdout="not json{{{", stderr="",
                               envelope={}, latency_seconds=0.001)
        with self.assertRaises(h.FourPlaneFailure):
            h.four_plane_check("garbage-response", "claude", garbage, expect="allow",
                               verify_side_effect=lambda decision: True)


# ---------------------------------------------------------------------------
# 11. Timeout simulation => per CX-5 semantics.
# ---------------------------------------------------------------------------


class TimeoutSimulationScenarioTests(unittest.TestCase):
    def test_a_probe_that_times_out_is_recorded_as_a_timeout_never_a_pass(self) -> None:
        with h.e2e_repo() as repo:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(repo.state)}, clear=False):
                result = run_probe(repo.project, repo.archive, "claude", timeout=0.0001)
            self.assertEqual(result["state"], "UNAVAILABLE")
            self.assertFalse(result["denied"])
            events = repo.archive.select(kind="action", subject="probe-failed", limit=5)
            self.assertTrue(events)
            self.assertEqual(events[-1]["data"]["reason"], "timeout")


# ---------------------------------------------------------------------------
# 12. Per-host dialect replay: read-only, edit, and shell-mutation payloads
#     in every documented dialect, run through the real hook subprocess.
# ---------------------------------------------------------------------------


class PerHostDialectReplayTests(unittest.TestCase):
    def test_every_documented_host_dialect_denies_the_same_force_push(self) -> None:
        for host, builder in h.HOST_SHELL_BUILDERS.items():
            with self.subTest(host=host):
                with h.e2e_repo() as repo:
                    payload = builder("git push --force origin main", str(repo.project))
                    result = h.run_hook(payload, repo, host=host)
                    self.assertIn(result.returncode, (0, 2))
                    self.assertEqual(h.interpret(host, result), "deny")

    def test_every_documented_host_dialect_allows_an_in_scope_edit(self) -> None:
        for host, builder in h.HOST_EDIT_BUILDERS.items():
            with self.subTest(host=host):
                with h.e2e_repo() as repo:
                    target = repo.project / "notes.md"
                    target.write_text("baseline\n", encoding="utf-8")
                    payload = builder(str(target), str(repo.project))
                    result = h.run_hook(payload, repo, host=host)
                    self.assertEqual(h.interpret(host, result), "allow")

    def test_codex_apply_patch_reaches_the_scope_fence(self) -> None:
        with h.e2e_repo() as repo:
            _approved_fence(repo.archive, "src/auth/**")
            outside = "src/billing/invoice.py"
            patch = (
                "*** Begin Patch\n"
                f"*** Add File: {outside}\n"
                "+new content\n"
                "*** End Patch\n"
            )
            payload = h.codex_apply_patch(patch, str(repo.project))
            result = h.run_hook(payload, repo, host="codex")
            self.assertEqual(h.interpret("codex", result), "deny")


if __name__ == "__main__":
    unittest.main()
