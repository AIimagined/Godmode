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
        # Sprint 4: Codex fires the SHARED CamelCase block (captured live),
        # resolving ${CLAUDE_PLUGIN_ROOT} as the documented legacy alias for
        # ${PLUGIN_ROOT}. There are no Codex-only keys left to check - the
        # snake_case pair named events Codex cannot fire and is retired.
        events = list(manifest["hooks"])
        self.assertNotIn("session_start", events)
        self.assertNotIn("pre_tool_use", events)

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
        # Codex's tools now ride the CamelCase PreToolUse matcher, which is
        # the event Codex actually fires. `apply_patch` living only under the
        # retired snake_case key is what left Codex file edits ungated.
        matcher = [b["matcher"] for b in manifest["hooks"]["PreToolUse"]
                   if "matcher" in b][0]
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


# ---------------------------------------------------------------------------
# SEC-B item 2: the Codex hook-DISCOVERY contract.
# ---------------------------------------------------------------------------

# Codex CLI 0.147.0 ships its own plugin-authoring reference INSIDE the
# binary: `plugin-creator/references/plugin-json-spec.md`. Every quoted line
# below is copied from that embedded document, never paraphrased, and never
# from a third-party summary:
#
#   "- `hooks` (`string`): Hook config path."
#   "- Path values should be relative and begin with `./`."
#   "  - Keep file paths relative to plugin root."
#   "- `skills`, `hooks`, and string-valued `mcpServers` are supplemented on
#      top of default component discovery; they do not replace defaults."
#
# The loader's own default hooks path is the literal `hooks/hooks.json`
# (adjacent to the source label `plugin.json#hooks[` in
# `core-plugins/src/loader.rs`), corroborated by this machine's live
# `~/.codex/config.toml` `[hooks.state]` table, whose only godmode entry is
# keyed `godmode@aiimagined:hooks/hooks.json:SessionStart:0:0`.
#
# `hooks` is DELIBERATELY not pinned present-or-absent here. The same
# embedded document contradicts itself about it - its "Plugin validation
# notes" say "Validation rejects unsupported manifest fields such as
# `hooks`, so the scaffold keeps them out of generated manifests", of a
# validator it describes as mirroring "the workspace plugin ingestion
# schema" - so whether declaring the key is safe is exactly the question
# only a live Codex plugin panel can settle (Sprint 4). What IS pinned is
# every part of the contract the document states without contradicting
# itself, so that the answer, whichever way it lands, cannot be reached by
# a manifest that was malformed on some OTHER axis.
# Sprint 4: superseded by OpenAI's PUBLISHED hooks reference (fetched
# 2026-08-19), which lists the events verbatim and entirely in CamelCase.
# The snake_case set this previously held was inferred when the list was
# unpublished; it is kept below only as the retired spelling map.
CODEX_DOCUMENTED_HOOK_EVENTS = frozenset({
    "SessionStart", "SessionEnd", "SubagentStart", "SubagentStop",
    "PreToolUse", "PermissionRequest", "PostToolUse", "PreCompact",
    "PostCompact", "UserPromptSubmit", "Stop",
})

# The CamelCase spelling of each event above, as the host's own hook
# vocabulary carries it. Both spellings exist in the host; whether the two
# COLLIDE when they appear as sibling keys in one hooks.json is the open
# question `CodexHookCasingTripwireTests` below records rather than answers.
CODEX_CAMEL_TO_SNAKE = {
    "PreToolUse": "pre_tool_use",
    "PermissionRequest": "permission_request",
    "PostToolUse": "post_tool_use",
    "PreCompact": "pre_compact",
    "PostCompact": "post_compact",
    "SessionStart": "session_start",
    "SessionEnd": "session_end",
    "UserPromptSubmit": "user_prompt_submit",
    "SubagentStart": "subagent_start",
    "SubagentStop": "subagent_stop",
    "Stop": "stop",
}

CODEX_DEFAULT_HOOKS_PATH = "hooks/hooks.json"


def _hosts_json() -> dict:
    return json.loads((PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8"))


class CodexHookDiscoveryContractTests(unittest.TestCase):
    """SEC-B item 2. Pins every part of Codex's documented plugin-manifest
    hooks contract that the host's own embedded reference states WITHOUT
    self-contradiction, so the one genuinely open question (declare the key
    or not) is the only thing a live panel has to answer.
    """

    def _codex_manifest(self) -> dict:
        return json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

    def test_a_declared_hooks_key_is_a_dot_slash_relative_string(self) -> None:
        """"- `hooks` (`string`): Hook config path." + "Path values should be
        relative and begin with `./`." - so if the key is declared at all,
        an object, an array, an absolute path, or a bare relative path is
        off-contract regardless of how the open question lands."""
        manifest = self._codex_manifest()
        if "hooks" not in manifest:
            self.skipTest("no hooks key declared - nothing to constrain")
        declared = manifest["hooks"]
        self.assertIsInstance(declared, str)
        self.assertTrue(declared.startswith("./"), declared)
        self.assertNotIn("..", declared)
        self.assertNotIn("\\", declared)

    def test_a_declared_hooks_key_resolves_to_a_file_that_actually_exists(self) -> None:
        """"Keep file paths relative to plugin root." A manifest pointing at
        a path that does not exist under the plugin root is the failure mode
        that produces exactly the observed symptom (a hooks component that
        loads nothing) whatever the key's validity turns out to be."""
        manifest = self._codex_manifest()
        if "hooks" not in manifest:
            self.skipTest("no hooks key declared - nothing to resolve")
        declared = str(manifest["hooks"])
        target = PLUGIN_ROOT / declared.removeprefix("./")
        self.assertTrue(target.is_file(), f"{declared} -> {target}")

    def test_a_declared_hooks_key_names_the_file_default_discovery_already_finds(self) -> None:
        """"`skills`, `hooks`... are supplemented on top of default component
        discovery; they do not replace defaults." A declared path that names
        a DIFFERENT file from the one the generator writes (and the loader
        default-discovers) would make the plugin ship two disagreeing hook
        representations at once - the condition the host's own hook engine
        warns about ("loading hooks from both ... prefer a single
        representation for this layer")."""
        manifest = self._codex_manifest()
        if "hooks" not in manifest:
            self.skipTest("no hooks key declared - nothing to compare")
        generated = _hosts_json()["hook_manifests"]["codex"]["path"]
        self.assertEqual(generated, CODEX_DEFAULT_HOOKS_PATH)
        self.assertEqual(manifest["hooks"], "./" + generated)

    def test_the_gate_is_discoverable_at_the_default_path_with_or_without_the_key(self) -> None:
        """The invariant that survives either answer: the file the loader
        default-discovers exists, parses, and carries godmode's Codex event
        keys. If the manifest key is ever removed, nothing is lost; if it
        stays, it points here."""
        default_file = PLUGIN_ROOT / CODEX_DEFAULT_HOOKS_PATH
        self.assertTrue(default_file.is_file())
        events = json.loads(default_file.read_text(encoding="utf-8"))["hooks"]
        for event in host_manifests.CODEX_HOOK_EVENTS:
            self.assertIn(event, events)

    def test_every_codex_event_this_repo_emits_is_in_the_hosts_own_vocabulary(self) -> None:
        """The host's hook-event enum is a closed set. An event name outside
        it is a name the host cannot register, however the manifest declares
        the file it lives in."""
        self.assertLessEqual(
            set(host_manifests.CODEX_HOOK_EVENTS), CODEX_DOCUMENTED_HOOK_EVENTS)

    def test_the_sibling_hosts_that_load_by_convention_declare_no_hooks_key(self) -> None:
        """The convention Codex's entry diverged from, and the recorded
        reason for it, both stay readable. `packaging/hosts.json` has carried
        the note since 2026-08-06 (commit 6d8d5e5), ten days before CX-3
        added the key for Codex - deleting the note to make the divergence
        look uncontested is exactly what this pins against."""
        hosts = _hosts_json()["hosts"]
        for host in ("claude", "grok"):
            self.assertNotIn("hooks", hosts[host]["fields"], host)
            self.assertNotIn("hooks", hosts[host].get("extra", {}), host)
        self.assertIn("duplicate-load", hosts["claude"]["note"])
        for name, path in (("claude", "plugin.json"),
                           ("grok", ".grok-plugin/plugin.json")):
            manifest = json.loads((PLUGIN_ROOT / path).read_text(encoding="utf-8"))
            self.assertNotIn("hooks", manifest, name)


class CodexHookCasingTripwireTests(unittest.TestCase):
    """SEC-B item 2, the OTHER candidate cause of the same field report, and
    the reason this task shipped no manifest change.

    CX-3 (commit 98c34db) changed two files in one commit: it added the
    `hooks` key to `.codex-plugin/plugin.json` AND added the snake_case
    `session_start`/`pre_tool_use` keys to the shared `hooks/hooks.json`,
    which already carried CamelCase `SessionStart`/`PreToolUse`. The
    operator observed three hooks in the Codex panel before that commit and
    none after - a count consistent with EITHER change, because the panel
    was only read once, after both.

    That the panel showed three CamelCase-only hooks BEFORE proves the host
    accepts CamelCase config keys. If it normalizes them to its snake_case
    event enum, the post-CX-3 file declares two events twice, and a
    duplicate key is a whole-file parse failure - which lands on exactly
    zero hooks, not two.

    These tests do not claim that is the cause. They RECORD the exact
    condition, so that (a) it cannot change without someone reading this,
    and (b) Sprint 4's live panel observation has a named state to compare
    against. The settling observation is stated in
    `.superpowers/sdd/2026-08-16-cx/task-secB-report.md`.
    """

    def _shared_events(self) -> list[str]:
        return list(json.loads(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"])

    def test_the_double_casing_condition_is_retired(self) -> None:
        """SETTLED by Sprint 4, which is what this tripwire was recording
        the condition FOR.

        Two independent results, both live: OpenAI's published hooks
        reference lists every Codex event in CamelCase and contains no
        snake_case spelling at all, and a `codex exec` session captured the
        hook firing with `hook_event_name: "PreToolUse"` - the CamelCase
        block, resolving `${CLAUDE_PLUGIN_ROOT}` as the documented legacy
        alias.

        The duplicate-key parse-failure hypothesis this class recorded is
        therefore REFUTED, not confirmed: the file parsed and the hook ran
        the whole time. The snake_case keys named events Codex cannot fire,
        which is what left the orphan trust row (a `trusted_hash` with no
        `enabled`) in the operator's config - and, far worse, left
        `apply_patch` matched only under a key that never fires, so Codex
        file edits reached no boundary at all.
        """
        events = self._shared_events()
        collisions = sorted(
            {CODEX_CAMEL_TO_SNAKE[key] for key in events
             if key in CODEX_CAMEL_TO_SNAKE
             and CODEX_CAMEL_TO_SNAKE[key] in events})
        self.assertEqual(collisions, [])
        self.assertEqual(
            [k for k in events if k in CODEX_CAMEL_TO_SNAKE.values()], [])

    def test_the_camelcase_keys_that_predate_cx3_are_still_present(self) -> None:
        events = self._shared_events()
        for key in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
            self.assertIn(key, events)

    def test_no_event_key_is_outside_either_documented_casing(self) -> None:
        """Whatever the collision question turns out to be, no third spelling
        is allowed to appear in this file unnoticed."""
        for key in self._shared_events():
            self.assertTrue(
                key in CODEX_DOCUMENTED_HOOK_EVENTS or key in CODEX_CAMEL_TO_SNAKE,
                key)


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
                '[hooks.state."godmode@x:hooks/hooks.json:SessionStart:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n',
                encoding="utf-8",
            )
            result = bindings.install_verify(project, "codex", state_path=state)
        self.assertEqual(result["verdict"], "partial")
        self.assertEqual(result["missing_events"], ["PreToolUse", "UserPromptSubmit"])
        self.assertEqual(result["registered_events"], ["SessionStart"])

    def test_install_verify_passes_when_every_declared_event_registers(self) -> None:
        with _built_project() as project:
            state = project / "fake-codex-config.toml"
            # All three CamelCase events Codex actually fires (Sprint 4:
            # the snake_case pair is retired), each trusted AND enabled.
            state.write_text(
                '[hooks.state."godmode@x:hooks/hooks.json:SessionStart:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n'
                "enabled = true\n\n"
                '[hooks.state."godmode@x:hooks/hooks.json:PreToolUse:0:0"]\n'
                'trusted_hash = "sha256:deadbeef"\n'
                "enabled = true\n\n"
                '[hooks.state."godmode@x:hooks/hooks.json:UserPromptSubmit:0:0"]\n'
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
                '[hooks.state."some-other-plugin@evil:hooks/hooks.json:SessionStart:0:0"]\n'
                'trusted_hash = "sha256:notgodmode1"\n\n'
                '[hooks.state."some-other-plugin@evil:hooks/hooks.json:PreToolUse:0:0"]\n'
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
                '[hooks.state."godmode@x:hooks/hooks.json:SessionStart:0:0"]\n'
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


class EveryShippedMatcherResolvesInItsAdapter(unittest.TestCase):
    """Sprint 4's generalisation: a manifest and an adapter are two
    authorities over one list of tool names, and nothing compared them.

    Found the expensive way on Grok - `.grok-plugin/hooks.json` subscribed
    PreToolUse to nine names while `_adapt_grok` implemented three, so six
    of the names godmode's OWN manifest asked the host to send came back
    `unrecognized-tool`. Enforcement held (they were denied), but no
    interception proof could ever be written for a tool the adapter could
    not name, and `hooks probe --host grok` reported UNAVAILABLE
    indefinitely.

    This walks EVERY shipped manifest instead of that one, so the same
    class cannot hide on a host nobody has probed yet. It is static by
    design: it needs no host installed, which is the point - Cursor is not
    installed on the machine this was written on, and the identical defect
    was sitting in its manifest (`Shell|Write|Delete`, of which only
    `Write` resolved).

    A regex-wildcard matcher (Cursor's `beforeShellExecution: .*`, which
    matches on COMMAND TEXT rather than tool name - Addendum 5) is skipped:
    it names no tools to check.
    """

    # manifest path -> (host label for detection, event keys to check)
    # `hooks/hooks.json` is the SHARED file: Claude and Codex both read the
    # same CamelCase block (Sprint 4 captured Codex firing it), so its
    # matcher is a union and a name need only resolve for ONE of its
    # readers - `apply_patch` is Codex's, `NotebookEdit` is Claude's.
    MANIFESTS = (
        (Path("hooks/hooks.json"), ("claude", "codex"), ("PreToolUse",)),
        (Path(".grok-plugin/hooks.json"), ("grok",), ("PreToolUse",)),
        (Path(".cursor-plugin/hooks.json"), ("cursor",), ("preToolUse",)),
    )

    # A representative payload per tool-input shape. Only the SHAPE matters:
    # the adapter is being asked "do you know this name", not "is this
    # command dangerous".
    _SHELLISH = {"command": "ls"}
    _PATHISH = {"file_path": "a.txt"}
    _PATCHISH = {"command": "*** Add File: a.txt\n+x\n"}

    # `functions.exec` is Codex's ORCHESTRATION WRAPPER, not a tool: it only
    # resolves when it carries a nested `{"function": {"name", "arguments"}}`
    # call, and failing closed on any other shape is its documented, correct
    # behaviour (Plan amendment 2). It gets a real wrapper here so the guard
    # tests recognition, not the wrapper's own fail-closed.
    _WRAPPED = {"function": {"name": "shell_command",
                             "arguments": {"command": "ls"}}}

    def _payload_for(self, name: str) -> dict:
        lowered = name.lower()
        if name == "functions.exec":
            return self._WRAPPED
        if "patch" in lowered:
            return self._PATCHISH
        if any(k in lowered for k in ("write", "edit", "delete", "read", "replace")):
            return self._PATHISH
        return self._SHELLISH

    def test_no_manifest_subscribes_to_a_name_its_adapter_rejects(self) -> None:
        import os
        from unittest import mock

        from godmode_runtime import godmode_hostevent as he

        unresolved: list[str] = []
        for relative, hosts, events in self.MANIFESTS:
            manifest = json.loads(
                (PLUGIN_ROOT / relative).read_text(encoding="utf-8"))
            for event in events:
                for block in manifest.get("hooks", {}).get(event, []):
                    matcher = block.get("matcher")
                    if not matcher or matcher == ".*":
                        continue
                    for name in (n for n in matcher.split("|") if n):
                        resolved_by = []
                        for host in hosts:
                            with mock.patch.dict(os.environ,
                                                 {"GODMODE_HOST": host},
                                                 clear=False):
                                os.environ.pop("GROK_AGENT", None)
                                os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)
                                parsed = he.parse_host_payload({
                                    "hook_event_name": event,
                                    "tool_name": name,
                                    "tool_input": self._payload_for(name),
                                })
                            if parsed.tool_kind != he.TOOL_KIND_UNRECOGNIZED:
                                resolved_by.append(host)
                        if not resolved_by:
                            unresolved.append(
                                f"{relative.as_posix()}:{'/'.join(hosts)}:{name}")
        self.assertEqual(unresolved, [], "a shipped manifest subscribes the "
                         "host to tool names its own adapter answers with "
                         "unrecognized-tool")


if __name__ == "__main__":
    unittest.main()


class CodexEventNamesMatchTheirPublishedList(unittest.TestCase):
    """Sprint 4: the snake_case Codex keys are not Codex event names, and
    Codex's own file-editing tool was never gated.

    `godmode_host_manifests` chose `session_start`/`pre_tool_use` on
    honestly-stated evidence - its own comment records that the build doc
    said the event list was NOT published, so an audit observation of those
    two spellings was preferred over the doc's lone CamelCase example.

    That evidence is now superseded from both directions. OpenAI publishes
    the full list, and every name in it is CamelCase: SessionStart,
    SessionEnd, SubagentStart, SubagentStop, PreToolUse, PermissionRequest,
    PostToolUse, PreCompact, PostCompact, UserPromptSubmit, Stop. And a
    live `codex exec` session captured the hook firing with
    `hook_event_name: "PreToolUse"` - the CamelCase block - while the
    snake_case entry produced only an orphan trust row in the operator's
    `~/.codex/config.toml` carrying a `trusted_hash` and no `enabled`,
    because it names an event Codex cannot enable.

    The second half is the one that mattered: `apply_patch` - documented as
    Codex's file-edit tool - was listed ONLY under the invalid
    `pre_tool_use` key, so the valid `PreToolUse` matcher never covered it.
    Proven live: a `codex exec` run created a file through `apply_patch`
    and wrote ZERO archive records. Unlike every other Sprint 4 finding,
    which failed CLOSED, this one was a fail-open by omission - the tool
    Codex edits files with reached no boundary at all.
    """

    # Verbatim from OpenAI's published hooks reference (fetched 2026-08-19).
    OFFICIAL_CODEX_EVENTS = frozenset({
        "SessionStart", "SessionEnd", "SubagentStart", "SubagentStop",
        "PreToolUse", "PermissionRequest", "PostToolUse", "PreCompact",
        "PostCompact", "UserPromptSubmit", "Stop",
    })

    def test_no_shipped_event_key_is_absent_from_the_published_list(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        unpublished = sorted(k for k in manifest["hooks"]
                             if k not in self.OFFICIAL_CODEX_EVENTS)
        self.assertEqual(unpublished, [], "hooks.json declares event names "
                         "that appear nowhere in Codex's published list")

    def test_codexs_file_edit_tool_is_covered_by_a_valid_event(self) -> None:
        """`apply_patch` must be matched under an event Codex actually
        fires - being listed under an unpublished key gates nothing."""
        manifest = json.loads(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        covered = False
        for event, blocks in manifest["hooks"].items():
            if event not in self.OFFICIAL_CODEX_EVENTS:
                continue
            for block in blocks:
                if "apply_patch" in (block.get("matcher") or "").split("|"):
                    covered = True
        self.assertTrue(covered, "apply_patch - Codex's documented file-edit "
                        "tool - is matched by no valid event, so Codex file "
                        "edits reach no boundary")


if __name__ == "__main__":
    unittest.main()


class GeminiDocumentedToolsResolve(unittest.TestCase):
    """Sprint 4: the Gemini fragment subscribes EVERY tool and the adapter
    knew none of them.

    `.gemini-plugin/hooks-fragment.json` matches `BeforeTool` with `.*`, so
    a wildcard cannot be enumerated the way the other manifests' matchers
    can - the drift guard above has nothing to read. The check instead
    pins Gemini's DOCUMENTED tool names (published hooks reference and
    hooks guide, fetched 2026-08-19), which is what the wildcard actually
    delivers: `run_shell_command`, `read_file`, `write_file`, `replace`.

    Before this, Gemini routed through the generic adapter, whose map holds
    only Claude's names, so every Gemini tool call - `run_shell_command`
    included - arrived as `unrecognized-tool`.
    """

    DOCUMENTED = {
        "run_shell_command": {"command": "ls"},
        "read_file": {"absolute_path": "/x/a.txt"},
        "write_file": {"absolute_path": "/x/a.txt"},
        "replace": {"file_path": "a.txt"},
    }

    def _parse(self, tool: str, tool_input: dict):
        import os
        from unittest import mock
        from godmode_runtime import godmode_hostevent as he
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "gemini"}, clear=False):
            os.environ.pop("GROK_AGENT", None)
            os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)
            return he, he.parse_host_payload({
                "hook_event_name": "BeforeTool", "tool_name": tool,
                "tool_input": tool_input})

    def test_every_documented_gemini_tool_resolves(self) -> None:
        unresolved = []
        for tool, payload in self.DOCUMENTED.items():
            he, parsed = self._parse(tool, payload)
            if parsed.tool_kind == he.TOOL_KIND_UNRECOGNIZED:
                unresolved.append(tool)
        self.assertEqual(unresolved, [])

    def test_the_shell_tool_carries_its_command_text(self) -> None:
        _he, parsed = self._parse("run_shell_command",
                                  {"command": "git push --force origin main"})
        self.assertEqual(parsed.operation, "git push --force origin main")

    def test_an_undocumented_gemini_tool_still_fails_closed(self) -> None:
        he, parsed = self._parse("mcp_someserver_sometool", {"x": 1})
        self.assertEqual(parsed.tool_kind, he.TOOL_KIND_UNRECOGNIZED)

    def test_the_fragment_only_declares_published_gemini_events(self) -> None:
        """Published Gemini CLI event list, verbatim."""
        published = {
            "BeforeTool", "AfterTool", "BeforeAgent", "AfterAgent",
            "BeforeModel", "BeforeToolSelection", "AfterModel",
            "SessionStart", "SessionEnd", "Notification", "PreCompress",
        }
        fragment = json.loads(
            (PLUGIN_ROOT / ".gemini-plugin" / "hooks-fragment.json").read_text(
                encoding="utf-8"))
        unpublished = sorted(k for k in fragment["hooks"] if k not in published)
        self.assertEqual(unpublished, [])


if __name__ == "__main__":
    unittest.main()
