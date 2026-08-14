"""Witness + independent-checker verdicts (U-V1).

"Agent claims it fixed X" becomes admissible only as: a claimed value stated
explicitly, a data-only witness sufficient to recompute it, and a checker
that recomputes from the witness alone (never invoking the producer that
made the claim) and asserts against the stated value.

Three dispositions, never two. Structural preconditions of the witness are
validated BEFORE the checker ever runs: a missing file or an unresolvable
seq means the claim was never judged (`witness-malformed`), which is a
different fact from "judged and found false" (`refuted`). A checker that
cannot start or never finishes is the same failure - "the checker could not
judge" is not "the claim is false" - so `FileNotFoundError` and
`TimeoutExpired` also land on `witness-malformed`, never `refuted`.

Two invariants are enforced at the moment a verdict record would be written,
not left for a later reader to notice:

- Drive-vs-acquit: `acquitted_by: "self"` may attest execution completeness
  only. A `disposition: "confirmed"` needs an independent checker; a
  self-acquitted "confirmed" is refused outright.
- Terminated-vs-truncated: a `run_state: "truncated"` run (a budget or
  timeout cutoff) can never be recorded `confirmed` - budget exhaustion must
  not impersonate completion.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

DISPOSITIONS = ("confirmed", "refuted", "witness-malformed")
RUN_STATES = ("terminated", "truncated")
ACQUITTED_BY = ("independent", "self")

_SUBJECT_CAP = 120


def _split_command(command: str) -> list[str]:
    # Posix-mode shlex (the default) treats backslash as an escape character,
    # which mangles a bare Windows path (C:\Users\...\python.exe) before the
    # OS ever sees it. Non-posix mode leaves backslashes alone.
    return shlex.split(command, posix=os.name != "nt")


def _witness_readable(project: Path, archive: Chronicle, kind: str, value: str) -> bool:
    """Structural precondition only: can this witness be recomputed from at all.

    Never a statement about what it says - that is the checker's job, run
    only once this returns True.
    """
    if kind == "file":
        return (project / value).is_file()
    if kind == "seq":
        try:
            sequence = int(value)
        except ValueError:
            return False
        return any(record["sequence"] == sequence for record in archive.read_events())
    return False


def _append_verdict(
    archive: Chronicle,
    claim: str,
    claimed_value: str,
    witness_kind: str | None,
    witness_value: str | None,
    checker_cmd: str,
    disposition: str | None,
    run_state: str,
    acquitted_by: str,
    checker_exit: int | None,
) -> dict[str, Any]:
    if disposition == "confirmed" and acquitted_by == "self":
        raise ArchiveError(
            "acquitted_by='self' may attest execution completeness only; a "
            "'confirmed' disposition needs an independent checker "
            "(acquitted_by='independent') - self-acquitted quality is refused"
        )
    if disposition == "confirmed" and run_state == "truncated":
        raise ArchiveError(
            "a truncated run cannot be recorded 'confirmed'; budget or "
            "timeout exhaustion must not impersonate completion"
        )
    evidence: list[str] = []
    if checker_cmd:
        evidence.append(f"cmd:{checker_cmd}")
    if witness_kind and witness_value is not None:
        evidence.append(f"{witness_kind}:{witness_value}")
    if checker_exit is not None:
        evidence.append(f"checker_exit:{checker_exit}")
    data = {
        "claim": claim,
        "claimed_value": claimed_value,
        "witness": {"kind": witness_kind, "ref": witness_value},
        "checker": f"cmd:{checker_cmd}" if checker_cmd else None,
        "disposition": disposition,
        "run_state": run_state,
        "acquitted_by": acquitted_by,
    }
    subject = (claim or "verdict")[:_SUBJECT_CAP]
    return archive.append("verdict", subject, data, evidence=evidence)


def record_verdict(
    archive: Chronicle,
    project: Path,
    claim: str,
    claimed_value: str,
    witness_ref: str,
    checker_cmd: str,
    *,
    run_state: str = "terminated",
    acquitted_by: str = "independent",
    timeout: int = 300,
) -> dict[str, Any]:
    """Run an independent checker against a witness and record the verdict.

    The checker never sees the producer of the claim - only the witness. It
    is invoked exactly once the witness has passed structural validation
    (exists and is readable for `file:`, resolves in the archive for
    `seq:`); a witness that fails that check means the checker never runs at
    all, and the record says so (`witness-malformed`), not `refuted`.
    """
    if run_state not in RUN_STATES:
        raise ArchiveError(
            f"Unknown run_state '{run_state}'; expected one of {', '.join(RUN_STATES)}"
        )
    if acquitted_by not in ACQUITTED_BY:
        raise ArchiveError(
            f"Unknown acquitted_by '{acquitted_by}'; expected one of {', '.join(ACQUITTED_BY)}"
        )

    if ":" in witness_ref:
        witness_kind, witness_value = witness_ref.split(":", 1)
    else:
        witness_kind, witness_value = "unknown", witness_ref

    checker_exit: int | None = None
    if not _witness_readable(project, archive, witness_kind, witness_value):
        disposition = "witness-malformed"
    else:
        try:
            completed = subprocess.run(
                _split_command(checker_cmd),
                cwd=str(project),
                timeout=timeout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            checker_exit = completed.returncode
            disposition = "confirmed" if checker_exit == 0 else "refuted"
        except FileNotFoundError:
            # The checker could not run at all - "could not judge" is not
            # "judged false".
            disposition = "witness-malformed"
        except subprocess.TimeoutExpired:
            disposition = "witness-malformed"

    return _append_verdict(
        archive, claim, claimed_value, witness_kind, witness_value, checker_cmd,
        disposition, run_state, acquitted_by, checker_exit,
    )


def attest_run_state(
    archive: Chronicle,
    run_state: str = "terminated",
    *,
    claim: str = "",
) -> dict[str, Any]:
    """Self-attestation of execution completeness only - no quality judgment.

    `acquitted_by` is fixed at `"self"`: an agent can attest that it ran to
    completion (or was cut off) without that being mistaken for an
    independent checker's verdict on whether the result is correct.
    `disposition` stays `None` - self acquits execution, never quality.
    """
    if run_state not in RUN_STATES:
        raise ArchiveError(
            f"Unknown run_state '{run_state}'; expected one of {', '.join(RUN_STATES)}"
        )
    return _append_verdict(
        archive, claim, "", None, None, "", None, run_state, "self", None,
    )


def verdict_for(archive: Chronicle, seq: int) -> dict[str, Any] | None:
    """The verdict record at this sequence, or None when it does not exist."""
    for record in archive.select(kind="verdict", limit=2000):
        if record["sequence"] == seq:
            return record
    return None
