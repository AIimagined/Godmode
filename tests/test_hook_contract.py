"""R-2: one hook contract, tested per manifest.

`docs/HOOK-CONTRACT.md` is the one public contract every generated host
manifest is checked against here. This module parses that file's own
tables rather than hand-copying a second list of events or channel keys in
Python - a table edited in the doc without a matching code change (or the
reverse) fails a test here instead of drifting silently.

Three things are pinned:

1. Every host manifest `godmode_host_manifests` can build today emits only
   events the contract's section 1 table declares for that host, every
   command in it routes through the generated launcher, and every hook
   entry carries a timeout (section 8's acceptance bar).
2. `godmode_hostevent.render_decision`'s real per-host top-level key set for
   a `deny` response matches section 6's own "deny/ask key(s)" column,
   read from the same table.
3. `godmode_sentinel.classify_action` reaches the identical verdict for the
   same operation text whichever `tool_name` carries it in ("Bash",
   "PowerShell", or none at all) - the one-parse-view guarantee section 2
   documents, and the `tests/fixtures/gate_corpus.json` rows tagged
   `"tool": "Bash"` / `"tool": "PowerShell"` for the same `git commit`
   operation agree with each other, matching the corpus's own expectation.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as hm  # noqa: E402
from godmode_runtime.godmode_hostevent import render_decision  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

CONTRACT = PLUGIN_ROOT / "docs" / "HOOK-CONTRACT.md"
CORPUS = PLUGIN_ROOT / "tests" / "fixtures" / "gate_corpus.json"

_BACKTICK = re.compile(r"`([^`]+)`")


def _contract_text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _table_rows(text: str, header_line: str) -> list[list[str]]:
    """Every data row of the markdown table whose header row is exactly
    `header_line`, as a list of raw (still-backtick-quoted) cell strings.
    Assumes GitHub-flavoured markdown: a `|---|---|...` separator line
    immediately follows the header, then one or more `|`-led data rows
    until the first non-`|` line.
    """
    lines = text.splitlines()
    try:
        start = lines.index(header_line)
    except ValueError:
        raise AssertionError(f"contract table header not found: {header_line!r}")
    rows: list[list[str]] = []
    i = start + 2  # skip the header row and its `---` separator
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append(cells)
        i += 1
    if not rows:
        raise AssertionError(f"contract table under {header_line!r} has no data rows")
    return rows


def _tokens(cell: str) -> list[str]:
    return _BACKTICK.findall(cell)


# ---------------------------------------------------------------------------
# Section 1: emitted events per host.
# ---------------------------------------------------------------------------

_EVENTS_HEADER = "| Host key | Manifest shape | Events (closed set) |"


def _contract_events_by_host() -> dict[str, frozenset[str]]:
    rows = _table_rows(_contract_text(), _EVENTS_HEADER)
    out: dict[str, frozenset[str]] = {}
    for host_cell, _shape, events_cell in rows:
        hosts = _tokens(host_cell)
        assert len(hosts) == 1, f"expected exactly one host key, got {host_cell!r}"
        out[hosts[0]] = frozenset(_tokens(events_cell))
    return out


def _build_dedicated(build) -> dict:
    """Call a `HOOK_ARTIFACTS[...]["build"]` builder the same way
    `godmode_bindings._render_hook_artifact` dispatches - BY PARAMETER
    NAME, not arity: a builder taking `project` gets the real plugin root,
    one taking anything else (or nothing) is called with no arguments."""
    if "project" in inspect.signature(build).parameters:
        return build(PLUGIN_ROOT)
    return build()


def _all_hosts() -> frozenset[str]:
    """Every host this module can name a manifest for: `claude` (the
    shared file, which carries no `HOOK_ARTIFACTS` entry of its own) plus
    every key `HOOK_ARTIFACTS` declares - never a second, hand-typed host
    list that a new host could be added without."""
    return frozenset({"claude"}) | frozenset(hm.HOOK_ARTIFACTS)


class ContractEventsMatchTheAllowlistTests(unittest.TestCase):
    """The contract's own table, read back, must equal what
    `godmode_host_manifests` actually declares - so the doc cannot silently
    fall behind a host that starts emitting a new event."""

    def test_the_table_names_every_host_this_module_ships(self) -> None:
        declared = set(_contract_events_by_host())
        self.assertEqual(declared, set(_all_hosts()))

    def test_every_hosts_events_equal_the_contract_row_exactly(self) -> None:
        declared = _contract_events_by_host()
        shared = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json")
                            .read_text(encoding="utf-8"))
        # `codex`/`grok` merge into the shared file rather than building a
        # dedicated manifest of their own (`HOOK_ARTIFACTS[host]["mode"] ==
        # "merge-into-shared"`), so they have no `build`/`emitted` pair to
        # call generically - handled explicitly, the same way the doc's own
        # events table describes them as a special case.
        actual = {"claude": frozenset(shared["hooks"]),
                  "codex": hm.codex_emitted_events(),
                  "grok": frozenset(hm.GROK_HOOK_EVENTS)}
        for host, artifact in hm.HOOK_ARTIFACTS.items():
            if artifact["mode"] == "merge-into-shared":
                continue
            manifest = _build_dedicated(artifact["build"])
            actual[host] = artifact["emitted"](manifest)
        self.assertEqual(set(actual), set(_all_hosts()))
        for host, events in actual.items():
            self.assertEqual(events, declared[host], host)


# ---------------------------------------------------------------------------
# Section 6: decision-channel keys per host.
# ---------------------------------------------------------------------------

_CHANNELS_HEADER = ("| Host key | deny/ask key(s) | additionalContext-analog "
                   "| systemMessage-analog |")

_POSITIVE_HOSTS = ("claude", "codex", "grok", "cursor", "antigravity")


def _contract_deny_ask_keys() -> dict[str, frozenset[str]]:
    rows = _table_rows(_contract_text(), _CHANNELS_HEADER)
    out: dict[str, frozenset[str]] = {}
    for host_cell, deny_ask_cell, _ctx, _sysmsg in rows:
        hosts = _tokens(host_cell)
        if len(hosts) != 1:
            # The "undetected host" row names several hosts/keys in prose;
            # every OTHER row names exactly one host key, which is what
            # this test cross-checks against real code.
            continue
        top_level = {token.split(".", 1)[0] for token in _tokens(deny_ask_cell)}
        out[hosts[0]] = frozenset(top_level)
    return out


class ContractChannelKeysMatchRenderDecisionTests(unittest.TestCase):
    def test_every_positively_detected_hosts_deny_keys_match_the_table(self) -> None:
        declared = _contract_deny_ask_keys()
        for host in _POSITIVE_HOSTS:
            body, _code = render_decision(host, "PreToolUse", "deny", "why")
            self.assertEqual(frozenset(body), declared[host], host)

    def test_gemini_shares_the_undetected_host_fallback_as_the_contract_states(self) -> None:
        gemini_body, _code = render_decision("gemini", "PreToolUse", "deny", "why")
        unknown_body, _code = render_decision("unknown", "PreToolUse", "deny", "why")
        self.assertEqual(frozenset(gemini_body), frozenset(unknown_body))
        # Every key the contract's channel table names anywhere must be
        # covered by that union - nothing in the table is unreachable text.
        declared = _contract_deny_ask_keys()
        every_declared_key = frozenset().union(*declared.values())
        self.assertTrue(every_declared_key.issubset(frozenset(unknown_body)))


# ---------------------------------------------------------------------------
# Section 8: command routing and timeouts, walked over the real, live output
# of every builder - never a second, hand-copied list of the commands.
# ---------------------------------------------------------------------------

_LAUNCHER_NAMES = ("run-hook.cmd", "run-hook.sh")


def _walk_hook_entries(node):
    """Yield every `{"type": "command", ...}`-shaped dict anywhere inside
    `node` (arbitrarily nested lists/dicts), which is what every builder in
    `godmode_host_manifests` emits one of per hook handler."""
    if isinstance(node, dict):
        if node.get("type") == "command":
            yield node
        for value in node.values():
            yield from _walk_hook_entries(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_hook_entries(item)


def _all_manifests() -> dict[str, dict]:
    """Every manifest `godmode_host_manifests` can build today, `claude`'s
    shared file and Codex's project projection named explicitly (neither is
    a `HOOK_ARTIFACTS["...", "dedicated"]` entry), every OTHER dedicated
    builder derived straight from `HOOK_ARTIFACTS` - B2 (Task 6 fix round
    1): this used to hand-list five hosts, so a new dedicated manifest
    (Copilot, Kiro) could be added to `HOOK_ARTIFACTS` without this
    function - and therefore this file's own launcher-routing/timeout
    checks - ever noticing it existed."""
    shared = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json")
                        .read_text(encoding="utf-8"))
    manifests: dict[str, dict] = {
        "claude/shared": shared,
        "codex/project": hm.codex_project_hooks(PLUGIN_ROOT),
    }
    for host, artifact in hm.HOOK_ARTIFACTS.items():
        if artifact["mode"] != "dedicated":
            continue
        manifests[host] = _build_dedicated(artifact["build"])
    return manifests


class LauncherRoutingTests(unittest.TestCase):
    def test_every_command_in_every_manifest_routes_through_the_launcher(self) -> None:
        for name, manifest in _all_manifests().items():
            entries = list(_walk_hook_entries(manifest))
            self.assertTrue(entries, name)
            for entry in entries:
                commands = [entry.get("command", "")]
                if "commandWindows" in entry:
                    commands.append(entry["commandWindows"])
                for command in commands:
                    self.assertTrue(
                        any(launcher in command for launcher in _LAUNCHER_NAMES),
                        f"{name}: {command!r} does not route through a generated launcher")

    def test_every_hook_entry_carries_a_timeout(self) -> None:
        # Section 8's one stated exception: Codex's project-level projection
        # drops the timeout entirely (its bundled hooks carry neither, and
        # its own 600s default exceeds every declared budget) - pinned
        # separately by
        # tests/test_host_manifests.py::CodexProjectFallbackTests::test_projection_carries_every_event_with_absolute_commands.
        for name, manifest in _all_manifests().items():
            if name == "codex/project":
                continue
            for entry in _walk_hook_entries(manifest):
                self.assertIn("timeout", entry, f"{name}: {entry!r} has no timeout")
                self.assertIsInstance(entry["timeout"], int, name)
                self.assertGreater(entry["timeout"], 0, name)

    def test_the_codex_project_exception_is_exactly_what_the_contract_states(self) -> None:
        manifest = hm.codex_project_hooks(PLUGIN_ROOT)
        entries = list(_walk_hook_entries(manifest))
        self.assertTrue(entries)
        for entry in entries:
            self.assertNotIn("timeout", entry)
            self.assertNotIn("async", entry)


# ---------------------------------------------------------------------------
# Section 2: the Bash/PowerShell one-parse-view guarantee.
# ---------------------------------------------------------------------------


class ToolNameParseViewTests(unittest.TestCase):
    """classify_action's `tool_name` is provenance only - passing "Bash",
    "PowerShell", or nothing must never change the verdict for the same
    operation text. This is what the R-2 spec calls fixing the historical
    Bash-refused/PowerShell-allowed inconsistency: one parse view, made an
    explicit, tested parameter rather than an implicit cross-caller
    assumption."""

    OPERATIONS = (
        'git commit -m "apply pending changes"',
        "git push --force origin main",
        "ls -la",
        "git commit --amend --no-edit",
    )

    def test_bash_and_powershell_reach_the_same_verdict(self) -> None:
        for operation in self.OPERATIONS:
            bare = classify_action(operation, project_root=PLUGIN_ROOT)
            bash = classify_action(operation, project_root=PLUGIN_ROOT, tool_name="Bash")
            pwsh = classify_action(operation, project_root=PLUGIN_ROOT, tool_name="PowerShell")
            self.assertEqual(bare, bash, operation)
            self.assertEqual(bare, pwsh, operation)

    def test_an_unrecognised_tool_name_still_does_not_change_the_verdict(self) -> None:
        operation = 'git commit -m "apply pending changes"'
        baseline = classify_action(operation, project_root=PLUGIN_ROOT)
        other = classify_action(operation, project_root=PLUGIN_ROOT, tool_name="shell")
        self.assertEqual(baseline, other)


class CorpusBashPowerShellParityTests(unittest.TestCase):
    """The two `tests/fixtures/gate_corpus.json` rows this task adds: the
    same `git commit` operation, once tagged `"tool": "Bash"` and once
    `"tool": "PowerShell"`, must carry the same `expected` decision - and
    the classifier must actually agree with both."""

    def test_the_two_tagged_rows_exist_and_agree(self) -> None:
        entries = json.loads(CORPUS.read_text(encoding="utf-8"))
        # G-5 adds more tool-tagged rows (dialect pins); this test owns
        # only the two R-2 rows, named by their note.
        tagged = [e for e in entries if e.get("tool") in ("Bash", "PowerShell")
                  and str(e.get("note", "")).startswith("R-2")]
        self.assertEqual(len(tagged), 2)
        operations = {e["operation"] for e in tagged}
        self.assertEqual(len(operations), 1, "the two rows must share one operation")
        expected = {e["expected"] for e in tagged}
        self.assertEqual(len(expected), 1, "the two rows must share one expected decision")
        tools = {e["tool"] for e in tagged}
        self.assertEqual(tools, {"Bash", "PowerShell"})
        operation = operations.pop()
        for entry in tagged:
            verdict = classify_action(operation, project_root=PLUGIN_ROOT,
                                      tool_name=entry["tool"])
            decision = "allow" if not verdict["protected"] else (
                "refuse" if verdict["tier"] == "R5" else "ask")
            self.assertEqual(decision, entry["expected"], entry["tool"])


if __name__ == "__main__":
    unittest.main()
