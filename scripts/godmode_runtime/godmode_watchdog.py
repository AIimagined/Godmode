"""C-55: a watchdog over the agent's own record, on demand.

No daemon. Godmode is invoked, never resident, and the privacy boundary
forbids a watcher; "during a run" means between steps, and the report says
so in its `note`. The watchdog reads the newest window of the archive and
names three anomaly shapes, each one a failure that has actually been
observed in agent runs:

- `repeated-operation`: the same operation attempted N times in a row -
  the loop an agent falls into when a step keeps failing the same way.
- `refusal-burst`: several refusals close together - the agent is probing
  the gate rather than doing the work.
- `unattested-run`: a run of actions with no attestation behind any of
  them - work that is not being verified as it goes.

`interrupt` writes the operator-stop flag the stop algebra
(`godmode_stop.OperatorStop`) already honours, so an anomaly halts the
next guarded step with no new mechanism. Operations are reported by
digest prefix, not by text: the archive already holds the text, and the
report should not be a second copy of it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .godmode_guardrails import OPERATOR_STOP_FLAG

WINDOW = 50
REPEAT_THRESHOLD = 3
REFUSAL_THRESHOLD = 3
REFUSAL_SPAN = 10
UNATTESTED_THRESHOLD = 5

NOTE = ("on demand, read between steps - godmode runs no daemon; invoke "
        "this before the next guarded step, or pass --interrupt to halt it")


def _operation_digest(record: dict[str, Any]) -> str:
    data = record.get("data") or {}
    text = str(data.get("operation") or data.get("command") or record.get("subject") or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12] if text else ""


def watchdog_report(archive: Any, *, window: int = WINDOW) -> dict[str, Any]:
    records = archive.read_events(verify=False)[-window:] if archive.initialized() else []
    anomalies: list[dict[str, Any]] = []

    run, previous = 0, ""
    for record in records:
        if record.get("kind") not in ("action", "refusal"):
            continue
        digest = _operation_digest(record)
        run = run + 1 if digest and digest == previous else 1
        previous = digest
        if run == REPEAT_THRESHOLD:
            anomalies.append({
                "kind": "repeated-operation",
                "operation": digest,
                "sequence": record.get("sequence"),
                "detail": f"the same operation attempted {REPEAT_THRESHOLD} times in a row",
            })

    recent = records[-REFUSAL_SPAN:]
    refusals = [r for r in recent if r.get("kind") == "refusal"]
    if len(refusals) >= REFUSAL_THRESHOLD:
        anomalies.append({
            "kind": "refusal-burst",
            "count": len(refusals),
            "sequence": refusals[-1].get("sequence"),
            "detail": f"{len(refusals)} refusals in the last {len(recent)} records",
        })

    since_attestation = 0
    for record in records:
        if record.get("kind") == "attestation":
            since_attestation = 0
        elif record.get("kind") == "action":
            since_attestation += 1
    if since_attestation >= UNATTESTED_THRESHOLD:
        anomalies.append({
            "kind": "unattested-run",
            "count": since_attestation,
            "detail": f"{since_attestation} actions since the last attestation",
        })

    return {
        "window": len(records),
        "anomalies": anomalies,
        "verdict": "anomaly" if anomalies else "clean",
        "note": NOTE,
    }


def interrupt(project: Path | str, reason: str) -> Path:
    """Write the operator-stop flag. Presence is the signal the stop
    algebra reads; the content is diagnostic only."""
    flag = Path(project) / OPERATOR_STOP_FLAG
    flag.write_text(f"watchdog: {reason}\n", encoding="utf-8")
    return flag
