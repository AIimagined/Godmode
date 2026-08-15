"""Disposition register with superseded states and rejection precedent (U-V2).

A closed-enumeration register over decisions where "was true, got superseded"
and "worse than baseline" are first-class facts, refusals become citable
precedent instead of tribal memory, and every entry points at the evidence
that put it there.

**Derived view, never stored.** The register is not a record kind of its
own - it is a pure fold over `decision` records whose subject is
`reg:<domain>:<key>`, the same regeneration rule E52 named: a view computed
fresh from the archive on every read can never drift from the ledger that
backs it, because there is no second copy to drift. `register_view()`
recomputes latest-state-per-key, with full lineage, every time it is called.

**Closed enumeration, not free text.** A state that is not one of `STATES`
is not a new disposition someone invented on the fly; it is a mistake. An
unlisted key - one nobody ever wrote a register record for - reads as the
explicit named default `open`, not as an error and not as `None`: "nothing
decided yet" is itself a fact this register can state.

**Evidence is not optional.** Every non-`open` entry must carry at least one
`witness:`/`verdict:`/`file:` evidence citation - E52's defect was a
register with no evidence discipline, so a state and the reason for it could
drift apart with nothing to notice. Refused at `set_state()`, and refused
again at the archive seam itself (`godmode_invariants._register_invariants`,
seeded eagerly into `Chronicle.append()`'s `KIND_INVARIANTS`) so a raw
`archive.append()` that bypasses this module is held to the same rule.

**Legal transitions only.** `open` is the only state anything may enter
freely - there is nothing yet to contradict. Every other state is a closed
disposition: leaving it requires a record that names `supersedes:<seq>`
citing the exact record it replaces, so the lineage is an explicit chain of
citations rather than "whichever record is newest wins by default." The one
path back into `established` from a closed disposition - including
`rejected-precedent` - is that same citing supersede; nothing else reopens
it. `set_state()` enforces this at write time for every caller that goes
through it. A raw `archive.append()` cannot be refused the same way, because
enforcing it needs the archive's history and the kind-invariant hook the
archive seam offers only ever sees one record's `data` in isolation - so an
illegal transition written that way lands on disk, and `conflict_findings()`
is the read-time detector that catches it: a planted conflicting record
becomes a blocking finding, not a silent state flip.

**Rejection precedent.** A `rejected-precedent` entry is a refusal a later
session can cite instead of re-litigating: `precheck()` (see
`godmode_precheck.py`) matches a task's normalized terms against every
`rejected-precedent` key across every domain and surfaces the precedent's
sequence with the instruction that closes the loop - cite it and supersede
it, or drop the work.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

# Closed enumeration. Anything not in this tuple is not a fourth kind of
# "sort of decided" - it is refused at set_state() and at the archive seam,
# never silently accepted and never silently coerced into a listed state.
STATES = (
    "established", "superseded", "refuted", "worse-than-baseline",
    "matched-baseline", "rejected-precedent", "open",
)

# Evidence prefixes that count as "this state points at something checkable."
# Mirrored (not imported) in godmode_invariants._register_invariants - see
# that module's docstring for why the duplication is deliberate.
EVIDENCE_PREFIXES = ("witness:", "verdict:", "file:")

# The legal target states reachable FROM each state. `open` is the implicit
# default for a key with no records at all, and it is also a state a caller
# may write explicitly (e.g. to attach a delta with no firm disposition
# yet) - either way, anything is reachable from it, because nothing has been
# decided yet to contradict. Every other state is a closed disposition:
# `established` is the live center, reachable only from `open` or (via a
# citing supersede) from any closed disposition; the four terminal outcomes
# (`superseded`, `refuted`, `worse-than-baseline`, `matched-baseline`) are
# reached only by first being `established` and then superseded out of it,
# or directly from `open` for a first-time evaluation against a baseline;
# `rejected-precedent` is reached only from `open` - a proposal rejected
# before it was ever established - and its only way out is back to
# `established`, and only by citing it.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset(STATES),
    "established": frozenset(
        {"superseded", "refuted", "worse-than-baseline", "matched-baseline"}
    ),
    "superseded": frozenset({"established"}),
    "refuted": frozenset({"established"}),
    "worse-than-baseline": frozenset({"established"}),
    "matched-baseline": frozenset({"established"}),
    "rejected-precedent": frozenset({"established"}),
}

DELTAS = ("added", "modified", "removed")

_SUBJECT_PREFIX = "reg:"

# U-E2 cross-project precedent exchange: a SEPARATE subject namespace for
# imported records, never `reg:<domain>:<key>` itself. Keeping it a distinct
# prefix is what makes "foreign never joins conflict detection against local
# records" true for free - `_domain_records()`/`conflict_findings()` only
# ever scan `reg:<domain>:` subjects, so a `reg-foreign:` record is invisible
# to both without either needing to know this module added a new kind of
# entry. Subject shape is `reg-foreign:<origin-fp16>:<key>` (no domain
# segment - two different domains from the same origin can share a literal
# subject string; that is harmless because grouping here, like the local
# fold, trusts `data["register_key"]`/`data["register_domain"]`, never the
# subject text, for exactly the reason `_key_of`'s docstring already gives).
FOREIGN_SUBJECT_PREFIX = "reg-foreign:"


def _subject(domain: str, key: str) -> str:
    return f"{_SUBJECT_PREFIX}{domain}:{key}"


def _foreign_subject(origin_fp16: str, key: str) -> str:
    return f"{FOREIGN_SUBJECT_PREFIX}{origin_fp16}:{key}"


def _domain_records(archive: Chronicle, domain: str) -> list[dict[str, Any]]:
    if not archive.initialized():
        return []
    prefix = f"{_SUBJECT_PREFIX}{domain}:"
    return [
        record for record in archive.read_events()
        if record.get("kind") == "decision" and record.get("subject", "").startswith(prefix)
    ]


def _key_of(record: dict[str, Any]) -> str | None:
    data = record.get("data") or {}
    key = data.get("register_key")
    return str(key) if key else None


def _unambiguous_subject_key(subject: str, domain: str) -> str | None:
    """The `<key>` segment of `reg:<domain>:<key>` - only when unambiguous.

    A key may itself contain ':' (confirmed by design: grouping is entirely
    `data["register_key"]`-driven, never a subject colon-split - see
    `_key_of`), which makes a subject carrying more than three ':'-separated
    segments ambiguous to parse a key back out of. Rather than guess, this
    returns `None` for anything but an exact, single-colon-free key segment,
    per review guidance: guard only the unambiguous case, skip the rest.
    """
    prefix = f"{_SUBJECT_PREFIX}{domain}:"
    if not subject.startswith(prefix):
        return None
    remainder = subject[len(prefix):]
    return None if ":" in remainder else remainder


def _grouped_by_key(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = _key_of(record)
        if key is None:
            continue
        by_key[key].append(record)
    for entries in by_key.values():
        entries.sort(key=lambda r: r["sequence"])
    return by_key


def register_view(archive: Chronicle, domain: str) -> dict[str, dict[str, Any]]:
    """Fold every `reg:<domain>:<key>` record into latest-state-per-key.

    Pure function of the archive's current content - never stored, never
    cached beyond one call. Only keys with at least one record appear here;
    an unlisted key's state is the named default `open`, read through
    `state_of()` rather than a missing dict entry, so "nothing decided" has
    an explicit name instead of being inferred from a `KeyError`.
    """
    view: dict[str, dict[str, Any]] = {}
    for key, entries in _grouped_by_key(_domain_records(archive, domain)).items():
        latest = entries[-1]
        data = latest.get("data") or {}
        view[key] = {
            "state": data.get("state", "open"),
            "sequence": latest["sequence"],
            "evidence": list(latest.get("evidence") or []),
            "lineage": [entry["sequence"] for entry in entries],
            "delta": data.get("delta"),
        }
    return view


def state_of(archive: Chronicle, domain: str, key: str) -> str:
    """The current state of one key - `open` by explicit default, not absence."""
    entry = register_view(archive, domain).get(key)
    return entry["state"] if entry is not None else "open"


def domains(archive: Chronicle) -> set[str]:
    """Every domain with at least one register record."""
    if not archive.initialized():
        return set()
    found: set[str] = set()
    for record in archive.read_events():
        if record.get("kind") != "decision":
            continue
        subject = record.get("subject", "")
        if not subject.startswith(_SUBJECT_PREFIX):
            continue
        # reg:<domain>:<key> - domain never contains ':', keys may (matches
        # rsplit-free parsing everywhere else in this module).
        parts = subject.split(":", 2)
        if len(parts) >= 2 and parts[1]:
            found.add(parts[1])
    return found


def set_state(
    archive: Chronicle,
    domain: str,
    key: str,
    state: str,
    evidence: list[str] | None,
    *,
    supersedes: int | None = None,
    delta: str | None = None,
) -> dict[str, Any]:
    """Record a disposition for `reg:<domain>:<key>`, refusing an illegal write.

    Refuses (ArchiveError) before ever touching the archive: an unlisted
    state, a non-open state with no witness:/verdict:/file: evidence, an
    illegal transition per `LEGAL_TRANSITIONS`, or a transition away from a
    non-open state whose `supersedes` does not name the exact record it
    replaces. The same evidence/state-membership rule is also enforced by
    `godmode_invariants._register_invariants` at the archive seam, so a raw
    `archive.append()` that skips this function cannot slip either check
    past silently - but the transition/supersedes rule needs this
    function's read of the archive's history to enforce at write time; a
    raw append that gets the state and evidence right but the lineage wrong
    lands on disk and is caught instead by `conflict_findings()`.
    """
    if state not in STATES:
        raise ArchiveError(f"Unknown register state '{state}'; expected one of {', '.join(STATES)}")
    if delta is not None and delta not in DELTAS:
        raise ArchiveError(f"Unknown delta '{delta}'; expected one of {', '.join(DELTAS)}")
    evidence = list(evidence or [])
    if state != "open" and not any(e.startswith(EVIDENCE_PREFIXES) for e in evidence):
        raise ArchiveError(
            f"Register state '{state}' needs witness:/verdict:/file: evidence; none given"
        )

    view = register_view(archive, domain)
    current = view.get(key)
    current_state = current["state"] if current is not None else "open"
    legal_targets = LEGAL_TRANSITIONS.get(current_state, frozenset())
    if state not in legal_targets:
        raise ArchiveError(
            f"Illegal register transition for '{domain}:{key}': "
            f"'{current_state}' -> '{state}' is not permitted "
            f"(legal targets from '{current_state}': {sorted(legal_targets) or 'none'})"
        )
    if current_state != "open":
        current_seq = current["sequence"]
        if supersedes != current_seq:
            raise ArchiveError(
                f"Leaving '{current_state}' for '{domain}:{key}' needs "
                f"supersedes={current_seq} (the record it replaces); got {supersedes!r}"
            )

    data = {
        "register_domain": domain,
        "register_key": key,
        "state": state,
        "supersedes": supersedes,
        "delta": delta,
        # Denormalised copy of `evidence`: the archive-seam invariant hook
        # (godmode_invariants._register_invariants) sees only `data`, never
        # the separate `evidence=` argument append() also stores, so the
        # evidence-sufficiency rule needs its own citations inside `data`
        # to be enforceable for a raw append that bypasses this function.
        "evidence": list(evidence),
    }
    return archive.append("decision", _subject(domain, key), data, evidence=evidence)


def conflict_findings(archive: Chronicle, domain: str) -> list[dict[str, Any]]:
    """Illegal lineages and mismatched records a raw append could write.

    `set_state()` enforces legal-transition-only and correct-supersedes-citation
    at write time, but only for callers that go through it; a hand-built
    `archive.append("decision", "reg:...", ...)` bypasses it entirely and
    the archive-seam invariant hook cannot catch a lineage error because it
    only ever sees one record's `data`, never the archive's history. This
    walks every key's full lineage in sequence order and reports exactly
    the same two violations `set_state()` would have refused - a HARD halt
    finding per E6: "conflict, ask before doing anything else," not a
    silent latest-wins.

    A third, cheaper check rides along for the same reason: `set_state()`
    always writes a subject whose own `<key>` segment agrees with
    `data["register_key"]`, but nothing stops a raw append from disagreeing -
    a record filed under `reg:<domain>:x` whose `data["register_key"]` is
    actually `y` groups under `y` (data is what grouping trusts, confirmed
    correct against a colliding-prefix probe), while the subject visually
    implies it revises `x`. That mismatch needs the record's real, stored
    `subject` alongside its `data` to detect at all - the archive-seam hook
    sees only `data`, never the subject a caller passed to `append()` - so,
    like the lineage checks above, this is read-time-only, not a write-time
    refusal.
    """
    findings: list[dict[str, Any]] = []
    records = _domain_records(archive, domain)
    for record in records:
        data = record.get("data") or {}
        register_key = data.get("register_key")
        if register_key is None:
            continue
        subject_key = _unambiguous_subject_key(record.get("subject", ""), domain)
        if subject_key is not None and subject_key != register_key:
            findings.append({
                "domain": domain, "key": register_key, "sequence": record["sequence"],
                "conflict": "subject-key-mismatch",
                "message": (
                    f"seq:{record['sequence']} subject names key '{subject_key}' but "
                    f"data.register_key is '{register_key}' - the subject is not a "
                    "reliable handle for this record"
                ),
            })
    for key, entries in _grouped_by_key(records).items():
        state = "open"
        seq: int | None = None
        for record in entries:
            data = record.get("data") or {}
            next_state = data.get("state")
            next_seq = record["sequence"]
            if next_state not in STATES:
                findings.append({
                    "domain": domain, "key": key, "sequence": next_seq,
                    "conflict": "unknown-state",
                    "message": f"seq:{next_seq} declares unlisted state '{next_state}'",
                })
                state, seq = "open", None
                continue
            legal_targets = LEGAL_TRANSITIONS.get(state, frozenset())
            illegal_transition = next_state not in legal_targets
            bad_supersedes = state != "open" and data.get("supersedes") != seq
            if illegal_transition or bad_supersedes:
                findings.append({
                    "domain": domain, "key": key, "sequence": next_seq,
                    "conflict": "illegal-transition" if illegal_transition else "bad-supersedes",
                    "message": (
                        f"seq:{next_seq} moves '{key}' from '{state}' to '{next_state}' "
                        f"without a legal, correctly-cited supersede "
                        f"(supersedes={data.get('supersedes')!r}, expected {seq!r}): "
                        "conflict - ask before doing anything else"
                    ),
                })
            state, seq = next_state, next_seq
    return findings


def rejected_precedents(archive: Chronicle) -> list[dict[str, Any]]:
    """Every key, across every domain, whose latest state is `rejected-precedent`.

    Read by `godmode_precheck.py` so a task about to redo refused work is
    told to cite the precedent's sequence and supersede it, or drop the
    work, instead of re-litigating a decision the archive already made.
    """
    hits: list[dict[str, Any]] = []
    for domain in sorted(domains(archive)):
        for key, entry in register_view(archive, domain).items():
            if entry["state"] == "rejected-precedent":
                hits.append({"domain": domain, "key": key, "sequence": entry["sequence"]})
    return hits


# --------------------------------------------------------------------------
# U-E2: cross-project precedent exchange (opt-in, file-carried).
#
# The transport is the file itself, carried by the operator - no network, no
# daemon, no shared mutable state. `export_precedents()` turns one project's
# register entries for one domain into a self-verifying JSON string;
# `import_precedents()` verifies that file's own whole-file hash and appends
# the entries into the SEPARATE `reg-foreign:` namespace above, where they
# stay strictly advisory: never scanned by `conflict_findings()`, never
# reachable through `register_view()`/`state_of()`, and never binding no
# matter what the imported file's bytes claim - `import_precedents()` sets
# `data["binding"] = False` unconditionally for every entry it writes,
# reading nothing from the entry to decide that. `adopt_precedent()` is the
# one explicit, human-triggered step that promotes a foreign entry into a
# real local `reg:<domain>:<key>` record, citing the foreign entry itself as
# the promotion's evidence.
# --------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    """Sorted-key, separator-tight JSON text - the same shape a hash needs to
    be stable across re-serialization (whitespace, key order) but not across
    an actual content change. Duplicated from `godmode_chronicle._canonical_json`
    rather than imported: that name is private to its module, and this
    module already duplicates `godmode_invariants`'s copies of `STATES`/
    `EVIDENCE_PREFIXES` for the same reason given there - avoiding a needless
    coupling between two modules that only agree on one small, stable shape.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _content_hash(doc_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(doc_without_hash).encode("utf-8")).hexdigest()


def _genesis_hash(archive: Chronicle) -> str:
    """The record_hash of this archive's very first record, ever.

    Stable for the archive's whole lifetime (record 1 never changes once
    written - the hash chain would break if it did), so it makes a fine
    origin fingerprint ingredient: unlike `anchor.project_key`, which is
    salted from *where* the project lives, this is salted from *what the
    archive actually recorded*, so two projects that happen to share a
    directory name still fingerprint differently once either has written
    anything at all.
    """
    if not archive.initialized():
        raise ArchiveError(
            "Cannot compute an origin fingerprint: this archive is not initialized"
        )
    events = archive.read_events()
    if not events:
        raise ArchiveError(
            "Cannot compute an origin fingerprint: this archive has no records yet"
        )
    return events[0]["record_hash"]


def origin_fingerprint(archive: Chronicle) -> str:
    """sha256(project-root basename + archive genesis hash)[:16] - U-E2's origin id.

    Two ingredients on purpose: the basename alone collides across projects
    with the same folder name (every fresh checkout named the same way), and
    the genesis hash alone is already unique but gives a reader no human
    anchor at all. Neither ingredient is personal or path-identifying by
    itself - the basename is a folder name the operator chose, the hash is
    opaque - and the fingerprint itself is one-way.
    """
    root_name = Path(archive.anchor.project_root).name
    return hashlib.sha256(
        f"{root_name}:{_genesis_hash(archive)}".encode("utf-8")
    ).hexdigest()[:16]


def export_precedents(archive: Chronicle, domain: str) -> str:
    """Write this project's `domain` register entries as one self-verifying file.

    Evidence citations are collapsed to plain `statements` - a receiving
    project cannot resolve a `witness:seq:5` citation that names a sequence
    in an archive it does not hold, so the export carries only the bounded
    strings, never a citation an importer would be unable to check. The
    whole-file `content_hash` covers every other field (`origin`, `domain`,
    `entries`) via canonical (sorted-key) JSON, computed over the document
    WITHOUT the hash field itself - the transport is the file byte-for-byte,
    so any tamper anywhere in it is refused at import, not silently carried.
    """
    view = register_view(archive, domain)
    entries = [
        {
            "key": key,
            "state": entry["state"],
            "statements": list(entry.get("evidence") or []),
            "evidence_count": len(entry.get("evidence") or []),
        }
        for key, entry in sorted(view.items())
    ]
    doc: dict[str, Any] = {
        "origin": origin_fingerprint(archive),
        # Additive to the core {origin, entries, content_hash} contract:
        # `import_precedents()` needs to know which domain these entries
        # belong to (the `reg-foreign:` subject itself carries no domain
        # segment - see `_foreign_subject`'s docstring), and there is no
        # other honest place to carry it than the export document.
        "domain": domain,
        "entries": entries,
    }
    doc["content_hash"] = _content_hash(doc)
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, indent=2)


def import_precedents(archive: Chronicle, blob: str) -> dict[str, Any]:
    """Verify `blob`'s content hash, then append every entry as a foreign, advisory record.

    Fully verified and structurally validated BEFORE any record is written -
    a hash mismatch or a malformed entry anywhere in the file refuses the
    whole import with nothing partially written, matching the archive's own
    all-or-nothing append discipline. `binding` is force-set to `False` on
    every written record regardless of what the entry claims: a hash can
    prove the file is unmodified since it was written, never that what was
    written is honest, so "binding" - if trusted from the file - would let a
    crafted export grant local authority from another project's say-so alone.
    """
    try:
        doc = json.loads(blob)
    except (TypeError, ValueError) as exc:
        raise ArchiveError(f"Malformed precedent export: not valid JSON ({exc})") from exc
    if not isinstance(doc, dict):
        raise ArchiveError("Malformed precedent export: the document is not a JSON object")

    origin = doc.get("origin")
    domain = doc.get("domain")
    entries = doc.get("entries")
    claimed_hash = doc.get("content_hash")
    if not isinstance(origin, str) or not origin:
        raise ArchiveError("Malformed precedent export: missing or empty 'origin'")
    if not isinstance(domain, str) or not domain:
        raise ArchiveError("Malformed precedent export: missing or empty 'domain'")
    if not isinstance(entries, list):
        raise ArchiveError("Malformed precedent export: 'entries' must be a list")
    if not isinstance(claimed_hash, str) or not claimed_hash:
        raise ArchiveError("Malformed precedent export: missing or empty 'content_hash'")

    unsigned = {key: value for key, value in doc.items() if key != "content_hash"}
    actual_hash = _content_hash(unsigned)
    if actual_hash != claimed_hash:
        raise ArchiveError(
            "Precedent export content hash mismatch - refused, nothing imported "
            f"(file claims {claimed_hash}, computed {actual_hash} over its own bytes)"
        )

    prepared: list[tuple[str, dict[str, Any], list[str]]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise ArchiveError("Malformed precedent export: an entry is not a JSON object")
        key = raw_entry.get("key")
        state = raw_entry.get("state")
        if not isinstance(key, str) or not key:
            raise ArchiveError("Malformed precedent export: an entry is missing 'key'")
        if state not in STATES:
            raise ArchiveError(
                f"Malformed precedent export: entry '{key}' declares unknown state {state!r}"
            )
        statements = [
            str(item) for item in (raw_entry.get("statements") or [])
            if isinstance(item, (str, int, float))
        ]
        evidence = [f"file:precedent-export:{origin}"]
        data = {
            "register_domain": domain,
            "register_key": key,
            "state": state,
            "supersedes": None,
            "delta": None,
            "evidence": list(evidence),
            "statements": statements,
            "foreign": True,
            "foreign_origin": origin,
            # Forced, never read from `raw_entry`: see the docstring above -
            # a foreign precedent can never arrive binding, no matter what
            # bytes a hand-crafted (but hash-valid) export claims.
            "binding": False,
        }
        prepared.append((key, data, evidence))

    imported: list[str] = []
    for key, data, evidence in prepared:
        archive.append(
            "decision", _foreign_subject(origin, key), data,
            evidence=evidence, dedupe=True,
        )
        imported.append(key)
    return {"origin": origin, "domain": domain, "imported": imported, "count": len(imported)}


def foreign_register_view(archive: Chronicle, domain: str) -> dict[str, dict[str, Any]]:
    """The `reg-foreign:*` counterpart to `register_view()` - always advisory.

    Folded the same way (latest record per key wins, full lineage kept), but
    over the separate foreign namespace, filtered to `domain` via
    `data["register_domain"]` since the foreign subject itself carries no
    domain segment. Every entry carries `foreign: True` and its `origin`
    fingerprint, so a reader (or `register()` below) can never mistake one
    for a local, binding disposition.
    """
    if not archive.initialized():
        return {}
    records = [
        record for record in archive.read_events()
        if record.get("kind") == "decision"
        and record.get("subject", "").startswith(FOREIGN_SUBJECT_PREFIX)
        and (record.get("data") or {}).get("register_domain") == domain
    ]
    view: dict[str, dict[str, Any]] = {}
    for key, group in _grouped_by_key(records).items():
        latest = group[-1]
        data = latest.get("data") or {}
        view[key] = {
            "state": data.get("state", "open"),
            "sequence": latest["sequence"],
            "evidence": list(latest.get("evidence") or []),
            "lineage": [entry["sequence"] for entry in group],
            "delta": data.get("delta"),
            "statements": list(data.get("statements") or []),
            "foreign": True,
            "origin": data.get("foreign_origin"),
            "binding": bool(data.get("binding", False)),
        }
    return view


def register(
    archive: Chronicle, domain: str, *, foreign: bool = False
) -> dict[str, dict[str, Any]]:
    """One reader for both namespaces: local by default, foreign on request.

    `register_view()` remains the direct, canonical entry point for local
    reads (every existing caller keeps using it unchanged); this is a thin
    dispatcher added for callers - the precedent-exchange tests among them -
    that want one name covering both without threading two functions
    through call sites that do not otherwise care which namespace they mean.
    """
    return foreign_register_view(archive, domain) if foreign else register_view(archive, domain)


def foreign_domains(archive: Chronicle) -> set[str]:
    """Every domain with at least one imported foreign entry."""
    if not archive.initialized():
        return set()
    found: set[str] = set()
    for record in archive.read_events():
        if record.get("kind") != "decision":
            continue
        if not record.get("subject", "").startswith(FOREIGN_SUBJECT_PREFIX):
            continue
        domain = (record.get("data") or {}).get("register_domain")
        if domain:
            found.add(str(domain))
    return found


def foreign_precedents(archive: Chronicle) -> list[dict[str, Any]]:
    """Every foreign entry, across every domain - read by `godmode_precheck.py`.

    Unlike `rejected_precedents()`, this is not filtered to one state: a
    foreign precedent is advisory information regardless of the disposition
    it carries, and it is precheck's job (not this fold's) to decide which
    ones are relevant to a given task's terms.
    """
    hits: list[dict[str, Any]] = []
    for domain in sorted(foreign_domains(archive)):
        for key, entry in foreign_register_view(archive, domain).items():
            hits.append({
                "domain": domain, "key": key, "state": entry["state"],
                "sequence": entry["sequence"], "origin": entry["origin"],
            })
    return hits


def adopt_precedent(
    archive: Chronicle, domain: str, key: str, *, evidence: list[str] | None = None
) -> dict[str, Any]:
    """Promote one foreign, advisory entry to a real local, binding one.

    The one explicit operator step the trust model allows: this calls
    `set_state()` exactly as a human typing `register set` would, so every
    rule that already governs a local write - legal transitions, evidence
    sufficiency, the archive-seam invariant - applies here identically. The
    foreign entry's own reference is always cited as evidence (in addition
    to whatever the caller supplies), so the promoted record's lineage shows
    plainly that it originated in another project's archive.
    """
    entry = foreign_register_view(archive, domain).get(key)
    if entry is None:
        raise ArchiveError(
            f"No foreign precedent recorded for '{domain}:{key}' - import it first"
        )
    origin = entry.get("origin") or "unknown-origin"
    lineage = [f"file:precedent-export:{origin}"]
    return set_state(
        archive, domain, key, entry["state"],
        list(evidence or []) + lineage,
        supersedes=None, delta=entry.get("delta"),
    )
