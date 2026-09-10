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

# Seconds the precheck atlas walk may take before it answers with what it
# has and says so. Field report 26: an unbounded build outlasted the suite.
PRECHECK_ATLAS_BUDGET_SECONDS = 20.0

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

    # Field report 26: `precheck --about` did not return in five minutes on
    # a TypeScript tree whose full atlas build takes nine. A gate that
    # outlasts the suite is not a gate: the build is bounded, and the bound
    # is stated in `searched` so a partial map never reads as a full one.
    atlas = build_atlas(root, budget_seconds=PRECHECK_ATLAS_BUDGET_SECONDS)
    searched.append(f"atlas symbols in {root.name or '.'}"
                    + (f" (bounded: {atlas.gap})" if getattr(atlas, "gap", None) else ""))
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
        "missing_surface": missing_surface(task),
        "registry_matches": _registry_matches(Path(project_root), task),
        "design_mentions": _design_mentions(Path(project_root), task),
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


_SURFACES: tuple[tuple[str, str, str], ...] = (
    (r"(?i)\b(?:auth|login|sign[- ]?in|session|token|permission|role|admin)\b", "authorization check",
     "who may call this, and the test that proves the denied case"),
    (r"(?i)\b(?:api|endpoint|fetch|request|client|upstream|webhook|http)\b", "retries and timeouts",
     "what happens on a timeout or a 5xx, and the bound on retries"),
    (r"(?i)\b(?:tenants?|org(?:anization)?s?|workspaces?|customers?|accounts?)\b", "tenant isolation",
     "the query or path that carries the tenant id, and the cross-tenant denied case"),
    (r"(?i)\b(?:migration|schema|table|column|database|db)\b", "migration and rollback",
     "the migration's reverse step, and the data left behind on rollback"),
    (r"(?i)\b(?:upload|file|attachment|image|video|import)\b", "input limits",
     "size and type limits on what arrives, and the rejected case"),
    (r"(?i)\b(?:payment|checkout|order|invoice|billing|charge)\b", "idempotency",
     "what a retried request does the second time, and the test for it"),
    (r"(?i)\b(?:queue|worker|job|cron|background|async|concurren|parallel)\b", "race and retry",
     "the concurrent case and the poisoned-job case"),
    (r"(?i)\b(?:cache|memo|redis)\b", "invalidation", "what clears the cache and what is served stale"),
    # Part 4, 4.5: dev-observed duplicates were StrictMode; the decisive step
    # was a production build re-measured before any fix.
    (r"(?i)\b(?:latency|slow|perf(?:ormance)?|duplicate|double[- ]?(?:load|render|request|fetch)|timing|"
     r"waterfall|re-?render|N\+1|n\+1)\b", "measurement environment",
     "the number that decides the fix comes from the environment that ships (a production build, real "
     "data), not the dev server: StrictMode double-invokes effects and dev bundles are not what users run"),
)


def _registry_matches(project: Path, task: str) -> list[dict[str, Any]]:
    try:
        from .godmode_registry import match_feedback, parse_registry, registry_path
        path = registry_path(project)
        return match_feedback(task, parse_registry(path)) if path else []
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable registry matches nothing
        return []


def _design_mentions(project: Path, task: str) -> list[dict[str, Any]]:
    try:
        from .godmode_registry import design_mentions
        return design_mentions(project, task)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: unreadable design documents mention nothing
        return []


def missing_surface(task: str) -> list[dict[str, str]]:
    """PRD C-1: the invisible twenty percent, from the task text alone -
    surfaces a feature of this shape needs and that agents leave out.
    Obligations to discharge or waive, never generated code."""
    out: list[dict[str, str]] = []
    for pattern, surface, why in _SURFACES:
        if re.search(pattern, task or ""):
            out.append({"surface": surface, "why": why,
                        "record": f"godmode remember --kind obligation --subject \"{surface}: {task[:40]}\" "
                                  f"--value \"{why}\""})
    return out


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


# Raw check runners only - godmode's own verdict-bearing subcommands are
# deliberately absent, and any command that already says `godmode` is
# already on the wrapped path.
_RAW_CHECK = re.compile(
    r"(?i)\b(?:pytest|py\.test|unittest|vitest|jest|mocha|rspec|phpunit|"
    r"cargo\s+test|go\s+test|dotnet\s+test|tsc\b|mypy|pyright|"
    r"npm\s+(?:test|run\s+test\S*)|yarn\s+test|pnpm\s+test)")


def verify_promotion_advisory(archive: Chronicle, command: str,
                              session: str | None) -> str | None:
    """One sentence, once per session, when a check runs raw.

    A raw test run's exit code evaporates; the same run under `godmode
    verify <name> -- <command>` leaves an attestation the claim gate can
    cite. Advisory only, receipt-bounded exactly like the recurrence
    nudge: the first raw check-shaped command of a session speaks, every
    later one is silent - a nag on every test run teaches dismissal.
    """
    # No session key means no honest once-per-session bound: the receipt
    # would become once-per-archive-forever (field-diagnosed 2026-09-01 -
    # the advisory fired exactly once in the dev archive's whole life and
    # then never again, and one hook e2e test paid for it). Silence beats
    # a bound that lies.
    if not session or not command or "godmode" in command.lower():
        return None
    if not _RAW_CHECK.search(command):
        return None
    key = session
    try:
        for record in archive.select(kind="action", limit=200):
            if record["subject"] == "verify-promotion-nudge" and \
                    record["data"].get("session") == key:
                return None
        archive.append("action", "verify-promotion-nudge", {"session": key})
    except Exception:  # noqa: BLE001 - an unwritable receipt silences the nudge
        return None
    return (
        "godmode: this check runs raw - its exit code leaves no record. "
        "`godmode verify <name> -- <command>` runs the same check and "
        "attests the outcome, which claims can then cite. Once per "
        "session; carry on if this run is exploratory.")


# The prompt's own shape names the verb. Few shapes, each once per
# session - a vocabulary that grows past what a session can absorb teaches
# dismissal.
_PROMPT_SHAPES = (
    ("fix", re.compile(r"(?i)\b(?:fix|debug|broken|not\s+working|failing|"
                       r"keeps?\s+fail|crash)"),
     "godmode: fix-shaped work - `godmode atlas closure <files>` lists the "
     "dependents a fix must retest; if one check has already failed twice "
     "with edits between, open `godmode remember --kind incident` before "
     "the next attempt, and run the deciding check via `godmode verify` so "
     "its outcome is attested."),
    ("ship", re.compile(r"(?i)\b(?:push|release|ship|deploy|publish|"
                        r"cut\s+(?:a\s+)?(?:release|version|tag))"),
     "godmode: ship-shaped work - `godmode precheck --preflight` runs the "
     "scans and the demand-vs-use census on a disposable worktree before "
     "anything leaves the machine; when nothing leaves the machine, "
     "`godmode precheck --about \"<what ships>\"` runs the known-bad-shape "
     "scan on the working tree instead."),
    # Thirteenth field report (obligation 9700): 198 plan-shaped asks and
    # zero plan records in one archive; a reversal is the demand for an
    # independent check (8 warranted, 0 run). The census names both
    # afterwards; these name the verb as the ask arrives.
    ("plan", re.compile(r"(?i)\b(?:make\s+a\s+plan|plan\s+(?:for|out|the)|"
                        r"roadmap|milestones?|spec\s+(?:it\s+)?out|"
                        r"break\s+(?:this|it|the\s+work)\s+(?:down|into))\b"),
     "godmode: plan-shaped work - record the contract before executing: "
     "`godmode plan` (spec, acceptance criteria, steps) so `planmode check` "
     "can hold the work to it; a plan that lives only in prose has no reader."),
    ("reversal", re.compile(
        r"(?i)(?:\bturns\s+out\b|\b(?:diagnosis|cause|fix|root\s+cause)\s+"
        r"was\s+wrong\b|\bwrong\s+(?:fix|cause|diagnosis)\b|"
        r"\bactually\s+the\s+(?:cause|bug|problem)\b|\bre-?check(?:ed)?\s+"
        r"(?:the|that|my)\b|\breal\s+cause\s+is\b)"),
     "godmode: reversal-shaped work - a diagnosis that reversed once is the "
     "demand for an independent check: `godmode verify <name> --command "
     "\"<deciding check>\"` attests the outcome and `godmode differential` "
     "records the two states before the next edit."),
    ("resume", re.compile(r"(?i)\b(?:where\s+(?:are|were)\s+we|pick\s+up|"
                          r"continue\s+from|what.s\s+the\s+status)"),
     "godmode: resume-shaped work - `godmode resume` reads the recorded "
     "state; trust it over memory of the last session."),
    ("review", re.compile(r"(?i)\b(?:review|audit|critique|second\s+opinion|"
                          r"look\s+over)\b"),
     "godmode: review-shaped work - record the conclusion with `godmode "
     "verdict record` (witness + independent checker) so the all-clear "
     "is a record, not a sentence."),
    ("done-check", re.compile(r"(?i)\b(?:is\s+it\s+done|are\s+we\s+done|"
                              r"anything\s+pending|what.s\s+left)\b"),
     "godmode: done-check - `godmode status remaining` lists the frontier "
     "with evidence tiers; declared and verified are different columns."),
    # The largest lesson source in every field corpus is the operator's
    # own catch - and the catch-moment is when the evidence is freshest.
    # Twenty-first field report (obligation 10116): zero help on an RCA.
    # The verbs exist; nothing named them when a failure was chased.
    ("investigation", re.compile(
        r"(?i)(?:\broot[\s-]?cause\b|\brca\b|\bwhy\s+(?:did|does|is|was|are)\b[^?.]{0,60}"
        r"\b(?:fail|failing|failed|break|broken|crash|wrong|slow|red)\b|"
        r"\binvestigat|\bdiagnos|\bwhat\s+caused\b|\bdeep[\s-]?dive\b|\bpost-?mortem\b)"),
     "godmode: investigation-shaped work - `godmode mistakes` lists prior "
     "incidents of this class; `godmode error-pattern` matches the failure "
     "text against declared patterns; `godmode incident --failure-class "
     "<class>` records the failure while the evidence is fresh; `godmode "
     "differential` records the two states before and after a change; "
     "`godmode plant` proves a guard fails when broken; `godmode verify "
     "<name> --command \"<deciding check>\"` attests the deciding check "
     "so the root cause is a record, not a story."),
    ("correction", re.compile(
        r"(?i)(?:\bthat.s\s+(?:wrong|incorrect|not\s+right)\b|"
        r"\bwhy\s+(?:did|do|have|are)\s+you\s+(?:miss|not|skip|ignor)|"
        r"\byou\s+(?:did\s*n[o']t|missed|forgot|skipped|ignored)\b|"
        r"\bnot\s+what\s+i\s+asked\b|\bwrong\s+again\b)"),
     "godmode: the operator caught a miss - record it while the evidence "
     "is fresh (`godmode remember --kind incident \"<what happened>\"`); "
     "a miss that recurs earns a guard, not another apology."),
)


def prompt_shape_nudge(archive: Chronicle, prompt: str,
                       session: str | None,
                       resume_doc: str | None = None) -> str | None:
    """One sentence when the prompt's shape names a verb, once per shape
    per session - the receipt contract `verify_promotion_advisory` uses,
    keyed additionally by shape so fix and ship each get their one say.

    `resume_doc` is the project's own state document when it keeps one
    (field report 23: `godmode resume` was pushed at a project whose
    STATE.md already carried the resume); the resume shape then says
    nothing."""
    if not prompt:
        return None
    matched = next(((name, text) for name, pattern, text in _PROMPT_SHAPES
                    if pattern.search(prompt)), None)
    if not matched:
        return None
    shape, text = matched
    if shape == "resume" and resume_doc:
        return None
    if not session:
        return None
    key = session
    try:
        for record in archive.select(kind="action", limit=200):
            if record["subject"] == "prompt-shape-nudge" and \
                    record["data"].get("session") == key and \
                    record["data"].get("shape") == shape:
                return None
        archive.append("action", "prompt-shape-nudge",
                       {"session": key, "shape": shape})
    except Exception:  # noqa: BLE001
        return None
    return text


_FAILURE_SIGNAL = re.compile(
    r"(?im)(?:^Traceback \(most recent call last\)|\bexit(?:ed)?(?: code)?\s+[1-9]\d*\b|"
    r"\bFAILED\b|\b(?:Error|Exception)\b:|\bcommand not found\b|\bfatal:|"
    r"\bpanic:|\bsegmentation fault\b|\bnpm ERR!|\bERROR\b|"
    # Field report 22 (2026-09-09): "no help with the memory kills". A
    # process the kernel or the host killed for memory leaves one of these.
    r"\bKilled\b|\bexit(?:ed)?(?: code)?\s+137\b|\bOOM\b|\bout of memory\b|"
    r"\bMemoryError\b|\bheap out of memory\b|\bENOMEM\b)")


def changes_since_last_green(archive: Chronicle, project: Path | None) -> dict[str, Any]:
    """What the record already knows about this tree: the newest attestation
    that ran and carries a worktree head, its age, and every file changed
    since that head (tracked diff plus untracked). Empty `project` or no git
    gives the honest shape - `attested` None, `changed` from nothing."""
    out: dict[str, Any] = {"attested": None, "head": None, "age_days": None,
                           "changed": [], "prior_incidents": 0}
    try:
        for record in reversed(archive.select(kind="attestation", limit=200)):
            data = record.get("data") or {}
            head = (data.get("worktree") or {}).get("head")
            if data.get("status") == "ran" and head:
                out["attested"] = str(record.get("subject", ""))
                out["head"] = str(head)
                stamp = str(record.get("recorded_at", ""))[:19]
                try:
                    from datetime import datetime, timezone
                    then = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
                    out["age_days"] = round((datetime.now(timezone.utc) - then).total_seconds() / 86400, 1)
                except ValueError:
                    out["age_days"] = None  # an unparseable stamp is an unknown age, stated as such
                break
        out["prior_incidents"] = len(archive.select(kind="incident", limit=500))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable archive reports nothing; this rides a hook that never raises into the host
        return out
    if project is None:
        return out
    from .godmode_anchor import run_git
    changed: set[str] = set()
    if out["head"]:
        changed.update((run_git(project, "diff", "--name-only", out["head"]) or "").split())
    else:
        changed.update((run_git(project, "diff", "--name-only", "HEAD") or "").split())
    for line in (run_git(project, "status", "--porcelain") or "").splitlines():
        if line.startswith("??"):
            changed.add(line[3:].strip())
    out["changed"] = sorted(p for p in changed if p)[:200]
    return out


def _named_files(paths: list[str], cap: int = 4) -> str:
    shown = ", ".join(paths[:cap])
    return shown + (f" (+{len(paths) - cap} more)" if len(paths) > cap else "")


def failure_nudge(archive: Chronicle, tool_output: str,
                  session: str | None, project: Path | None = None) -> str | None:
    """One line, once per session, when a tool run failed: what the record
    already knows about this tree, never a list of verbs to run (field
    reports 21-25: a verb-naming line reached four sessions in 368
    tracebacks and pointed at nothing when it did). Read at Stop from the
    turn's tool output, because PostToolUseFailure is not in the shared
    manifest every host reads."""
    if not tool_output or not session or not _FAILURE_SIGNAL.search(tool_output):
        return None
    try:
        for record in archive.select(kind="action", limit=200):
            if record["subject"] == "failure-nudge" and                     record["data"].get("session") == session:
                return None
        archive.append("action", "failure-nudge", {"session": session})
    except Exception:  # noqa: BLE001
        return None
    if _MEMORY_KILL.search(tool_output):
        # Field report 22: a kill is not a bug in the code under test; it
        # is a run that outgrew its box, and the next move is a smaller box.
        return (
            "godmode: a tool run was killed for memory this turn (137/OOM) - "
            "the next attempt needs a bound (`godmode watchdog`) or a smaller "
            "scope; a kill that recurs is a ceiling, not a retry (failure "
            "class memory-kill).")
    known = changes_since_last_green(archive, project)
    changed = known["changed"]
    if known["attested"]:
        age = f"{known['age_days']} day(s) ago" if known["age_days"] is not None else "at an unknown time"
        line = (f"godmode: a tool run failed this turn; last attested check "
                f"'{known['attested']}' ran {age} at {known['head']}; "
                f"{len(changed)} file(s) changed since"
                + (f": {_named_files(changed)}" if changed else ""))
    else:
        line = ("godmode: a tool run failed this turn; no attested check on "
                f"record for this tree; {len(changed)} uncommitted file(s)"
                + (f": {_named_files(changed)}" if changed else ""))
    if known["prior_incidents"]:
        line += f"; {known['prior_incidents']} prior incident(s) on record"
    return line + "."


_MEMORY_KILL = re.compile(
    r"(?i)(?:\bKilled\b|\bexit(?:ed)?(?: code)?\s+137\b|\bOOM\b|\bout of memory\b|"
    r"\bMemoryError\b|\bheap out of memory\b|\bENOMEM\b)")
