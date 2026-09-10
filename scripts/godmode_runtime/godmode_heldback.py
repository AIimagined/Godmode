"""Held-back checks: the operator designates them with the password, the
done bar runs them, the agent never picks them (the Aspire finding - a
self-chosen evaluation is narrow - turned into a gate, 2026-09-10).

Kept apart from `godmode_oracle` (pure functions over the diff) because
this side runs commands through the attested runner, and the runner's
module imports the oracle: one module each way is a cycle.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HELDBACK_FILENAME = "godmode-heldback.json"


def _heldback_path(archive: Any) -> Path:
    return Path(archive.root) / HELDBACK_FILENAME


def held_checks(archive: Any) -> list[dict[str, Any]]:
    """The held-back checks on record, stored beside the capability store
    under the git metadata directory, never in the tree the agent edits."""
    path = _heldback_path(archive)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [entry for entry in (raw.get("checks") or []) if isinstance(entry, dict) and entry.get("command")]


def hold_check(archive: Any, command: str, password: str) -> dict[str, Any]:
    """Designate one held-back check. Password-gated through the same
    store `authorize` uses, so the agent cannot designate its own judge."""
    from .godmode_errors import AuthorizationError
    from .godmode_sentinel import CapabilityBroker

    broker = CapabilityBroker(archive)
    if not broker.configured():
        raise AuthorizationError("no authorization password is set; run `godmode authorize setup` first")
    if not broker._password_matches(password, broker._load()):  # noqa: SLF001 - one store, one password
        raise AuthorizationError("Authorization failed")
    text = " ".join(str(command).split())
    if not text:
        raise AuthorizationError("a held-back check needs a command")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    checks = [c for c in held_checks(archive) if c.get("digest") != digest]
    checks.append({"command": text, "digest": digest})
    path = _heldback_path(archive)
    path.write_text(json.dumps({"version": 1, "checks": checks[-16:]}, indent=2), encoding="utf-8")
    return {"held": len(checks[-16:]), "digest": digest}


def run_held_checks(archive: Any, session: str, project: Path, timeout: int = 900) -> list[dict[str, Any]]:
    """Run every held-back check through the attested runner; each outcome
    is a `heldback-<digest>` attestation, red or green."""
    from .godmode_attest import run_check, split_command

    results: list[dict[str, Any]] = []
    for entry in held_checks(archive):
        outcome = run_check(archive, session, project, f"heldback-{entry['digest']}",
                            split_command(str(entry["command"])), timeout=timeout)
        results.append({"digest": entry["digest"], "passed": bool(outcome.get("passed")),
                        "exit_code": outcome.get("exit_code"), "citation": outcome.get("citation")})
    return results
