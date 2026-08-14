"""Witness + independent-checker verdicts (U-V1).

"Agent claims it fixed X" becomes admissible only as: a claimed value stated
explicitly, a data-only witness sufficient to recompute it, and a checker
that recomputes from the witness alone (never invoking the producer that
made the claim) and asserts against the stated value.

Three dispositions, never two. Structural preconditions of the witness are
validated BEFORE the checker ever runs: a missing file or an unresolvable
seq means the claim was never judged (`witness-malformed`), which is a
different fact from "judged and found false" (`refuted`). A checker that
cannot be parsed, is empty, cannot start, or never finishes is the same
failure - "the checker could not judge" is not "the claim is false" - so all
of those also land on `witness-malformed`, never `refuted`, and never as an
uncaught exception: an adversarial checker string is a malformed judge, not
a fourth outcome.

Two invariants are enforced at the archive seam itself (`Chronicle.append`'s
`KIND_INVARIANTS` registry, registered below at import), not just by the
functions in this module - so a future caller that builds a `verdict`
record via a raw `archive.append(...)` (the experiment ledger among them)
is held to the same rule as `record_verdict`/`attest_run_state`:

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

from .godmode_chronicle import Chronicle, register_kind_invariant
from .godmode_errors import ArchiveError

DISPOSITIONS = ("confirmed", "refuted", "witness-malformed")
RUN_STATES = ("terminated", "truncated")
ACQUITTED_BY = ("independent", "self")

_SUBJECT_CAP = 120


def _split_command(command: str) -> list[str]:
    """Tokenize a checker command, safe for a bare or quoted Windows path.

    Posix-mode shlex (the plain-`shlex.split(command)` default) treats
    backslash as an escape character, which mangles a bare Windows path
    (`C:\\Users\\...\\python.exe`) before the OS ever sees it. Non-posix mode
    leaves backslashes alone, at the cost of leaving surrounding quote
    characters attached to the token instead of consuming them - so a path
    quoted to protect embedded spaces (`"C:\\Program Files\\...\\python.exe"`)
    comes back as a single token that still carries its own quote marks and
    fails to resolve as a file. Stripping one matching pair of outer quotes
    off each token (the same thing posix mode would have consumed) covers
    that case without reintroducing the backslash-eating problem posix mode
    has on this platform. May raise ValueError on unbalanced quoting -
    callers treat that as "could not parse", not a crash.
    """
    if os.name != "nt":
        return shlex.split(command)
    return [_strip_outer_quotes(token) for token in shlex.split(command, posix=False)]


def _strip_outer_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


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


def _run_checker(
    checker_cmd: str, project: Path, timeout: int
) -> tuple[str, str | None, int | None]:
    """Launch the checker; every failure to even judge lands on witness-malformed.

    Returns (disposition, malformed_reason, checker_exit). malformed_reason
    is None whenever disposition is confirmed/refuted - it names WHY the
    checker could not judge, so the record explains the gap instead of
    silently folding "could not run" into "false".
    """
    try:
        argv = _split_command(checker_cmd)
    except ValueError:
        return "witness-malformed", "checker-unparseable", None
    if not argv:
        return "witness-malformed", "checker-empty", None
    try:
        completed = subprocess.run(
            argv,
            cwd=str(project),
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return "witness-malformed", "checker-not-found", None
    except subprocess.TimeoutExpired:
        return "witness-malformed", "checker-timeout", None
    except OSError:
        # Covers platform-specific launch failures shlex's own tokenizing
        # cannot catch - an empty or otherwise unusable argv reaching the OS
        # (WinError 87 on Windows for `subprocess.run([])`; other launch
        # failures elsewhere). Still "could not judge", not "judged false".
        return "witness-malformed", "checker-unlaunchable", None
    checker_exit = completed.returncode
    disposition = "confirmed" if checker_exit == 0 else "refuted"
    return disposition, None, checker_exit


def _verdict_invariants(data: dict[str, Any]) -> None:
    """The two forbidden combinations, enforced for every append of this kind.

    Registered with Chronicle's KIND_INVARIANTS below so this runs whether
    the record was built by `record_verdict`, `attest_run_state`, or any
    future direct `archive.append("verdict", ...)` caller - the archive
    seam is the one place this cannot be bypassed by a new call site.
    """
    if data.get("disposition") != "confirmed":
        return
    if data.get("acquitted_by") == "self":
        raise ArchiveError(
            "acquitted_by='self' may attest execution completeness only; a "
            "'confirmed' disposition needs an independent checker "
            "(acquitted_by='independent') - self-acquitted quality is refused"
        )
    if data.get("run_state") == "truncated":
        raise ArchiveError(
            "a truncated run cannot be recorded 'confirmed'; budget or "
            "timeout exhaustion must not impersonate completion"
        )


register_kind_invariant("verdict", _verdict_invariants)


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
    malformed_reason: str | None = None,
) -> dict[str, Any]:
    evidence: list[str] = []
    if checker_cmd:
        evidence.append(f"cmd:{checker_cmd}")
    if witness_kind and witness_value is not None:
        evidence.append(f"{witness_kind}:{witness_value}")
    if checker_exit is not None:
        evidence.append(f"checker_exit:{checker_exit}")
    if malformed_reason is not None:
        evidence.append(f"reason:{malformed_reason}")
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
    # The two forbidden combinations are checked by KIND_INVARIANTS inside
    # archive.append() itself - not duplicated here - so this is the only
    # place either check runs, whatever path built the data.
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
    all, and the record says so (`witness-malformed`), not `refuted`. An
    empty, unparseable, or unlaunchable `checker_cmd` is the same class of
    failure and lands on the same disposition, never an uncaught exception.
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

    if not _witness_readable(project, archive, witness_kind, witness_value):
        disposition, reason, checker_exit = "witness-malformed", "witness-unreadable", None
    else:
        disposition, reason, checker_exit = _run_checker(checker_cmd, project, timeout)

    return _append_verdict(
        archive, claim, claimed_value, witness_kind, witness_value, checker_cmd,
        disposition, run_state, acquitted_by, checker_exit, reason,
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
