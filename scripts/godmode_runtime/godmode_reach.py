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

from typing import Any

HOSTS: tuple[str, ...] = (
    "claude", "codex", "grok", "cursor", "gemini", "antigravity",
    "opencode", "pi", "goose",
)

# Hosts that carry a hook manifest and can therefore be probed live.
HOOK_HOSTS: tuple[str, ...] = ("claude", "codex", "grok", "cursor", "gemini", "antigravity")

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
        "pre-tool-gate": (_Y, "PreToolUse wired; the gate confirmed in a live session (tenth field report)"),
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


def reach_table() -> dict[str, dict[str, dict[str, str]]]:
    """host -> feature -> {status, reason}; every cell present."""
    table: dict[str, dict[str, dict[str, str]]] = {}
    for host in HOSTS:
        row = _TABLE[host]
        table[host] = {feature: {"status": row[feature][0], "reason": row[feature][1]}
                       for feature in FEATURES}
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
    """The preflight judgment finding: a declared host with no live proof."""
    hosts = unverifiable_hosts(archive)
    if not hosts:
        return None
    return {
        "check": "host-reach",
        "detail": (f"{len(hosts)} declared hook host(s) unverifiable on this archive "
                   f"({', '.join(hosts)}): no interception proof is recorded, so "
                   "every feature-reach row for them is declared, not proven; "
                   "run `godmode hooks probe --host <name>` inside that host, or "
                   "ship knowing the row is on paper"),
    }
