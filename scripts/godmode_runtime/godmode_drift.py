"""Detect when a model or host change quietly changed how work gets done.

Switching model should change how fast or how well work happens, never which
mandated steps happen at all. Every attestation already carries the agent that wrote
it, so comparing step sets across sessions turns "the new model feels different" into
a list of steps that stopped being performed.

Also reports what this host can actually enforce, so a control that cannot be held is
named rather than assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import os
from typing import Any

from .godmode_chronicle import Chronicle


def _fingerprint(agent: dict[str, Any]) -> str:
    return f"{agent.get('host', 'unknown')}/{agent.get('model', 'unknown')}"


def sessions(archive: Chronicle) -> list[dict[str, Any]]:
    """Per-session step sets with the agent that produced them, oldest first."""
    grouped: dict[str, dict[str, Any]] = {}
    # select() is chronological; iterate forward so first-seen sequence is the earliest.
    for record in archive.select(kind="attestation", limit=500):
        data = record["data"]
        session = data.get("session")
        if not session:
            continue
        entry = grouped.setdefault(
            session,
            {"session": session, "agent": _fingerprint(data.get("agent", {})), "steps": set(),
             "skipped": set(), "sequence": record["sequence"]},
        )
        entry["steps"].add(record["subject"])
        if data.get("status") == "skipped":
            entry["skipped"].add(record["subject"])
    ordered = sorted(grouped.values(), key=lambda entry: entry["sequence"])
    return [
        {
            "session": entry["session"],
            "agent": entry["agent"],
            "steps": sorted(entry["steps"]),
            "skipped": sorted(entry["skipped"]),
        }
        for entry in ordered
    ]


def unrouted_steps(transcript_path: str | Path | None, steps: set[str]) -> set[str]:
    """Steps whose command text ran in the host transcript without going
    through `godmode verify` (field report file 2026-09-10, finding on
    `drift`: the full suite ran six times and tsc nine, none routed, and
    the detector called them dropped). A step matches when its name, or a
    `cmd:` it was attested with, appears in a Bash/PowerShell call."""
    if not transcript_path or not steps:
        return set()
    try:
        lines = Path(str(transcript_path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    commands: list[str] = []
    for line in lines[-12000:]:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") != "assistant":
            continue
        for part in (entry.get("message") or {}).get("content") or []:
            if isinstance(part, dict) and part.get("type") == "tool_use" and part.get("name") in ("Bash", "PowerShell"):
                commands.append(" ".join(str((part.get("input") or {}).get("command", "")).split()).lower())
    joined = "\n".join(commands)
    found: set[str] = set()
    for step in steps:
        needle = " ".join(str(step).split()).lower()
        if needle.startswith("cmd:"):
            needle = needle[4:]
        core = needle.split("(", 1)[0].strip()
        if core and (core in joined or any(core in c for c in commands)):
            found.add(step)
    return found


def compare(archive: Chronicle, threshold: int = 1,
            transcript_path: str | Path | None = None) -> dict[str, Any]:
    """Flag sessions where the step set shrank, and say whether the agent changed."""
    history = sessions(archive)
    findings: list[dict[str, Any]] = []
    # Compare against everything established before, not only the previous session:
    # a step an agent never performs would otherwise vanish from the baseline after
    # one quiet session and stop being reported.
    baseline: set[str] = set()
    agents_so_far: set[str] = set()
    for index, current in enumerate(history):
        if index:
            dropped = sorted(baseline - set(current["steps"]))
            ran_unrouted = unrouted_steps(transcript_path, set(dropped))
            dropped = [step for step in dropped if step not in ran_unrouted]
            if len(dropped) >= threshold:
                findings.append(
                    {
                        "session": current["session"],
                        "agent": current["agent"],
                        "agent_changed": current["agent"] not in agents_so_far,
                        "known_agents": sorted(agents_so_far),
                        "dropped_steps": dropped,
                        "skipped_steps": current["skipped"],
                    }
                )
        baseline |= set(current["steps"])
        agents_so_far.add(current["agent"])
    correlated = [finding for finding in findings if finding["agent_changed"]]
    return {
        "sessions": len(history),
        "agents": sorted({entry["agent"] for entry in history}),
        "findings": findings,
        "model_correlated": len(correlated),
        "verdict": "drift-detected" if findings else "stable",
    }


# Host capability negotiation lives in godmode_anchor (imported by everything,
# importing nothing runtime) so both this module and the session handshake can
# use it without a cycle.
from .godmode_anchor import host_capabilities as capabilities  # noqa: E402,F401


def _self_check() -> None:
    import tempfile
    from pathlib import Path
    from unittest import mock

    from .godmode_anchor import resolve_anchor
    from .godmode_attest import record_step

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        env = {"GODMODE_STATE_HOME": str(base / "state")}
        with mock.patch.dict(os.environ, env, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()

            with mock.patch.dict(os.environ, {"GODMODE_MODEL": "model-a"}, clear=False):
                for step in ("bundle", "artefact", "code", "prior-art"):
                    record_step(archive, "S-1", step, "ran", result="ok")

            # Same agent, fewer steps: still a finding, but not model-correlated.
            with mock.patch.dict(os.environ, {"GODMODE_MODEL": "model-a"}, clear=False):
                record_step(archive, "S-2", "bundle", "ran", result="ok")

            # Different agent, fewer steps again: model-correlated drift.
            with mock.patch.dict(os.environ, {"GODMODE_MODEL": "model-b"}, clear=False):
                record_step(archive, "S-3", "bundle", "ran", result="ok")
                record_step(archive, "S-3", "code", "skipped", reason="seemed obvious")

            report = compare(archive)
            assert report["verdict"] == "drift-detected", report

            first = report["findings"][0]
            assert first["session"] == "S-2", first
            assert "artefact" in first["dropped_steps"], first
            assert not first["agent_changed"], first

            # The new model still misses steps the baseline established, and the
            # detector attributes it to the agent change rather than to chance.
            second = report["findings"][1]
            assert second["session"] == "S-3", second
            assert second["agent_changed"], second
            assert "artefact" in second["dropped_steps"], second
            assert "code" in second["skipped_steps"], second
            assert report["model_correlated"] >= 1, report
            assert len(report["agents"]) == 2, report["agents"]

    surface = capabilities()
    assert surface["controls"]["tool_call_interception"] == "UNAVAILABLE"
    assert "tool_call_interception" in surface["unavailable"]

    print("godmode_drift self-check OK")


if __name__ == "__main__":
    _self_check()
