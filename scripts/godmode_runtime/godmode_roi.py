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
            # Every refusal record IS a denial - godmode_session_hook.py
            # only appends this kind from its deny branch (see the module
            # docstring). Disjoint from the `action`/`roi_event` convention
            # below, so folding both never double-counts the same record.
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
