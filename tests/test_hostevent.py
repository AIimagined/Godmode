"""CX-2: the canonical host-event adapter.

Every case here is red-first against the requirements named in
`docs/superpowers/plans/2026-08-16-codex-compat.md` (Task CX-2 + Plan
amendments 1-4) and `docs/superpowers/specs/2026-08-16-codex-compat-design.md`
(CX-2 unit + Addenda 2/6): field dual-casing, the host detection chain,
per-host tool maps, unrecognized-tool fail-closed behaviour, the
payload-capture probe, and multi-host response rendering.

**Fix round 1** (`.superpowers/sdd/2026-08-16-cx/task-cx2-review.md`) added:
`ApplyPatchMalformedDirectiveTests` (C1 - a patch mixing one well-formed
directive with one malformed one must fail the WHOLE call closed, never
just drop the malformed one), `NoDedupTests` (C2/I1 - gate-exactly-once was
removed entirely; replaces the deleted `GateExactlyOnceTests`),
`FirstAliasWinsTests` (I3 - camelCase-over-snake_case is a pinned, tested
security property), and `EmptyToolNameTests` (M2 - a present-but-empty
`tool_name` is `unrecognized-tool`, not the bare-operation path).
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
        })
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


class ApplyPatchMalformedDirectiveTests(unittest.TestCase):
    """Fix round 1, C1 (review Critical): a patch mixing one well-formed
    directive with one malformed/indented one must fail the WHOLE call
    closed - partial recognition is never allowed to shrink the target set.

    Fix round 2 (re-review adversarial extension) widened the detector
    itself: two smuggling vectors used to defeat round 1's lookalike regex
    outright - a Unicode zero-width character breaking the literal `***`
    run, and a directive keyword with no trailing colon - both read as
    ordinary content (not a recognised target, not flagged malformed) and
    were silently dropped while the call proceeded on whatever DID parse.
    `UnicodeAndColonlessDirectiveTests` below is the reviewer's own
    adversarial repro, plus the additional Cf characters and the negative
    markdown control the round-2 order named explicitly.
    """

    def test_has_malformed_directive_detects_the_reviewers_exact_repro(self) -> None:
        patch = "*** Add File: harmless.txt\n+hello\n  *** Add File: /etc/passwd\n+pwned\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_a_tab_prefixed_directive_is_detected(self) -> None:
        patch = "*** Add File: harmless.txt\n+hello\n\t*** Delete File: secret.env\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_a_doubled_space_directive_is_detected(self) -> None:
        patch = "***  Add File:  harmless.txt\n+hello\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_the_malformed_line_first_is_still_caught_mixed_order(self) -> None:
        # Order-independence: the malformed line does not have to come
        # after the well-formed one to be caught.
        patch = "  *** Add File: /etc/passwd\n+pwned\n*** Delete File: harmless.txt\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_a_fully_well_formed_patch_is_never_flagged(self) -> None:
        patch = "*** Add File: a.py\n+x\n*** Delete File: b.py\n"
        self.assertFalse(he.has_malformed_directive(patch))

    def test_ordinary_diff_content_never_trips_the_lookalike(self) -> None:
        patch = ("*** Begin Patch\n*** Add File: a.py\n"
                 "+# adds a File: marker in a comment, not a directive\n"
                 "*** End Patch\n")
        self.assertFalse(he.has_malformed_directive(patch))

    def test_the_adapter_fails_the_whole_call_closed_never_the_benign_target_alone(self) -> None:
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": {
                    "input": ("*** Add File: harmless.txt\n+hello\n"
                              "  *** Add File: /etc/passwd\n+pwned\n"),
                },
            })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_MALFORMED)
        self.assertEqual(event.targets, [])
        self.assertEqual(event.operation, "")
        # The reviewer's exact regression: harmless.txt must NOT reach the
        # fence alone while /etc/passwd is silently dropped.
        self.assertNotIn("harmless.txt", str(event.targets))

    def test_malformed_preview_names_the_real_cause_not_unmapped_tool(self) -> None:
        preview = he.malformed_apply_patch_preview("apply_patch")
        self.assertTrue(preview["protected"])
        self.assertEqual(preview["category"], "apply-patch-malformed-directive")
        self.assertTrue(preview["_chronicled_miss"])

    def test_malformed_record_is_counts_only(self) -> None:
        archive = _FakeArchive()
        he.record_malformed_apply_patch(archive, "codex", "apply_patch")
        self.assertEqual(len(archive.records), 1)
        kind, subject, data = archive.records[0]
        self.assertEqual(kind, "refusal")
        self.assertEqual(subject, "apply-patch-malformed-directive")
        self.assertEqual(data["host"], "codex")


class ApplyPatchCommandBodyFieldTests(unittest.TestCase):
    """SEC-B item 1: the real Codex `apply_patch` call delivers its patch
    body in a field named `command`, which `_PATCH_BODY_FIELDS` did not
    list - so every such call parsed an EMPTY body, found no target, and
    fell out as `unrecognized-tool`. Fail-closed (the call was refused, not
    allowed), but structurally the scope fence never saw a single one of the
    paths the patch names, and the malformed-directive detector never saw a
    single line of the body it was written to inspect.

    `command` is tried FIRST, ahead of `input`/`patch`/`content`. The
    precedence is a security decision, not a style one, and it is the same
    one `_ALIASES` already makes for dual-cased payload fields (see
    `FirstAliasWinsTests`): when a payload carries the body under two names
    with different contents, the one the REAL host executes must be the one
    the fence reads. Reading the other would let a caller fence a benign
    patch under `input` while the host applies a different one from
    `command`. `_SHELL_COMMAND_FIELDS` already spells the same host's shell
    body `command` alone, so this also makes the two Codex tools agree.
    """

    ADD_AND_DELETE = "*** Add File: a.py\n+x\n*** Delete File: b.py\n"

    def _codex_apply_patch(self, tool_input: dict) -> "he.HostEvent":
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            return he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                "tool_input": tool_input,
            })

    def test_command_is_a_recognised_patch_body_field(self) -> None:
        self.assertIn("command", he._PATCH_BODY_FIELDS)

    def test_a_command_bodied_patch_reaches_the_fence_with_every_target(self) -> None:
        event = self._codex_apply_patch({"command": self.ADD_AND_DELETE})
        self.assertEqual(event.tool_kind, he.TOOL_KIND_FENCED)
        self.assertEqual(set(event.targets), {"a.py", "b.py"})
        self.assertIn("write file a.py", event.operation)
        self.assertIn("rm b.py", event.operation)

    def test_every_target_of_a_multi_target_command_body_reaches_the_fence(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Add File: new_module.py\n"
            "+print('hi')\n"
            "*** Update File: existing.py\n"
            "-old\n+new\n"
            "*** Move to: renamed.py\n"
            "*** Delete File: obsolete.py\n"
            "*** End Patch\n"
        )
        event = self._codex_apply_patch({"command": patch})
        self.assertEqual(
            event.targets,
            ["new_module.py", "existing.py", "renamed.py", "obsolete.py"],
        )

    def test_a_malformed_command_body_fails_the_whole_call_closed(self) -> None:
        # The C1 regression, re-run through the field the real host uses:
        # harmless.txt must NOT reach the fence alone while the indented
        # /etc/passwd directive is silently dropped.
        event = self._codex_apply_patch({
            "command": ("*** Add File: harmless.txt\n+hello\n"
                        "  *** Add File: /etc/passwd\n+pwned\n"),
        })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_MALFORMED)
        self.assertEqual(event.targets, [])
        self.assertEqual(event.operation, "")

    def test_a_command_body_with_no_parseable_target_still_fails_closed(self) -> None:
        event = self._codex_apply_patch({"command": "not a patch"})
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)

    def test_command_wins_over_input_when_both_carry_a_body(self) -> None:
        # Confusable-body pin: the fence must read what the host executes.
        event = self._codex_apply_patch({
            "command": "*** Add File: real.py\n+x\n",
            "input": "*** Add File: decoy.py\n+x\n",
        })
        self.assertEqual(event.targets, ["real.py"])

    def test_command_wins_over_every_other_body_field(self) -> None:
        event = self._codex_apply_patch({
            "content": "*** Add File: decoy_content.py\n+x\n",
            "patch": "*** Add File: decoy_patch.py\n+x\n",
            "input": "*** Add File: decoy_input.py\n+x\n",
            "command": "*** Add File: real.py\n+x\n",
        })
        self.assertEqual(event.targets, ["real.py"])

    def test_a_malformed_command_body_beats_a_well_formed_input_body(self) -> None:
        # Precedence must not become an escape hatch: a malformed `command`
        # body fails the call closed even when a perfectly well-formed
        # `input` body sits beside it.
        event = self._codex_apply_patch({
            "command": "  *** Add File: /etc/passwd\n+pwned\n",
            "input": "*** Add File: harmless.txt\n+hello\n",
        })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_MALFORMED)
        self.assertEqual(event.targets, [])

    def test_the_three_pre_existing_fields_keep_working(self) -> None:
        # Additive, not a replacement: a host that ships any of the original
        # three names is unchanged when `command` is absent.
        for name in ("input", "patch", "content"):
            with self.subTest(field=name):
                event = self._codex_apply_patch({name: self.ADD_AND_DELETE})
                self.assertEqual(event.tool_kind, he.TOOL_KIND_FENCED)
                self.assertEqual(set(event.targets), {"a.py", "b.py"})

    def test_an_empty_command_falls_through_to_the_next_field(self) -> None:
        # `_first_field` skips a present-but-empty value; an empty `command`
        # must not shadow a real body sitting under `input`.
        event = self._codex_apply_patch({
            "command": "", "input": self.ADD_AND_DELETE})
        self.assertEqual(set(event.targets), {"a.py", "b.py"})

    def test_a_non_string_command_falls_through_to_the_next_field(self) -> None:
        # Codex's shell dialect can carry `command` as an argv ARRAY. The
        # adapter has never read a non-string body and still does not: it is
        # skipped, the next field is tried, and when nothing string-valued
        # remains the call fails closed rather than guessing at a shape this
        # repo has no live fixture for.
        event = self._codex_apply_patch({
            "command": ["apply_patch", self.ADD_AND_DELETE],
            "input": self.ADD_AND_DELETE,
        })
        self.assertEqual(set(event.targets), {"a.py", "b.py"})

        array_only = self._codex_apply_patch({
            "command": ["apply_patch", self.ADD_AND_DELETE]})
        self.assertEqual(array_only.tool_kind, he.TOOL_KIND_UNRECOGNIZED)

    def test_an_orchestrated_apply_patch_reads_the_command_body_too(self) -> None:
        # `functions.exec` unwraps to the nested call and re-enters the same
        # adapter - the body-field fix must apply there as well.
        with mock.patch.dict(os.environ, {"GODMODE_HOST": "codex"}, clear=False):
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": "functions.exec",
                "tool_input": {
                    "name": "apply_patch",
                    "arguments": {"command": self.ADD_AND_DELETE},
                },
            })
        self.assertEqual(event.tool, "apply_patch")
        self.assertEqual(set(event.targets), {"a.py", "b.py"})


class UnicodeAndColonlessDirectiveTests(unittest.TestCase):
    """Fix round 2 (re-review adversarial extension, both reviewer vectors
    plus the additional cases the round-2 order named): a directive line
    must be caught as malformed (never silently dropped as ordinary
    content) whether it is disguised with an invisible Unicode character
    or missing its colon. Every Unicode character below is spelled as an
    explicit `\\uXXXX` escape - never a literal invisible glyph pasted into
    source - so the exact code point under test is unambiguous on read.
    """

    ZWSP = "\u200b"             # ZERO WIDTH SPACE (Cf)
    FEFF = "\ufeff"             # ZERO WIDTH NO-BREAK SPACE / BOM (Cf)
    ZWJ = "\u200d"              # ZERO WIDTH JOINER (Cf)
    RLM = "\u200f"              # RIGHT-TO-LEFT MARK (Cf)
    INVISIBLE_TIMES = "\u2062"  # Cf, unrelated to any named vector

    def test_zero_width_space_inside_the_star_run_is_still_caught(self) -> None:
        # Reviewer's exact adversarial repro: a ZWSP breaks the literal
        # `***` run round 1's detector required.
        malformed = f"**{self.ZWSP}* Add File: /etc/passwd\n+pwned\n"
        patch = "*** Add File: harmless.txt\n+hi\n" + malformed
        self.assertTrue(he.has_malformed_directive(patch))

    def test_a_directive_keyword_with_no_colon_is_still_caught(self) -> None:
        # Reviewer's exact second adversarial repro.
        patch = "*** Add File: harmless.txt\n+hi\n*** Add File /etc/passwd\n+pwned\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_u_feff_mid_line_is_still_caught(self) -> None:
        patch = f"*** Add{self.FEFF} File: /etc/passwd\n+pwned\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_zero_width_joiner_is_still_caught(self) -> None:
        patch = f"**{self.ZWJ}* Add File: /etc/passwd\n+pwned\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_leading_bom_on_the_directive_line_itself_is_still_caught(self) -> None:
        patch = f"{self.FEFF}*** Add File /etc/passwd\n+pwned\n"
        self.assertTrue(he.has_malformed_directive(patch))

    def test_right_to_left_mark_inside_the_keyword_is_still_caught(self) -> None:
        patch = (f"*** Add File: harmless.txt\n+hi\n"
                 f"*** Delete{self.RLM} File: /etc/passwd\n")
        self.assertTrue(he.has_malformed_directive(patch))

    def test_the_green_control_still_allows_a_well_formed_multi_target_patch(self) -> None:
        patch = "*** Add File: a.py\n+x\n*** Add File: b.py\n+y\n"
        self.assertFalse(he.has_malformed_directive(patch))

    def test_innocuous_markdown_bold_never_trips_the_widened_detector(self) -> None:
        # Negative control the round-2 order named explicitly: two
        # asterisks with no directive keyword after them must never
        # false-positive, even though the widened detector no longer
        # requires a colon.
        patch = "+See the **bold** text in the README for details.\n"
        self.assertFalse(he.has_malformed_directive(patch))

    def test_normalize_strips_every_cf_category_character_not_a_hardcoded_list(self) -> None:
        # Category lookup, not an enumerated set: an arbitrary Cf character
        # unrelated to any of the named vectors is stripped the same way.
        self.assertEqual(
            he._normalize_for_lookalike(f"a{self.INVISIBLE_TIMES}b"), "ab")

    def test_normalize_folds_whitespace_runs_left_behind_by_stripping(self) -> None:
        self.assertEqual(
            he._normalize_for_lookalike(f"Add{self.ZWSP}{self.ZWSP}  File"),
            "Add File")


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


class NoDedupTests(unittest.TestCase):
    """Fix round 1, C2/I1 (review Critical + Important): gate-exactly-once
    dedup was removed entirely - `parse_host_payload` takes no `seen`
    argument and every call classifies fully, regardless of `request_id`
    repetition. This replaces the deleted `GateExactlyOnceTests`, whose own
    tests asserted the defect this round fixes (dedup-by-id-alone silently
    allowed a second, different operation under a reused id)."""

    def test_parse_host_payload_no_longer_accepts_a_seen_argument(self) -> None:
        import inspect
        parameters = inspect.signature(he.parse_host_payload).parameters
        self.assertNotIn("seen", parameters)

    def test_tool_kind_duplicate_no_longer_exists(self) -> None:
        self.assertFalse(hasattr(he, "TOOL_KIND_DUPLICATE"))

    def test_a_reused_request_id_with_a_different_operation_still_classifies_fully(self) -> None:
        """The reviewer's exact C2 repro: a force-push riding a request id
        already seen for an ordinary read must still be classified and
        still reach the R5 force-push tier, never silently pass through."""
        p1 = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
              "tool_input": {"command": "git status"}, "requestId": "req-X"}
        p2 = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
              "tool_input": {"command": "git push --force origin main"},
              "requestId": "req-X"}
        first = he.parse_host_payload(p1)
        second = he.parse_host_payload(p2)
        self.assertEqual(first.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(first.operation, "git status")
        # Fully classified, not silently allowed: this is exactly the
        # force-push operation text the classifier gates.
        self.assertEqual(second.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(second.operation, "git push --force origin main")

    def test_request_id_still_travels_on_the_event(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"}, "requestId": "req-1",
        })
        self.assertEqual(event.request_id, "req-1")


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


class FirstAliasWinsTests(unittest.TestCase):
    """Fix round 1, I3: camelCase-over-snake_case precedence is a pinned
    security property, not incidental dict-literal ordering - checked here
    at the `parse_host_payload` level (the reviewer's own cross-call-site
    check compared `field()`, the fast gate's local lookup, and the hook's
    `host_field` shortcut directly; this pins the same precedence at the
    adapter's own public entry point) across event, tool, and input fields.
    """

    def test_tool_name_camelcase_wins_over_snake_case(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse",
            "toolName": "Read", "tool_name": "Bash",
            "toolInput": {"file_path": "a.py"}, "tool_input": {"command": "rm -rf /"},
        })
        self.assertEqual(event.tool, "Read")
        self.assertEqual(event.tool_kind, he.TOOL_KIND_READ)

    def test_tool_input_camelcase_wins_over_snake_case(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "toolInput": {"command": "git status"},
            "tool_input": {"command": "git push --force origin main"},
        })
        self.assertEqual(event.operation, "git status")

    def test_hook_event_name_camelcase_wins_over_snake_case(self) -> None:
        self.assertTrue(he.is_pretool_event(
            {"hookEventName": "PreToolUse", "hook_event_name": "SessionStart"}))

    def test_field_helper_itself_agrees(self) -> None:
        self.assertEqual(
            he.field({"toolName": "Read", "tool_name": "Bash"}, "tool_name"), "Read")


class EmptyToolNameTests(unittest.TestCase):
    """Fix round 1, M2: `tool_name` PRESENT but empty/whitespace is
    `unrecognized-tool` - distinct from no `tool_name` field at all, which
    stays the bare-operation shape."""

    def test_empty_string_tool_name_is_unrecognized_not_bare(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "",
            "tool_input": {"anything": 1},
        })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)

    def test_whitespace_only_tool_name_is_unrecognized_not_bare(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "   ",
            "tool_input": {},
        })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)

    def test_a_missing_tool_name_field_is_still_the_bare_shape(self) -> None:
        event = he.parse_host_payload({"operation": "git status"})
        self.assertIsNone(event.tool_kind)

    def test_field_present_distinguishes_empty_from_absent(self) -> None:
        self.assertTrue(he.field_present({"tool_name": ""}, "tool_name"))
        self.assertFalse(he.field_present({}, "tool_name"))
        self.assertFalse(he.field_present({"operation": "x"}, "tool_name"))


if __name__ == "__main__":
    unittest.main()
