"""C-6: ownership map, gate-table freshness, and the install manifest
(0.3.28 Plan 4, Task 2).

`ownership_map`/`owner_of` name which sentinel rule owns a sample path or
command; `table_is_stale` is the cheap digest-only freshness check the
pre-commit backstop (`godmode_githooks._evaluate_pre_commit`) now runs
unconditionally, as a sibling to the closure check Plan 3 Task 8 added.
The install-manifest half extends the manifest that already existed
(`godmode_installmanifest.py`/`godmode_installremove.py`) rather than
adding a second one under a different "state home" - see
`godmode_ownership`'s own module docstring for the divergence from the
brief this records.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import os

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_ownership import (  # noqa: E402
    check, ownership_map, owner_of, table_is_stale,
)
from godmode_runtime.godmode_console import Runtime, cmd_hooks, cmd_ownership  # noqa: E402
from godmode_runtime import godmode_bindings as bindings  # noqa: E402
from godmode_runtime import godmode_host_manifests as host_manifests  # noqa: E402
from godmode_runtime import godmode_installmanifest as manifest_io  # noqa: E402
from godmode_runtime import godmode_installremove as remove_io  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(project), *args],
        check=True, capture_output=True, timeout=60,
    )


class OwnershipMapPathTests(unittest.TestCase):
    """Ownership of three sample paths, each matched by a distinct sentinel rule."""

    def test_three_sample_paths_resolve_to_distinct_rules(self) -> None:
        table = ownership_map()
        cases = {
            ".github/workflows/ci.yml": "hook-as-code-write",
            "RELEASE-FREEZE.md": "release-freeze-mutation",
            ".env": "worktree-file-mutation",
        }
        for path, expected_rule in cases.items():
            owner = owner_of(path, table)
            self.assertIsNotNone(owner, path)
            self.assertEqual(owner["rule"], expected_rule, path)
            self.assertTrue(owner["tier"], path)

    def test_an_ordinary_source_file_is_unowned(self) -> None:
        # Not a fabricated default: `ownership_map` has no catch-all pattern
        # (see its own module docstring), so a path none of the three static
        # rules match is honestly reported as owned by nothing.
        self.assertIsNone(owner_of("scripts/godmode_runtime/godmode_status.py"))


class OwnershipMapCommandTests(unittest.TestCase):
    """Ownership of three sample commands, each matched by a distinct
    `_ACTION_PATTERNS` category."""

    def test_three_sample_commands_resolve_to_distinct_rules(self) -> None:
        table = ownership_map()
        cases = {
            "git push": "git-history-or-remote",
            "rm -rf /tmp/x": "filesystem-mutation",
            "kill 1234": "process-control",
        }
        for command, expected_rule in cases.items():
            owner = owner_of(command, table)
            self.assertIsNotNone(owner, command)
            self.assertEqual(owner["rule"], expected_rule, command)

    def test_a_read_only_command_is_unowned(self) -> None:
        self.assertIsNone(owner_of("ls -la"))


class FreshnessTests(unittest.TestCase):
    def test_the_real_shipped_table_is_fresh(self) -> None:
        report = table_is_stale(PLUGIN_ROOT)
        self.assertTrue(report["present"], report)
        self.assertFalse(report["stale"], report)

    def test_a_hand_edited_table_copy_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "hooks").mkdir()
            table = json.loads(
                (PLUGIN_ROOT / "hooks" / "gate_table.json").read_text(encoding="utf-8"))
            table["generated_from"] = "0" * 12  # deliberately wrong
            (project / "hooks" / "gate_table.json").write_text(
                json.dumps(table), encoding="utf-8")

            report = table_is_stale(project)
            self.assertTrue(report["present"], report)
            self.assertTrue(report["stale"], report)

    def test_a_project_with_no_table_at_all_is_not_reported_stale(self) -> None:
        """A project (or a synthetic test fixture) that never shipped
        `hooks/gate_table.json` has nothing to be stale about - see
        `table_is_stale`'s own docstring for why this must not block every
        commit in a project with no such artifact."""
        with tempfile.TemporaryDirectory() as raw:
            report = table_is_stale(Path(raw))
            self.assertFalse(report["present"], report)
            self.assertFalse(report["stale"], report)

    def test_a_godmode_source_checkout_missing_its_table_is_stale(self) -> None:
        """Fix round 1 (reviewer finding): a project that DOES carry the
        sentinel module - a real godmode-source checkout, including any of
        this project's own worktree checkouts, not only the one
        `godmode_ownership.py` happens to be imported from - but has no
        `hooks/gate_table.json` at all is the drift this task exists to
        catch, not a "nothing to check" case."""
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            sentinel_dir = project / "scripts" / "godmode_runtime"
            sentinel_dir.mkdir(parents=True)
            (sentinel_dir / "godmode_sentinel.py").write_text(
                "# a godmode-source checkout marker\n", encoding="utf-8")
            # deliberately no hooks/gate_table.json

            report = table_is_stale(project)
            self.assertFalse(report["present"], report)
            self.assertTrue(report["stale"], report)

    def test_cmd_ownership_exits_1_on_a_stale_table(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            _git(project, "init", "-q")
            (project / "hooks").mkdir()
            table = json.loads(
                (PLUGIN_ROOT / "hooks" / "gate_table.json").read_text(encoding="utf-8"))
            table["generated_from"] = "0" * 12
            (project / "hooks" / "gate_table.json").write_text(
                json.dumps(table), encoding="utf-8")

            runtime = Runtime(anchor=anchor, archive=archive)
            args = argparse.Namespace(check=True, diff_only=False)
            result = cmd_ownership(args, runtime)
            self.assertEqual(result.exit_code, 1, result.payload)
            self.assertFalse(result.payload["table_fresh"])

    def test_cmd_ownership_exits_0_on_the_real_shipped_table(self) -> None:
        from godmode_runtime.godmode_anchor import resolve_anchor
        from godmode_runtime.godmode_chronicle import Chronicle
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": raw}, clear=False):
                anchor = resolve_anchor(PLUGIN_ROOT)
                runtime = Runtime(anchor=anchor, archive=Chronicle(anchor))
                args = argparse.Namespace(check=True, diff_only=False)
                result = cmd_ownership(args, runtime)
        self.assertEqual(result.exit_code, 0, result.payload)
        self.assertTrue(result.payload["table_fresh"])


class DiffOnlyWalkTests(unittest.TestCase):
    def test_diff_only_scopes_to_working_tree_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            _git(project, "init", "-q")
            (project / "a.txt").write_text("x", encoding="utf-8")
            _git(project, "add", "-A")
            _git(project, "commit", "-q", "-m", "base")
            (project / "b.txt").write_text("y", encoding="utf-8")  # untracked

            diff_report = check(project, diff_only=True)
            diff_paths = {entry["path"] for entry in diff_report["entries"]}
            self.assertIn("b.txt", diff_paths)
            self.assertNotIn("a.txt", diff_paths)

            full_report = check(project, diff_only=False)
            full_paths = {entry["path"] for entry in full_report["entries"]}
            self.assertIn("a.txt", full_paths)


class GitTableFreshnessBackstopTests(unittest.TestCase):
    """The pre-commit backstop's sibling check (`godmode_githooks.
    _evaluate_pre_commit`), added next to Plan 3 Task 8's closure check."""

    def test_a_stale_table_blocks_the_commit(self) -> None:
        from godmode_runtime import godmode_githooks

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _git(project, "init", "-q")
            (project / "hooks").mkdir()
            table = json.loads(
                (PLUGIN_ROOT / "hooks" / "gate_table.json").read_text(encoding="utf-8"))
            table["generated_from"] = "0" * 12
            (project / "hooks" / "gate_table.json").write_text(
                json.dumps(table), encoding="utf-8")
            (project / "README.md").write_text("hello\n", encoding="utf-8")
            _git(project, "add", "-A")

            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "block", decision)
            self.assertEqual(decision["category"], "gate-table-stale")

    def test_a_project_without_a_table_is_not_blocked_by_this_check(self) -> None:
        from godmode_runtime import godmode_githooks

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _git(project, "init", "-q")
            (project / "README.md").write_text("hello\n", encoding="utf-8")
            _git(project, "add", "-A")

            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertNotEqual(decision.get("category"), "gate-table-stale", decision)

    def test_a_godmode_source_checkout_missing_its_table_is_blocked(self) -> None:
        """Fix round 1: the sentinel module present with no table alongside
        it is a godmode-source checkout that shipped without its table -
        blocked, same as a present-but-mismatched one."""
        from godmode_runtime import godmode_githooks

        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _git(project, "init", "-q")
            sentinel_dir = project / "scripts" / "godmode_runtime"
            sentinel_dir.mkdir(parents=True)
            (sentinel_dir / "godmode_sentinel.py").write_text(
                "# a godmode-source checkout marker\n", encoding="utf-8")
            # deliberately no hooks/gate_table.json
            _git(project, "add", "-A")

            decision = godmode_githooks._evaluate_pre_commit(archive, project)
            self.assertEqual(decision["verdict"], "block", decision)
            self.assertEqual(decision["category"], "gate-table-stale")


class InstallManifestTests(unittest.TestCase):
    """Every path `bindings --write`/`hooks wire` creates is recorded, and a
    removal test finds none missing after uninstall - extending the
    manifest that already exists rather than adding a second one."""

    def test_bindings_write_records_every_path_it_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / "packaging").mkdir()
            (project / "packaging" / "hosts.json").write_text(
                (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (project / "hooks").mkdir()
            (project / "hooks" / "hooks.json").write_text(
                (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            result = bindings.write(project)
            self.assertTrue(result["written"], result)

            recorded = set(manifest_io.recorded_paths(project, "godmode"))
            for path in result["written"]:
                self.assertIn(path, recorded, f"{path} was written but not recorded")

    def test_hooks_wire_paths_are_recorded_and_status_reads_them(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            _git(project, "init", "-q")
            result = host_manifests.write_codex_project_hooks(PLUGIN_ROOT, project)
            self.assertTrue(result.get("written"), result)

            runtime = Runtime(anchor=anchor, archive=archive)
            args = argparse.Namespace(hooks_command="status", host=None, git=False)
            outcome = cmd_hooks(args, runtime)

            manifest_report = outcome.payload["install_manifest"]
            relative = manifest_io.relative_posix(project, result["path"])
            self.assertIn(relative, manifest_report["recorded"], manifest_report)
            self.assertEqual(manifest_report["missing"], [], manifest_report)

    def test_hooks_status_flags_a_recorded_path_that_is_missing(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            _git(project, "init", "-q")
            manifest_io.record(project, "godmode", "test-group",
                               [project / "never-actually-written.txt"])

            runtime = Runtime(anchor=anchor, archive=archive)
            args = argparse.Namespace(hooks_command="status", host=None, git=False)
            outcome = cmd_hooks(args, runtime)

            manifest_report = outcome.payload["install_manifest"]
            self.assertIn("never-actually-written.txt", manifest_report["missing"], manifest_report)

    def test_removal_after_a_real_install_finds_none_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            written: list[str] = []
            for call in (
                lambda: host_manifests.write_codex_project_hooks(PLUGIN_ROOT, project),
                lambda: host_manifests.write_opencode_project_shim(PLUGIN_ROOT, project),
                lambda: host_manifests.write_antigravity_project_hooks(PLUGIN_ROOT, project),
            ):
                result = call()
                if result.get("written"):
                    written.append(result["path"])
            self.assertTrue(written, "no host writer produced a file")

            report = remove_io.archive(project, "godmode")
            self.assertEqual(report["missing"], [], report)
            expected = sorted(manifest_io.relative_posix(project, p) for p in written)
            self.assertEqual(sorted(report["archived"]), expected)


if __name__ == "__main__":
    unittest.main()
