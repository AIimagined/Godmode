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
from godmode_runtime.godmode_constants import READ_ONLY_TOOLS  # noqa: E402
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
    HOSTS_WITH_ASK, TOOL_KIND_MALFORMED, TOOL_KIND_READ, TOOL_KIND_UNRECOGNIZED,
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

# Tools that read and cannot write. Owned by `godmode_constants` so this
# gate and the Claude adapter cannot disagree about which tools can mutate;
# a tool absent from the set is treated as capable of mutation and pays the
# full check.
_READ_ONLY_TOOLS = READ_ONLY_TOOLS

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
        # S4: the trial states its own age. A field project ran observe for
        # twelve days because the promotion rule keyed on R4/R5 events that
        # never came; a date turns "still observing" from ambient into a
        # decision the reader can see themselves making.
        entered = ""
        try:
            for record in archive.select(kind="action", limit=200):
                if record.get("subject") == "observe-mode-entered":
                    entered = str(record.get("recorded_at", ""))[:10]
        except GodmodeError:
            entered = ""
        notice = (
            "gate in OBSERVE mode"
            + (f" since {entered}" if entered else "")
            + " - nothing will be blocked; every deny/ask "
            "this session would have produced is instead recorded as an "
            "advisory refusal (`godmode roi --digest` reads them back). "
            "Entered via .godmode-authorization-policy.json's gate_mode - "
            "edit that file to return to enforcement, and state it plainly "
            "if the trial is meant to continue."
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
            irreversible = summary["r4"] + summary["r5"]
            asks = summary["r2"] + summary["r3"]
            if summary["total"]:
                # Field report 2026-08-28: a brief that listed r2..r5 counts
                # was read as "340 refused ops, none a real risk". Lead with
                # the tier that means risk, zero stated; name the rest as the
                # friction it is, with the posture that trims it.
                notice += (
                    f" This trial so far: {irreversible} would-have-denied at R4/R5"
                    f" (irreversible: r5={summary['r5']} r4={summary['r4']})"
                    f"{'' if irreversible else ' - none'}; {asks} would-have-asked at R2/R3"
                    f" (r3={summary['r3']} r2={summary['r2']} - friction, not risk;"
                    " `godmode roi --digest` proposes an ask_only posture that trims it)"
                    + (f"; top: {summary['top']}" if summary["top"] else "")
                    + ". `godmode observe --report` lists them."
                )
            else:
                notice += " There are no would-have events recorded yet this trial."
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


def _open_next_actions(records: list[dict[str, Any]]) -> list[str]:
    """The latest checkpoint's declared next-actions - the in-flight work a
    dying session would otherwise take with it. Empty when the latest
    checkpoint declared none (or none exists): finished is finished."""
    for record in reversed(records):
        if record["kind"] == "checkpoint":
            raw = (record.get("data") or {}).get("next") or []
            return [str(item) for item in raw if str(item).strip()] \
                if isinstance(raw, list) else []
    return []


def _capture_interrupted_intent(archive: Chronicle) -> None:
    """B4-4: when a session ends (or compacts) with declared work in flight
    - open next-actions, an unconsumed staged capability, an active plan
    fence - record that fact as counts + subject hashes, so the next resume
    digest can surface it first. Content-free by construction and by
    invariant: the record carries how MUCH was in flight, never what."""
    import hashlib
    import time as _time
    records = archive.read_events()
    open_actions = _open_next_actions(records)
    from godmode_runtime.godmode_fence import declared_fence
    fence_active = declared_fence(archive) is not None
    staged = 0
    try:
        broker = _broker(archive)
        if broker.configured():
            now = int(_time.time())
            staged = sum(
                1 for entry in broker._load().get("staged", [])  # noqa: SLF001
                if int(entry.get("expires_at", 0)) >= now)
    except Exception:  # noqa: BLE001
        staged = 0
    if not (open_actions or staged or fence_active):
        return
    archive.append(
        "action", "interrupted-intent",
        {
            "interrupted": True,
            "open_obligations": len(open_actions),
            "staged_capabilities": staged,
            "plan_fence_active": fence_active,
            "subject_hashes": [
                hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                for text in open_actions[:16]
            ],
        },
        evidence=[],
    )


# A checkpoint older than this is likelier to be behind the project's own
# state document than ahead of it; the brief says so instead of letting a
# resuming agent read an eight-day-old checkpoint as current (field
# report, 2026-08-27).
STALE_CHECKPOINT_DAYS = 7


# Field report 2026-08-28: projects that keep their own state document. The
# first that exists is named in the brief so a stale checkpoint is never
# the only pointer. Relative POSIX paths, checked in this order.
RESUME_DOC_CANDIDATES = (
    "docs/STATE.md", "STATE.md", "docs/HANDOVER.md", "HANDOVER.md",
    "docs/HANDOFF.md", "HANDOFF.md", "docs/RESUME.md", "RESUME.md",
    "docs/STATUS.md", "STATUS.md",
)


def project_resume_doc(project_root: Path) -> str | None:
    """The project's own resume document, if it keeps one - the first of
    RESUME_DOC_CANDIDATES that exists, as a relative POSIX path."""
    for candidate in RESUME_DOC_CANDIDATES:
        if (project_root / candidate).is_file():
            return candidate
    return None


def _final_reply_text(submitted: dict[str, Any]) -> str:
    """The turn's final assistant text, bounded, from the payload itself
    (Grok sends `lastAssistantMessage`) or the host transcript's tail
    (Claude/Codex send `transcript_path`). Read in memory, never stored."""
    direct = submitted.get("lastAssistantMessage") or submitted.get("last_assistant_message")
    if isinstance(direct, str) and direct.strip():
        return direct[-6000:]
    path = submitted.get("transcript_path") or submitted.get("transcriptPath")
    if not path:
        return ""
    try:
        lines = Path(str(path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines[-400:]):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        parts = message.get("content")
        if isinstance(parts, str):
            return parts[-6000:]
        if isinstance(parts, list):
            texts = [str(p.get("text", "")) for p in parts
                     if isinstance(p, dict) and p.get("type") == "text"]
            joined = "\n".join(t for t in texts if t)
            if joined.strip():
                return joined[-6000:]
    return ""


def _open_obligations_touched(archive: Any, reply_text: str) -> list[str]:
    """Open obligations whose vocabulary the turn's final text shares (S9,
    report 16 2026-08-29): an obligation recorded mid-session surfaced only
    at resume and session close - inert for the whole middle. The turn
    boundary is the carrier the claim echo already proved. Latest record
    per subject is the state; >=3 salient shared words is the match bar the
    guard-pin lookup already uses; bounded to two subjects."""
    try:
        from godmode_runtime.godmode_sources import _salient_words

        latest: dict[str, dict] = {}
        for record in archive.select(kind="obligation", limit=200):
            latest[str(record.get("subject", ""))] = record
        reply_words = _salient_words(reply_text)
        if not reply_words:
            return []
        touched = []
        for subject, record in latest.items():
            data = record.get("data") or {}
            if str(data.get("status", "open")) in ("closed", "done", "retired"):
                continue
            vocab = _salient_words(f"{subject} {data.get('value', '')}")
            if len(reply_words & vocab) >= 3:
                touched.append(subject)
        return touched[:2]
    except Exception:  # noqa: BLE001
        return []


def _unrecorded_claims(archive: Any, reply_text: str) -> list[str]:
    """Claim-shaped sentences in the reply with no claim record behind them.
    Reuses the public-surface claim definition (`claimscan.is_claim`) and
    the archive's normalised claim set - one definition of a claim, not two."""
    from godmode_runtime.godmode_claimscan import _normalise, _recorded_claims, is_claim

    try:
        recorded = _recorded_claims(archive)
    except Exception:  # noqa: BLE001 - an unreadable archive silences the advisory
        return []
    found: list[str] = []
    for raw_line in reply_text.splitlines():
        line = raw_line.strip().lstrip("-*#>| ").strip()
        if not line:
            continue
        for chunk in line.replace("!", ".").replace("?", ".").split("."):
            sentence = chunk.strip()
            if len(sentence) < 15 or not is_claim(sentence):
                continue
            if _normalise(sentence) in recorded:
                continue
            found.append(sentence)
    return found


def checkpoint_age(record: dict[str, Any], *, now: Any = None,
                   resume_doc: str | None = None) -> tuple[int | None, str | None]:
    """(whole days since the record was written, note) - the note only past
    STALE_CHECKPOINT_DAYS, and None for a record with no readable time.
    `resume_doc` names the project's own state document when it has one,
    so the note can say which file to read first."""
    from datetime import datetime, timezone

    raw = record.get("recorded_at")
    if not isinstance(raw, str):
        return None, None
    try:
        written = datetime.fromisoformat(raw)
    except ValueError:
        return None, None
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    days = max(0, int((current - written).total_seconds() // 86_400))
    note = None
    if days > STALE_CHECKPOINT_DAYS:
        if resume_doc:
            note = (f"this checkpoint is {days} days old; {resume_doc} is the "
                    "project's own state document - read it first, and write a "
                    "checkpoint as part of the next handover")
        else:
            note = (f"this checkpoint is {days} days old; prefer the project's own "
                    "state document if it is newer, and write a checkpoint as part "
                    "of the next handover")
    return days, note


def _silenced_by_ask_only(policy: dict[str, Any], preview: dict[str, Any]) -> bool:
    """True when the policy names `ask_only`, this call would have asked,
    its tier is R2/R3, and its category is not on the list. R4 and R5 are
    never silenced: the list narrows attention, it never lowers the ceiling."""
    listed = policy.get("ask_only")
    if not listed:
        return False
    if _decision_for(preview) != "ask":
        return False
    if str(preview.get("tier") or "") not in ("R2", "R3"):
        return False
    return str(preview.get("category") or "") not in set(listed)


def _session_counts(archive: Chronicle) -> dict[str, int]:
    """Counts of what happened since the last checkpoint, by kind. Numbers
    only - the auto checkpoint must carry no operation text."""
    counts: dict[str, int] = {}
    since = 0
    records = archive.read_events(verify=False)
    for record in records:
        if record.get("kind") == "checkpoint":
            since = record.get("sequence", 0)
    for record in records:
        if record.get("sequence", 0) <= since:
            continue
        kind = str(record.get("kind"))
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _resume_digest(archive: Chronicle, project_root: Path,
                   obligations: dict[str, Any]) -> dict[str, Any]:
    """B4-4: the counts-only "where you left off" answer, rendered into the
    existing brief within its budget. An interruption recorded since the
    last checkpoint comes first; a checkpoint whose file refs no longer
    resolve is marked stale rather than repeated as truth; the unattested-
    HARD count is lifted from the obligations block already computed rather
    than derived a second time."""
    records = archive.read_events()
    digest: dict[str, Any] = {}
    checkpoints = [r for r in records if r["kind"] == "checkpoint"]
    # An automatic session-end checkpoint is dated, not authored: it must
    # not hide an interruption captured moments before it. Only a written
    # checkpoint counts as having covered what came before it.
    authored = [r for r in checkpoints if not (r.get("data") or {}).get("auto")]
    last_checkpoint_sequence = authored[-1]["sequence"] if authored else 0
    interruptions = [r for r in records
                     if r["kind"] == "action"
                     and r["subject"] == "interrupted-intent"]
    if interruptions and interruptions[-1]["sequence"] > last_checkpoint_sequence:
        data = interruptions[-1].get("data") or {}
        digest["interrupted"] = {
            "sequence": interruptions[-1]["sequence"],
            "open_obligations": data.get("open_obligations", 0),
            "staged_capabilities": data.get("staged_capabilities", 0),
            "plan_fence_active": bool(data.get("plan_fence_active")),
        }
    if checkpoints:
        checkpoint = checkpoints[-1]
        entry: dict[str, Any] = {
            "subject": str(checkpoint["subject"])[:120],
            "status": str((checkpoint.get("data") or {}).get("status", "")),
            "sequence": checkpoint["sequence"],
        }
        resume_doc = project_resume_doc(project_root)
        if resume_doc:
            entry["resume_doc"] = resume_doc
        age_days, age_note = checkpoint_age(checkpoint, resume_doc=resume_doc)
        if age_days is not None:
            entry["age_days"] = age_days
        if age_note:
            entry["note"] = age_note
        stale_refs = sum(
            1 for ref in checkpoint.get("evidence", [])
            if isinstance(ref, str) and ref.startswith("file:")
            and not (project_root / ref[len("file:"):]).exists())
        if stale_refs:
            entry["stale"] = True
            entry["stale_refs"] = stale_refs
        digest["last_checkpoint"] = entry
    digest["open_obligations"] = len(_open_next_actions(records))
    charter = obligations.get("charter")
    if isinstance(charter, dict) and "unattested_hard" in charter:
        digest["unattested_hard_rules"] = charter["unattested_hard"]
    verdicts = [r for r in records if r["kind"] == "verdict"][-5:]
    if verdicts:
        counts: dict[str, int] = {}
        for record in verdicts:
            disposition = str((record.get("data") or {}).get("disposition", "?"))
            counts[disposition] = counts.get(disposition, 0) + 1
        digest["last_verdicts"] = counts
    return digest


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


def _sources_gate_reason(archive: Chronicle, anchor: Any,
                         session: str | None) -> str | None:
    """Obligation 4094 (S5): the required-sources counter gates, not only
    reports. Returns the ask reason for the first otherwise-allowed pre-tool
    call of a session while a bound authority document is uncited and
    unexempted - naming the unread files and both escapes - and None ever
    after: once per session by contract, so the gate informs without nagging.
    """
    if not session:
        return None
    try:
        for record in archive.select(kind="action", limit=150):
            if (record.get("subject") == "sources-gate"
                    and (record.get("data") or {}).get("session") == session):
                return None
    except Exception:
        return None
    try:
        from godmode_runtime.godmode_sources import required_sources_view

        view = required_sources_view(Path(anchor.project_root), archive)
    except Exception:
        return None
    unread = view.get("unread") or []
    if not unread:
        return None
    try:
        archive.append("action", "sources-gate",
                       {"session": session, "unread": len(unread),
                        "documents": view.get("documents", 0)},
                       evidence=[])
    except Exception:
        pass
    named = ", ".join(unread[:5])
    return (
        f"required sources unread ({len(unread)} of {view.get('documents', 0)}): "
        f"{named}. Read them and cite each with file:<path> evidence, or exempt "
        "one on the record: `godmode remember --kind decision --subject "
        '"sources-exemption:<path>" --value "<why>"`. Asked once per session; '
        "approve to proceed without."
    )


# Obligation 4516: twice in one day a removal-shaped operation was saved by
# reading discipline while the governance preview - the designed net - sat
# uninvoked. The boundary now carries the skill's name to the moment.
_REMOVAL_SHAPED = frozenset({
    "filesystem-mutation", "worktree-discard", "local-repository-change",
})


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
    parser.add_argument("event", choices=["stop", "session-start", "pre-compact", "session-end",
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
            # B4-4: the resume digest, counts only, inside the same budget -
            # best-effort like every other section, never a blocked session.
            try:
                brief["resume"] = _resume_digest(
                    archive, Path(anchor.project_root), brief["obligations"])
            except GodmodeError as exc:
                # Stated, not skipped: an absent `resume` block reads as
                # "nothing to resume", which is a claim. This says the
                # digest could not be built and why.
                brief["resume"] = {"unavailable": str(exc)[:160]}
            # Sprint L1 (decision 4114): the top laws ride the brief so the
            # Code of Law fires without being fetched. Bounded, and stated
            # rather than skipped on failure - an absent `laws` block would
            # read as "no laws", which is a claim.
            try:
                from godmode_runtime.godmode_law import (
                    debrief_status, record_delivery, top_laws)
                laws = top_laws(archive, 3)
                if laws:
                    brief["laws"] = laws
                    # S11-A: the meta-loop's staleness gauge, three bounded
                    # fields - the first live debrief had nothing prompting
                    # a second.
                    brief["law_debrief"] = debrief_status(archive)
                    # L2: the delivery receipt - the denominator without
                    # which "violated 0" cannot be told from "never seen".
                    record_delivery(
                        archive, laws,
                        session=str(submitted.get("session_id") or "") or None)
            except Exception as exc:  # noqa: BLE001
                brief["laws"] = {"unavailable": str(exc)[:120]}
            if claude_session:
                _emit_claude_context(brief)
            else:
                print(json.dumps({"godmode": "context", "brief": brief}))
                # S8 addendum (three Grok field reports in a row): Grok
                # ignores SessionStart stdout, so the brief never reached
                # the model and resume stayed a manual step. Park a bounded
                # copy beside the archive; the first prompt boundary
                # delivers it as context exactly once, then deletes it -
                # the same parking contract as the claim echo.
                if current_host() == "grok":
                    try:
                        rendered = json.dumps(
                            brief, ensure_ascii=False, default=str)[:4000]
                        (archive.root / "godmode-brief-echo.json").write_text(
                            json.dumps({"brief": rendered}, ensure_ascii=False),
                            encoding="utf-8")
                    except OSError:
                        pass
            return 0

        if args.event == "stop":
            # S4 (obligation 4102): the claim gate at the message boundary.
            # Seven field reports in one day ended with "claim still
            # unused" - the verbs wait to be invoked and never are, so the
            # check moves to the moment of claiming. Advisory ONLY: a
            # systemMessage naming the unsupported claim-shaped sentence
            # and the one command that records it. Never a block, never a
            # nonzero exit, and silent when the reply carries no claim, when
            # every claim has a record, or when the host is re-firing the
            # hook (stop_hook_active) - a Stop hook that loops is worse
            # than no gate at all. The reply text is read in memory from
            # the host's own transcript and never stored (the 4018 privacy
            # decision governs here too).
            if submitted.get("stop_hook_active") or submitted.get("stopHookActive"):
                return 0
            reply_text = _final_reply_text(submitted)
            if not reply_text:
                return 0
            unsupported = _unrecorded_claims(archive, reply_text)
            touched = _open_obligations_touched(archive, reply_text)
            if touched:
                print(json.dumps({"systemMessage": (
                    "godmode: open obligation(s) this turn touches: "
                    + ", ".join(touched)
                    + " - update or close them, or they resurface.")}))
                try:
                    echo = archive.root / "godmode-claim-echo.json"
                    parked = {}
                    if echo.exists():
                        parked = json.loads(echo.read_text(encoding="utf-8"))
                    parked["obligations"] = touched
                    echo.write_text(json.dumps(parked, ensure_ascii=False),
                                    encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            if unsupported:
                shown = "; ".join(f"'{s[:160]}'" for s in unsupported[:2])
                print(json.dumps({"systemMessage": (
                    f"godmode: {len(unsupported)} claim-shaped sentence(s) in this "
                    f"reply have no record: {shown} - record with `godmode claim "
                    "--cite <evidence>` (grades honestly, downgrades what the "
                    "citations cannot carry) or soften the sentence.")}))
                # S8 (obligation 4538, self-census 2026-08-29): the
                # systemMessage above reaches the OPERATOR; the model that
                # made the claim never sees it, so nothing changes next turn
                # (fifteen sessions of "claim unused" measured exactly this).
                # The flagged sentences - the model's OWN output, bounded -
                # are parked beside the archive, outside it, and deleted the
                # moment the next prompt boundary delivers them back.
                try:
                    echo = archive.root / "godmode-claim-echo.json"
                    parked = {}
                    if echo.exists():
                        parked = json.loads(echo.read_text(encoding="utf-8"))
                    parked["sentences"] = [s[:200] for s in unsupported[:3]]
                    echo.write_text(json.dumps(parked, ensure_ascii=False),
                                    encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return 0

        if args.event == "user-prompt":
            # Recorded here because it cannot be recovered anywhere else. The
            # host's transcript stores an input at the moment it is delivered,
            # not the moment it was typed, so an ask that arrived mid-task is
            # indistinguishable afterwards from one that waited its turn - and
            # the mid-task ones are exactly the ones that get lost.
            #
            # Silent by contract, with ONE exception (S8, obligation 4538):
            # when the previous turn's Stop hook parked unrecorded claim
            # sentences, they are delivered here as context TO THE MODEL -
            # the audience that can actually record or soften them - exactly
            # once, and the parking file is deleted before anything else can
            # read it. Otherwise this hook adds no context and blocks
            # nothing.
            echo_path = archive.root / "godmode-claim-echo.json"
            try:
                if echo_path.exists():
                    parked = json.loads(echo_path.read_text(encoding="utf-8"))
                    echo_path.unlink()
                    sentences = [str(s)[:200]
                                 for s in (parked.get("sentences") or [])][:3]
                    touched = [str(s)[:120]
                               for s in (parked.get("obligations") or [])][:2]
                    parts = []
                    if sentences:
                        listed = "; ".join(f"'{s}'" for s in sentences)
                        parts.append(
                            "godmode: your previous reply made "
                            f"{len(sentences)} claim-shaped statement(s) "
                            f"with no record: {listed}. Record each with "
                            "`godmode claim --cite <evidence>` (it grades "
                            "honestly) or soften the wording this turn.")
                    if touched:
                        parts.append(
                            "godmode: open obligation(s) the previous turn "
                            "touched: " + ", ".join(touched)
                            + " - act on them or close them on the record.")
                    if parts:
                        joined = " ".join(parts)
                        print(json.dumps({"hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": joined}},
                            ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass
            # S8 addendum: the parked continuity brief, for hosts that
            # ignore SessionStart stdout (Grok). Delivered once; both the
            # Claude-dialect key and a top-level additionalContext ride the
            # same object so whichever the host reads, it reads.
            brief_echo = archive.root / "godmode-brief-echo.json"
            try:
                if brief_echo.exists():
                    parked = json.loads(brief_echo.read_text(encoding="utf-8"))
                    brief_echo.unlink()
                    rendered = str(parked.get("brief") or "")[:4000]
                    if rendered:
                        print(json.dumps({
                            "hookSpecificOutput": {
                                "hookEventName": "UserPromptSubmit",
                                "additionalContext":
                                    "godmode continuity brief: " + rendered},
                            "additionalContext":
                                "godmode continuity brief: " + rendered,
                        }, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass
            prompt = str(submitted.get("prompt", ""))
            try:
                from godmode_runtime.godmode_requests import record_request
                record_request(
                    archive, prompt,
                    session=str(submitted.get("session_id") or "") or None,
                    tools_in_flight=int(submitted.get("tools_in_flight") or 0),
                )
                # L2: the operator-correction detector rides the same guarded
                # block - a correction-shaped prompt becomes a law candidate,
                # keywords and digest only, never the sentence.
                from godmode_runtime.godmode_law import (
                    record_correction_candidate, record_instruction_candidate)
                record_correction_candidate(
                    archive, prompt,
                    session=str(submitted.get("session_id") or "") or None)
                # S6 (obligation 4435): the first telling of a standing rule
                # lands in the archive without the agent volunteering it.
                record_instruction_candidate(
                    archive, prompt,
                    session=str(submitted.get("session_id") or "") or None)
            except Exception:  # noqa: BLE001
                # A prompt that cannot be stored - a secret-shaped paste the
                # archive refuses, a locked store - must not stop the turn the
                # operator is trying to have.
                pass
            return 0

        if args.event in {"pre-compact", "session-end"}:
            # B4-4: capture in-flight declared work BEFORE anything else in
            # this branch - the summary checkpoint below is optional and a
            # session dying without one is exactly the case this exists for.
            try:
                _capture_interrupted_intent(archive)
            except GodmodeError:
                # A capture that cannot be written is a hook-health fact,
                # not nothing: recorded through the same degradation path
                # every other boundary failure in this file uses, so it
                # surfaces in `hooks status` instead of vanishing. The
                # session still ends normally - this is bookkeeping about
                # bookkeeping, and it may never cost the operator a close.
                record_hook_degradation(
                    archive, current_host(), "interrupted-intent-capture-failed")
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
            auto = False
            if not summary and args.event == "session-end":
                # Field report, 2026-08-27: a host's SessionEnd payload
                # carries no summary, so this branch never wrote anything,
                # and the next session's brief showed a checkpoint eight
                # days old as if it were current. A counts-only checkpoint
                # written at every session end is not a handover, and it
                # says so in its status - but it is dated today, and it is
                # what stops the brief lying about when work last happened.
                summary = "session-end (auto, counts only)"
                auto = True
            if not summary:
                print(json.dumps({"godmode": "no-structured-checkpoint", "stored": False}))
                return 0
            data: dict[str, Any] = {
                "status": "auto" if auto else str(submitted.get("status", "active"))[:40],
                "next": _bounded_list(submitted.get("next")),
                "hypothesis": str(submitted.get("hypothesis", ""))[:500] or None,
                "outcome": str(submitted.get("outcome", ""))[:100] or None,
                "lifecycle": args.event,
            }
            if auto:
                data["auto"] = True
                data["counts"] = _session_counts(archive)
            record = archive.append(
                "checkpoint",
                summary[:200],
                data,
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
        # H3 (external audit): `policy_unreadable_detail` is kept alongside
        # the `{}` degrade below, rather than only the degrade itself -
        # this call site (unlike the session-start notice above) makes a
        # real allow/ask decision from `policy`, and losing the detail here
        # is what let that decision silently fall back to "no policy was
        # ever declared" further down.
        policy_unreadable_detail: str | None = None
        try:
            policy = local_authorization_policy(archive)
        except GodmodeError as exc:
            policy = {}
            policy_unreadable_detail = str(exc)
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
        elif event.tool_kind == TOOL_KIND_READ:
            # Field report 2026-08-28 (Grok live): a host's own read-only
            # builtin (get_command_or_subagent_output) arrived unrecognized
            # and fail-closed, blocking ordinary work. An adapter that
            # POSITIVELY identified a read-kind tool is allow by
            # construction - reads mutate nothing the tiers protect - while
            # unknown names keep failing closed one branch above.
            preview = {"protected": False, "category": "host-read-tool",
                       "impact": []}
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
        # H3 (external audit): a malformed/unreadable policy file was
        # caught above and silently replaced with `{}`, which reads to
        # every check below as "no policy was ever declared" - an
        # operator's own `approval_required`/`password_required` widening
        # evaporates the instant their JSON has a typo, and the exact
        # category they protected reverts to whatever `classify_action`'s
        # UNWIDENED baseline says (the audit's own repro: R1, silently
        # allowed). The lost widening cannot be recovered - the file that
        # named it is the one that failed to parse - so this fails closed
        # the only honest way available: the policy being unreadable is
        # itself surfaced as a reason to ask, on every call this (full,
        # archive-backed) gate reaches, until the file is fixed. Never
        # applied when the baseline already asked/refused on its own -
        # this only ever ADDS protection, the same tighten-only direction
        # `extra_protected`/`require_approval` themselves are documented to
        # take.
        if policy_unreadable_detail is not None and not preview.get("protected"):
            preview["protected"] = True
            preview["category"] = preview.get("category") or "policy-unreadable"
            preview["impact"] = list(preview.get("impact", ())) + [
                "the authorization policy file is unreadable "
                f"({policy_unreadable_detail}); any approval_required/"
                "password_required it declared cannot be honoured, so this "
                "asks rather than silently reverting to no policy"
            ]
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
        elif _silenced_by_ask_only(policy, preview):
            # The focused posture (field report 2026-08-27): an R2/R3 ask
            # for a category the operator did not list is an allow - with
            # a record, never silently. R4 and R5 never reach here.
            preview["allow"] = True
            preview["silenced_by"] = "ask_only"
            try:
                archive.append("action", str(preview.get("category") or "unclassified-mutation"), {
                    "category": str(preview.get("category") or ""),
                    "tier": str(preview.get("tier") or ""),
                    "tool": str(host_field(submitted, "tool_name") or "")[:40],
                    "gate": "allow",
                    "silenced_by": "ask_only",
                })
            except GodmodeError:
                record_hook_degradation(archive, current_host(), "ask-only-record-failed")
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
            governance_note = (
                " Preview it first with the godmode-governance skill."
                if str(preview.get("category")) in _REMOVAL_SHAPED else "")
            # A question, phrased as one - what a host that actually has an
            # `ask` decision (Claude, Cursor) shows the operator.
            ask_reason = (
                f"{preview['category']} ({preview.get('tier', 'R?')})"
                + (f" - touches {impact}" if impact else "")
                + ". Approve to run it." + governance_note
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
                ) + governance_note
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
            if not effectively_denied and not observe:
                # Obligation 4026 (S4): an enforce-mode ask was invisible -
                # only denies were chronicled, so nothing could learn from
                # what the operator actually approves. Counts only: tier and
                # category, never the operation. Best-effort the same way
                # the refusal record below degrades.
                try:
                    archive.append(
                        "action", "gate-asked",
                        {"tier": str(preview.get("tier", "R?")),
                         "category": preview.get("category", "unclassified"),
                         "tool": tool or "operation"},
                        evidence=[],
                    )
                except Exception as error:  # noqa: BLE001
                    from godmode_runtime.godmode_sentinel import _degraded

                    _degraded(f"recording a gate ask: {type(error).__name__}")
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
                    # Obligation 4523: a LIVE shim block is the proof the
                    # grade was waiting for. The OpenCode shim marks its
                    # spawns (GODMODE_SHIM_BOUNDARY), and its documented
                    # throw stops the tool - so a deny relayed through it
                    # IS host-acknowledged, recorded TTL-bounded like every
                    # other proof. A self-injected probe still cannot claim
                    # this: it does not run under the shim's marker.
                    if os.environ.get("GODMODE_SHIM_BOUNDARY") == "opencode":
                        try:
                            record_interception_proof(
                                archive, host="opencode",
                                tool=tool or "operation",
                                request_id=(
                                    f"live-shim-{event.request_id or 'call'}")[:200],
                                hook_script=Path(__file__).resolve(),
                                host_acknowledgement=True,
                            )
                        except Exception:  # noqa: BLE001
                            pass

        # Obligation 4094 (S5): the required-sources gate, before the fence.
        # Once per session, the first pre-tool call that would otherwise be
        # allowed while a bound authority document is uncited becomes an ask
        # naming the unread files and both escapes (cite it, or exempt it on
        # the record). Observe mode converts it like every other would-ask.
        if pretool and preview.get("allow") and not preview.get("capability_consumed"):
            sources_reason = _sources_gate_reason(archive, anchor, session)
            if sources_reason is not None:
                preview["allow"] = False
                preview["sources_gate"] = True
                preview["reason"] = sources_reason

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

        # Sprint 9: what the host said about its OWN boundary, recorded
        # beside what godmode decided. Every adapter already lifted this
        # onto the event and nothing ever wrote it, so the evidence was
        # collected and dropped. Recorded only when the host actually
        # carried approval metadata - most calls carry none, and a row per
        # call would bury the ones that say something.
        #
        # Placed after observe mode so the recorded decision is the one
        # that took effect, not the one that would have. Best-effort by the
        # same contract as every other write on this path: a chronicle that
        # cannot be written must not fail the tool call.
        if event.approval_context:
            try:
                from godmode_runtime.godmode_hostapproval import record_host_approval

                record_host_approval(
                    archive, host=event.host, tool=tool, operation=operation,
                    approval_context=event.approval_context,
                    godmode_decision=_decision_for(preview),
                )
            except GodmodeError as error:
                from godmode_runtime.godmode_sentinel import _degraded

                _degraded(f"recording a host approval: {type(error).__name__}")

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
        # M7 (external audit): `claude_session` is read from the PAYLOAD
        # (`hook_event_name == "SessionStart"`, in `_is_claude_session`),
        # never from argv - a payload that CLAIMED `hook_event_name:
        # "SessionStart"` while argv (`args.event`, the host's own
        # invocation of this hook, unforgeable by the payload) actually
        # said `pre-action` used to take the branch below regardless: a
        # friendly systemMessage and exit 0, on ANY error raised anywhere
        # above - silently allowing the tool call argv says this really
        # was. argv decides which branch handles the error FIRST, before
        # `claude_session` gets a say, and a pre-action error can never
        # reach the session-start success path.
        if args.event == "pre-action":
            reason = (
                f"godmode error during pre-action evaluation ({exc}); refusing "
                "rather than allowing a call this hook could not evaluate"
            )
            body, _code = render_decision(current_host(), "", "deny", reason)
            print(json.dumps(body, ensure_ascii=False))
            # Exit 2 alongside the deny-shaped JSON body: a host that reads
            # the body (Claude/Cursor/Grok) sees "deny" there; a host that
            # only reads the exit code sees nonzero either way. Never 0 -
            # this is the exact branch M7 exists to close.
            return 2
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
