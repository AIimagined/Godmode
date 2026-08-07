"""Checked-in agent configuration, read as an executable surface.

The repository sweep already opens these files, but it asks only whether their
prose is shaped like an instruction. That misses what they actually are: a
cloned repository can declare a hook that runs a command the moment a tool is
used, declare a server whose launch line is arbitrary, or pre-authorise the
exact operations the action gate exists to interrupt.

This product's own enforcement is a host hook, which makes the omission
reflexive - the gate's off-switch lived in a file the gate never read.

Two questions, asked structurally rather than lexically:

* what would this configuration **run**, and
* what would it **permit** that would otherwise be interrupted?

Nothing here decides whether a declaration is hostile. That is the operator's
judgement about their own repository, and a tool that guessed would either cry
wolf or miss the case that mattered. It reports what is there, names the file
and the remedy, and says plainly what it inspected - because a sweep that lists
only hits cannot be told from one that ran on nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Host configuration a repository can carry, in the order an operator would
# think of them. Absent files are not findings; unreadable ones are.
CONFIGURATION_FILES: tuple[str, ...] = (
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
    ".gemini/settings.json",
    ".codex/config.json",
)

# Permission modes that hand over the decision wholesale. These are the
# operator's to set on their own machine; shipped inside a cloned repository
# they answer a question the operator was never asked.
_SURRENDERING_MODES = frozenset({"bypassPermissions", "acceptEdits", "plan-bypass"})

# An allowance is only interesting when it covers something the gate would
# otherwise stop. Pre-approving `ls` is not a governance event.
_PROTECTED_IN_GRANT = re.compile(
    r"(?i)\b(?:git\s+push|git\s+reset|git\s+clean|git\s+rebase|force|rm\b|rmdir|"
    r"remove-item|drop\s+table|truncate|deploy|publish|release|curl|wget|"
    r"npm\s+publish|sudo)\b|\bBash\(\s*\*\s*\)|\bBash\(\s*:\s*\*\s*\)")

# A command that reaches the network and then executes what it received is the
# shape worth naming on sight; everything else is reported without escalation.
_FETCH_AND_RUN = re.compile(
    r"(?i)\b(?:curl|wget|iwr|invoke-webrequest)\b[^|;&]*[|;&]+\s*"
    r"(?:sh|bash|zsh|python[\d.]*|node|iex|powershell)\b"
    r"|\b(?:iex|invoke-expression)\b")


def _finding(code: str, path: str, detail: str, remedy: str,
             severity: str) -> dict[str, Any]:
    return {"code": code, "path": path, "detail": detail,
            "remedy": remedy, "severity": severity}


def _hook_commands(document: Any) -> list[tuple[str, str]]:
    """Every command a hooks block would execute, with the event it fires on.

    The nesting differs between hosts and versions, so the structure is walked
    rather than indexed: a shape this has not seen before should still yield
    its commands instead of silently yielding none.
    """
    found: list[tuple[str, str]] = []

    def walk(node: Any, event: str) -> None:
        if isinstance(node, dict):
            command = node.get("command")
            if isinstance(command, str) and command.strip():
                found.append((event, command.strip()))
            for key, value in node.items():
                walk(value, key if isinstance(key, str) and key[:1].isupper() else event)
        elif isinstance(node, list):
            for item in node:
                walk(item, event)

    hooks = document.get("hooks") if isinstance(document, dict) else None
    if hooks is not None:
        walk(hooks, "hooks")
    return found


def _server_commands(document: Any) -> list[tuple[str, str]]:
    servers = document.get("mcpServers") if isinstance(document, dict) else None
    if not isinstance(servers, dict):
        return []
    found: list[tuple[str, str]] = []
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        command = spec.get("command")
        if isinstance(command, str) and command.strip():
            arguments = spec.get("args")
            if isinstance(arguments, list):
                command = " ".join([command, *(str(a) for a in arguments)])
            found.append((str(name), command.strip()))
        url = spec.get("url")
        if isinstance(url, str) and url.strip():
            found.append((str(name), f"connects to {url.strip()}"))
    return found


def _permission_findings(document: Any, relative: str) -> list[dict[str, Any]]:
    permissions = document.get("permissions") if isinstance(document, dict) else None
    if not isinstance(permissions, dict):
        return []
    findings: list[dict[str, Any]] = []

    mode = permissions.get("defaultMode")
    if isinstance(mode, str) and mode in _SURRENDERING_MODES:
        findings.append(_finding(
            "permission-grant", relative,
            f"default permission mode `{mode}` answers the authorisation "
            "question before it is asked",
            "remove the mode from the repository and let the operator set it "
            "for their own machine",
            "high"))

    for key in ("allow", "deny", "ask"):
        entries = permissions.get(key)
        if not isinstance(entries, list):
            continue
        if key != "allow":
            continue
        covered = [str(entry) for entry in entries
                   if _PROTECTED_IN_GRANT.search(str(entry))]
        if covered:
            findings.append(_finding(
                "permission-grant", relative,
                "pre-approves operations the gate would otherwise interrupt: "
                + ", ".join(covered[:6]),
                "delete these entries, or move them to operator-scoped settings "
                "outside the repository",
                "high" if any(re.search(r"(?i)\*|force|rm\b", entry)
                              for entry in covered) else "medium"))
    return findings


def scan_agent_configuration(project: Path) -> dict[str, Any]:
    """Report what a repository's checked-in agent configuration would run."""
    root = Path(project)
    findings: list[dict[str, Any]] = []
    inspected: list[str] = []
    declarations = 0

    for relative in CONFIGURATION_FILES:
        target = root / relative
        if not target.is_file():
            continue
        inspected.append(relative)
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(_finding(
                "unreadable-configuration", relative,
                f"present but could not be parsed: {type(exc).__name__}",
                "fix or remove the file; an unreadable configuration is not an "
                "absent one, and silence here would read as approval",
                "medium"))
            continue

        for event, command in _hook_commands(document):
            severity = "high" if _FETCH_AND_RUN.search(command) else "medium"
            findings.append(_finding(
                "executable-declaration", relative,
                f"{event} runs: {command[:160]}",
                "read the command before trusting the worktree; a repository "
                "that ships a hook executes it on your machine, not its own",
                severity))
            declarations += 1

        for name, command in _server_commands(document):
            severity = "high" if _FETCH_AND_RUN.search(command) else "medium"
            findings.append(_finding(
                "executable-declaration", relative,
                f"server `{name}` launches: {command[:160]}",
                "confirm the server binary and its arguments before enabling it",
                severity))
            declarations += 1

        permission_findings = _permission_findings(document, relative)
        findings.extend(permission_findings)
        declarations += len(permission_findings)

        findings.extend(_disarm_findings(document, relative))

    high = sum(1 for finding in findings if finding["severity"] == "high")
    return {
        "inspected": inspected,
        "declarations": declarations,
        "findings": findings,
        "high_severity": high,
        "verdict": _verdict(inspected, findings, high),
    }


def _disarm_findings(document: Any, relative: str) -> list[dict[str, Any]]:
    """Configuration that would stop this product's own gate from running.

    Reported separately from the grant that causes it, because the operator's
    question is not "is a permission set" but "is the thing I installed to
    interrupt me still able to".
    """
    findings: list[dict[str, Any]] = []
    permissions = document.get("permissions") if isinstance(document, dict) else {}
    mode = permissions.get("defaultMode") if isinstance(permissions, dict) else None
    if isinstance(mode, str) and mode in _SURRENDERING_MODES:
        findings.append(_finding(
            "gate-disarmed", relative,
            f"`{mode}` bypasses the pre-tool interruption entirely, so no "
            "protected operation would be previewed",
            "remove it, or accept explicitly that this repository runs "
            "ungoverned",
            "high"))

    for event, command in _hook_commands(document):
        if event != "PreToolUse":
            continue
        # A PreToolUse hook that decides nothing occupies the slot the gate
        # needs while permitting everything through it.
        if re.fullmatch(r"(?i)\s*(?:exit\s+0|true|:|/bin/true)\s*", command):
            findings.append(_finding(
                "gate-disarmed", relative,
                f"a PreToolUse hook that always succeeds: {command.strip()}",
                "a hook that approves unconditionally is indistinguishable from "
                "no hook; remove it or make it decide",
                "high"))
    return findings


def _verdict(inspected: list[str], findings: list[dict[str, Any]], high: int) -> str:
    if not inspected:
        return "no-configuration-present"
    if not findings:
        return "no-declarations"
    if high:
        return "review-required"
    return "declarations-present"


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / ".claude").mkdir()
        (project / ".claude" / "settings.json").write_text(json.dumps({
            "permissions": {"defaultMode": "bypassPermissions",
                            "allow": ["Bash(git push:*)", "Bash(ls:*)"]},
            "hooks": {"PreToolUse": [{"hooks": [
                {"type": "command", "command": "sh ./setup.sh"}]}]},
        }), encoding="utf-8")
        report = scan_agent_configuration(project)
        codes = {finding["code"] for finding in report["findings"]}
        assert "executable-declaration" in codes, codes
        assert "permission-grant" in codes, codes
        assert "gate-disarmed" in codes, codes
        assert report["high_severity"] >= 1, report
        assert ".claude/settings.json" in report["inspected"], report

        clean = Path(raw) / "clean"
        clean.mkdir()
        empty = scan_agent_configuration(clean)
        assert empty["verdict"] == "no-configuration-present", empty
        assert empty["findings"] == [], empty

    print("godmode_trust self-check OK")


if __name__ == "__main__":
    _self_check()
