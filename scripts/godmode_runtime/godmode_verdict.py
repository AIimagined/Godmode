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

Four invariants are enforced INNATELY at the archive seam - `Chronicle.append`
consults a `KIND_INVARIANTS` registry that `godmode_chronicle.py` seeds from
`godmode_invariants.py` at its OWN import, not as a side effect of this
module being imported - so a future caller that builds a `verdict` record
via a raw `archive.append(...)` (the experiment ledger among them) is held
to the same rules as `record_verdict`/`attest_run_state`, whether or not
that caller ever imports this module. The four rules (owned by
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
- Tool-error-vs-ack (PARTIAL-P3/B3-7): a `disposition: "confirmed"` fold
  whose own `tool_error_findings` is non-empty (a checker's captured output
  matched a DECLARED tool error pattern, see `register_error_pattern` and
  `TOOL_ERROR_ACK` below) needs a valid `tool_error_ack` - a tool's own
  declared error severity cannot ship as a silent "confirmed".

`verdict:<seq>` citations resolve only when that verdict's disposition is
`confirmed` (`godmode_attest._citation_resolves`) - `contested` is refused
by that same rule with no separate code path, the same way `refuted` and
`witness-malformed` already were.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
from .godmode_sentinel import find_secret_shapes

DISPOSITIONS = ("confirmed", "refuted", "witness-malformed", "contested")
RUN_STATES = ("terminated", "truncated")
ACQUITTED_BY = ("independent", "self")

_SUBJECT_CAP = 120

# PARTIAL-P3/B3-7: the closed acknowledgement vocabulary a `confirmed`
# verdict needs when its own checker output matched a declared tool error
# pattern - kept in sync BY HAND with `godmode_invariants.py`'s copy (that
# module stays import-free of this one on purpose, see its own module
# docstring), the same way `_REGISTER_STATES` there is kept in sync with
# `godmode_register.STATES`. `tests.test_tool_error_gate` asserts the two
# patterns agree.
TOOL_ERROR_ACK = re.compile(r"^acknowledged-remediated$|^acknowledged-deferred: .+$")
_TOOL_ERROR_EXCERPT_CAP = 160


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
) -> tuple[str, str | None, int | None, str]:
    """Launch the checker; every failure to even judge lands on witness-malformed.

    Returns (disposition, malformed_reason, checker_exit, output).
    malformed_reason is None whenever disposition is confirmed/refuted - it
    names WHY the checker could not judge, so the record explains the gap
    instead of silently folding "could not run" into "false". `output` is
    the checker's own combined stdout+stderr, used ONLY as the input to the
    PARTIAL-P3/B3-7 tool-error-pattern match below - it is never itself
    persisted to the archive, so a checker's output is not a new place for
    secrets to leak into the record.
    """
    try:
        argv = _split_command(checker_cmd)
    except ValueError:
        return "witness-malformed", "checker-unparseable", None, ""
    if not argv:
        return "witness-malformed", "checker-empty", None, ""
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
        return "witness-malformed", "checker-not-found", None, ""
    except subprocess.TimeoutExpired:
        return "witness-malformed", "checker-timeout", None, ""
    except OSError:
        # Covers platform-specific launch failures shlex's own tokenizing
        # cannot catch - an empty or otherwise unusable argv reaching the OS
        # (WinError 87 on Windows for `subprocess.run([])`; other launch
        # failures elsewhere). Still "could not judge", not "judged false".
        return "witness-malformed", "checker-unlaunchable", None, ""
    checker_exit = completed.returncode
    disposition = "confirmed" if checker_exit == 0 else "refuted"
    output = (completed.stdout or "") + (completed.stderr or "")
    return disposition, None, checker_exit, output


def _tool_named_in(tool: str, checker_cmd: str) -> bool:
    """Fix-round-1 (review I2): whether `tool` appears as a whole TOKEN of
    `checker_cmd`, not merely as a substring.

    A plain `in` check made a declared tool named `"lint"` match
    `"python unlinted_check.py"` - "lint" is a real substring of "unlinted",
    with no relationship between the two beyond spelling. `\\b...\\b` anchors
    the match to a word boundary on both sides: `unlinted_check.py` has no
    boundary immediately before or after the embedded "lint" (both
    neighbours - "n" before, "e" after - are word characters, and the
    underscore in "unlinted_check" is also a word character), so it no
    longer matches; `"lint --fix"` and `"python -m lint"` both have real
    boundaries around "lint" (whitespace or string edges) and still match.
    `tool` is escaped since it may carry regex metacharacters that are
    otherwise ordinary characters in a tool name (`eslint.config`,
    `media-lint`).
    """
    return re.search(rf"\b{re.escape(tool)}\b", checker_cmd, re.IGNORECASE) is not None


_REDACTED_EXCERPT = "[redacted: secret-shaped content]"


def _tool_error_findings(
    declared: dict[str, str], checker_cmd: str, output: str
) -> list[dict[str, str]]:
    """PARTIAL-P3/B3-7: which declared tool error-patterns this ONE checker's
    OWN captured output matched.

    A tool is "in play" for a checker only when the declared tool name
    appears as a whole token of that checker's own command text (see
    `_tool_named_in`) - the checker literally invokes the tool being
    watched. This is the exact shape L-173 named: a tool that logs its own
    declared error severity and still exits 0, invisible to the exit-code
    fold alone, because the fold only ever asked "did it exit clean," never
    "what did it say." `declared` empty (no tool ever registered via
    `register_error_pattern`) short-circuits to nothing checked at all - the
    undeclared-tool fast path every existing caller of `record_verdict`
    takes.

    Fix-round-1 (review M3): the matched excerpt is itself persisted into
    the archive (`data["tool_error_findings"]`, denormalised in
    `_append_verdict`) even though the FULL captured output never is - an
    operator-authored pattern with a wide capture (not just `\\berror\\b`
    but something greedier) could otherwise pull a secret-shaped fragment
    out of a checker's own stdout/stderr into a permanent record. Every
    excerpt is run through the project's existing secret-shape scanner
    (`godmode_sentinel.find_secret_shapes`, the same one `godmode_egress`
    and `godmode_trust` already use) before archiving; a hit replaces the
    excerpt with a fixed redaction marker rather than the matched text -
    the same whole-value redaction convention `godmode_egress.manifest`
    already uses for a secret-bearing file (no partial masking, no
    per-character leak of how much of the value was sensitive).
    """
    if not declared or not output:
        return []
    found: list[dict[str, str]] = []
    for tool, pattern in declared.items():
        if not tool or not _tool_named_in(tool, checker_cmd):
            continue
        try:
            match = re.search(pattern, output)
        except re.error:
            # A pattern this malformed should have been refused at
            # registration (`register_error_pattern` compiles it first) -
            # if one slipped through anyway, "could not match" is the
            # honest read, not a crash mid-fold.
            continue
        if match:
            excerpt = match.group(0)[:_TOOL_ERROR_EXCERPT_CAP]
            if find_secret_shapes(excerpt):
                excerpt = _REDACTED_EXCERPT
            found.append({"tool": tool, "excerpt": excerpt})
    return found


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
    tool_error_findings: list[dict[str, str]] | None = None,
    tool_error_ack: str = "",
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
        # PARTIAL-P3/B3-7: stored even when empty/unset, same reasoning as
        # `record_claim`'s `blast_radius` field - a reader never has to
        # guess whether an absent key means "no tool declared" or "not yet
        # this schema version". Denormalised here (not recomputed at read
        # time) so `godmode_invariants._verdict_invariants` can hold a RAW
        # `archive.append(...)` to the same rule from `data` alone, without
        # needing archive access itself - see that module's docstring.
        "tool_error_findings": tool_error_findings or [],
        "tool_error_ack": tool_error_ack or None,
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
    tool_error_ack: str = "",
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

    PARTIAL-P3/B3-7: after the fold, every checker's OWN captured output is
    tested against whatever tool error-patterns `register_error_pattern`
    has declared (undeclared tool -> nothing tested, no behaviour change at
    all). If the fold lands on `confirmed` AND a declared pattern matched,
    `tool_error_ack` must be `"acknowledged-remediated"` or
    `"acknowledged-deferred: <reason>"` - anything else, including the
    default empty string, refuses the write outright: a tool's own declared
    error severity cannot ship as a silent `confirmed`. `contested`/
    `refuted`/`witness-malformed` folds are never gated by this - only a
    `confirmed` claims the checker's output was clean enough to trust.
    """
    if run_state not in RUN_STATES:
        raise ArchiveError(
            f"Unknown run_state '{run_state}'; expected one of {', '.join(RUN_STATES)}"
        )
    if acquitted_by not in ACQUITTED_BY:
        raise ArchiveError(
            f"Unknown acquitted_by '{acquitted_by}'; expected one of {', '.join(ACQUITTED_BY)}"
        )
    # Fix-round-1 (review M1): stripped before validation (and before it is
    # stored below) so a whitespace-only "reason" - "acknowledged-deferred:
    # " with nothing but spaces after the colon - collapses to
    # "acknowledged-deferred:" with no reason left at all, which the
    # (unchanged) TOOL_ERROR_ACK pattern correctly refuses to match, the
    # same as if no reason had been typed. A reason's whitespace can only
    # ever trail the value in this format, so stripping the whole string is
    # exact, not an approximation.
    tool_error_ack = tool_error_ack.strip()
    if tool_error_ack and not TOOL_ERROR_ACK.match(tool_error_ack):
        raise ArchiveError(
            f"Unknown tool_error_ack {tool_error_ack!r}; expected "
            "'acknowledged-remediated' or 'acknowledged-deferred: <reason>'"
        )

    checkers = [checker_cmd] if isinstance(checker_cmd, str) else list(checker_cmd)
    if not checkers:
        raise ArchiveError("record_verdict needs at least one checker command")

    if ":" in witness_ref:
        witness_kind, witness_value = witness_ref.split(":", 1)
    else:
        witness_kind, witness_value = "unknown", witness_ref

    # Local import: avoids a module-level cycle risk (`godmode_attest`
    # currently has no reason to import `godmode_verdict`, but a
    # module-level import here would be the first thread tying the two
    # together for good; a function-scoped import costs nothing extra since
    # `record_verdict` is not a hot loop).
    from .godmode_attest import declared_error_patterns

    declared = declared_error_patterns(archive)

    witness_ok = _witness_readable(project, archive, witness_kind, witness_value)
    checks: list[dict[str, Any]] = []
    tool_error_findings: list[dict[str, str]] = []
    for cmd in checkers:
        if not witness_ok:
            disposition, reason, checker_exit, output = (
                "witness-malformed", "witness-unreadable", None, "",
            )
        else:
            disposition, reason, checker_exit, output = _run_checker(cmd, project, timeout)
        entry: dict[str, Any] = {
            "checker": cmd, "exit": checker_exit, "disposition": disposition,
        }
        if reason is not None:
            entry["reason"] = reason
        checks.append(entry)
        tool_error_findings.extend(_tool_error_findings(declared, cmd, output))

    folded = _fold_panel(checks)
    if folded == "confirmed" and tool_error_findings and not tool_error_ack:
        tools = ", ".join(sorted({f["tool"] for f in tool_error_findings}))
        raise ArchiveError(
            f"checker output matched a declared error pattern for: {tools}; a "
            "'confirmed' disposition needs tool_error_ack="
            "'acknowledged-remediated' or 'acknowledged-deferred: <reason>' "
            "- the tool's own declared error severity cannot ship unacknowledged"
        )
    return _append_verdict(
        archive, claim, claimed_value, witness_kind, witness_value, checks,
        folded, run_state, acquitted_by,
        tool_error_findings=tool_error_findings, tool_error_ack=tool_error_ack,
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
