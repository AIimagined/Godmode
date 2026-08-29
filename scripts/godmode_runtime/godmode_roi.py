"""ROI report - counts-only, no causal language (U-E1).

The measurement loop closed: burn (`metric` records, C-79/U-T1) reported
beside gate activity, verdict dispositions (U-V1), precedent hits, and fence
findings - from stored records only, never an invented "savings" number.

**What this counts.** One linear fold over `archive.read_events()` (plus a
single cheap pre-scan to locate the `--sessions` window, when requested -
still O(n), never O(n) per bucket). Every number in the report is either a
count of records or a sum drawn from records whose kind and shape are named,
so a reader can walk from a number back to the record that produced it via
`basis` (`"seq:<sequence>"` references, resolvable with `archive.select()`).

**Tokens.** From `metric` records (`godmode_session_log.record_measurement`):
`measured: True` records contribute `tokens_in`/`tokens_out` to the sum and
count toward `measured_sessions`; `measured: False` records (a missing or
unreadable transcript, `record_measurement`'s own stated gap) count toward
`unmeasured_sessions` and contribute no token numbers. When no session was
measured, `tokens` carries no `in`/`out` keys at all - a gap is stated, never
interpolated as zero or guessed from anything else.

**Gate activity, precedent hits, fence findings.** Denials have a real,
already-shipped source: `godmode_session_hook.py` appends a `kind="refusal"`
record at every R5 deny (`stage_from_refusal` reads them back the same way).
Every `refusal` record IS a denial - the hook's `ask` branch never appends
one, only the deny branch does - so `gate.denied` folds `kind="refusal"`
records unconditionally, no field to check. For `asked`/`advisories` (and a
second, additional source for `denied`), this module also defines the
convention a future emitter would use: an `action` record whose
`data["roi_event"]` is one of the closed values below (`GATE_DENIED`,
`GATE_ASKED`, `GATE_ADVISORY`, `PRECEDENT_HIT`, `FENCE_FINDING`). No shipped
writer emits `action`/`roi_event` records yet, and the two sources are
disjoint by kind (`refusal` vs `action`), so no dedupe is needed between
them - a record can only ever be counted once. Until an `action`/`roi_event`
writer exists, the `asked`/`advisories` buckets and this second `denied`
source count what is actually in the archive - zero, honestly, rather than a
number nothing produced. The same discipline covers
`verdicts.contested`: the `verdict` disposition vocabulary
(`godmode_verdict.DISPOSITIONS`) does not include `"contested"` yet - a
future verdict-panel unit (U-E4) may ship it - so this report counts
`disposition == "contested"` where it finds it and reports 0 where it does
not, rather than raising on a disposition that has not shipped.

**Framing, enforced in the emitter, not merely documented.** `render_roi`
never prints a causal-attribution word (`CAUSAL_DENYLIST`, tested against its
own output). A REFUTED verdict is rendered as what the event IS -
`rework-candidate-caught` - never a claim about what it might have averted.
Nothing from a record's free-text fields (a claim's prose, a gate's reason)
is ever copied into the rendered report; only counts and `seq:` references
travel outward.
"""

from __future__ import annotations

import json
from typing import Any

from .godmode_chronicle import Chronicle

# The closed vocabulary a future gate/precedent/fence emitter uses to tag an
# `action` record as something this report folds. See the module docstring:
# no shipped writer emits these yet, so every count below is honest, not
# merely optimistic - it counts records that exist.
GATE_DENIED = "gate:denied"
GATE_ASKED = "gate:asked"
GATE_ADVISORY = "gate:advisory"
PRECEDENT_HIT = "precedent:hit"
FENCE_FINDING = "fence:finding"

_ROI_EVENTS = (GATE_DENIED, GATE_ASKED, GATE_ADVISORY, PRECEDENT_HIT, FENCE_FINDING)

# Never printed by render_roi, checked against its own output below. This is
# the framing rule from the spec, made mechanical: a rendered report that
# claims a saving, a prevention, an avoidance, an earning, or an "ROI of X"
# is asserting a counterfactual nobody measured. Lowercase, matched against
# lowercased rendered text - case is not a way around this.
CAUSAL_DENYLIST = ("saved", "prevented", "avoided", "earned", "roi of")

# B4-10(d): accumulated R4/R5 would-have events at which the session brief
# states the promotion case plainly. Three rather than one: a single
# irreversible-tier event is already visible in the brief's counts line the
# moment it exists; the prompt is for a pattern, not an incident.
OBSERVE_PROMOTION_THRESHOLD = 3

_WOULD_HAVE_TIERS = ("r2", "r3", "r4", "r5")

# The categories an `ask_only` proposal always keeps: the ones whose
# operation cannot be undone by the next command. Field report 2026-08-27:
# in one observed session these were 13 of 304 asks, and they sat in the
# same bucket as 137 inline interpreter runs. Any category that produced
# an R4/R5 event joins them in the proposal; nothing else does.
IRREVERSIBLE_CATEGORIES: tuple[str, ...] = (
    "worktree-discard", "git-history-or-remote",
    "release-or-external-write", "process-control",
)
_SILENCEABLE_TIERS = frozenset({"R2", "R3"})


def _tune(by_category: dict[str, int],
          tiers_by_category: dict[str, set[str]]) -> dict[str, Any] | None:
    """Propose an `ask_only` list from what was observed. Never installed:
    the operator writes the key by hand, and the proposal says so."""
    if not by_category:
        return None
    keep = set(IRREVERSIBLE_CATEGORIES)
    for category, tiers in tiers_by_category.items():
        if tiers - _SILENCEABLE_TIERS:
            keep.add(category)
    kept = sum(n for c, n in by_category.items() if c in keep)
    silenced = {c: n for c, n in sorted(by_category.items()) if c not in keep}
    ask_only = sorted(keep)
    return {
        "ask_only": ask_only,
        "asks_kept": kept,
        "asks_silenced": sum(silenced.values()),
        "silenced_by_category": silenced,
        "policy": {"ask_only": ask_only},
        "note": ("proposal only - write `ask_only` into "
                 ".godmode-authorization-policy.json by hand to adopt it; R4 "
                 "still asks and R5 still denies whatever the list says"),
    }

# `basis` names every counted record so a number can be checked, not
# believed - bounded so a long-lived archive cannot make the report itself
# unbounded.
_BASIS_CAP = 200


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def roi_report(archive: Chronicle, sessions: int | None = None) -> dict[str, Any]:
    """Fold the archive into the counts-only ROI shape. One linear pass.

    `sessions=None` folds the whole archive. `sessions=N` narrows the fold to
    records at or after the sequence of the Nth-from-last `session` record -
    a single, cheap pre-scan of the already-loaded record list, not a second
    read of the archive.
    """
    records = archive.read_events()

    floor_sequence = 0
    if sessions is not None and sessions > 0:
        session_sequences = [r["sequence"] for r in records if r["kind"] == "session"]
        if len(session_sequences) > sessions:
            floor_sequence = session_sequences[-sessions]

    session_count = 0
    tokens_in = 0
    tokens_out = 0
    measured_sessions = 0
    unmeasured_sessions = 0
    gate_denied = 0
    gate_asked = 0
    gate_advisories = 0
    verdict_confirmed = 0
    verdict_refuted = 0
    verdict_contested = 0
    precedent_hits = 0
    fence_findings = 0
    basis: list[str] = []

    def _cite(record: dict[str, Any]) -> None:
        if len(basis) < _BASIS_CAP:
            basis.append(f"seq:{record['sequence']}")

    for record in records:
        if record["sequence"] < floor_sequence:
            continue
        kind = record["kind"]
        data = record.get("data") or {}

        if kind == "session":
            session_count += 1

        elif kind == "refusal":
            # U-E7: a refusal carrying `observed: True` was written under
            # gate_mode=observe - the call was NEVER actually denied, only
            # classified as though it would have been. Folding it into
            # `gate.denied` here would misreport a hypothetical as a real
            # enforcement outcome, which is exactly the causal-attribution
            # slip this report's own framing rule exists to refuse. It is
            # counted instead by `roi_digest`, below, labeled
            # `would-have-denied`/`would-have-asked` - an event label, never
            # a claim about what the operation would have done or what
            # would have followed. Every OTHER refusal record IS a real
            # denial - godmode_session_hook.py only appends the non-observed
            # shape from its deny branch (see the module docstring) - and
            # those still fold here, disjoint from the `action`/`roi_event`
            # convention below, so folding both never double-counts.
            if data.get("observed") is True:
                continue
            gate_denied += 1
            _cite(record)

        elif kind == "metric":
            if data.get("measured") is True:
                measured_sessions += 1
                tokens_in += _int(data.get("tokens_in"))
                tokens_out += _int(data.get("tokens_out"))
                _cite(record)
            elif data.get("measured") is False:
                unmeasured_sessions += 1
                _cite(record)

        elif kind == "verdict":
            disposition = data.get("disposition")
            if disposition == "confirmed":
                verdict_confirmed += 1
                _cite(record)
            elif disposition == "refuted":
                verdict_refuted += 1
                _cite(record)
            elif disposition == "contested":
                verdict_contested += 1
                _cite(record)
            # witness-malformed: the claim was never judged, not this
            # report's concern - it counts what was measured or decided.

        elif kind == "action":
            roi_event = data.get("roi_event")
            if roi_event not in _ROI_EVENTS:
                continue
            if roi_event == GATE_DENIED:
                gate_denied += 1
            elif roi_event == GATE_ASKED:
                gate_asked += 1
            elif roi_event == GATE_ADVISORY:
                gate_advisories += 1
            elif roi_event == PRECEDENT_HIT:
                precedent_hits += 1
            elif roi_event == FENCE_FINDING:
                fence_findings += 1
            _cite(record)

    tokens: dict[str, Any] = {
        "measured_sessions": measured_sessions,
        "unmeasured_sessions": unmeasured_sessions,
    }
    if measured_sessions > 0:
        # Only ever added when at least one real measurement exists - see
        # the module docstring: a gap is stated, never interpolated as zero.
        tokens["in"] = tokens_in
        tokens["out"] = tokens_out

    return {
        "sessions": session_count,
        "tokens": tokens,
        "gate": {
            "denied": gate_denied,
            "asked": gate_asked,
            "advisories": gate_advisories,
        },
        "verdicts": {
            "confirmed": verdict_confirmed,
            "refuted": verdict_refuted,
            "contested": verdict_contested,
        },
        "precedent_hits": precedent_hits,
        "fence_findings": fence_findings,
        "basis": basis,
    }


def render_roi(report: dict[str, Any]) -> str:
    """Prose rendering: counts and record kinds only, never a claim of savings.

    Every section names the record kind(s) it folded, so the reader always
    knows what produced the number beside it - and never what a stored
    record's own free-text fields said, because this function never reads
    them.
    """
    lines: list[str] = [
        "GODMODE ROI REPORT - counts only; causal attribution is the operator's call",
        f"Sessions covered (from session records): {report['sessions']}",
        "",
    ]

    tokens = report["tokens"]
    lines.append(
        f"Tokens (from {tokens['measured_sessions']} measured + "
        f"{tokens['unmeasured_sessions']} unmeasured metric records):"
    )
    if "in" in tokens:
        lines.append(
            f"  in={tokens['in']} out={tokens['out']} "
            f"measured_sessions={tokens['measured_sessions']} "
            f"unmeasured_sessions={tokens['unmeasured_sessions']}"
        )
    else:
        lines.append(
            f"  no measured sessions; unmeasured_sessions={tokens['unmeasured_sessions']} "
            "(stated gap, not interpolated)"
        )
    lines.append("")

    gate = report["gate"]
    gate_total = gate["denied"] + gate["asked"] + gate["advisories"]
    lines.append(f"Gate activity (from {gate_total} gate-event records):")
    lines.append(
        f"  denied={gate['denied']} asked={gate['asked']} advisories={gate['advisories']}"
    )
    lines.append("  Gate activity beside burn; causal attribution is the operator's call.")
    lines.append("")

    verdicts = report["verdicts"]
    verdict_total = verdicts["confirmed"] + verdicts["refuted"] + verdicts["contested"]
    lines.append(f"Verdicts (from {verdict_total} verdict records):")
    lines.append(
        f"  confirmed={verdicts['confirmed']} refuted={verdicts['refuted']} "
        f"contested={verdicts['contested']}"
    )
    if verdicts["refuted"]:
        lines.append(
            f"  {verdicts['refuted']} refuted verdict(s) recorded as "
            "rework-candidate-caught - what happened, not a claim about what "
            "would have followed otherwise."
        )
    lines.append("")

    lines.append(
        f"Precedent hits (from {report['precedent_hits']} action records): "
        f"{report['precedent_hits']}"
    )
    lines.append(
        f"Fence findings (from {report['fence_findings']} action records): "
        f"{report['fence_findings']}"
    )
    lines.append("")
    lines.append("Basis: " + (", ".join(report["basis"]) if report["basis"] else "(none)"))

    return "\n".join(lines) + "\n"


def roi_digest(archive: Chronicle, sessions: int | None = None) -> dict[str, Any]:
    """U-E7: the would-have-caught view over gate_mode=observe records only.

    Folds ONLY `kind="refusal"` records carrying `observed: True` - the
    advisory record `hooks/godmode_session_hook.py`'s `_apply_observe_mode`
    writes for a call that would have been denied or asked about under
    enforcement, but ran anyway because the local policy's `gate_mode` was
    `"observe"`. Disjoint from `roi_report`'s `gate.denied`, which excludes
    these on purpose (see that function's own comment) - a would-have-caught
    count and a real enforcement count answer different questions and must
    never be added together.

    Same causal-denylist discipline as `roi_report`: `would_have_denied`/
    `would_have_asked` name what the CLASSIFIER decided, never what the
    operator would have done, never what damage (if any) would have
    followed. "would-have-denied" is an event label, not a savings or
    prevention claim - `render_digest` is checked against `CAUSAL_DENYLIST`
    exactly like `render_roi` is.
    """
    records = archive.read_events()

    floor_sequence = 0
    if sessions is not None and sessions > 0:
        session_sequences = [r["sequence"] for r in records if r["kind"] == "session"]
        if len(session_sequences) > sessions:
            floor_sequence = session_sequences[-sessions]

    would_have_denied = 0
    would_have_asked = 0
    by_category: dict[str, int] = {}
    tiers_by_category: dict[str, set[str]] = {}
    basis: list[str] = []

    def _cite(record: dict[str, Any]) -> None:
        if len(basis) < _BASIS_CAP:
            basis.append(f"seq:{record['sequence']}")

    for record in records:
        if record["sequence"] < floor_sequence:
            continue
        if record["kind"] != "refusal":
            continue
        data = record.get("data") or {}
        if data.get("observed") is not True:
            continue
        category = str(data.get("category") or "unclassified-mutation")[:80]
        by_category[category] = by_category.get(category, 0) + 1
        tiers_by_category.setdefault(category, set()).add(str(data.get("tier") or ""))
        if data.get("would_have") == "ask":
            would_have_asked += 1
        else:
            would_have_denied += 1
        _cite(record)

    return {
        "would_have_denied": would_have_denied,
        "would_have_asked": would_have_asked,
        "by_category": dict(sorted(by_category.items())),
        "basis": basis,
        "tune": _tune(by_category, tiers_by_category),
    }


def would_have_summary(archive: Chronicle) -> dict[str, Any]:
    """B4-10(b): the tier-shaped fold behind `assess`, `status` and the
    session brief - `{r2, r3, r4, r5, total, top}` over the observed-refusal
    records `roi_digest` already reads, where `top` is the most frequent
    category within the highest tier that has any events.

    Same discipline as every other fold here: counts and category names
    only, never a record's free-text fields. Zero is a real answer - the
    caller renders `total: 0` as an explicit statement, because absence of
    signal stated is the whole point of B4-10 (observe mode that is silent
    is a mute button, not a trial). Bounded by `select`'s own cap: the 500
    most recent refusal records, which is also what keeps a long trial from
    making every session brief pay for its whole history.
    """
    summary: dict[str, Any] = {tier: 0 for tier in _WOULD_HAVE_TIERS}
    summary["total"] = 0
    by_tier: dict[str, dict[str, int]] = {tier: {} for tier in _WOULD_HAVE_TIERS}
    for record in archive.select(kind="refusal", limit=500):
        data = record.get("data") or {}
        if data.get("observed") is not True:
            continue
        summary["total"] += 1
        tier = str(data.get("tier", "")).lower()
        if tier in by_tier:
            summary[tier] += 1
            category = str(data.get("category") or "unclassified-mutation")[:80]
            by_tier[tier][category] = by_tier[tier].get(category, 0) + 1
    summary["top"] = None
    for tier in reversed(_WOULD_HAVE_TIERS):
        if by_tier[tier]:
            summary["top"] = max(by_tier[tier].items(), key=lambda item: item[1])[0]
            break
    return summary


def enforce_digest(archive: Chronicle) -> dict[str, Any] | None:
    """S11-B: the posture loop's second half. Enforce-era gate-asked and
    silenced records exist so tuning could learn from what the operator
    actually approves - this reads them, and re-proposes ask_only over BOTH
    eras, diffed against the installed policy. Proposal-only, like the
    observe tune; counts and categories, never operations."""
    asked: dict[str, int] = {}
    asked_tiers: dict[str, set] = {}
    silenced: dict[str, int] = {}
    for record in archive.read_events():
        if record.get("kind") != "action":
            continue
        data = record.get("data") or {}
        if record.get("subject") == "gate-asked":
            category = str(data.get("category") or "unclassified")
            asked[category] = asked.get(category, 0) + 1
            asked_tiers.setdefault(category, set()).add(str(data.get("tier") or ""))
        elif data.get("silenced_by") == "ask_only":
            category = str(data.get("category") or "unclassified")
            silenced[category] = silenced.get(category, 0) + 1
    if not asked and not silenced:
        return None
    combined = dict(asked)
    tiers = {c: set(t) for c, t in asked_tiers.items()}
    proposal = _tune(combined, tiers)
    installed: list[str] = []
    try:
        from .godmode_sentinel import local_authorization_policy

        installed = sorted(local_authorization_policy(archive).get("ask_only") or [])
    except Exception:  # noqa: BLE001
        installed = []
    proposed = sorted((proposal or {}).get("ask_only") or [])
    return {
        "asked_by_category": dict(sorted(asked.items())),
        "silenced_by_category": dict(sorted(silenced.items())),
        "installed_ask_only": installed,
        "re_proposal": proposal,
        "drift": {
            "added": [c for c in proposed if c not in installed],
            "removable": [c for c in installed if c not in proposed],
        },
        "note": "proposal only; recomputed from enforce-era asks - adopt by "
                "editing .godmode-authorization-policy.json by hand",
    }


def render_digest(digest: dict[str, Any]) -> str:
    """Prose rendering: counts, categories, and `seq:` refs only - the same
    content-free discipline `render_roi` holds, never a record's free-text
    fields, never a causal-attribution word.
    """
    total = digest["would_have_denied"] + digest["would_have_asked"]
    lines: list[str] = [
        "GODMODE ROI DIGEST - observe-mode records only; counts + seq refs, "
        "causal attribution is the operator's call",
        f"Observed refusals (from {total} observed refusal records; "
        "gate_mode=observe let every one of these through):",
        f"  would-have-denied={digest['would_have_denied']} "
        f"would-have-asked={digest['would_have_asked']}",
        "",
    ]
    if digest["by_category"]:
        lines.append("By category (from the same observed refusal records):")
        for category, count in digest["by_category"].items():
            lines.append(f"  {category}: {count}")
    else:
        lines.append("By category: (none observed)")
    lines.append("")
    lines.append(
        "These are events the classifier flagged - what the operation was, "
        "not what would otherwise have happened to it or because of it."
    )
    lines.append("")
    tune = digest.get("tune")
    if tune:
        lines.append(
            f"Tune (proposal, not installed): ask_only={tune['ask_only']} keeps "
            f"{tune['asks_kept']} of these asks and silences {tune['asks_silenced']}; "
            "R4 still asks, R5 still denies. Adopt by writing "
            f"{json.dumps(tune['policy'])} into .godmode-authorization-policy.json.")
        lines.append("")
    enforce = digest.get("enforce")
    if enforce:
        lines.append(
            "Enforce era: asks by category "
            + json.dumps(enforce["asked_by_category"])
            + "; silenced " + json.dumps(enforce["silenced_by_category"]))
        drift = enforce["drift"]
        lines.append(
            f"Re-proposal drift vs installed ask_only: added={drift['added']} "
            f"removable={drift['removable']} (proposal only)")
        lines.append("")
    lines.append("Basis: " + (", ".join(digest["basis"]) if digest["basis"] else "(none)"))

    return "\n".join(lines) + "\n"
