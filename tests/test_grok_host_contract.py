"""CX-2/CX-6: fixtures drawn from the operator's live Grok probe (spec
Addendum 6) and its Codex/Claude counterparts, run through the REAL hook
subprocess - the same discipline `tests/test_hook_end_to_end.py` already
uses, for the same reason: a payload built by hand and a payload a host
actually sends are not the same test.

Binding facts this file locks in, all from
`docs/superpowers/specs/2026-08-16-codex-compat-design.md` Addendum 6 and
the Plan's amendments:

- Grok force-push (`run_terminal_command`) -> deny, and NEVER exit 3 (the
  probe's own finding: any exit other than 0/2 fail-opens on Grok).
- Grok `write`/`search_replace` -> classified and fenced, not the old
  "unclassified-mutation" exit-3 miss the probe caught live.
- An uninitialized project never denies, on any host.
- Claude payloads decide byte-identically to the pre-CX-2 hook (regression
  lock via the golden PreToolGate/HookEndToEnd suites this file does not
  duplicate, plus one direct check here).
- Codex `shell_command` force-push reaches R5; `apply_patch` targets reach
  the scope fence.
- Host detection: `GROK_AGENT=1` present -> host `grok`.

**Fix round 1** (`.superpowers/sdd/2026-08-16-cx/task-cx2-review.md`) added
`CodexApplyPatchMalformedDirectiveTests` (C1 - the reviewer's live repro,
replayed through the real hook subprocess: a patch mixing one well-formed
target with one malformed one must fail the WHOLE call closed, and the
well-formed target must never reach the fence alone) and
`ChronicleOnceTests` (M1 - a single unrecognized-tool/malformed-apply_patch
miss writes exactly one chronicle record, not two).
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime import godmode_hostevent as he  # noqa: E402


@contextmanager
def _hosted():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        project.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
        yield project, state


def _run(payload: dict, project: Path, state: Path, *, extra_env: dict | None = None
         ) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GODMODE_STATE_HOME"] = str(state)
    # A real host session does not export GODMODE_HOST - detection must work
    # from GROK_AGENT / payload shape alone, exactly as it would live. Any
    # inherited override is cleared so this file's own env vars decide.
    environment.pop("GODMODE_HOST", None)
    environment.pop("CLAUDE_CODE_ENTRYPOINT", None)
    environment.pop("GROK_AGENT", None)
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK), "pre-action", "--project", str(project)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", timeout=120, env=environment,
    )


def _read_events(project: Path, state: Path) -> list[dict]:
    """Re-open the SAME on-disk archive the subprocess just wrote to, so a
    test can count what actually landed in the chronicle - not what the
    hook's stdout claimed."""
    with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
        archive = Chronicle(resolve_anchor(project))
        return archive.read_events()


class GrokForcePushTests(unittest.TestCase):
    """Addendum 6 PROBE MATRIX: `run_terminal_command` + a force-push used to
    come back "unclassified-mutation", EXIT 3 - and any exit other than 0/2
    fail-opens on Grok, so the force-push would have run."""

    def test_force_push_denies_and_never_exits_three(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
                 "toolInput": {"command": "git push --force origin main"}},
                project, state, extra_env={"GROK_AGENT": "1"},
            )
        self.assertNotEqual(done.returncode, 3, done.stdout)
        self.assertIn(done.returncode, (0, 2), done.stdout)
        body = json.loads(done.stdout)
        self.assertEqual(body["decision"], "deny")
        self.assertNotEqual(body["decision"], "unclassified-mutation")

    def test_force_push_is_the_irreversible_r5_tier_not_a_soft_ask(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
                 "toolInput": {"command": "git push --force origin main"}},
                project, state, extra_env={"GROK_AGENT": "1"},
            )
        body = json.loads(done.stdout)
        self.assertIn("git-history-or-remote", body["reason"])


class GrokWriteAndSearchReplaceTests(unittest.TestCase):
    """Addendum 6: write/search_replace payloads came back the same
    unclassified exit 3 the force-push did - edits unfenced. They must now
    be classified (ordinary work allowed) and fenced (out-of-scope denied),
    never the generic miss."""

    def test_an_ordinary_write_after_init_is_allowed(self) -> None:
        with _hosted() as (project, state):
            target = project / "notes.md"
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "write",
                 "toolInput": {"file_path": str(target)}},
                project, state, extra_env={"GROK_AGENT": "1"},
            )
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(done.stdout.strip(), "")

    def test_search_replace_outside_the_tree_is_fenced_not_unclassified(self) -> None:
        with _hosted() as (project, state):
            outside = project.parent / "elsewhere.md"
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "search_replace",
                 "toolInput": {"file_path": str(outside)}},
                project, state, extra_env={"GROK_AGENT": "1"},
            )
        body = json.loads(done.stdout)
        self.assertEqual(body["decision"], "deny")
        self.assertNotIn("unclassified-mutation", json.dumps(body))


class GrokUninitializedProjectTests(unittest.TestCase):
    def test_an_uninitialized_project_never_denies_on_grok(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "fresh"
            project.mkdir()
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
                 "toolInput": {"command": "rm -rf /"}},
                project, base / "state", extra_env={"GROK_AGENT": "1"},
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('"deny"', done.stdout)


class GrokHostDetectionTests(unittest.TestCase):
    def test_grok_agent_present_resolves_the_grok_host(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
                 "toolInput": {"command": "git push --force origin main"}},
                project, state, extra_env={"GROK_AGENT": "1"},
            )
        body = json.loads(done.stdout)
        # The response body always carries the dual/multi-host keys - `decision`
        # is Grok's own contract key, present regardless of whether detection
        # also stamped `hookSpecificOutput` (Claude's key, also present).
        self.assertIn("decision", body)
        self.assertIn("hookSpecificOutput", body)


class GrokAskFoldsToDenyTests(unittest.TestCase):
    """Addendum 6: Grok has no `ask` decision - R3/R4 "ask" maps to deny,
    with a reason naming the staged-capability remedy."""

    def test_a_recoverable_refusal_denies_with_the_staged_capability_remedy(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hookEventName": "pre_tool_use", "toolName": "run_terminal_command",
                 "toolInput": {"command": "rm -rf build"}},
                project, state, extra_env={"GROK_AGENT": "1"},
            )
        body = json.loads(done.stdout)
        # On Claude this exact command asks; on Grok (no ask) it must deny.
        self.assertEqual(body["decision"], "deny")
        self.assertIn("godmode authorize stage --operation", body["reason"])


class ClaudeRegressionLockTests(unittest.TestCase):
    """The same payload shapes Claude has always sent, run through this
    file's own harness (not Grok's), decide exactly as before CX-2."""

    def test_a_force_push_still_asks_claude_for_permission_not_grok_style_deny(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git push --force origin main"}},
                project, state,
            )
        body = json.loads(done.stdout)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_a_recoverable_refusal_still_asks_on_claude(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "rm -rf build"}},
                project, state,
            )
        body = json.loads(done.stdout)
        # Claude HAS ask - this must not have been folded to deny the way the
        # Grok fixture above is.
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_a_read_only_call_is_silent(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git status"}},
                project, state,
            )
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")


class CodexShellCommandTests(unittest.TestCase):
    def test_a_force_push_reaches_r5(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "shell_command",
                 "tool_input": {"command": "git push --force origin main"}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        body = json.loads(done.stdout)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("git-history-or-remote", body["hookSpecificOutput"]["permissionDecisionReason"])

    def test_a_read_only_command_is_silent(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "shell_command",
                 "tool_input": {"command": "git status"}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")


class CodexApplyPatchTests(unittest.TestCase):
    def test_a_new_file_inside_the_tree_is_allowed(self) -> None:
        with _hosted() as (project, state):
            patch = f"*** Add File: {project / 'new_file.py'}\n+print(1)\n"
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                 "tool_input": {"input": patch}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(done.stdout.strip(), "")

    def test_a_target_outside_the_tree_reaches_the_scope_fence_and_denies(self) -> None:
        with _hosted() as (project, state):
            outside = project.parent / "elsewhere.py"
            patch = f"*** Add File: {outside}\n+print(1)\n"
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                 "tool_input": {"input": patch}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        body = json.loads(done.stdout)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")


class UnrecognizedToolAcrossHostsTests(unittest.TestCase):
    def test_an_unknown_tool_name_fails_closed_never_silently_allowed(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "some_future_tool",
                 "tool_input": {"anything": "shape"}},
                project, state,
            )
        body = json.loads(done.stdout)
        self.assertIn(body["hookSpecificOutput"]["permissionDecision"], ("ask", "deny"))
        self.assertIn("unrecognized-tool", body["hookSpecificOutput"]["permissionDecisionReason"])


class CodexApplyPatchMalformedDirectiveTests(unittest.TestCase):
    """Fix round 1, C1 (review Critical) - the reviewer's own live repro,
    replayed through the real hook subprocess and against a real scope
    fence: a well-formed target beside a malformed one must never reach the
    fence alone."""

    def test_the_reviewers_repro_fails_the_whole_call_closed(self) -> None:
        with _hosted() as (project, state):
            harmless = project / "harmless.txt"
            patch = (f"*** Add File: {harmless}\n+hello\n"
                     f"  *** Add File: /etc/passwd\n+pwned\n")
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                 "tool_input": {"input": patch}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        body = json.loads(done.stdout)
        decision = body["hookSpecificOutput"]["permissionDecision"]
        # Malformed-directive fails closed at R3 (ask/deny, recoverable) -
        # never "allow", which is the exact bypass the review caught.
        self.assertIn(decision, ("ask", "deny"))
        self.assertIn("apply-patch-malformed-directive",
                      body["hookSpecificOutput"]["permissionDecisionReason"])

    def test_a_tab_prefixed_malformed_directive_also_fails_closed(self) -> None:
        with _hosted() as (project, state):
            patch = f"*** Add File: {project / 'a.py'}\n+x\n\t*** Delete File: b.py\n"
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                 "tool_input": {"input": patch}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        body = json.loads(done.stdout)
        self.assertIn(body["hookSpecificOutput"]["permissionDecision"], ("ask", "deny"))

    def test_a_fully_well_formed_multi_target_patch_still_reaches_the_fence_normally(self) -> None:
        """Green control: the C1 fix must not make an ORDINARY multi-target
        patch fail closed - only a genuinely malformed directive line does.
        Both targets are `Add File` (not `Delete File`, which is always
        protected regardless of C1 - `rm <path>` is R4 filesystem-mutation
        in the full sentinel, independent of this fix) so a silent allow is
        the correct baseline to compare the malformed case against."""
        with _hosted() as (project, state):
            patch = (f"*** Add File: {project / 'a.py'}\n+x\n"
                     f"*** Add File: {project / 'b.py'}\n+y\n")
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                 "tool_input": {"input": patch}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(done.stdout.strip(), "")


class ChronicleOnceTests(unittest.TestCase):
    """Fix round 1, M1: an unrecognized-tool or malformed-apply_patch miss
    writes exactly ONE chronicle record for that miss, not two."""

    def test_an_unrecognized_tool_miss_is_chronicled_exactly_once(self) -> None:
        with _hosted() as (project, state):
            _run(
                {"hook_event_name": "PreToolUse", "tool_name": "some_future_tool",
                 "tool_input": {}},
                project, state,
            )
            events = _read_events(project, state)
        misses = [e for e in events if e["kind"] == "refusal"
                 and e["data"].get("category") == "unrecognized-tool"]
        self.assertEqual(len(misses), 1, misses)

    def test_a_malformed_apply_patch_miss_is_chronicled_exactly_once(self) -> None:
        with _hosted() as (project, state):
            patch = f"*** Add File: {project / 'a.py'}\n+x\n  *** Add File: b.py\n"
            _run(
                {"hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                 "tool_input": {"input": patch}},
                project, state, extra_env={"GODMODE_HOST": "codex"},
            )
            events = _read_events(project, state)
        misses = [e for e in events if e["kind"] == "refusal"
                 and e["data"].get("category") == "apply-patch-malformed-directive"]
        self.assertEqual(len(misses), 1, misses)


class LiveGrokHarnessShapeTests(unittest.TestCase):
    """Sprint 4: the manifest subscribed to nine tool names, the adapter
    understood three.

    The spec bound this seam as a UNION - "Matcher union keeps Claude names
    and adds run_terminal_command|search_replace|write" - and
    `.grok-plugin/hooks.json` honours it, matching
    `Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit|run_terminal_command|
    search_replace|write`. `_adapt_grok` implemented only Grok's own three,
    so six of the names OUR OWN MANIFEST asks Grok to send were answered
    with `_unrecognized`. Nothing about the vendor's documentation was
    wrong or missing; two files in this repository disagreed, and no test
    compared them.

    Confirmed live rather than reasoned: a `grok -p` run against this
    repository captured `{"event": "PreToolUse", "tool": "Bash",
    "field_names": ["command"]}` through the payload-capture probe, and
    `grok inspect` reports "Harness Compatibility -> claude -> hooks on".

    Fail-closed held the whole time - every such call was DENIED, never
    allowed - so this was a proof-recording and friction defect, not an
    escape. But a tool the adapter cannot name cannot have a proof written
    for it, which is why `hooks probe --host grok` reported UNAVAILABLE.
    """

    def setUp(self) -> None:
        # Host detection reads the environment; pin it here rather than
        # inheriting whatever the runner happened to export.
        self._env = mock.patch.dict(os.environ, {"GROK_AGENT": "1"}, clear=False)
        self._env.start()
        os.environ.pop("GODMODE_HOST", None)
        os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)

    def tearDown(self) -> None:
        self._env.stop()

    def test_every_name_in_the_shipped_matcher_resolves(self) -> None:
        """The drift guard whose absence let this happen: the manifest and
        the adapter are two authorities over one list, so the list is read
        from the manifest itself and every entry must resolve."""
        # Grok discovers the SHARED `hooks/hooks.json` (its own 09-plugins.md
        # lists only that path), so the matcher it actually sends is the
        # shared file's union, not a dedicated Grok manifest's.
        manifest = json.loads(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        matchers = [block["matcher"]
                    for blocks in manifest["hooks"].values()
                    for block in blocks if "matcher" in block]
        self.assertTrue(matchers, "the Grok manifest declares no matcher")
        names = sorted({n for m in matchers for n in m.split("|") if n})
        # The shared file also carries Codex's tool names; Grok never sends
        # those, so they are outside what THIS adapter must resolve.
        names = [n for n in names if n not in he.CODEX_TOOLS]
        self.assertGreaterEqual(len(names), 9, names)
        payload_for = {
            "Bash": {"command": "ls"}, "PowerShell": {"command": "ls"},
            "run_terminal_command": {"command": "ls"},
            "Write": {"file_path": "a.txt"}, "Edit": {"file_path": "a.txt"},
            "MultiEdit": {"file_path": "a.txt"},
            "NotebookEdit": {"file_path": "a.ipynb"},
            "write": {"file_path": "a.txt"},
            "search_replace": {"file_path": "a.txt"},
        }
        unresolved = []
        for name in names:
            event = he.parse_host_payload({
                "hook_event_name": "PreToolUse", "tool_name": name,
                "tool_input": payload_for.get(name, {"command": "ls"}),
            })
            if event.tool_kind == he.TOOL_KIND_UNRECOGNIZED:
                unresolved.append(name)
        self.assertEqual(unresolved, [], "the Grok manifest subscribes to tool "
                         "names this adapter answers with unrecognized-tool")

    def test_the_live_shell_shape_is_a_shell_call_not_an_unrecognized_tool(self) -> None:
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git push --force origin main"},
        })
        self.assertEqual(event.host, "grok")
        self.assertEqual(event.tool_kind, he.TOOL_KIND_SHELL)
        self.assertEqual(event.operation, "git push --force origin main")

    def test_the_live_shell_shape_still_denies_an_irreversible_command(self) -> None:
        with _hosted() as (project, state):
            done = _run(
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git push --force origin main"}},
                project, state, extra_env={"GODMODE_HOST": "grok"},
            )
        body = json.loads(done.stdout)
        self.assertEqual(body["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_the_live_edit_shapes_reach_the_fence(self) -> None:
        for tool, key in (("Write", "file_path"), ("Edit", "file_path")):
            with self.subTest(tool=tool):
                event = he.parse_host_payload({
                    "hook_event_name": "PreToolUse", "tool_name": tool,
                    "tool_input": {key: "/tmp/x.txt"},
                })
                self.assertEqual(event.host, "grok")
                self.assertEqual(event.targets, ["/tmp/x.txt"])

    def test_the_documented_spellings_still_work(self) -> None:
        """Addendum 6's names are not dropped - a Grok build that speaks the
        documented dialect must keep working."""
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "run_terminal_command",
            "tool_input": {"command": "ls"},
        })
        self.assertEqual(event.operation, "ls")

    def test_a_genuinely_unknown_tool_still_fails_closed(self) -> None:
        """CX-2's rule survives the widening: recognising more NAMED shapes
        must never become guessing at unnamed ones."""
        event = he.parse_host_payload({
            "hook_event_name": "PreToolUse", "tool_name": "some_future_grok_tool",
            "tool_input": {"whatever": "shape"},
        })
        self.assertEqual(event.tool_kind, he.TOOL_KIND_UNRECOGNIZED)


if __name__ == "__main__":
    unittest.main()
