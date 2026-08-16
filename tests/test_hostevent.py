"""CX-2: the canonical host-event adapter.

Every case here is red-first against the requirements named in
`docs/superpowers/plans/2026-08-16-codex-compat.md` (Task CX-2 + Plan
amendments 1-4) and `docs/superpowers/specs/2026-08-16-codex-compat-design.md`
(CX-2 unit + Addenda 2/6): field dual-casing, the host detection chain,
per-host tool maps, unrecognized-tool fail-closed behaviour, gate-exactly-
once, the payload-capture probe, and multi-host response rendering.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_hostevent as he  # noqa: E402


class _FakeArchive:
    """Minimal `.append` stand-in - the archive helpers here only need to
    know what was recorded, not a real hash-chained Chronicle."""

    def __init__(self, fail: bool = False) -> None:
        self.records: list[tuple] = []
        self._fail = fail

    def append(self, kind, subject, data, *, evidence=None):
        if self._fail:
            raise RuntimeError("archive unavailable")
        self.records.append((kind, subject, dict(data)))
        return {"kind": kind, "subject": subject, "data": data}


class FieldDualCasingTests(unittest.TestCase):
    def test_camel_and_snake_both_resolve(self) -> None:
        self.assertEqual(he.field({"hookEventName": "PreToolUse"}, "hook_event_name"),
                         "PreToolUse")
        self.assertEqual(he.field({"hook_event_name": "PreToolUse"}, "hook_event_name"),
                         "PreToolUse")
        self.assertEqual(he.field({"toolName": "Bash"}, "tool_name"), "Bash")
        self.assertEqual(he.field({"tool_name": "Bash"}, "tool_name"), "Bash")
        self.assertEqual(he.field({"toolInput": {"a": 1}}, "tool_input"), {"a": 1})
        self.assertEqual(he.field({"tool_input": {"a": 1}}, "tool_input"), {"a": 1})
        self.assertEqual(he.field({"sessionId": "s1"}, "session_id"), "s1")
        self.assertEqual(he.field({"session_id": "s1"}, "session_id"), "s1")
        self.assertEqual(he.field({"workspaceRoot": "/x"}, "cwd"), "/x")
        self.assertEqual(he.field({"cwd": "/x"}, "cwd"), "/x")

    def test_absent_field_is_none_not_a_raise(self) -> None:
        self.assertIsNone(he.field({}, "tool_name"))
        self.assertIsNone(he.field("not-a-dict", "tool_name"))
        self.assertIsNone(he.field(None, "tool_name"))

    def test_first_alias_present_wins(self) -> None:
        # Both casings present (a host that free-doubles a field, or a
        # malformed replay) - the lookup must not raise or pick randomly.
        self.assertEqual(
            he.field({"toolName": "A", "tool_name": "B"}, "tool_name"), "A")


class HostDetectionChainTests(unittest.TestCase):
    """GODMODE_HOST || GROK_AGENT || CLAUDE_CODE_ENTRYPOINT || payload-shape
    || "unknown" - Addendum 6's binding chain, checked in precedence order."""

    def test_godmode_host_wins_over_everything(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "custom-host",
                                           "GROK_AGENT": "1",
                                           "CLAUDE_CODE_ENTRYPOINT": "cli"}, clear=False):
            self.assertEqual(he.detect_host({}), "custom-host")

    def test_grok_agent_wins_over_claude_entrypoint(self) -> None:
        environment = dict(os.environ)
        environment.pop("GODMODE_HOST", None)
        environment["GROK_AGENT"] = "1"
        environment["CLAUDE_CODE_ENTRYPOINT"] = "cli"
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(he.detect_host({}), "grok")

    def test_claude_entrypoint_alone_resolves_claude(self) -> None:
        environment = {k: v for k, v in os.environ.items()
                       if k not in ("GODMODE_HOST", "GROK_AGENT")}
        environment["CLAUDE_CODE_ENTRYPOINT"] = "cli"
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(he.detect_host({}), "claude")

    def test_payload_shape_is_the_last_resort(self) -> None:
        environment = {k: v for k, v in os.environ.items()
                       if k not in ("GODMODE_HOST", "GROK_AGENT", "CLAUDE_CODE_ENTRYPOINT")}
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                he.detect_host({"hook_event_name": "PreToolUse", "tool_name": "Bash"}),
                "claude")
            self.assertEqual(
                he.detect_host({"hook_event_name": "PreToolUse", "tool_name": "shell_command"}),
                "codex")
            self.assertEqual(
                he.detect_host({"hookEventName": "pre_tool_use",
                                "toolName": "run_terminal_command"}),
                "grok")
            self.assertEqual(
                he.detect_host({"hook_event_name": "preToolUse"}), "cursor")
            self.assertEqual(
                he.detect_host({"hook_event_name": "BeforeTool"}), "gemini")
            self.assertEqual(he.detect_host({}), "unknown")
            self.assertEqual(he.detect_host("not-a-dict"), "unknown")


class IsPretoolEventTests(unittest.TestCase):
    def test_every_documented_dialect_is_recognised(self) -> None:
        self.assertTrue(he.is_pretool_event({"hook_event_name": "PreToolUse"}))
        self.assertTrue(he.is_pretool_event({"hookEventName": "pre_tool_use"}))
        self.assertTrue(he.is_pretool_event({"hook_event_name": "preToolUse"}))
        self.assertTrue(he.is_pretool_event({"hook_event_name": "BeforeTool"}))
        self.assertFalse(he.is_pretool_event({"hook_event_name": "SessionStart"}))
        self.assertFalse(he.is_pretool_event({}))


class ClaudeAdapterTests(unittest.TestCase):
    """Byte-identical to the pre-CX-2 hook's own `tool_operation` mapping."""

    def test_bash_powershell_carry_the_command_text(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
        })
        self.assertEqual(event.host, "claude")
        self.assertEqual(event.operation, "git push origin main")
        self.assertEqual(event.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(event.targets, [])

    def test_write_and_edit_carry_file_path_as_a_target(self) -> None:
        write = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": "src/app.py"},
        })
        self.assertEqual(write.operation, "write file src/app.py")
        self.assertEqual(write.targets, ["src/app.py"])
        self.assertEqual(write.tool_kind, he.TOOL_KIND_FENCED)

        edit = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": "src/app.py"},
        })
        self.assertEqual(edit.operation, "edit file src/app.py")
        self.assertEqual(edit.targets, ["src/app.py"])

    def test_read_tools_are_marked_read_kind(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Read",
            "tool_input": {"file_path": "README.md"},
        })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_READ)

    def test_an_unmapped_claude_tool_name_fails_closed(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "SomeFutureTool",
            "tool_input": {"x": 1},
        }, seen=set())
        # Payload-shape detection cannot place an unknown tool name under any
        # host - it stays "unknown", never guessed into "claude" just
        # because the event name looked like Claude's.
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)
        self.assertEqual(event.tool, "SomeFutureTool")
        self.assertEqual(event.operation, "")
        self.assertEqual(event.targets, [])


class CodexAdapterTests(unittest.TestCase):
    def test_shell_command_carries_the_command_text(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "shell_command",
                "tool_input": {"command": "git push --force origin main"},
            })
        self.assertEqual(event.host, "codex")
        self.assertEqual(event.operation, "git push --force origin main")
        self.assertEqual(event.tool_kind, he.TOOL_KIND_SHELL)

    def test_apply_patch_targets_carry_add_update_delete_intent(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Add File: new_module.py\n"
            "+print('hi')\n"
            "*** Update File: existing.py\n"
            "-old\n+new\n"
            "*** Delete File: obsolete.py\n"
            "*** End Patch\n"
        )
        targets = he.apply_patch_targets(patch)
        self.assertEqual(
            targets,
            [("new_module.py", "add"), ("existing.py", "update"),
             ("obsolete.py", "delete")],
        )

    def test_apply_patch_move_pairs_with_the_preceding_update(self) -> None:
        patch = (
            "*** Update File: old_name.py\n"
            "*** Move to: new_name.py\n"
            "-x\n+y\n"
        )
        targets = he.apply_patch_targets(patch)
        self.assertEqual(
            targets, [("old_name.py", "update"), ("new_name.py", "rename")])

    def test_apply_patch_event_reaches_the_scope_fence_with_every_target(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": {
                    "input": "*** Add File: a.py\n+x\n*** Delete File: b.py\n",
                },
            })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_FENCED)
        self.assertEqual(set(event.targets), {"a.py", "b.py"})
        self.assertIn("write file a.py", event.operation)
        self.assertIn("rm b.py", event.operation)

    def test_apply_patch_with_no_parseable_target_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": {"input": "not a patch"},
            })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)

    def test_functions_exec_unwraps_a_documented_nested_shape(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "functions.exec",
                "tool_input": {
                    "name": "shell_command",
                    "arguments": {"command": "rm -rf build"},
                },
            })
        self.assertEqual(event.tool, "shell_command")
        self.assertEqual(event.operation, "rm -rf build")

    def test_functions_exec_with_an_undocumented_shape_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "functions.exec",
                "tool_input": {"something": "unrecognised-wrapper-shape"},
            })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)
        self.assertEqual(event.tool, "functions.exec")


class GrokAdapterTests(unittest.TestCase):
    """Addendum 6, verbatim tool map."""

    def test_run_terminal_command_maps_to_command_text(self) -> None:
        with mock.patch.dict(os.environ, {"GROK_AGENT": "1"}, clear=False):
            event = he.parse_host_payload({
                "hookEventName": "pre_tool_use",
                "toolName": "run_terminal_command",
                "toolInput": {"command": "git push --force origin main"},
            })
        self.assertEqual(event.host, "grok")
        self.assertEqual(event.operation, "git push --force origin main")
        self.assertEqual(event.tool_kind, he.TOOL_KIND_SHELL)

    def test_write_and_search_replace_map_to_file_path(self) -> None:
        with mock.patch.dict(os.environ, {"GROK_AGENT": "1"}, clear=False):
            write = he.parse_host_payload({
                "hookEventName": "pre_tool_use", "toolName": "write",
                "toolInput": {"file_path": "notes.md"},
            })
            replace = he.parse_host_payload({
                "hookEventName": "pre_tool_use", "toolName": "search_replace",
                "toolInput": {"file_path": "notes.md"},
            })
        self.assertEqual(write.targets, ["notes.md"])
        self.assertEqual(write.tool_kind, he.TOOL_KIND_FENCED)
        self.assertEqual(replace.targets, ["notes.md"])
        self.assertEqual(replace.tool_kind, he.TOOL_KIND_FENCED)

    def test_an_unmapped_grok_tool_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"GROK_AGENT": "1"}, clear=False):
            event = he.parse_host_payload({
                "hookEventName": "pre_tool_use", "toolName": "some_other_tool",
                "toolInput": {},
            })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)


class UnrecognizedToolTests(unittest.TestCase):
    def test_preview_is_protected_and_fail_closed(self) -> None:
        preview = he.unrecognized_tool_preview("mystery_tool")
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "unrecognized-tool")
        self.assertEqual(preview["tier"], "R3")
        self.assertIn("mystery_tool", preview["impact"][0])

    def test_record_is_counts_only(self) -> None:
        archive = _FakeArchive()
        he.record_unrecognized_tool(archive, "grok", "mystery_tool")
        self.assertEqual(len(archive.records), 1)
        kind, subject, data = archive.records[0]
        self.assertEqual(kind, "refusal")
        self.assertEqual(subject, "unrecognized-tool")
        self.assertEqual(data, {"host": "grok", "tool": "mystery_tool",
                                "category": "unrecognized-tool", "tier": "R3"})

    def test_a_recording_failure_never_raises(self) -> None:
        archive = _FakeArchive(fail=True)
        he.record_unrecognized_tool(archive, "grok", "mystery_tool")  # must not raise


class GateExactlyOnceTests(unittest.TestCase):
    def test_a_repeated_request_id_is_marked_duplicate_not_reclassified(self) -> None:
        seen: set[str] = set()
        payload = {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"}, "requestId": "req-1",
        }
        first = he.parse_host_payload(payload, seen=seen)
        second = he.parse_host_payload(payload, seen=seen)
        self.assertEqual(first.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(second.tool_kind, he.TOOL_KIND_DUPLICATE)

    def test_no_seen_set_means_no_dedup_at_all(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"}, "requestId": "req-1",
        }
        first = he.parse_host_payload(payload)
        second = he.parse_host_payload(payload)
        self.assertEqual(first.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(second.tool_kind, he.TOOL_KIND_SHELL)

    def test_dedup_is_scoped_to_the_caller_owned_set_not_global_state(self) -> None:
        """Two independent `seen` sets (as two separate hook process
        invocations would each have) never see each other's request ids."""
        payload = {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"}, "requestId": "req-shared",
        }
        seen_a: set[str] = set()
        seen_b: set[str] = set()
        first = he.parse_host_payload(payload, seen=seen_a)
        second = he.parse_host_payload(payload, seen=seen_b)
        self.assertEqual(first.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(second.tool_kind, he.TOOL_KIND_SHELL)

    def test_a_blank_request_id_is_never_deduplicated(self) -> None:
        seen: set[str] = set()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": "git status"}}
        first = he.parse_host_payload(payload, seen=seen)
        second = he.parse_host_payload(payload, seen=seen)
        self.assertEqual(first.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(second.tool_kind, he.TOOL_KIND_SHELL)


class PayloadCaptureProbeTests(unittest.TestCase):
    def test_captures_only_names_and_hashes_never_values(self) -> None:
        archive = _FakeArchive()
        raw = {
            "hook_event_name": "PreToolUse", "tool_name": "mystery_tool",
            "tool_input": {"secret_field": "super-secret-value", "another": 1},
            "cwd": "/home/operator/private-project",
            "requestId": "req-abc123",
        }
        event = he.parse_host_payload(raw)
        he.capture_payload_probe(archive, raw, event)
        self.assertEqual(len(archive.records), 1)
        _kind, _subject, data = archive.records[0]
        self.assertEqual(data["field_names"], ["another", "secret_field"])
        joined = " ".join(str(v) for v in data.values())
        self.assertNotIn("super-secret-value", joined)
        self.assertNotIn("private-project", joined)
        self.assertNotIn("req-abc123", joined)
        self.assertNotEqual(data["request_id_hash"], "")
        self.assertNotEqual(data["cwd_hash"], "")

    def test_a_capture_failure_never_raises(self) -> None:
        archive = _FakeArchive(fail=True)
        event = he.parse_host_payload({"tool_name": "x", "tool_input": {}})
        he.capture_payload_probe(archive, {"tool_input": {}}, event)  # must not raise


class RenderDecisionTests(unittest.TestCase):
    def test_allow_is_silent_on_every_host(self) -> None:
        for host in ("claude", "codex", "grok", "cursor", "gemini", "unknown"):
            body, code = he.render_decision(host, "PreToolUse", "allow", "n/a")
            self.assertEqual(body, {})
            self.assertEqual(code, 0)

    def test_exit_code_is_never_three(self) -> None:
        for host in ("claude", "codex", "grok", "cursor", "gemini", "unknown"):
            for decision in ("allow", "ask", "deny"):
                _body, code = he.render_decision(host, "PreToolUse", decision, "why")
                self.assertNotEqual(code, 3)

    def test_claude_and_cursor_keep_ask_as_ask(self) -> None:
        for host in ("claude", "cursor"):
            body, _code = he.render_decision(host, "PreToolUse", "ask", "why")
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "ask")
            self.assertEqual(body["permission"], "ask")

    def test_hosts_without_ask_receive_deny_naming_the_staged_remedy_style(self) -> None:
        # render_decision itself only folds the DECISION, not the reason text
        # (the hook constructs the deny-shaped reason before calling in) -
        # this asserts the fold, and that the caller's reason travels intact.
        reason = ('refused: unclassified-mutation (R3). stage a capability: '
                  '`godmode authorize stage --operation "..."`')
        for host in ("grok", "codex", "gemini", "unknown"):
            body, _code = he.render_decision(host, "PreToolUse", "ask", reason)
            self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertEqual(body["decision"], "deny")
            self.assertEqual(body["reason"], reason)

    def test_the_response_body_carries_every_hosts_key_at_once(self) -> None:
        """Addendum 6's DUAL-OUTPUT requirement, generalised: a host reads
        only its own key and ignores the rest, so shipping every documented
        dialect's key in one object is always safe."""
        body, _code = he.render_decision("grok", "PreToolUse", "deny", "why")
        for key in ("hookSpecificOutput", "decision", "reason", "permission",
                    "user_message", "agent_message"):
            self.assertIn(key, body)


class BareOperationTests(unittest.TestCase):
    """The host-neutral `{"operation": "..."}` shape - CX-1's probe path and
    the CLI/test-harness convention, unchanged by CX-2."""

    def test_a_bare_operation_string_is_carried_through_untouched(self) -> None:
        event = he.parse_host_payload({"operation": "git status"})
        self.assertEqual(event.tool, "")
        self.assertEqual(event.operation, "git status")
        self.assertIsNone(event.tool_kind)

    def test_a_bare_operation_is_never_treated_as_unrecognized(self) -> None:
        event = he.parse_host_payload({"operation": "godmode-probe:abc123"})
        self.assertNotEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)


class ActorFieldTests(unittest.TestCase):
    def test_actor_is_carried_through_when_the_host_supplies_one(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"}, "agentId": "sub-1",
        })
        self.assertEqual(event.actor, "sub-1")

    def test_actor_is_none_when_absent(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        })
        self.assertIsNone(event.actor)


if __name__ == "__main__":
    unittest.main()
