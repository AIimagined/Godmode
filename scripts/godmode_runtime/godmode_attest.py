"""Make a skipped step a blocking state instead of an apology afterwards.

Two mechanisms, both deliberately dumb so they cannot be reasoned around:

* Attestation. Every mandated step records what it did, including finding nothing.
  A HARD rule with no attestation blocks the gate it guards.
* Claim binding. An assertion about project state cites records that must resolve.
  An unresolvable citation downgrades the claim to a hypothesis automatically — it
  is not warned about, it is demoted.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

STATUSES = ("ran", "empty", "skipped", "blocked")
GRADES = ("observed", "hypothesis", "verified", "unknown")

_FILE_CITE = re.compile(r"^file:(?P<path>[^#]+)(?:#L(?P<start>\d+)(?:-L?(?P<end>\d+))?)?$")
_RECORD_CITE = re.compile(r"^rec:(?P<digest>[0-9a-f]{6,64})$")

# Named because naming them is the intervention. Each entry is a thought that has
# preceded a skipped step, mapped to the gate it predicts. Surfaced on a block so the
# reasoning is interrupted rather than the action alone.
RATIONALIZATIONS: tuple[tuple[str, str], ...] = (
    ("This one is small enough to skip the check.", "before_mutation"),
    ("The answer seems obvious already.", "before_approach"),
    ("No code is written yet, so this is not a change.", "before_approach"),
    ("The suite passed, so the blast radius is covered.", "before_completion"),
    ("I already know what that document says.", "session_open"),
    ("The status label is recent enough to trust.", "before_completion"),
    ("I will record the evidence after this step.", "session_close"),
)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    trigger: str
    missing: tuple[dict[str, Any], ...]

    def view(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trigger": self.trigger,
            "allowed": self.allowed,
            "missing": list(self.missing),
        }
        if not self.allowed:
            payload["watch_for"] = [
                text for text, trigger in RATIONALIZATIONS if trigger == self.trigger
            ] or [text for text, _ in RATIONALIZATIONS]
        return payload


def agent_fingerprint() -> dict[str, Any]:
    """Identify who is acting, so drift between models is attributable."""
    from .godmode_chronicle import writer_fingerprint

    return writer_fingerprint()


def open_session(archive: Chronicle, label: str) -> str:
    record = archive.append(
        "session", label, {"state": "open", "agent": agent_fingerprint()}, evidence=[]
    )
    return f"S-{record['record_hash'][:12]}"


def opening_handshake(archive: Chronicle, anchor: Any, project: Path) -> dict[str, Any]:
    """The fixed, model-independent sequence every session opens with.

    The order is part of the contract: whichever model opens the session, the
    same facts arrive in the same places, so a missing fact is visible as a gap
    instead of a difference in style. Includes the enforcement table, so the
    contract degrades honestly on hosts that cannot hold every control.
    """
    from .godmode_anchor import host_capabilities, run_git
    from .godmode_lens import repo_state
    from .godmode_plan import active_plan

    porcelain = run_git(project, "status", "--porcelain=v1", "--untracked-files=all")
    dirty = [line[2:].lstrip() for line in porcelain.splitlines()] if porcelain else []
    state = repo_state(project)
    plan = active_plan(archive)
    obligations = [
        record["subject"]
        for record in archive.select(kind="obligation", limit=200)
        if record["data"].get("status") not in ("closed", "done")
    ]
    invariants = [
        record["subject"]
        for record in archive.select(kind="invariant", limit=200)
        if record["data"].get("status") != "retired"
    ]
    try:
        from .godmode_corpus import resolve_roles

        sources_total = len(resolve_roles(project).bindings)
    except Exception:
        sources_total = 0
    handshake: dict[str, Any] = {
        "identity": anchor.public_view() if anchor is not None else None,
        "branch": getattr(anchor, "branch", None),
        "head": getattr(anchor, "head", None),
        "dirty_files": {"count": len(dirty), "paths": sorted(dirty)[:20]},
        # Directly after dirty_files, because an unfinished git operation is
        # what a dirty count silently hides.
        "repo_state": state,
        "active_plan": {"id": plan["id"], "state": plan["state"]} if plan else None,
        "open_obligations": sorted(set(obligations))[:20],
        "protected_invariants": sorted(set(invariants))[:20],
        "required_sources": {
            "documents": sources_total,
            "read": 0,
            "statement": f"read 0 of {sources_total} required sources",
        },
        "enforcement": host_capabilities()["controls"],
        "agent": agent_fingerprint(),
    }
    if state["crisis"]:
        operations = state["in_progress"] or ["detached-head"]
        handshake["warning"] = (
            f"repository has an in-progress git operation: {', '.join(operations)}; "
            "finish or abort it before substantive work"
        )
    return handshake


def _sessions(archive: Chronicle) -> list[dict[str, Any]]:
    return archive.select(kind="session", limit=200)


def latest_session(archive: Chronicle) -> str | None:
    records = _sessions(archive)
    if not records:
        return None
    # select() is chronological, so the newest session is the last element.
    return f"S-{records[-1]['record_hash'][:12]}"


def record_step(
    archive: Chronicle,
    session: str,
    step: str,
    status: str,
    result: str = "",
    evidence: list[str] | None = None,
    rule_ids: list[str] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ArchiveError(f"Unknown attestation status '{status}'; expected one of {', '.join(STATUSES)}")
    if status == "skipped" and not reason.strip():
        # A skip without a reason is the failure this module exists to stop.
        raise ArchiveError("A skipped step requires --reason stating why it was skipped")
    return archive.append(
        "attestation",
        step,
        {
            "session": session,
            "status": status,
            "result": result,
            "reason": reason,
            "rule_ids": sorted(rule_ids or []),
            "agent": agent_fingerprint(),
        },
        evidence=evidence or [],
    )


def run_check(
    archive: Chronicle,
    session: str,
    project: Path,
    name: str,
    command: list[str],
    rule_ids: list[str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    """Run a declared check and attest its exit code, rather than its report.

    An attestation an agent writes about its own work is a report. The gate it
    satisfies is then only as good as the agent's willingness to say the check
    failed, which is exactly the moment it is least inclined to. So the runner
    records the result: a non-zero exit is stored as `blocked`, and `blocked` never
    satisfies a gate, so a failing check cannot be attested into a pass.
    """
    import subprocess

    try:
        completed = subprocess.run(
            command, cwd=str(project), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        code = completed.returncode
        tail = ((completed.stdout or "") + (completed.stderr or "")).strip().splitlines()
        detail = " | ".join(tail[-3:])[:300] if tail else "(no output)"
    except FileNotFoundError:
        code, detail = 127, f"command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        code, detail = 124, f"timed out after {timeout}s"

    passed = code == 0
    citation = f"cmd:{' '.join(command)[:160]}"
    record = record_step(
        archive,
        session,
        f"check:{name}",
        "ran" if passed else "blocked",
        result=f"exit {code}: {detail}",
        evidence=[citation],
        rule_ids=rule_ids,
        reason="" if passed else f"check failed with exit {code}",
    )
    return {
        "check": name,
        "command": command,
        "exit_code": code,
        "passed": passed,
        "detail": detail,
        "attested": "ran" if passed else "blocked",
        "sequence": record["sequence"],
        # Returned so a caller cites what was stored instead of rebuilding it. A
        # citation reconstructed by hand has to guess the normalisation, and a near
        # miss reads exactly like a fabrication.
        "citation": citation,
    }


def plant_and_observe(
    archive: Chronicle,
    session: str,
    project: Path,
    name: str,
    command: list[str],
    target: str,
    replace: str | None = None,
    with_text: str = "",
    append: str | None = None,
    rule_ids: list[str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    """Prove a guard can fail, by breaking the thing it guards and watching it.

    A guard that has never been seen failing is a suggestion. It may be asserting
    nothing, testing the wrong surface, or silently skipping - and all three look
    exactly like a pass. So the sequence is green, then red with a planted
    violation, then green again once restored. Only that whole sequence attests.

    The plant itself is verified to have landed: a mutation that changed no bytes
    would produce a green run that reads as "the guard held" when nothing was ever
    broken.
    """
    import subprocess

    path = project / target
    if not path.is_file():
        raise ArchiveError(f"Cannot plant a violation in a missing file: {target}")
    original = path.read_bytes()

    def run() -> int:
        try:
            done = subprocess.run(command, cwd=str(project), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout)
            return done.returncode
        except FileNotFoundError:
            return 127
        except subprocess.TimeoutExpired:
            return 124

    steps: dict[str, Any] = {}
    try:
        steps["baseline"] = run()

        text = original.decode("utf-8", errors="replace")
        if append is not None:
            mutated = text + ("" if text.endswith("\n") else "\n") + append + "\n"
        elif replace is not None:
            mutated = text.replace(replace, with_text, 1)
        else:
            raise ArchiveError("A plant needs --replace or --append")

        planted_bytes = mutated.encode("utf-8")
        # A plant that changes nothing turns the whole exercise into a green run
        # that proves only that the file was untouched.
        if planted_bytes == original:
            raise ArchiveError(
                f"The planted violation changed no bytes in {target}; the guard would "
                "have been observed passing against unmodified code"
            )
        path.write_bytes(planted_bytes)
        steps["planted_bytes_changed"] = len(planted_bytes) - len(original)
        steps["with_violation"] = run()
    finally:
        path.write_bytes(original)
    steps["restored"] = run()

    green_first = steps["baseline"] == 0
    went_red = steps["with_violation"] != 0
    green_again = steps["restored"] == 0
    proven = green_first and went_red and green_again

    if proven:
        detail = f"green({steps['baseline']}) -> red({steps['with_violation']}) -> green({steps['restored']})"
        reason = ""
    else:
        detail = (
            f"baseline={steps['baseline']} planted={steps['with_violation']} "
            f"restored={steps['restored']}"
        )
        reason = (
            "guard did not fail against a planted violation" if green_first and not went_red
            else "guard was not green before planting" if not green_first
            else "state did not return to green after restoring"
        )

    record = record_step(
        archive, session, f"guard:{name}",
        "ran" if proven else "blocked",
        result=f"{'observed failing' if proven else 'not observed failing'}: {detail}",
        evidence=[f"cmd:{' '.join(command)[:120]}", f"file:{target}"],
        rule_ids=rule_ids,
        reason=reason,
    )
    return {
        "guard": name,
        "target": target,
        "sequence": steps,
        "observed_failing": proven,
        "detail": detail,
        "reason": reason,
        "attested": "ran" if proven else "blocked",
        "record": record["sequence"],
    }


def attested_rule_ids(archive: Chronicle, session: str) -> set[str]:
    covered: set[str] = set()
    for record in archive.select(kind="attestation", limit=1000):
        data = record["data"]
        if data.get("session") != session:
            continue
        if data.get("status") in ("ran", "empty"):
            covered.update(data.get("rule_ids", []))
    return covered


def gate(archive: Chronicle, session: str, charter: dict[str, Any], trigger: str) -> Verdict:
    """Block when a HARD rule for this trigger has no attestation in this session."""
    covered = attested_rule_ids(archive, session)
    missing = tuple(
        {"id": rule["id"], "text": rule["text"], "source": rule["source"], "verify": rule["verify"]}
        for rule in charter["compiled"]
        if rule["trigger"] == trigger
        and rule["enforcement"] == "HARD"
        and rule["id"] not in covered
    )
    return Verdict(allowed=not missing, trigger=trigger, missing=missing)


# Words too common to corroborate anything. A claim whose only overlap with the
# cited line is "the" has not been corroborated.
_STOPWORDS = frozenset("""
about after all also and any are because been before being both but can cannot did
does doing done during each either else every for from had has have how into its
itself just like made make many may might more most must never new non not now off
once only other our out over own same should since some such than that the their
them then there these they this those through too under until use used using very
was were what when where which while who why will with within would your
""".split())

# How far either side of a cited line a supporting term may sit. A claim usually
# refers to a small region rather than one exact line, but not to a whole file.
POSITION_WINDOW = 3


def _salient(text: str) -> set[str]:
    """Distinctive terms, with identifiers split into their parts.

    Prose says "the widget renders" where code says `render_widget`. Comparing the
    two as whole tokens finds no overlap and reports a correct citation as drifted,
    so identifiers contribute both their whole form and their parts, and a crude
    plural stem closes the rest of the gap.
    """
    found: set[str] = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        parts = [token] + re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", token)
        for part in parts:
            lowered = part.lower()
            if len(lowered) < 4 or lowered in _STOPWORDS:
                continue
            found.add(lowered)
            if lowered.endswith("s") and len(lowered) > 4:
                found.add(lowered[:-1])
    return found


def _position_support(project: Path, citation: str, claim: str) -> str | None:
    """Does the cited line actually say anything the claim is about?

    A citation that resolves proves the location exists; it does not prove the
    location is the right one. Reported positions drifting off target while still
    pointing at real lines is a documented failure of agent-produced findings, and
    it is undetectable by checking existence alone.

    Returns "corroborated", "unsupported", or None when no honest judgement is
    possible - a claim with no distinctive terms cannot be corroborated or refuted,
    and guessing either way would be worse than abstaining.
    """
    match = _FILE_CITE.match(citation)
    if not match or match.group("start") is None:
        return None
    terms = _salient(claim)
    if not terms:
        return None
    target = project / match.group("path")
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    low = max(0, start - 1 - POSITION_WINDOW)
    high = min(len(lines), end + POSITION_WINDOW)
    window = _salient(" ".join(lines[low:high]))
    return "corroborated" if terms & window else "unsupported"


def _citation_resolves(project: Path, archive: Chronicle, citation: str) -> bool:
    if citation.startswith("cmd:"):
        # A command citation resolves when some attestation records having run it.
        # Anyone can write the words; only a run leaves the record.
        return any(
            citation in record.get("evidence", [])
            for record in archive.select(kind="attestation", limit=500)
        )
    match = _RECORD_CITE.match(citation)
    if match:
        digest = match.group("digest")
        # A claim cannot support a claim: citing one's own earlier hypothesis
        # would launder confidence - each hop looks locally justified while the
        # chain rests on nothing. rec: support must come from primary records.
        return any(
            record["record_hash"].startswith(digest) and record["kind"] != "claim"
            for record in archive.select(limit=2000)
        )
    match = _FILE_CITE.match(citation)
    if match:
        target = project / match.group("path")
        if not target.is_file():
            return False
        start = match.group("start")
        if start is None:
            return True
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return False
        return 1 <= int(start) <= len(lines)
    # A source outside the worktree is the operator's assertion that they read
    # it. Nothing local can confirm that, and confirming it over the network is
    # not something this runtime does - so it resolves as a declaration and the
    # claim carries a marker saying the evidence was asserted rather than
    # checked. Without this the external gate was unsatisfiable: it demanded a
    # `doc:` or `url:` citation and then rejected every one of them, so a claim
    # about the outside world could never be recorded as verified whatever the
    # author had actually read.
    if citation.startswith(("doc:", "url:")):
        return _is_plausible_source_reference(citation.split(":", 1)[1])
    return False


# What the operator asserts they read has to look like a reference to something.
# Accepting any non-empty remainder let a fuzzed citation of control characters
# and encoded traversal earn a verified grade - garbage is not an assertion, and
# a gate that accepts it is worse than one that accepts nothing, because it
# reports confidence it never had.
_PLAUSIBLE_REFERENCE = re.compile(r"^[^\x00-\x1f\x7f]{4,512}$")
_ENCODED_TRAVERSAL = re.compile(r"(?i)%2e%2e|\.\.[/\\]")


def _is_plausible_source_reference(reference: str) -> bool:
    reference = reference.strip()
    if not _PLAUSIBLE_REFERENCE.fullmatch(reference):
        return False
    if _ENCODED_TRAVERSAL.search(reference):
        return False
    # At least one readable word, so a string of punctuation cannot pass as the
    # name of a document somebody opened.
    return re.search(r"[A-Za-z0-9]{3,}", reference) is not None


def known_citations(archive: Chronicle, limit: int = 500) -> list[str]:
    """Every citation string the archive has actually stored."""
    found: set[str] = set()
    for record in archive.select(kind="attestation", limit=limit):
        found.update(record.get("evidence", []))
    return sorted(found)


def near_miss(citation: str, candidates: list[str], floor: float = 0.6) -> str | None:
    """The stored citation a failed one most likely meant.

    A citation that nearly matches something real is almost always a formatting
    guess, not an invention - and the two are indistinguishable in a bare "does not
    resolve". Naming the near miss turns an unhelpful refusal into a correction,
    while an invention still matches nothing and stays refused.
    """
    from difflib import SequenceMatcher

    best, score = None, floor
    for candidate in candidates:
        ratio = SequenceMatcher(None, citation, candidate).ratio()
        if ratio > score:
            best, score = candidate, ratio
    return best


# A claim about the outside world, recognised without being declared.
#
# The external check already existed and already worked; it simply only ran
# when the caller passed the flag, so it protected whoever remembered they were
# talking about a remote system. The seed case was an assertion that a pinned
# action version did not exist - stated from recall, wrong, and caught only
# because a human checked. No flag was passed, because it did not feel like a
# claim about anything remote. It was one.
#
# Narrow on purpose. A detector that fires on ordinary local statements teaches
# the operator to route around it, so this names third-party artefacts and
# version behaviour and nothing else.
_THIRD_PARTY_PIN = re.compile(
    r"(?i)\b[\w.-]+/[\w.-]+@v?\d"        # org/repo@v7 - an action or package pin
    r"|\b[\w.-]{2,}@\d+(?:\.\d+)*\b"     # react@19
)
_VERSION_BEHAVIOUR = re.compile(
    r"(?i)\b(?:latest|newest|current)\s+(?:stable\s+)?version\s+of\b"
    r"|\b[A-Z][\w.+-]*\s+\d+(?:\.\d+)*\s+(?:supports?|introduced|added|"
    r"removed|dropped|deprecat\w+|requires?|is\s+(?:not\s+)?(?:yet\s+)?"
    r"released)\b"
    r"|\b(?:was|were)\s+(?:removed|added|introduced|deprecated)\s+in\s+"
    r"[A-Z][\w.+-]*\s*\d"
)


def looks_external(text: str) -> tuple[bool, str]:
    """Whether a claim asserts something about a system outside this worktree.

    Returns the verdict and what triggered it, so a downgrade can say why
    rather than leaving the author to guess which words tripped it.
    """
    match = _THIRD_PARTY_PIN.search(text)
    if match:
        return True, f"names a third-party artefact at a pinned version: {match.group(0)}"
    match = _VERSION_BEHAVIOUR.search(text)
    if match:
        return True, f"asserts what a released version does: {match.group(0)}"
    return False, ""


def record_claim(
    archive: Chronicle,
    project: Path,
    session: str,
    text: str,
    grade: str,
    cites: list[str] | None = None,
    external: bool = False,
) -> dict[str, Any]:
    """Persist a claim, downgrading it when its citations do not resolve.

    Not a warning. A claim the evidence does not support is stored as a hypothesis,
    because a claim asserted at full confidence is what a later session will trust.

    A claim about an external API or library (`external=True`) must cite a
    primary source read this session (`doc:` or `url:` citation) - memory of a
    library is a hypothesis about a version that may no longer exist.
    """
    if grade not in GRADES:
        raise ArchiveError(f"Unknown claim grade '{grade}'; expected one of {', '.join(GRADES)}")
    citations = cites or []
    # Detected as well as declared: the check protected whoever remembered to
    # pass the flag, which is not the person who needs it.
    if not external and grade == "verified":
        external, _reason = looks_external(text)
    if external and grade == "verified":
        primary = [c for c in citations if c.startswith(("doc:", "url:"))]
        if not primary:
            record = archive.append(
                "claim", text[:120],
                {"text": text, "grade": "hypothesis", "requested": grade, "session": session,
                 "downgraded": True, "unresolved": [],
                 "reason": "external claim without a primary source read this session; "
                           "cite doc:<path> or url:<address> from a source actually opened"},
                evidence=citations,
            )
            return record
    unresolved = [
        citation for citation in citations if not _citation_resolves(project, archive, citation)
    ]
    # A citation can resolve and still point at the wrong place. Existence and
    # support are separate claims, so they are checked separately.
    unsupported = [
        citation
        for citation in citations
        if citation not in unresolved
        and _position_support(project, citation, text) == "unsupported"
    ]
    effective = grade
    reason = ""
    absence = is_absence_claim(text)
    if grade == "verified":
        if not citations:
            effective, reason = "hypothesis", "no citation"
        elif unresolved:
            effective, reason = "hypothesis", "citation does not resolve"
            suggestion = near_miss(unresolved[0], known_citations(archive))
            if suggestion:
                reason += f"; did you mean {suggestion!r}"
        elif absence and not _cites_a_search(archive, citations):
            # "No X exists" cannot be shown by pointing at somewhere X is not. Without
            # the search that would have found X, the claim cannot be wrong - and a
            # claim nothing could falsify is not verified, it is merely unchallenged.
            effective, reason = (
                "hypothesis",
                "absence claim cites no search that would have found a counter-example",
            )
        elif unsupported:
            effective, reason = "hypothesis", "cited location does not support the claim"
    record = archive.append(
        "claim",
        text[:120],
        {
            "session": session,
            "text": text,
            "claimed_grade": grade,
            "grade": effective,
            "unresolved": unresolved,
            "unsupported": unsupported,
            "downgraded": effective != grade,
            "reason": reason,
            # Named rather than implied: a later reader can see which part of
            # the support was machine-checked and which was taken on the
            # author's word, instead of reading one uniform "verified".
            "operator_asserted": [
                citation for citation in citations
                if citation.startswith(("doc:", "url:"))
            ],
        },
        evidence=citations,
    )
    return record


_NEGATION = re.compile(
    r"\b(?:not|never|no longer|cannot|can't|doesn't|does not|isn't|is not|"
    r"won't|will not|without|disabled|removed|absent|missing|fails?)\b"
)


def reflect(archive: Chronicle, text: str, limit: int = 200) -> dict[str, Any]:
    """Check a new claim against what the record already says.

    Run as its own step rather than folded into producing the claim, for the same
    reason a review is not done by the author: the pass that generates an assertion
    is the pass least able to notice it contradicts something.

    This flags, it does not decide. Polarity disagreement between two claims about
    the same subject is a lead worth a human look, and calling it a contradiction
    outright would manufacture findings.
    """
    terms = _salient(text)
    if not terms:
        return {"checked": 0, "conflicts": [], "note": "claim has no distinctive terms to compare"}

    polarity = bool(_NEGATION.search(text.lower()))
    conflicts: list[dict[str, Any]] = []
    checked = 0
    for record in archive.select(kind="claim", limit=limit):
        data = record["data"]
        prior = str(data.get("text", ""))
        if not prior or prior == text:
            continue
        checked += 1
        overlap = terms & _salient(prior)
        # Two distinctive terms in common means the claims are about the same thing;
        # one is coincidence in prose this short.
        if len(overlap) < 2:
            continue
        if bool(_NEGATION.search(prior.lower())) != polarity:
            conflicts.append({
                "prior": prior[:160],
                "prior_grade": data.get("grade"),
                "shared_terms": sorted(overlap)[:6],
                "why": "the two claims share a subject but disagree in polarity",
            })
    return {
        "checked": checked,
        "conflicts": conflicts[:5],
        "verdict": "conflict-suspected" if conflicts else "no-conflict-found",
    }


# Claims that assert something is not there. Pointing at a file proves presence;
# absence is only ever proved by a search that would have found it.
_ABSENCE = re.compile(
    r"\b(?:no|zero|none|never|without|nothing|absent|free of|clean of)\b"
    r"|\bnot? (?:present|found|used|imported|referenced|reachable)\b"
    r"|\bdoes not (?:exist|contain|appear|reference)\b"
)


def is_absence_claim(text: str) -> bool:
    return bool(_ABSENCE.search(text.lower()))


def _cites_a_search(archive: Chronicle, citations: list[str]) -> bool:
    """Whether any citation points at something that actually looked.

    A `cmd:` citation is a command that ran. A `rec:` citation may resolve to an
    attestation, which is a record of a step having been performed. A `file:`
    citation is neither: it shows one place the thing is not, which says nothing
    about everywhere else.
    """
    for citation in citations:
        if citation.startswith("cmd:"):
            return True
        match = _RECORD_CITE.match(citation)
        if not match:
            continue
        digest = match.group("digest")
        for record in archive.select(kind="attestation", limit=500):
            if record["record_hash"].startswith(digest):
                return True
    return False


def recurrences(archive: Chronicle, limit: int = 500) -> dict[str, Any]:
    """Find blocks that happened more than once for the same reason.

    A control firing twice on the same cause is a different signal from it firing
    once. The first time is the control working; the second is evidence that
    understanding the rule did not install it, and that something upstream - a
    template, a habit, a missing default - keeps reproducing the violation.
    """
    seen: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in archive.select(kind="attestation", limit=limit):
        data = record["data"]
        if data.get("status") != "blocked":
            continue
        cause = (data.get("reason") or data.get("result") or "")[:80]
        key = (record["subject"], cause)
        seen.setdefault(key, []).append({
            "sequence": record["sequence"],
            "session": data.get("session"),
            "agent": (data.get("agent") or {}).get("model", "unknown"),
        })

    repeated = [
        {
            "step": step,
            "cause": cause,
            "occurrences": len(events),
            "sessions": sorted({e["session"] for e in events if e["session"]}),
            "agents": sorted({e["agent"] for e in events}),
            "why_it_matters": (
                "the same control blocked the same cause more than once; the rule was "
                "understood and violated again, so the fix belongs upstream of the block"
            ),
        }
        for (step, cause), events in sorted(seen.items())
        if len(events) > 1
    ]
    return {
        "checked": sum(len(v) for v in seen.values()),
        "recurrences": repeated,
        "count": len(repeated),
        "verdict": "recurrence-detected" if repeated else "no-recurrence",
    }


def close_session(archive: Chronicle, session: str, charter: dict[str, Any]) -> dict[str, Any]:
    """Refuse closure while any HARD rule is unattested or any claim is unsupported."""
    covered = attested_rule_ids(archive, session)
    unattested = [
        {"id": rule["id"], "text": rule["text"], "trigger": rule["trigger"]}
        for rule in charter["compiled"]
        if rule["enforcement"] == "HARD" and rule["id"] not in covered
    ]
    downgraded = [
        {"text": record["data"]["text"], "unresolved": record["data"]["unresolved"]}
        for record in archive.select(kind="claim", limit=500)
        if record["data"].get("session") == session and record["data"].get("downgraded")
    ]
    half_done = half_done_pairs(archive, session, charter)
    allowed = not unattested and not downgraded and not half_done
    verdict: dict[str, Any] = {
        "session": session,
        "closed": allowed,
        "unattested_hard_rules": unattested,
        "downgraded_claims": downgraded,
        "half_done_pairs": half_done,
        "watch_for": [] if allowed else [text for text, _ in RATIONALIZATIONS],
    }
    if allowed and not charter.get("compiled"):
        # A closure no rule could have blocked is not the same as a clean one.
        verdict["detail"] = ("closed with 0 compiled rules - nothing could have "
                             "blocked; write GODMODE.md directives so this gate means something")
    return verdict


def half_done_pairs(
    archive: Chronicle, session: str, charter: dict[str, Any]
) -> list[dict[str, Any]]:
    """A pair rule attested with one artefact is half a ritual, and blocks closure.

    The attestation for a `pair_complete` rule must cite at least two `file:`
    artefacts - the thing and its counterpart. One citation names exactly which
    half moved alone.
    """
    pair_rules = {
        rule["id"]: rule["text"]
        for rule in charter.get("compiled", [])
        if rule.get("verify") == "pair_complete"
    }
    if not pair_rules:
        return []
    findings: list[dict[str, Any]] = []
    for record in archive.select(kind="attestation", limit=1000):
        data = record["data"]
        if data.get("session") != session or data.get("status") != "ran":
            continue
        cited_rules = [r for r in data.get("rule_ids") or [] if r in pair_rules]
        if not cited_rules:
            continue
        files = [e for e in record.get("evidence", []) if e.startswith("file:")]
        if len(files) < 2:
            findings.append({
                "rule": cited_rules[0],
                "text": pair_rules[cited_rules[0]],
                "moved_alone": files[0] if files else "(no artefact cited)",
                "missing": "the paired artefact was never cited",
            })
    return findings


# §15.2: the only order in which confidence about a finding may grow. Each
# step names what was added — a corroborating signal, a root cause, a local
# fix, a verification — so skipping a rung means asserting work never done.
EVIDENCE_LEVELS = (
    "observation", "hypothesis", "corroborated", "rooted",
    "fixed-locally", "verified", "closed",
)


def record_lesson_scoped(
    archive: Chronicle,
    subject: str,
    value: Any,
    *,
    project_tag: str,
    surface: str = "",
    framework: str = "",
    confidence: str = "observed",
    guard: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    """§21.1: a lesson tagged with where it was learned, so it cannot leak.

    A lesson recorded in one project and replayed verbatim in another is
    cross-project contamination: "always mock the payment client" is wisdom in
    the repo with a payment client and noise everywhere else. The tag is
    mandatory because an untagged lesson is exactly the kind that leaks; a
    lesson meant to travel must say so explicitly with portable=True, never by
    omission.
    """
    if not str(project_tag).strip():
        raise ArchiveError(
            "A scoped lesson requires a non-empty project_tag; an untagged lesson "
            "is the cross-project leak this scoping exists to stop"
        )
    return archive.append(
        "lesson",
        subject,
        {
            "value": value,
            "project_tag": str(project_tag).strip(),
            "surface": surface,
            "framework": framework,
            "confidence": confidence,
            "guard": guard,
            "portable": False,
        },
        evidence=evidence or [],
    )


def lessons_for(archive: Chronicle, project_tag: str) -> list[dict[str, Any]]:
    """Lessons that legitimately apply here: this project's, or marked portable.

    Filtering happens at read time rather than write time because the writer
    cannot know every future reader; only the reader knows which project it is
    standing in. A lesson with a foreign tag and no explicit portable=True is
    excluded even if it looks universally useful — usefulness is exactly the
    judgement portable exists to record.
    """
    tag = str(project_tag).strip()
    return [
        record
        for record in archive.select(kind="lesson", limit=500)
        if record["data"].get("portable") is True
        or record["data"].get("project_tag") == tag
    ]


def advance_evidence(
    archive: Chronicle,
    subject: str,
    level: str,
    evidence: str | list[str],
    *,
    reason: str = "",
) -> dict[str, Any]:
    """§15.2: move a subject along the evidence ladder one rung at a time.

    Confidence that jumps from observation to verified has skipped the steps
    where it could have been proven wrong, which is how a hunch gets stored
    wearing a certainty it never earned. The current rung is read from the
    archive rather than trusted from the caller, so the ladder cannot be
    climbed by assertion. Downward is always open — reality demoting a finding
    must never be blocked — but it must carry a reason, because an unexplained
    demotion erases history instead of correcting it.
    """
    if level not in EVIDENCE_LEVELS:
        raise ArchiveError(
            f"Unknown evidence level '{level}'; expected one of {', '.join(EVIDENCE_LEVELS)}"
        )
    prior = [
        record
        for record in archive.select(subject=subject, limit=500)
        if record["data"].get("evidence_level") in EVIDENCE_LEVELS
    ]
    current = prior[-1]["data"]["evidence_level"] if prior else EVIDENCE_LEVELS[0]
    current_index = EVIDENCE_LEVELS.index(current)
    new_index = EVIDENCE_LEVELS.index(level)
    if new_index - current_index > 1:
        skipped = ", ".join(EVIDENCE_LEVELS[current_index + 1:new_index])
        raise ArchiveError(
            f"Evidence for '{subject}' is at '{current}'; jumping to '{level}' skips "
            f"{skipped}. Record each intermediate level with its own evidence first."
        )
    if new_index < current_index and not reason.strip():
        raise ArchiveError(
            "Demoting evidence is always allowed but requires a reason; an "
            "unexplained demotion erases history instead of correcting it"
        )
    citations = [evidence] if isinstance(evidence, str) else list(evidence or [])
    direction = (
        "down" if new_index < current_index
        else "up" if new_index > current_index
        else "same"
    )
    return archive.append(
        "claim",
        subject,
        {
            "evidence_level": level,
            "previous_level": current,
            "direction": direction,
            "reason": reason,
        },
        evidence=citations,
    )


def lesson_pipeline(archive: Chronicle) -> dict[str, Any]:
    """S27-02: a lesson either becomes an executable guard or is retired.

    The 237-lesson corpus failed by unbounded append: every lesson stayed prose
    forever, so none was enforced and all were re-read. Here each lesson gets a
    verdict - `promoted` when its guard has been observed running, otherwise
    `promote-or-retire` with the exact next command.
    """
    guarded_files: set[str] = set()
    for record in archive.select(kind="attestation", limit=1000):
        if record["subject"].startswith("guard:") and record["data"].get("status") == "ran":
            guarded_files.update(
                e[len("file:"):] for e in record.get("evidence", []) if e.startswith("file:"))
    lessons = []
    unresolved = 0
    for record in archive.select(kind="lesson", limit=500):
        if record["data"].get("status") == "retired":
            continue
        cited = {e[len("file:"):] for e in record.get("evidence", []) if e.startswith("file:")}
        promoted = bool(record["data"].get("generalized_guard")) and bool(cited & guarded_files)
        if not promoted:
            unresolved += 1
        lessons.append({
            "subject": record["subject"][:80],
            "sequence": record["sequence"],
            "verdict": "promoted" if promoted else "promote-or-retire",
            "next": None if promoted else (
                "plant a violation so its guard is observed failing, or retire it with "
                f"`remember --kind lesson --subject \"{record['subject'][:50]}\" --status retired`"),
        })
    return {
        "lessons": lessons,
        "promoted": sum(1 for l in lessons if l["verdict"] == "promoted"),
        "unresolved": unresolved,
        "verdict": "pipeline-clear" if unresolved == 0 else "lessons-awaiting-promotion",
        "note": "a lesson that stays prose forever is re-read forever and enforced never",
    }


def advisory_decay(
    archive: Chronicle, charter: dict[str, Any], window: int = 10
) -> dict[str, Any]:
    """Rules no session has touched in the last `window` sessions, surfaced.

    A rule that never fires is either dead weight or an unenforced promise;
    both deserve a decision, not accumulation.
    """
    sessions = [f"S-{r['record_hash'][:12]}" for r in archive.select(kind="session", limit=500)
                if r["data"].get("state") == "open"]
    recent = set(sessions[-window:])
    seen: dict[str, set[str]] = {}
    for record in archive.select(kind="attestation", limit=1000):
        data = record["data"]
        if data.get("session") in recent:
            for rule_id in data.get("rule_ids") or []:
                seen.setdefault(rule_id, set()).add(data["session"])
    dormant = [
        {"id": rule["id"], "text": rule["text"], "enforcement": rule["enforcement"]}
        for rule in charter.get("compiled", [])
        if rule["id"] not in seen
    ]
    return {
        "window_sessions": len(recent),
        "rules_total": len(charter.get("compiled", [])),
        "rules_dormant": len(dormant),
        "dormant": dormant[:50],
        "note": "dormant rules deserve retirement or promotion, not accumulation",
    }


def _self_check() -> None:
    import tempfile
    from unittest import mock

    from .godmode_anchor import resolve_anchor
    from .godmode_charter import compile_charter

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        (project / "GODMODE.md").write_text(
            "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            charter = compile_charter(project)
            session = open_session(archive, "self-check")

            hard = [r for r in charter["compiled"] if r["enforcement"] == "HARD"]
            assert hard, charter["enforcement"]
            trigger = hard[0]["trigger"]

            # Unattested HARD rule blocks its gate and names the rationalizations.
            blocked = gate(archive, session, charter, trigger)
            assert not blocked.allowed
            assert blocked.view()["watch_for"]

            # A skip must state a reason; a bare skip is refused outright.
            try:
                record_step(archive, session, "preflight", "skipped")
                raise AssertionError("a reasonless skip must be refused")
            except ArchiveError:
                pass

            # An attested step opens the gate. 'empty' counts: finding nothing is a finding.
            record_step(archive, session, "preflight", "empty",
                        result="no overlapping invariant", rule_ids=[hard[0]["id"]])
            assert gate(archive, session, charter, trigger).allowed

            # A claim citing nothing cannot be 'verified'.
            bare = record_claim(archive, project, session, "The retry path is disabled.", "verified")
            assert bare["data"]["grade"] == "hypothesis", bare["data"]

            # A claim whose cited line actually mentions it stays verified.
            good = record_claim(archive, project, session,
                                "Commit requires an explicit ask.", "verified",
                                cites=["file:GODMODE.md#L2"])
            assert good["data"]["grade"] == "verified", good["data"]

            # A claim whose citation resolves but points somewhere unrelated is
            # downgraded: existence is not support, and drifted positions are the
            # documented failure mode of agent-reported findings.
            (project / "rotate.py").write_text(
                "def rotate():\n    return 1\n\n\ndef unrelated():\n    return 2\n",
                encoding="utf-8",
            )
            drifted = record_claim(archive, project, session,
                                   "Retention policy expires audit rows after ninety days.",
                                   "verified", cites=["file:rotate.py#L5"])
            assert drifted["data"]["grade"] == "hypothesis", drifted["data"]
            assert drifted["data"]["unsupported"] == ["file:rotate.py#L5"], drifted["data"]
            assert "does not support" in drifted["data"]["reason"], drifted["data"]

            # And one that lands on the right line survives.
            landed = record_claim(archive, project, session,
                                  "The rotate function returns a value.", "verified",
                                  cites=["file:rotate.py#L1"])
            assert landed["data"]["grade"] == "verified", landed["data"]

            # A claim citing a missing file is downgraded and blocks closure.
            record_claim(archive, project, session, "The absent module is wired.", "verified",
                         cites=["file:nope.py#L1"])
            verdict = close_session(archive, session, charter)
            assert not verdict["closed"]
            assert verdict["downgraded_claims"]

            # A failing check cannot be attested into a pass: the runner records the
            # exit code, and 'blocked' never satisfies a gate.
            # Distinct ids, because a rule already attested earlier in this check
            # would make the coverage assertions pass for the wrong reason.
            failed_rule, passed_rule = "R-checkfail", "R-checkpass"
            failing = run_check(archive, session, project, "failing",
                                [sys.executable, "-c", "raise SystemExit(3)"],
                                rule_ids=[failed_rule])
            assert failing["exit_code"] == 3 and not failing["passed"], failing
            assert failing["attested"] == "blocked", failing
            assert failed_rule not in attested_rule_ids(archive, session), \
                "a failed check satisfied the rule it was run for"

            passing = run_check(archive, session, project, "passing",
                                [sys.executable, "-c", "print('ok')"], rule_ids=[passed_rule])
            assert passing["passed"] and passing["attested"] == "ran", passing
            assert passed_rule in attested_rule_ids(archive, session), \
                "a passing check did not satisfy its rule"

            missing = run_check(archive, session, project, "absent",
                                ["definitely-not-a-real-binary-xyz"])
            assert missing["exit_code"] == 127 and not missing["passed"], missing

            # A guard must be seen failing. A real guard goes green -> red -> green.
            (project / "value.txt").write_text("42\n", encoding="utf-8")
            real_guard = [sys.executable, "-c",
                          "import pathlib,sys; sys.exit(0 if pathlib.Path('value.txt')"
                          ".read_text().strip()=='42' else 1)"]
            proven = plant_and_observe(archive, session, project, "value", real_guard,
                                       target="value.txt", replace="42", with_text="99",
                                       rule_ids=["R-guard"])
            assert proven["observed_failing"], proven
            assert proven["sequence"]["baseline"] == 0 and proven["sequence"]["with_violation"] != 0
            assert "R-guard" in attested_rule_ids(archive, session)
            # The file is byte-identical afterwards; a plant must never leak.
            assert (project / "value.txt").read_text(encoding="utf-8") == "42\n"

            # A guard that asserts nothing stays green under the plant and is refused.
            hollow = [sys.executable, "-c", "raise SystemExit(0)"]
            weak = plant_and_observe(archive, session, project, "hollow", hollow,
                                     target="value.txt", replace="42", with_text="99",
                                     rule_ids=["R-hollow"])
            assert not weak["observed_failing"], weak
            assert "did not fail" in weak["reason"], weak
            assert "R-hollow" not in attested_rule_ids(archive, session)

            # A plant that changes nothing is refused rather than read as a pass.
            try:
                plant_and_observe(archive, session, project, "noop", real_guard,
                                  target="value.txt", replace="absent-token", with_text="x")
                raise AssertionError("a no-op plant must be refused")
            except ArchiveError as exc:
                assert "changed no bytes" in str(exc), exc

            # An absence claim needs the search that would have found a counter-example.
            assert is_absence_claim("The runtime has no network dependencies.")
            assert not is_absence_claim("The rotate function returns a value.")

            pointing = record_claim(archive, project, session,
                                    "There are no secrets in the archive.", "verified",
                                    cites=["file:GODMODE.md#L2"])
            assert pointing["data"]["grade"] == "hypothesis", pointing["data"]
            assert "absence claim" in pointing["data"]["reason"], pointing["data"]

            sweep = [sys.executable, "-c", "print('swept')"]
            swept = run_check(archive, session, project, "secret-sweep", sweep)
            # Cite what was stored, rather than rebuilding the string and guessing
            # its normalisation.
            searching = record_claim(archive, project, session,
                                     "There are no secrets in the archive.", "verified",
                                     cites=[swept["citation"]])
            assert searching["data"]["grade"] == "verified", searching["data"]

            # A near miss is corrected rather than merely refused, because a
            # formatting guess and an invention read identically otherwise.
            mistyped = record_claim(archive, project, session,
                                    "There are no secrets in the archive.", "verified",
                                    cites=[swept["citation"].replace("-c ", "-c  ")])
            assert mistyped["data"]["grade"] == "hypothesis", mistyped["data"]
            assert "did you mean" in mistyped["data"]["reason"], mistyped["data"]

            fabricated = record_claim(archive, project, session,
                                      "There are no orphans.", "verified",
                                      cites=["cmd:entirely-unlike-anything-recorded"])
            assert "did you mean" not in fabricated["data"]["reason"], fabricated["data"]

            # A command nobody ran cites nothing: the words are not the evidence.
            invented = record_claim(archive, project, session,
                                    "There are no orphaned records.", "verified",
                                    cites=["cmd:a-sweep-that-never-ran"])
            assert invented["data"]["grade"] == "hypothesis", invented["data"]

            # A control that blocked twice on the same cause is a recurrence, not noise.
            for _ in range(2):
                record_step(archive, session, "guard:url-literal", "blocked",
                            result="url literal in fixture", reason="url literal in fixture")
            repeats = recurrences(archive)
            assert repeats["verdict"] == "recurrence-detected", repeats
            assert repeats["recurrences"][0]["occurrences"] >= 2, repeats

            # Reflection notices that a new claim disagrees with a recorded one.
            record_claim(archive, project, session,
                         "The rotation guard is enabled for every account.", "observed")
            echo = reflect(archive, "The rotation guard is not enabled for every account.")
            assert echo["verdict"] == "conflict-suspected", echo
            assert echo["conflicts"][0]["shared_terms"], echo

            # Agreement is not flagged, and neither is an unrelated subject.
            assert reflect(archive, "The rotation guard is enabled for every account today."
                           )["verdict"] == "no-conflict-found"
            assert reflect(archive, "Billing exports run nightly.")["verdict"] == "no-conflict-found"

    print("godmode_attest self-check OK")


if __name__ == "__main__":
    _self_check()
