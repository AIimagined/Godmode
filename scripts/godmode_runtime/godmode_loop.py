"""Anti-loop detectors: notice repetition the repeating agent cannot see.

A loop never looks like a loop from inside - each iteration arrives with fresh
optimism and the same normalised content. These detectors read the archive's own
records (actions, changes, attestations, checkpoints), so what was actually done
is compared, not what the current session remembers doing. Blocking findings
stop the next repetition; the finding cites the earlier record so the prior
result is retrieved instead of regenerated.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .godmode_chronicle import Chronicle

REPEAT_THRESHOLD = 3


def _signature(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _finding(detector: str, detail: str, blocking: bool, citations: list[int]) -> dict[str, Any]:
    return {"detector": detector, "detail": detail, "blocking": blocking,
            "citations": [f"seq:{s}" for s in citations]}


def _repeated_actions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, list[int]] = {}
    for record in records:
        if record["kind"] != "action":
            continue
        data = {k: v for k, v in record["data"].items() if k not in ("at", "recorded_at")}
        key = _signature({"subject": record["subject"], "data": data})
        counts.setdefault(key, []).append(record["sequence"])
    findings = []
    for sequences in counts.values():
        if len(sequences) >= REPEAT_THRESHOLD:
            findings.append(_finding(
                "repeated-action",
                f"the same normalised action ran {len(sequences)} times with nothing "
                "changed between runs; what varied was hope, not input",
                True, sequences,
            ))
    return findings


def _repeated_patches(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    findings = []
    for record in records:
        if record["kind"] != "change":
            continue
        key = _signature({"subject": record["subject"],
                          "files": record["data"].get("files", [])})
        if key in seen:
            findings.append(_finding(
                "repeated-patch",
                f"'{record['subject']}' was already applied at seq:{seen[key]}; "
                "retrieve that record's outcome instead of reapplying",
                True, [seen[key], record["sequence"]],
            ))
        else:
            seen[key] = record["sequence"]
    return findings


def _oscillation(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_files: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["kind"] != "change":
            continue
        key = _signature(record["data"].get("files", []))
        by_files.setdefault(key, []).append(record)
    findings = []
    checkpoints = [r["sequence"] for r in records if r["kind"] == "checkpoint"]
    for changes in by_files.values():
        subjects = [c["subject"] for c in changes]
        for i in range(len(subjects) - 2):
            if subjects[i] == subjects[i + 2] and subjects[i] != subjects[i + 1]:
                before = [s for s in checkpoints if s < changes[i]["sequence"]]
                rollback = (f"roll back to checkpoint seq:{before[-1]}" if before
                            else "no checkpoint precedes the oscillation; record one before continuing")
                findings.append(_finding(
                    "oscillation",
                    f"A->B->A over the same files ('{subjects[i]}' <-> '{subjects[i+1]}'); "
                    f"neither state satisfied the check that keeps reverting it. {rollback}",
                    True,
                    [c["sequence"] for c in changes[i:i + 3]],
                ))
                break
    return findings


def _prior_fix_reversal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guarded: dict[str, tuple[int, str]] = {}
    for record in records:
        if record["kind"] in ("lesson", "invariant"):
            for evidence in record.get("evidence", []):
                if evidence.startswith("file:"):
                    guarded[evidence[len("file:"):].split("#")[0]] = (
                        record["sequence"], record["subject"])
    findings = []
    for record in records:
        if record["kind"] != "change":
            continue
        for path in record["data"].get("files", []):
            hit = guarded.get(path)
            if hit and hit[0] < record["sequence"]:
                reverified = any(
                    r["kind"] == "attestation" and r["sequence"] > record["sequence"]
                    and r["data"].get("status") == "ran"
                    and any(e == f"file:{path}" for e in r.get("evidence", []))
                    for r in records
                )
                if not reverified:
                    findings.append(_finding(
                        "prior-fix-reversal",
                        f"{path} carries fix '{hit[1]}' (seq:{hit[0]}) and was changed "
                        "without its guard being re-observed; re-run the guard before this counts",
                        True, [hit[0], record["sequence"]],
                    ))
    return findings


def _silent_success(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for record in records:
        if record["kind"] != "attestation":
            continue
        data = record["data"]
        if (record["subject"].startswith("check:") and data.get("status") == "ran"
                and "(no output)" in str(data.get("result", ""))):
            findings.append(_finding(
                "silent-success",
                f"{record['subject']} exited zero with no output; silence is a no-op "
                "until a re-query shows the effect, not a success",
                False, [record["sequence"]],
            ))
    return findings


def hypothesis_reset_required(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Three non-green checkpoints under one hypothesis end that hypothesis.

    A wrong hypothesis does not announce itself; it produces plausible next steps
    forever. The only external signal is that the checkpoints stop moving while
    the explanation stays the same - so the record of what stayed constant, not
    the agent's confidence, decides when the explanation is spent. The finding
    blocks further mutation because a fourth attempt under the same hypothesis is
    the same attempt.
    """
    findings: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    run_key: str | None = None

    def flush() -> None:
        if len(run) >= REPEAT_THRESHOLD:
            hypothesis = str(run[0]["data"]["hypothesis"])
            statuses = ", ".join(str(r["data"].get("status", "unknown")) for r in run)
            findings.append(_finding(
                "no-progress-cycle",
                f"{len(run)} consecutive checkpoints stayed non-green ({statuses}) "
                f"while the hypothesis stayed constant: '{hypothesis[:120]}'. "
                "The world moved and the explanation did not, so the explanation is "
                "spent: a hypothesis reset is required - discard it, state a new "
                "one, and record it on the next checkpoint before any further mutation",
                True, [r["sequence"] for r in run],
            ))

    for record in records:
        if record["kind"] != "checkpoint":
            continue
        hypothesis = record["data"].get("hypothesis")
        status = str(record["data"].get("status", "")).lower()
        key = None if hypothesis is None else _signature({"hypothesis": hypothesis})
        if key is not None and status != "green" and key == run_key:
            run.append(record)
            continue
        flush()
        if key is not None and status != "green":
            run, run_key = [record], key
        else:
            # A green checkpoint or an absent hypothesis is progress or a fresh
            # start; either way the streak of sameness is broken.
            run, run_key = [], None
    flush()
    return findings


def model_blame_allowed(records: list[dict[str, Any]], session: str | None = None) -> dict[str, Any]:
    """Blaming the model requires a non-model control: the same input through a
    path with no model in it. Without one, the blame is a hypothesis."""
    controls = [
        r["sequence"] for r in records
        if r["kind"] == "attestation"
        and "non-model-control" in r["subject"]
        and (session is None or r["data"].get("session") == session)
    ]
    return {
        "allowed": bool(controls),
        "controls": [f"seq:{s}" for s in controls],
        "reason": ("a non-model control was attested" if controls else
                   "no non-model control attested; attest one as 'non-model-control:<name>' first"),
    }


def analyze(archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events()
    findings = (
        _repeated_actions(records)
        + _repeated_patches(records)
        + _oscillation(records)
        + _prior_fix_reversal(records)
        + _silent_success(records)
        + hypothesis_reset_required(records)
    )
    blocking = [f for f in findings if f["blocking"]]
    return {
        "records_scanned": len(records),
        "findings": findings,
        "blocking": bool(blocking),
        "verdict": "loop-detected" if blocking else "no-loop",
    }
