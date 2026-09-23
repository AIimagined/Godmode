"""Shared fixtures for the ONE thing `godmode law compile` now asks of a
lesson before its guard becomes law.

NS-2 (0.3.28 Plan 5 Task 2, fix round 1, B1): `godmode_law._guarded_lessons`
admits a guarded lesson only when it carries approval lineage
(`approval_seq`, written by `godmode_lessons.approve` and by nothing else)
or was written with operator trust. Before that gate, any process could
append `{"status": "active", "generalized_guard": "<anything>"}` and read
its own sentence back out of `GODMODE-CODE-OF-LAW.md` on the next compile.

Every law-side test that needs a lesson to COMPILE goes through one of the
three helpers here, so the next change to the admission rule has one place
to move rather than twenty fixture writes to chase:

- `graduated_lesson` - the full, real path: a structured candidate,
  promoted under one agent id, approved under another. Use this wherever
  the test is about the promotion pipeline, or wants a record shaped the
  way a real graduated law is shaped. It writes THREE records where the old
  fixture wrote one, so a test that pins exact sequence numbers or record
  counts must read them off the returned record rather than assuming 1.
- `operator_lesson` - the carve-out, for a test that only needs a standing
  law to exist and is not about how it got there. One record, one write,
  `writer: operator`. An operator typing their own guard IS the second
  actor; that is the rule, not a test-only shortcut.
- `OPERATOR_RECORD_FIELDS` - for the handful of tests that build record
  DICTS by hand against a fake archive rather than appending to a real
  `Chronicle`. Spread into the record (not into its `data`): `writer` is a
  top-level field of the sealed record, which is exactly why it cannot be
  back-filled by whatever wrote the payload.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any
from unittest import mock

# The five NS-10j fields under the archive's own canonical keys, complete,
# so `godmode_lessons.promote` has nothing to refuse. `generalized_guard` is
# overridden per call; the rest are fixture prose and are never asserted on.
STRUCTURED_FIELDS: dict[str, str] = {
    "root_cause": "the step ran before its precondition was checked",
    "correction": "check the precondition first, then run the step",
    "reflection": "any step with a precondition needs it named, not assumed",
    "refuted_by": "the step succeeds with the precondition unmet",
}

# Spread into a hand-built record dict, never into its `data`.
OPERATOR_RECORD_FIELDS: dict[str, Any] = {"writer": "operator", "trust": 3}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def graduated_lesson(archive: Any, subject: str, guard: str, *,
                     value: str = "observed", promoter: str = "fixture-author",
                     approver: str = "fixture-checker",
                     **extra: Any) -> dict[str, Any]:
    """Write `subject`'s guard the way a real one reaches the law: a fully
    structured CANDIDATE, a `lesson_promotion` under `promoter`, and a
    `lesson_approval` under a different actor (`approver`) with its own
    re-run hash. Returns the GRADUATED `lesson` record - the active one
    carrying `approval_seq`, which is the record `law compile` reads.

    `extra` lands in the candidate's `data` and is carried forward onto the
    graduated record by `approve` (`standing=True`, a custom `value`, an
    `enforce` predicate). `status` is not overridable: the candidate must
    be a candidate for `promote` to have anything to grant.
    """
    from godmode_runtime.godmode_lessons import approve, promote

    data = {**STRUCTURED_FIELDS, "value": value, **extra,
            "generalized_guard": guard, "status": "candidate"}
    candidate = archive.append("lesson", subject, data, evidence=[])
    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": promoter}, clear=False):
        promotion = promote(
            archive, candidate["sequence"],
            [f"seq:{candidate['sequence']}"], _digest(f"author:{subject}:{guard}"))
    with mock.patch.dict(os.environ, {"GODMODE_AGENT_ID": approver}, clear=False):
        outcome = approve(
            archive, promotion["sequence"], _digest(f"checker:{subject}:{guard}"))
    graduated = None
    for record in archive.read_events(verify=False):
        if int(record.get("sequence", 0)) == int(outcome["graduated_seq"]):
            graduated = record
            break
    assert graduated is not None, "approve() reported a graduation it did not write"
    return graduated


def operator_lesson(archive: Any, subject: str, guard: str, *,
                    value: str = "observed", status: str = "active",
                    **extra: Any) -> dict[str, Any]:
    """The carve-out path: one `lesson` record, written with operator trust,
    which compiles with no promotion because the operator IS the second
    actor. For tests that need a law to exist and are not about how it got
    there."""
    data = {"value": value, **extra, "generalized_guard": guard, "status": status}
    return archive.append("lesson", subject, data, evidence=[],
                          as_operator=True, operator_verified=True)
