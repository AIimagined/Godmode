#!/usr/bin/env python3
"""The runtime-backed half of the uninitialized-project harm guard.

`godmode_gate_fast.py` is a documented zero-import boundary -
`godmode_atlas.direction_findings` flags any import of `godmode_runtime`
there, at any depth, even one reached only on its rare `harm_candidate`
branch (its own docstring: "this module imports nothing from
godmode_runtime - not even to reuse the segment splitter"). A confirmed
harm-class candidate still needs the real classifier
(`godmode_sentinel.classify_action`) and the host-dialect renderer
(`godmode_hostevent.render_decision`), so that half of the guard lives
here instead - a sibling hooks module, reached only after
`godmode_gate_fast.harm_candidate` (regex-only, no import) already said
yes. A hook importing another hook is not the boundary the checker
enforces - only a hook importing `godmode_runtime` is - so this file may
import the runtime freely, and `godmode_gate_fast.py` stays clean by
reaching it with a deferred import of its own, paid only on that same
rare branch.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_HOOKS_DIR = Path(__file__).resolve().parent

_HARM_LABELS = {
    "git-history-or-remote": "history or remote",
    "git-branch-mutation": "branch deletion",
    "filesystem-mutation": "delete or overwrite outside the project",
    "release-or-external-write": "release or publish",
    "database-mutation": "database drop",
    "recovery-point-destruction": "recovery point deletion",
    "interpreter-opaque-inline": "an interpreter payload naming a harm-class operation",
    "password-in-transcript": "a password typed into the transcript",
    "operator-authorization-from-agent": "an agent opening the operator's password prompt",
    "unreadable-command": "a command whose program or verb is built when it runs",
}

# A word the shell builds when the line runs: its value is not in the text.
_EXPANSION = re.compile(r"[$`]|^[(@]")
# A word the shell completes when the line runs: an expanding `$`
# (`$x`, `$@`, `${_}`, `$(..)`), a backtick substitution or a cmd `%x%`.
_WORD_EXPANSION = re.compile(r"\$[\w@*#?!$({'\"-]|`|%\w+%")
# A bare word carrying a brace or glob the shell expands (`pu{s,}h`,
# `pu?h`): no path separator, so it is a verb or flag, not a file.
_SPLICED_PATTERN = re.compile(r"^[\w,{}?*\[\]-]*[{?*\[][\w,{}?*\[\]-]*$")
# An expansion spliced onto literal letters in one word (`r$@m`, `p${_}ush`).
_SPLICED = re.compile(
    r"\w[\"']*(?:\$|`|%\w+%)|(?:\}|\)|`|\$[@*#?!0-9-]|%\w+%)[\"']*\w")
# The expansions an unset or empty value removes, for reading what the
# command runs when they expand to nothing.
_EMPTY_EXPANSION = re.compile(
    r"\$\{[^}]*\}|\$\([^)]*\)|`[^`]*`|\$[@*#?!$0-9_-]|\$[A-Za-z_]\w*|%\w+%")
_FLAT = re.compile(r"[\"'\\^]")
_HARM_TIERS = ("R3", "R4", "R5")


def _unreadable_command(operation: str, verdict: dict[str, Any] | None = None) -> bool:
    """Whether a segment runs a program - or a git verb, a flag, any word
    - that is only built when the line runs (`& ('gi'+'t') push`, `$cmd
    push`, `git $(printf pu)sh`, `git reset --ha$@rd`, `r$@m`). The call
    already named a harm-class word, so a command the classifier cannot
    read is not cleared as harmless. In a segment the classifier did not
    clear (R3 and above), a word with an expansion spliced onto letters
    (`--ha$@rd`, `p${_}ush`) or a spliced brace or glob is unreadable, and
    in one it placed in a harm family (history, release, delete) any
    expanded word is; a command word spliced from an expansion and
    letters is unreadable whatever the verdict."""
    from godmode_runtime.godmode_parseview import opaque_head
    from godmode_runtime.godmode_sentinel import shell_segments
    verdict = verdict if verdict is not None else {"protected": True}
    protected = bool(verdict.get("protected"))
    if protected and (opaque_head(operation, True) or opaque_head(operation, False)):
        return True
    uncleared = [(str(part.get("text") or ""), str(part.get("category") or ""))
                 for part in verdict.get("components") or []
                 if isinstance(part, dict) and part.get("tier") in _HARM_TIERS]
    if protected and not verdict.get("components") and verdict.get("tier") in _HARM_TIERS:
        uncleared = [(operation, str(verdict.get("category") or ""))]
    for text, category in uncleared:
        for word in text.split():
            flat = _FLAT.sub("", word)
            if (_SPLICED.search(word)
                    or (_SPLICED_PATTERN.match(flat) and re.search(r"[A-Za-z]", flat))
                    or (category != "unknown-command" and _WORD_EXPANSION.search(word))):
                return True
    for segment in shell_segments(operation):
        words = segment.split()
        command = next((word for word in words if not re.match(r"^\w+=", word)), "")
        if _SPLICED.search(command):
            return True
        if not protected:
            continue
        if opaque_head(segment, True) or opaque_head(segment, False):
            return True
        # The splitter drops PowerShell's call operator: `('gi'+'t') push`
        # is what is left of `& ('gi'+'t') push`.
        if words and _EXPANSION.search(words[0]):
            return True
        if (len(words) > 1 and _FLAT.sub("", words[0]).lower() in ("git", "git.exe")
                and _EXPANSION.search(words[1])):
            return True
    return False


def _harm_when_empty(operation: str, root: str, tool: str | None) -> str | None:
    """The harm-class category `operation` has when every expansion in it
    comes out empty (`npm pub$@lish` runs `npm publish`), or None."""
    emptied = _EMPTY_EXPANSION.sub("", operation)
    if emptied == operation:
        return None
    from godmode_gate_fast import _harm_category
    from godmode_runtime.godmode_sentinel import _contained, classify_action
    verdict = classify_action(emptied, project_root=Path(root), tool_name=tool)
    return _harm_category(verdict, root, _contained)


def _shown(operation: str) -> str:
    text = " ".join(operation.split())
    return text if len(text) <= 120 else text[:117] + "..."


def _guard_reason(kind: str, operation: str, label: str, can_ask: bool) -> str:
    shown = _shown(operation)
    if kind == "setting":
        if can_ask:
            return ("Godmode: this changes the guard for uninitialized projects "
                    f"(`{shown}`). Only you should change it; approve only if you asked for it.")
        return ("godmode: refused - this changes the guard for uninitialized projects "
                f"(`{shown}`), which is yours to change. Run "
                "`godmode config set uninitialized off` yourself in a terminal, "
                "or run `godmode init` here for full Godmode.")
    if can_ask:
        return (f"Godmode is not initialized here, and `{shown}` is a harm-class command "
                f"({label}). Your approval at this prompt is the only check it gets. "
                "Run `godmode init` here for full Godmode, or turn this guard off with "
                "`godmode config set uninitialized off`.")
    return (f"godmode: refused - `{shown}` is a harm-class command ({label}), and "
            "Godmode is not initialized here. Run `godmode init` here to approve it "
            "with your password, run it yourself in a terminal, or turn this guard "
            "off with `godmode config set uninitialized off`.")


def guard_decision(payload: dict[str, Any], root: str) -> dict[str, Any] | None:
    """The host body for a harm-class call in an uninitialized project, or
    None to allow. Only reached by a `harm_candidate`; any failure here
    asks (or denies) rather than allowing, since the call already named a
    harm-class word."""
    host = "unknown"
    event_name = "PreToolUse"
    operation = ""
    try:
        if str(_HOOKS_DIR) not in sys.path:
            sys.path.insert(0, str(_HOOKS_DIR))
        scripts = str(_HOOKS_DIR.parent / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from godmode_gate_fast import _disables_guard, _harm_category
        from godmode_runtime import godmode_hostevent as hostevent
        from godmode_runtime.godmode_sentinel import _contained, classify_action
        event = hostevent.parse_host_payload(payload)
        host, event_name = event.host, event.event or "PreToolUse"
        can_ask = host in hostevent.HOSTS_WITH_ASK

        def body(kind: str, label: str = "") -> dict[str, Any]:
            decision = "ask" if can_ask else "deny"
            rendered, _code = hostevent.render_decision(
                host, event_name, decision, _guard_reason(kind, operation, label, can_ask))
            return rendered

        if event.tool_kind in (hostevent.TOOL_KIND_READ, hostevent.TOOL_KIND_OTHER):
            return None
        operation = event.operation or ""
        if event.tool_kind not in (hostevent.TOOL_KIND_SHELL, hostevent.TOOL_KIND_FENCED):
            return body("harm", "a tool call Godmode could not read")
        if not operation.strip():
            return None
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
        if _disables_guard(operation, list(event.targets or []), root, cwd or event.cwd or None):
            return body("setting")
        verdict = classify_action(operation, project_root=Path(root), tool_name=event.tool)
        category = _harm_category(verdict, root, _contained)
        if category is None and _unreadable_command(operation, verdict):
            category = "unreadable-command"
        if category is None:
            category = _harm_when_empty(operation, root, event.tool)
        if category is None:
            return None
        return body("harm", _HARM_LABELS.get(category, category.replace("-", " ")))
    except Exception:  # noqa: BLE001 - a harm-class candidate that cannot be judged is not allowed
        return unjudged_refusal(host, event_name)


def unjudged_refusal(host: str = "unknown", event_name: str = "PreToolUse") -> dict[str, Any]:
    """The deny for a harm-class candidate this module could not judge -
    in the host's own dialect when the runtime can render it, else every
    documented dialect's keys at once."""
    reason = ("godmode: refused - this names a harm-class operation and Godmode, "
              "not initialized here, could not classify it. Run it yourself in a "
              "terminal, run `godmode init` here, or turn this guard off with "
              "`godmode config set uninitialized off`.")
    try:
        scripts = str(_HOOKS_DIR.parent / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from godmode_runtime.godmode_hostevent import render_decision
        rendered, _code = render_decision(host, event_name, "deny", reason)
        return rendered
    except Exception:  # noqa: BLE001 - the runtime itself is unreachable
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": reason},
                "decision": "deny", "reason": reason}
