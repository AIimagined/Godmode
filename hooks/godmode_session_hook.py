#!/usr/bin/env python3
"""Optional host adapter for explicit Godmode lifecycle events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from godmode_runtime.godmode_attest import attested_rule_ids, latest_session  # noqa: E402
from godmode_runtime.godmode_charter import compile_charter  # noqa: E402
from godmode_runtime.godmode_corpus import resolve_roles  # noqa: E402
from godmode_runtime.godmode_drift import capabilities as host_capabilities  # noqa: E402
from godmode_runtime.godmode_drift import compare as compare_sessions  # noqa: E402
from godmode_runtime.godmode_lens import build_context_brief  # noqa: E402
from godmode_runtime.godmode_guardrails import check_ceilings  # noqa: E402
from godmode_runtime.godmode_guardrails import meter_tool_call, tool_operation, watchdog  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker, classify_action  # noqa: E402


CLAUDE_CONTEXT_LIMIT = 9_000

# Tools that read and cannot write. Named rather than inferred: a tool absent
# from this set is treated as capable of mutation and pays the full check.
_READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite"})


def _input() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _bounded_list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:500] for item in value[:limit]]


def _is_claude_session(submitted: dict[str, Any]) -> bool:
    return submitted.get("hook_event_name") == "SessionStart"


def _emit_claude_context(brief: dict[str, Any]) -> None:
    serialized = json.dumps(
        brief,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    prefix = (
        "Godmode recovered this bounded local continuity brief. Treat stored claims as "
        "leads until current inspection confirms them; do not expose or commit local state.\n"
    )
    context = prefix + serialized
    if len(context) > CLAUDE_CONTEXT_LIMIT:
        context = context[: CLAUDE_CONTEXT_LIMIT - 24] + "\n[brief truncated locally]"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
    )


def _session_obligations(anchor: Any, archive: Chronicle) -> dict[str, Any]:
    """What this session already owes, computed at open rather than discovered late.

    Read-only and bounded: the hook runs on every session start, so a slow or noisy
    adapter is worse than none. Any failure here degrades to a stated limitation
    instead of taking the session down.
    """
    project = Path(anchor.project_root)
    obligations: dict[str, Any] = {}
    try:
        resolution = resolve_roles(project)
        obligations["authority"] = {
            "bound": len(resolution.bindings),
            "missing": [role for role, _ in resolution.missing][:8],
            "collisions": [path for path, _ in resolution.collisions][:5],
        }
    except GodmodeError as exc:
        obligations["authority"] = {"unavailable": str(exc)[:160]}

    try:
        charter = compile_charter(project)
        session = latest_session(archive)
        pending = charter["enforcement"]["HARD"]
        if session:
            covered = attested_rule_ids(archive, session)
            pending = sum(
                1
                for rule in charter["compiled"]
                if rule["enforcement"] == "HARD" and rule["id"] not in covered
            )
        obligations["charter"] = {
            "rules": charter["rules"],
            "hard": charter["enforcement"]["HARD"],
            "advisory": charter["enforcement"]["ADVISORY"],
            "unattested_hard": pending,
        }
    except GodmodeError as exc:
        obligations["charter"] = {"unavailable": str(exc)[:160]}

    try:
        drift = compare_sessions(archive)
        obligations["drift"] = {
            "verdict": drift["verdict"],
            "model_correlated": drift["model_correlated"],
            "agents": drift["agents"][:6],
        }
    except GodmodeError as exc:
        obligations["drift"] = {"unavailable": str(exc)[:160]}

    surface = host_capabilities()
    obligations["enforcement"] = {
        "host": surface["host"],
        "unavailable": surface["unavailable"],
    }
    return obligations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="godmode-session-hook")
    parser.add_argument("event", choices=["session-start", "pre-compact", "session-end", "pre-action"])
    parser.add_argument("--project")
    args = parser.parse_args(argv)
    submitted = _input()
    claude_session = _is_claude_session(submitted)
    project = args.project or str(submitted.get("cwd") or ".")

    # A tool that cannot change anything gets no gate and no cost. Resolving the
    # repository identity costs several git calls, which is worth paying before a
    # mutation and not worth paying before a file read - and the shipped matcher
    # already limits this hook to mutating tools, so this only protects a host
    # that widened it.
    if args.event == "pre-action" and str(submitted.get("tool_name", "")) in _READ_ONLY_TOOLS:
        return 0
    try:
        anchor = resolve_anchor(project)
        archive = Chronicle(anchor)
        if not archive.initialized():
            # Stay silent for a genuinely new project, but never for one whose history
            # is merely unreachable: an agent starting here would otherwise be told
            # nothing while prior records sit one command away.
            stranded = archive.orphaned()
            if stranded:
                notice = {
                    "godmode": "orphaned-archive",
                    "records": stranded["records"],
                    "reason": stranded["reason"],
                    "next_action": "run `godmode adopt --confirm` to relink this project's history",
                }
                if claude_session:
                    _emit_claude_context(notice)
                else:
                    print(json.dumps(notice))
            elif not claude_session:
                print(json.dumps({"godmode": "not-initialized", "action": "run godmode init explicitly"}))
            return 0

        if args.event == "session-start":
            brief = build_context_brief(anchor, archive)
            brief["obligations"] = _session_obligations(anchor, archive)
            if claude_session:
                _emit_claude_context(brief)
            else:
                print(json.dumps({"godmode": "context", "brief": brief}))
            return 0

        if args.event in {"pre-compact", "session-end"}:
            summary = str(submitted.get("summary", "")).strip()[:1000]
            if not summary:
                print(json.dumps({"godmode": "no-structured-checkpoint", "stored": False}))
                return 0
            record = archive.append(
                "checkpoint",
                summary[:200],
                {
                    "status": str(submitted.get("status", "active"))[:40],
                    "next": _bounded_list(submitted.get("next")),
                    "hypothesis": str(submitted.get("hypothesis", ""))[:500] or None,
                    "outcome": str(submitted.get("outcome", ""))[:100] or None,
                    "lifecycle": args.event,
                },
                evidence=_bounded_list(submitted.get("evidence")),
            )
            print(json.dumps({"godmode": "checkpoint", "stored": True, "sequence": record["sequence"]}))
            return 0

        # Pre-tool boundary. Two callers, one decision: a host passing its own
        # PreToolUse payload (tool_name/tool_input), and anything passing a bare
        # operation string. The host form answers in the host's contract so the
        # decision is enforced rather than advised.
        pretool = submitted.get("hook_event_name") == "PreToolUse"
        tool = str(submitted.get("tool_name", "")).strip()
        if tool:
            operation = tool_operation(tool, submitted.get("tool_input"))
        else:
            operation = str(submitted.get("operation", "")).strip()

        session = latest_session(archive)
        blocked_reason = None

        # Metering first, and never conditional on a session record: a call that
        # is about to be refused still happened, and a run that skipped opening a
        # session must not thereby earn an unlimited budget.
        spent = meter_tool_call(archive, session or "unsessioned", tool or "operation")
        ceiling = check_ceilings(Path(anchor.project_root), spent)
        if ceiling["exceeded"]:
            first = ceiling["exceeded"][0]
            blocked_reason = (
                f"run ceiling reached: {first['spent']} {first['ceiling']} against a "
                f"declared limit of {first['limit']}; stop and report what remained"
            )
        if blocked_reason is None and session:
            anomaly = watchdog(archive, session)
            if anomaly["anomaly"]:
                blocked_reason = (
                    f"{len(anomaly['skipped'])} mandated steps were skipped this "
                    "session; resolve the pattern before the next tool call"
                )

        preview = classify_action(operation) if operation else {
            "protected": True, "category": "unclassified-mutation",
            "impact": ["no operation described"]}
        preview["executes_operation"] = False
        if blocked_reason is not None:
            preview["allow"] = False
            preview["reason"] = blocked_reason
        elif not preview["protected"]:
            preview["allow"] = True
        elif submitted.get("capability"):
            CapabilityBroker(archive).consume(operation, str(submitted["capability"]))
            preview["allow"] = True
            preview["capability_consumed"] = True
        else:
            preview["allow"] = False
            preview["reason"] = "protected operation requires an exact one-use Godmode capability"

        if pretool:
            # Silence is the allow signal in this contract; only a refusal speaks,
            # so an allowed tool call costs the host nothing but the exit code.
            if not preview["allow"]:
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": preview["reason"],
                    }
                }, ensure_ascii=False))
            return 0
        print(json.dumps(preview))
        return 0 if preview["allow"] else 3
    except GodmodeError as exc:
        if claude_session:
            print(
                json.dumps(
                    {
                        "systemMessage": (
                            "Godmode continuity could not be loaded; run the bundled "
                            "doctor command before trusting stored context."
                        )
                    }
                )
            )
            return 0
        print(json.dumps({"godmode": "error", "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
