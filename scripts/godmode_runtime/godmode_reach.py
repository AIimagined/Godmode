"""Feature reach per host: which hook-borne feature can fire where, and why not.

Written 2026-09-08 from docs/HOST-FEATURE-REACH.md after an operator finding
that features built on Claude's events were assumed to work everywhere the
plugin installs. A feature reaches a host only when three things hold: an
event the host fires, a channel the host reads the hook's output on, and
live proof that the host dispatched the hook. Every cell below states one
of `yes` (all three), `partial` (wired, channel or proof missing), or `no`
(cannot fire today) with the reason, so `hooks status`, `doctor --host` and
the preflight gate read one table instead of prose.

The table is declared, not measured: a cell says what the code and the
hosts' own documentation say. Live proof is measured separately
(`unverifiable_hosts`), from the interception-proof records the hooks write.
"""
from __future__ import annotations

import re
from typing import Any

from . import godmode_host_manifests as host_manifests

HOSTS: tuple[str, ...] = (
    "claude", "codex", "grok", "cursor", "gemini", "antigravity",
    "copilot", "kiro", "opencode", "pi", "goose",
)

# Hosts that carry a hook manifest and can therefore be probed live.
HOOK_HOSTS: tuple[str, ...] = ("claude", "codex", "grok", "cursor", "gemini",
                                "antigravity", "copilot", "kiro")

FEATURES: tuple[str, ...] = (
    "pre-tool-gate",
    "advisories",
    "continuity-brief",
    "prompt-nudges",
    "claim-echo",
    "request-recording",
    "post-edit-findings",
    "done-bar",
    "stop-notices",
    "auto-checkpoint",
    "subagent-stop",
    "ask-decision",
)

_Y, _P, _N = "yes", "partial", "no"

# host -> feature -> (status, reason). Read from hooks/hooks.json, the
# per-host builders in godmode_host_manifests.py, the event branches in
# hooks/godmode_session_hook.py, and each host's documented channels.
_TABLE: dict[str, dict[str, tuple[str, str]]] = {
    "claude": {
        "pre-tool-gate": (_Y, "PreToolUse wired; permissionDecision read; live refusals chronicled"),
        "advisories": (_Y, "hookSpecificOutput.additionalContext reaches the model"),
        "continuity-brief": (_Y, "SessionStart additionalContext read"),
        "prompt-nudges": (_Y, "UserPromptSubmit stdout read"),
        "claim-echo": (_Y, "UserPromptSubmit stdout read"),
        "request-recording": (_Y, "UserPromptSubmit wired"),
        "post-edit-findings": (_Y, "PostToolUse additionalContext read"),
        "done-bar": (_Y, "Stop block read; live blocks chronicled"),
        "stop-notices": (_Y, "Stop systemMessage plus parked echo at the next prompt"),
        "auto-checkpoint": (_Y, "SessionEnd and PreCompact wired"),
        "subagent-stop": (_Y, "SubagentStop wired, advisory"),
        "ask-decision": (_Y, "permissionDecision ask is a real prompt"),
    },
    "codex": {
        "pre-tool-gate": (_Y, "PreToolUse fired live on Codex 0.153.4 Windows (PowerShell 7) through the project projection's commandWindows, 2026-09-09: a forced push was refused and Codex reported the block"),
        "advisories": (_P, "additionalContext documented on its PreToolUse wire; delivery to the model unproven live"),
        "continuity-brief": (_P, "SessionStart fired live 2026-09-09 (session anchor recorded); whether Codex feeds its stdout to the model is unproven"),
        "prompt-nudges": (_P, "UserPromptSubmit fired live 2026-09-09 (prompt-shape nudge recorded); stdout channel to the model unproven"),
        "claim-echo": (_P, "UserPromptSubmit fires; stdout channel to the model unproven"),
        "request-recording": (_Y, "UserPromptSubmit fired live 2026-09-09 and the ask was recorded"),
        "post-edit-findings": (_P, "PostToolUse declared since 2026-09-08; additionalContext documented; unproven live"),
        "done-bar": (_P, "Stop declared since 2026-09-08; unproven live"),
        "stop-notices": (_P, "Stop declared since 2026-09-08; unproven live"),
        "auto-checkpoint": (_Y, "SessionEnd fired live 2026-09-09 and wrote the auto checkpoint; PreCompact declared, unproven"),
        "subagent-stop": (_P, "SubagentStop declared since 2026-09-08; unproven live"),
        "ask-decision": (_P, "PreToolUse ask accepted by its wire; PermissionRequest deny dialect projected; unproven live"),
    },
    "grok": {
        "pre-tool-gate": (_Y, "PreToolUse wired; pinned live on 1.0.13 Windows via project-scope hooks"),
        "advisories": (_Y, "PreToolUse additionalContext delivered after the call"),
        "continuity-brief": (_Y, "SessionStart stdout ignored by Grok; the brief rides the first allowed call, pinned live"),
        "prompt-nudges": (_N, "an allowing UserPromptSubmit hook's stdout is discarded by Grok; only parked echoes re-route"),
        "claim-echo": (_Y, "rides the first allowed call as additionalContext"),
        "request-recording": (_Y, "UserPromptSubmit wired; recorded, nudges lost"),
        "post-edit-findings": (_N, "PostToolUse stdout ignored by Grok"),
        "done-bar": (_Y, "Stop block read"),
        "stop-notices": (_P, "operator text only; the model copy rides the next allowed call"),
        "auto-checkpoint": (_Y, "SessionEnd and PreCompact wired"),
        "subagent-stop": (_Y, "SubagentStop wired"),
        "ask-decision": (_N, "no ask in its dialect; folds to deny"),
    },
    "cursor": {
        "pre-tool-gate": (_P, "preToolUse and beforeShellExecution wired, failClosed; plugin-root expansion by its loader unverified"),
        "advisories": (_P, "agent_message on its own contract; unverified"),
        "continuity-brief": (_P, "sessionStart wired; channel unverified"),
        "prompt-nudges": (_P, "beforeSubmitPrompt wired since 2026-09-09; payload field names unverified"),
        "claim-echo": (_P, "beforeSubmitPrompt wired since 2026-09-09; unverified"),
        "request-recording": (_P, "beforeSubmitPrompt wired since 2026-09-09; unverified"),
        "post-edit-findings": (_P, "afterFileEdit wired since 2026-09-09; unverified"),
        "done-bar": (_P, "stop wired with followup_message under loop_limit 1; unverified"),
        "stop-notices": (_P, "stop wired; parked echo rides beforeSubmitPrompt; unverified"),
        "auto-checkpoint": (_P, "preCompact and sessionEnd wired since 2026-09-09; unverified"),
        "subagent-stop": (_P, "subagentStop wired since 2026-09-09; unverified"),
        "ask-decision": (_P, "permission ask is documented; unverified"),
    },
    "gemini": {
        "pre-tool-gate": (_P, "BeforeTool fragment; fail-open host; no proof"),
        "advisories": (_P, "fragment only; channel unverified"),
        "continuity-brief": (_P, "SessionStart fragment; channel unverified"),
        "prompt-nudges": (_N, "no prompt event in the fragment; Gemini's hooks list no prompt event godmode wires"),
        "claim-echo": (_N, "no prompt event wired"),
        "request-recording": (_N, "no prompt event wired"),
        "post-edit-findings": (_P, "AfterTool fragment since 2026-09-09; unverified"),
        "done-bar": (_N, "AfterAgent is not a stop block; Gemini's hooks cannot block a reply, so the done-bar cannot fire"),
        "stop-notices": (_P, "AfterAgent fragment since 2026-09-09 carries the notices as text; unverified"),
        "auto-checkpoint": (_N, "no session-end or compact event wired"),
        "subagent-stop": (_N, "no subagent event in Gemini's list"),
        "ask-decision": (_N, "no ask in its dialect; folds to deny"),
    },
    "antigravity": {
        "pre-tool-gate": (_Y, "PreToolUse wired; the gate confirmed in a live session"),
        "advisories": (_P, "reason on an allow; delivery unverified"),
        "continuity-brief": (_N, "no session event in its five-event list; PreInvocation is wired as the prompt boundary, and the brief needs a start"),
        "prompt-nudges": (_P, "PreInvocation wired since 2026-09-09 as the prompt boundary; unverified"),
        "claim-echo": (_P, "PreInvocation wired since 2026-09-09; unverified"),
        "request-recording": (_P, "PreInvocation wired since 2026-09-09; unverified"),
        "post-edit-findings": (_P, "PostToolUse wired since 2026-09-09; unverified"),
        "done-bar": (_P, "Stop wired; not firing on Windows is field-confirmed"),
        "stop-notices": (_P, "Stop wired; Windows gap as above"),
        "auto-checkpoint": (_N, "no session-end or compact event in its five-event list"),
        "subagent-stop": (_N, "no subagent event in its list"),
        "ask-decision": (_Y, "{decision, reason} carries ask unfolded"),
    },
    "copilot": {
        "pre-tool-gate": (_P, "PreToolUse wired in .github/hooks/godmode.json; render_decision has no dedicated copilot branch yet, so the exact deny shape it emits is unconfirmed"),
        "advisories": (_P, "top-level additionalContext documented for Copilot-shaped hosts; _advisory_body emits it nested-only (hookSpecificOutput.additionalContext), never top-level - a known gap, not merely unverified delivery"),
        "continuity-brief": (_P, "SessionStart wired; the emitter prints only the nested hookSpecificOutput.additionalContext there, not the top-level shape documented for Copilot-shaped hosts - a known gap, not merely unverified delivery"),
        "prompt-nudges": (_P, "UserPromptSubmit wired; delivery unverified"),
        "claim-echo": (_P, "UserPromptSubmit wired; delivery unverified"),
        "request-recording": (_P, "UserPromptSubmit wired; whether the event fires at all on Copilot is unconfirmed"),
        "post-edit-findings": (_P, "PostToolUse wired; delivery unverified"),
        "done-bar": (_P, "Stop wired; block delivery unverified"),
        "stop-notices": (_P, "Stop wired; notice delivery unverified"),
        "auto-checkpoint": (_P, "SessionEnd and PreCompact wired; unverified"),
        "subagent-stop": (_P, "SubagentStop wired; unverified"),
        "ask-decision": (_N, "no ask in the documented Copilot-shaped dialect; folds to deny"),
    },
    "kiro": {
        "pre-tool-gate": (_P, "a toolCall rule is wired in .kiro/hooks.json, routed through the launcher; Kiro's own event-name vocabulary beyond 'rule metadata that matches' is unread, so the trigger name is inferred, not confirmed"),
        "advisories": (_P, "HookResult's inject_context/modify factory is the plausible channel; unconfirmed"),
        "continuity-brief": (_N, "no session-start rule declared; the read documentation names no session-boundary event"),
        "prompt-nudges": (_N, "no prompt rule declared"),
        "claim-echo": (_N, "no prompt rule declared"),
        "request-recording": (_N, "no prompt rule declared"),
        "post-edit-findings": (_N, "no post-tool rule declared"),
        "done-bar": (_N, "no stop rule declared"),
        "stop-notices": (_N, "no stop rule declared"),
        "auto-checkpoint": (_N, "no session-end rule declared"),
        "subagent-stop": (_N, "no subagent rule declared"),
        "ask-decision": (_N, "ToolHookResult distinguishes a hard-security deny from a stateful-policy deny, not a documented ask; folds to deny"),
    },
    "opencode": {
        "pre-tool-gate": (_P, "tool.execute.before shim relays a deny as a throw; one live block chronicled"),
        "advisories": (_N, "no channel from the shim to the model"),
        "continuity-brief": (_N, "no session event in the shim"),
        "prompt-nudges": (_N, "no prompt event in the shim"),
        "claim-echo": (_N, "no prompt event in the shim"),
        "request-recording": (_N, "no prompt event in the shim"),
        "post-edit-findings": (_N, "no post-tool event in the shim"),
        "done-bar": (_N, "no stop event in the shim"),
        "stop-notices": (_N, "no stop event in the shim"),
        "auto-checkpoint": (_N, "no session-end event in the shim"),
        "subagent-stop": (_N, "no subagent event in the shim"),
        "ask-decision": (_N, "a deny is a throw; no ask surface"),
    },
    "pi": {
        "pre-tool-gate": (_P, "tool_call extension; pi has no permission surface, so a deny is advisory"),
        "advisories": (_N, "no channel"),
        "continuity-brief": (_N, "no session event"),
        "prompt-nudges": (_N, "no prompt event"),
        "claim-echo": (_N, "no prompt event"),
        "request-recording": (_N, "no prompt event"),
        "post-edit-findings": (_N, "no post-tool event"),
        "done-bar": (_N, "no stop event"),
        "stop-notices": (_N, "no stop event"),
        "auto-checkpoint": (_N, "no session-end event"),
        "subagent-stop": (_N, "no subagent event"),
        "ask-decision": (_N, "no permission surface"),
    },
    "goose": {
        "pre-tool-gate": (_N, "MCP server exposes verbs as tools; no hook surface"),
        "advisories": (_N, "no hook surface"),
        "continuity-brief": (_P, "the resume tool is available on demand; nothing fires it"),
        "prompt-nudges": (_N, "no hook surface"),
        "claim-echo": (_N, "no hook surface"),
        "request-recording": (_N, "no hook surface"),
        "post-edit-findings": (_N, "no hook surface"),
        "done-bar": (_N, "no hook surface"),
        "stop-notices": (_N, "no hook surface"),
        "auto-checkpoint": (_P, "the checkpoint tool is available on demand; nothing fires it"),
        "subagent-stop": (_N, "no hook surface"),
        "ask-decision": (_N, "no hook surface"),
    },
}

# Replication provenance per hook host (same keys as `HOOK_HOSTS`, the only
# hosts `unverifiable_hosts` ever names). `reference` is a private ledger
# entry id (never a name - `"ledger:<n>"` is the whole shape); `replication_test`
# is the dotted unittest id that reproduces the referenced behaviour against
# our own launcher; `next_probe` is the date a live confirmation is
# scheduled. Empty strings mean "not yet".
#
# `live_proof` (Task 5 fix round 1, B1): a citation to the host's own newest
# `hook-interception-proof` chronicle record - the exact record `last_proof()`
# (`godmode_hookproof.py`) would read for this host, and therefore the exact
# evidence `unverifiable_hosts()`/`reach_finding()` already treat as "this
# host is not unverifiable". Cited as `seq:<n>` (the record's chronicle
# sequence number) plus its recorded date and the `hook_version` it carried -
# never a host name literal standing in for "trust me, it happened". Read
# read-only from this project's own archive (`godmode history --kind action
# --subject hook-interception-proof`) on 2026-09-17: Claude's newest record
# is sequence 13288 (2026-09-13, hook_version 0.3.26); Grok's is sequence
# 2557 (2026-08-19, hook_version 0.3.0). Codex also carries proof records in
# that archive (sequence 2554, 2026-08-19) but is deliberately left without
# a `live_proof` entry here: unlike claude/grok, codex's exemption was never
# claimed on live-session grounds - it already carries its own
# reference+replication_test pair (below), and widening the exemption to a
# host that did not ask for it is not this fix's job. A host with an empty
# `live_proof` is not "unverifiable" by construction of this field alone -
# it just falls back to the reference/replication_test citation requirement
# `MATRIX_CITATION_HOSTS` still enforces for it.
#
# R-0 correction (Task 5, 2026-09-17): the private R-1 hook-mechanism table
# is the only place these ids are checked against, and two of the three
# below were wrong. `ledger:103` (gemini's prior reference) is the R-1
# table's own excluded entry - not hook-bearing at all, no hooks manifest of
# any kind. `ledger:109` (antigravity's prior reference) names no entry in
# the R-1 table in either direction; it never resolved to anything. Both are
# replaced with ids the table actually backs: `ledger:174` opens a real
# per-tool-call hooks manifest naming Gemini specifically - the one entry in
# the whole table that is Gemini-specific hook evidence; `ledger:158` is a
# per-host generator that writes Antigravity's own native hook-config file
# among several targets. `ledger:99` (cursor's reference) was already
# correct - its entry is entirely about Cursor's own hooks-manifest dialect
# (root-variable expansion, the stop hook's `followup_message`/`loop_limit`
# shape this module's own `build_cursor_manifest` already replicates) - kept
# unchanged.
REACH: dict[str, dict[str, str]] = {
    "claude": {"reference": "", "replication_test": "", "next_probe": "",
               "live_proof": "seq:13288 (2026-09-13, hook_version 0.3.26)"},
    "codex": {"reference": "ledger:193",
              "replication_test": "tests.test_launcher_root_fallback.LauncherTests.test_windows_prefers_py_launcher_with_3_flag",
              "next_probe": "post-0.3.28", "live_proof": ""},
    "grok": {"reference": "", "replication_test": "", "next_probe": "",
             "live_proof": "seq:2557 (2026-08-19, hook_version 0.3.0)"},
    "cursor": {"reference": "ledger:99", "replication_test": "", "next_probe": "",
               "live_proof": ""},
    "gemini": {"reference": "ledger:174", "replication_test": "", "next_probe": "",
               "live_proof": ""},
    "antigravity": {"reference": "ledger:158", "replication_test": "", "next_probe": "",
                    "live_proof": ""},
    # NS-6 (Task 6): both replicated from the private R-1 table's own rows
    # against this module's manifest builders - `replication_test` names
    # the dotted unittest id that feeds the reference's own input shape and
    # asserts Godmode's manifest against it.
    # N9 (Task 6 fix round 1): two ids, not one - the row's `pre-tool-gate`
    # shape rests on `ledger:3` (Copilot's `.github/hooks/` grouping), but
    # its `advisories`/`continuity-brief` reason cells above and
    # `HOOK_ARTIFACTS["copilot"]["gap"]` both also cite `ledger:15` for the
    # top-level additionalContext dialect - a citation column that named
    # only the first under-cited the row's own stated basis.
    "copilot": {"reference": "ledger:3, ledger:15",
                "replication_test": "tests.test_host_manifests.CopilotManifestTests."
                                     "test_replicates_the_shared_hooks_json_shape",
                "next_probe": "post-0.3.28", "live_proof": ""},
    "kiro": {"reference": "ledger:92",
             "replication_test": "tests.test_host_manifests.KiroManifestTests."
                                  "test_replicates_the_declarative_rule_shape",
             "next_probe": "post-0.3.28", "live_proof": ""},
}


# R-3a: a named fallback tier instead of "unverifiable" for a host with no
# hook dispatch. Closed set - a host missing from this dict, or carrying a
# value outside `TIERS`, fails `validate_tiers()` (the matrix test this
# guards; R-4's generated matrix, once it lands, refuses the same way for
# the identical reason: a row that cannot say what it is is not a row).
# `hook` = the host fires a hook per `HOOK_ARTIFACTS`/this module's
# `HOOK_HOSTS`; `shim` = a language-runtime shim relays the decision
# (opencode); `mcp` = the surface is an on-demand MCP tool, no hook fires
# it (goose); `none` = no dispatch and no shim surface at all (pi).
TIERS: tuple[str, ...] = ("hook", "shim", "mcp", "none")

TIER: dict[str, str] = {
    "claude": "hook",
    "codex": "hook",
    "grok": "hook",
    "cursor": "hook",
    "gemini": "hook",
    "antigravity": "hook",
    "copilot": "hook",
    "kiro": "hook",
    "opencode": "shim",
    "pi": "none",
    "goose": "mcp",
}


def host_tier(host: str) -> str:
    """The named fallback tier for `host`, or `""` if it carries none."""
    return TIER.get(host, "")


def validate_tiers() -> list[str]:
    """Every declared host must carry a tier from the closed `TIERS` set,
    and `TIER` must carry no entry for a host that is not declared.

    Returns the offending host names - empty means the matrix is clean. A
    non-empty result is what `hooks status`/the matrix test treat as a
    failure: a host row without a tier is refused, not defaulted, and (N4,
    task-3-review.md) a stale `TIER` entry for a host that no longer exists
    in `HOSTS` is refused too, not silently ignored - `HOSTS` iteration
    alone would never see a key it does not ask for.
    """
    missing_or_invalid = {host for host in HOSTS if TIER.get(host) not in TIERS}
    stale = {host for host in TIER if host not in HOSTS}
    return sorted(missing_or_invalid | stale)


def reach_metadata() -> dict[str, dict[str, str]]:
    return {host: dict(fields) for host, fields in REACH.items()}


# NS-10b: which `godmode_host_manifests.STDOUT_CHANNELS` member a feature
# needs to reach the model or the operator at all - a tuple means "any one
# of these", `None` means the feature needs no output channel (it fires
# because its EVENT fires; the archive write/checkpoint/recording IS the
# effect, not something read back from stdout). Read from the same emitters
# `_TABLE`'s own per-cell reasons already cite: `hookSpecificOutput.
# permissionDecision` gates (deny/ask), `additionalContext` carries a
# message to the model, `systemMessage` carries one to the operator (Stop's
# parked-echo pattern accepts either, since the echo can ride the next
# prompt's additionalContext instead).
FEATURE_CHANNELS: dict[str, tuple[str, ...] | None] = {
    "pre-tool-gate": ("deny",),
    "advisories": ("additionalContext",),
    "continuity-brief": ("additionalContext",),
    "prompt-nudges": ("additionalContext",),
    "claim-echo": ("additionalContext",),
    "request-recording": None,
    "post-edit-findings": ("additionalContext",),
    "done-bar": ("deny",),
    "stop-notices": ("systemMessage", "additionalContext"),
    "auto-checkpoint": None,
    "subagent-stop": ("additionalContext",),
    "ask-decision": ("ask",),
}


def _capability_unreachable(host: str, feature: str) -> bool:
    """True when `feature` needs a channel `host_manifests.HOST_CAPABILITIES`
    does not declare for `host` - NS-10b's own acceptance line: "a feature
    that needs a channel the host does not declare is reported as
    unreachable before any probe." An unmapped feature is never flagged
    unreachable by this alone - only a declared, missing channel is.

    `host` MUST already be a `HOST_CAPABILITIES` key - a plain `[...]`
    lookup, deliberately not `.get(host, {})` (fix round 1, nit 2/3): a host
    declared in `HOSTS`/`_TABLE` but missing from `HOST_CAPABILITIES` is a
    defect in this module, and defaulting to "declares nothing" would hide
    it behind a row that silently reads all-`no` instead of raising loudly
    where the mistake was made.
    """
    needed = FEATURE_CHANNELS.get(feature)
    if not needed:
        return False
    declared = host_manifests.HOST_CAPABILITIES[host]["stdout"]
    return not any(channel in declared for channel in needed)


def reach_table() -> dict[str, dict[str, dict[str, str]]]:
    """host -> feature -> {status, reason}; every cell present.

    A cell already `no` stays as authored. A `yes`/`partial` cell whose
    feature needs a channel `host_manifests.HOST_CAPABILITIES` does not
    declare for this host is downgraded to `no` here, with the reason
    naming the missing channel - the enum overrides an optimistic reading,
    never the reverse: no cell is ever upgraded by this function.
    """
    table: dict[str, dict[str, dict[str, str]]] = {}
    for host in HOSTS:
        row = _TABLE[host]
        cells: dict[str, dict[str, str]] = {}
        for feature in FEATURES:
            status, reason = row[feature]
            if status != "no" and _capability_unreachable(host, feature):
                needed = FEATURE_CHANNELS[feature]
                channel = " or ".join(needed)
                status = "no"
                reason = (f"{reason} - unreachable: {host} does not declare "
                          f"the {channel} channel")
            cells[feature] = {"status": status, "reason": reason}
        table[host] = cells
    return table


def host_reach(host: str) -> dict[str, Any]:
    """One host's row plus the features that cannot fire there, for `doctor --host`."""
    if host not in _TABLE:
        return {"host": host, "known": False, "features": {}, "cannot_fire": [], "partial": []}
    row = reach_table()[host]
    return {
        "host": host,
        "known": True,
        "features": row,
        "cannot_fire": [f for f in FEATURES if row[f]["status"] == "no"],
        "partial": [f for f in FEATURES if row[f]["status"] == "partial"],
        "fires": [f for f in FEATURES if row[f]["status"] == "yes"],
    }


def unverifiable_hosts(archive: Any) -> list[str]:
    """Declared hook hosts with no interception proof on this archive."""
    from .godmode_hookproof import last_proof

    missing = []
    for host in HOOK_HOSTS:
        try:
            proof = last_proof(archive, host)
        except Exception:  # noqa: BLE001 - an unreadable archive proves nothing
            proof = None
        if proof is None:
            missing.append(host)
    return missing


def reach_finding(archive: Any) -> dict[str, str] | None:
    """The preflight judgment finding: a declared host with no live proof.

    The old finding knew two states: live proof or nothing, so it always
    blocked. A host whose hook path is instead replicated from a code-level
    read and pinned by a test is not on paper - it is proven by replication
    and awaits a live confirmation, so it is reported (advisory), never
    blocking, as long as it names its replication test or the entry still
    to read. Only a host with neither still blocks the gate.
    """
    hosts = unverifiable_hosts(archive)
    if not hosts:
        return None
    meta = reach_metadata()
    bare = [h for h in hosts
            if not (meta.get(h, {}).get("replication_test") or meta.get(h, {}).get("reference"))]
    severity = "blocking" if bare else "advisory"
    detail = (f"{len(hosts)} declared hook host(s) unverifiable on this archive "
              f"({', '.join(hosts)}): ")
    if bare:
        detail += (f"{', '.join(bare)} cite no replication test and no reference to read - "
                   "replicate the host's hook path from a read implementation and pin it "
                   "with a test, or name the entry still to read")
    else:
        probes = sorted(h for h in hosts if meta.get(h, {}).get("next_probe"))
        detail += "each cites its replication test or the entry still to read"
        if probes:
            detail += f"; live confirmation scheduled for host(s) {', '.join(probes)}"
        else:
            detail += "; no live confirmation scheduled yet"
    return {"check": "host-reach", "severity": severity, "detail": detail}


# ---------------------------------------------------------------------------
# R-4 + R-0 guard: `docs/HOST-FEATURE-REACH.md` generated by `godmode hooks
# status --matrix [--write]`, never hand-typed. The doc keeps its own prose
# (intro, root-causes narrative, the verb-layer census, the dated status
# log) as a template outside one marker pair; this module only ever
# rewrites what sits between the markers - the tables this data model
# actually owns.
# ---------------------------------------------------------------------------

MATRIX_BEGIN = "<!-- godmode:matrix:begin -->"
MATRIX_END = "<!-- godmode:matrix:end -->"

# Fix round 1, B1: a host is excluded from the static citation requirement
# below when, and only when, its own `REACH` row carries a `live_proof`
# citation - never a hardcoded name tuple. Claude and Grok qualify today
# because both carry a dated `hook-interception-proof` record this project's
# own archive holds (see the `live_proof` comment above `REACH`); every
# OTHER declared hook host has no such record on file, so it always needs a
# reference or a replicating test, whatever a given probe's own archive
# proof state says (`reach_finding` is the archive-scoped version of this
# same rule; this is the always-on, archive-free floor the generator itself
# enforces before printing a single row). Adding a `live_proof` citation to
# any other host's `REACH` row - never editing this tuple by hand - is what
# widens the exemption; the derivation, not a comment, is what enforces it.
MATRIX_CITATION_HOSTS: tuple[str, ...] = tuple(
    host for host in HOOK_HOSTS if not REACH.get(host, {}).get("live_proof"))


class MatrixGuardError(Exception):
    """R-0: the matrix generator refuses a host row that cites neither a
    reference read nor a replicating test."""


# Fix round 1, nit 4: `reference` is a private ledger entry id and nothing
# else - the whole shape is `ledger:<digits>`. A bare truthy check (any
# nonempty string) let an empty-but-truthy typo or a name slip through
# uncaught; it would not by itself have caught the wrong-ID bug this task's
# R-0 correction fixed (a wrongly-numbered but still shape-valid id), but it
# closes the cheaper, more likely failure mode in the same guard, at the
# same cost.
#
# Task 6 fix round 1 (N9): widened to allow more than one citation
# (`"ledger:3, ledger:15"`) for a row whose shape rests on more than one
# ledger entry - each still bare `ledger:<digits>`, comma-joined, never a
# name or free text; the privacy shape this regex exists to enforce is
# per-id, not "exactly one id per row".
_LEDGER_REFERENCE_RE = re.compile(r"^ledger:\d+(, ledger:\d+)*$")


def validate_reach_citations(hosts: tuple[str, ...] = MATRIX_CITATION_HOSTS) -> list[str]:
    """Every host in `hosts` must carry a shape-valid `ledger:<digits>`
    `reference` or a `replication_test` in `REACH` - the static, always-on
    half of R-0's guard (`reach_finding` is the archive-scoped half).
    Returns the offending host names, sorted; empty means the matrix
    generator may proceed.
    """
    offenders = []
    for host in hosts:
        meta = REACH.get(host, {})
        reference = meta.get("reference", "")
        reference_ok = bool(_LEDGER_REFERENCE_RE.match(reference))
        if not (reference_ok or meta.get("replication_test")):
            offenders.append(host)
    return sorted(offenders)


_OS_LABEL = {"windows": "Windows", "linux": "Linux", "macos": "macOS"}


def _capabilities_table() -> str:
    lines = ["| Host | Tier | Declared events | Declared stdout channels | OS |",
             "|---|---|---|---|---|"]
    for host in HOSTS:
        # Fix round 1, nit 2/3: a plain `[...]` lookup, not `.get(host, {})`
        # - a host declared here with no `HOST_CAPABILITIES` entry is a
        # defect in that module, and must fail loudly (`KeyError`) rather
        # than silently render as "none | none | none", which reads exactly
        # like a host that genuinely declares nothing.
        capability = host_manifests.HOST_CAPABILITIES[host]
        events = ", ".join(sorted(capability["events"])) or "none"
        channels = ", ".join(sorted(capability["stdout"])) or "none"
        oses = (", ".join(_OS_LABEL[name] for name in sorted(capability["os"]))
                or "none")
        lines.append(f"| {host} | {host_tier(host)} | {events} | {channels} | {oses} |")
    return "\n".join(lines)


def _reference_cell(meta: dict[str, str]) -> str:
    """A source is either read already or still to read - never the id.

    A bare `reference` names an entry still to read. The one exception
    this module can tell apart from the reference alone: a host that also
    carries a `replication_test` has had that entry's mechanism actually
    reproduced against our own code (you cannot write a passing
    replicating test against an entry you never read), so that row
    honestly says "read" instead. Either way, the entry's own internal
    id never reaches this cell - a shipped doc names what state a source
    is in, not which private record backs it.
    """
    reference = meta.get("reference") or ""
    if not reference:
        return "(not required - live proof)" if meta.get("live_proof") else "(none - still to read)"
    if meta.get("replication_test"):
        return "(read)"
    return "(still to read)"


_LIVE_PROOF_RE = re.compile(r"^seq:\d+ \(([^,]+), hook_version ([^)]+)\)$")


def _neutral_live_proof(value: str) -> str:
    """Render a `live_proof` citation without its archive sequence number.

    The stored shape (`seq:<n> (<date>, hook_version <v>)`) is this
    project's own internal citation for the exact chronicle record that
    proves a host; a shipped doc states what was proven and when, not the
    internal record number. `seq:13288 (2026-09-13, hook_version 0.3.26)`
    renders as `live proof, 2026-09-13, hook 0.3.26`. A value not in that
    shape (empty, or a future format) passes through unchanged.
    """
    if not value:
        return value
    match = _LIVE_PROOF_RE.match(value)
    if not match:
        return value
    date, hook_version = match.groups()
    return f"live proof, {date}, hook {hook_version}"


def _reference_table() -> str:
    lines = ["| Host | Reference (read / still to read) | Replication test | "
             "Next live probe | Live proof |",
             "|---|---|---|---|---|"]
    for host in HOOK_HOSTS:
        meta = REACH.get(host, {})
        reference = _reference_cell(meta)
        test = f"`{meta['replication_test']}`" if meta.get("replication_test") else "(none)"
        probe = meta.get("next_probe") or "(none scheduled)"
        live_proof = _neutral_live_proof(meta.get("live_proof") or "") or "(none)"
        lines.append(f"| {host} | {reference} | {test} | {probe} | {live_proof} |")
    return "\n".join(lines)


def _feature_reach_grid() -> str:
    table = reach_table()
    header = "| Feature | " + " | ".join(HOSTS) + " |"
    separator = "|---|" + "---|" * len(HOSTS)
    lines = [header, separator]
    for feature in FEATURES:
        cells = [table[host][feature]["status"] for host in HOSTS]
        lines.append(f"| {feature} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _feature_reach_reasons_table() -> str:
    """Fix round 1, B2: every non-`yes` cell's stated reason, the half of
    `reach_table()`'s own data model the status grid alone throws away -
    including the enum-derived "unreachable: <host> does not declare the
    <channel> channel" text `reach_table()` computes for a capability
    downgrade. This is what makes the doc's own opening line ("every 'no'
    here is a stated gap") true of the generated block, not just its prose.
    """
    table = reach_table()
    lines = ["| Host | Feature | Status | Reason |", "|---|---|---|---|"]
    for host in HOSTS:
        for feature in FEATURES:
            cell = table[host][feature]
            if cell["status"] == "yes":
                continue
            reason = cell["reason"].replace("|", "/")
            lines.append(f"| {host} | {feature} | {cell['status']} | {reason} |")
    return "\n".join(lines)


def render_matrix_tables() -> str:
    """The generated content for the marker pair - four tables, none
    hand-typed: declared capabilities (NS-10b's enum), each hook host's
    replication provenance (R-0, including its own live-proof citation),
    the feature-reach grid (`_TABLE`, with `reach_table()`'s own
    channel-derived downgrades already applied), and the reason behind
    every non-`yes` cell in that grid.

    Raises `MatrixGuardError` (R-0 guard) before rendering anything if any
    of `MATRIX_CITATION_HOSTS` cites neither a reference nor a test.
    """
    offenders = validate_reach_citations()
    if offenders:
        raise MatrixGuardError(
            "refusing to generate the host matrix: "
            f"{', '.join(offenders)} cite no reference and no replication "
            "test - name the source still to read, or pin a "
            "replicating test, before regenerating docs/HOST-FEATURE-REACH.md")
    parts = [
        "### Declared capabilities",
        "",
        "Read straight from `godmode_host_manifests.HOST_CAPABILITIES` - a "
        "closed enum, not prose; `tests.test_host_manifests` fails a "
        "manifest that declares a channel or OS outside it.",
        "",
        _capabilities_table(),
        "",
        "### Replication provenance",
        "",
        "Every hook host cites the source read, or names the source "
        "still to read, and/or the test that replicates its mechanism - or "
        "the matrix generator itself refuses (`validate_reach_citations`) "
        'rather than printing a bare "unverifiable" row. A host whose Live '
        'proof column is not "(none)" is exempt from that citation '
        "requirement instead (`MATRIX_CITATION_HOSTS`, derived from this "
        "same table, never a hardcoded host name): it is proven by a "
        "chronicled live session - the interception-proof record cited "
        "there - rather than by replication.",
        "",
        _reference_table(),
        "",
        "### Feature reach",
        "",
        "Legend: **yes** = event wired, channel declared, live proof; "
        "**partial** = wired, channel unverified or proof missing; **no** = "
        "the feature cannot fire on that host today - including a feature "
        "whose one needed channel the host's own capability enum does not "
        "declare (unreachable before any probe). Every non-`yes` "
        "cell's reason is stated in the reasons table below.",
        "",
        _feature_reach_grid(),
        "",
        "### Feature reach reasons",
        "",
        "The reason behind every non-`yes` cell above, `reach_table()`'s "
        "own per-cell text - the authored note, or, for a capability-driven "
        "downgrade, the enum-derived \"unreachable: <host> does not declare "
        "the <channel> channel\" statement.",
        "",
        _feature_reach_reasons_table(),
    ]
    return "\n".join(parts)


def generate_matrix_document(current_text: str) -> str:
    """Splice `render_matrix_tables()` between `MATRIX_BEGIN`/`MATRIX_END`
    in `current_text`, leaving everything else - the doc's own prose
    preamble and its dated narrative tail - byte-for-byte untouched.

    Raises `ValueError` if the marker pair is not both present, and
    propagates `MatrixGuardError` from the R-0 guard before touching
    anything (`render_matrix_tables()` runs the guard first).
    """
    body = render_matrix_tables()
    if MATRIX_BEGIN not in current_text or MATRIX_END not in current_text:
        raise ValueError(
            f"docs/HOST-FEATURE-REACH.md is missing its {MATRIX_BEGIN!r}/"
            f"{MATRIX_END!r} marker pair; the generator has nowhere to write")
    before, rest = current_text.split(MATRIX_BEGIN, 1)
    _old_body, after = rest.split(MATRIX_END, 1)
    return f"{before}{MATRIX_BEGIN}\n\n{body}\n\n{MATRIX_END}{after}"
