"""Forgetting engine (NS-11e + NS-11g, 0.3.28 Plan 5 Task 7): the fifth
memory layer the archive lacked. `expunge` stays the retraction for a
secret that slipped past the scanner; this is routine memory hygiene -
three operations, run together every time `godmode forget` is invoked:

- **expire**: episodic kinds (`action`, `refusal`, `attestation`) past
  their kind's TTL are moved out of the hot tier into a rotated, still
  hash-chained cold segment (`Chronicle.rotate_to_cold`). Pins are never
  episodic kinds to begin with, and the chronicle refuses to rotate one
  anyway - see `Chronicle.rotate_to_cold`'s own docstring.
- **supersede**: writes nothing. A read-only report of every supersession
  chain currently on record, through the same `superseded_sequences`
  helper (NS-10e, Task 6) every latest-per-subject reader routes through -
  never a second, independently-derived notion of "superseded".
- **flag contradictions**: among ACTIVE records (excluded exactly the way
  `latest_by_subject` excludes a superseded one), two or more sharing a
  (kind, subject) whose `data["value"]` disagree get one `review` record
  naming both sequences - never a verdict about which one is right.

Nothing here is a security boundary the way `expunge`'s tombstone or the
write-trust guards are; it is retention policy, expressed as a pure
function of `now` (fabricated by every caller, never read from the wall
clock inside this module) over records the caller already holds a verified
read of.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .godmode_chronicle import Chronicle, superseded_sequences
from .godmode_constants import FORGET_PASS_SUBJECT
from .godmode_errors import ArchiveError
from .godmode_invariants import REVIEW_STATUSES
from .godmode_law import LESSON_DORMANT_STATUSES

# Per-kind retention, in days, for the episodic kinds `expire` considers.
# `attestation` outlives `action`/`refusal` because a witnessed step is
# read back far more often (session close, law compilation) than a single
# tool action or a single refusal ever is. Not a security boundary -
# retention policy only, the one thing this module owns.
TTL_DAYS: dict[str, int] = {
    "action": 30,
    "refusal": 30,
    "attestation": 90,
    # NS-13f: a hypothesis belongs to one investigation. A killed or
    # abandoned one expires like the attestations of the runs that tested
    # it; one a live fix claim cites (`hyp:<seq>`) stays hot with its kill
    # result - see `protected_sequences`.
    "hypothesis": 90,
}

EPISODIC_KINDS = frozenset(TTL_DAYS)

# Kinds `flag_contradictions` compares for a same-subject value conflict -
# the two kinds that actually carry `data["value"]` as their own recorded
# fact (NS-11c's decision invariant; a lesson's own generalisation, the
# same pairing `godmode_hygiene.hygiene` already reads for its own,
# fuzzier near-duplicate/contradiction pass). `pattern` and `metric` are
# deliberately excluded - neither carries a `value` to disagree over.
CONTRADICTION_KINDS = ("decision", "lesson")

# A record's `status` values `flag_contradictions` (and `latest_by_subject`
# callers generally) treat as no longer standing - the same closed set
# `godmode_hygiene._INACTIVE` uses, kept here as an independent literal on
# purpose (this module stays free of that one's fuzzy-matching machinery).
_INACTIVE_STATUSES = frozenset({"closed", "retired", "superseded", "withdrawn", "done", "waived"})

# Sidecars this module's `--dry-run` digest deliberately excludes: every
# one of them is documented elsewhere in this codebase as a disposable
# accelerator or hint (the head cache, the chain anchor, the checkpoint
# registry, the read index, the lock sidecars) - a plain READ can
# legitimately refresh any of them with no state actually having changed,
# so including them would make the digest assertion flicker on a read that
# wrote nothing meaningful. What the digest DOES cover - the hot record
# files, any cold segment, and the cold registry - is exactly what
# `--dry-run` promises never to touch.
#
# Fix round 1 (review A, B8): all six live in the archive ROOT, and
# `_digest_paths` below now globs the record directory and the two cold
# files by name rather than walking the root, so none of them can be
# reached in the first place. The set stays as the named guard for a
# disposable sidecar that ever lands INSIDE the record directory - which is
# the only way one could re-enter the digest - rather than as a filter the
# current paths depend on.
_DIGEST_EXCLUDED_NAMES = frozenset({
    "godmode-head.json",
    "godmode-chain-anchor.json",
    "godmode-checkpoint-registry.json",
    "godmode-events.index.json",
    "godmode-write.lock",
    "godmode-write.excl.lock",
})


def _parse_now(now: str | None) -> datetime:
    """`--now` is the only clock this module ever reads - no caller here
    ever calls `datetime.now()` itself. `None` (the CLI's default) falls
    back to the real time, exactly once, at this one boundary.

    Fix round 1 (review B, B1): unparseable input raises `ArchiveError`,
    which `main()` renders as the verb's own JSON refusal. A bare
    `ValueError` escaped that handler entirely and `godmode forget --now
    not-a-date` exited on a Python traceback.
    """
    if now is None:
        return datetime.now(timezone.utc)
    try:
        value = datetime.fromisoformat(now)
    except (TypeError, ValueError):
        raise ArchiveError(
            f"--now takes an ISO-8601 timestamp, not {now!r} - for example "
            "2026-09-17T12:00:00+00:00 (a bare date, 2026-09-17, is also "
            "accepted and reads as midnight UTC)"
        ) from None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _recorded_at(record: dict[str, Any]) -> datetime | None:
    raw = record.get("recorded_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def age_days(record: dict[str, Any], *, now: datetime) -> float | None:
    """A record's age in days as of `now`; `None` when it carries no
    parseable `recorded_at` (never treated as either eligible or exempt by
    that absence - see `eligible_for_expiry`)."""
    recorded = _recorded_at(record)
    if recorded is None:
        return None
    return (now - recorded).total_seconds() / 86400.0


# `hyp:N` (NS-13f) names a hypothesis a fix rests on, by sequence, the same
# way the other three forms name their records.
_SEQ_CITE = re.compile(r"^(?:seq|verdict|diff|hyp):(\d+)$")

# The same three citation forms found anywhere INSIDE a string rather than
# as the whole of one (fix round 2, R2-B6): a `seq:` cite written into a
# record's own `value`, `summary` or `reason` is a live reference to that
# record exactly as an `evidence` entry is, and `require_seq_cite` will
# refuse a later write against it either way. Bounded by a word boundary so
# a longer token ("noseq:4", "seq:40" for 4) never matches by accident.
_EMBEDDED_CITE = re.compile(r"\b(?:seq|verdict|diff|hyp):(\d+)\b")

# Outcomes that SETTLE the claim they resolve. Anything else - an
# unresolved claim, or one resolved `held` - is still live, and what it
# cited stays reachable (review A, B6). `godmode_attest.RESOLUTION_OUTCOMES`
# is the full vocabulary; these are the two that end a claim's standing.
_SETTLING_OUTCOMES = frozenset({"failed", "superseded"})


def _collect_citations(record: dict[str, Any], into: set[int]) -> None:
    """Add every record sequence this record points at to `into`.

    Three citation forms, not one (fix round 2, R2-B6): `seq:N`, `verdict:N`
    (`godmode_attest._VERDICT_CITE`) and `diff:N` (`_DIFF_CITE`) all name a
    record by sequence and all resolve through the same hot-only
    `seq_cite_resolves`, so rotating what any of them names dangles the
    citation identically.

    Two places, not two lists: the `evidence` list and `data["evidence"]`
    (where a citation is written deliberately), AND the record's own
    free-text string values, where a `seq:N` written into a `value`,
    `summary` or `reason` is just as load-bearing and was previously
    invisible here. One pass over the record's own top-level values; no
    archive read, nothing recursive.

    Writes into the caller's set rather than returning a fresh one: this
    runs once per record in `protected_sequences`' own fold, and at 20,000
    records the per-call set allocation and union were a measurable share
    of the whole pass.
    """
    cited = into
    data = record.get("data")
    is_mapping = isinstance(data, dict)
    for source in (record.get("evidence"),
                   data.get("evidence") if is_mapping else None):
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, str):
                continue
            match = _SEQ_CITE.match(item.strip())
            if match is not None:
                cited.add(int(match.group(1)))
    if is_mapping:
        for key, value in data.items():
            # The cost gate: three C-level substring searches, tried in
            # descending order of how often each form appears, before any
            # regex touches the string. Spelled out rather than folded into
            # an `any(...)` over a tuple - the generator alone cost more
            # than the searches it was guarding, at one call per record.
            if (not isinstance(value, str)
                    or ("seq:" not in value
                        and "verdict:" not in value
                        and "diff:" not in value
                        and "hyp:" not in value)
                    or key == "evidence"):
                continue
            for match in _EMBEDDED_CITE.finditer(value):
                cited.add(int(match.group(1)))


def protected_sequences(records: list[dict[str, Any]]) -> set[int]:
    """Sequences that stay hot however old they are (NS-11e fix round 1,
    review A B6): every sequence cited by a record that is still load-bearing.

    Four sources, built once per pass from the records already in hand:

    - a **live claim** - one no later claim has resolved `failed` or
      `superseded`; an unresolved claim and one that HELD are both still
      standing, and `seq_cite_resolves`/`reconstruct` read the hot tier, so
      rotating what they cite dangles the citation;
    - a **checkpoint** - the record a compaction handed the next session;
    - a **law guard** - a lesson carrying an `enforce` predicate that is not
      dormant, whose cited evidence is the ground the guard rests on;
    - a **pin**, and every sequence a pin cites.

    Before this, the shipped "pins are exempt" protection could not protect
    anything: `pin` is not an episodic kind, so the kind filter excluded it
    already and `rotate_to_cold`'s refusal never fired from this path.

    Fix round 2 (R2-B6): the four sources above are now the four with EXTRA
    rules, not the only kinds scanned. The allow-list has become a
    deny-list - every record's citations count unless the citing record is
    itself episodic (one past its own TTL protects nothing; it is the thing
    being forgotten) - because a `seq:` cite from a `decision`, `verdict`,
    `attestation`, `obligation`, `incident` or `improvement_proposal` was
    rotated out from under exactly as easily, and `require_seq_cite` refuses
    a later write against a dangling one all the same. The three citation
    forms and the free-text sweep live in `_collect_citations`.

    Deliberately a SUPERSET where the question is close: a claim with no
    recorded resolution counts as live, because a dangling `seq:` cite is a
    worse outcome than a record that stays hot longer than its TTL.

    Linear in the number of records, and a pure fold over the list already
    in hand: no archive read, nothing quadratic, one pass to find settled
    claims and one to collect.
    """
    settled: set[int] = set()
    for record in records:
        if record.get("kind") != "claim":
            continue
        data = record.get("data") or {}
        resolves = data.get("resolves")
        if (isinstance(resolves, int) and not isinstance(resolves, bool)
                and str(data.get("outcome", "")).strip().lower() in _SETTLING_OUTCOMES):
            settled.add(int(resolves))
    protected: set[int] = set()
    for record in records:
        kind = record.get("kind")
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        sequence = int(record.get("sequence", 0) or 0)
        if kind in EPISODIC_KINDS:
            # The kinds this pass is here to forget. A cite written by one
            # of them keeps nothing alive - otherwise two old `action`
            # records citing each other would pin each other hot forever.
            continue
        if kind == "claim" and sequence in settled:
            continue
        if kind == "lesson":
            # A lesson protects what it cites only while it is LAW: an
            # enforce predicate that is not dormant. A plain lesson's cite
            # is covered by the deny-list below like any other kind's.
            enforce = isinstance(data.get("enforce"), dict)
            dormant = str(data.get("status", "active")).strip().lower() in LESSON_DORMANT_STATUSES
            if enforce and dormant:
                continue
        if kind == "pin":
            # A pin's own sequence too, not only what it cites - the record
            # that names an enforced file must stay where `pinned_evaluators()`
            # reads it.
            protected.add(sequence)
        _collect_citations(record, protected)
    # NS-13f: a protected hypothesis keeps its kill results hot too - its
    # status is the newest record whose `of` names it, and rotating that
    # away would silently reopen a hypothesis a fix already rests on.
    # The runner attestation a kill result names (`kills.check_seq`) is what
    # a `hyp:` citation resolves through, so it stays hot with them.
    for record in records:
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        if record.get("kind") == "hypothesis" and data.get("of") in protected:
            protected.add(int(record.get("sequence", 0) or 0))
            kills = data.get("kills") if isinstance(data.get("kills"), dict) else {}
            check_seq = kills.get("check_seq")
            if isinstance(check_seq, int) and not isinstance(check_seq, bool):
                protected.add(check_seq)
    return protected


def eligible_for_expiry(records: list[dict[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
    """Episodic records past their kind's TTL, minus everything
    `protected_sequences` says is still load-bearing. A record with no
    `recorded_at` (older than this field, or hand-edited) is never
    eligible - an unmeasurable age is not evidence of staleness."""
    protected = protected_sequences(records)
    # NS-11g fix round 1 (review A, N4): the newest record is never eligible.
    # `Chronicle._chain_tail` reads the tail off the last HOT record, so a
    # rotation that moved the true tail away would hand the next append a
    # sequence number already sealed. `rotate_to_cold` refuses it outright as
    # defense in depth; this is what keeps an ordinary pass from ever asking.
    tail = max((int(record.get("sequence", 0) or 0) for record in records), default=0)
    eligible = []
    for record in records:
        kind = record.get("kind")
        if kind not in EPISODIC_KINDS:
            continue
        sequence = int(record.get("sequence", 0) or 0)
        if sequence in protected or sequence == tail:
            continue
        age = age_days(record, now=now)
        if age is None or age < TTL_DAYS[kind]:
            continue
        eligible.append(record)
    return eligible


def _digest_paths(root: Path) -> list[Path]:
    """Exactly the files a forgetting pass can change: the record files, the
    cold segments, and the cold registry.

    Fix round 1 (review A, B8): three targeted globs, never `root.rglob("*")`
    over the whole archive. Measured on this project's live archive, the
    whole-root walk stat'd 19,363 paths and cost 10-17 s - a per-call price
    on a read-only report. Everything the old walk covered that these globs
    do not is a disposable cache `_DIGEST_EXCLUDED_NAMES` named anyway, or a
    sidecar no operation in this module writes.
    """
    if not root.is_dir():
        return []
    paths = []
    for candidate in list((root / "godmode-events").rglob("*")) + \
            list(root.glob("events-cold-*.jsonl")) + \
            list(root.glob("godmode-cold-registry.json")):
        if not candidate.is_file():
            continue
        if candidate.name in _DIGEST_EXCLUDED_NAMES:
            continue
        paths.append(candidate)
    return sorted(paths)


def archive_digest(root: Path) -> str:
    """A digest over exactly what a forgetting pass may change: hot record
    files, cold segments, and the cold registry - never the disposable
    caches `_DIGEST_EXCLUDED_NAMES` names. `--dry-run`'s own proof: called
    once before and once after, and asserted equal (see `forget()`'s
    `digest_unchanged` field and `tests/test_forget.py`). Content is not
    hashed, only (relative path, size, mtime) - a rotation always changes
    at least one file's name or size, and this stays a directory-stat
    operation, never a re-read of every record's bytes.
    """
    parts = [
        f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}"
        for path in _digest_paths(root)
        for stat in (path.stat(),)
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _expire(archive: Chronicle, records: list[dict[str, Any]], *,
            now: datetime, dry_run: bool) -> dict[str, Any]:
    eligible = eligible_for_expiry(records, now=now)
    sequences = sorted(int(record["sequence"]) for record in eligible)
    report: dict[str, Any] = {
        "operation": "expire",
        "eligible": sequences,
        "count": len(sequences),
        "rotated": False,
    }
    if dry_run or not sequences:
        return report
    outcome = archive.rotate_to_cold(sequences)
    report["rotated"] = True
    report["segment"] = outcome["segment"]
    if outcome.get("resumed"):
        # A previous pass crashed between registering the segment and
        # unlinking the hot files; this one finished it (review A, B3).
        report["resumed"] = outcome["resumed"]
    return report


def _supersede_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Writes nothing - a pure function of the records handed in (fix round
    1, review A N6: this used to take its own `read_events()` pass, a third
    walk of the same archive `forget()` had already read and verified).
    Every chain currently on record, through `superseded_sequences` alone -
    the ONE place that rule lives (NS-10e)."""
    superseded = superseded_sequences(records)
    chains = []
    for record in records:
        target = (record.get("data") or {}).get("supersedes")
        if target is None:
            continue
        try:
            target_sequence = int(target)
        except (TypeError, ValueError):
            continue
        if target_sequence not in superseded:
            continue
        chains.append({
            "from": target_sequence,
            "to": int(record.get("sequence", 0) or 0),
            "subject": str(record.get("subject", "")),
        })
    chains.sort(key=lambda chain: chain["to"])
    return {"operation": "supersede", "chains": chains, "count": len(chains)}


def _canonical_value(record: dict[str, Any]) -> str:
    return json.dumps((record.get("data") or {}).get("value"), sort_keys=True, default=str)


def _reviews_on_record(records: list[dict[str, Any]]) -> dict[tuple[str, tuple[int, ...]], str]:
    """Every `review` already on record, keyed by (subject, its exact
    sequence set) -> status (fix round 1, review B B4).

    ANY review for that subject and that sequence set counts, not just the
    newest one: `append(..., dedupe=True)` compares only the most recent
    same-kind/same-subject record, so an operator who acknowledged a finding
    made the newest review differ from what the next pass computes - and the
    next pass filed a fresh open review over a contradiction that had been
    deliberately accepted, forever.
    """
    seen: dict[tuple[str, tuple[int, ...]], str] = {}
    for record in records:
        if record.get("kind") != "review":
            continue
        data = record.get("data") or {}
        sequences = data.get("sequences")
        if not isinstance(sequences, list):
            continue
        key = (
            str(record.get("subject", "")),
            tuple(sorted(int(s) for s in sequences
                         if isinstance(s, int) and not isinstance(s, bool))),
        )
        status = str(data.get("status", "open")).strip().lower()
        if status not in REVIEW_STATUSES:
            status = "open"
        # Later records win: the operator's acknowledgement is the current
        # state of a finding an earlier pass opened.
        seen[key] = status
    return seen


def _flag_contradictions(archive: Chronicle, records: list[dict[str, Any]], *,
                         dry_run: bool) -> dict[str, Any]:
    """Same subject, conflicting `data["value"]`, both active -> one
    `review` record naming every conflicting sequence. "Active" uses
    `latest_by_subject`'s own exclusion rule (`superseded_sequences`) so a
    record another one has already superseded never counts as still
    standing - but unlike `latest_by_subject`, this does not fold survivors
    down to one winner per subject; it groups them and flags a group only
    when its members do not all agree.

    Idempotent, and durable across an operator's decision (fix round 1,
    review B B4): a subject whose exact sequence set already has a review on
    record - open, acknowledged or dismissed, and at ANY point in the
    archive rather than only as the newest one - is reported with that
    review's status and written again never. `append(..., dedupe=True)`
    stays as the second belt.
    """
    excluded = superseded_sequences(records)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        kind = record.get("kind")
        if kind not in CONTRADICTION_KINDS:
            continue
        if int(record.get("sequence", 0) or 0) in excluded:
            continue
        status = str((record.get("data") or {}).get("status", "active")).strip().lower()
        if status in _INACTIVE_STATUSES:
            continue
        groups.setdefault((kind, str(record.get("subject", ""))), []).append(record)
    on_record = _reviews_on_record(records)
    flagged = []
    written = []
    for (kind, subject), group in sorted(groups.items()):
        if len(group) < 2:
            continue
        if len({_canonical_value(record) for record in group}) < 2:
            continue
        sequences = sorted(int(record.get("sequence", 0) or 0) for record in group)
        status = on_record.get((subject, tuple(sequences)))
        flagged.append({"kind": kind, "subject": subject, "sequences": sequences,
                        "status": status or "new"})
        if dry_run or status is not None:
            continue
        written_record = archive.append(
            "review", subject,
            {
                "kind": kind,
                "sequences": sequences,
                "status": "open",
                "reason": "same subject, conflicting value, both active",
            },
            evidence=[f"seq:{sequence}" for sequence in sequences],
            dedupe=True,
        )
        written.append(int(written_record["sequence"]))
    return {
        "operation": "contradictions",
        "flagged": flagged,
        "count": len(flagged),
        "open": sum(1 for item in flagged if item["status"] in ("new", "open")),
        "written": written,
    }


def _findings(expire: dict[str, Any], contradictions: dict[str, Any], *,
              dry_run: bool) -> tuple[list[dict[str, Any]], str]:
    """The pass's findings and its next action, in the shapes `--brief` and
    `--terse` already read (`_FINDING_LISTS`, `_ACTIONS`, `_COUNTS` in
    `godmode_console`) - fix round 1, review B B2. Before this, every count
    sat one level down inside `expire`/`contradictions`, so `--terse` read a
    payload carrying real findings and printed "next: nothing - no findings
    reported".

    Supersession chains are reported, never counted here: they are a
    standing fact about the archive, not something this pass leaves for
    anyone to act on, and counting them would make every run report
    findings forever.
    """
    findings: list[dict[str, Any]] = []
    if expire["count"]:
        findings.append({
            "code": "expire-due" if dry_run else "expired",
            "detail": (
                f"{expire['count']} episodic record(s) past their kind's TTL"
                + (" - a real pass rotates them into a cold segment"
                   if dry_run else f", rotated into {expire.get('segment')}")
            ),
        })
    if contradictions["count"]:
        findings.append({
            "code": "contradiction",
            "detail": (
                f"{contradictions['count']} subject(s) hold conflicting active values"
                + (f"; {contradictions['open']} still open" if not dry_run else "")
            ),
        })
    if not findings:
        return findings, ("nothing is due - no episodic record is past its TTL "
                          "and no active subject disagrees with itself")
    if dry_run:
        return findings, (f"run `godmode forget` to act on {len(findings)} finding(s) - "
                          "this pass wrote nothing")
    if contradictions["written"]:
        return findings, (
            "read the new review record(s) with `godmode history --kind review`, then "
            "close each one: `godmode remember --kind review --subject \"<subject>\" "
            "--status acknowledged` (or `dismissed`)"
        )
    return findings, ("the pass acted on every finding; `godmode doctor` re-walks the "
                      "cold tier if you want the thorough check")


def _record_pass(archive: Chronicle, expire: dict[str, Any],
                 contradictions: dict[str, Any], *, when: datetime) -> int:
    """Record that a pass ran, as a record (fix round 1, review B cadence /
    N9). Before this a pass left no trace of itself unless it happened to
    rotate something, so nothing could say when one last ran - `recurring`
    had to re-derive it with a full dry run on every call, and NS-11f's
    "scheduled (forget pass ran)" test had no evidence to assert on.

    Counts and outcomes only, never a narration - the same shape every other
    bookkeeping `action` in this archive carries.

    Worth naming once (fix round 2, N7): this record is itself an `action`,
    one of the three episodic kinds, so the record proving a pass ran is
    eligible for expiry by a later pass. That is harmless in the steady
    state - every real pass writes a fresh one, and the newest record is
    never eligible anyway - but anything that comes to depend on a LONG
    history of passes (a cadence report, Task 8's scheduling evidence) must
    read the latest one, not expect a series.
    """
    record = archive.append(
        "action", FORGET_PASS_SUBJECT,
        {
            "summary": "forget pass",
            "ran_at": when.isoformat(),
            "expired": expire["count"],
            "segment": expire.get("segment"),
            "contradictions": contradictions["count"],
            "reviews_written": len(contradictions["written"]),
        },
        evidence=[],
    )
    return int(record["sequence"])


def forget(archive: Chronicle, *, now: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """`godmode forget`'s three operations, run together every call:
    expire, supersede (report only), flag contradictions. NS-11e + NS-11g
    (0.3.28 Plan 5 Task 7). `--dry-run` runs every read exactly as a real
    pass would (so the report is the same report a real run would have
    given) but performs neither write - proved, not merely claimed, by
    `archive_digest` over the record files, the cold segments and the cold
    registry before and after, and REFUSED if that digest ever moves.

    A real pass records itself (`_record_pass`); a dry run does not, which
    is what keeps the digest assertion above honest.
    """
    if not archive.initialized():
        raise ArchiveError("Godmode is not initialized; run `init` first")
    when = _parse_now(now)
    digest_before = archive_digest(archive.root) if dry_run else None
    # Fix round 1 (review A, N6): ONE verified read for the whole pass,
    # handed down to all three operations. Expire is the only one that can
    # change what the others would see, and it can only ever REMOVE episodic
    # records from the hot tier - never a `decision`, `lesson`, `claim` or
    # `review`, the kinds the other two reason about.
    records = archive.read_events(verify=True)
    expire = _expire(archive, records, now=when, dry_run=dry_run)
    supersede = _supersede_report(records)
    contradictions = _flag_contradictions(archive, records, dry_run=dry_run)
    findings, next_action = _findings(expire, contradictions, dry_run=dry_run)
    report: dict[str, Any] = {
        "now": when.isoformat(),
        "dry_run": dry_run,
        "expire": expire,
        "supersede": supersede,
        "contradictions": contradictions,
        "count": len(findings),
        "findings": findings,
        "next_action": next_action,
    }
    if dry_run:
        report["digest_unchanged"] = digest_before == archive_digest(archive.root)
        if not report["digest_unchanged"]:
            # Fix round 1 (review B, N2): advisory was the wrong register. A
            # dry run that changed the archive is either a concurrent writer
            # or a bug in this module, and either way the operator must hear
            # it as a refusal, not as a boolean nobody branches on.
            raise ArchiveError(
                "`forget --dry-run` changed the archive: the digest over the record "
                "files, the cold segments and the cold registry moved between the "
                "start and the end of this pass. Nothing on the dry-run path writes, "
                "so this is a concurrent writer or a defect - run `godmode doctor` "
                "before trusting either state."
            )
        return report
    report["pass_recorded"] = _record_pass(archive, expire, contradictions, when=when)
    return report
