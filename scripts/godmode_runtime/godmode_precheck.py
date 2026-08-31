"""Was this already built, and was it already refused.

Two questions, asked at the only moment the answers are worth having: before
the work starts. Both were answered wrong in the session that produced this
module. A sentinel allowlist came one command from being rebuilt after two
shipped releases had already fixed it. A reinvention check designed in an
earlier session was rediscovered from scratch, because nothing read the record
saying it had been designed.

Neither answer was missing. `removal` records why something was deleted,
decisions record what was rejected and why, and the atlas records what exists.
The archive was already holding both, and nothing consulted either.

**It reports where it looked.** An absence claim needs the search that would
have disproved it - the rule this project applies to every other claim. A
`nothing found` produced by a check that examined nothing is worse than no
check, because it reads as clearance.

**Findings, never closures.** Prior work is a reason to look, not a refusal.
Sometimes the earlier rejection was right and the request should stop; sometimes
the constraint that drove it has gone. Only a person can tell those apart, and
an agent that could clear its own precheck would clear it the way it currently
skips it.

**Precedent is a fourth, sharper question.** `already_rejected` above matches
by fuzzy term overlap over free-text `decision`/`lesson`/`request` records - a
weak test by design, because a strong one that reports nothing is the check
that cannot fail. U-V2's disposition register (`godmode_register.py`) is the
precise counterpart: a closed-enumeration `rejected-precedent` entry is a
refusal the archive itself adjudicated, not prose that happens to contain a
refusal word. A task whose normalized terms name a `rejected-precedent` key
is told the sequence and the way through - cite it and supersede it, or drop
the work - rather than being left to rediscover the same refusal by hand.

**Foreign precedent is a fifth question, strictly advisory.** U-E2's
cross-project exchange (`godmode_register.py`'s `reg-foreign:` namespace)
lets a precedent imported from another project's archive travel here as a
FILE, never a network call. It is surfaced the same way `rejected_precedents`
is - matched by the key's own terms, never by fuzzy free-text overlap - but
it never joins `already_rejected`, never contributes to `findings`/`verdict`,
and is labeled distinctly (`foreign precedent (from <fp8>)`) so a reader can
never mistake it for something this project's own archive adjudicated.

**Paired-artifact is a sixth question, GAP-2's other half, also advisory.**
`godmode_minimality.duplicate_authority_findings` catches an *undeclared*
pair drifting apart by *auto-detected* member overlap; this is the
declared, explicit counterpart - a project states "these two artifacts
change together" once, and every later diff is checked against that
statement rather than against a similarity score. Declaring is writing a
`decision` record whose subject is `paired-artifact:<label>` - the same
"reuse an existing kind, namespace the subject" house pattern `removal`
above and `reg:`/`reg-foreign:` in `godmode_register.py` already use. A
paired-artifact charter is project *policy* that a session writes,
revises, and can retire - the same evolving, evidenced, append-only shape
`reg:` decisions already have, not a generated inventory snapshot
regenerated from source the way a static declared-config file
(`capabilities.json`'s shape) is. It is checked here, in `precheck`, and
not in `godmode_fence.completion_audit` (which owns this unit's excluded
scope): `precheck` is the seam an agent already consults *before* touching
files, so a one-sided diff is caught while there is still time to add the
other half, not after the commit already landed. Never blocking: v1 is a
question, same as everything else in this module.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from .godmode_chronicle import Chronicle
from .godmode_constants import SETTLED_STATUSES
from .godmode_register import FOREIGN_SUBJECT_PREFIX
from .godmode_register import foreign_precedents as foreign_register_precedents
from .godmode_register import rejected_precedents
from .godmode_requests import closure_reason

# Subject prefix that marks a `decision` record as a paired-artifact
# declaration, mirroring `removal:`'s own prefix-on-an-existing-kind
# convention rather than opening a new EVENT_KINDS entry for it.
PAIRED_ARTIFACT_PREFIX = "paired-artifact:"

# Kinds that can carry a "we decided against this" meaning. There is no
# `removal` kind: `godmode removal record` writes a `decision` whose subject is
# prefixed `removal:`, which is exactly the surface that already existed for
# this purpose and had no reader.
_REJECTION_KINDS = frozenset({"decision", "lesson"})

# Words that mark a record as a refusal rather than an ordinary decision. A
# decision to *do* something is not prior grounds against doing it again.
_REFUSAL_WORDS = re.compile(
    r"(?i)\b(reject|rejected|refus|declin|dropped|removed|out of scope|wontfix|"
    r"will not|not adopt|incompatible|abandoned)\b")

# Kinds that can carry "this is already known and nobody has closed it". The
# third question, and the one that was missing: `already_built` reads the tree
# and `already_rejected` reads what was turned down, so a thing FILED and still
# open - an incident, a standing obligation, an ask nobody answered - matched
# neither and stayed invisible. The case that produced it: an open item
# describing the same symptom class as the report under investigation, listed
# twice in the same session's own queue and never once connected to it.
_OPEN_KINDS = frozenset({"obligation", "incident", "request"})

# Statuses that mean the thing is done with, on top of the settled ones. A
# record with no status at all counts as open, for the same reason a record
# with no status counts as live in the contradiction check: records written
# before status was recorded must keep being reported, or the exemption
# retires the reader rather than the record.
_DISCHARGED = frozenset({"closed", "done", "discharged", "resolved", "complete",
                         "completed", "fixed", "refused"})

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOPWORDS = frozenset("""
add the a an and or of to in on at is it this that for with from by as into
new make build create support implement need want should would could please
""".split())


def _terms(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text)} - _STOPWORDS


def _overlap(terms: set[str], text: str) -> int:
    haystack = text.lower()
    return sum(1 for term in terms if term in haystack)


def _norm(path: str) -> str:
    return str(path).replace("\\", "/")


def declare_paired_artifact(archive: Chronicle, label: str, a: str, b: str,
                            reason: str) -> dict[str, Any]:
    """Record "`a` and `b` change together" as a `decision` (see the module
    docstring for why this reuses that kind rather than a config file or a
    new EVENT_KINDS entry). `label` names the pair for later reference
    (`paired-artifact:<label>` becomes the record's subject) and must be
    unique per pair the same way a `removal:` subject is.
    """
    return archive.append(
        "decision", f"{PAIRED_ARTIFACT_PREFIX}{label}",
        {"a": _norm(a), "b": _norm(b), "reason": reason, "status": "active"},
    )


def declared_paired_artifacts(archive: Chronicle) -> list[dict[str, Any]]:
    """Every declared "these change together" pair, latest record per label
    only - a later declaration of the same label supersedes the last one
    the same way a plain `decision` naturally does when nothing folds it."""
    if not archive.initialized():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for record in archive.read_events():
        if record.get("kind") != "decision":
            continue
        subject = str(record.get("subject", ""))
        if not subject.startswith(PAIRED_ARTIFACT_PREFIX):
            continue
        data = record.get("data") or {}
        a, b = data.get("a"), data.get("b")
        if not a or not b:
            continue
        label = subject[len(PAIRED_ARTIFACT_PREFIX):]
        latest[label] = {
            "label": label, "a": _norm(a), "b": _norm(b),
            "reason": str(data.get("reason", "")),
            "sequence": record.get("sequence"),
        }
    return [latest[label] for label in sorted(latest)]


def paired_artifact_findings(archive: Chronicle, changed_files: Iterable[str]) -> dict[str, Any]:
    """A declared pair where this diff touches exactly one half.

    Advisory only (GAP-2, v1): the finding is a question, never a refusal -
    `godmode_fence.py` owns actually blocking a commit, and this module has
    never done that for any of its other five questions either.
    """
    changed = {_norm(path) for path in changed_files}
    pairs = declared_paired_artifacts(archive)
    findings: list[dict[str, Any]] = []
    for pair in pairs:
        a_touched, b_touched = pair["a"] in changed, pair["b"] in changed
        if a_touched == b_touched:  # both, or neither - nothing to flag
            continue
        touched, untouched = (pair["a"], pair["b"]) if a_touched else (pair["b"], pair["a"])
        findings.append({
            "label": pair["label"],
            "touched": touched,
            "untouched": untouched,
            "reason": pair["reason"],
            "where": f"seq:{pair['sequence']}",
            "question": f"'{touched}' changed but its declared pair '{untouched}' did not"
                        + (f" ({pair['reason']})" if pair["reason"] else "")
                        + " - was the omission deliberate, or is the other half owed an edit too?",
        })
    return {
        "changed_files": sorted(changed),
        "declared_pairs": len(pairs),
        "findings": findings,
        "verdict": "one-sided-change" if findings else "paired-or-clean",
    }


def recurrence_nudges(archive: Chronicle, task: str,
                      changed_files: Iterable[str] | None,
                      session: str) -> list[dict[str, Any]]:
    """Patterns the archive already holds, delivered BEFORE the action.

    Two sources, both requiring at least two recorded occurrences (one
    observation is an event; two are a pattern - the same floor the skill
    ladder uses): repeated incidents by subject, and controls that blocked
    the same cause more than once. Matching is the precheck's own weak
    term overlap, on purpose. Once per session per pattern: a delivery
    receipt is recorded and consulted, because a nudge that nags is a
    nudge that gets ignored.
    """
    if not archive.initialized():
        return []
    context = task + " " + " ".join(str(f) for f in (changed_files or []))
    terms = _terms(context)
    if not terms:
        return []

    candidates: list[dict[str, Any]] = []
    # Full archive, never a window: a pattern counter that forgets is a
    # monitor a patient failure mode simply waits out.
    incidents: dict[str, list[int]] = {}
    for record in archive.read_events(verify=False):
        if record.get("kind") == "incident":
            incidents.setdefault(str(record["subject"]), []).append(record["sequence"])
    for subject, seqs in sorted(incidents.items()):
        if len(seqs) >= 2:
            candidates.append({"pattern": subject, "occurrences": len(seqs),
                               "evidence": [f"seq:{s}" for s in seqs[-3:]]})

    from .godmode_attest import recurrences as _recurrences
    for entry in _recurrences(archive).get("repeated", []):
        candidates.append({
            "pattern": f"{entry['step']}: {entry['cause']}",
            "occurrences": entry["occurrences"],
            "evidence": [],
        })

    delivered: set[str] = set()
    for record in archive.select(kind="action", limit=500):
        if record["subject"] == "recurrence-nudge" and \
                record["data"].get("session") == session:
            delivered.add(str(record["data"].get("pattern", "")))

    nudges = []
    for candidate in candidates:
        if candidate["pattern"] in delivered:
            continue
        if _overlap(terms, candidate["pattern"]) < 2:
            continue
        nudges.append({
            **candidate,
            "why": "this pattern has recurred in the record; read it before "
                   "the action repeats it",
        })
        archive.append("action", "recurrence-nudge",
                       {"session": session, "pattern": candidate["pattern"]})
    return nudges


def precheck(project_root: Path | str, archive: Chronicle, task: str,
            changed_files: Iterable[str] | None = None) -> dict[str, Any]:
    """What already exists and what was already refused, for this task.

    Matching is by term overlap rather than by wording, because a request is
    almost never phrased the way the thing it duplicates was phrased. It is a
    weak test on purpose: a strong one that reports nothing is the check that
    cannot fail, and the cost of over-reporting is a line the reader dismisses.
    """
    root = Path(project_root)
    terms = _terms(task)
    searched: list[str] = []

    already_built: list[dict[str, Any]] = []
    symbols_examined = 0
    from .godmode_atlas import build as build_atlas

    atlas = build_atlas(root)
    searched.append(f"atlas symbols in {root.name or '.'}")
    for symbol in atlas.symbols:
        symbols_examined += 1
        name = str(getattr(symbol, "name", symbol))
        path = str(getattr(symbol, "path", ""))
        line = getattr(symbol, "line", None)
        # A location a reader can open, not a repr. The first version printed
        # the dataclass and the answer was unusable at exactly the moment it
        # was meant to be read.
        where = f"{path}:{line} {name}" if path else name
        if terms and _overlap(terms, f"{name} {path}".replace("_", " ").replace("/", " ")) >= 2:
            already_built.append({
                "where": where,
                "name": name,
                "question": f"'{name}' already exists in {path or 'this project'} - does it "
                            "do what this asks, or is this genuinely a different thing?",
            })

    records = archive.read_events() if archive.initialized() else []
    searched.append(f"{len(records)} archive records ({', '.join(sorted(_REJECTION_KINDS))})")
    already_rejected: list[dict[str, Any]] = []
    for record in records:
        kind = record.get("kind")
        data = record.get("data") or {}
        # U-E2: a `reg-foreign:` record is a decision-kind record too (an
        # imported precedent's `state` field routinely reads "rejected-
        # precedent", which trips `_REFUSAL_WORDS` on its own), but it must
        # never be scored by this LOCAL free-text scanner - only the
        # dedicated, explicitly-advisory `foreign_precedents` section below
        # may surface it. Skipped here, not filtered out of `records`
        # itself, so `records_examined`/`searched` still count it honestly.
        if str(record.get("subject", "")).startswith(FOREIGN_SUBJECT_PREFIX):
            continue
        if kind == "request":
            # A request closed as `refused` is a rejection with the operator's
            # own words attached, which is the strongest form of prior ground
            # there is. It only counts when the closure said so: a plain
            # `closed` covers both "we built it" and "we turned it down".
            if closure_reason(str(data.get("status", ""))) != "refused":
                continue
        elif kind not in _REJECTION_KINDS:
            continue
        # Every string field, not just `value`: a removal record carries its
        # reason across six named fields and none of them is called `value`,
        # so reading one key found nothing in the records written by the one
        # command built to answer this question.
        text = " ".join([str(record.get("subject", ""))]
                        + [str(v) for v in data.values() if isinstance(v, str)])
        # A refused request already said so in its status; requiring the word
        # again in its prose would discard the one record that states the
        # outcome without arguing it.
        if kind != "request" and not _REFUSAL_WORDS.search(text):
            continue
        if terms and _overlap(terms, text) >= 2:
            already_rejected.append({
                "where": f"seq:{record.get('sequence')}",
                "subject": str(record.get("subject", ""))[:120],
                "question": "this was refused before - has the reason changed, or does "
                            "the refusal still hold?",
            })

    searched.append(f"open records ({', '.join(sorted(_OPEN_KINDS))})")
    already_reported: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") not in _OPEN_KINDS:
            continue
        data = record.get("data") or {}
        status = str(data.get("status", "")).lower()
        if status in _DISCHARGED or status in SETTLED_STATUSES:
            continue
        if record.get("kind") == "request" and closure_reason(status) is not None:
            continue
        text = " ".join([str(record.get("subject", ""))]
                        + [str(v) for v in data.values() if isinstance(v, str)])
        if terms and _overlap(terms, text) >= 2:
            already_reported.append({
                "where": f"seq:{record.get('sequence')}",
                "subject": str(record.get("subject", ""))[:120],
                "question": "this is already filed and still open - is the task in hand the "
                            "same thing, and does what is known there change the approach?",
            })

    precedents = rejected_precedents(archive)
    searched.append(f"{len(precedents)} rejected-precedent register entries")
    rejected_precedent_hits: list[dict[str, Any]] = []
    for hit in precedents:
        key_terms = _terms(hit["key"].replace("-", " ").replace("_", " "))
        # A precise match, not a weak one: the register is a closed
        # enumeration the archive itself adjudicated, so every term the
        # precedent's key names must be present in the task - unlike
        # already_rejected's deliberately loose overlap-of-two over free
        # text, a short identifying key earns a subset match instead of an
        # arbitrary threshold that would be too strict for a one-word key
        # and too loose for a five-word one.
        if key_terms and key_terms.issubset(terms):
            rejected_precedent_hits.append({
                "where": f"seq:{hit['sequence']}",
                "domain": hit["domain"],
                "key": hit["key"],
                "sequence": hit["sequence"],
                "message": "cite and supersede it, or drop the work",
            })

    foreign_hits = foreign_register_precedents(archive)
    searched.append(f"{len(foreign_hits)} foreign precedent (reg-foreign:) entries")
    foreign_precedent_hits: list[dict[str, Any]] = []
    for hit in foreign_hits:
        key_terms = _terms(hit["key"].replace("-", " ").replace("_", " "))
        # Same precise, subset-of-key-terms match as the local rejected-
        # precedent check above - never the weaker overlap-of-two used for
        # free text. U-E2's trust model (advisory everywhere): this hit
        # never enters `findings`/`verdict` below, no matter how strong the
        # match is - a foreign precedent cannot block, only inform.
        if key_terms and key_terms.issubset(terms):
            origin = str(hit.get("origin") or "")
            foreign_precedent_hits.append({
                "where": f"seq:{hit['sequence']}",
                "domain": hit["domain"],
                "key": hit["key"],
                "state": hit["state"],
                "sequence": hit["sequence"],
                "origin": origin,
                "message": f"foreign precedent (from {origin[:8]}) - advisory only; "
                           "review before treating it as settled here",
            })

    # `foreign_precedent_hits` is deliberately excluded from `findings`: U-E2's
    # trust model makes a foreign precedent advisory everywhere, and that
    # includes never flipping this precheck from "proceed" to "prior work
    # found" on its own.
    findings = bool(already_built or already_rejected or already_reported
                    or rejected_precedent_hits)
    report = {
        "task": task,
        "already_built": already_built,
        "already_rejected": already_rejected,
        "already_reported": already_reported,
        "rejected_precedents": rejected_precedent_hits,
        "foreign_precedents": foreign_precedent_hits,
        # Stated so an empty answer cannot be read as clearance from a check
        # that examined nothing.
        "searched": searched,
        "symbols_examined": symbols_examined,
        "records_examined": len(records),
        "verdict": "prior-work-found" if findings else "no-prior-work-found",
    }
    if changed_files is not None:
        # Same advisory-everywhere rule as `foreign_precedents`: a one-sided
        # paired-artifact diff never joins `findings`/`verdict` above, no
        # matter how confident the hit - GAP-2 v1 is a question, not a gate.
        report["paired_artifacts"] = paired_artifact_findings(archive, changed_files)
    return report


def render(report: dict[str, Any]) -> str:
    """For a reader deciding whether to keep going, not for a parser."""
    if report["verdict"] == "no-prior-work-found":
        lines = [f"No prior work found for '{report['task'][:60]}'; searched "
                 f"{report['symbols_examined']} symbols and "
                 f"{report['records_examined']} records."]
        # A foreign precedent never changes this verdict (advisory
        # everywhere, U-E2), but it must not go unmentioned just because it
        # was the only thing found - that would be surfacing it in the JSON
        # report while silently dropping it from the text a human reads.
        for hit in report.get("foreign_precedents", []):
            lines.append(
                f"  [foreign precedent (from {hit['origin'][:8]})] {hit['domain']}:{hit['key']} "
                f"state={hit['state']} ({hit['where']}) - advisory only, not a local finding"
            )
        lines.extend(_paired_artifact_lines(report))
        return "\n".join(lines)
    lines = [f"Prior work touching '{report['task'][:60]}':"]
    # Precedent first: a closed-enumeration refusal the archive itself
    # adjudicated is a sharper claim than free-text overlap, and the one
    # that comes with a way through rather than just a warning.
    for hit in report.get("rejected_precedents", []):
        lines.append(
            f"  [rejected-precedent] {hit['domain']}:{hit['key']} "
            f"({hit['where']}) - {hit['message']}"
        )
    # Advisory only, and rendered as such: a foreign precedent never blocked
    # `verdict` above, and its line here must not read like the local,
    # archive-adjudicated finding directly above it.
    for hit in report.get("foreign_precedents", []):
        lines.append(
            f"  [foreign precedent (from {hit['origin'][:8]})] {hit['domain']}:{hit['key']} "
            f"state={hit['state']} ({hit['where']}) - advisory only, not a local finding"
        )
    # Open first of the rest: a thing already filed and unclosed is the one a
    # reader is most likely to be about to duplicate, and the one that
    # carries what is already known about it.
    for hit in report.get("already_reported", []):
        lines.append(f"  [already filed, open] {hit['subject']} ({hit['where']})")
    for hit in report["already_rejected"]:
        lines.append(f"  [refused before] {hit['subject']} ({hit['where']})")
    shown = report["already_built"][:10]
    for hit in shown:
        lines.append(f"  [already exists] {hit['where']}")
    # A truncated list that does not say it was truncated is the defect this
    # product reports elsewhere; it does not get to commit it here.
    if len(report["already_built"]) > len(shown):
        lines.append(f"  ... and {len(report['already_built']) - len(shown)} more existing "
                     "symbols, not shown")
    lines.append("None of these is a refusal. Check whether the reason still holds.")
    lines.extend(_paired_artifact_lines(report))
    return "\n".join(lines)


def _paired_artifact_lines(report: dict[str, Any]) -> list[str]:
    """Paired-artifact hits, rendered the same in either verdict branch: a
    clean precheck for the *task* can still sit on top of a one-sided diff
    against a *declared* pair, and the two questions are independent."""
    hits = report.get("paired_artifacts", {}).get("findings", [])
    return [
        f"  [paired-artifact, advisory] {hit['question']} ({hit['where']})"
        for hit in hits
    ]
