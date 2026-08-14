"""Witness + independent-checker verdicts (U-V1), extended to N-checker panels (U-E4).

"Agent claims it fixed X" becomes admissible only as: a claimed value stated
explicitly, a data-only witness sufficient to recompute it, and one or more
checkers that recompute from the witness alone (never invoking the producer
that made the claim) and assert against the stated value.

Four dispositions, never fewer, never averaged. Structural preconditions of
the witness are validated BEFORE any checker ever runs: a missing file or an
unresolvable seq means the claim was never judged (`witness-malformed`),
which is a different fact from "judged and found false" (`refuted`). A
checker that cannot be parsed, is empty, cannot start, or never finishes is
the same failure - "the checker could not judge" is not "the claim is
false" - so all of those also land on `witness-malformed` for that checker,
never `refuted`, and never as an uncaught exception: an adversarial checker
string is a malformed judge, not a fourth outcome.

`record_verdict` runs `checker_cmd` as a REPEATED panel (1..N; a single
command is still accepted and folds to a one-element panel, so every caller
from before this panel existed is unaffected). Each checker runs
independently (own subprocess, own timeout, producer never invoked); the
per-checker result is recorded verbatim in `data["checks"]` as
`{"checker", "exit", "disposition"}` (plus a `reason` when that checker
could not judge at all). The panel folds to ONE overall disposition by a
closed rule, never a score:

- all judged checkers `confirmed` -> `confirmed`.
- any judged checker `refuted` -> `contested` when at least one other judged
  checker `confirmed`, else `refuted` outright (unanimous refutation is not
  contested - contested means the panel disagreed).
- a checker that could not judge (`witness-malformed`) is excluded from the
  fold and recorded as a stated gap in `checks`, UNLESS no checker judged
  anything at all, in which case the whole panel folds to
  `witness-malformed` - a minority of malformed checkers never taints an
  otherwise-unanimous verdict, and it never manufactures a judgment out of
  checkers that could not run either.

Three invariants are enforced INNATELY at the archive seam - `Chronicle.append`
consults a `KIND_INVARIANTS` registry that `godmode_chronicle.py` seeds from
`godmode_invariants.py` at its OWN import, not as a side effect of this
module being imported - so a future caller that builds a `verdict` record
via a raw `archive.append(...)` (the experiment ledger among them) is held
to the same rules as `record_verdict`/`attest_run_state`, whether or not
that caller ever imports this module. The three rules (owned by
`godmode_invariants._verdict_invariants`, not duplicated here):

- Drive-vs-acquit: `acquitted_by: "self"` may attest execution completeness
  only. A `disposition: "confirmed"` needs an independent checker; a
  self-acquitted "confirmed" is refused outright.
- Terminated-vs-truncated: a `run_state: "truncated"` run (a budget or
  timeout cutoff) can never be recorded `confirmed` - budget exhaustion must
  not impersonate completion.
- Fold-vs-check: a `disposition: "confirmed"` fold can never carry a
  `checks` entry whose own disposition is `refuted` - that combination is
  not "confirmed", it is a fold that lied about a dissent it is holding.

`verdict:<seq>` citations resolve only when that verdict's disposition is
`confirmed` (`godmode_attest._citation_resolves`) - `contested` is refused
by that same rule with no separate code path, the same way `refuted` and
`witness-malformed` already were.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

DISPOSITIONS = ("confirmed", "refuted", "witness-malformed", "contested")
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


def _fold_panel(checks: list[dict[str, Any]]) -> str:
    """Closed fold, no scoring - see the module docstring for the rule.

    `checks` already holds one entry per checker, each with its own
    `disposition` of `confirmed`/`refuted`/`witness-malformed`. A malformed
    checker is excluded from the fold (it is recorded in `checks` as a
    stated gap, not silently dropped) unless it is ALL of them, in which
    case the panel as a whole never reached a judgment.
    """
    judged = [c["disposition"] for c in checks if c["disposition"] != "witness-malformed"]
    if not judged:
        return "witness-malformed"
    if all(d == "confirmed" for d in judged):
        return "confirmed"
    # At least one refuted among the judged checkers past this point.
    if any(d == "confirmed" for d in judged):
        return "contested"
    return "refuted"


def _append_verdict(
    archive: Chronicle,
    claim: str,
    claimed_value: str,
    witness_kind: str | None,
    witness_value: str | None,
    checks: list[dict[str, Any]],
    disposition: str | None,
    run_state: str,
    acquitted_by: str,
) -> dict[str, Any]:
    single = len(checks) == 1
    evidence: list[str] = []
    for index, check in enumerate(checks):
        cmd = check.get("checker")
        prefix = "" if single else f"{index}:"
        if cmd:
            evidence.append(f"cmd:{prefix}{cmd}")
        if check.get("exit") is not None:
            evidence.append(f"checker_exit:{prefix}{check['exit']}")
        if check.get("reason") is not None:
            evidence.append(f"reason:{prefix}{check['reason']}")
    if witness_kind and witness_value is not None:
        evidence.append(f"{witness_kind}:{witness_value}")
    data = {
        "claim": claim,
        "claimed_value": claimed_value,
        "witness": {"kind": witness_kind, "ref": witness_value},
        "checker": f"cmd:{checks[0]['checker']}" if single and checks[0].get("checker") else None,
        "checks": checks,
        "disposition": disposition,
        "run_state": run_state,
        "acquitted_by": acquitted_by,
    }
    subject = (claim or "verdict")[:_SUBJECT_CAP]
    # The forbidden combinations are checked inside archive.append() itself
    # (godmode_invariants._verdict_invariants, seeded into
    # Chronicle.append()'s KIND_INVARIANTS at godmode_chronicle's own
    # import) - not duplicated here, and not dependent on this module
    # having been imported either.
    return archive.append("verdict", subject, data, evidence=evidence)


def record_verdict(
    archive: Chronicle,
    project: Path,
    claim: str,
    claimed_value: str,
    witness_ref: str,
    checker_cmd: str | list[str],
    *,
    run_state: str = "terminated",
    acquitted_by: str = "independent",
    timeout: int = 300,
) -> dict[str, Any]:
    """Run one or more independent checkers against a witness, fold, record.

    `checker_cmd` accepts a bare command string (folds to a one-checker
    panel - every pre-panel caller of this function is unaffected) or a
    list of 1..N command strings for a real panel. No checker ever sees the
    producer of the claim - only the witness. Every checker is invoked only
    once the witness has passed structural validation (exists and is
    readable for `file:`, resolves in the archive for `seq:`); a witness
    that fails that check means NO checker ever runs, and the record says so
    (`witness-malformed`), not `refuted`. An empty, unparseable, or
    unlaunchable checker command is the same class of failure for that one
    checker and lands its own `checks` entry on `witness-malformed`, never
    an uncaught exception.

    The panel folds to one `disposition` per the closed rule in the module
    docstring; every individual checker's own exit/disposition/gap-reason is
    still recorded verbatim in `data["checks"]`, so a downgrade to
    `contested` never hides which checker dissented.
    """
    if run_state not in RUN_STATES:
        raise ArchiveError(
            f"Unknown run_state '{run_state}'; expected one of {', '.join(RUN_STATES)}"
        )
    if acquitted_by not in ACQUITTED_BY:
        raise ArchiveError(
            f"Unknown acquitted_by '{acquitted_by}'; expected one of {', '.join(ACQUITTED_BY)}"
        )

    checkers = [checker_cmd] if isinstance(checker_cmd, str) else list(checker_cmd)
    if not checkers:
        raise ArchiveError("record_verdict needs at least one checker command")

    if ":" in witness_ref:
        witness_kind, witness_value = witness_ref.split(":", 1)
    else:
        witness_kind, witness_value = "unknown", witness_ref

    witness_ok = _witness_readable(project, archive, witness_kind, witness_value)
    checks: list[dict[str, Any]] = []
    for cmd in checkers:
        if not witness_ok:
            disposition, reason, checker_exit = (
                "witness-malformed", "witness-unreadable", None,
            )
        else:
            disposition, reason, checker_exit = _run_checker(cmd, project, timeout)
        entry: dict[str, Any] = {
            "checker": cmd, "exit": checker_exit, "disposition": disposition,
        }
        if reason is not None:
            entry["reason"] = reason
        checks.append(entry)

    folded = _fold_panel(checks)
    return _append_verdict(
        archive, claim, claimed_value, witness_kind, witness_value, checks,
        folded, run_state, acquitted_by,
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
    `disposition` stays `None` - self acquits execution, never quality. No
    checker ran, so `checks` stays empty.
    """
    if run_state not in RUN_STATES:
        raise ArchiveError(
            f"Unknown run_state '{run_state}'; expected one of {', '.join(RUN_STATES)}"
        )
    return _append_verdict(
        archive, claim, "", None, None, [], None, run_state, "self",
    )


def verdict_for(archive: Chronicle, seq: int) -> dict[str, Any] | None:
    """The verdict record at this sequence, or None when it does not exist."""
    for record in archive.select(kind="verdict", limit=2000):
        if record["sequence"] == seq:
            return record
    return None
