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
import posixpath
import sys
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
from .godmode_session_log import command_digest

STATUSES = ("ran", "empty", "skipped", "blocked")
GRADES = ("observed", "hypothesis", "verified", "unknown")
# PARTIAL-P2/B3-4: closed vocabulary a claim may opt into via `blast_radius`.
# Closed on purpose - an open string field would let every claim invent its
# own severity label, which is not a bar anyone could size a check against.
# Named for the shape of what a wrong "verified" costs, not the domain:
# an action that reaches outside this worktree, a side effect that persists
# past the session that caused it, or a guard whose entire job is to detect
# byte-level tampering.
BLAST_RADIUS_KINDS = ("ops-directed", "sticky-side-effect", "checksum-guard")
# The independent-witness floor every `blast_radius` value shares in v1 - see
# `_independent_witness_count`'s docstring for what "independent" means here.
_BLAST_RADIUS_MIN_WITNESSES = 2

_FILE_CITE = re.compile(r"^file:(?P<path>[^#]+)(?:#L(?P<start>\d+)(?:-L?(?P<end>\d+))?)?$")
_RECORD_CITE = re.compile(r"^rec:(?P<digest>[0-9a-f]{6,64})$")
_VERDICT_CITE = re.compile(r"^verdict:(?P<sequence>\d+)$")
# U-E3: what a differential's a_ref/b_ref name when they point at an archived
# state rather than a file or a command, and the differential citation itself.
_SEQ_CITE = re.compile(r"^seq:(?P<sequence>\d+)$")
_DIFF_CITE = re.compile(r"^diff:(?P<sequence>\d+)$")
# U-T3: the one output shape a numeric claim about a registered metric may
# cite - reconstructed as "<name>:<value>" and checked against the metric's
# own registered anchor pattern.
_LINE_CITE = re.compile(r"^line:(?P<name>[^:]+):(?P<value>.+)$")
# The cap `line:`'s value half is held to before it is ever matched against
# an anchor (see `_citation_resolves`'s `line:` handling) - a metric value
# never legitimately needs more than this many characters, and the length
# cap on the anchor itself (`_ANCHOR_MAX_LEN`) bounds the wrong side of the
# match: it says nothing about how long the TEXT matched against it may be.
_MAX_METRIC_VALUE_LEN = 64

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
    # SOFT findings that ride alongside a gate check without affecting
    # `allowed` - currently just the assumption gate (U-S4), below.
    advisories: tuple[str, ...] = ()

    def view(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trigger": self.trigger,
            "allowed": self.allowed,
            "missing": list(self.missing),
        }
        if self.advisories:
            payload["advisories"] = list(self.advisories)
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
    from .godmode_anchor import current_host, host_capabilities, run_git
    from .godmode_hookproof import interception_state
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
    # Field report 2026-08-28: `read` was the literal 0. The line "read 0 of
    # 8 required sources" could never have said anything else, so an agent
    # that quoted it and an agent that obeyed it produced the same number -
    # a counter that cannot move is decoration, and this one was read aloud
    # in a status report and stepped past. A source counts as read when any
    # record in this archive cites it (`file:<path>`), which is the same
    # evidence class every other check here trusts; the unread ones are
    # named, because a count with no list is not actionable.
    from .godmode_sources import required_sources_view

    sources_view = required_sources_view(project, archive)
    sources_total = sources_view["documents"]
    unread = sources_view["unread"]
    sources_read = sources_view["read"]
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
            "read": sources_read,
            "unread": unread[:20],
            "statement": (
                f"read {sources_read} of {sources_total} required sources"
                + (f"; unread: {', '.join(unread[:5])}" if unread else "")
                + ("" if not unread else
                   " - read them before the first mutation, or say which one "
                   "you are proceeding without and why")
            ),
        },
        "enforcement": host_capabilities(
            tool_call_interception=interception_state(archive, current_host()))["controls"],
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

    from .godmode_anchor import run_git

    def _tree_state() -> str:
        return run_git(project, "status", "--porcelain=v1") or ""

    # A check that rewrites the tree reports on a tree that no longer exists.
    # The run is real; the subject moved underneath it, and every later reading
    # of that attestation is about something else.
    before = _tree_state()

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
    # Recorded on the attestation rather than raised: a check that writes is
    # sometimes legitimate, and refusing every one of them is how a gate gets
    # switched off. What must not happen is the result being read later as a
    # statement about the tree that produced it.
    mutated = _tree_state() != before
    citation = f"cmd:{' '.join(command)[:160]}"
    record = record_step(
        archive,
        session,
        f"check:{name}",
        "ran" if passed else "blocked",
        result=(f"exit {code}: {detail}"
                + ("; this check changed the working tree while running, so its "
                   "result describes a tree that no longer exists" if mutated else "")),
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
        "mutated_tree": mutated,
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


def gate(
    archive: Chronicle, session: str, charter: dict[str, Any], trigger: str,
    timeline: dict[str, Any] | None = None,
) -> Verdict:
    """Block when a HARD rule for this trigger has no attestation in this session.

    `timeline` is optional and only read for `before_approach` (U-S4's
    assumption gate, below); every other trigger ignores it, and its
    absence never blocks anything - a SOFT advisory degrades to silent
    when the instrument that would confirm it is not available.
    """
    covered = attested_rule_ids(archive, session)
    missing = tuple(
        {"id": rule["id"], "text": rule["text"], "source": rule["source"], "verify": rule["verify"]}
        for rule in charter["compiled"]
        if rule["trigger"] == trigger
        and rule["enforcement"] == "HARD"
        and rule["id"] not in covered
    )
    advisories: tuple[str, ...] = ()
    if trigger == "before_approach":
        note = assumption_gate(archive, session, timeline)
        if note:
            advisories = (note,)
    return Verdict(allowed=not missing, trigger=trigger, missing=missing, advisories=advisories)


# U-S4 assumption gate [E4]. R3+ tier proxy: fix-vocabulary claims + Edit/Write
# mutation turns stand in for sentinel risk tiers (out of scope here) - the
# same proxy U-T2's temporal check and `record_criterion`'s late-ordering
# check already use (see their comments above); reused rather than reinvented
# so "R3+ work happened this session" means the same thing everywhere it is
# asked. Known gap carried forward unchanged: non-file-mutating R3+ commands
# (`git branch -D`) are not counted as mutations.
ASSUMPTION_GATE_ADVISORY = "state assumptions or state that there are none"


def assumption_gate(
    archive: Chronicle, session: str, timeline: dict[str, Any] | None = None,
) -> str | None:
    """The advisory once, for a session doing R3+ work with no assumption record.

    Cleared by any `assumption` record on this session - including one whose
    value literally says there were none; the gate asks the question, it does
    not grade the answer. Recomputed fresh from the archive on every call
    (the same idiom `gate()`'s own HARD-rule check already uses), so it reads
    as one standing fact about the session rather than a counter that could
    fall out of sync with it: call it once or a hundred times before the
    first assumption record lands and it names the same session-level gap
    every time, not once per call.
    """
    engaged = bool(timeline is not None and timeline.get("mutation_turns"))
    if not engaged:
        engaged = any(
            record["data"].get("session") == session
            and looks_like_fix_claim(str(record["data"].get("text", "")))[0]
            for record in archive.select(kind="claim", limit=500)
        )
    if not engaged:
        return None
    has_assumption = any(
        record["data"].get("session") == session
        for record in archive.select(kind="assumption", limit=500)
    )
    return None if has_assumption else ASSUMPTION_GATE_ADVISORY


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


def _citation_resolves(project: Path, archive: Chronicle, citation: str,
                       session: str | None = None) -> bool:
    if citation.startswith("cmd:"):
        # A command citation resolves when some attestation records having run it.
        # Anyone can write the words; only a run leaves the record.
        #
        # `session` narrows that to a run from the session making the claim.
        # Without it the record proves the command ran once, at any distance in
        # the past, against a tree that has since changed - which is a memory of
        # having looked, presented as an observation.
        return any(
            citation in record.get("evidence", [])
            and (session is None or record["data"].get("session") == session)
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
    match = _VERDICT_CITE.match(citation)
    if match:
        # Existence is not enough here: a claim standing on a refuted or
        # malformed verdict is the false-claim class this whole mechanism
        # exists to catch, so only a confirmed disposition resolves.
        sequence = int(match.group("sequence"))
        return any(
            record["sequence"] == sequence and record["data"].get("disposition") == "confirmed"
            for record in archive.select(kind="verdict", limit=2000)
        )
    match = _SEQ_CITE.match(citation)
    if match:
        # U-E3: a differential's a_ref/b_ref pointing at an archived state -
        # existence in the chain is enough here; the differential's own
        # record is what vouches for the comparison, this only vouches the
        # state being compared exists.
        sequence = int(match.group("sequence"))
        return any(record["sequence"] == sequence for record in archive.select(limit=2000))
    match = _DIFF_CITE.match(citation)
    if match:
        # U-E3: a differential resolves only when its own record exists AND
        # both sides of the comparison it names also resolve - pointing at
        # one side of a comparison is reading the artefact, not diffing it,
        # so a dangling a_ref/b_ref (or a deleted differential record) must
        # not resolve either.
        sequence = int(match.group("sequence"))
        for record in archive.select(kind="differential", limit=2000):
            if record["sequence"] == sequence:
                data = record["data"]
                return (
                    _citation_resolves(project, archive, str(data.get("a_ref", "")), session)
                    and _citation_resolves(project, archive, str(data.get("b_ref", "")), session)
                )
        return False
    match = _LINE_CITE.match(citation)
    if match:
        # U-T3: resolves only against a metric contract registered for this
        # exact name, and only when the reconstructed "name:value" text
        # matches the anchor that contract declared at registration - an
        # unregistered metric name resolves nothing, by design.
        anchor = _registered_anchor(archive, match.group("name"))
        if anchor is None:
            return False
        value = match.group("value")
        # Layer 2 of 2 against catastrophic backtracking (layer 1 is the
        # registration-time shape refusal in `register_metric_contract`):
        # `value` is an agent-supplied citation string, matched against an
        # anchor at GRADING time - untrusted input reaching a regex the
        # length cap on the anchor itself never bounded. A metric value
        # never legitimately needs more than this many characters, so
        # anything longer is refused outright, before the regex engine
        # ever sees it - holds even for a pattern layer 1's heuristic
        # missed.
        if len(value) > _MAX_METRIC_VALUE_LEN:
            return False
        try:
            return re.match(anchor, f"{match.group('name')}:{value}") is not None
        except re.error:
            return False
    if citation.startswith("criterion:"):
        # U-T2: resolves when a criterion record exists under that exact
        # subject - the citation string and the subject are the same text,
        # so no separate parsing is needed to compare them.
        return any(
            record["subject"] == citation
            for record in archive.select(kind="criterion", limit=500)
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
    # Same reasoning as doc:/url: - nothing local can mechanically confirm a
    # search was exhaustive, a population was fully scanned, or a control
    # probe actually ran; these resolve as the operator's declaration, same
    # plausibility floor. Without this, the mistake-class detectors that
    # read this exact vocabulary (M18 claim-from-a-sample, M21
    # absence-without-control) would teach an operator to cite it, then
    # silently downgrade every claim that did - punishing the evidence
    # discipline the detectors exist to reward.
    if citation.startswith(("searched:", "scanned:", "population:", "control:", "second:")):
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
# A status about a system this runtime cannot see. Reading it costs one call;
# stating it from memory costs the reader their trust in every other line. The
# case that produced this: release state asserted from seventeen-hour-old recall
# while the API sat one call away, already used minutes earlier.
_EXTERNAL_STATUS = re.compile(
    r"(?i)\b(?:ci|the build|the pipeline|the run|the job)\b[^.]{0,30}"
    r"\b(?:is|was|are|passed|failed|green|red|succeeded)\b"
    r"|\b(?:release|tag|package|pull request|branch)\b[^.]{0,30}"
    r"\b(?:is |was |been )?(?:published|merged|released|deployed|live)\b"
    r"|\bpassed on the (?:runner|server|host)\b")

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
    match = _EXTERNAL_STATUS.search(text)
    if match:
        return True, f"states the status of a system this runtime cannot see: {match.group(0)}"
    return False, ""



# A root cause asserted without the differential that confirmed it.
#
# A live project's ledger names this as its highest-frequency error: explaining
# a symptom with the nearest salient anomaly, three times in one day, when the
# decisive evidence was a comparison already in hand. Its own rule - never
# design a remedy on a root the differential has not confirmed - was written
# down and not followed, because a rule an agent must remember is a rule an
# agent in a hurry skips.
#
# So the claim carries the burden instead. A root cause recorded without a
# citation of what was run to confirm it is stored as a hypothesis, whatever
# the author believed when writing it.
_ROOT_CAUSE = re.compile(
    r"(?i)\broot cause\b|\bcaused by\b|\bbecause\b|\bthe reason\b|\bdue to\b"
    r"|\bwhat (?:broke|caused) it\b")


def looks_like_root_cause(text: str) -> tuple[bool, str]:
    """Whether a claim asserts why something happened."""
    match = _ROOT_CAUSE.search(text)
    return (True, f"asserts a cause: {match.group(0)}") if match else (False, "")


# U-E3: differential-evidence detector - diff before theory.
# The rule above fires on any root-cause phrasing; this is the
# more precise instrument it was missing - it only holds a claim to needing
# the *diff* once the archive actually holds two comparable states to diff,
# so a project with nothing to compare yet pays no friction for it.
#
# The vocabulary is a public constant (part of this detector's declared
# interface) rather than folded into `_ROOT_CAUSE`, because the two phrases
# they do not share ("the mechanism", "the root is") are new here and the
# recognizer above stays exactly as it was - callers and tests that already
# depend on `looks_like_root_cause` see no change in what it matches.
ROOT_CAUSE_VOCAB = ("root cause", "the mechanism", "caused by", "the root is")

# Gate v2 learned this the same way for shell vocabulary
# (`godmode_sentinel.split_segments`'s quote-aware tokenizing): a word found
# only inside quoted text or a code span was not said by the speaker, it was
# reported by them. "the user said 'the root cause is y'" is not itself
# asserting a mechanism. The prose variant lives here, beside `_prose`-style
# markdown handling, rather than importing the shell-command tokenizer,
# which parses a different grammar entirely.
_QUOTED_SPAN = re.compile(r"`[^`\n]{0,200}`|\"[^\"\n]{0,200}\"|'[^'\n]{0,200}'")


def _strip_quoted(text: str) -> str:
    return _QUOTED_SPAN.sub(" ", text)


def _asserts_a_cause(text: str) -> tuple[bool, str]:
    """The union of the old recognizer and U-E3's own vocabulary.

    `looks_like_root_cause` itself is left untouched (see the constant's
    docstring above); this is the trigger the differential gate actually
    uses, so a claim written with either vocabulary is held to the same
    comparable-states discipline.
    """
    asserted, why = looks_like_root_cause(text)
    if asserted:
        return asserted, why
    lowered = text.lower()
    for phrase in ROOT_CAUSE_VOCAB:
        if phrase in lowered:
            return True, f"asserts a cause: {phrase}"
    return False, ""


# Record kinds that represent a measured or archived STATE a differential can
# compare - checkpoints, verdicts, metric readings. Deliberately excludes the
# day-to-day bookkeeping kinds (session, attestation, claim, criterion,
# decision...) that would otherwise make nearly every claim look like it had
# two comparable states purely by sharing an archive with them.
_COMPARABLE_KINDS = ("checkpoint", "verdict", "metric")


def _comparable_states(archive: Chronicle, terms: set[str]) -> list[int]:
    """Sequence numbers of recorded states sharing a salient term with the claim."""
    if not terms:
        return []
    found: list[int] = []
    for kind in _COMPARABLE_KINDS:
        for record in archive.select(kind=kind, limit=500):
            if _salient(str(record["subject"])) & terms:
                found.append(record["sequence"])
    return found


def _differential_reason(
    project: Path,
    archive: Chronicle,
    session: str | None,
    text: str,
    citations: list[str],
) -> str | None:
    """U-E3: the downgrade reason when a root-cause claim needs the diff, or
    `None` when the claim should be left alone.

    Fires on root-cause vocabulary found OUTSIDE quotes and code spans, and
    only once the archive holds two or more comparable-state records sharing
    a salient term with the claim - absence of that instrument is a stated
    gap, never a penalty (same discipline as U-T2). Once it fires, a bare
    `cmd:` no longer satisfies it: the claim must cite a RESOLVING `diff:` or
    `verdict:`, naming what was actually compared rather than just that
    something ran.
    """
    stripped = _strip_quoted(text)
    asserted, why = _asserts_a_cause(stripped)
    if not asserted:
        return None
    comparable = sorted(set(_comparable_states(archive, _salient(stripped))))
    if len(comparable) < 2:
        return None
    for citation in citations:
        citation = str(citation)
        if citation.startswith(("diff:", "verdict:")) and _citation_resolves(
            project, archive, citation, session
        ):
            return None
    named = ", ".join(f"seq:{s}" for s in comparable[:2])
    return (
        f"two comparable states exist ({named}) - the root cause claim needs "
        f"the differential that confirmed it ({why}); cite diff:<what you "
        "compared> or verdict:<the confirmed check>, not just that something ran"
    )


_DELTA_MAX_ITEMS = 20
_DELTA_MAX_CHARS = 160


def record_differential(
    archive: Chronicle,
    subject: str,
    a_ref: str,
    b_ref: str,
    delta: list[str],
    method: str,
) -> dict[str, Any]:
    """U-E3: record a comparison of two archived states.

    `a_ref`/`b_ref` are citation strings (`seq:<n>`, `file:<path>`, `cmd:...`)
    naming the two states compared - stored as given, NOT validated to
    resolve here. That is deliberate: a differential recorded against a ref
    that later stops resolving (the state was deleted, the file moved) must
    still be constructible, so `diff:<seq>` citing it can be observed
    failing to resolve rather than the write being refused and the failure
    mode going untested. Neither ref may itself be a `diff:` citation - a
    differential compares two states, not two other differentials, and
    allowing that would open unbounded recursion in `_citation_resolves`.
    """
    subject = subject.strip()
    if not subject:
        raise ArchiveError("A differential needs a non-empty subject")
    a_ref, b_ref = str(a_ref), str(b_ref)
    if not a_ref or not b_ref:
        raise ArchiveError("A differential needs both a_ref and b_ref")
    if a_ref.startswith("diff:") or b_ref.startswith("diff:"):
        raise ArchiveError(
            "A differential's a_ref/b_ref must name an archived state, not another differential"
        )
    if method != "read" and not method.startswith("cmd:"):
        raise ArchiveError("A differential's method must be 'read' or 'cmd:<command>'")
    if len(delta) > _DELTA_MAX_ITEMS:
        raise ArchiveError(
            f"A differential's delta is capped at {_DELTA_MAX_ITEMS} items; got {len(delta)}"
        )
    bounded_delta = [str(item)[:_DELTA_MAX_CHARS] for item in delta]
    data = {
        "subject": subject,
        "a_ref": a_ref,
        "b_ref": b_ref,
        "delta": bounded_delta,
        "method": method,
    }
    return archive.append("differential", subject, data, evidence=[a_ref, b_ref])


# U-T2: a claim that a broken thing now works. Narrow on purpose - the
# red-before-green rule below is a real burden (it demands the cited command
# was actually run failing, not merely cited), and holding every verified
# claim to it would be the over-gating that gets a check switched off. Only
# claims using this vocabulary are held to the temporal shape.
_FIX_VOCAB = re.compile(
    r"(?i)\bfix(?:e[sd]|ing)?\b|\bresolv(?:e[sd]?|ing)\b|\brepair(?:ed|s|ing)?\b"
    r"|\bpatch(?:ed|es|ing)?\b|\bcorrect(?:ed|s|ing)?\b|\bnow pass(?:es|ing)?\b"
    r"|\bbug is (?:fixed|gone)\b"
)


def looks_like_fix_claim(text: str) -> tuple[bool, str]:
    """Whether a claim asserts that something broken now works."""
    match = _FIX_VOCAB.search(text)
    return (True, f"asserts a fix: {match.group(0)}") if match else (False, "")


# E4 R4 / E6 tdd, superpowers-class: a completion claim citing a test command
# is admissible only when the SAME command is observed failing before the
# fix-edit and passing after - the temporal shape, not just the citation.
# One reason text for every way the shape can be missing (green-only,
# red-only, or absent): the point is the missing shape, not which half of it
# is missing.
TEMPORAL_REASON = (
    "cited test was never seen failing (red) before the fix - run it red, "
    "fix, run it green"
)


def _temporal_violation(timeline: dict[str, Any], cmd_citations: list[str]) -> str | None:
    """Whether none of the cited commands show red-before-green.

    Returns the downgrade reason when the shape is missing; `None` when at
    least one cited command was observed failing before the last mutating
    turn and passing after it. A command absent from the timeline entirely
    (never observed running) is treated the same as one with no matching
    outcome - it cannot show a shape it was never seen having.
    """
    commands = timeline.get("commands") or {}
    mutations = timeline.get("mutation_turns") or []
    last_mutation = max(mutations) if mutations else None

    for citation in cmd_citations:
        command_text = str(citation)[len("cmd:"):]
        observations = commands.get(command_digest(command_text), [])
        if not observations:
            continue
        reds = [turn for turn, exit_code in observations if exit_code != 0]
        greens = [turn for turn, exit_code in observations if exit_code == 0]
        if not reds or not greens:
            continue
        if last_mutation is not None:
            if any(r < last_mutation for r in reds) and any(g > last_mutation for g in greens):
                return None
        # No mutation recorded in the timeline at all (unusual for a fix
        # claim, but not this check's business to refuse) - fall back to the
        # ordering the rule is really about: seen failing, then seen passing.
        elif min(reds) < max(greens):
            return None
    return TEMPORAL_REASON


# E4: state what passing looks like before doing the work, so the
# criterion judges the work rather than the work retrofitting the criterion.
_WEAK_VERBS = re.compile(
    r"(?i)\b(?:improve[sd]?|clean(?:ed|s|ing)?(?:\s+up)?|better|nicer"
    r"|enhance[sd]?|polish(?:ed|ing)?)\b"
)

LATE_CRITERION_FINDING = "criterion must precede the work it judges"


# U-T3: anchored-metric contracts. A numeric claim about a registered metric
# must cite an output line matching the anchor declared for it, never a
# paraphrase - and when it does cite one, the value on that line must be the
# number the claim states, or the two are said out loud.
_ANCHOR_MAX_LEN = 200

# A quantified group ((X+), (X*), (X{m,n})) immediately followed by another
# quantifier - (X+)+, (X*)+, (X+)*, (X*)*, and the {m,n} forms - is the
# textbook catastrophic-backtracking shape: the same run of input characters
# can be partitioned between the two quantifiers exponentially many ways
# before the engine gives up, so a short anchor and a short(ish) matched
# value are enough to hang. `re.compile("(a+)+b").match("a" * 28)` on this
# codebase's own interpreter does not return in under 8 seconds - the length
# cap above bounds the ANCHOR's length, which says nothing about that.
#
# This is a text scan for the named shapes, not a full regex parser - it
# will not catch every pathological pattern, but it catches these by name,
# at registration time, before an agent-supplied value is ever matched
# against the anchor. `_MAX_METRIC_VALUE_LEN` (grading time, see
# `_citation_resolves`'s `line:` handling) is the second, independent layer:
# it holds even for a shape this heuristic misses.
_QUANT = r"(?:[+*]|\{\d+,\d*\})"
_CATASTROPHIC_SHAPE = re.compile(r"\((?:[^()]*" + _QUANT + r"[^()]*)\)" + _QUANT)


def _catastrophic_shape(pattern: str) -> str | None:
    """The nested-quantifier substring that risks exponential backtracking."""
    match = _CATASTROPHIC_SHAPE.search(pattern)
    return match.group(0) if match else None


def _registered_anchor(archive: Chronicle, name: str) -> str | None:
    """The anchor most recently registered for `name`, or `None` if never."""
    subject = f"metric-contract:{name}"
    anchor: str | None = None
    for record in archive.select(kind="decision", limit=500):
        if record["subject"] == subject:
            anchor = record["data"].get("anchor")
    return anchor


def _registered_metric_names(archive: Chronicle) -> set[str]:
    return {
        record["subject"][len("metric-contract:"):]
        for record in archive.select(kind="decision", limit=500)
        if record["subject"].startswith("metric-contract:")
    }


def register_metric_contract(
    archive: Chronicle, session: str, name: str, anchor: str
) -> dict[str, Any]:
    """Declare the one output shape a numeric claim about `name` may cite.

    Validated at registration, before the anchor can ever gate a claim, in
    three steps: it must compile as a regex; it is length-capped; and it is
    scanned for the named catastrophic-backtracking shapes (`(X+)+`, `(X*)+`,
    `(X+)*`, `(X*)*`, and the `{m,n}` forms - see `_catastrophic_shape`).
    `re.compile` plus a length cap alone is NOT the whole defense - a review
    round demonstrated `(a+)+b` compiles fine, is well under the length cap,
    and hangs the interpreter once matched against a crafted `line:` value at
    grading time, because the length cap bounds the anchor's own length, not
    the length of the text later matched against it (see
    `_MAX_METRIC_VALUE_LEN`, the second, independent layer against the same
    class of pattern). The shape scan is a heuristic text match, not a full
    regex parser, so this runs once over a short pattern an operator
    declares by hand - not a claim that every pathological pattern is caught.
    """
    name = name.strip()
    if not name:
        raise ArchiveError("A metric contract needs a non-empty name")
    if not anchor or len(anchor) > _ANCHOR_MAX_LEN:
        raise ArchiveError(f"A metric anchor must be 1-{_ANCHOR_MAX_LEN} characters")
    try:
        re.compile(anchor)
    except re.error as exc:
        raise ArchiveError(f"Metric anchor {anchor!r} is not a valid pattern: {exc}") from exc
    shape = _catastrophic_shape(anchor)
    if shape:
        raise ArchiveError(
            f"Metric anchor {anchor!r} contains a nested-quantifier shape "
            f"({shape!r}) that risks catastrophic backtracking - simplify it"
        )
    return archive.append(
        "decision", f"metric-contract:{name}",
        {"anchor": anchor, "session": session},
        evidence=[],
    )


# PARTIAL-P3/B3-7: a declared tool name, used only to test whether it is
# mentioned in a checker command - not a shell identifier, so this stays
# permissive (dots and plus for things like "eslint.config", dashes for
# "media-lint") while still refusing anything empty or absurdly long.
_TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")


def register_error_pattern(
    archive: Chronicle, session: str, tool: str, pattern: str
) -> dict[str, Any]:
    """PARTIAL-P3/B3-7: declare a third-party tool's error-severity vocabulary.

    Requirement-driven, no defaults: an undeclared tool gates nothing.
    `godmode_verdict.record_verdict` only ever tests a checker's OWN
    captured output against a pattern registered HERE for a tool named in
    that same checker's command - a project that never calls this function
    sees no change in behaviour at all, whatever its checkers print.

    Charter-rule TEMPLATE (this docstring is the emission - see the module
    note on `godmode_charter.py` templates being doc-only for kinds like
    this one, whose actual declaration is data, not prose an operator
    writes by hand). A project that wants this gate states the doctrine in
    GODMODE.md, in a shape the existing `never ... without ...` classifier
    already compiles to a HARD `attestation_present` rule:

        Never confirm a verdict whose checker output logs a declared tool's
        error severity without an acknowledged-remediated or
        acknowledged-deferred attestation.

    ...and separately, ONCE, registers the tool + pattern this data-level
    gate actually matches against (prose cannot carry a regex safely):

        godmode error-pattern register --tool pytest --pattern "(?i)\\berror\\b"

    Validated exactly as `register_metric_contract` validates its anchor -
    same class of hand-written, untrusted regex, later matched against
    untrusted captured tool output, so it earns the same three checks
    (compiles, length-capped, scanned for catastrophic-backtracking shapes).
    """
    tool = tool.strip()
    if not tool or not _TOOL_NAME.match(tool):
        raise ArchiveError(
            "An error-pattern tool name must be 1-64 characters of "
            "letters/digits/._+- starting with a letter or digit"
        )
    if not pattern or len(pattern) > _ANCHOR_MAX_LEN:
        raise ArchiveError(f"An error pattern must be 1-{_ANCHOR_MAX_LEN} characters")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ArchiveError(f"Error pattern {pattern!r} is not a valid pattern: {exc}") from exc
    shape = _catastrophic_shape(pattern)
    if shape:
        raise ArchiveError(
            f"Error pattern {pattern!r} contains a nested-quantifier shape "
            f"({shape!r}) that risks catastrophic backtracking - simplify it"
        )
    return archive.append(
        "decision", f"error-pattern:{tool}",
        {"tool": tool, "pattern": pattern, "session": session},
        evidence=[],
    )


def declared_error_patterns(archive: Chronicle) -> dict[str, str]:
    """Every tool -> pattern declared via `register_error_pattern`.

    An empty result means no tool is declared at all - the fast, common
    path `record_verdict` takes for every caller that has never touched
    this mechanism. The most recently registered pattern for a given tool
    wins, the same "last write wins" precedent `_registered_anchor` already
    uses for metric contracts.
    """
    patterns: dict[str, str] = {}
    for record in archive.select(kind="decision", limit=500):
        subject = record["subject"]
        if not subject.startswith("error-pattern:"):
            continue
        data = record["data"]
        tool = data.get("tool") or subject[len("error-pattern:"):]
        patterns[tool] = data.get("pattern", "")
    return patterns


# Markdown emphasis stripped before the metric-name search runs, so
# "**val_bpb** improved to 3.21" still names the metric it bolded. Bare `*`
# and `` ` `` only - NOT `_`, because a metric name is exactly the kind of
# identifier that carries underscores itself (`val_bpb`), and stripping every
# underscore in the text would delete the very thing this is searching for.
_EMPHASIS = re.compile(r"[*`]")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _strip_emphasis(text: str) -> str:
    return _EMPHASIS.sub("", text)


def _metric_line_citations(name: str, citations: list[str]) -> list[tuple[str, str]]:
    """(citation, cited_value) pairs among `citations` naming this metric."""
    found: list[tuple[str, str]] = []
    for citation in citations:
        match = _LINE_CITE.match(str(citation))
        if match and match.group("name") == name:
            found.append((str(citation), match.group("value")))
    return found


def _numbers_differ(cited: str, claimed: str) -> bool:
    try:
        return float(cited) != float(claimed)
    except ValueError:
        return cited != claimed


def _metric_contract_reason(archive: Chronicle, text: str, citations: list[str]) -> str | None:
    """U-T3: the downgrade reason when a claimed number contradicts its
    cited anchored line, or `None` when the claim should be left alone.

    Only fires when a registered metric's name literally appears in the
    (emphasis-stripped) claim text - an unregistered metric name gets no
    friction from this at all. Only the FIRST number in the claim text is
    compared against each mentioned metric's cited value: a single claim
    naming two metrics with two different numbers each is a known scale
    limit of this check, not a silent skip - the common case this contract
    targets (one metric, one number) is exact.
    """
    names = _registered_metric_names(archive)
    if not names:
        return None
    normalized = _strip_emphasis(text)
    mentioned = [name for name in names if re.search(rf"\b{re.escape(name)}\b", normalized)]
    if not mentioned:
        return None
    numbers = _NUMBER.findall(normalized)
    if not numbers:
        return None
    claimed = numbers[0]
    for name in mentioned:
        for citation, cited_value in _metric_line_citations(name, citations):
            if _numbers_differ(cited_value, claimed):
                return (
                    f"the cited line says {name}:{cited_value}, the claim says "
                    f"{claimed} ({citation} does not match)"
                )
    return None


def record_criterion(
    archive: Chronicle,
    session: str,
    task: str,
    text: str,
    cites: list[str] | None = None,
    timeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record what passing looks like, under subject `criterion:<task>`.

    A later claim cites it back by that same string (`criterion:<task>`,
    resolved in `_citation_resolves`). Two checks here, both advisory - they
    inform the record, they never block writing the criterion:

    * Weak-criterion lint: no `cmd:` citation and only vague verbs
      (improve/clean/better) in the text - nothing an outside reader could
      check pass/fail against.
    * Ordering: when `timeline` is supplied (a transcript was available) and
      it already shows a mutation turn, the criterion is being written after
      work has already started, and cannot have judged that work. `timeline`
      absent is a stated gap, not a violation - the ordering simply cannot
      be checked without an instrument.
    """
    if not task.strip():
        raise ArchiveError("A criterion needs a non-empty task slug")
    citations = cites or []
    has_command = any(str(c).startswith("cmd:") for c in citations)
    advisories: list[str] = []
    if not has_command and _WEAK_VERBS.search(text):
        advisories.append(
            "weak criterion: no command citation and only vague verbs "
            "(improve/clean/better) - state what passing looks like, "
            "ideally citing cmd:<the check that will judge it>"
        )
    late = bool(timeline is not None and timeline.get("mutation_turns"))
    if late:
        advisories.append(LATE_CRITERION_FINDING)
    return archive.append(
        "criterion",
        f"criterion:{task.strip()}",
        {
            "task": task.strip(),
            "text": text,
            "session": session,
            "late": late,
            "advisories": advisories,
        },
        evidence=citations,
    )


# PARTIAL-P2/B3-4: two witnesses that would both dissolve to the same
# underlying fact are not two witnesses - they are one fact, cited twice.
# Fix-round-1 (review I1): a `file:` target compared as raw text let cosmetic
# spelling alone launder a single read into two witnesses - `file:x` and
# `file:./x` name the identical on-disk file but partitioned to different
# strings. Slash direction is canonicalised to `/` FIRST so `posixpath`'s own
# `.`/`..` collapsing (which only understands `/`) works the same whether the
# citation was written with a Windows backslash or not - this is deliberately
# "ntpath-safe" by normalizing away the platform difference up front rather
# than delegating to `ntpath` itself, which would accept a bare `x` as a
# relative-to-current-drive path and complicate the comparison for no benefit
# here (this is never used to touch the filesystem, only to compare two
# citation strings). Casefolded only on a case-insensitive host (`os.name ==
# "nt"`): POSIX filesystems are case-sensitive by default, so `file:X` and
# `file:x` legitimately name different files there and must NOT collapse.
def _normalize_file_target(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/"))
    if os.name == "nt":
        normalized = normalized.casefold()
    return normalized


def _witness_identity(citation: str) -> tuple[str, str]:
    """(kind, resolved-target) used only to test whether two citations name
    the same underlying artifact - never to test whether either resolves.

    Same kind AND same target means "the same witness": a `file:` target
    drops any `#L...` line locator AND is normalized (see
    `_normalize_file_target`) before comparison, so `file:pin.py#L10`,
    `file:./pin.py#L40`, and `file:sub/../pin.py` are all the same file read
    more than once, not independent reads. Every other kind's target is its
    citation text verbatim after the prefix, so `cmd:python check.py a.txt`
    and `cmd:python check.py b.txt` are two distinct artifacts (different
    resolved targets) even though both are `cmd:`, while two copies of the
    exact same `cmd:` string collapse to one. A different kind is always
    independent of every other kind, regardless of target - a `file:` and a
    `cmd:` citation are never "the same witness" just because they happen to
    concern the same subject.
    """
    kind, sep, rest = citation.partition(":")
    if not sep:
        return "", citation
    if kind == "file":
        rest = _normalize_file_target(rest.split("#", 1)[0])
    return kind, rest


def _independent_witness_count(citations: list[str]) -> int:
    """How many DISTINCT underlying artifacts `citations` names.

    Simple by design (documented, not tuned): the count of unique
    `_witness_identity` pairs. Two copies of one witness count once;
    anything genuinely different - kind or target - counts again.
    """
    return len({_witness_identity(str(c)) for c in citations})


def _guard_citations(citations: list[str]) -> list[str]:
    """Citations that name a test/guard file: `tests/` path segment, a
    `test_*`/`*_test.*`/`*.test.*` basename. Conservative on purpose - a
    false positive here taxes an honest claim."""
    guards: list[str] = []
    for citation in citations:
        text = str(citation)
        if not text.startswith("file:"):
            continue
        path = text[len("file:"):].replace("\\", "/").lower()
        name = path.rsplit("/", 1)[-1]
        if ("/tests/" in f"/{path}" or name.startswith("test_")
                or ".test." in name or name.endswith("_test.py")):
            guards.append(citation)
    return guards


def _guard_pin_reason(project: Path, archive: Chronicle, text: str,
                      citations: list[str]) -> str:
    from .godmode_sources import guard_pin_reason

    return guard_pin_reason(project, archive, text, citations)


def record_claim(
    archive: Chronicle,
    project: Path,
    session: str,
    text: str,
    grade: str,
    cites: list[str] | None = None,
    external: bool = False,
    timeline: dict[str, Any] | None = None,
    blast_radius: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Persist a claim, downgrading it when its citations do not resolve.

    Not a warning. A claim the evidence does not support is stored as a hypothesis,
    because a claim asserted at full confidence is what a later session will trust.

    A claim about an external API or library (`external=True`) must cite a
    primary source read this session (`doc:` or `url:` citation) - memory of a
    library is a hypothesis about a version that may no longer exist.

    `timeline` (U-T2, from `godmode_session_log.session_timeline`) is the
    optional per-command red/green shape from this session's transcript. A
    fix-vocabulary claim citing `cmd:<command>` is checked against it: when
    a timeline is supplied and shows no red-before-green for any cited
    command, the claim downgrades. `timeline=None` (no transcript available)
    skips the check entirely - absence of the instrument is never a penalty.

    `blast_radius` (PARTIAL-P2/B3-4) is opt-in and defaults to unset: a
    claim that does not declare one is graded exactly as before this field
    existed. Declared as one of `BLAST_RADIUS_KINDS` (an ops-directed
    action, a sticky/persisting side effect, or a checksum-class guard), it
    raises the evidence bar for a `verified` grade past mere citation
    resolution - the claim needs `_BLAST_RADIUS_MIN_WITNESSES` INDEPENDENT
    witnesses (see `_witness_identity`), not that many citations. Two
    citations that both resolve to the same file, or two copies of the same
    `cmd:` string, are one witness said twice and downgrade exactly like too
    few citations at all, naming the bar in the reason.
    """
    if grade not in GRADES:
        raise ArchiveError(f"Unknown claim grade '{grade}'; expected one of {', '.join(GRADES)}")
    if confidence is not None:
        # The calibration ledger only works if the number means one thing:
        # a probability. Out-of-range values are refused, not clamped -
        # clamping would silently rewrite what the author said they believed.
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            raise ArchiveError(
                f"confidence must be a number in [0, 1]; got {confidence!r}"
            )
        confidence = float(confidence)
    if blast_radius is not None and blast_radius not in BLAST_RADIUS_KINDS:
        raise ArchiveError(
            f"Unknown blast_radius '{blast_radius}'; expected one of "
            f"{', '.join(BLAST_RADIUS_KINDS)}"
        )
    citations = cites or []
    # Detected as well as declared: the check protected whoever remembered to
    # pass the flag, which is not the person who needs it.
    if not external and grade == "verified":
        external, _reason = looks_external(text)
    # A cause is a claim about a mechanism, and the ledger this rule comes from
    # is a record of mechanisms asserted from the nearest anomaly. Checked
    # before the external gate so a root cause about a third-party system is
    # held to both. U-E3: only bites once the archive holds two comparable
    # states to diff - see `_differential_reason`.
    if grade == "verified":
        differential_reason = _differential_reason(project, archive, session, text, citations)
        if differential_reason:
            return archive.append(
                "claim", text[:120],
                {"text": text, "grade": "hypothesis", "claimed_grade": grade,
                 "session": session, "downgraded": True, "unresolved": [],
                 "operator_asserted": [], "blast_radius": blast_radius, "confidence": confidence,
                 "reason": differential_reason},
                evidence=citations,
            )
    # U-T3: a claimed number that contradicts the value on its own cited
    # anchored line - checked before the external gate for the same reason
    # as the root-cause check above: a claim can be held to more than one
    # discipline at once.
    if grade == "verified":
        metric_reason = _metric_contract_reason(archive, text, citations)
        if metric_reason:
            return archive.append(
                "claim", text[:120],
                {"text": text, "grade": "hypothesis", "claimed_grade": grade,
                 "session": session, "downgraded": True, "unresolved": [],
                 "operator_asserted": [], "blast_radius": blast_radius, "confidence": confidence,
                 "reason": metric_reason},
                evidence=citations,
            )
    if external and grade == "verified":
        primary = [c for c in citations if c.startswith(("doc:", "url:"))]
        if not primary:
            record = archive.append(
                "claim", text[:120],
                {"text": text, "grade": "hypothesis", "claimed_grade": grade, "session": session,
                 "downgraded": True, "unresolved": [], "blast_radius": blast_radius, "confidence": confidence,
                 "reason": "external claim without a primary source read this session; "
                           "cite doc:<path> or url:<address> from a source actually opened"},
                evidence=citations,
            )
            return record
    unresolved = [
        citation for citation in citations
        if not _citation_resolves(project, archive, citation, session)
    ]
    # A citation can resolve and still point at the wrong place. Existence and
    # support are separate claims, so they are checked separately.
    unsupported = [
        citation
        for citation in citations
        if citation not in unresolved
        and _position_support(project, citation, text) == "unsupported"
    ]
    fix_claim, _fix_why = looks_like_fix_claim(text)
    cmd_citations = [c for c in citations if str(c).startswith("cmd:")]
    effective = grade
    reason = ""
    absence = is_absence_claim(text)
    if grade == "verified":
        if not citations:
            effective, reason = "hypothesis", "no citation"
        elif unresolved:
            # A command that ran in an earlier session is a different failure
            # from one that never ran, and saying so is the difference between
            # a remedy the reader can perform and a puzzle.
            stale = _ran_in_another_session(archive, unresolved, session)
            if stale:
                effective, reason = (
                    "hypothesis",
                    f"{stale} ran in another session, not this one; the record "
                    "proves it ran once, not that it still holds - run it again "
                    "and cite this session's attestation",
                )
            else:
                effective, reason = "hypothesis", "citation does not resolve"
                suggestion = near_miss(unresolved[0], known_citations(archive))
                if suggestion:
                    reason += f"; did you mean {suggestion!r}"
        elif blast_radius is not None and (
            witness_count := _independent_witness_count(citations)
        ) < _BLAST_RADIUS_MIN_WITNESSES:
            # PARTIAL-P2/B3-4: every citation resolved (checked above), but a
            # blast_radius claim needs INDEPENDENT witnesses, not just enough
            # citations - two citations that both name the same file, or two
            # copies of the same cmd:, are one fact said twice.
            effective, reason = (
                "hypothesis",
                f"blast_radius={blast_radius!r} needs >={_BLAST_RADIUS_MIN_WITNESSES} "
                "independent witnesses (distinct citation kinds or distinct "
                f"resolved artifacts); found {witness_count} distinct among "
                f"{len(citations)} citation(s)",
            )
        elif fix_claim and timeline is not None and cmd_citations:
            # U-T2: the citation resolves (checked above), but a fix claim
            # needs more than a citation - it needs the command to have been
            # observed failing before the fix and passing after.
            #
            # R3+ tier proxy: fix-vocabulary claims + Edit/Write mutation turns
            # stand in for sentinel risk tiers (out of scope here); known gap:
            # non-file-mutating R3+ commands (git branch -D) are not counted
            # as mutations. Wire to classify_action tiers when a task owns
            # the sentinel.
            temporal_reason = _temporal_violation(timeline, cmd_citations)
            if temporal_reason:
                effective, reason = "hypothesis", temporal_reason
        elif absence and not _probed_twice(archive, citations):
            # One probe that found nothing is evidence about where it looked.
            # A second, different probe is what turns that into a fact about
            # what exists - a search miss promoted to absence is one of the
            # commonest ways a confident wrong finding gets published.
            effective, reason = (
                "hypothesis",
                "an absence claim rests on one probe; prove it a second, "
                "different way and cite both",
            )
        elif absence and not _cites_a_search(archive, citations):
            # "No X exists" cannot be shown by pointing at somewhere X is not. Without
            # the search that would have found X, the claim cannot be wrong - and a
            # claim nothing could falsify is not verified, it is merely unchallenged.
            effective, reason = (
                "hypothesis",
                "absence claim cites no search that would have found a counter-example",
            )
        elif _guard_citations(citations) and not cmd_citations:
            # Obligation 4122 (field report 2026-08-28): three withdrawals
            # rested on guard assertions READ but not RUN. Reading a test
            # file pins what it would check; only running it checks it. A
            # verified claim resting on a test file needs the run beside it.
            effective, reason = (
                "hypothesis",
                "a guard is cited but not run: reading a test pins intent, "
                "only running it verifies - add cmd:<the command that ran it> "
                "beside the file citation",
            )
        elif absence and (pin_reason := _guard_pin_reason(project, archive, text, citations)):
            # Obligation 4166 (field report 2026-08-28): a state-is-a-gap
            # claim about a line an uncited test pins, or a symptom the
            # lessons ledger already holds, is answered by that pin's
            # provenance - not published as a gap, not fixed in place.
            effective, reason = "hypothesis", pin_reason
        elif unsupported:
            effective, reason = "hypothesis", "cited location does not support the claim"

    # Criterion pre-registration [E4]: advisory only - it informs a fix claim
    # that a criterion exists and was not cited, it never downgrades one. A
    # project that never records criteria gets no friction from this at all.
    #
    # R3+ tier proxy: fix-vocabulary claims + Edit/Write mutation turns stand
    # in for sentinel risk tiers (out of scope here); known gap: non-file-
    # mutating R3+ commands (git branch -D) are not counted as mutations.
    # Wire to classify_action tiers when a task owns the sentinel.
    advisories: list[str] = []
    if grade == "verified" and fix_claim:
        session_has_criterion = any(
            record["data"].get("session") == session
            for record in archive.select(kind="criterion", limit=500)
        )
        if session_has_criterion and not any(
            str(c).startswith("criterion:") for c in citations
        ):
            advisories.append(
                "no criterion citation: cite criterion:<task> naming what "
                "you judged success by"
            )

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
            "advisories": advisories,
            # PARTIAL-P2/B3-4: stored even when unset (None) so every claim
            # record carries the same field set - a reader never has to
            # guess whether an absent key means "not declared" or "not yet
            # this schema version".
            "blast_radius": blast_radius, "confidence": confidence,
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


RESOLUTION_OUTCOMES = ("held", "failed")


def resolve_claim(
    archive: Chronicle,
    project: Path,
    session: str,
    seq: int,
    outcome: str,
    cites: list[str] | None = None,
) -> dict[str, Any]:
    """Close one claim with an outcome and the evidence that decided it.

    The calibration ledger's second half: a claim recorded with a
    confidence eventually meets what actually happened. `held` means the
    claim survived contact with the check; `failed` means it did not. The
    pair yields a score, 1 - (confidence - outcome)^2, stored on the
    resolution so the doctor can read calibration straight off the record.

    Resolutions are claims too (same kind, `resolves` field) - no new
    record schema, and the privacy/verification machinery covers them for
    free. Three refusals keep the ledger honest: a resolution needs the
    claim to exist, needs evidence of the outcome (an outcome nobody can
    check is just a second claim), and lands at most once - recalibrating
    history would defeat the point of measuring it.
    """
    if outcome not in RESOLUTION_OUTCOMES:
        raise ArchiveError(
            f"Unknown outcome '{outcome}'; expected one of {', '.join(RESOLUTION_OUTCOMES)}"
        )
    citations = cites or []
    if not citations:
        raise ArchiveError(
            "a resolution needs at least one citation: the evidence that "
            "decided the outcome, not the outcome alone"
        )
    target: dict[str, Any] | None = None
    for record in archive.select(kind="claim", limit=500):
        if record["sequence"] == seq:
            target = record
        if record["data"].get("resolves") == seq:
            raise ArchiveError(
                f"claim seq:{seq} is already resolved by seq:{record['sequence']}; "
                "a claim resolves at most once"
            )
    if target is None:
        raise ArchiveError(f"No claim record at seq:{seq}")
    if target["data"].get("resolves") is not None:
        raise ArchiveError(
            f"seq:{seq} is itself a resolution; resolutions are terminal"
        )
    unresolved = [
        citation for citation in citations
        if not _citation_resolves(project, archive, citation, session)
    ]
    if unresolved:
        raise ArchiveError(
            f"resolution evidence does not resolve: {', '.join(unresolved)}"
        )
    confidence = target["data"].get("confidence")
    outcome_value = 1.0 if outcome == "held" else 0.0
    score = (
        None if confidence is None
        else round(1.0 - (float(confidence) - outcome_value) ** 2, 6)
    )
    return archive.append(
        "claim",
        f"resolution of seq:{seq}: {outcome}",
        {
            "session": session,
            "text": f"claim seq:{seq} {outcome}",
            "resolves": seq,
            "outcome": outcome,
            # Copied down so the summary never joins across records to score.
            "confidence": confidence,
            "score": score,
            "grade": "observed",
            "claimed_grade": "observed",
            "downgraded": False,
            "unresolved": [],
            "unsupported": [],
            "reason": "",
            "advisories": [],
            "blast_radius": None,
            "operator_asserted": [],
        },
        evidence=citations,
    )


# Confidence bands for the calibration summary. One table, one place -
# the render and any future tier threshold read these, never re-derive.
_CALIBRATION_BANDS = (("high", 0.8, 1.01), ("mid", 0.5, 0.8), ("low", 0.0, 0.5))


def calibration_summary(archive: Chronicle) -> dict[str, Any]:
    """Read the whole calibration ledger into one doctor-ready block.

    Reports the mean score over resolved scored claims, the error rate
    per confidence band (how often each band's claims failed - the number
    that makes any tier threshold auditable instead of aesthetic), and
    the standing debt: scored claims never resolved. Honest-empty when
    nothing is scored yet.
    """
    records = archive.select(kind="claim", limit=500)
    resolutions = [r for r in records if r["data"].get("resolves") is not None]
    resolved_seqs = {r["data"]["resolves"] for r in resolutions}
    scored = [r for r in resolutions if r["data"].get("score") is not None]
    debt = [
        r for r in records
        if r["data"].get("resolves") is None
        and r["data"].get("confidence") is not None
        and r["sequence"] not in resolved_seqs
    ]
    summary: dict[str, Any] = {
        "scored_resolved": len(scored),
        "unresolved_scored": len(debt),
        "oldest_unresolved_seq": min((r["sequence"] for r in debt), default=None),
    }
    if not scored and not debt:
        summary["note"] = "no scored claims yet - claims carry no confidence until one is declared"
        summary["bands"] = []
        return summary
    if scored:
        summary["mean_score"] = round(
            sum(r["data"]["score"] for r in scored) / len(scored), 6
        )
    bands = []
    for name, floor, ceiling in _CALIBRATION_BANDS:
        members = [
            r for r in scored
            if floor <= float(r["data"]["confidence"]) < ceiling
        ]
        if not members:
            continue
        failures = sum(1 for r in members if r["data"]["outcome"] == "failed")
        bands.append({
            "band": name,
            "resolved": len(members),
            "error_rate": round(failures / len(members), 6),
        })
    summary["bands"] = bands
    return summary


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
    checked = sum(len(v) for v in seen.values())
    # A green verdict from a scan that examined nothing is the failure this
    # project keeps finding in itself: `no-recurrence` on `checked: 0` reads
    # as "the same cause never repeated" when it means "no blocked step has
    # ever been recorded". The reconciler and the census both learned to say
    # which of the two they mean; this said the reassuring one.
    if not checked:
        verdict = "insufficient-data"
    elif repeated:
        verdict = "recurrence-detected"
    else:
        verdict = "no-recurrence"
    return {
        "checked": checked,
        "recurrences": repeated,
        "count": len(repeated),
        "verdict": verdict,
        "scope": ("blocked steps recorded by `attest`; a project that has "
                  "never recorded one has nothing to compare"),
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
    # E62 (Task 4b): each `accept: cmd:...` entry on the active plan needs a
    # this-session attestation before completion - the same discipline as an
    # unattested HARD rule, applied to a plan's own executable acceptance.
    from .godmode_plan import unattested_accept_commands

    unattested_accept = unattested_accept_commands(archive, session)
    allowed = not unattested and not downgraded and not half_done and not unattested_accept
    verdict: dict[str, Any] = {
        "session": session,
        "closed": allowed,
        "unattested_hard_rules": unattested,
        "downgraded_claims": downgraded,
        "half_done_pairs": half_done,
        "unattested_accept_commands": unattested_accept,
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


def _ran_in_another_session(
    archive: Chronicle, unresolved: list[str], session: str
) -> str | None:
    """The first unresolved command that did run, just not in this session.

    Naming that case separately is the whole value: "does not resolve" sends a
    reader looking for a typo, when the command ran perfectly well a fortnight
    ago against a tree that has since moved.
    """
    attestations = archive.select(kind="attestation", limit=500)
    for citation in unresolved:
        if not str(citation).startswith("cmd:"):
            continue
        for record in attestations:
            if citation in record.get("evidence", []) and record["data"].get("session") != session:
                return str(citation)
    return None


def _probed_twice(archive: Chronicle, citations: list[str]) -> bool:
    """Whether an absence claim needs a second probe, and has one.

    Proportionate on purpose. The failure this guards is concluding absence
    from a search that came back empty - a miss is evidence about where you
    looked, not about what exists. A probe that positively enumerated something
    is a different act, and demanding a second one for every absence claim
    would be the over-gating that gets a check switched off.

    So: if every cited command came back empty, a second distinct probe is
    required. If any of them actually found and listed something, one is enough.
    """
    commands = {str(c) for c in citations if str(c).startswith("cmd:")}
    if len(commands) >= 2:
        return True
    if not commands:
        return False
    empties = 0
    for record in archive.select(kind="attestation", limit=500):
        if commands & set(record.get("evidence", [])):
            if record["data"].get("status") == "empty":
                empties += 1
            else:
                # A probe that enumerated rather than missed.
                return True
    return empties == 0


def evidence_from_elsewhere(
    archive: Chronicle, citations: list[str]
) -> list[dict[str, Any]]:
    """Cited runs that happened under a different platform or interpreter.

    Reported, never refused. Cross-platform work is ordinary and blocking it
    would be absurd; what must not happen is a result being read as a statement
    about this environment when it was produced in another one. This project
    learned that twice in a day - a detector called broken by a test written
    where history existed, and a suite green here and red on six CI jobs.
    """
    here = agent_fingerprint()
    found: list[dict[str, Any]] = []
    for record in archive.select(kind="attestation", limit=500):
        agent = (record["data"] or {}).get("agent") or {}
        if not agent.get("platform"):
            continue
        same = (agent.get("platform") == here.get("platform")
                and agent.get("python") == here.get("python"))
        if same:
            continue
        for citation in citations:
            if citation in record.get("evidence", []):
                found.append({
                    "citation": citation,
                    "ran_on": f"{agent.get('platform')} / python {agent.get('python')}",
                    "reading_on": f"{here.get('platform')} / python {here.get('python')}",
                    "note": "this ran somewhere else; reproduce here before "
                            "reading it as evidence about this environment",
                })
    return found
