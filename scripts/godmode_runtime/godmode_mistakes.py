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

from .godmode_chronicle import Chronicle, latest_by_subject
from .godmode_errors import ArchiveError
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

# The closed failure-class table. One list, one place: a free-text class
# cannot be trended, and an open list grows a synonym per author until no
# two records match. Extend by recorded precedent, never in passing.
FAILURE_CLASSES = (
    "plan-departure",        # required direction or agreed plan not followed
    "invented-information",  # content grounded in no input, context, or output
    "malformed-invocation",  # tool called with inputs its schema refuses
    "misread-tool-output",   # correct output, wrong conclusion drawn from it
    "goal-misread",          # the ask itself was misunderstood; plan was wrong
    "underspecified-ask",    # the record shows the information was never there
    "capability-gap",        # the needed tool or capability does not exist
    "blocked-by-guard",      # a control stopped the run; the guard is the story
    "environment-failure",   # the world broke: connectivity, host, filesystem
)


REPRO_PREFIX = "repro:"

# What a reproduction run showed at incident time. Only `red` can anchor a
# fix claim: a command that passed, or never started, reproduced nothing.
REPRO_RED = "red"
REPRO_NOT_REPRODUCING = "repro-not-reproducing"
REPRO_NOT_RUNNABLE = "repro-not-runnable"
REPRO_WAIVED = "waived"


def repro_command(cites: list[str] | None) -> str | None:
    """The first `repro:<cmd>` citation's command, or None."""
    for cite in cites or []:
        text = str(cite)
        if text.startswith(REPRO_PREFIX) and text[len(REPRO_PREFIX):].strip():
            return text[len(REPRO_PREFIX):].strip()
    return None


def validate_incident(failure_class: str | None, turning_point: bool,
                      cites: list[str] | None) -> None:
    """The refusals `record_incident` raises, checkable before anything runs -
    so a reproduction command is never executed for a record that will then be
    refused."""
    if failure_class is not None and failure_class not in FAILURE_CLASSES:
        raise ArchiveError(
            f"Unknown failure class '{failure_class}'; expected one of: "
            + ", ".join(FAILURE_CLASSES)
        )
    if turning_point and not (cites or []):
        raise ArchiveError(
            "a turning point is a causal claim - cite the record or artifact "
            "that shows the run never recovered past it"
        )


def run_repro(
    archive: Chronicle, session: str, project: Path, command: str, timeout: int = 900,
) -> dict[str, Any]:
    """Run an incident's reproduction command through the attested runner (NS-13e).

    The exit code is recorded at write time, by the runner, never reported by
    the author: argv with no shell, bounded by `timeout`. A shell operator is
    refused by name for the same reason `claim --verify` refuses it - the
    runner would pass it as a literal argument.
    """
    from .godmode_attest import run_check, split_command, unsupported_shell_grammar

    offending = unsupported_shell_grammar(command)
    if offending:
        raise ArchiveError(
            f"the reproduction command contains {offending!r}, which the runner cannot "
            "use: it runs as argv with no shell - put a multi-step reproduction in a "
            "script and cite that script")
    outcome = run_check(archive, session, Path(project), "repro", split_command(command),
                        timeout=timeout)
    code = int(outcome["exit_code"])
    # Not runnable only when the runner could not start it: a script that
    # itself exits 127 (a tool missing inside it) is a genuine red.
    never_started = str(outcome.get("detail", "")).startswith("command not found")
    state = (REPRO_NOT_REPRODUCING if code == 0
             else REPRO_NOT_RUNNABLE if never_started else REPRO_RED)
    return {"command": command, "citation": outcome["citation"], "exit_code": code,
            "state": state, "check_seq": outcome["sequence"],
            "detail": str(outcome.get("detail", ""))[:200]}


def record_incident(
    archive: Chronicle,
    subject: str,
    detail: str,
    *,
    failure_class: str | None = None,
    turning_point: bool = False,
    cites: list[str] | None = None,
    predicts: str | None = None,
    refuted_by: str | None = None,
    hypothesis: str | None = None,
    repro: dict[str, Any] | None = None,
    no_repro: str | None = None,
) -> dict[str, Any]:
    """One incident, optionally classed, optionally the turning point.

    `predicts` (absorbed 2026-09-11 from a multi-agent workspace's review
    rules): a mechanism that explains the observation is not evidence for
    it until it forbids something - name one consequence the hypothesis
    requires, a check that must come out a particular way, and go look.

    `refuted_by` (I-3): the one command or observation that would refute
    this incident's hypothesis, the same field a claim carries. Stored,
    not required - `godmode_falsifiers.due_falsifiers` is what ages an
    unrun one into a finding, not this call.

    `hypothesis` (I-4): the explanation itself, in the operator's own
    words - what `refuted_by` is a falsifier FOR. Neither alone is the
    record the two-reversals gate (`godmode_reversals.
    third_edit_without_incident`) reads for: a `refuted_by` with no stated
    `hypothesis` is a command with nothing named to refute, and the gate
    requires both before it lifts a refusal.

    The class comes from `FAILURE_CLASSES` or is absent - an off-list word
    is refused with the list rendered, because the whole value of a class
    is that two records can share it. `turning_point` marks the first
    failure the run never recovered from; it is a causal claim, so it
    requires at least one citation.

    `repro` (NS-13e) is `run_repro`'s result: the reproduction command and
    the exit code the runner saw at write time. `no_repro` is the stated
    reason there is none; the incident is then classed `underspecified-ask`
    unless a class was given, because the record shows the failure was
    never pinned to a command. `remember --kind incident` requires one of
    the two; internal writers may still record without either.
    """
    if repro is not None and no_repro:
        raise ArchiveError("an incident carries a reproduction or a reason it has none, not both")
    if no_repro is not None and not str(no_repro).strip():
        raise ArchiveError("--no-repro needs the reason there is no reproduction command")
    validate_incident(failure_class, turning_point, cites)
    advisories: list[str] = []
    if not predicts:
        advisories.append(
            "no prediction: a mechanism that explains what was seen is not evidence for it "
            "until it forbids something - record what the hypothesis predicts "
            "(--predicts \"<check that must go a particular way>\") and run that check")
    # An investigation opened is an investigation running on assumptions;
    # unstated ones are the six-round failure mode (audit 2026-09-01).
    if not any(r.get("kind") == "assumption"
               for r in archive.select(kind="assumption", limit=50)):
        advisories.append(
            "no assumption records exist - state the assumptions this "
            "investigation rests on (godmode remember --kind assumption) "
            "so a wrong one can be found instead of lived in")
    evidence = list(cites or [])
    data_repro: dict[str, Any] | None = None
    if repro is not None:
        data_repro = dict(repro)
        for cite in (f"{REPRO_PREFIX}{repro['command']}", f"seq:{repro['check_seq']}"):
            if cite not in evidence:
                evidence.append(cite)
        if repro.get("state") == REPRO_NOT_REPRODUCING:
            advisories.append(
                "the reproduction command passed at write time, so it does not reproduce "
                "this failure - a fix claim cannot pair against it; find the command that "
                "fails, then record the incident again")
        elif repro.get("state") == REPRO_NOT_RUNNABLE:
            advisories.append(
                "the reproduction command did not start (exit 127) - it reproduced "
                "nothing; cite a command that runs on this machine")
    elif no_repro is not None:
        data_repro = {"state": REPRO_WAIVED, "reason": str(no_repro).strip(),
                      "class": "underspecified-ask"}
        if failure_class is None:
            failure_class = "underspecified-ask"
    return archive.append(
        "incident", subject,
        {"detail": detail, "failure_class": failure_class,
            "predicts": predicts,
         "turning_point": bool(turning_point),
         "refuted_by": refuted_by,
         "hypothesis": hypothesis,
         **({"repro": data_repro} if data_repro is not None else {}),
         "advisories": advisories},
        evidence=evidence,
    )


# Fix round 1 (review finding 1): a bound on the detect-and-merge retry
# below. Each attempt writes one more superseding record; a subject racing
# past this many hand-offs is refused loudly instead of looping forever.
_PATTERN_RACE_MAX_ATTEMPTS = 3


def _fold_pattern_occurrences(
    records: list[dict[str, Any]], subject: str
) -> tuple[list[int], int]:
    """The latest `occurrences` for `subject` in `records`, plus the highest
    `sequence` among the pattern records folded - the fold's high-water
    mark, used by `record_pattern` to detect a concurrent writer it missed.
    """
    occurrences: list[int] = []
    high_water = 0
    for record in records:
        if record.get("kind") != "pattern" or str(record.get("subject", "")) != subject:
            continue
        occurrences = list((record.get("data") or {}).get("occurrences") or [])
        sequence = record.get("sequence")
        if isinstance(sequence, int) and sequence > high_water:
            high_water = sequence
    return occurrences, high_water


def record_pattern(
    archive: Chronicle,
    subject: str,
    workaround: str,
    pattern_class: str,
    *,
    occurrence: int | None = None,
    cites: list[str] | None = None,
) -> dict[str, Any]:
    """NS-12e: a recurring failure mode as a record that ACCUMULATES.

    The archive is append-only, so "append an occurrence to an existing
    pattern" cannot mean rewriting the first record - it means writing a
    NEW `pattern` record for the same subject whose `occurrences` carries
    every prior sighting plus this one, so the latest record is always the
    whole picture and a second sighting never mints a duplicate the way a
    naive `remember` would. `history --kind pattern` still shows every
    step as its own record (the evolution log); `list_patterns` below folds
    to the latest per subject (the index).

    `pattern_class` is checked against the same closed table
    `record_incident`'s `failure_class` uses - one vocabulary a preflight
    finding's own `class` field can be matched against
    (`godmode_preflight.pattern_workaround_findings`), rather than a second,
    independently-typed set of bucket names.

    Concurrency (fix round 1, review finding 1): the fold above and the
    `archive.append()` below are two separate chronicle operations, not
    one atomic step, so two processes calling `record_pattern` for the
    same subject at nearly the same time can both fold the same prior
    occurrences and each write a divergent "next" record. This cannot be
    closed by wrapping both in one `with archive.write_lock():` here -
    `append()` takes its own `write_lock()` on a fresh descriptor, and
    flock/msvcrt do not reenter across descriptors in the same process, so
    nesting would stall every call until the 20 s "archive is busy"
    timeout. Instead this detects the race AFTER the write: it remembers
    the highest sequence its own fold saw, and once `append()` returns it
    re-reads the subject's pattern records for any sequence strictly
    between that high-water mark and the record it just wrote - exactly
    the record its own fold missed. If found, it writes ONE more
    superseding record whose `occurrences` is the union, then repeats the
    check (a fresh writer could race the merge write too), bounded to
    `_PATTERN_RACE_MAX_ATTEMPTS` attempts before refusing loudly rather
    than looping forever or silently dropping an occurrence.
    """
    if pattern_class not in FAILURE_CLASSES:
        raise ArchiveError(
            f"Unknown pattern class '{pattern_class}'; expected one of: "
            + ", ".join(FAILURE_CLASSES)
        )
    prior_occurrences, fold_high_water = _fold_pattern_occurrences(
        archive.read_events(), subject
    )
    occurrences = list(prior_occurrences)
    if occurrence is not None and occurrence not in occurrences:
        occurrences.append(int(occurrence))
    if not occurrences:
        raise ArchiveError(
            "a new pattern needs at least one occurrence - pass "
            "--occurrence seq:<n> naming the record that shows one instance"
        )
    data = {"workaround": workaround, "class": pattern_class, "occurrences": occurrences}
    # dedupe=True (review finding 2): a retried `remember --kind pattern`
    # with the same subject/class/occurrence folds to byte-identical data
    # (the idempotency check just above already keeps a repeated
    # `--occurrence` from appearing twice in the list) - Chronicle's own
    # dedupe machinery returns the existing record instead of growing the
    # chain with a duplicate. A retry that adds a genuinely new occurrence,
    # or changes the workaround text, produces different data and is never
    # collapsed by this.
    written = archive.append("pattern", subject, data, evidence=cites or [], dedupe=True)
    if written.get("deduplicated"):
        return written

    attempts = 0
    while True:
        written_sequence = written.get("sequence")
        interlopers = [
            record for record in archive.read_events()
            if record.get("kind") == "pattern"
            and str(record.get("subject", "")) == subject
            and isinstance(record.get("sequence"), int)
            and fold_high_water < record["sequence"] < written_sequence
        ]
        if not interlopers:
            return written
        attempts += 1
        if attempts > _PATTERN_RACE_MAX_ATTEMPTS:
            raise ArchiveError(
                f"record_pattern: subject {subject!r} kept racing a "
                f"concurrent writer across {attempts - 1} merge attempts - "
                "run `godmode index patterns` to inspect the raw chain and "
                "reconcile the occurrence lists by hand"
            )
        merged = set(occurrences)
        for record in interlopers:
            merged.update((record.get("data") or {}).get("occurrences") or [])
        occurrences = sorted(merged)
        fold_high_water = written_sequence
        data = {"workaround": workaround, "class": pattern_class, "occurrences": occurrences}
        written = archive.append("pattern", subject, data, evidence=cites or [])


def list_patterns(archive: Any) -> list[dict[str, Any]]:
    """NS-12e's index: one row per pattern subject, folded to its latest
    record - read before deciding whether a new sighting is a fresh
    pattern or one more occurrence of an old one. `history --kind pattern`
    is the sibling evolution log, unfolded."""
    # NS-10e: a pattern another record has named via `--supersedes` (e.g.
    # merged into a broader pattern subject) drops out of the index the
    # same way any other latest-per-subject reader now excludes one.
    latest = latest_by_subject(
        [r for r in archive.read_events() if r.get("kind") == "pattern"])
    rows: list[dict[str, Any]] = []
    for subject, record in sorted(latest.items()):
        data = record.get("data") or {}
        occurrences = list(data.get("occurrences") or [])
        rows.append({
            "subject": subject,
            "class": data.get("class"),
            "workaround": data.get("workaround"),
            "occurrences": occurrences,
            "occurrence_count": len(occurrences),
            "sequence": record.get("sequence"),
        })
    return rows


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
    r"does not (?:exist|appear)|is absent|are absent|no such|"
    # Reversed word order and common idioms for the same claim shape - found
    # missing by an adversarial pass: "the search turned up nothing" passed
    # through this detector undetected because only "nothing found" (not
    # "found nothing") was covered.
    r"(?:found|turned up|came back|returned|yielded|showed) (?:nothing|empty))\b",
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


# Markdown emphasis stripped before any keyword matcher runs. Models bold
# exactly the words a matcher anchors on - "**no evidence** of X" carries
# asterisks through `\b`, and a matcher that has never seen its needle
# formatted is a matcher that fires on plain text only. Links keep their
# text and lose their target; emphasis marks vanish; code spans keep their
# content because a claim quoted in backticks is still the claim.
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3}|`)(?=\S)(.+?)(?<=\S)\1")


def _prose(text: str) -> str:
    """Markdown-normalised text for keyword matchers."""
    text = _MD_LINK.sub(r"\1", text)
    # Nested emphasis (***x***, **`y`**) unwraps one layer per pass.
    for _ in range(3):
        stripped = _MD_EMPHASIS.sub(r"\2", text)
        if stripped == text:
            break
        text = stripped
    return text


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
        text = _prose(str(record["data"].get("text", record["subject"])))
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
            # The subject is a digest (no prompt text in the store); the
            # keywords are what identifies the ask to a reader.
            "detail": "the session is waiting on '"
                      + " ".join([str(record.get("subject", ""))]
                                 + [str(k) for k in ((record.get("data") or {}).get("keywords") or [])])[:90]
                      + "', which the agent inferred rather than the operator stating; "
                      "state the assumption and carry on under it, or ask without stopping",
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
        text = _prose(str(data.get("text") or record["subject"]))
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
        text = _prose(str(data.get("text") or record["subject"]))
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


# Status vocabulary that says an item is being CARRIED - re-presented from a
# ledger, a handover, a checklist row - rather than freshly established. A
# carried label was measured drifting from code twice in one recorded night:
# a "pending sweep" listed six items already shipped, and a month-old OPEN
# marker put fixed work back on the critical path.
_CARRIED_STATUS = re.compile(
    r"\b(?:still (?:open|broken|pending|failing)|remains? (?:open|broken|unfixed)|"
    r"carried (?:forward|over)|not yet (?:fixed|done|shipped)|"
    r"pending (?:items?|list|sweep)|open items?)\b",
    re.IGNORECASE,
)


def carried_status_unverified(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M19: a carried status re-presented without fresh per-item evidence.

    A pending list is not evidence; each item it re-emits needs one cheap
    existence check against the code, or the list is a label describing a
    label. The claim clears by citing what was checked - a `file:` for the
    surface examined, or `searched:`/`scanned:` naming the sweep - in the
    same record that carries the status.
    """
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        data = record.get("data") or {}
        text = _prose(str(data.get("text") or record["subject"]))
        if not _CARRIED_STATUS.search(text):
            continue
        evidence = record.get("evidence", [])
        if any(e.startswith(("file:", "searched:", "scanned:")) for e in evidence):
            continue
        findings.append({
            "detector": "carried-status-unverified", "blocking": True,
            "detail": f"'{text[:70]}' re-presents a carried status with no fresh "
                      "check behind it; a pending list is not evidence - verify "
                      "each item against the code and cite what was examined",
            "citations": [f"seq:{record['sequence']}"],
        })
    return findings


def remedy_on_hypothesis(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M20: a plan or change built on a root still graded as a hypothesis.

    Designing the remedy is how an unconfirmed root hardens into a fact
    nobody re-examines - the fix's existence becomes the evidence. A plan may
    cite a hypothesis to TEST it; what fires here is a plan citing one as its
    foundation while no confirmed claim on the same subject exists.
    """
    grade_by_seq: dict[int, str] = {}
    confirmed_subjects: set[str] = set()
    for record in records:
        if record["kind"] != "claim":
            continue
        data = record.get("data") or {}
        grade = str(data.get("grade", "")).lower()
        grade_by_seq[int(record.get("sequence", 0))] = grade
        if grade not in {"hypothesis", "unknown", ""} and any(
                e.startswith("file:") for e in record.get("evidence", [])):
            confirmed_subjects.add(record.get("subject", ""))

    findings = []
    for record in records:
        if record["kind"] not in {"plan", "change"}:
            continue
        cited_hypotheses = [
            e for e in record.get("evidence", [])
            if e.startswith("seq:")
            and grade_by_seq.get(int(e.split(":", 1)[1] or 0), None)
            in {"hypothesis", "unknown"}
        ]
        if not cited_hypotheses:
            continue
        if record.get("subject", "") in confirmed_subjects:
            continue
        findings.append({
            "detector": "remedy-on-hypothesis", "blocking": False,
            "detail": f"{record['kind']} '{record['subject'][:60]}' cites "
                      f"{cited_hypotheses[0]} which is graded hypothesis, and no "
                      "confirmed claim on this subject exists; confirm the root "
                      "with a differential before building the remedy, or name "
                      "the plan as the experiment that will grade it",
            "citations": [f"seq:{record['sequence']}"] + cited_hypotheses[:2],
        })
    return findings


def absence_without_control(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M21: an absence claim whose search was never proven able to find.

    M18 demands the extent; this demands the instrument. A search that has
    never found anything is indistinguishable from a search that cannot -
    a malformed pattern, a wrong root, a harness whose failure shares a
    return value with 'no results'. The claim clears by citing a control:
    a probe of a known-present target through the same instrument
    (`control:` evidence), or a second independent method (`second:`).
    Advisory, because M18 already blocks the extent-free form.
    """
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        data = record.get("data") or {}
        text = _prose(str(data.get("text") or record["subject"]))
        if not _ABSENCE.search(text):
            continue
        evidence = record.get("evidence", [])
        stated_extent = any(e.startswith(("searched:", "scanned:", "population:"))
                            for e in evidence) or _EXTENT.search(text)
        if not stated_extent:
            continue  # M18's finding; one defect, one detector.
        if any(e.startswith(("control:", "second:")) for e in evidence):
            continue
        findings.append({
            "detector": "absence-without-control", "blocking": False,
            "detail": f"'{text[:70]}' asserts an absence from a search never "
                      "proven able to find - run the same instrument against a "
                      "known-present target (`control:`) or prove the absence a "
                      "second independent way (`second:`); an empty result from "
                      "a broken probe reads identically to a true negative",
            "citations": [f"seq:{record['sequence']}"],
        })
    return findings


# A change whose own description quantifies over a class. "Every caller",
# "all sites", "never again" - each is a promise to enumerate, and a
# one-file diff under it means the promise was kept at one member. Recorded
# five times in one session as the same shape: the fix landed on the
# reported instance and the user found the sibling.
_CLASS_CLAIM = re.compile(
    r"\b(?:every|all|each|any)\s+(?:caller|site|path|lane|surface|consumer|"
    r"reader|writer|branch|route|usage|instance|occurrence)s?\b|"
    r"\bnever\s+(?:again|recurs?)\b|\bwhole\s+class\b|\bclass[- ]wide\b",
    re.IGNORECASE,
)


def class_claim_single_file(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M22: a change quantifying over a class while touching one file.

    'Scoped fix' means don't change unrelated surfaces, not don't check the
    identical sibling. A change that says 'every caller' and diffs one file
    either swept and found nothing - in which case the sweep is citable
    (`searched:`) - or never swept, in which case the user becomes the sweep.
    """
    findings = []
    for record in records:
        if record["kind"] != "change":
            continue
        data = record.get("data") or {}
        text = _prose(" ".join(str(part) for part in (
            record.get("subject", ""), data.get("plan", ""))))
        if not _CLASS_CLAIM.search(text):
            continue
        files = data.get("files") or []
        if len(files) != 1:
            continue
        evidence = record.get("evidence", [])
        if any(e.startswith(("searched:", "scanned:")) for e in evidence):
            continue
        findings.append({
            "detector": "class-claim-single-file", "blocking": False,
            "detail": f"change '{record['subject'][:60]}' quantifies over a class "
                      f"and touches one file ({files[0]}); cite the sweep that "
                      "cleared the siblings (`searched:`) or narrow the claim to "
                      "the instance it fixed",
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
        + carried_status_unverified(records)
        + remedy_on_hypothesis(records)
        + absence_without_control(records)
        + class_claim_single_file(records)
    )
    blocking = [f for f in findings if f["blocking"]]
    return {
        "records_scanned": len(records),
        "findings": findings,
        "blocking": bool(blocking),
        "verdict": "mistake-class-detected" if blocking else "clean",
    }


def obligation_sibling_advisory(archive: Any, subject: str,
                                value: str) -> str | None:
    """One sentence when a new obligation is an open one in new clothes.

    Field report (2026-09-01): a version-bearing subject mints a fresh
    obligation every bump, subject-keyed supersession never links them,
    and the corpses nag beside the living one. At record time the overlap
    is cheapest to name: >=3 shared salient words with an OPEN obligation
    of a different subject means close or supersede the elder now.

    Fix round 1 (NS-10e task-6, ruling 4): now routed through
    `latest_by_subject` - the exact `supersedes` link this docstring
    describes as absent now exists, and a superseded elder should stop
    nagging here the same way it stops nagging in `status.remaining()`.
    """
    from .godmode_sources import _salient_words

    new_vocab = _salient_words(f"{subject} {value}")
    if not new_vocab:
        return None
    try:
        latest = latest_by_subject(archive.select(kind="obligation", limit=200))
    except Exception:  # noqa: BLE001
        return None
    for elder_subject, record in latest.items():
        if elder_subject == subject:
            continue
        data = record.get("data") or {}
        if str(data.get("status", "open")) in ("closed", "done", "retired"):
            continue
        vocab = _salient_words(f"{elder_subject} {data.get('value', '')}")
        if len(new_vocab & vocab) >= 3:
            return (
                f"an open obligation '{elder_subject}' shares this one's "
                "vocabulary - if this replaces it, supersede or close the "
                "elder now (`godmode remember --kind obligation --subject "
                f"\"{elder_subject}\" --status closed`), or the nag will "
                "surface both forever.")
    return None


import re as _re

_BUILD_VOCAB = _re.compile(
    r"(?i)\b(?:build|implement|add|create|wire|introduce|design|ship)\b")

_DIFFERS_VOCAB = _re.compile(
    r"(?i)\b(?:differs?|unlike|replaces?|supersedes?|extends?|beyond)\b")


def reinvention_advisory(archive: Any, subject: str, value: str) -> str | None:
    """One sentence when a build-shaped record overlaps a shipped capability.

    The agent that reinvents discovers the original mid-implementation,
    after the cost (operator challenge, 2026-09-03; the corpus's
    inventory-preflight rule as machinery). At record time: >=4 shared
    salient words with a SHIPPED capability - a version record's note, a
    closed obligation, or a ship-vocabulary claim - and the elder is
    named. Saying what differs silences it: a deliberate replacement is
    not a reinvention.
    """
    from .godmode_sources import _salient_words

    text = f"{subject} {value}"
    if not _BUILD_VOCAB.search(text) or _DIFFERS_VOCAB.search(text):
        return None
    new_vocab = _salient_words(text)
    if len(new_vocab) < 4:
        return None
    best: tuple[int, int, str] | None = None
    try:
        candidates: list[dict] = []
        for record in archive.select(kind="version", limit=100):
            candidates.append(record)
        for record in archive.select(kind="obligation", limit=200):
            data = record.get("data") or {}
            if str(data.get("status", "open")) in ("closed", "done",
                                                   "resolved"):
                candidates.append(record)
        for record in archive.select(kind="claim", limit=200):
            data = record.get("data") or {}
            if data.get("resolves"):
                continue
            if _re.search(r"(?i)\b(?:shipped|built|landed|wired)\b",
                                   str(data.get("text", ""))):
                candidates.append(record)
    except Exception:  # noqa: BLE001
        return None
    for record in candidates:
        data = record.get("data") or {}
        elder_text = " ".join(
            str(data.get(field) or "")
            for field in ("value", "text", "note")) + \
            f" {record.get('subject', '')}"
        vocab = _salient_words(elder_text)
        overlap = len(new_vocab & vocab)
        if overlap >= 4:
            key = (overlap, int(record.get("sequence", 0)),
                   str(record.get("subject", ""))[:80])
            if best is None or key > best:
                best = key
    if best is None:
        return None
    return (
        f"the record already holds this capability at seq {best[1]} "
        f"('{best[2]}') - reuse it, or say what differs; discovering the "
        "original mid-implementation is the expensive way")


def validate_load_bearing(load_bearing: bool, cites: list[str] | None) -> None:
    """An assumption marked load-bearing must say what fails without it.

    The product already forces falsifiability after the fact: an incident's
    hypothesis is not evidence until it forbids something. Nothing forced it
    before the work started, so a plan could rest entirely on one unexamined
    premise while every record about it looked locally justified.

    This is deliberately the same contract `turning_point` holds above, not a
    parallel one. Both are causal claims - "the run never recovered past this"
    and "remove this and the plan fails" - and a causal claim with no citation
    is an assertion wearing a record's clothes. A second convention would drift
    from the first, which is the duplicate-authority failure this codebase has
    been bitten by more than once.
    """
    if not load_bearing:
        return
    if not [c for c in (cites or []) if str(c).strip()]:
        raise ArchiveError(
            "a load-bearing assumption is a causal claim - pass --evidence "
            "naming what fails without it. 'Requires evidence' alone does not "
            "tell the next reader what the assumption was holding up."
        )
