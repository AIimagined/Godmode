#!/usr/bin/env python3
"""Optional host adapter for explicit Godmode lifecycle events."""

from __future__ import annotations

import argparse
import json
import os
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
from godmode_runtime.godmode_anchor import current_host, resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_errors import GodmodeError  # noqa: E402
from godmode_runtime.godmode_attest import attested_rule_ids, latest_session  # noqa: E402
from godmode_runtime.godmode_guardrails import check_ceilings  # noqa: E402
from godmode_runtime.godmode_guardrails import meter_tool_call, watchdog  # noqa: E402
from godmode_runtime.godmode_hookproof import (  # noqa: E402
    DEGRADE_REASON_MALFORMED_PAYLOAD, PROBE_PREFIX, degraded_reason,
    interception_state, record_hook_degradation, record_interception_proof,
    record_session_anchor)
from godmode_runtime.godmode_hostevent import (  # noqa: E402
    HOSTS_WITH_ASK, TOOL_KIND_MALFORMED, TOOL_KIND_UNRECOGNIZED,
    capture_payload_probe, field as host_field, is_pretool_event,
    malformed_apply_patch_preview, parse_host_payload,
    record_malformed_apply_patch, record_unrecognized_tool, render_decision,
    unrecognized_tool_preview)
from godmode_runtime.godmode_sentinel import (  # noqa: E402
    GATE_MODE_OBSERVE, classify_action, evidence_pipe_advisory,
    find_secret_shapes, local_authorization_policy)

# CX-2 payload-capture probe: counts-only capture of an unrecognized host
# shape (event/tool names, sorted input field names, request-id/cwd hashes -
# never a value), for building future host fixtures. Off unless explicitly
# requested - either the env var (set once for a whole session) or
# `--capture-payload` (this invocation only).
CAPTURE_PAYLOAD_ENV = "GODMODE_CAPTURE_HOST_PAYLOADS"


CLAUDE_CONTEXT_LIMIT = 9_000

# Tools that read and cannot write. Named rather than inferred: a tool absent
# from this set is treated as capable of mutation and pays the full check.
_READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite"})

# CX-2: which tools name the file(s) they change - Claude's Write/Edit/
# NotebookEdit, Codex's apply_patch (one to several) - is now an adapter
# decision (`godmode_hostevent.py`), surfaced as `HostEvent.targets`. A
# shell command that edits a file in passing is still not covered here - it
# is covered by the classifier, which reads commands - and pretending
# otherwise would put a fence on the tools that announce their target while
# leaving the ones that do not.


def _input() -> tuple[dict[str, Any], bool]:
    """`(payload, malformed)`.

    CX-5: a payload that failed to parse as JSON is a distinct, recordable
    hook-health signal (`DEGRADE_REASON_MALFORMED_PAYLOAD`), told apart from
    the ordinary, legitimate "nothing on stdin" case (a TTY, or genuinely
    empty input) - the latter is not a failure, and must never be counted
    as one. `malformed` is also `True` for a JSON document that parsed but
    was not an object (e.g. a bare list or string) - every downstream
    consumer of this hook's stdin expects a mapping, so that shape is exactly
    as unusable as a parse failure, never silently coerced to `{}` without
    the caller knowing it happened.
    """
    if sys.stdin.isatty():
        return {}, False
    raw = sys.stdin.read()
    if not raw.strip():
        return {}, False
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}, True
    if not isinstance(value, dict):
        return {}, True
    return value, False


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

    host = current_host()
    interception_level = interception_state(archive, host)
    surface = host_capabilities(tool_call_interception=interception_level)
    obligations["enforcement"] = {
        "host": surface["host"],
        "unavailable": surface["unavailable"],
        # CX-5: the five-level grade itself, not just the "unavailable"
        # bucket - PARTIAL/SOFT/DEGRADED are meaningfully different from
        # each other and from a bare UNAVAILABLE, and a caller reading only
        # the older `unavailable`/`controls` fields would not be able to
        # tell a fresh install from a broken upgrade.
        "tool_call_interception": interception_level,
    }
    if interception_level == "DEGRADED":
        # CX-5 mode table: hook registered-but-untrusted/disabled must carry
        # a VISIBLE warning line in the session brief, persistently, until a
        # probe passes - never a silent downgrade an operator has to go
        # looking for. `degraded_reason` names the specific check that
        # tripped (superseded/expired/version-drift/hash-drift), so the
        # line says more than "trust me."
        reason = degraded_reason(archive, host)
        obligations["enforcement"]["degraded_reason"] = reason
        obligations["enforcement"]["warning"] = (
            "godmode's pre-tool interception for this host was previously proven "
            f"and is now DEGRADED ({reason or 'unknown reason'}) - no HARD "
            "enforcement claim holds until `godmode hooks probe` passes again."
        )
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
        notice = (
            "gate in OBSERVE mode - nothing will be blocked; every deny/ask "
            "this session would have produced is instead recorded as an "
            "advisory refusal (`godmode roi --digest` reads them back). "
            "Entered via .godmode-authorization-policy.json's gate_mode - "
            "edit that file to return to enforcement."
        )
        # B4-10(a)/(d): the trial's evidence, in the same brief every session
        # reads - counts by tier plus the highest-tier example's category,
        # never command text (that lives behind `godmode observe --report`,
        # where the operator explicitly asks). Zero is stated, not implied:
        # observe mode that is silent is a mute button, not a trial.
        try:
            from godmode_runtime.godmode_roi import (
                OBSERVE_PROMOTION_THRESHOLD, would_have_summary,
            )
            summary = would_have_summary(archive)
            obligations["enforcement"]["would_have"] = summary
            if summary["total"]:
                notice += (
                    f" This trial's would-have events so far: r5={summary['r5']} "
                    f"r4={summary['r4']} r3={summary['r3']} r2={summary['r2']}"
                    + (f" (top: {summary['top']})" if summary["top"] else "")
                    + " - `godmode observe --report` lists them."
                )
            else:
                notice += " There are no would-have events recorded yet this trial."
            irreversible = summary["r4"] + summary["r5"]
            if irreversible >= OBSERVE_PROMOTION_THRESHOLD:
                notice += (
                    f" PROMOTE? Under enforce mode, {irreversible} of these "
                    "operations would have been denied or asked about at the "
                    "irreversible tiers (R4/R5). To promote the gate to "
                    "enforce, remove 'gate_mode' from "
                    ".godmode-authorization-policy.json."
                )
        except GodmodeError:
            notice += " (would-have counts unavailable: archive unreadable)"
        obligations["enforcement"]["notice"] = notice
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


def _ellipsize(text: str, limit: int) -> str:
    """Bound text a human reads: break at the last word inside `limit` and
    say it was cut. A hard slice ended the refusal's staged-command example
    mid-word (`...authorize stage "git push --f`) with nothing to show
    anything was missing. A token with no space inside the limit still cuts
    hard - bounded beats pretty - but the marker always lands. The marker is
    ASCII on purpose: this string crosses a pipe whose two ends can disagree
    about encoding (a cp1252 child console read as utf-8 turns U+2026 into a
    dead reader thread and a None stdout - found the hard way)."""
    if len(text) <= limit:
        return text
    kept = text[:limit - 3]
    space = kept.rfind(" ")
    if space > 0:
        kept = kept[:space]
    return kept + "..."


def _checkpoint_pressure(archive: Chronicle, anchor: Any) -> str | None:
    """B4-7 rider 1: tick the tracked-mutation counter and answer with an
    advisory when it crosses the threshold - or, under declared
    `auto_checkpoint` policy, write the chronicled auto-checkpoint and
    reset. Best-effort throughout: a counter or checkpoint that cannot be
    written never blocks the tool call it rides on."""
    from godmode_runtime.godmode_guardrails import (
        checkpoint_trigger_policy, count_tracked_mutation,
        reset_mutation_counter,
    )
    count = count_tracked_mutation(archive)
    threshold, auto = checkpoint_trigger_policy(Path(anchor.project_root))
    if count < threshold:
        return None
    if auto:
        try:
            archive.append(
                "checkpoint", "auto-checkpoint",
                {"status": "auto",
                 "next": ["review the last stretch and name the next step"],
                 "mutations": count},
                evidence=[],
            )
        except Exception:  # noqa: BLE001
            return None
        reset_mutation_counter(archive)
        return (f"auto-checkpoint recorded after {count} tracked-file "
                "mutations (declared auto_checkpoint policy); counter reset")
    if count % threshold == 0:
        return (f"{count} tracked-file mutations since the last checkpoint - "
                "consider `godmode checkpoint`, or declare auto_checkpoint "
                "in .godmode-authorization-policy.json")
    return None


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
    reason = str(preview.get("reason") or preview.get("category", "operation"))[:300]
    # B4-10: a secret-shaped operation used to VANISH from the trial's
    # record here - `Chronicle.append` refuses secret-shaped payloads
    # (`enforce_private_payload`), the best-effort except below swallowed
    # the refusal, and the would-have event was silently dropped: invisible
    # to the digest, the brief, and `observe --report` alike. Redact at
    # write time instead - whole-value replacement, the same convention
    # egress/verdict use - so the EVENT persists even when its text cannot.
    recorded_operation = operation[:500]
    if find_secret_shapes(recorded_operation):
        recorded_operation = "[redacted: secret-shaped content]"
    recorded_reason = reason
    if find_secret_shapes(recorded_reason):
        recorded_reason = "[redacted: secret-shaped content]"
    # Fix round 1, M1: skipped when `record_unrecognized_tool`/
    # `record_malformed_apply_patch` already chronicled this exact miss,
    # unconditionally, before observe mode was even consulted - the same
    # "once, not twice" discipline the enforcement-mode write above applies.
    if not preview.get("_chronicled_miss"):
        try:
            archive.append(
                "refusal",
                str(preview.get("category", "refusal"))[:200] or "refusal",
                {
                    "operation": recorded_operation,
                    "tool": tool or "operation",
                    "tier": str(preview.get("tier", "R?")),
                    "category": preview.get("category", "unclassified-mutation"),
                    "observed": True,
                    "would_have": would_have,
                    # B4-10(c): `observe --report` names reasons; a reason
                    # never persisted cannot be reported. Bounded like the
                    # advisory's own cap below.
                    "reason": recorded_reason,
                },
                evidence=[],
            )
        except Exception:  # noqa: BLE001
            pass
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
    parser.add_argument("--capture-payload", action="store_true",
                        help="CX-2: record this call's structural shape (names/hashes "
                             "only, never values) for building a future host fixture")
    args = parser.parse_args(argv)
    capture_payload = args.capture_payload or bool(os.environ.get(CAPTURE_PAYLOAD_ENV))
    submitted, malformed_payload = _input()
    claude_session = _is_claude_session(submitted)
    project = args.project or str(submitted.get("cwd") or ".")

    # A tool that cannot change anything gets no gate and no cost. Resolving the
    # repository identity costs several git calls, which is worth paying before a
    # mutation and not worth paying before a file read - and the shipped matcher
    # already limits this hook to mutating tools, so this only protects a host
    # that widened it. CX-5: a malformed payload has no readable tool_name field
    # (it parsed to `{}`), so this can never short-circuit a genuinely malformed
    # call into the silent-allow read-only path - it always falls through to the
    # full classify path below, which fails closed on an empty operation.
    if args.event == "pre-action" and str(host_field(submitted, "tool_name") or "") in _READ_ONLY_TOOLS:
        return 0
    try:
        anchor = resolve_anchor(project)
        archive = Chronicle(anchor)
        if not archive.initialized():
            # Stay silent for a genuinely new project, but never for one whose history
            # is merely unreachable: an agent starting here would otherwise be told
            # nothing while prior records sit one command away.
            #
            # CX-5 mode table: an uninitialized project never records
            # anything here, including a malformed-payload degradation -
            # `archive.append` (which `record_hook_degradation` calls)
            # auto-initializes on first write, and doing that from a
            # malformed-payload side effect would silently turn "governance
            # was never asked for" into "governance is now active," exactly
            # the uninvited opt-in this mode table forbids. Ordinary work
            # stays allowed either way; only an initialized project's own
            # health gets tracked.
            # B4-8 extension (field feedback 3): a scope-less
            # `not-initialized` was read as GLOBAL state in the field when
            # the truth was cwd-relative - every answer here names the
            # resolved project root it is about.
            resolved_root = str(anchor.project_root)
            stranded = archive.orphaned()
            if stranded:
                notice = {
                    "godmode": "orphaned-archive",
                    "project": resolved_root,
                    "records": stranded["records"],
                    "reason": stranded["reason"],
                    "next_action": "run `godmode adopt --confirm` to relink this project's history",
                }
                if claude_session:
                    _emit_claude_context(notice)
                else:
                    print(json.dumps(notice))
            elif not claude_session:
                print(json.dumps({
                    "godmode": "not-initialized",
                    "project": resolved_root,
                    "action": f"not initialized for {resolved_root}; "
                              "run godmode init explicitly",
                }))
            return 0

        if malformed_payload:
            # CX-5: recorded for every event type this hook handles, not
            # only pre-action - a degraded mode is about the hook's own
            # health, not about one call's decision. Best-effort: a
            # chronicle write failure must not turn a malformed-payload
            # call into a crashed hook.
            try:
                record_hook_degradation(
                    archive, current_host(), DEGRADE_REASON_MALFORMED_PAYLOAD)
            except Exception:  # noqa: BLE001
                pass

        if args.event == "session-start":
            # CX-1 fix round 1, Critical-2: every real session start writes
            # a lightweight, counts-only freshness anchor, unconditionally -
            # this is the ONLY place that happens automatically, and without
            # it `interception_state` had nothing newer than "the beginning
            # of time" to compare a proof's freshness against (a proof from
            # months ago read as fresh forever). Best-effort: a session that
            # cannot record its own anchor must still be allowed to open -
            # the honesty cost of a missed anchor (a proof stays fresh one
            # session longer than it should) is far smaller than the cost
            # of blocking the session itself over a recording failure.
            try:
                record_session_anchor(archive, current_host())
            except Exception:  # noqa: BLE001
                pass
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

        # Pre-tool boundary. CX-2: every payload - a host's own tool-call
        # shape in any documented dialect, or a bare `{"operation": ...}`
        # string - is translated ONCE into one canonical `HostEvent` here;
        # everything below reads `event.tool`/`event.operation`/
        # `event.targets`, never the raw payload again.
        pretool = is_pretool_event(submitted)
        # Fix round 1 (C2/I1): the prior gate-exactly-once `seen`-set dedup
        # is removed - every call classifies fully. See
        # `godmode_hostevent.py`'s module docstring for why (a request id
        # reused for a genuinely DIFFERENT operation was silently allowed
        # with zero scrutiny, guarding a double-dispatch path that does not
        # exist anywhere in this tree).
        event = parse_host_payload(submitted)
        tool = event.tool
        operation = event.operation

        # CX-1: `godmode hooks probe` sends this exact marker through this
        # exact path to prove the boundary is reachable, not to test whether
        # anything should be allowed. It is denied unconditionally - before
        # ceilings, staged capabilities, or observe mode get a say, none of
        # which may ever turn a probe into an allow, or the proof it writes
        # below would attest to a denial that never actually happened. The
        # denial IS the proof: nothing about a probe the boundary never
        # received could reach this branch to record one.
        if operation.startswith(PROBE_PREFIX):
            host = current_host()
            try:
                archive.append(
                    "refusal", "hook-interception-probe",
                    {
                        "operation": operation[:500],
                        "tool": tool or "operation",
                        "tier": "R5",
                        "category": "hook-interception-probe",
                    },
                    evidence=[],
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                # CX-5: `hook_script=Path(__file__)` hashes THIS exact,
                # currently-executing file - the trust anchor a later
                # `interception_state` read compares the file's THEN-current
                # hash against, to catch an edit made after this proof was
                # written (the same tamper class `godmode_githooks.py`'s own
                # digest already proves is real for the git backstop).
                record_interception_proof(
                    archive, host=host, tool=tool or "operation",
                    request_id=operation[len(PROBE_PREFIX):][:200],
                    hook_script=Path(__file__).resolve(),
                )
            except Exception:  # noqa: BLE001
                pass
            reason = (
                "refused: hook-interception-probe (R5) - this operation exists only "
                "to prove the pre-tool boundary is reachable; it is always denied."
            )
            if pretool:
                body, _code = render_decision(event.host, event.event, "deny", reason)
                print(json.dumps(body, ensure_ascii=False))
                return 0
            print(json.dumps({
                "protected": True, "allow": False, "category": "hook-interception-probe",
                "tier": "R5", "reason": reason,
            }))
            # EXIT 3 REMOVED (CX-2): a live probe on a host whose fail-open
            # semantics treat any non-{0,2} exit as an implicit allow (the
            # Grok probe, Addendum 6) must never be handed a code that means
            # "proceed" on that host by accident - 2 is deny everywhere, 3
            # meant nothing to any documented dialect and fail-opened on at
            # least one.
            return 2

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
        # CX-2: an unknown tool name never degrades into a guessed operation
        # string - it fails closed on its own, dedicated category, and the
        # miss is chronicled (counts only: host + tool name, never the
        # command/target that came with it). This replaces the pre-CX-2
        # generic-invocation degradation path entirely. Fix round 1, C1: a
        # structurally-malformed `apply_patch` body (a directive-looking
        # line that failed to parse) gets its own distinct fail-closed
        # category instead of being folded into "unrecognized tool" - the
        # tool IS known here, the patch body's own shape is what failed.
        if event.tool_kind == TOOL_KIND_UNRECOGNIZED:
            preview = unrecognized_tool_preview(tool)
            record_unrecognized_tool(archive, event.host, tool)
            if capture_payload:
                capture_payload_probe(archive, submitted, event)
        elif event.tool_kind == TOOL_KIND_MALFORMED:
            preview = malformed_apply_patch_preview(tool)
            record_malformed_apply_patch(archive, event.host, tool)
            if capture_payload:
                capture_payload_probe(archive, submitted, event)
        elif operation:
            preview = classify_action(
                operation, project_root=Path(anchor.project_root),
                archive=archive,
                extra_protected=policy.get("password_required", ()),
                require_approval=policy.get("approval_required", ()),
            )
        else:
            preview = {
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
            impact = _ellipsize(
                "; ".join(str(item) for item in preview.get("impact", ())), 160)
            # A question, phrased as one - what a host that actually has an
            # `ask` decision (Claude, Cursor) shows the operator.
            ask_reason = (
                f"{preview['category']} ({preview.get('tier', 'R?')})"
                + (f" - touches {impact}" if impact else "")
                + ". Approve to run it."
            )
            if operation:
                deny_reason = (
                    f"refused: this is irreversible ({preview['category']}, "
                    f"{preview.get('tier', 'R?')})"
                    + (f" - touches {impact}" if impact else "")
                    + ". Run it yourself, rephrase it as something narrower, or "
                    "stage a capability for this exact command: `godmode "
                    "authorize stage --operation "
                    f"{json.dumps(_ellipsize(operation, 200))}` - it needs the password "
                    "from `godmode authorize setup`, is spent once, and expires. "
                    "In a hosted session, type it with a leading '!' to run it "
                    "from the prompt without leaving the conversation.\n"
                    "! godmode authorize stage --from-last-refusal"
                )
            else:
                # CX-2: an unrecognized tool (or any other no-operation-text
                # case) has nothing to stage an exact command for - naming
                # a remedy that names an empty command would be worse than
                # naming none.
                deny_reason = (
                    f"refused: {preview['category']} ({preview.get('tier', 'R?')})"
                    + (f" - touches {impact}" if impact else "")
                    + ". No operation text is available to stage a capability "
                    "for; run this yourself outside the agent, or extend the "
                    "host adapter so this call carries one."
                )
            # CX-2 (Addendum 6): a host with no `ask` decision in its own
            # contract (Grok/Codex/Gemini) never receives "ask" - it is
            # DENIED, with a reason naming the staged-capability remedy, the
            # instant `_decision_for` would otherwise have asked. Computed
            # with the exact same condition `render_decision` uses to fold
            # ask into deny, so the reason text sent and the decision value
            # sent can never disagree about which one this call actually
            # got. Claude/Cursor (both have `ask`) are UNCHANGED from
            # pre-CX-2: `effectively_denied` is only ever True for them when
            # `_decision_for` already said "deny".
            effectively_denied = (
                _decision_for(preview) != "ask" or event.host not in HOSTS_WITH_ASK
            )
            preview["reason"] = deny_reason if effectively_denied else ask_reason
            if effectively_denied:
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
                #
                # Also skipped when `preview["_chronicled_miss"]` is already
                # set (fix round 1, M1): `unrecognized_tool_preview`/
                # `malformed_apply_patch_preview` already wrote their own
                # dedicated record above, before this branch ever ran - a
                # second, generic `refusal` record for the exact same miss
                # is redundant bookkeeping, not a second fact.
                if not observe and not preview.get("_chronicled_miss"):
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
        # CX-2: `event.targets` is one path for Claude's Write/Edit/
        # NotebookEdit (the pre-CX-2 shape, unchanged) and MAY be several
        # for Codex's `apply_patch` (Plan amendment 3: every add/update/
        # delete/rename target reaches this same fence). First denial wins -
        # both checks are binary allow/deny, so there is no "worst of" to
        # rank, only the first target that is not allowed.
        if preview.get("allow") and event.targets:
            # Deferred: only fenced tool calls pay for the fence module - the
            # far more common read-only and R0-R2 tool calls never reach
            # this branch.
            from godmode_runtime.godmode_fence import design_verdict, fence_verdict
            for target in event.targets:
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
                    break
                fenced = fence_verdict(archive, target,
                                       project_root=Path(anchor.project_root))
                if not fenced["allowed"]:
                    preview["allow"] = False
                    preview["fence"] = fenced["fence"]
                    preview["reason"] = f"{fenced['detail']}. {fenced['remedy']}"
                    break

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
                # B4-7 rider 1: an allowed tracked-file mutation ticks the
                # edit counter; at the threshold that becomes a checkpoint
                # suggestion, or - under declared policy - a chronicled
                # auto-checkpoint. Counted here, after every gate said yes,
                # so a refused edit never inflates the count.
                checkpoint_advisory = None
                if event.targets and tool in (
                        "Write", "Edit", "NotebookEdit", "apply_patch"):
                    checkpoint_advisory = _checkpoint_pressure(archive, anchor)
                # An allowed call may still deserve one sentence: a test run
                # piped through a truncating filter destroys the evidence the
                # run exists to produce, or (U-E7) this call would have been
                # denied/asked about and observe mode let it through anyway -
                # the classifier cannot know which run is the deciding one,
                # and observe mode cannot be silent about looser enforcement.
                advisory = (preview.get("observe_advisory")
                            or evidence_pipe_advisory(operation)
                            or checkpoint_advisory)
                if advisory:
                    print(json.dumps({"systemMessage": advisory},
                                     ensure_ascii=False))
                return 0
            if not preview["allow"]:
                body, _code = render_decision(
                    event.host, event.event, _decision_for(preview), preview["reason"])
                print(json.dumps(body, ensure_ascii=False))
            return 0
        print(json.dumps(preview))
        # EXIT 3 REMOVED (CX-2): see the probe branch's comment above - no
        # documented host dialect assigns exit 3 any meaning, and at least
        # one (Grok) fail-opens on it.
        return 0 if preview["allow"] else 2
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
