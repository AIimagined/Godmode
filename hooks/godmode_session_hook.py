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
from godmode_runtime.godmode_requests import record_request  # noqa: E402
from godmode_runtime.godmode_drift import capabilities as host_capabilities  # noqa: E402
from godmode_runtime.godmode_drift import compare as compare_sessions  # noqa: E402
from godmode_runtime.godmode_fence import design_verdict, fence_verdict  # noqa: E402
from godmode_runtime.godmode_lens import build_context_brief  # noqa: E402
from godmode_runtime.godmode_contribution import contribution  # noqa: E402
from godmode_runtime.godmode_contribution import render_line as render_contribution  # noqa: E402
from godmode_runtime.godmode_guardrails import check_ceilings  # noqa: E402
from godmode_runtime.godmode_guardrails import meter_tool_call, tool_operation, watchdog  # noqa: E402
from godmode_runtime.godmode_sentinel import CapabilityBroker, classify_action  # noqa: E402


CLAUDE_CONTEXT_LIMIT = 9_000

# Tools that read and cannot write. Named rather than inferred: a tool absent
# from this set is treated as capable of mutation and pays the full check.
_READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite"})

# Tools that name the file they change in `file_path`, which is what the scope
# fence is written against. A shell command that edits a file in passing is not
# covered here - it is covered by the classifier, which reads commands - and
# pretending otherwise would put a fence on the tools that announce their
# target while leaving the ones that do not.
_FENCED_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})


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


# Tiers that stop the call outright. Everything else protected becomes a
# question the operator answers.
#
# The gate emitted `deny` and only `deny`, for every protected operation, on the
# reasoning written into its own refusal: no capability can be attached to a
# host tool call, so there is no in-session approval. The first clause is true.
# The conclusion does not follow — the host takes `ask`, and asking *is* an
# in-session approval. It was never reached for.
#
# What that cost is measurable rather than theoretical. Another project running
# this plugin hit `rm probe-tmp.mjs` on a scratch file it had just written,
# `git checkout -- out/`, and `taskkill` on a dev server it had started; each
# was a hard stop, each became a command typed by hand, and that session's
# advice to its operator was to disable the hook. A gate that cannot ask has
# only one way to be careful, and it spends the operator's patience every time.
#
# R5 keeps its refusal. The tier exists for operations whose damage no later
# command undoes — a forced push, a dropped table, a recursive delete outside
# the tree — and a one-key confirmation is the wrong shape for those. That is
# what `authorize stage` is for, and it still works: a staged capability is
# consumed before this is reached.
_REFUSE_OUTRIGHT = frozenset({"R5"})


def _decision_for(preview: dict[str, Any]) -> str:
    """`ask` or `deny`, from the tier the classifier already computed.

    A governance block carries no tier, and the first version of this returned
    `ask` for it — so an exceeded ceiling and a run of skipped mandated steps
    both became one-key confirmations. Those are the two signals that say the
    session has stopped being trustworthy, and asking a session like that to
    approve itself is the whole failure they exist to interrupt.
    """
    if preview.get("governance_block"):
        return "deny"
    # A frozen design surface. Not a risk tier and not a session gone wrong -
    # the operator declared that this needs their permission, and permission
    # obtained by the same keystroke as every other confirmation in a long run
    # is not permission. It moves by staged capability or not at all.
    if preview.get("design_block"):
        return "deny"
    return "deny" if preview.get("tier") in _REFUSE_OUTRIGHT else "ask"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="godmode-session-hook")
    parser.add_argument("event", choices=["session-start", "pre-compact", "session-end",
                                          "pre-action", "user-prompt"])
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

        if args.event == "user-prompt":
            # Recorded here because it cannot be recovered anywhere else. The
            # host's transcript stores an input at the moment it is delivered,
            # not the moment it was typed, so an ask that arrived mid-task is
            # indistinguishable afterwards from one that waited its turn - and
            # the mid-task ones are exactly the ones that get lost.
            #
            # Silent by contract: this hook adds no context and blocks nothing.
            # A ledger of asks that interrupts to announce itself would be one
            # more thing to answer beside the work already running.
            prompt = str(submitted.get("prompt", ""))
            try:
                record_request(
                    archive, prompt,
                    session=str(submitted.get("session_id") or "") or None,
                    tools_in_flight=int(submitted.get("tools_in_flight") or 0),
                )
            except Exception:  # noqa: BLE001
                # A prompt that cannot be stored - a secret-shaped paste the
                # archive refuses, a locked store - must not stop the turn the
                # operator is trying to have.
                pass
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
            payload = {"godmode": "checkpoint", "stored": True,
                       "sequence": record["sequence"]}
            # What the gates did this run, at the moment the run ends. Silent
            # when nothing fired, and switched off by .godmode-report.json.
            session = latest_session(archive)
            if session:
                summary = render_contribution(
                    contribution(archive, Path(anchor.project_root), session))
                if summary:
                    payload["summary"] = summary
            print(json.dumps(payload, ensure_ascii=False))
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

        # The root is passed, not inferred: containment decides whether an edit
        # is ordinary work, and without it every edit the host sends - always
        # an absolute path - was judged to be outside the tree and refused.
        preview = classify_action(
            operation, project_root=Path(anchor.project_root)) if operation else {
            "protected": True, "category": "unclassified-mutation",
            "impact": ["no operation described"]}
        preview["executes_operation"] = False
        if blocked_reason is not None:
            preview["allow"] = False
            preview["reason"] = blocked_reason
            # A governance stop, not a risk tier. An exceeded ceiling or a run
            # of skipped mandated steps says the session itself is off the
            # rails, and offering to proceed one confirmation at a time is how
            # a session stays off them - so these refuse whatever the operation
            # would otherwise have scored.
            preview["governance_block"] = True
        elif not preview["protected"]:
            preview["allow"] = True
        elif (staged := CapabilityBroker(archive).consume_staged(operation)) is not None:
            # An operator authorised this exact command with the password, and
            # left it where the hook can read it. Without this the refusal
            # named a remedy nobody could perform, so the only answer to a
            # false positive was to remove the guard entirely.
            preview["allow"] = True
            preview["capability_consumed"] = True
            preview["authorized_by"] = "staged capability"
        elif submitted.get("capability"):
            CapabilityBroker(archive).consume(operation, str(submitted["capability"]))
            preview["allow"] = True
            preview["capability_consumed"] = True
        else:
            preview["allow"] = False
            # Name a remedy the reader can actually perform - and name the one
            # that exists. This message was written when the broker really was
            # unreachable from a host tool call, and it was never revisited
            # when staging shipped to answer exactly that: twenty lines above,
            # a staged capability is consumed and the call proceeds. So the
            # refusal denied the existence of its own remedy and offered
            # disabling the guard instead, which is the worst advice this
            # sentence could give and the likeliest to be taken.
            impact = "; ".join(str(item) for item in preview.get("impact", ()))[:160]
            if _decision_for(preview) == "ask":
                # A question, phrased as one. The reason is read aloud to the
                # operator beside the command, so it says what is at stake
                # rather than what the tool has decided.
                preview["reason"] = (
                    f"{preview['category']} ({preview.get('tier', 'R?')})"
                    + (f" - touches {impact}" if impact else "")
                    + ". Approve to run it."
                )
            else:
                preview["reason"] = (
                    f"refused: this is irreversible ({preview['category']}, "
                    f"{preview.get('tier', 'R?')})"
                    + (f" - touches {impact}" if impact else "")
                    + ". Run it yourself, rephrase it as something narrower, or "
                    "stage a capability for this exact command: `godmode "
                    "authorize stage --operation "
                    f"{json.dumps(operation[:200])}` - it needs the password "
                    "from `godmode authorize setup`, is spent once, and expires."
                )

        # The fence, applied last and only to what would otherwise proceed. It
        # answers a question none of the checks above ask: not `is this
        # operation dangerous` but `is this file one this piece of work said it
        # would touch`. An ordinary edit to an unrelated file is not dangerous
        # by any tier, which is exactly why every check above lets it through.
        #
        # It asks rather than refuses outright. Widening a fence is a normal
        # part of finding out what a change really touches, and a scope that
        # can only be widened by rewriting a plan would be abandoned the first
        # time it was wrong. Undeclared fences allow silently - every project
        # that predates this has no fence, and none may start refusing edits
        # because this shipped.
        if preview.get("allow") and tool in _FENCED_TOOLS:
            target = str((submitted.get("tool_input") or {}).get("file_path", "")).strip()
            if target:
                # The design boundary is checked first and denies outright. It
                # is project state rather than task state, and the operator
                # said this one needs their permission - a one-key `ask` in the
                # middle of a long run is the same keystroke as every other
                # confirmation that session, which is not permission.
                design = design_verdict(Path(anchor.project_root), target)
                if not design["allowed"]:
                    preview["allow"] = False
                    preview["design_block"] = True
                    preview["boundary"] = design["boundary"]
                    preview["reason"] = f"{design['detail']}. {design['remedy']}"
                else:
                    fenced = fence_verdict(archive, target,
                                           project_root=Path(anchor.project_root))
                    if not fenced["allowed"]:
                        preview["allow"] = False
                        preview["fence"] = fenced["fence"]
                        preview["reason"] = f"{fenced['detail']}. {fenced['remedy']}"

        if pretool:
            # Silence is the allow signal in this contract; only a refusal speaks,
            # so an allowed tool call costs the host nothing but the exit code.
            if not preview["allow"]:
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": _decision_for(preview),
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
