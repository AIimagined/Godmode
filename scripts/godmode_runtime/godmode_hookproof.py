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

**Fix round 1 (review of commit 9c558a7) closed two Critical gaps:**

1. `run_probe` used to compute this attempt's own `denied`/`proof_recorded`
   and then overwrite `state` with `interception_state`'s STANDING answer -
   which reads whatever the most recently persisted proof says, regardless
   of whether THIS attempt observed a denial at all. A project already
   holding a valid, still-fresh proof from an earlier successful probe
   would report `state: "HARD"` (and exit 0) on a LATER probe attempt whose
   own denial was never observed - the self-check meant to catch a
   degraded hook silently passed by reusing history. Fixed: `state` here is
   this attempt's own verdict ONLY (`"HARD"` iff `denied and
   proof_recorded`, both computed fresh from THIS run); the pre-attempt
   history is still visible, but only in the separate `last_proof` field,
   never as this attempt's verdict. A failed attempt also now WRITES a
   `probe-failed` record (see below) - required shipped behavior, not a
   test fixture - so the STANDING state a later, probe-less `hooks
   status`/`capabilities` call reads is corrected too, not only this one
   response.

2. `_session_anchor_sequence` read `kind="session"` records, but nothing in
   the shipped `hooks/godmode_session_hook.py` `session-start` branch ever
   wrote one - only the explicit `godmode session open` CLI command did.
   Under the one host this repo ships live support for, that branch runs
   automatically every session and `open_session` is never called from it,
   so the anchor sequence was always 0 and every proof read as fresh
   forever. Fixed: `session-start` now also writes a lightweight,
   counts-only `SUBJECT_ANCHOR` record via `record_session_anchor` on every
   real session, automatically. `_session_anchor_sequence` takes the newer
   of the two anchor kinds (see its own docstring for why they are kept
   separate rather than unified, and why taking the max reconciles them
   without either fighting the other).

**Who writes each supersession/anchor subject, and when (per fix round 1's
order to state this explicitly):**

- `SUBJECT_PROOF` (`hook-interception-proof`) - written by
  `record_interception_proof`, called from the hook's probe-marker branch
  every time a `godmode-probe:<nonce>` operation is denied.
- `SUBJECT_ANCHOR` (`hook-session-anchor`) - written by
  `record_session_anchor`, called automatically from the hook's
  `session-start` branch on every real session. Also effectively supplied
  by `kind="session"` records from the explicit `godmode session open` CLI
  (`godmode_attest.open_session`) - see `_session_anchor_sequence`.
- `SUBJECT_PROBE_FAILED` (`probe-failed`) - written by `run_probe` itself,
  whenever an attempt's own `denied`/`proof_recorded` isn't both true. This
  is the only shipped writer as of fix round 1.
- `SUBJECT_UNINSTALLED` (`hook-uninstalled`) - **consumed, not yet
  written**, by design, in this unit. `interception_state` treats it as
  supersession the moment any record with this subject exists (so a
  detector, or an operator/test constructing one directly, immediately
  flips the standing state), but nothing in CX-1 detects an actual
  uninstall event and writes one automatically. Real writers belong to
  CX-3 (native manifest install/uninstall) and CX-4 (git-hook backstop
  uninstall), which is where "the hook came down" becomes something this
  codebase can observe rather than something only a test or an operator
  can assert by hand.
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

# The `action`-kind subjects `interception_state` reasons about. One module
# owns all of them so a caller cannot spell "the hook came down" a second,
# drifting way. See the module docstring's "who writes each" section for
# which of these are actually written by shipped code today.
SUBJECT_PROOF = "hook-interception-proof"
SUBJECT_ANCHOR = "hook-session-anchor"
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


def record_session_anchor(archive: Chronicle, host: str) -> dict[str, Any]:
    """The lightweight, counts-only freshness anchor a real session start produces.

    Called automatically from `hooks/godmode_session_hook.py`'s
    `session-start` branch, on every session, unconditionally - not gated
    on whether the operator ever runs `godmode session open`. See
    `_session_anchor_sequence` for how this reconciles with that heavier,
    explicit, opt-in record.
    """
    return archive.append("action", SUBJECT_ANCHOR, {"host": str(host)[:80]}, evidence=[])


def _session_anchor_sequence(archive: Chronicle) -> int:
    """The sequence a proof must be at or after to still count as fresh.

    Two DIFFERENT record kinds can each mark "a session started", and this
    reads whichever is newer - so neither can make the other's anchor
    stale, and an operator using both never sees them fight:

    - `kind="session"` (`godmode_attest.open_session`, driven by the
      explicit `godmode session open` CLI command). This is the heavier,
      opt-in unit of TRACKED work: it is also what attestation coverage
      (`attested_rule_ids`), the watchdog's skip-pattern detector, and
      `close_session`'s unattested-command check key off of. Reusing it
      directly as CX-1's freshness anchor - writing one automatically on
      every hook session-start - would have pulled every ordinary Claude
      Code session into that tracked-work machinery whether or not the
      operator ever asked for it: a materially bigger behavior change than
      an honesty fix needs to make.
    - `kind="action", subject=SUBJECT_ANCHOR` (`record_session_anchor`,
      written automatically by `hooks/godmode_session_hook.py`'s
      `session-start` branch on every real session). Lightweight,
      counts-only, and carries no attestation/watchdog side effects at all
      - CX-1's own anchor, scoped to exactly the honesty question this
      module answers.

    A project that also runs `godmode session open` inside a Claude Code
    session gets one anchor of each kind, close together in sequence;
    taking the max is exactly "the freshness bar is set by whichever
    anchor is more recent, whichever kind wrote it" - sound regardless of
    order, so the two never need to agree on which one governs.

    Neither kind ever written (no session-start hook installed, and
    `session open` never run) returns 0 - nothing to be stale relative to,
    so any existing proof counts. That residual gap is CX-6's e2e harness
    (an installed package, a real host, a real session-start) to close for
    hosts whose session-start branch this repository does not itself run;
    for every host with the hook installed at all - Claude Code included -
    this fix closes it now.
    """
    session_sequence = 0
    sessions = archive.select(kind="session", limit=200)
    if sessions:
        session_sequence = sessions[-1]["sequence"]
    anchor_sequence = 0
    anchors = archive.select(kind="action", subject=SUBJECT_ANCHOR, limit=200)
    if anchors:
        anchor_sequence = anchors[-1]["sequence"]
    return max(session_sequence, anchor_sequence)


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
    stronger claim is CX-3's install-verify.

    `state` (and the caller's exit code, which is derived from it) is THIS
    ATTEMPT's own verdict, and nothing else: `"HARD"` iff `denied` and
    `proof_recorded`, both computed fresh from what just happened, never
    from `interception_state`'s standing answer. A project that already
    holds a valid, still-fresh proof from an earlier successful probe gets
    no credit for it here - that history is still available, in the
    separate `last_proof` field, but a re-probe exists precisely to answer
    "does interception still work RIGHT NOW", and letting a stale-but-
    technically-fresh record answer on this attempt's behalf is exactly the
    silent-pass fix round 1 exists to close.

    Any attempt whose own denial was not observed - hook script missing,
    subprocess failure, or a response with no matching proof - writes a
    `probe-failed` record (`SUBJECT_PROBE_FAILED`) before returning, so the
    STANDING state (what a later, probe-less `hooks status`/`capabilities`
    call reads via `interception_state`) is corrected too, not only this
    response. Best-effort: a probe that already failed must still report
    the failure even if this write itself fails.
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
        # Pre-attempt history, captured before this probe runs, so it can
        # never be conflated with this attempt's own outcome below.
        "last_proof": last_proof(archive, host),
    }

    def _fail(detail: str, reason: str) -> dict[str, Any]:
        result["detail"] = detail
        try:
            archive.append(
                "action", SUBJECT_PROBE_FAILED,
                {"host": str(host)[:80], "reason": reason},
                evidence=[],
            )
        except Exception:  # noqa: BLE001
            pass
        return result

    if not hook_script.is_file():
        return _fail(
            "hook script not found at the resolved package root", "hook-script-missing")

    environment = dict(os.environ)
    environment["GODMODE_HOST"] = host
    try:
        completed = subprocess.run(
            [sys.executable, str(hook_script), "pre-action", "--project", str(project)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _fail(f"probe subprocess failed: {exc}"[:200], "subprocess-failed")

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

    if result["denied"] and result["proof_recorded"]:
        result["state"] = "HARD"
        return result
    if not result["denied"]:
        return _fail("hook did not deny the probe operation", "not-denied")
    return _fail("hook denied the probe but wrote no matching proof record", "proof-not-recorded")
