"""I-4: the two-reversals gate.

Doctrine already says stop after two failed fixes and go read instead of
trying a third time blind; nothing enforced it at the one moment it would
matter - the edit itself. `godmode_loop._prior_fix_reversal` is the closest
existing detector, and it is advisory: it names a finding in a loop report
nobody has to read before typing the next edit. This module is the gate
version, read from the pre-tool boundary (`hooks/godmode_session_hook.py`'s
Edit/Write path) before the edit is allowed to happen at all.

**What counts as "the same check".** A `godmode retest --run` attestation
(`godmode_attest.run_check`, subject `check:{name}` where `name` is
`retest:{runner}`) never names a source file directly - its one evidence
entry is `cmd:<the pinning test modules' command line>`
(`godmode_retest.commands`). The link back to `path` is therefore built the
same way `godmode_closure.py` (I-6) already builds it for the same
attestations: which test files `godmode_retest.pinning_tests` says pin
`path`, turned into the dotted module name `godmode_retest.commands` bakes
into the command line, matched as a substring of the attestation's `cmd:`
evidence. Two attestations count as "the same check" when they share BOTH
that module-name link AND their `subject` string exactly (`check:retest:
unittest` and `check:retest:vitest` are different checks even if both
happen to cover `path` - a check is a runner, and a red run of one says
nothing about the other).

**What counts as "an edit to the file".** Only `edit-recorded` actions
(`hooks/godmode_post_edit.py`, `EDIT_RECORD_SUBJECT`) naming `path` - the
same record `godmode_closure.py` reads for "was this edited". A git-applied
patch or a tool outside `_EDIT_TOOL_NAMES` leaves none, and is invisible to
this gate exactly as it is to that one; this gate refuses only what its own
evidence shows, never what it merely suspects.

**Counting rule (fix round 1, review of ac48f2d).** `red_runs` is the
NEWEST pair of blocked attestations for the check, not the oldest
(`seqs[-2:]`, not `seqs[:2]`) - the first pair taken for the life of the
archive would let the first incident ever recorded, anywhere, with both
fields disarm this gate for every file forever, since `red_runs[1]` would
never move and the old incident would always read as "after" it. Taking
the newest pair means a fresh red/red/edit/edit loop always re-arms the
gate on its own, no matter how many incidents predate it.

The two red retests bracket the loop, and the brief's own word "bracket"
is load-bearing: at least one `edit-recorded` for `path` must fall
STRICTLY BETWEEN `red_runs[0]` and `red_runs[1]` (the fix attempt that did
not hold - without it, two red runs back to back with no edit between them
is two confirmations of the same failure, not a loop, and refusing the
next few ordinary Edit calls on that alone was a false refusal). It is
refused unless an `incident` recorded after `red_runs[1]` carries both a
`hypothesis` and a `refuted_by` - the record that says the reading actually
happened, not just that a claim was made. `now` is accepted for parity with
the archive's other point-in-time detectors; nothing here reasons about
wall-clock time; sequence order is the whole ordering this gate needs.

**The edit count is anchored separately from the bracket (fix round 2,
re-review of 039b35c).** Counting edits from `red_runs[0]` - the newest
pair's own left edge - was wrong: that edge slides forward on every new red
run, so a refused loop cleared itself the instant one more `godmode retest
--run` came back red with no edit in between (the exact next keystroke this
gate encourages), and the disciplined shape it exists to catch - edit,
retest red, edit, retest red, ... - could never trip it at all, because the
edit count reset on every iteration. The count instead anchors at the
OLDEST blocked run of this check that is not preceded by a lifting
incident: every `hypothesis`+`refuted_by` incident on record moves the
anchor forward, once, to the first red run after it (never backward, and
never past a red run that was already counted) - so a fresh reset still
happens exactly when the round-1 fix required it (finding 1.1's re-arm), but
adding more red runs with no new incident can only ever raise the edit
count from here, never lower it. `red_runs` itself - the bracket's two
endpoints and the incident-lift cutoff - stays the newest pair; only the
count anchor moved.

**Cheap on the common case.** Every Edit/Write PreToolUse call reaches this
gate, and on an ordinary edit - no loop history at all - the correct answer
is `None` on every one of them. `retest_module_names` (`godmode_retest.
pinning_tests`) shells out to `git ls-files` twice and reads and regex-scans
every test file in the project; measured at 1.3-3.1s per call, it must never
run before a cheaper check has a chance to say "nothing to see here" first.
`archive.read_events()` is disk-indexed and cached per instance, and the hook
has usually already paid for it elsewhere this call - so the read happens
FIRST, and `pinning_tests` runs only when at least one `check:retest:*`
subject already has two `blocked` attestations on record (the one
precondition every refusal needs, checked without needing to know which
file it is about yet).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .godmode_constants import EDIT_RECORD_SUBJECT
from .godmode_metrics import _action_paths
from .godmode_retest import retest_module_names

#: Two failed fixes on one check is the trip point - the doctrine's own number.
_REQUIRED_REVERSALS = 2

_REMEDY = ('godmode remember --kind incident "<what>" --repro "<failing cmd>" '
           '--hypothesis "..." --refuted-by "<cmd>"')

# Fix round 1, S1: `_retest_module_names` used to be its own copy here,
# wrapping `path` in a one-element list; now a thin call to the one shared
# `godmode_retest.retest_module_names`, the same helper `godmode_closure`
# and `godmode_graph` call, so the file->module bridge cannot drift into
# three independently-typed copies of the same three lines.


def _any_check_has_two_blocked_runs(records: list[dict[str, Any]]) -> bool:
    """Whether any `check:retest:*` subject at all has two or more `blocked`
    attestations on record - the one precondition every refusal needs,
    checked with no knowledge yet of which file or which module names are
    involved. Read from already-loaded records, never from disk itself:
    the point is to let an ordinary edit (the overwhelming common case)
    skip `retest_module_names`'s `git ls-files` calls entirely, not to
    change what a positive answer means."""
    counts: dict[str, int] = {}
    for record in records:
        if record.get("kind") != "attestation":
            continue
        subject = str(record.get("subject", ""))
        if not subject.startswith("check:retest:"):
            continue
        if (record.get("data") or {}).get("status") != "blocked":
            continue
        counts[subject] = counts.get(subject, 0) + 1
        if counts[subject] >= _REQUIRED_REVERSALS:
            return True
    return False


def _blocked_retests_by_subject(
    records: list[dict[str, Any]], module_names: set[str],
) -> dict[str, list[int]]:
    """`{subject: [sequence, ...]}` for every `check:retest:*` attestation
    whose `status` is `blocked` and whose `cmd:` evidence names one of
    `module_names` - grouped by subject because "the same check" means the
    same runner, not merely any two red runs that happen to both cover the
    file. Sequences are sorted oldest first; when two runners both qualify,
    the one picked by the caller is the first in record-insertion order,
    not the most recently red one - harmless while a project runs at most
    one retest runner per file, worth revisiting if that stops holding."""
    by_subject: dict[str, list[int]] = {}
    if not module_names:
        return by_subject
    for record in records:
        if record.get("kind") != "attestation":
            continue
        subject = str(record.get("subject", ""))
        if not subject.startswith("check:retest:"):
            continue
        data = record.get("data") or {}
        if data.get("status") != "blocked":
            continue
        evidence = " ".join(str(item) for item in record.get("evidence") or [])
        if not any(name in evidence for name in module_names):
            continue
        by_subject.setdefault(subject, []).append(record["sequence"])
    for seqs in by_subject.values():
        seqs.sort()
    return by_subject


def _edit_sequences(records: list[dict[str, Any]], path: str) -> list[int]:
    """Every `edit-recorded` sequence naming `path`, oldest first."""
    out = [
        record["sequence"] for record in records
        if record.get("kind") == "action" and record.get("subject") == EDIT_RECORD_SUBJECT
        and path in _action_paths(record.get("data") or {})
    ]
    out.sort()
    return out


def _incident_lifts_it(records: list[dict[str, Any]], after_seq: int) -> bool:
    """An `incident` recorded after `after_seq` naming both a `hypothesis`
    and a `refuted_by` - the record that the reading actually happened,
    escaped by deliberate evidence rather than by rephrasing the edit."""
    for record in records:
        if record.get("kind") != "incident" or record["sequence"] <= after_seq:
            continue
        data = record.get("data") or {}
        if str(data.get("hypothesis") or "").strip() and str(data.get("refuted_by") or "").strip():
            return True
    return False


def _lifting_incident_sequences(records: list[dict[str, Any]]) -> list[int]:
    """Every `incident` sequence naming both a `hypothesis` and a
    `refuted_by`, oldest first - the same criterion `_incident_lifts_it`
    checks for one cutoff, read once here as a full list so `_loop_anchor`
    can walk every one of them, not just the newest bracket's."""
    out = [
        record["sequence"] for record in records
        if record.get("kind") == "incident"
        and str((record.get("data") or {}).get("hypothesis") or "").strip()
        and str((record.get("data") or {}).get("refuted_by") or "").strip()
    ]
    out.sort()
    return out


def _loop_anchor(seqs: list[int], lifting_incidents: list[int]) -> int:
    """The oldest blocked run in `seqs` (ascending) not preceded by a
    lifting incident - fix round 2 (re-review of 039b35c, required finding
    1). Each lifting incident moves the anchor forward to the first red run
    after it, once: an incident with nothing red after it yet changes
    nothing (there is no fresh loop to anchor to), and an incident that
    already moved the anchor past some red run never moves it BACKWARD for
    an earlier one. `seqs` is `by_subject`'s list for one check subject,
    already sorted ascending; `lifting_incidents` order does not matter -
    every one is applied, and only the furthest-forward result wins."""
    anchor = seqs[0]
    for incident_seq in lifting_incidents:
        after = [seq for seq in seqs if seq > incident_seq]
        if after and min(after) > anchor:
            anchor = min(after)
    return anchor


def third_edit_without_incident(
    archive: Any, path: str, now: Any = None,
) -> dict[str, Any] | None:
    """Refuse the third edit to `path` since the NEWEST two red retests of
    one check, unless an incident recorded after the second of that pair
    names both a hypothesis and its falsifier.

    Returns `None` when there is nothing to refuse - no `check:retest:*`
    subject anywhere has two blocked runs yet (checked first, cheaply,
    before anything file-specific is computed), no closure links such a
    check to `path`, no edit to `path` falls strictly between the newest
    pair's two red runs, fewer than two edits to `path` are recorded since
    the loop anchor (the oldest red run not preceded by a lifting
    incident - see `_loop_anchor`), or an incident already lifts the
    current pair. Otherwise `{"check", "red_runs": [seq, seq], "edits": n,
    "remedy"}`.
    """
    records = archive.read_events()
    if not _any_check_has_two_blocked_runs(records):
        return None
    normalized = str(path).replace("\\", "/")
    project = Path(archive.anchor.project_root)
    module_names = retest_module_names(project, [normalized])
    if not module_names:
        return None
    by_subject = _blocked_retests_by_subject(records, module_names)
    check_subject: str | None = None
    red_runs: list[int] = []
    for subject, seqs in by_subject.items():
        if len(seqs) >= _REQUIRED_REVERSALS:
            check_subject = subject
            # The NEWEST pair, not the oldest: taking `seqs[:2]` would let
            # the first incident ever recorded, anywhere, with both fields
            # disarm this gate for this check forever, since `red_runs[1]`
            # would never move past it. The newest pair means a fresh
            # red/edit/red/edit loop always re-arms the gate on its own.
            red_runs = seqs[-_REQUIRED_REVERSALS:]
            # Bound explicitly here, not read back below as the loop
            # variable `seqs` (fix round 3, observation) - correct today
            # only because the loop always `break`s right after this, but
            # binding it beside `red_runs` makes that safe by construction
            # instead of by every no-break path returning first.
            window = list(seqs)
            break
    if check_subject is None:
        return None
    all_edits = _edit_sequences(records, normalized)
    # The bracket the brief names: at least one edit strictly BETWEEN some
    # consecutive pair of this check's blocked runs (fix round 3, required
    # finding N-1) - checked against EVERY consecutive pair in `window`,
    # not only the newest pair `red_runs`. Bracketing only `red_runs` let
    # two red runs land back to back with nothing edited between THEM
    # clear a live refusal and disarm the gate for the rest of the round,
    # even though an earlier pair in the same run of blocked retests still
    # had a fix attempt bracketed between it. Two red runs with no edit
    # between them still contribute no candidate pair on their own (that
    # keeps `test_two_back_to_back_reds_with_no_edit_between_do_not_refuse`
    # green), but they no longer erase the pairs behind them.
    between = [
        edit
        for a, b in zip(window, window[1:])
        for edit in all_edits
        if a < edit < b
    ]
    if not between:
        return None
    # The edit count anchors at the oldest red run of THIS check not
    # preceded by a lifting incident (fix round 2, required finding 1) -
    # separate from `red_runs`, which stays the newest pair for the
    # incident cutoff below. Anchoring at `red_runs[0]` instead (round 1's
    # mistake) slid the count forward on every new red run, so a live
    # refusal cleared itself with one more retest and the disciplined
    # edit/retest/edit/retest loop could never trip it at all.
    lifting_incidents = _lifting_incident_sequences(records)
    anchor = _loop_anchor(window, lifting_incidents)
    since_anchor = [seq for seq in all_edits if seq > anchor]
    if len(since_anchor) < _REQUIRED_REVERSALS:
        return None
    if _incident_lifts_it(records, red_runs[1]):
        return None
    return {
        "check": check_subject,
        "red_runs": red_runs,
        "edits": len(since_anchor),
        "remedy": _REMEDY,
    }
