"""CX-3: native per-host hook manifests, generated from one mechanism.

CX-2 taught the runtime to *read* five hosts' dialects through one adapter
(`godmode_hostevent.py`). CX-3 is the other half: teaching the *package* to
*ship* a manifest each host actually loads, so the adapter has something to
be called by in the first place. Before this unit, only Claude's hand-authored
`hooks/hooks.json` wired a real pre-tool boundary; Codex's own matcher never
named a Codex tool, Grok never ran the `command` + `args` entries it was
handed, and Cursor had no hook manifest at all.

**Governing rule, repeated from the plan/spec because it is the one this
whole module exists to obey:** every event name, field name, or matcher this
module emits must be traceable to a specific spec addendum or an existing
adapter constant in `godmode_hostevent.py`. An unverifiable name is OMITTED,
never guessed - and the gap is surfaced honestly by `hooks status` /
`hooks install`, not silently shipped as if it were confirmed. Each
constant/builder below cites its source in its own docstring or comment.

**Extends the existing mechanism, does not replace it.** `godmode_bindings.py`
already generates every host's *identity* manifest (`plugin.json`) from one
source file, `packaging/hosts.json`. This module supplies the second kind of
artifact that mechanism's `write()`/`check()` now also drive: *hook*
manifests, whose shape (nested event -> matcher -> command lists) has nothing
in common with the flat identity-field copy `godmode_bindings.render()`
already does, so it gets its own builder functions here - called BY
`godmode_bindings.write()`/`check()`, not a second, parallel entry point.

**File-layout decision (revisited 2026-08-28 on two field reports):** Codex's
build doc and Grok's own 09-plugins.md both name `hooks/hooks.json` as the
one hooks file a plugin carries - the SAME default path Claude loads. Both
hosts fire the shared CamelCase events, so neither gets keys of its own;
their tool names join the shared PreToolUse matcher
(`merge_host_tools_into_shared`). The shared file's entries are shell-form
command strings (`_shell_entry`), the one shape all three parse: the
earlier `command` + `args` pair was Claude's exec form only - Grok resolved
the bare `python` token against the file's directory and failed every hook
open, Codex refused the shape and registered nothing. The dedicated
`.grok-plugin/hooks.json` that revision shipped was never read and is gone.
Cursor's `"version": 1` envelope and `failClosed` field, and Gemini's
settings.json-fragment shape, differ in shape rather than only in path, so
they keep a dedicated file under their own host directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import godmode_hostevent as hostevent

# ---------------------------------------------------------------------------
# Event-name allowlists. ONE constant per host, each an exhaustive list of
# every hook-config event key this module is willing to emit for that host -
# never a superset "for completeness". `tests/test_host_manifests.py` asserts
# the emitted set from each builder below equals its allowlist here exactly,
# so a future edit that starts emitting an unverified extra event name (or
# silently drops a verified one) fails the test, not a live host.
# ---------------------------------------------------------------------------

# Sprint 4 correction, on evidence that did not exist when the previous
# spelling was chosen. The old comment here recorded its own reasoning
# honestly: the Codex build doc's example was CamelCase, but the event list
# was "NOT published", so an audit observation of `session_start`/
# `pre_tool_use` was preferred over a single documented example.
#
# Both halves of that are now superseded:
#   - OpenAI publishes the full list, and every name in it is CamelCase:
#     SessionStart, SessionEnd, SubagentStart, SubagentStop, PreToolUse,
#     PermissionRequest, PostToolUse, PreCompact, PostCompact,
#     UserPromptSubmit, Stop.
#   - A live `codex exec` session captured the hook firing with
#     `hook_event_name: "PreToolUse"` - Codex reads the CamelCase block,
#     the same one Claude uses, resolving `${CLAUDE_PLUGIN_ROOT}` as the
#     documented legacy alias for `${PLUGIN_ROOT}`.
#
# The snake_case keys were not merely redundant: naming an event Codex
# cannot enable is what left the orphan trust row in the operator's
# `~/.codex/config.toml` (a `trusted_hash` with no `enabled`), and it put
# `apply_patch` - Codex's documented file-edit tool - behind a key that
# never fires, so Codex file edits reached no boundary at all. Codex now
# rides the shared CamelCase events, and its tool names join that matcher.
CODEX_HOOK_EVENTS = frozenset({"SessionStart", "UserPromptSubmit", "PreToolUse"})

# Plan amendments (CX-3 additions, spec Addendum 6 verbatim): "register
# PreCompact + SessionEnd" alongside Addendum 2026-08-16's own confirmed
# CamelCase config-event list (SessionStart, UserPromptSubmit, PreToolUse,
# ..., PreCompact, ..., verbatim spellings). Grok's own docs describe these
# CONFIG keys as "largely CLAUDE-COMPATIBLE" - only the stdin envelope's
# `hookEventName` VALUE is snake_case, never the hooks.json KEY.
GROK_HOOK_EVENTS = frozenset({
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PreCompact", "SessionEnd",
    # Field report 2026-08-29: the shipped shared file carries Stop and
    # PostToolUse, and `hooks status` said Grok declared neither - the list
    # lagged the manifest it describes.
    "Stop", "PostToolUse",
})

# Addendum 5 (spec, verified fetch): Cursor's own camelCase dialect names
# `sessionStart`, `preToolUse`, `beforeShellExecution` verbatim among its
# documented event list.
CURSOR_HOOK_EVENTS = frozenset({"sessionStart", "preToolUse", "beforeShellExecution"})

# Addendum 4a (spec, verified fetch, correcting Addendum 4): Gemini CLI's own
# event list names `SessionStart` and `BeforeTool` verbatim (the pre-tool
# event is `BeforeTool`, NOT `PreToolUse` - "a third event-name dialect").
# Every other documented Gemini event (AfterAgent, BeforeModel, PreCompress,
# ...) stays unemitted: CX-3 only asks for the BeforeTool hook fragment, and
# emitting names this module has no builder logic for would be exactly the
# "declare it, never call it" honesty gap CX-1 exists to prevent elsewhere.
GEMINI_HOOK_EVENTS = frozenset({"SessionStart", "BeforeTool"})
# Antigravity (antigravity.google/docs/hooks, fetched 2026-08-29): five
# lifecycle events (PreToolUse, PostToolUse, PreInvocation, PostInvocation,
# Stop). Only the two below are emitted: PreToolUse is the gate, Stop is
# the claim-echo parking pass. A community report (Antigravity IDE 1.107.0
# on Windows, discuss.ai.google.dev) says Stop/PostToolUse hooks may never
# fire there - shipped anyway because the contract is documented, with the
# gap named on the artifact registry entry.
ANTIGRAVITY_HOOK_EVENTS = frozenset({"PreToolUse", "Stop"})

# Addendum 2 confirmed fact + CX-3's own instruction: Codex's matcher is the
# union of every tool `godmode_hostevent._adapt_codex` recognises, including
# the orchestration wrapper (`functions.exec`) so a nested call reaches the
# gate at all - built FROM `hostevent.CODEX_TOOLS`, never re-typed.
CODEX_MATCHER = "|".join(sorted(hostevent.CODEX_TOOLS))

# Fix round 1 (C2, review Critical): Addendum 5's own documented tool-type
# vocabulary for Cursor matchers is a CLOSED list - "Matchers by tool type
# (Shell, Read, Write, Grep, Delete, Task, MCP:<name>)", verbatim - and
# `"Edit"` is not in it (the prior revision emitted it anyway, untraceable
# and unflagged). `preToolUse`'s matcher is narrowed to the MUTATING subset
# of that documented list the fast gate actually handles: `Shell` (shell
# commands), `Write` (file writes), `Delete` (filesystem removals). `Read`
# and `Grep` are excluded deliberately - they are non-mutating, so gating
# them would cost latency for no protection the fast path exists to add.
# `Task` and `MCP:<name>` are excluded because this manifest's gate script
# (`godmode_gate_fast.py`) has no logic for either shape - matching a tool
# type this module cannot classify would be worse than not matching it at
# all, the same over-trigger-never-under-trigger asymmetry documented at
# `CURSOR_SHELL_TEXT_MATCHER`/`GEMINI_TOOL_MATCHER` below, applied in the
# OTHER direction here (narrow to what is both DOCUMENTED and HANDLED,
# rather than wildcard-matching everything).
CURSOR_PRETOOLUSE_MATCHER = "Shell|Write|Delete"

# Addendum 5's own documented tool-type vocabulary, verbatim, as a CLOSED
# set: "Matchers by tool type (Shell, Read, Write, Grep, Delete, Task,
# MCP:<name>)". `MCP:<name>` is a named PATTERN (one entry per configured
# MCP server), not a literal token, so it is tracked separately and never
# belongs in a literal-name set like this one - no MCP server ships with
# this manifest, so it is never emitted regardless.
CURSOR_DOCUMENTED_TOOL_TYPES = frozenset({"Shell", "Read", "Write", "Grep", "Delete", "Task"})


def cursor_pretooluse_matcher_tools() -> frozenset[str]:
    """The literal tool-type tokens `CURSOR_PRETOOLUSE_MATCHER` emits, split
    on `|` - what a test checks against `CURSOR_DOCUMENTED_TOOL_TYPES`
    (traceability: every emitted name must be documented) and against the
    deliberately narrowed mutating subset this module actually emits
    (fix round 1, C2's own binding instruction: `Shell|Write|Delete`).
    """
    return frozenset(CURSOR_PRETOOLUSE_MATCHER.split("|"))

# The task's binding instruction: Cursor's `beforeShellExecution` matches on
# COMMAND TEXT via regex (Addendum 5), not a tool-name union - and no tool
# vocabulary or command-shape allowlist is documented for Cursor to match
# narrowly against. Over-triggering here (every shell command reaches the
# gate script) costs nothing but one subprocess call; under-triggering would
# be a silent bypass - the same asymmetry `godmode_gate_fast.py`'s own
# escalate-not-guess default and the `apply_patch` lookalike detector already
# choose elsewhere in this codebase. The gate script itself, not this regex,
# makes the real allow/ask/deny decision.
CURSOR_SHELL_TEXT_MATCHER = ".*"

# Same reasoning as `CURSOR_SHELL_TEXT_MATCHER`: Gemini's own tool-name
# vocabulary is undocumented (Addendum 4a), so `BeforeTool`'s regex matcher
# over-triggers rather than guesses at names.
GEMINI_TOOL_MATCHER = ".*"
# Same reasoning again for Antigravity: its docs show run_command/view_file/
# browser_.* as matcher examples but publish no closed tool vocabulary, so
# the matcher subscribes to everything and the adapter fails unknown names
# closed itself.
ANTIGRAVITY_TOOL_MATCHER = ".*"


# ---------------------------------------------------------------------------
# Shared plumbing.
# ---------------------------------------------------------------------------

SESSION_HOOK = "hooks/godmode_session_hook.py"
GATE_FAST_HOOK = "hooks/godmode_gate_fast.py"


def _shell_entry(root_var: str, script: str, *args: str, timeout: int) -> dict[str, Any]:
    """The one hook-entry shape every host parses: `command` is ONE shell
    string, never a `command` + `args` pair.

    Claude's hooks reference: no `args` means shell form, with the root
    variable substituted and quoted. Codex's plugin guide: one command
    string, `${CLAUDE_PLUGIN_ROOT}` honoured as a compatibility alias.
    Grok's 10-hooks.md: `command` is "Path to executable (relative to the
    JSON file) or inline shell command", `${VAR}` expanded, the
    `CLAUDE_PLUGIN_ROOT` alias set. The 2026-08-28 field reports are why
    this is the only builder left: Grok took a bare `"python"` token as a
    path beside the file and failed every hook open; Codex refused the
    `args` shape and listed zero hooks. Forward slashes are fine on
    Windows for python, Git Bash and PowerShell alike, so there is no
    per-OS variant.
    """
    tail = " ".join(args)
    # Field report 2026-09-03 (stock macOS): bare `python` does not exist
    # there, so every hook died silently. The polyglot launcher resolves
    # python3/python/py per platform and execs, preserving the exit codes
    # that carry gate blocks.
    return {
        "type": "command",
        "command": (f'"{root_var}/hooks/run-hook.cmd" {script.rsplit("/", 1)[-1]}'
                    + (f" {tail}" if tail else "")),
        "timeout": timeout,
    }


# ---------------------------------------------------------------------------
# Codex: merge two native, snake_case keys into the SHARED hooks/hooks.json.
# ---------------------------------------------------------------------------


def merge_host_tools_into_shared(existing: dict[str, Any]) -> dict[str, Any]:
    """Return `existing` (the hand-authored `hooks/hooks.json`) with every
    shared-file host's tool names present in the PreToolUse matcher - every
    OTHER key stays byte-identical, insertion order preserved, so Claude's
    own behavior and the file's `check()`/`write()` diff for a Claude-only
    edit are both unaffected by this function ever having run.

    Codex and Grok both discover this one default file (Codex's build doc;
    Grok's 09-plugins.md lists `hooks/hooks.json` as the sole hooks
    component) and both fire the shared CamelCase events, so neither needs
    keys of its own - only its tool names inside the matcher. Widening the
    matcher is what gates `apply_patch` on Codex and `run_terminal_command`
    on Grok; a name under a key a host never fires gates nothing.
    """
    merged = dict(existing)
    merged["hooks"] = dict(existing.get("hooks") or {})
    # Retire the two snake_case keys an earlier revision emitted. They name
    # events that appear nowhere in Codex's published list, and a checkout
    # carrying them keeps producing the orphan trust row - so regeneration
    # removes them rather than merely ceasing to add them.
    for retired in ("session_start", "pre_tool_use"):
        merged["hooks"].pop(retired, None)
    pre_tool_use = [dict(block) for block in merged["hooks"].get("PreToolUse") or []]
    for block in pre_tool_use:
        if "matcher" not in block:
            continue
        # Field report 2026-08-28: the matcher is a REGEX to Claude-family
        # hosts, so a dotted tool name must ship escaped (`functions\.exec`);
        # identity is compared on the unescaped name so regeneration stays
        # idempotent.
        names = [n.replace("\\.", ".") for n in block["matcher"].split("|") if n]
        for tool in sorted(hostevent.CODEX_TOOLS) + sorted(hostevent.GROK_TOOLS):
            if tool not in names:
                names.append(tool)
        block["matcher"] = "|".join(n.replace(".", "\\.") for n in names)
    if pre_tool_use:
        merged["hooks"]["PreToolUse"] = pre_tool_use
    return merged


def codex_project_hooks(plugin_root) -> dict:
    """Project the shared hooks file into the `.codex/hooks.json` Codex loads.

    Codex CLI 0.150.1 ignores plugin-bundled hook manifests entirely - its
    own bundled plugins' hooks show Installed: 0 in /hooks - which conflicts
    with its documented plugin-hook behaviour (host bug, confirmed
    2026-08-28 by an isolated review against the installed cache). What it
    DOES load is project-level config, so the same events and matchers ship
    there with absolute commands into THIS install. `python` on Windows,
    NOT `py -3` (Codex retest 2026-08-29): the launcher resolves to the
    USER-local AppData interpreter, which Codex's sandbox accounts are
    denied - law 12 already ruled it: the sandbox sees only the machine
    PATH, so the interpreter must be the machine-scope `python` that this
    project's Codex row requires. Timeout/async keys are dropped -
    Codex's bundled hooks carry neither and its 600s default exceeds every
    declared budget.
    """
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    root = _Path(plugin_root)
    shared = _json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    projected: dict = {"hooks": {}}
    for event, blocks in shared["hooks"].items():
        out_blocks = []
        for block in blocks:
            entries = [{
                "type": "command",
                "command": entry["command"].replace(
                    '"${CLAUDE_PLUGIN_ROOT}/',
                    '"' + root.as_posix() + "/"),
            } for entry in block.get("hooks", [])]
            out = {"matcher": block["matcher"]} if "matcher" in block else {}
            out["hooks"] = entries
            out_blocks.append(out)
        projected["hooks"][event] = out_blocks
    return projected


def write_codex_project_hooks(plugin_root, project, *, force: bool = False) -> dict:
    import json as _json
    from pathlib import Path as _Path

    target = _Path(project) / ".codex" / "hooks.json"
    rendered = _json.dumps(codex_project_hooks(plugin_root), indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != rendered and not force:
        return {"written": False, "path": str(target),
                "reason": "exists with different content; pass --force to overwrite"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    return {"written": True, "path": str(target),
            "events": sorted(codex_project_hooks(plugin_root)["hooks"]),
            "note": "Codex requires explicit trust: open codex, review each "
                    "command, Trust, then restart - hooks run outside its sandbox"}


# No plugin-root variable is documented for Antigravity's hooks.json - the
# fragment carries this placeholder and `hooks wire --host antigravity`
# substitutes the absolute install path per project.
ANTIGRAVITY_ROOT_TOKEN = "${godmodePluginRoot}"


def build_antigravity_fragment() -> dict:
    """The `.agents/hooks.json`-shaped artifact for Antigravity
    (antigravity.google/docs/hooks, fetched 2026-08-29): the file maps HOOK
    NAMES to event configurations - so the note travels under a `_note` key
    an installer strips, and godmode's own entry is the `godmode` key.
    Handlers are `{type: "command", command, timeout}` with timeouts in
    SECONDS (default 30); tool-use handlers carry a regex `matcher`.
    PreToolUse stdout is one JSON object `{decision, reason}` - the dialect
    `render_decision` speaks for this host."""
    root = ANTIGRAVITY_ROOT_TOKEN
    return {
        "_note": (
            "Antigravity loads hooks.json from the workspace's .agents/ "
            "directory (or ~/.gemini/config/). This file is the reference "
            "shape; `godmode hooks wire --host antigravity` merges the "
            "godmode key into the project's .agents/hooks.json with "
            f"{ANTIGRAVITY_ROOT_TOKEN} replaced by the absolute install "
            "path. stdout for PreToolUse must be a single JSON object "
            "{decision, reason}. Never claim HARD interception without a "
            "fresh probe proof; Stop hooks not firing on Windows (IDE "
            "1.107.0) is field-confirmed, 2026-08-29."
        ),
        "godmode": {
            "enabled": True,
            "PreToolUse": [
                {
                    "matcher": ANTIGRAVITY_TOOL_MATCHER,
                    "type": "command",
                    "command": f"{root}/hooks/run-hook.cmd godmode_gate_fast.py",
                    "timeout": 8,
                },
            ],
            "Stop": [
                {
                    "type": "command",
                    "command": f"{root}/hooks/run-hook.cmd godmode_session_hook.py stop",
                    "timeout": 10,
                },
            ],
        },
    }


def antigravity_emitted_events(fragment: dict[str, Any]) -> frozenset[str]:
    entry = fragment.get("godmode", {})
    return frozenset(k for k in entry if k != "enabled")


def write_antigravity_project_hooks(plugin_root, project, *,
                                    force: bool = False) -> dict:
    """Merge godmode's hook entry into `<project>/.agents/hooks.json`.

    The file maps hook names to configs, so foreign hooks are preserved and
    only the `godmode` key is owned here. Same overwrite contract as the
    Codex fallback: an existing `godmode` key with different content is
    refused without force. Interpreter is machine-PATH `python` on Windows
    (law 12: a sandboxed host account sees only the machine PATH).
    """
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    root = _Path(plugin_root)
    fragment = build_antigravity_fragment()
    entry = _json.loads(_json.dumps(fragment["godmode"]).replace(
        ANTIGRAVITY_ROOT_TOKEN + "/", root.as_posix() + "/"))
    target = _Path(project) / ".agents" / "hooks.json"
    existing: dict = {}
    if target.exists():
        try:
            existing = _json.loads(target.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a corrupt file is refused, never clobbered
            return {"written": False, "path": str(target),
                    "reason": "exists but is not valid JSON; fix or remove it first"}
        if not isinstance(existing, dict):
            return {"written": False, "path": str(target),
                    "reason": "exists but is not a JSON object; fix or remove it first"}
        if existing.get("godmode") not in (None, entry) and not force:
            return {"written": False, "path": str(target),
                    "reason": "a different godmode entry exists; pass --force to overwrite"}
    existing["godmode"] = entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return {"written": True, "path": str(target),
            "events": sorted(antigravity_emitted_events(fragment)),
            "note": "restart Antigravity, then run a protected command to "
                    "probe; interception stays SOFT until a live deny is "
                    "chronicled (Stop may not fire on Windows per a "
                    "community report)"}


def write_opencode_project_shim(plugin_root, project, *, force: bool = False) -> dict:
    """Install the Bun shim into a project's `.opencode/plugins/` (field
    verdict 2026-08-28: the adapter works but the copy step was manual).
    The shim itself sets GODMODE_HOST=opencode and fails closed; the one
    thing it cannot know is where this install lives, so the note names the
    exact GODMODE_PLUGIN_ROOT to export (and GODMODE_PYTHON for a
    non-default interpreter). Same overwrite contract as the Codex fallback:
    a differing existing file is refused without force.
    """
    from pathlib import Path as _Path

    root = _Path(plugin_root)
    source = root / "adapters" / "opencode" / "godmode.opencode.js"
    body = source.read_text(encoding="utf-8")
    target = _Path(project) / ".opencode" / "plugins" / "godmode.js"
    if target.exists() and target.read_text(encoding="utf-8") != body and not force:
        return {"written": False, "path": str(target),
                "reason": "exists with different content; pass --force to overwrite"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return {"written": True, "path": str(target),
            "env": {"GODMODE_PLUGIN_ROOT": str(root),
                    "GODMODE_PYTHON": "optional; defaults to python"},
            "note": "export GODMODE_PLUGIN_ROOT before starting OpenCode; "
                    "append adapters/opencode/AGENTS-godmode.md to the "
                    "project AGENTS.md for the CLI controls; a live denied "
                    "tool call is what upgrades the SOFT interception claim"}


def runtime_census(home=None) -> list:
    """Every godmode install held by this machine's known plugin caches.

    S6 (obligation 4436, field report 2026-08-28): three runtimes shared one
    archive across processes and raced its chain, and the stale 0.3.0 cache
    was still being loaded by something. Stat-and-regex only, bounded."""
    import re as _re
    from pathlib import Path as _Path

    base = _Path(home) if home else _Path.home()
    installs = []
    for cache in (base / ".claude" / "plugins" / "cache",
                  base / ".codex" / "plugins" / "cache",
                  base / ".grok" / "plugins" / "cache"):
        if not cache.is_dir():
            continue
        pattern = "*/godmode/*/scripts/godmode_runtime/godmode_constants.py"
        for constants in sorted(cache.glob(pattern))[:10]:
            try:
                text = constants.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = _re.search(r'RUNTIME_VERSION = "([^"]+)"', text)
            installs.append({
                "path": str(constants.parents[2]),
                "version": match.group(1) if match else "unknown",
            })
    return installs


def runtime_census_issues(current_version, home=None) -> list:
    """Doctor issues for stale cached runtimes sharing this archive."""
    issues = []
    for install in runtime_census(home):
        if install["version"] == current_version:
            continue
        issues.append({
            "code": "stale-runtime-cache",
            "severity": "warning",
            "detail": (f"{install['path']} holds godmode {install['version']} "
                       f"while this runtime is {current_version}; two runtimes "
                       "share one archive and race its chain - remove or "
                       "update the stale cache."),
        })
    return issues


def codex_emitted_events() -> frozenset[str]:
    return frozenset(CODEX_HOOK_EVENTS)


# ---------------------------------------------------------------------------
# Grok: dedicated `.grok-plugin/hooks.json`.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cursor: dedicated `.cursor-plugin/hooks.json`.
# ---------------------------------------------------------------------------


def build_cursor_manifest() -> dict[str, Any]:
    """Cursor's own native manifest: `"version": 1` envelope (Addendum 5,
    verified fetch), camelCase event keys, `failClosed: true` set on both
    gate hooks (`preToolUse` and `beforeShellExecution` - Addendum 5: "Cursor
    is the ONLY host with opt-in fail-closed... godmode's Cursor manifest
    sets failClosed true on its gate hooks"), `sessionStart` registered per
    the task's own binding instruction.

    GAP, documented rather than guessed: no plugin-root variable is named
    anywhere in Addendum 5 (only `CURSOR_PROJECT_DIR`, a project dir, not a
    plugin dir). `${PLUGIN_ROOT}` is used here as the best-effort choice -
    it is the Agent Plugins Specification v1.0.0's own portable placeholder
    (Addendum 3, verified fetch), and Cursor is independently named as a
    client that spec's PORTABLE (non-hook) components already reach "at zero
    extra cost" - but the spec explicitly excludes hooks from v1
    ("V1 HAS NO HOOKS"), so whether Cursor's OWN hook loader expands this
    placeholder is UNVERIFIED. This exact gap is also carried on
    `HOOK_ARTIFACTS["cursor"]["gap"]` (fix round 1, I2) so `hooks status`'s
    structured `gap` field surfaces it the same way it already does for
    Gemini's fragment-only gap - never only in a docstring a status read
    cannot see.
    """
    root = "${PLUGIN_ROOT}"
    return {
        "version": 1,
        "hooks": {
            "sessionStart": [
                {"hooks": [_shell_entry(root, SESSION_HOOK, "session-start", timeout=10)]},
            ],
            "preToolUse": [
                {
                    "matcher": CURSOR_PRETOOLUSE_MATCHER,
                    "failClosed": True,
                    "hooks": [_shell_entry(root, GATE_FAST_HOOK, timeout=3)],
                },
            ],
            "beforeShellExecution": [
                {
                    "matcher": CURSOR_SHELL_TEXT_MATCHER,
                    "failClosed": True,
                    "hooks": [_shell_entry(root, GATE_FAST_HOOK, timeout=3)],
                },
            ],
        },
    }


def cursor_emitted_events(manifest: dict[str, Any]) -> frozenset[str]:
    return frozenset(manifest.get("hooks", {}).keys())


# ---------------------------------------------------------------------------
# Gemini CLI: dedicated hooks FRAGMENT (not a full `gemini-extension.json` -
# that manifest kind needs its own required `mcpServers` shape and
# distribution metadata this unit does not touch; the fragment is the
# cleanly-emittable slice CX-3 asks for, and the surrounding gap is reported,
# never silently expanded into a claim this module does not back).
# ---------------------------------------------------------------------------


def build_gemini_fragment() -> dict[str, Any]:
    """A settings.json-shaped `hooks` fragment (Addendum 4a: "Defined in
    settings.json layers... fields name/type("command")/command/
    timeout(ms, default 60000)/description") an installer merges into
    `.gemini/settings.json`'s own `hooks` key - Gemini CLI hooks are NOT
    auto-loaded from a fixed plugin-relative path the way Claude/Codex/Grok's
    are, so this artifact is explicitly a fragment to merge, not a manifest
    a host discovers on its own. `${extensionPath}` is Addendum 4's own
    CONFIRMED (verified fetch) extension path variable - the correct one for
    an extension-carried fragment, not the project-dir env vars Addendum 4a
    separately lists (`GEMINI_PROJECT_DIR` etc., which name where the
    PROJECT lives, not where this plugin's own script does).

    Timeouts are in MILLISECONDS (Addendum 4a states the field's own default,
    60000ms, explicitly) - the one host among the four whose unit differs
    from every other manifest's seconds, so the values below are deliberately
    NOT the same numbers used elsewhere.
    """
    root = "${extensionPath}"
    return {
        "_note": (
            "Gemini CLI hooks are defined inside settings.json layers "
            "(project .gemini/settings.json, user ~/.gemini/settings.json, "
            "or an extension's own settings - Addendum 4a), not auto-loaded "
            "from a fixed plugin path. Merge this fragment's \"hooks\" object "
            "into that file's own \"hooks\" key. stdout MUST be a single JSON "
            "object only (Addendum 4a's I/O contract) - any other exit code "
            "than 0 or 2 is a non-fatal WARNING that proceeds with the "
            "original parameters (fail-open); never claim HARD interception "
            "on Gemini without a fresh CX-1 probe proof."
        ),
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "name": "godmode-session-start",
                            "type": "command",
                            "command": f"python {root}/{SESSION_HOOK} session-start",
                            "timeout": 10000,
                            "description": "Godmode session continuity brief.",
                        },
                    ],
                },
            ],
            "BeforeTool": [
                {
                    "matcher": GEMINI_TOOL_MATCHER,
                    "hooks": [
                        {
                            "name": "godmode-pre-tool-gate",
                            "type": "command",
                            "command": f"{root}/hooks/run-hook.cmd godmode_gate_fast.py",
                            "timeout": 3000,
                            "description": "Godmode pre-tool gate.",
                        },
                    ],
                },
            ],
        },
    }


def gemini_emitted_events(fragment: dict[str, Any]) -> frozenset[str]:
    return frozenset(fragment.get("hooks", {}).keys())


# ---------------------------------------------------------------------------
# Base `plugin.json` (Agent Plugins Specification v1.0.0) - closed field list.
# ---------------------------------------------------------------------------

# Addendum 3 (spec, verified fetch): "Defines closed plugin.json schema
# ($schema, name, version, description, author, homepage, repository,
# license, keywords, extensions ONLY)". Any OTHER top-level key is a schema
# violation - "no invented top-level keys" per the task's own binding text.
PLUGIN_V1_CLOSED_FIELDS = frozenset({
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
})


def validate_plugin_v1(manifest: dict[str, Any]) -> list[str]:
    """Every top-level key not in the closed field list, sorted - empty
    means conformant. A pure structural check: this does not validate types
    or nested shapes against the published JSON Schema (no network fetch,
    per this project's zero-runtime-dependency/no-network doctrine), only
    the one property CX-3 is bound to guarantee - the field list is closed.
    """
    if not isinstance(manifest, dict):
        return ["<not-an-object>"]
    return sorted(key for key in manifest if key not in PLUGIN_V1_CLOSED_FIELDS)


# ---------------------------------------------------------------------------
# Registry: what `godmode_bindings.write()`/`check()` iterate over. Paths are
# NOT declared here - `packaging/hosts.json`'s own `hook_manifests` section
# is the single source for those, same as every identity manifest's `path`
# already lives there and nowhere else. `build` returns the FULL artifact
# content for a dedicated file; Codex's `merge-into-shared` mode is handled
# specially by the caller, since it reads-then-patches an existing file
# rather than overwriting one wholesale.
# ---------------------------------------------------------------------------

HOOK_ARTIFACTS: dict[str, dict[str, Any]] = {
    "codex": {
        "mode": "merge-into-shared",
        "allowed_events": CODEX_HOOK_EVENTS,
    },
    "grok": {
        "mode": "merge-into-shared",
        "allowed_events": GROK_HOOK_EVENTS,
    },
    "cursor": {
        "mode": "dedicated",
        "build": build_cursor_manifest,
        "emitted": cursor_emitted_events,
        "allowed_events": CURSOR_HOOK_EVENTS,
        # Fix round 1, I2 (review Important): this gap was previously only
        # documented in `build_cursor_manifest`'s own docstring, invisible
        # to `hooks status`'s structured `gap` field - asymmetric with
        # Gemini's entry below, and a live violation of this module's own
        # governing rule that a gap is surfaced honestly, not silently
        # shipped as if confirmed.
        "gap": "plugin-root variable (${PLUGIN_ROOT}) is a best-effort choice "
               "for the hooks loader specifically - Addendum 5 names no "
               "plugin-root variable at all, and the Agent Plugins "
               "Specification v1.0.0 (the source of ${PLUGIN_ROOT}) "
               "explicitly excludes hooks from v1; unverified until a live "
               "probe confirms Cursor's hook loader expands it",
    },
    "antigravity": {
        "mode": "dedicated",
        "build": build_antigravity_fragment,
        "emitted": antigravity_emitted_events,
        "allowed_events": ANTIGRAVITY_HOOK_EVENTS,
        "gap": "schema transcribed from antigravity.google/docs/hooks, never "
               "probed live - the handler nesting and the {decision, reason} "
               "stdout contract hold on paper only until a live deny is "
               "chronicled; Stop not firing on Windows is field-confirmed "
               "(2026-08-29, IDE 1.107.0)",
    },
    "gemini": {
        "mode": "dedicated",
        "build": build_gemini_fragment,
        "emitted": gemini_emitted_events,
        "allowed_events": GEMINI_HOOK_EVENTS,
        "gap": "fragment only; no full gemini-extension.json is generated, "
               "and no auto-discovery path is verified - an installer must "
               "merge this file's \"hooks\" object by hand",
    },
}
