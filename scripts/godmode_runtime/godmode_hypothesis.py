"""Competing hypotheses as records, each with an experiment that could kill it.

An investigation that holds one hypothesis tests whether its story is
consistent, not whether it is true. So a hypothesis here is a record that
names its cause, what confirms it, and a kill experiment: a command the
hypothesis predicts will pass. `kill` runs that command through the attested
runner - argv, no shell, bounded - and records whether it ran and whether it
fired (a non-zero exit). A fix may cite `hyp:<seq>` only when that
hypothesis's kill experiment ran and did not fire.

Records are append-only: a kill writes a new `hypothesis` record whose `of`
names the original, and the original's status is the newest record for it.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError
# The citation check lives in godmode_attest, which gates fixes on it;
# importing it from there keeps the two modules free of an import cycle.
from .godmode_attest import (  # noqa: F401 - re-exported names
    HYP_CITE, _history, _kill_run_refusal, _originals, fix_citation_refusal, survived,
)

HYPOTHESIS_STATUSES = ("open", "killed", "survived")

# An investigation weighs rivals before it commits: fewer open hypotheses
# than this before a fix is named in `status`.
MIN_COMPETING = 2


def add_hypothesis(
    archive: Chronicle,
    cause: str,
    kills: str,
    *,
    confirms: list[str] | None = None,
    next_experiment: str | None = None,
    subject: str | None = None,
) -> dict[str, Any]:
    """Record an open hypothesis with its kill experiment (not yet run)."""
    from .godmode_attest import unsupported_shell_grammar

    cause = str(cause or "").strip()
    kills = str(kills or "").strip()
    if not cause:
        raise ArchiveError("a hypothesis needs --cause: the mechanism it proposes")
    if not kills:
        raise ArchiveError(
            "a hypothesis needs --kills \"<command>\": the check it predicts will pass; "
            "a hypothesis nothing could kill is a story, not a finding")
    offending = unsupported_shell_grammar(kills)
    if offending:
        raise ArchiveError(
            f"the kill command contains {offending!r}, which the runner cannot use: it "
            "runs as argv with no shell - put a multi-step experiment in a script")
    confirms = [str(c) for c in confirms or [] if str(c).strip()]
    return archive.append(
        "hypothesis", (subject or cause)[:120],
        {"cause": cause, "confirms": confirms,
         "kills": {"command": kills, "ran": False, "fired": False},
         "next_experiment": next_experiment, "status": "open"},
        evidence=confirms,
    )


def current(records: list[dict[str, Any]], sequence: int) -> dict[str, Any] | None:
    """The newest record for hypothesis `sequence`: the original or its latest kill."""
    original = _originals(records).get(int(sequence))
    if original is None:
        return None
    history = _history(records, sequence)
    return history[-1] if history else original


def kill_hypothesis(
    archive: Chronicle, session: str, project: Path, sequence: int, timeout: int = 900,
) -> dict[str, Any]:
    """Run the kill experiment and record ran/fired as the hypothesis's new state.

    A killed hypothesis stays killed: running its experiment again after the
    environment changed would resurrect it silently, so it is refused - a
    cause worth reviving is a new hypothesis with its own record.
    """
    from .godmode_attest import run_check, split_command

    records = archive.read_events()
    original = _originals(records).get(int(sequence))
    if original is None:
        raise ArchiveError(f"no hypothesis at seq:{sequence}; `godmode hypothesis status` lists them")
    if any((r.get("data") or {}).get("status") == "killed" for r in _history(records, sequence)):
        raise ArchiveError(
            f"hypothesis seq:{sequence} was killed by its experiment and stays killed; "
            "if the cause deserves another look, record it again with `hypothesis add`")
    data = original["data"]
    command = str(data["kills"]["command"])
    outcome = run_check(archive, session, Path(project), f"kill-hyp-{sequence}",
                        split_command(command), timeout=timeout)
    code = int(outcome["exit_code"])
    # A command the runner could not start (not found) or that timed out is
    # no verdict: the experiment did not run to an answer, so it stays open.
    detail = str(outcome.get("detail", ""))
    ran = not (detail.startswith("command not found") or code == 124)
    fired = ran and code != 0
    status = "killed" if fired else "survived" if ran else "open"
    kills: dict[str, Any] = {"command": command, "ran": ran, "fired": fired, "exit_code": code}
    if ran:
        kills.update({"citation": outcome["citation"], "check_seq": outcome["sequence"]})
    record = archive.append(
        "hypothesis", original["subject"],
        {"of": int(sequence), "cause": data["cause"], "confirms": list(data.get("confirms") or []),
         "kills": kills, "next_experiment": data.get("next_experiment"), "status": status},
        evidence=[f"seq:{sequence}", f"seq:{outcome['sequence']}"],
    )
    return {"hypothesis": int(sequence), "status": status, "ran": ran, "fired": fired,
            "exit_code": code, "sequence": record["sequence"]}


def hypothesis_status(archive: Chronicle) -> dict[str, Any]:
    """Every hypothesis at its current state, every kill attempt beside it,
    and whether rivals are weighed."""
    records = archive.read_events()
    rows = []
    for sequence, original in sorted(_originals(records).items()):
        latest = current(records, sequence) or original
        data = latest["data"]
        rows.append({"sequence": sequence, "cause": data.get("cause"),
                     "status": data.get("status"), "kills": data.get("kills"),
                     "attempts": [(r.get("data") or {}).get("status")
                                  for r in _history(records, sequence)],
                     "next_experiment": data.get("next_experiment")})
    open_count = sum(1 for row in rows if row["status"] == "open")
    advisories = []
    if 0 < len(rows) < MIN_COMPETING:
        advisories.append(
            f"{len(rows)} hypothesis on record - weigh at least {MIN_COMPETING} competing "
            "causes, each with its own kill experiment, before a fix")
    return {"hypotheses": rows, "open": open_count,
            "survived": sum(1 for row in rows if row["status"] == "survived"),
            "killed": sum(1 for row in rows if row["status"] == "killed"),
            "advisories": advisories}
