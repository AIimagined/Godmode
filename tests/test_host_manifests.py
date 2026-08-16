"""CX-3: native host hook manifests.

Every assertion here is bound to `docs/superpowers/plans/2026-08-16-codex-
compat.md` (Task CX-3 + Global Constraints + Plan amendments 1-4) and
`docs/superpowers/specs/2026-08-16-codex-compat-design.md` (CX-3 unit +
Addenda 2, 4, 4a, 5, 6, 6a) - the same discipline `test_hostevent.py` (CX-2)
already applies: an emitted name that cannot be traced to a specific
addendum is a defect in the module under test, not a gap in this file.

Covers: `godmode bindings --write` regenerating the Codex/Grok/Cursor/Gemini
hook artifacts alongside the existing identity manifests, byte-stable across
repeated runs; the event-name allowlist agreement `godmode_host_manifests.py`
declares as its own governing rule; the base `plugin.json`'s closed v1 field
list; and the skills roster fix (no Claude-only directory hints, host-neutral
forge destination).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_bindings as bindings  # noqa: E402
from godmode_runtime import godmode_host_manifests as host_manifests  # noqa: E402


@contextmanager
def _built_project():
    """A real copy of this repo's packaging inputs (`packaging/hosts.json`
    plus whatever hook scripts the manifests reference), freshly regenerated
    into a scratch directory - so these tests exercise the ACTUAL generator
    against the ACTUAL source file, never a hand-built fixture that could
    drift from it.
    """
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
        bindings.write(project)
        yield project


class CodexManifestTests(unittest.TestCase):
    def test_the_generated_codex_identity_manifest_names_the_native_variable(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")

    def test_the_shared_hooks_file_uses_plugin_root_never_claude_plugin_root_for_codex_keys(
        self,
    ) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        codex_text = json.dumps(manifest["hooks"]["session_start"]) + json.dumps(
            manifest["hooks"]["pre_tool_use"])
        self.assertIn("${PLUGIN_ROOT}", codex_text)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", codex_text)

    def test_claudes_own_three_keys_are_untouched_by_the_codex_merge(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        original = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for key in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
            self.assertEqual(manifest["hooks"][key], original["hooks"][key])

    def test_the_pre_tool_use_matcher_is_the_union_of_codex_tools_the_adapter_recognises(
        self,
    ) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        matcher = manifest["hooks"]["pre_tool_use"][0]["matcher"]
        for tool in ("shell_command", "apply_patch", "functions.exec"):
            self.assertIn(tool, matcher)


class GrokManifestTests(unittest.TestCase):
    def test_grok_entries_are_a_single_string_command_never_an_args_array(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".grok-plugin" / "hooks.json").read_text(encoding="utf-8"))
        for event in manifest["hooks"].values():
            for entry in event[0]["hooks"]:
                self.assertNotIn("args", entry, entry)
                self.assertIsInstance(entry["command"], str)
                self.assertIn("commandWindows", entry)
                self.assertIsInstance(entry["commandWindows"], str)

    def test_the_pretooluse_matcher_is_the_plans_exact_union_string(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".grok-plugin" / "hooks.json").read_text(encoding="utf-8"))
        matcher = manifest["hooks"]["PreToolUse"][0]["matcher"]
        self.assertEqual(
            matcher,
            "Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit|"
            "run_terminal_command|search_replace|write",
        )

    def test_precompact_and_sessionend_are_registered(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".grok-plugin" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("PreCompact", manifest["hooks"])
        self.assertIn("SessionEnd", manifest["hooks"])
        # The script this manifest wires to must actually accept these two
        # CLI subcommands - not just have the event key present.
        args_or_command = json.dumps(manifest["hooks"]["PreCompact"])
        self.assertIn("pre-compact", args_or_command)
        args_or_command = json.dumps(manifest["hooks"]["SessionEnd"])
        self.assertIn("session-end", args_or_command)

    def test_every_timeout_is_explicit_and_bounded(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".grok-plugin" / "hooks.json").read_text(encoding="utf-8"))
        for event, groups in manifest["hooks"].items():
            for entry in groups[0]["hooks"]:
                timeout = entry["timeout"]
                self.assertIsInstance(timeout, int, event)
                self.assertGreater(timeout, 0, event)
                self.assertLess(timeout, 120, event)  # bounded, not unbounded


class CursorManifestTests(unittest.TestCase):
    def test_version_envelope_is_one(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".cursor-plugin" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], 1)

    def test_fail_closed_is_true_on_both_gate_hooks(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".cursor-plugin" / "hooks.json").read_text(encoding="utf-8"))
        for event in ("preToolUse", "beforeShellExecution"):
            self.assertTrue(manifest["hooks"][event][0]["failClosed"], event)

    def test_session_start_is_registered_camelcase(self) -> None:
        with _built_project() as project:
            manifest = json.loads(
                (project / ".cursor-plugin" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("sessionStart", manifest["hooks"])

    def test_the_pretooluse_matcher_never_emits_edit_or_any_untraceable_name(self) -> None:
        """Fix round 1 (C2, review Critical): `"Edit"` has no source in
        Addendum 5's documented tool-type vocabulary (Shell, Read, Write,
        Grep, Delete, Task, MCP:<name>) - the prior manifest emitted it
        anyway, untraceable and unflagged. Every emitted tool-type name must
        be a member of that documented vocabulary."""
        with _built_project() as project:
            manifest = json.loads(
                (project / ".cursor-plugin" / "hooks.json").read_text(encoding="utf-8"))
        matcher = manifest["hooks"]["preToolUse"][0]["matcher"]
        emitted = frozenset(matcher.split("|"))
        self.assertNotIn("Edit", emitted)
        self.assertLessEqual(emitted, host_manifests.CURSOR_DOCUMENTED_TOOL_TYPES, emitted)

    def test_the_pretooluse_matcher_emitted_set_equals_the_traceable_mutating_set(self) -> None:
        """The emitted set (fix round 1's own binding instruction:
        `Shell|Write|Delete`, the mutating subset the fast gate handles)
        equals the traceable set exactly - not merely a subset of the full
        documented vocabulary, and not silently narrower or wider."""
        with _built_project() as project:
            manifest = json.loads(
                (project / ".cursor-plugin" / "hooks.json").read_text(encoding="utf-8"))
        matcher = manifest["hooks"]["preToolUse"][0]["matcher"]
        emitted = frozenset(matcher.split("|"))
        self.assertEqual(emitted, frozenset({"Shell", "Write", "Delete"}))
        self.assertEqual(emitted, host_manifests.cursor_pretooluse_matcher_tools())

    def test_cursor_plugin_root_gap_is_surfaced_on_the_hook_artifacts_registry(self) -> None:
        """Fix round 1 (I2, review Important): the plugin-root-variable gap
        was previously only in `build_cursor_manifest`'s docstring, invisible
        to `hooks status`'s structured `gap` field - asymmetric with
        Gemini's entry, which already carried one."""
        gap = host_manifests.HOOK_ARTIFACTS["cursor"].get("gap")
        self.assertIsNotNone(gap)
        self.assertIn("PLUGIN_ROOT", gap)


class GeminiFragmentTests(unittest.TestCase):
    """CX-3's own instruction: emit the fragment only if the bindings
    mechanism supports it cleanly. It does (a small declarative JSON file);
    the surrounding full `gemini-extension.json` gap is documented, not
    silently promised."""

    def test_before_tool_is_registered_with_a_millisecond_timeout(self) -> None:
        with _built_project() as project:
            fragment = json.loads(
                (project / ".gemini-plugin" / "hooks-fragment.json").read_text(encoding="utf-8"))
        entry = fragment["hooks"]["BeforeTool"][0]["hooks"][0]
        self.assertEqual(entry["timeout"], 3000)

    def test_the_stdout_single_json_discipline_is_documented(self) -> None:
        with _built_project() as project:
            fragment = json.loads(
                (project / ".gemini-plugin" / "hooks-fragment.json").read_text(encoding="utf-8"))
        self.assertIn("single JSON object", fragment["_note"])


class EventAllowlistTraceabilityTests(unittest.TestCase):
    """The governing rule `godmode_host_manifests.py`'s own module docstring
    states: every emitted event name is traceable to an addendum, and the
    ALLOWLIST constant for a host is exactly the set that host's builder
    emits - never a superset (an unverified name shipped "just in case")
    and never a subset (a verified name silently dropped)."""

    def test_codex_emitted_events_equal_the_allowlist(self) -> None:
        self.assertEqual(host_manifests.codex_emitted_events(), host_manifests.CODEX_HOOK_EVENTS)

    def test_grok_emitted_events_equal_the_allowlist(self) -> None:
        manifest = host_manifests.build_grok_manifest()
        self.assertEqual(
            host_manifests.grok_emitted_events(manifest), host_manifests.GROK_HOOK_EVENTS)

    def test_cursor_emitted_events_equal_the_allowlist(self) -> None:
        manifest = host_manifests.build_cursor_manifest()
        self.assertEqual(
            host_manifests.cursor_emitted_events(manifest), host_manifests.CURSOR_HOOK_EVENTS)

    def test_gemini_emitted_events_equal_the_allowlist(self) -> None:
        fragment = host_manifests.build_gemini_fragment()
        self.assertEqual(
            host_manifests.gemini_emitted_events(fragment), host_manifests.GEMINI_HOOK_EVENTS)


class BindingsRegenerateByteStableTests(unittest.TestCase):
    def test_running_write_twice_produces_identical_bytes(self) -> None:
        with _built_project() as project:
            paths = [
                "hooks/hooks.json",
                ".codex-plugin/plugin.json",
                ".grok-plugin/hooks.json",
                ".cursor-plugin/hooks.json",
                ".gemini-plugin/hooks-fragment.json",
            ]
            before = {p: (project / p).read_bytes() for p in paths}
            result = bindings.write(project)
            self.assertEqual(result["written"], [], result)
            after = {p: (project / p).read_bytes() for p in paths}
            self.assertEqual(before, after)

    def test_check_reports_current_immediately_after_write(self) -> None:
        with _built_project() as project:
            report = bindings.check(project)
            self.assertEqual(report["verdict"], "current", report["hosts"])


class BasePluginV1Tests(unittest.TestCase):
    def test_the_shipped_root_manifest_validates(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(host_manifests.validate_plugin_v1(manifest), [])

    def test_an_invented_top_level_key_is_rejected(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        manifest["hooks"] = {"PreToolUse": []}
        self.assertEqual(host_manifests.validate_plugin_v1(manifest), ["hooks"])

    def test_a_non_object_manifest_is_rejected_not_crashed_on(self) -> None:
        self.assertEqual(host_manifests.validate_plugin_v1([1, 2, 3]), ["<not-an-object>"])

    def test_host_manifests_and_host_hook_manifests_are_discriminated(self) -> None:
        """Fix round 1 (I3, review Important): `host_manifests` mixed
        identity manifests (a `plugin.json`-shaped file) and hook manifests
        (an unrelated shape) under one key with no discriminator. Split
        into `host_manifests` (identity only) and `host_hook_manifests`
        (hooks only) - every value under `host_manifests` names a file
        this repo's own `packaging/hosts.json` identity-manifest section
        also declares a path for; every value under `host_hook_manifests`
        names one its `hook_manifests` section declares a path for."""
        manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        extension = manifest["extensions"]["ai.aiimagined.godmode"]
        identity_paths = {
            spec["path"] for spec in json.loads(
                (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8")
            )["hosts"].values()
        }
        hook_paths = {
            spec["path"] for name, spec in json.loads(
                (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8")
            )["hook_manifests"].items() if not name.startswith("_")
        }
        for host, path in extension["host_manifests"].items():
            self.assertIn(path, identity_paths, host)
        for host, path in extension["host_hook_manifests"].items():
            self.assertIn(path, hook_paths, host)
        # No path appears under both keys - the two maps track disjoint
        # artifact kinds, never the same file wearing two labels.
        self.assertEqual(
            set(extension["host_manifests"].values())
            & set(extension["host_hook_manifests"].values()),
            set(),
        )


class RegistrationReportAndInstallVerifyTests(unittest.TestCase):
    def test_status_reports_structural_registration_per_host(self) -> None:
        with _built_project() as project:
            report = bindings.registration_report(project)
        for host in ("claude", "codex", "grok", "cursor", "gemini"):
            self.assertIn(host, report)
            self.assertTrue(report[host]["manifest_present"], host)

    def test_install_verify_reports_unverifiable_for_cursor_and_gemini(self) -> None:
        with _built_project() as project:
            for host in ("cursor", "gemini"):
                result = bindings.install_verify(project, host)
                self.assertEqual(result["verdict"], "unverifiable", host)

    def test_install_verify_fails_nonzero_when_only_session_start_registers(self) -> None:
        """The exact scenario CX-3 binds: a Codex config state showing
        `session_start` registered and `pre_tool_use` absent must fail the
        verify step loudly, listing the missing hook - not pass silently."""
        with _built_project() as project:
            state = project / "fake-codex-config.toml"
            state.write_text(
                '[hooks.state."godmode@x:hooks/hooks.json:session_start:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n',
                encoding="utf-8",
            )
            result = bindings.install_verify(project, "codex", state_path=state)
        self.assertEqual(result["verdict"], "partial")
        self.assertEqual(result["missing_events"], ["pre_tool_use"])
        self.assertEqual(result["registered_events"], ["session_start"])

    def test_install_verify_passes_when_every_declared_event_registers(self) -> None:
        with _built_project() as project:
            state = project / "fake-codex-config.toml"
            state.write_text(
                '[hooks.state."godmode@x:hooks/hooks.json:session_start:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n\n'
                '[hooks.state."godmode@x:hooks/hooks.json:pre_tool_use:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n'
                "enabled = true\n",
                encoding="utf-8",
            )
            result = bindings.install_verify(project, "codex", state_path=state)
        self.assertEqual(result["verdict"], "verified")
        self.assertEqual(result["missing_events"], [])

    def test_install_verify_is_never_tricked_by_a_decoy_plugin_sharing_the_relative_path(
        self,
    ) -> None:
        """Fix round 1 (I1, review Important) - the reviewer's own live
        repro: an unrelated plugin's `hooks.state` entries, sharing the
        conventional `hooks/hooks.json` relative path but registered under
        an unrelated identifier, must never be credited to godmode's own
        registration state. Zero godmode-identified evidence in the file
        means `"unverifiable"`, never `"verified"` and never `"partial"`
        (partial would still imply real evidence about godmode specifically,
        which this decoy file contains none of)."""
        with _built_project() as project:
            state = project / "decoy-codex-config.toml"
            state.write_text(
                '[hooks.state."some-other-plugin@evil:hooks/hooks.json:session_start:0:0"]\n'
                'trusted_hash = "sha256:notgodmode1"\n\n'
                '[hooks.state."some-other-plugin@evil:hooks/hooks.json:pre_tool_use:0:0"]\n'
                'trusted_hash = "sha256:notgodmode2"\n'
                "enabled = true\n",
                encoding="utf-8",
            )
            result = bindings.install_verify(project, "codex", state_path=state)
        self.assertEqual(result["verdict"], "unverifiable", result)
        self.assertNotEqual(result["verdict"], "verified")
        self.assertNotEqual(result["verdict"], "partial")

    def test_install_verify_reports_unverifiable_when_no_state_is_readable(self) -> None:
        with _built_project() as project:
            missing = project / "does-not-exist.toml"
            result = bindings.install_verify(project, "codex", state_path=missing)
        self.assertEqual(result["verdict"], "unverifiable")

    def test_the_cli_exits_nonzero_on_partial_registration(self) -> None:
        from godmode_runtime.godmode_console import main

        with _built_project() as project:
            state = project / "fake-codex-config.toml"
            state.write_text(
                '[hooks.state."godmode@x:hooks/hooks.json:session_start:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n',
                encoding="utf-8",
            )
            exit_code = main([
                "--project", str(project), "--json", "hooks", "install",
                "--host", "codex", "--state-path", str(state),
            ])
        self.assertEqual(exit_code, 1)


class SkillsHostNeutralityTests(unittest.TestCase):
    """CX-3's skills-roster fix (Addendum 6's ROSTER GAP): no skill text may
    carry a Claude-specific directory hint, and the forge destination
    defaults host-neutrally (`.grok/skills/` only on Grok)."""

    def test_no_skill_names_a_claude_specific_directory_variable(self) -> None:
        offenders = []
        for skill_md in sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8")
            if "CLAUDE_SKILL_DIR" in text or "In Claude Code, the" in text:
                offenders.append(str(skill_md.relative_to(PLUGIN_ROOT)))
        self.assertEqual(offenders, [])

    def test_the_root_skill_names_the_full_resolution_chain(self) -> None:
        text = (PLUGIN_ROOT / "skills" / "godmode" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("GROK_PLUGIN_ROOT", text)
        self.assertIn("CLAUDE_PLUGIN_ROOT", text)

    def test_skill_forge_destination_defaults_to_dot_grok_skills_on_grok(self) -> None:
        import os
        from unittest import mock
        from godmode_runtime.godmode_console import main

        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(project / "state")}):
                main(["--project", str(project), "--json", "init"])
                with mock.patch.dict(os.environ, {"GROK_AGENT": "1"}, clear=False):
                    main([
                        "--project", str(project), "--json", "skill", "forge",
                        "--name", "test-skill",
                        "--purpose", "A purpose long enough to pass validation.",
                        "--gap-evidence", "Two observed repeated uses of this gap.",
                        "--repeated-uses", "2",
                        "--positive", "trigger one example", "--positive", "trigger two example",
                        "--negative", "near miss one example", "--negative", "near miss two example",
                        "--assertion", "an observable result",
                    ])
            self.assertTrue((project / ".grok" / "skills" / "test-skill" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
