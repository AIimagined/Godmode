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

# Only names every `pre-action` call pays for. `pre-action` fires once per
# tool call - the hot path - while session-start/user-prompt/pre-compact/
# session-end fire once or a few times per session; their modules
# (charter, corpus, drift's compare, lens, requests, contribution,
# session_log, and the capability broker's secrets/getpass/hmac chain) are
# imported inside the branch that actually uses them, below, instead of
# paying for seven modules a mutating tool call never touches.
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from godmode_runtime.godmode_attest import attested_rule_ids, latest_session  # noqa: E402
from godmode_runtime.godmode_guardrails import check_ceilings  # noqa: E402
from godmode_runtime.godmode_guardrails import meter_tool_call, tool_operation, watchdog  # noqa: E402
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    GATE_MODE_OBSERVE, classify_action, evidence_pipe_advisory,
    local_authorization_policy)


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
    # Deferred: this function runs once per session, on session-start only,
    # so paying import cost here never touches the per-tool-call hot path.
    from godmode_runtime.godmode_charter import compile_charter
    from godmode_runtime.godmode_corpus import resolve_roles
    from godmode_runtime.godmode_drift import capabilities as host_capabilities
    from godmode_runtime.godmode_drift import compare as compare_sessions

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
    # U-E7: observe mode must be impossible to enter silently, which means
    # every session that opens under it is told so at open, not merely at
    # the moment a call would have been blocked. Best-effort like every
    # other obligation above: a malformed policy file degrades to "not
    # observe" here exactly as it does in the pre-action path below, never
    # to a crashed session-start hook.
    try:
        policy = local_authorization_policy(archive)
    except GodmodeError:
        policy = {}
    if policy.get("gate_mode") == GATE_MODE_OBSERVE:
        obligations["enforcement"]["gate_mode"] = GATE_MODE_OBSERVE
        obligations["enforcement"]["notice"] = (
            "gate in OBSERVE mode - nothing will be blocked; every deny/ask "
            "this session would have produced is instead recorded as an "
            "advisory refusal (`godmode roi --digest` reads them back). "
            "Entered via .godmode-authorization-policy.json's gate_mode - "
            "edit that file to return to enforcement."
        )
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


def _broker(archive: Chronicle) -> Any:
    # Deferred: CapabilityBroker drags secrets/hmac/getpass into the import
    # graph, which only the two consume branches below ever need - the
    # ordinary allow path (the overwhelming majority of tool calls) never
    # pays for them.
    from godmode_runtime.godmode_sentinel import CapabilityBroker
    return CapabilityBroker(archive)


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


def _apply_observe_mode(archive: Chronicle, tool: str, operation: str,
                        preview: dict[str, Any]) -> dict[str, Any]:
    """U-E7: convert a would-have-blocked decision into an advisory.

    Called exactly once per call, and only when the local policy's
    `gate_mode` is `godmode_sentinel.GATE_MODE_OBSERVE` (entry requires that
    exact, validated file edit - see `CapabilityBroker._policy()` - never
    `init --profile`, which stays enforcement-only by design; see
    `godmode_profile.py`'s module docstring) AND only after every check that
    can set `preview["allow"] = False` has already run: ceilings, the
    watchdog, the classifier's own ask/deny split, the design boundary, the
    scope fence. This is the single point downstream of all of them, so it
    is the single point observe mode needs to touch - every detector and
    gate above keeps classifying exactly as it always did; only what
    happens with a "no" changes.

    The fast gate (`hooks/godmode_gate_fast.py`) is untouched by this unit:
    its allow path was already silent, and every escalation reaches this
    hook, where the conversion below applies uniformly regardless of which
    check produced the "no".

    Two things happen, never a third: an archive record - the SAME
    `refusal` kind `stage_from_refusal`/`roi_report` already read, with
    `observed: True` added - and `allow` flips from False to True (never
    the reverse: a malformed or unreadable policy already resolved to "not
    observe" before this function is ever called, so fail-open is
    unaffected). No `permissionDecision` is emitted for this call; the
    advisory is printed the same way an allowed call's evidence-pipe
    advisory already is (`systemMessage`, no `hookSpecificOutput`) - which
    is what keeps the host's silence-is-allow contract intact even for a
    call that has something loud to say.

    `stage_from_refusal` treats an `observed: True` refusal as never
    stageable (its own docstring names the decision); `godmode_roi.py`
    excludes it from `gate.denied` - that bucket counts real enforcement
    outcomes, not hypothetical ones - and folds it instead into `godmode
    roi --digest`'s would-have-caught counts, labeled `would-have-denied`/
    `would-have-asked` (an event label, never a prevention or savings
    claim - same causal-denylist discipline as U-E1).

    Best-effort recording, exactly like the enforcement-mode write it
    replaces: a run that cannot be recorded must still be allowed to
    continue under a posture whose entire point is "never block".
    """
    would_have = "ask" if _decision_for(preview) == "ask" else "deny"
    try:
        archive.append(
            "refusal",
            str(preview.get("category", "refusal"))[:200] or "refusal",
            {
                "operation": operation[:500],
                "tool": tool or "operation",
                "tier": str(preview.get("tier", "R?")),
                "category": preview.get("category", "unclassified-mutation"),
                "observed": True,
                "would_have": would_have,
            },
            evidence=[],
        )
    except Exception:  # noqa: BLE001
        pass
    reason = str(preview.get("reason") or preview.get("category", "operation"))[:300]
    preview["allow"] = True
    preview["observed"] = True
    preview["observe_advisory"] = (
        "OBSERVE MODE - nothing is blocked: this call would have been "
        f"{'asked about' if would_have == 'ask' else 'denied'} "
        f"({preview.get('category', 'unclassified-mutation')}, "
        f"{preview.get('tier', 'R?')}). {reason}"
    )[:500]
    return preview


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
            from godmode_runtime.godmode_lens import build_context_brief
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
                from godmode_runtime.godmode_requests import record_request
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
            if args.event == "session-end":
                # Best-effort, counts-only measurement of the host's own
                # transcript. Never blocks the checkpoint below: a missing
                # transcript, an unreadable one, or any other failure here
                # must not cost the operator the checkpoint this branch
                # exists to record.
                try:
                    from godmode_runtime.godmode_session_log import record_measurement
                    record_measurement(
                        archive, submitted.get("transcript_path"),
                        session=str(submitted.get("session_id") or "") or None,
                    )
                except Exception:  # noqa: BLE001
                    pass
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
                from godmode_runtime.godmode_contribution import contribution
                from godmode_runtime.godmode_contribution import render_line as render_contribution
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

        # U-S4 approval-declarations - minimal isolated block. The local
        # policy's `password_required`/`approval_required` widen the
        # protected set (godmode_sentinel.classify_action's own
        # `extra_protected`/`require_approval`); read here, right before the
        # call that needs it, so this preview is what a declared category
        # actually gets rather than the un-widened default it silently fell
        # back to before. A malformed policy file is its own failure, not
        # this gate's: caught locally and treated as "no widening this call"
        # rather than left to propagate into the broad GodmodeError handler
        # around this whole function, which degrades to allowing everything.
        try:
            policy = local_authorization_policy(archive)
        except GodmodeError:
            policy = {}
        # U-E7: read once, alongside password_required/approval_required
        # above (same seam, same malformed-file degrade-to-"not observe"
        # behaviour). `observe` gates ONLY the conversion at the bottom of
        # this block, after every check below has already decided whether
        # this call would be denied or asked about - see
        # `_apply_observe_mode`'s docstring for why that ordering matters.
        observe = policy.get("gate_mode") == GATE_MODE_OBSERVE
        # The root is passed, not inferred: containment decides whether an edit
        # is ordinary work, and without it every edit the host sends - always
        # an absolute path - was judged to be outside the tree and refused.
        # `archive=archive` (U-B2): a pinned evaluator's Edit/Write payload
        # is denied here, at the same call every other protected category
        # already goes through - the archive is the authoritative pin
        # store, and this is the one call site that has it in scope.
        preview = classify_action(
            operation, project_root=Path(anchor.project_root),
            archive=archive,
            extra_protected=policy.get("password_required", ()),
            require_approval=policy.get("approval_required", ()),
        ) if operation else {
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
        elif (staged := _broker(archive).consume_staged(operation)) is not None:
            # An operator authorised this exact command with the password, and
            # left it where the hook can read it. Without this the refusal
            # named a remedy nobody could perform, so the only answer to a
            # false positive was to remove the guard entirely.
            preview["allow"] = True
            preview["capability_consumed"] = True
            preview["authorized_by"] = "staged capability"
        elif submitted.get("capability"):
            _broker(archive).consume(operation, str(submitted["capability"]))
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
                # Recorded here, in the full escalation path only - the fast
                # gate stays IO-free by contract, and this branch is where a
                # refusal is actually born. Bounded so the record cannot grow
                # the archive from an unbounded command line, and best-effort:
                # a refusal that failed to record must still refuse, the same
                # way the checkpoint and prompt records above degrade rather
                # than take the hook down with them.
                #
                # Skipped under observe (U-E7): the single, later call to
                # `_apply_observe_mode` writes the record for this call
                # instead, with `observed: True` set - writing it here too
                # would double-record the same decision, once enforced and
                # once advisory, for a call that was never actually denied.
                if not observe:
                    try:
                        archive.append(
                            "refusal",
                            str(preview["category"])[:200] or "refusal",
                            {
                                "operation": operation[:500],
                                "tool": tool or "operation",
                                "tier": str(preview.get("tier", "R?")),
                                "category": preview["category"],
                            },
                            evidence=[],
                        )
                    except Exception:  # noqa: BLE001
                        pass
                preview["reason"] = (
                    f"refused: this is irreversible ({preview['category']}, "
                    f"{preview.get('tier', 'R?')})"
                    + (f" - touches {impact}" if impact else "")
                    + ". Run it yourself, rephrase it as something narrower, or "
                    "stage a capability for this exact command: `godmode "
                    "authorize stage --operation "
                    f"{json.dumps(operation[:200])}` - it needs the password "
                    "from `godmode authorize setup`, is spent once, and expires. "
                    "In a hosted session, type it with a leading '!' to run it "
                    "from the prompt without leaving the conversation.\n"
                    "! godmode authorize stage --from-last-refusal"
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
                # Deferred: only Edit/Write-class tools pay for the fence
                # module - the far more common read-only and R0-R2 tool
                # calls never reach this branch.
                from godmode_runtime.godmode_fence import design_verdict, fence_verdict
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

        # U-E7 observe mode: the single point every check above converges at.
        # Ceilings, the watchdog, the classifier's ask/deny split, the design
        # boundary, and the scope fence have all already run and each may
        # have set `preview["allow"] = False` above - this is deliberately
        # placed after every one of them so the conversion is total, not a
        # partial list of "the paths someone remembered to route through
        # observe mode". The fast gate stays out of this entirely: its allow
        # path was already silent and untouched, and every escalation lands
        # here, where this already applies.
        if observe and not preview.get("allow", True):
            preview = _apply_observe_mode(archive, tool, operation, preview)

        if pretool:
            # Silence is the allow signal in this contract; only a refusal speaks,
            # so an allowed tool call costs the host nothing but the exit code.
            if preview["allow"] and operation:
                # An allowed call may still deserve one sentence: a test run
                # piped through a truncating filter destroys the evidence the
                # run exists to produce, or (U-E7) this call would have been
                # denied/asked about and observe mode let it through anyway -
                # the classifier cannot know which run is the deciding one,
                # and observe mode cannot be silent about looser enforcement.
                advisory = preview.get("observe_advisory") or evidence_pipe_advisory(operation)
                if advisory:
                    print(json.dumps({"systemMessage": advisory},
                                     ensure_ascii=False))
                return 0
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
