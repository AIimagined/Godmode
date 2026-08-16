"""CX-3: native per-host hook manifests, generated from one mechanism.

CX-2 taught the runtime to *read* five hosts' dialects through one adapter
(`godmode_hostevent.py`). CX-3 is the other half: teaching the *package* to
*ship* a manifest each host actually loads, so the adapter has something to
be called by in the first place. Before this unit, only Claude's hand-authored
`hooks/hooks.json` wired a real pre-tool boundary; Codex's own matcher never
named a Codex tool, Grok's `${CLAUDE_PLUGIN_ROOT}` never resolves on Grok
(no such variable exists there), and Cursor had no hook manifest at all.

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

**File-layout decision (not a guessed host fact - an architectural choice,
documented so it can be revisited):** Codex's own build doc names
`"hooks": "./hooks/hooks.json"` in its example manifest (spec Addendum 2,
CONFIRMED verified fetch) - the SAME default-detected path Claude already
uses. So Codex's two native event keys (`session_start`, `pre_tool_use`) are
MERGED into the existing shared `hooks/hooks.json`, leaving every one of
Claude's own keys byte-for-byte untouched (`merge_codex_into_shared`).
Grok, Cursor, and Gemini get their OWN dedicated files under their own host
directory instead: Addendum 3's CX-3 implication explicitly recommends
"host-specific hook manifests carried per host... host dirs" over three
bespoke files, and Grok's own documented command shape (a single string,
never an args array - Addendum 6) is structurally incompatible with the
array-based entries the shared file already carries for Claude - merging
them into one file would require one JSON key to mean two different things
at once, which is not possible. Cursor's `"version": 1` envelope and
`failClosed` field, and Gemini's settings.json-fragment shape, are equally
host-specific, so they follow the same per-host-directory pattern.
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

# Addendum 2 (spec, verified fetch): the Codex build doc's own event example
# is CamelCase ("SessionStart"), but the ONLY two event identifiers this repo
# has live evidence for are the operator's Sol audit's own two observations -
# "session_start registered" and "pre_tool_use supported" - both snake_case.
# Given the build doc explicitly says the full event list is NOT published
# and instructs verification before emission, the live-audit spelling is what
# ships; `user_prompt_submit` (a candidate in the Plan's ORIGINAL, PRE-spec
# red-test line) has no audit or doc confirmation at all and is OMITTED - a
# gap `hooks status`/`hooks install --host codex` reports, not a guess.
CODEX_HOOK_EVENTS = frozenset({"session_start", "pre_tool_use"})

# Plan amendments (CX-3 additions, spec Addendum 6 verbatim): "register
# PreCompact + SessionEnd" alongside Addendum 2026-08-16's own confirmed
# CamelCase config-event list (SessionStart, UserPromptSubmit, PreToolUse,
# ..., PreCompact, ..., verbatim spellings). Grok's own docs describe these
# CONFIG keys as "largely CLAUDE-COMPATIBLE" - only the stdin envelope's
# `hookEventName` VALUE is snake_case, never the hooks.json KEY.
GROK_HOOK_EVENTS = frozenset({
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PreCompact", "SessionEnd",
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

# Plan amendments (CX-3 additions, verbatim): "Grok manifest: single-string
# command + commandWindows (no args array); matcher union
# Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit|run_terminal_command|
# search_replace|write". Built from `hostevent.CLAUDE_TOOLS`'s fenced/shell
# subset plus `hostevent.GROK_TOOLS` so this string can never silently drift
# from what the adapter itself recognises - but the ORDER is the plan's own
# verbatim text (not the constants' natural iteration order), because that
# exact string is what a test pins against the plan.
GROK_MATCHER = "Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit|run_terminal_command|search_replace|write"

# Addendum 2 confirmed fact + CX-3's own instruction: Codex's matcher is the
# union of every tool `godmode_hostevent._adapt_codex` recognises, including
# the orchestration wrapper (`functions.exec`) so a nested call reaches the
# gate at all - built FROM `hostevent.CODEX_TOOLS`, never re-typed.
CODEX_MATCHER = "|".join(sorted(hostevent.CODEX_TOOLS))

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


# ---------------------------------------------------------------------------
# Shared plumbing.
# ---------------------------------------------------------------------------

SESSION_HOOK = "hooks/godmode_session_hook.py"
GATE_FAST_HOOK = "hooks/godmode_gate_fast.py"


def _claude_style_entry(root_var: str, script: str, *args: str, timeout: int) -> dict[str, Any]:
    """Claude/Codex's shared array-based hook-entry shape: `command` is the
    bare interpreter, `args` is a list, unchanged from the pre-CX-3 file.
    """
    return {
        "type": "command",
        "command": "python",
        "args": [f"{root_var}/{script}", *args] if args else [f"{root_var}/{script}"],
        "timeout": timeout,
    }


def _single_string_entry(root_var: str, script: str, *args: str, timeout: int) -> dict[str, Any]:
    """Grok's own documented shape (Addendum 6, "HOOK CONFIG FORMAT" bullet):
    `command` is ONE string (POSIX-separated), `commandWindows` the same
    invocation with backslash path separators - never an `args` array, which
    Grok's own docs single out as the outlier that fails open if a host drops
    it (a bare `python` with no arguments runs and times out).
    """
    tail = " ".join(args)
    posix = f'python "{root_var}/{script}"' + (f" {tail}" if tail else "")
    windows_script = script.replace("/", "\\")
    windows = f'python "{root_var}\\{windows_script}"' + (f" {tail}" if tail else "")
    return {
        "type": "command",
        "command": posix,
        "commandWindows": windows,
        "timeout": timeout,
    }


# ---------------------------------------------------------------------------
# Codex: merge two native, snake_case keys into the SHARED hooks/hooks.json.
# ---------------------------------------------------------------------------


def merge_codex_into_shared(existing: dict[str, Any]) -> dict[str, Any]:
    """Return `existing` (Claude's hand-authored `hooks/hooks.json`) with
    Codex's own two verified event keys inserted/overwritten - every OTHER
    top-level key stays byte-identical, insertion order preserved, so
    Claude's own behavior and the file's `check()`/`write()` diff for a
    Claude-only edit are both unaffected by this function ever having run.

    `${PLUGIN_ROOT}` is Codex's NATIVE root variable (Addendum 2, verified
    fetch: "${PLUGIN_ROOT} and ${PLUGIN_DATA}... CLAUDE_PLUGIN_ROOT... as
    legacy aliases") - CX-3's own binding instruction is to use the native
    spelling here, never the legacy alias, even though the alias would also
    resolve.
    """
    merged = dict(existing)
    merged["hooks"] = dict(existing.get("hooks") or {})
    merged["hooks"]["session_start"] = [
        {"hooks": [_claude_style_entry("${PLUGIN_ROOT}", SESSION_HOOK, "session-start", timeout=10)]},
    ]
    merged["hooks"]["pre_tool_use"] = [
        {
            "matcher": CODEX_MATCHER,
            "hooks": [_claude_style_entry("${PLUGIN_ROOT}", GATE_FAST_HOOK, timeout=3)],
        },
    ]
    return merged


def codex_emitted_events() -> frozenset[str]:
    return frozenset({"session_start", "pre_tool_use"})


# ---------------------------------------------------------------------------
# Grok: dedicated `.grok-plugin/hooks.json`.
# ---------------------------------------------------------------------------


def build_grok_manifest() -> dict[str, Any]:
    """Grok's own native manifest - CamelCase event keys (Addendum 6: "largely
    CLAUDE-COMPATIBLE"), single-string command entries (Addendum 6), the
    matcher union from the Plan's CX-3 additions verbatim, and PreCompact +
    SessionEnd registered per the same addition ("script already implements
    pre-compact/session-end branches" - verified above at
    `hooks/godmode_session_hook.py`'s `main()`, which accepts exactly these
    two `event` choices).

    Timeouts are this module's own explicit choice, not a documented Grok
    fact: Addendum 6 says Grok's hook timeout defaults to 5s and FAILS OPEN
    past it, and instructs "an explicit generous timeout" - so every entry
    below sets one well above the fast gate's own <150ms median budget
    (`docs/superpowers/plans/2026-08-16-codex-compat.md`'s Global
    Constraints) while staying finite and bounded, never unbounded.
    """
    root = "${GROK_PLUGIN_ROOT}"
    return {
        "description": "Godmode continuity + pre-tool gate for Grok's native plugin loader.",
        "hooks": {
            "SessionStart": [
                {"hooks": [_single_string_entry(root, SESSION_HOOK, "session-start", timeout=10)]},
            ],
            "UserPromptSubmit": [
                {"hooks": [_single_string_entry(root, SESSION_HOOK, "user-prompt", timeout=30)]},
            ],
            "PreToolUse": [
                {
                    "matcher": GROK_MATCHER,
                    "hooks": [_single_string_entry(root, GATE_FAST_HOOK, timeout=8)],
                },
            ],
            "PreCompact": [
                {"hooks": [_single_string_entry(root, SESSION_HOOK, "pre-compact", timeout=15)]},
            ],
            "SessionEnd": [
                {"hooks": [_single_string_entry(root, SESSION_HOOK, "session-end", timeout=15)]},
            ],
        },
    }


def grok_emitted_events(manifest: dict[str, Any]) -> frozenset[str]:
    return frozenset(manifest.get("hooks", {}).keys())


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
    placeholder is UNVERIFIED. `hooks status`/`hooks install --host cursor`
    must report this specific gap; it is never asserted as a confirmed fact.
    """
    root = "${PLUGIN_ROOT}"
    return {
        "version": 1,
        "hooks": {
            "sessionStart": [
                {"hooks": [_claude_style_entry(root, SESSION_HOOK, "session-start", timeout=10)]},
            ],
            "preToolUse": [
                {
                    "matcher": "Shell|Write|Edit|Delete",
                    "failClosed": True,
                    "hooks": [_claude_style_entry(root, GATE_FAST_HOOK, timeout=3)],
                },
            ],
            "beforeShellExecution": [
                {
                    "matcher": CURSOR_SHELL_TEXT_MATCHER,
                    "failClosed": True,
                    "hooks": [_claude_style_entry(root, GATE_FAST_HOOK, timeout=3)],
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
                            "command": f"python {root}/{GATE_FAST_HOOK}",
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
        "mode": "dedicated",
        "build": build_grok_manifest,
        "emitted": grok_emitted_events,
        "allowed_events": GROK_HOOK_EVENTS,
    },
    "cursor": {
        "mode": "dedicated",
        "build": build_cursor_manifest,
        "emitted": cursor_emitted_events,
        "allowed_events": CURSOR_HOOK_EVENTS,
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
