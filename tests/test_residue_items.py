"""Plan 7 Task 11: the carried residue items, one regression each.

Every class here names the residue item it closes. Each test fails on the
tree before its fix.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
for entry in (SCRIPTS, PLUGIN_ROOT, TESTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_guardrails import METER_FILENAME  # noqa: E402

from _host_env import scrubbed_env  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"


class S2EmptyStdinPreActionWritesNoMeter(unittest.TestCase):
    """An empty or whitespace-only pre-action payload describes no call, so
    it must not be metered as one against the project it ran in."""

    def _pre_action(self, project: Path, state: Path, stdin: bytes,
                    *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(HOOK), "pre-action", *extra],
            input=stdin, capture_output=True, timeout=60, cwd=str(project),
            env=scrubbed_env(GODMODE_STATE_HOME=str(state), GODMODE_HOST="claude"))

    def test_empty_and_whitespace_stdin_fail_closed_without_a_meter_write(self) -> None:
        for stdin in (b"", b"   ", b" \r\n\t\n"):
            with self.subTest(stdin=stdin):
                with isolated_project() as (project, state, _anchor, archive):
                    archive.initialize()
                    done = self._pre_action(project, state, stdin)
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertIn(b"no operation described", done.stderr)
                    self.assertFalse((archive.root / METER_FILENAME).exists())

    def test_an_explicit_project_does_not_meter_an_empty_payload_either(self) -> None:
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            done = self._pre_action(project, state, b"\n", "--project", str(project))
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertFalse((archive.root / METER_FILENAME).exists())


def _refusal(archive, operation: str, *, observed: bool) -> None:
    data = {"operation": operation, "tool": "Bash", "tier": "R4",
            "category": "filesystem-mutation"}
    if observed:
        data.update({"observed": True, "would_have": "deny", "reason": "r"})
    archive.append("refusal", "filesystem-mutation", data, evidence=[])


class S3ReadsPastTheFiveHundredRecordCap(unittest.TestCase):
    """`Chronicle.select` keeps only the newest 500 matching records, so a
    fold over it undercounts, and a lookup behind 500 newer records of the
    same kind reads as absent. Each site reads the whole archive now."""

    def test_would_have_summary_counts_every_observed_refusal(self) -> None:
        from godmode_runtime.godmode_roi import would_have_summary
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for i in range(600):
                _refusal(archive, f"rm -rf build{i}", observed=True)
            self.assertEqual(would_have_summary(archive)["total"], 600)

    def test_stage_from_refusal_finds_a_real_refusal_behind_600_observed_ones(self) -> None:
        from godmode_runtime.godmode_sentinel import stage_from_refusal
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            _refusal(archive, "git push --force", observed=False)
            for i in range(600):
                _refusal(archive, f"rm -rf build{i}", observed=True)
            self.assertEqual(stage_from_refusal(archive), "git push --force")

    def test_observe_report_lists_an_observed_refusal_behind_600_real_ones(self) -> None:
        import io
        import json
        from unittest import mock
        from godmode_runtime import godmode_console as console
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _refusal(archive, "rm -rf old-build", observed=True)
            for i in range(600):
                _refusal(archive, f"rm -rf build{i}", observed=False)
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                code = console.main(["--project", str(project), "observe", "--report"])
            self.assertEqual(code, 0)
            decisions = json.loads(out.getvalue())["decisions"]
            self.assertEqual([d["operation"] for d in decisions], ["rm -rf old-build"])

    def test_flake_ranking_counts_an_old_flake_behind_600_newer_retries(self) -> None:
        from godmode_runtime.godmode_trends import flakes
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            for _ in range(3):
                archive.append("action", "flaky-retry",
                               {"test_id": "tests.test_a.T.test_old",
                                "outcome": "passed-isolated"}, evidence=[])
            for _ in range(600):
                archive.append("action", "flaky-retry",
                               {"test_id": "tests.test_b.T.test_new",
                                "outcome": "passed-isolated"}, evidence=[])
            rows = {row["test_id"]: row for row in flakes(archive)}
            self.assertEqual(rows["tests.test_b.T.test_new"]["retries"], 600)
            self.assertEqual(rows["tests.test_a.T.test_old"]["retries"], 3)


class S4RemediesNameAResolvedLauncher(unittest.TestCase):
    """A remedy the operator is meant to type names the launcher by its
    resolved path, never a placeholder and never a bare `godmode` command
    that is not on PATH by default."""

    def test_require_tty_names_the_resolved_launcher(self) -> None:
        from unittest import mock
        from godmode_runtime import godmode_sentinel
        from godmode_runtime.godmode_errors import AuthorizationError
        with mock.patch.object(godmode_sentinel, "_stdin_is_interactive", return_value=False):
            with self.assertRaises(AuthorizationError) as raised:
                godmode_sentinel._require_tty()
        text = str(raised.exception)
        self.assertNotIn("<plugin-root>", text)
        self.assertIn((PLUGIN_ROOT.resolve() / "bin" / "godmode").as_posix(), text)

    def test_the_irreversible_refusal_names_no_bare_godmode_command(self) -> None:
        import json
        import re
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            payload = {"hook_event_name": "PreToolUse", "cwd": str(project),
                       "session_id": "s4", "tool_name": "Bash",
                       "tool_input": {"command": "git push --force origin main"}}
            done = subprocess.run(
                [sys.executable, str(HOOK), "pre-action"],
                input=json.dumps(payload).encode("utf-8"), capture_output=True,
                timeout=60, cwd=str(project),
                env=scrubbed_env(GODMODE_STATE_HOME=str(state), GODMODE_HOST="claude"))
            body = json.loads(done.stdout.decode("utf-8"))
            reason = body["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn("refused", reason)
            self.assertIsNone(re.search(r"`godmode\s", reason), reason)
            self.assertIn((PLUGIN_ROOT.resolve() / "bin" / "godmode").as_posix(), reason)


class S5FrozenRegionsAndTheFalseGreenRate(unittest.TestCase):
    """The frozen-region guard is proved at the real pre-tool boundary (the
    hook process, not only its helper), and the false-green rate counts
    every verified claim, not the newest 500."""

    def _edit(self, project: Path, state: Path, target: Path, old: str):
        import json
        payload = {"hook_event_name": "PreToolUse", "cwd": str(project),
                   "session_id": "s5", "tool_name": "Edit",
                   "tool_input": {"file_path": str(target), "old_string": old,
                                  "new_string": "changed"}}
        done = subprocess.run(
            [sys.executable, str(HOOK), "pre-action"],
            input=json.dumps(payload).encode("utf-8"), capture_output=True,
            timeout=60, cwd=str(project),
            env=scrubbed_env(GODMODE_STATE_HOME=str(state), GODMODE_HOST="claude"))
        out = done.stdout.decode("utf-8").strip()
        return json.loads(out) if out else {}

    def test_the_hook_refuses_an_edit_into_frozen_text_and_allows_the_region(self) -> None:
        from godmode_runtime.godmode_mutableregions import MARKER_END_TEXT, MARKER_START_TEXT
        with isolated_project() as (project, state, _anchor, archive):
            archive.initialize()
            target = project / "guarded.py"
            target.write_text(f"FROZEN_HEAD = 1\n# {MARKER_START_TEXT}\nBODY = 2\n"
                              f"# {MARKER_END_TEXT}\nFROZEN_TAIL = 3\n", encoding="utf-8")
            # The boundary stops the edit and names the region; on a host with
            # an ask decision the operator may still approve it.
            refused = self._edit(project, state, target, "FROZEN_HEAD = 1")
            decision = refused.get("hookSpecificOutput", {})
            self.assertIn(decision.get("permissionDecision"), ("ask", "deny"), refused)
            self.assertIn(MARKER_START_TEXT, decision.get("permissionDecisionReason", ""))
            allowed = self._edit(project, state, target, "BODY = 2")
            reason = allowed.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            self.assertNotIn(MARKER_START_TEXT, reason, allowed)

    def test_the_false_green_rate_sees_a_verified_claim_behind_500_newer_ones(self) -> None:
        from godmode_runtime.godmode_attest import false_green_rate
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            old = archive.append("claim", "the old fix holds", {"grade": "verified"},
                                 evidence=[])
            for i in range(510):
                archive.append("claim", f"filler claim {i}", {"grade": "observed"},
                               evidence=[])
            archive.append("claim", "the old fix holds - resolved",
                           {"resolves": old["sequence"], "outcome": "failed"}, evidence=[])
            rate = false_green_rate(archive)
            self.assertEqual(rate["false_greens"], 1, rate)
            self.assertEqual(rate["verified_resolved"], 1, rate)


def _manifest_fixture(root: Path, description: str) -> None:
    import json
    (root / "packaging").mkdir(parents=True)
    (root / "packaging" / "hosts.json").write_text(json.dumps({
        "identity": {"name": "demo", "version": "1.2.3",
                     "description": "Demo, enforced where the hook is live-proven."},
        "hosts": {}}), encoding="utf-8")
    (root / "plugin.json").write_text(json.dumps({
        "name": "demo", "version": "1.2.3", "description": description,
        "extensions": {"kept": True}}, indent=2) + "\n", encoding="utf-8")


class S7ManifestTextLivesInOnePlace(unittest.TestCase):
    """The description and its enforcement qualifier are written once, in
    packaging/hosts.json; the root portable manifest is generated from it,
    and `version --reconcile` reports a hand edit with a remedy."""

    def test_reconcile_reports_a_hand_edited_root_manifest_and_bindings_repairs_it(self) -> None:
        import io
        import json
        import tempfile
        from unittest import mock
        from godmode_runtime import godmode_bindings, godmode_console as console
        from godmode_runtime.godmode_reconcile import reconcile_versions
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            _manifest_fixture(root, "Demo, enforced everywhere.")
            report = reconcile_versions(root)
            self.assertEqual(report["verdict"], "manifest-drift")
            (finding,) = report["findings"]
            self.assertEqual(finding["surface"], "plugin.json")
            self.assertIn("bindings --write", finding["remedy"])
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                code = console.main(["--project", str(root), "version", "--reconcile"])
            self.assertEqual(code, 1)

            godmode_bindings.write(root)
            written = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(written["description"], "Demo, enforced where the hook is live-proven.")
            self.assertEqual(written["extensions"], {"kept": True}, "non-generated keys are kept")
            self.assertEqual(reconcile_versions(root)["verdict"], "agreed")

    def test_this_repository_writes_the_qualifier_once(self) -> None:
        from godmode_runtime import godmode_bindings
        source = (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8")
        self.assertEqual(source.count("live-proven"), 1)
        entries = {e["path"]: e for e in godmode_bindings.check(PLUGIN_ROOT)["hosts"]}
        self.assertEqual(entries["plugin.json"]["state"], "current")


if __name__ == "__main__":
    unittest.main()
