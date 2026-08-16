"""CX-1: a chronicled, live proof that a host actually calls the pre-tool boundary.

The claim `tool_call_interception: HARD` used to rest on an environment
variable (`GODMODE_PRETOOL_GATE`) nothing ever set - so it was wrong in both
directions: silently UNAVAILABLE while a host really was calling the hook,
and trivially fakeable by anyone who exported the variable by hand. Neither
direction is acceptable for a claim this product makes to an operator about
its own enforcement.

The replacement is a synthetic challenge instead of a self-report. A marker
operation, `godmode-probe:<nonce>`, is sent through the exact path a real
host tool call takes. The hook (`hooks/godmode_session_hook.py`) treats any
operation with this prefix as protected, denies it unconditionally - no
staged capability, no observe-mode conversion, no ceiling short-circuit can
turn it into an allow - and records the denial here. The denial IS the proof:
nothing about a probe that was never received could ever get this far to
write one.

`interception_state` reads that record back rather than trusting it forever.
A proof is `HARD` only while it is fresh (recorded at or after the current
session opened - a proof from three sessions ago says nothing about whether
this one's hook is even installed) and nothing newer says the hook came down
(`hook-uninstalled`) or a later probe failed (`probe-failed`). Every other
case, including a proof that never existed, reports `UNAVAILABLE` - the same
honest default `godmode_anchor.host_capabilities` always used, just backed by
evidence instead of an environment sniff.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .godmode_chronicle import Chronicle

# The operation prefix the hook recognises as a probe, never a real command.
# Followed by a per-probe nonce so a stale proof can never be replayed as a
# fresh one, and so a staged capability (which matches exact operation text)
# can never coincidentally cover the next probe.
PROBE_PREFIX = "godmode-probe:"

# The three `action`-kind subjects `interception_state` reasons about. One
# module owns all three so a caller cannot spell "the hook came down" a
# second, drifting way.
SUBJECT_PROOF = "hook-interception-proof"
SUBJECT_UNINSTALLED = "hook-uninstalled"
SUBJECT_PROBE_FAILED = "probe-failed"

# scripts/godmode_runtime/godmode_hookproof.py -> parents[2] is the package
# root. __file__-relative, never `${CLAUDE_PLUGIN_ROOT}` - the same
# resolution `godmode_scenarios.py`'s own hook-subprocess scenario already
# uses, so a probe run from any installed location finds the same hook a
# real host would.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def record_interception_proof(
    archive: Chronicle, host: str, tool: str, request_id: str
) -> dict[str, Any]:
    """Record that the pre-tool boundary demonstrably received and denied a probe.

    Counts-only, per privacy doctrine: a host label, a tool name, and the
    nonce that ties this record back to the probe that produced it - never a
    command body or any other free text.
    """
    return archive.append(
        "action",
        SUBJECT_PROOF,
        {
            "host": str(host)[:80],
            "tool": str(tool)[:80],
            "request_id": str(request_id)[:200],
            "proof": True,
        },
        evidence=[],
    )


def last_proof(archive: Chronicle, host: str | None = None) -> dict[str, Any] | None:
    """The newest interception-proof record, optionally scoped to one host."""
    records = archive.select(kind="action", subject=SUBJECT_PROOF, limit=500)
    if host is not None:
        records = [record for record in records if record["data"].get("host") == host]
    return records[-1] if records else None


def _session_anchor_sequence(archive: Chronicle) -> int:
    """The sequence of the session this project is currently in, or 0 if none opened.

    A proof older than this belongs to a session that already ended - session
    open/close is deliberately optional (most tool calls run with no open
    session at all, per `godmode_session_hook.py`'s own `latest_session`
    fallback), so no open session means nothing to be stale relative to, and
    any existing proof counts.
    """
    sessions = archive.select(kind="session", limit=200)
    return sessions[-1]["sequence"] if sessions else 0


def interception_state(archive: Chronicle, host: str | None) -> str:
    """`HARD` iff a fresh, unsuperseded proof exists; else `UNAVAILABLE`.

    Fresh: not older than the current session anchor. Unsuperseded: no later
    `hook-uninstalled` or `probe-failed` record exists. Both conditions read
    from the chronicle, never from an environment variable - there is
    nothing here for an operator to fake by exporting one.
    """
    proof = last_proof(archive, host)
    if proof is None:
        return "UNAVAILABLE"
    if proof["sequence"] < _session_anchor_sequence(archive):
        return "UNAVAILABLE"
    for record in archive.select(kind="action", limit=500):
        if record["sequence"] <= proof["sequence"]:
            continue
        if record["subject"] in (SUBJECT_UNINSTALLED, SUBJECT_PROBE_FAILED):
            return "UNAVAILABLE"
    return "HARD"


def hook_manifest_status(package_root: Path | None = None) -> dict[str, Any]:
    """What the shipped hook manifest itself declares - not what any host has done with it.

    `plugin_installed` means the manifest is present at the resolved package
    root; `session_hook_seen`/`pretool_hook_seen` mean the manifest wires
    that lifecycle event to a Godmode script. None of the three says a host
    actually loaded or calls any of it - that gap is exactly what
    `interception_state`'s live proof exists to close, and CX-3's
    install-verify closes the remaining one (whether the host's own state
    shows the hook enabled).
    """
    root = package_root or _PACKAGE_ROOT
    manifest_path = root / "hooks" / "hooks.json"
    status = {
        "plugin_installed": False,
        "session_hook_seen": False,
        "pretool_hook_seen": False,
    }
    if not manifest_path.is_file():
        return status
    status["plugin_installed"] = True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return status
    hooks = manifest.get("hooks", {})
    if not isinstance(hooks, dict):
        return status

    def _wired(event: str) -> bool:
        for group in hooks.get(event, []) or []:
            if not isinstance(group, dict):
                continue
            for entry in group.get("hooks", []) or []:
                if not isinstance(entry, dict):
                    continue
                args = entry.get("args") or []
                if any(
                    str(arg).endswith(("godmode_session_hook.py", "godmode_gate_fast.py"))
                    for arg in args
                ):
                    return True
        return False

    status["session_hook_seen"] = _wired("SessionStart")
    status["pretool_hook_seen"] = _wired("PreToolUse")
    return status


def run_probe(
    project: Path, archive: Chronicle, host: str, *, timeout: int = 20
) -> dict[str, Any]:
    """Self-inject a marker operation through the real hook process and verify the proof.

    "Self-injection" here means the CLI spawns the same hook script a host
    invokes, with the same PreToolUse payload shape - proving the mechanism
    (recognise, deny, record) works end-to-end. It does NOT prove a live
    host's own runtime is wired to call this script on real tool calls; that
    stronger claim is CX-3's install-verify. Exit 0 (via the caller's exit
    code, derived from `state`) only when the denial was observed AND the
    matching proof record was actually written - never inferred from silence
    or a clean exit code alone.
    """
    hook_script = _PACKAGE_ROOT / "hooks" / "godmode_session_hook.py"
    nonce = uuid.uuid4().hex[:16]
    operation = f"{PROBE_PREFIX}{nonce}"
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": operation},
    }
    result: dict[str, Any] = {
        "nonce": nonce,
        "host": host,
        "denied": False,
        "proof_recorded": False,
        "state": "UNAVAILABLE",
    }
    if not hook_script.is_file():
        result["detail"] = "hook script not found at the resolved package root"
        return result

    environment = dict(os.environ)
    environment["GODMODE_HOST"] = host
    try:
        completed = subprocess.run(
            [sys.executable, str(hook_script), "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["detail"] = f"probe subprocess failed: {exc}"[:200]
        return result

    try:
        response = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        response = {}
    decision = (response.get("hookSpecificOutput") or {}).get("permissionDecision")
    result["denied"] = decision == "deny"

    proof = last_proof(archive, host)
    result["proof_recorded"] = bool(
        proof is not None and proof["data"].get("request_id") == nonce
    )
    result["state"] = interception_state(archive, host)
    if not result["denied"]:
        result["detail"] = "hook did not deny the probe operation"
    elif not result["proof_recorded"]:
        result["detail"] = "hook denied the probe but wrote no matching proof record"
    return result
