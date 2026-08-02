from __future__ import annotations

from contextlib import contextmanager
import ast
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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import (  # noqa: E402
    ArchiveError,
    AuthorizationError,
    ForgeError,
    PrivacyError,
)
from godmode_runtime.godmode_forge import (  # noqa: E402
    SkillProposal,
    forge_skill,
    validate_skill,
)
from godmode_runtime.godmode_lens import (  # noqa: E402
    collect_inventory,
    detect_context_issues,
    inventory_diff,
    make_snapshot,
)
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    CapabilityBroker,
    classify_action,
)


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


class AnchorTests(unittest.TestCase):
    def test_non_git_state_is_salted_and_outside_project(self) -> None:
        with isolated_project() as (project, state, anchor, _archive):
            repeated = resolve_anchor(project)
            self.assertFalse(anchor.is_git)
            self.assertEqual(anchor.project_key, repeated.project_key)
            self.assertTrue(Path(anchor.archive_root).is_relative_to(state))
            self.assertFalse(Path(anchor.archive_root).is_relative_to(project))
            public = anchor.public_view()
            self.assertEqual(public["project_root"], ".")
            self.assertEqual(public["archive_root"], "<local-state>")
            self.assertNotIn(str(project), json.dumps(public))

    def test_public_authorship_is_passive_runtime_metadata(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        public_identity = manifest["author"]["name"].casefold()
        with isolated_project() as (_project, _state, anchor, archive):
            self.assertNotIn(public_identity, anchor.archive_root.casefold())
            archive.initialize()
            self.assertNotIn(
                public_identity,
                archive.config.read_text(encoding="utf-8").casefold(),
            )


class PackagingTests(unittest.TestCase):
    def test_codex_and_claude_manifests_are_aligned(self) -> None:
        codex = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        claude = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        marketplace = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        hook_config = json.loads(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )

        self.assertEqual(codex["name"], claude["name"])
        self.assertEqual(codex["version"], claude["version"])
        self.assertEqual(codex["author"]["name"], claude["author"]["name"])
        self.assertEqual(claude["repository"], "https://github.com/AIimagined/Godmode")
        self.assertEqual(claude["skills"], "./skills/")
        self.assertEqual(claude["hooks"], "./hooks/hooks.json")

        self.assertEqual(marketplace["name"], "aiimagined")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "godmode")
        self.assertEqual(entry["source"], "./")
        self.assertTrue(entry["strict"])
        self.assertNotIn("version", entry)

        handler = hook_config["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(handler["command"], "python")
        self.assertEqual(handler["args"][0], "${CLAUDE_PLUGIN_ROOT}/hooks/godmode_session_hook.py")
        self.assertEqual(handler["args"][1], "session-start")

    def test_claude_session_hook_is_silent_until_initialized(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            hook = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
            submitted = json.dumps(
                {
                    "session_id": "synthetic-session",
                    "cwd": str(project),
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                }
            )

            def run_hook() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, str(hook), "session-start"],
                    input=submitted,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=os.environ.copy(),
                )

            silent = run_hook()
            self.assertEqual(silent.returncode, 0, silent.stderr)
            self.assertEqual(silent.stdout, "")

            archive.initialize()
            active = run_hook()
            self.assertEqual(active.returncode, 0, active.stderr)
            output = json.loads(active.stdout)
            specific = output["hookSpecificOutput"]
            self.assertEqual(specific["hookEventName"], "SessionStart")
            self.assertIn("Godmode recovered", specific["additionalContext"])
            self.assertLessEqual(len(specific["additionalContext"]), 9_000)


class ChronicleTests(unittest.TestCase):
    def test_records_are_hash_chained_and_tamper_evident(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            archive.append("decision", "storage", {"value": "local"}, evidence=["check:1"])
            archive.append("lesson", "guard", {"value": "verify"}, evidence=[])
            verified = archive.verify()
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["records"], 2)

            first = archive.event_paths()[0]
            payload = json.loads(first.read_text(encoding="utf-8"))
            payload["data"]["value"] = "altered"
            first.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ArchiveError):
                archive.verify()

    def test_secret_shaped_material_is_rejected_before_persistence(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            with self.assertRaises(PrivacyError):
                archive.append(
                    "decision",
                    "unsafe",
                    {"value": "api_key=abcdefghijklmnopqrstuv"},
                    evidence=[],
                )
            self.assertEqual(archive.verify()["records"], 0)


class CapabilityTests(unittest.TestCase):
    def test_unknown_mutations_fail_closed(self) -> None:
        self.assertFalse(classify_action("git status")["protected"])
        preview = classify_action("change an unspecified production setting")
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unclassified-mutation")

    def test_capability_is_exact_and_single_use(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            broker = CapabilityBroker(archive)
            password = "correct-horse-local-only"
            operation = "git push origin main"
            broker.configure(password)
            token = broker.issue(operation, password, ttl_seconds=30)
            with self.assertRaises(AuthorizationError):
                broker.consume("git push origin release", token)
            result = broker.consume(operation, token)
            self.assertEqual(result["category"], "git-history-or-remote")
            with self.assertRaises(AuthorizationError):
                broker.consume(operation, token)


class InventoryAndDetectorTests(unittest.TestCase):
    def test_inventory_hashes_content_without_storing_bodies(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            (project / "package.json").write_text("{}", encoding="utf-8")
            (project / "app.py").write_text("private implementation body", encoding="utf-8")
            (project / "test_app.py").write_text("pass", encoding="utf-8")
            (project / "guide.md").write_text("notes", encoding="utf-8")
            (project / "settings.yaml").write_text("enabled: true", encoding="utf-8")
            (project / "local.sqlite").write_bytes(b"database")
            before = collect_inventory(project)
            self.assertEqual(
                before["categories"],
                {
                    "code": 1,
                    "configuration": 1,
                    "database": 1,
                    "documentation": 1,
                    "manifest": 1,
                    "test": 1,
                },
            )
            self.assertNotIn("private implementation body", json.dumps(before))
            (project / "app.py").write_text("changed implementation", encoding="utf-8")
            after = collect_inventory(project)
            self.assertEqual(inventory_diff(before, after)["changed"], ["app.py"])

    def test_detectors_surface_contradictions_loops_and_unproven_completion(self) -> None:
        with isolated_project() as (project, _state, anchor, archive):
            (project / "app.py").write_text("pass", encoding="utf-8")
            archive.initialize()
            snapshot = make_snapshot(anchor)
            archive.append("inventory", "baseline", snapshot, evidence=[])
            archive.append("invariant", "runtime-mode", {"value": "local"}, evidence=[])
            archive.append("invariant", "runtime-mode", {"value": "cloud"}, evidence=[])
            archive.append(
                "change", "unproven", {"status": "complete", "files": ["missing.py"]}, evidence=[]
            )
            for index in range(3):
                archive.append(
                    "checkpoint",
                    f"attempt-{index}",
                    {"status": "failed", "hypothesis": "the cache alone caused it"},
                    evidence=[f"test:{index}"],
                )
            archive.append(
                "sprint",
                "current",
                {"status": "active", "capacity": 1, "obligations": ["one", "two"]},
                evidence=[],
            )
            issues = detect_context_issues(anchor, archive.read_events(), collect_inventory(project))
            codes = {issue["code"] for issue in issues}
            self.assertTrue(
                {
                    "contradictory-invariants",
                    "unproven-completion",
                    "repeat-loop",
                    "phantom-reference",
                    "capacity-overflow",
                }.issubset(codes)
            )


class ForgeTests(unittest.TestCase):
    @staticmethod
    def proposal(**overrides: object) -> SkillProposal:
        values = {
            "name": "release-observer",
            "purpose": "Summarize release evidence: without mutating repository state",
            "gap_evidence": "Two release reviews lacked one repeatable evidence summary and verification boundary.",
            "repeated_uses": 2,
            "positive_triggers": (
                "a release review needs a bounded evidence summary",
                "a version handoff needs fresh verification",
            ),
            "negative_triggers": (
                "the user asks to publish a release",
                "the user only asks for the current version number",
            ),
            "assertions": (
                "The result lists the inspected version and verification evidence",
            ),
        }
        values.update(overrides)
        return SkillProposal(**values)  # type: ignore[arg-type]

    def test_forge_creates_yaml_safe_original_skill_and_evals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = forge_skill(Path(temporary), self.proposal())
            result = validate_skill(skill)
            self.assertTrue(result["valid"])
            self.assertEqual(result["positive_cases"], 2)
            frontmatter = (skill / "SKILL.md").read_text(encoding="utf-8").splitlines()[:4]
            self.assertTrue(frontmatter[2].startswith('description: "'))
            self.assertTrue((skill / "godmode-evals.json").is_file())

    def test_forge_requires_repetition_and_rejects_remote_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ForgeError):
                forge_skill(Path(temporary), self.proposal(repeated_uses=1))
            with self.assertRaises(ForgeError):
                forge_skill(
                    Path(temporary),
                    self.proposal(gap_evidence="The repeated gap is described at https://example.invalid/reference."),
                )


class CliAndPrivacyTests(unittest.TestCase):
    def test_cli_lifecycle_and_guard_exit_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            project.mkdir()
            (project / "main.py").write_text("print('ok')", encoding="utf-8")
            environment = os.environ.copy()
            environment["GODMODE_STATE_HOME"] = str(base / "state")
            cli = SCRIPTS / "godmode.py"

            def run(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        sys.executable,
                        str(cli),
                        "--project",
                        str(project),
                        "--json",
                        *arguments,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=environment,
                )

            initialized = run("init")
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertEqual(json.loads(initialized.stdout)["identity"]["project_root"], ".")
            self.assertEqual(run("inspect").returncode, 0)
            self.assertEqual(run("resume", "--token-budget", "200").returncode, 0)
            safe = run("guard", "--operation", "git status")
            self.assertEqual(safe.returncode, 0)
            self.assertFalse(json.loads(safe.stdout)["protected"])
            protected = run("guard", "--operation", "git push origin main")
            self.assertEqual(protected.returncode, 3)
            self.assertFalse(json.loads(protected.stdout)["authorized"])
            self.assertEqual(run("privacy").returncode, 0)

    def test_cli_record_surfaces_parity_export_and_forge_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            project = base / "project"
            reference = base / "reference"
            project.mkdir()
            reference.mkdir()
            (project / "main.py").write_text("print('ok')", encoding="utf-8")
            (reference / "reference.py").write_text("pass", encoding="utf-8")
            environment = os.environ.copy()
            environment["GODMODE_STATE_HOME"] = str(base / "state")
            cli = SCRIPTS / "godmode.py"

            def run(*arguments: str) -> subprocess.CompletedProcess[str]:
                result = subprocess.run(
                    [sys.executable, str(cli), "--project", str(project), "--json", *arguments],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=environment,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                return result

            run("init")
            run("inspect")
            run("plan", "--title", "bounded change", "--step", "inspect", "--obligation", "preserve state", "--evidence", "request:1")
            run("build", "--summary", "implemented", "--status", "complete", "--file", "main.py", "--evidence", "test:pass")
            run("checkpoint", "--summary", "handoff", "--status", "complete", "--next", "review", "--evidence", "test:pass")
            run("checklist", "update", "--item", "privacy", "--status", "done", "--evidence", "privacy:pass")
            run("remember", "--kind", "lesson", "--subject", "verification", "--value", "verify fresh state", "--guard", "rerun checks", "--evidence", "test:pass")
            run("version", "--name", "plugin", "--value", "0.1.0", "--evidence", "manifest:checked")
            run("db", "--engine", "sqlite", "--change", "future migration", "--status", "planned", "--rollback", "restore backup", "--evidence", "plan:reviewed")
            run("sprint", "--name", "current", "--status", "active", "--capacity", "2", "--obligation", "finish verification", "--evidence", "scope:reviewed")
            run("docs", "--document", "acceptance", "--status", "current", "--note", "verified", "--evidence", "docs:reviewed")
            run("branches", "--record")
            run("history", "--limit", "100")
            run("inventory", "diff")
            run("context", "status", "--scan")
            run("context", "why")
            run("explain-context")
            run("report", "--token-budget", "300")
            exported = base / "context-export.json"
            run("export", "--output", str(exported), "--token-budget", "300")
            self.assertTrue(exported.is_file())
            self.assertFalse(json.loads(exported.read_text(encoding="utf-8"))["raw_archive_included"])
            run("parity", "--reference", str(reference))
            run("actions")
            run("skill", "validate", "--path", str(PLUGIN_ROOT / "skills" / "godmode"))

            forged = base / "forged"
            wrapper = SCRIPTS / "godmode_skill_forge.py"
            wrapped = subprocess.run(
                [
                    sys.executable,
                    str(wrapper),
                    "--project",
                    str(project),
                    "--json",
                    "--destination",
                    str(forged),
                    "--name",
                    "context-observer",
                    "--purpose",
                    "Summarize bounded local context with direct verification evidence",
                    "--gap-evidence",
                    "Two separate handoffs lacked the same compact verified local context summary.",
                    "--repeated-uses",
                    "2",
                    "--positive",
                    "a handoff needs a verified local summary",
                    "--positive",
                    "a resumed task needs bounded context evidence",
                    "--negative",
                    "the user asks to modify source code",
                    "--negative",
                    "the user requests a remote research report",
                    "--assertion",
                    "The result identifies included evidence and explicit limits",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr or wrapped.stdout)
            self.assertTrue((forged / "context-observer" / "SKILL.md").is_file())
            run("doctor", "--deep")

    def test_runtime_has_no_network_client_imports_or_remote_literals(self) -> None:
        banned = {"sock" + "et", "url" + "lib", "http", "requests", "aiohttp", "websockets"}
        remote_marker = "ht" + "tps://"
        imported: set[str] = set()
        for path in (SCRIPTS / "godmode_runtime").glob("*.py"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn(remote_marker, content, path.name)
            tree = ast.parse(content, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertFalse(imported & banned, imported & banned)


if __name__ == "__main__":
    unittest.main()
