"""Mistake-class detectors: the recurring failures, distilled into checks.

Each detector targets one class from the lesson corpus - not hypothetical
failure modes but the ones that actually recurred. They read the archive and
the tree; none needs a model's cooperation to fire.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_constants import CODE_SUFFIXES, IGNORED_DIRECTORY_NAMES

# Records that prove the session kept moving, named in the kinds the archive
# actually holds. The first version listed the *commands* - build, verify,
# attest - and only `plan` among them is a record kind, so the check matched
# almost nothing while its tests passed against a fake ledger that did not
# validate kinds. `godmode build` writes `change`; `verify` and `attest` write
# `attestation`.
#
# A checkpoint is deliberately excluded: writing down that you are stuck is not
# the same as continuing.
_WORK_KINDS = frozenset({"action", "attestation", "change", "plan"})

_CLAIM_SPLIT = re.compile(r";\s+|\b(?:and also|as well as)\b|\n\s*\d+[.)]\s")
_VERBISH = re.compile(r"\b(?:is|are|was|were|works|passes|fixed|fails|blocks|returns)\b")

# Kinds whose text is written to be read by a person, which is the only place a
# dropped frame can mislead one. A `change` or an `action` records what ran.
_QUOTED_TO_A_PERSON = frozenset({"claim", "lesson", "decision"})

# The vocabulary of ATTRIBUTION, not of description. "the encode failed" reports
# an observation and is not making this mistake; "the encode failed because the
# probe timed out" indicts a mechanism, and a mechanism is answerable to a line.
# Asserting that something is not there. `no <noun>` needs the noun: "no" alone
# catches "no longer" and every other ordinary use of the word.
_ABSENCE = re.compile(
    r"\b(?:nothing (?:found|there|matched)|no (?:evidence|results?|matches?|hits?|rows?|"
    r"records?|occurrences?|instances?|references?|callers?|usages?)|"
    r"not (?:present|found|there|used|referenced|called)|"
    r"never (?:used|called|referenced)|zero |none (?:found|of them)|"
    r"does not (?:exist|appear)|is absent|are absent|no such)\b",
    re.IGNORECASE,
)

# A count offered as a total. Deliberately requires a countable noun after the
# number: a bare integer is a version, a port, a line number, a duration.
_BARE_COUNT = re.compile(
    r"\b\d+\s+(?:errors?|rows?|records?|files?|results?|matches?|hits?|items?|"
    r"tests?|failures?|warnings?|events?|entries?|occurrences?|instances?|"
    r"symbols?|modules?|documents?|projects?|users?|sessions?)\b",
    re.IGNORECASE,
)

# What turns either shape into an honest statement: the extent it covers.
_EXTENT = re.compile(
    r"\b(?:of|out of|/\s*\d|across|among|within|scanned|searched|examined|inspected|"
    r"all |every |entire|whole|total of|complete|capped|limited to|first \d+|"
    r"top \d+|sample|subset|denominator|population)\b",
    re.IGNORECASE,
)

_CAUSAL = re.compile(
    r"\b(?:root cause|the root is|caused by|causes|because|due to|owing to|"
    r"stems from|comes from|the culprit|responsible for|is why|which is why|"
    r"triggered by|introduced by|broken by|regressed by)\b",
    re.IGNORECASE,
)

# A time that already carries a numeric offset is deleted before the scan
# rather than exempted inside it. Both halves are needed and neither is
# sufficient: the offset must be removed WITH the clock it frames, because
# removing it alone strips the very evidence that made the clock legitimate,
# and leaving it alone lets its own `05:30` be read as a second bare time.
_NUMERICALLY_FRAMED = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\s*[+-]\d{2}:?\d{2}"
)

# A wall clock with nothing after it saying which clock. The trailing
# alternatives are the two honest endings: a named frame (`UTC`, `IST`) or a
# unit that makes the number a duration rather than a time of day - `1:30
# elapsed` is not a claim about when anything happened.
#
# `(?!:)` after the seconds group is what makes the exemption hold. Without it
# the engine matches `18:24:57`, finds ` IST` and rejects the match, then
# BACKTRACKS to `18:24`, whose next character is a colon rather than a frame -
# so a correctly labelled time reported itself as an unlabelled one.
_UNFRAMED_CLOCK = re.compile(
    r"\b\d{1,2}:\d{2}(?::\d{2})?(?!:)\b"
    r"(?!\s*(?:UTC|GMT|UT|Z\b|IST|BST|CET|CEST|EST|EDT|CST|CDT|MST|MDT|PST|PDT|JST|AEST"
    r"|local|localtime"
    r"|h\b|hrs?\b|hours?\b|m\b|min\b|minutes?\b|s\b|secs?\b|seconds?\b"
    r"|elapsed|remaining|long|of\b|into\b))",
    re.IGNORECASE,
)


def label_as_fact(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M1: a status label used as evidence must trace to the record that assigned it."""
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        evidence = record.get("evidence", [])
        labels = [e for e in evidence if e.startswith("status:") or e.startswith("label:")]
        traced = any(e.startswith("seq:") for e in evidence)
        if labels and not traced:
            findings.append({
                "detector": "label-as-fact", "blocking": True,
                "detail": f"claim '{record['subject'][:60]}' rests on {labels[0]} without "
                          "citing the seq: record that assigned the label",
                "citations": [f"seq:{record['sequence']}"],
            })
    return findings


def ritual_without_reading(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M2: a mandated artefact regenerated but never queried is a box-tick."""
    documented: dict[str, int] = {}
    for record in records:
        if record["kind"] == "documentation":
            documented[record["subject"]] = record["sequence"]
    if not documented:
        return []
    cited: set[str] = set()
    for record in records:
        for evidence in record.get("evidence", []):
            for name in documented:
                if name in evidence:
                    cited.add(name)
    return [{
        "detector": "ritual-without-reading", "blocking": False,
        "detail": f"'{name}' was regenerated (seq:{sequence}) and never cited afterwards; "
                  "generated-but-unread is a box-tick, not a step",
        "citations": [f"seq:{sequence}"],
    } for name, sequence in sorted(documented.items()) if name not in cited]


def invariant_vs_instance(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M6: a guard narrower than its ruling protects one surface of many.

    A lesson out of force is not reported, for the same reason a retired
    invariant no longer contradicts a live one: correcting a record is the
    documented lifecycle, and a check that keeps reading the superseded version
    turns using that lifecycle into a permanent finding. The word list is
    shared with the contradiction check rather than copied, which is the
    defect that produced this paragraph - the same rule was fixed in one reader
    and left standing in the other.
    """
    from .godmode_constants import SETTLED_STATUSES

    # The archive is append-only, so a record cannot go back and mark itself
    # superseded: retiring a ruling means writing a LATER record on the same
    # subject that says so. Reading each record's own status therefore settles
    # nothing - the correction carries the status and the record being corrected
    # never does, which is why the first version of this fix left the original
    # firing forever and made using the lifecycle look like a defect.
    settled_at: dict[str, int] = {}
    for record in records:
        if str((record.get("data") or {}).get("status", "")).lower() in SETTLED_STATUSES:
            subject = record.get("subject", "")
            settled_at[subject] = max(settled_at.get(subject, 0), int(record.get("sequence", 0)))

    findings = []
    for record in records:
        if record["kind"] != "lesson" or not record["data"].get("generalized_guard"):
            continue
        if str(record["data"].get("status", "")).lower() in SETTLED_STATUSES:
            continue
        # Only a LATER settlement retires it. An earlier one settled an earlier
        # ruling, and this is a new statement that has to answer for itself.
        if int(record.get("sequence", 0)) < settled_at.get(record.get("subject", ""), 0):
            continue
        files = [e for e in record.get("evidence", []) if e.startswith("file:")]
        if len(files) == 1:
            findings.append({
                "detector": "invariant-vs-instance", "blocking": True,
                "detail": f"lesson '{record['subject'][:60]}' declares a generalized guard "
                          f"but cites one surface ({files[0]}); enumerate the siblings or "
                          "narrow the ruling",
                "citations": [f"seq:{record['sequence']}"],
            })
    return findings


def stale_runtime(project: Path, process_started: str) -> dict[str, Any]:
    """M8: diagnosing against a process older than the code it runs is blocked.

    Both sides of the comparison are pinned to UTC, because they used not to be.
    An unlabelled `process_started` is naive, and the file mtime was read with
    `tz=started.tzinfo` - so a naive input made that `tz=None`, which is LOCAL.
    The verdict then compared a local wall clock against one meant as UTC and
    was wrong by the host's offset: on a +05:30 host, a process started two
    hours AFTER the newest source reported `stale`, blocking an RCA that should
    have run, and on a negative offset it clears a genuinely dead process.

    Neither timestamp was wrong in its own frame, which is why it read as
    plausible - the same shape this module's `unframed_clock` detector reports
    in prose, here in a comparison.
    """
    started = datetime.fromisoformat(process_started)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    newest_path, newest_ns = None, 0
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_SUFFIXES:
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        stat_ns = path.stat().st_mtime_ns
        if stat_ns > newest_ns:
            newest_path, newest_ns = path, stat_ns
    newest_at = datetime.fromtimestamp(newest_ns / 1e9, tz=timezone.utc)
    stale = newest_at > started
    return {
        "process_started": process_started,
        "newest_source": newest_path.relative_to(project).as_posix() if newest_path else None,
        "newest_mtime": newest_at.isoformat(),
        "stale": stale,
        "verdict": "restart-before-rca" if stale else "runtime-is-current",
        "detail": ("the running process predates the newest source change; restart it "
                   "before any diagnosis, or the RCA describes a program that no longer exists"
                   if stale else "the process is newer than every source file"),
    }


def claim_splitting(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M13: one report carrying several independent claims hides the weak one."""
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        text = str(record["data"].get("text", record["subject"]))
        parts = [p for p in _CLAIM_SPLIT.split(text) if _VERBISH.search(p or "")]
        if len(parts) >= 2:
            findings.append({
                "detector": "claim-splitting", "blocking": True,
                "detail": f"'{text[:80]}' bundles {len(parts)} independent claims; split "
                          "them so each is graded on its own evidence",
                "citations": [f"seq:{record['sequence']}"],
            })
    return findings


def inferred_ask_blocking(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M14: the agent waiting on an instruction the operator never gave.

    Every other detector here reads a claim about the repository. This one
    reads a claim about the operator, which is the same failure pointed at a
    different subject: an inference presented with the standing of a fact, and
    then acted on. The acting is what makes it costly - an assumption that
    shapes the work is ordinary and often right, while an assumption that
    *stops* the work spends the operator's turn on a question they never
    raised.

    So the test is not whether the agent guessed, nor whether the guess was
    wrong. It is whether anything happened afterwards. An inferred ask with
    work recorded after it shaped the work; one with nothing after it stopped
    the work.
    """
    from .godmode_requests import _closed_digests

    closed = _closed_digests(records)
    findings = []
    for record in records:
        if record["kind"] != "request":
            continue
        data = record.get("data") or {}
        if str(data.get("source", "stated")).lower() != "inferred":
            continue
        if str(data.get("status", "")).lower() != "open":
            continue
        if str(data.get("digest", "")) in closed:
            continue
        sequence = int(record.get("sequence", 0))
        # Only work *after* the guess proves the guess did not stop anything.
        if any(later["kind"] in _WORK_KINDS
               and int(later.get("sequence", 0)) > sequence for later in records):
            continue
        findings.append({
            "detector": "inferred-ask-blocking", "blocking": False,
            "detail": f"the session is waiting on '{record['subject'][:60]}', which the "
                      "agent inferred rather than the operator stating; state the "
                      "assumption and carry on under it, or ask without stopping",
            "citations": [f"seq:{sequence}"],
        })
    return findings


def unframed_clock(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M15: a wall-clock time quoted to a person without the clock it came from.

    Distinct from every other detector here, which asks whether a claim is
    *supported*. This one asks whether a supported claim is *commensurable*
    with the sentence carrying it. Stores write UTC; operator surfaces render
    the viewer's zone; both are internally correct, and a bare number copied
    from one into a sentence about the other is wrong by the viewer's offset.

    Nothing upstream can catch it. Citation binding resolves the citation, the
    cited record holds the right instant, and the frame is what was dropped in
    transcription - so the error is uniform, which is exactly what lets it pass
    every self-consistency check and read as plausible.

    Blocking only on a `claim`, which is the record kind that gets published.
    A lesson or a decision may legitimately mention a schedule, and blocking a
    release on a cron expression written into a lesson would teach the operator
    to route around the detector.
    """
    findings = []
    for record in records:
        if record["kind"] not in _QUOTED_TO_A_PERSON:
            continue
        data = record.get("data") or {}
        text = str(data.get("text") or data.get("value") or record["subject"])
        bare = _UNFRAMED_CLOCK.findall(_NUMERICALLY_FRAMED.sub("", text))
        if not bare:
            continue
        findings.append({
            "detector": "unframed-clock", "blocking": record["kind"] == "claim",
            "detail": f"'{bare[0]}' is quoted without its clock; the archive stores UTC and "
                      "operator surfaces render the viewer's zone, so a bare time is wrong by "
                      "their offset - suffix it (`12:54 UTC` / `18:24 IST`) or convert",
            "citations": [f"seq:{record['sequence']}"],
        })
    return findings


def root_without_code(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M16: a named root cause that cites no line of the program it indicts.

    A mechanism that explains the symptom is a hypothesis. It becomes a finding
    when a line of code says so, and until then the sentence is doing the work
    the evidence should - which is why the wrong ones are so consistently
    plausible. Nothing else here reaches this: the claim may be perfectly
    supported by records, cite its sequence, and still never have opened the
    file it accuses.

    The check is deliberately narrow. It fires only on a claim that NAMES a
    cause - the vocabulary of attribution, not of description - because a claim
    that reports an observation is not making this mistake. A `rec:` citation
    does not satisfy it: pointing at another record is how an unexamined theory
    travels between passes, gaining standing at each hop without ever touching
    the program.
    """
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        data = record.get("data") or {}
        text = str(data.get("text") or record["subject"])
        if not _CAUSAL.search(text):
            continue
        if str(data.get("grade", "")).lower() in {"hypothesis", "unknown"}:
            continue  # Graded as unproven, which is the honest alternative.
        if any(e.startswith("file:") for e in record.get("evidence", [])):
            continue
        findings.append({
            "detector": "root-without-code", "blocking": True,
            "detail": f"'{text[:70]}' names a cause with no file: citation; read the path and "
                      "cite the line, or grade it `hypothesis` and say what would refute it",
            "citations": [f"seq:{record['sequence']}"],
        })
    return findings


def unretracted_reversal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M17: the same question answered twice, differently, with neither withdrawn.

    An analysis that reverses is not merely wrong once - it is unstable, and the
    reader cannot tell which pass to act on because both answers are still
    standing. Revising an answer is ordinary and often right; what is reported
    here is revising it SILENTLY, so the archive holds two live roots for one
    subject and no record of which was abandoned.

    This needs nothing from the agent that it is not already doing. Claims are
    written as a matter of course, and two of them on one subject with different
    text is the reversal, whether or not anyone chose to describe it as one. The
    remedy is equally cheap: mark the superseded claim, which is the same
    lifecycle the invariant contradiction check already reads, from the same
    word list.

    Two live answers is a finding; three is blocking. A single revision can be
    an honest correction mid-investigation, while a subject on its third live
    root is not converging, and another pass at the same depth will produce a
    fourth.
    """
    from .godmode_constants import SETTLED_STATUSES

    live: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["kind"] != "claim":
            continue
        data = record.get("data") or {}
        if str(data.get("status", "")).lower() in SETTLED_STATUSES:
            continue
        text = str(data.get("text") or record["subject"]).strip()
        answers = live.setdefault(record["subject"], [])
        if all(a["text"] != text for a in answers):
            answers.append({"text": text, "sequence": record["sequence"]})

    findings = []
    for subject, answers in sorted(live.items()):
        if len(answers) < 2:
            continue
        findings.append({
            "detector": "unretracted-reversal", "blocking": len(answers) >= 3,
            "detail": f"'{subject[:60]}' carries {len(answers)} live answers and none is marked "
                      "superseded; withdraw the ones no longer held and say what read changed "
                      "them" + (" - a third root means the read set is still open, so stop "
                                "analysing and go read" if len(answers) >= 3 else ""),
            "citations": [f"seq:{a['sequence']}" for a in answers],
        })
    return findings


def claim_from_a_sample(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M18: a statement about a population, made from a sample, that omits the sample.

    Third member of the same family as M15 and M16 - a value correct in its own
    frame and wrong in the reader's - and the one with the widest blast radius,
    because it does not need a second system to go wrong in. One query with a
    filter and a limit is enough.

    Two shapes, one remedy.

    An ABSENCE. "Nothing found", "no evidence", "it does not exist" - true of
    the search that was run, and asserted about the world. Two greps that miss
    inside a document containing the answer produce exactly this sentence, and
    it reads as a conclusion rather than as the description of a search. An
    absence claim needs the search that would have disproved it, which is the
    standard `precheck` already holds itself to when it reports where it looked.

    A COUNT. A bare total carries its query's filter and cap invisibly: "29
    errors today" from a call with a category filter and a silent limit is not
    the error log, it is a slice of one, and nothing about the number says so.
    The reader has no way to tell a complete count from a truncated one.

    Both are cleared the same way - state the extent - so both are one check.
    Evidence naming what was examined satisfies it, as does saying so in the
    text: `of`, `out of`, `scanned`, `all`, a denominator. What does not satisfy
    it is the number or the absence alone.
    """
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        data = record.get("data") or {}
        text = str(data.get("text") or record["subject"])
        absence = _ABSENCE.search(text)
        count = _BARE_COUNT.search(text)
        if not absence and not count:
            continue
        if _EXTENT.search(text):
            continue
        # Evidence that names what was examined is the extent, stated properly.
        if any(e.startswith(("searched:", "scanned:", "population:")) for e in
               record.get("evidence", [])):
            continue
        shape = "an absence" if absence else "a count"
        remedy = ("name the search that would have disproved it - which filters, which "
                  "paths, and whether it was capped"
                  if absence else
                  "state the denominator and any cap; a bare total carries its query's "
                  "filter and limit invisibly")
        findings.append({
            "detector": "claim-from-a-sample", "blocking": True,
            "detail": f"'{text[:70]}' asserts {shape} about a population without saying what "
                      f"was examined; {remedy}",
            "citations": [f"seq:{record['sequence']}"],
        })
    return findings


def analyze(archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events()
    findings = (
        label_as_fact(records)
        + ritual_without_reading(records)
        + invariant_vs_instance(records)
        + claim_splitting(records)
        + inferred_ask_blocking(records)
        + unframed_clock(records)
        + root_without_code(records)
        + unretracted_reversal(records)
        + claim_from_a_sample(records)
    )
    blocking = [f for f in findings if f["blocking"]]
    return {
        "records_scanned": len(records),
        "findings": findings,
        "blocking": bool(blocking),
        "verdict": "mistake-class-detected" if blocking else "clean",
    }
