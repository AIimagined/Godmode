"""`privacy --repo`: what a tracked tree says about its author and machine.

Field report 27 (2026-09-10): a docs-privacy pass found every leak by hand
with `git ls-files` and `grep` while the plugin, which reads the repo, said
nothing. The scan walks the tracked files only (untracked files never
ship), reads text under a size cap, and names each hit by path, line and
kind with the value masked - the report is what a reviewer needs to act,
never a second copy of the thing being removed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_sentinel import _SECRET_PATTERNS

# Credential FORMATS only (key headers, provider token prefixes, JWTs,
# connection strings with a password, bearer values). The archive scanner
# also matches the phrases people use about credentials (`password: x`),
# which is right for a prompt store and wrong for a source tree that
# documents or tests credential handling - dogfooded on this repo, the
# phrase patterns named 76 files and every one was prose or a fixture.
_CREDENTIAL_SHAPES = tuple(p for p in _SECRET_PATTERNS if "password" not in p.pattern.lower()
                           or "://" in p.pattern)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# Documentation placeholders, never a person: RFC 2606 names and the
# forge's no-reply mailbox.
_PLACEHOLDER_DOMAINS = ("example.com", "example.org", "example.net", "example.invalid",
                        "noreply.github.com", "users.noreply.github.com")
_PLACEHOLDER_TLDS = (".invalid", ".test", ".example", ".localhost")
_HOME = re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/Users/|/home/)([A-Za-z0-9._-]{2,})")
_HOME_PLACEHOLDERS = frozenset({"user", "username", "you", "yourname", "name", "me", "runner",
                                "public", "default", "shared", "all"})
_IPV4 = re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})\b")
_TEXT_SUFFIXES = frozenset({
    ".md", ".txt", ".rst", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".env", ".sh", ".cmd", ".ps1", ".bat",
    ".html", ".css", ".xml", ".csv", ".sql", ".go", ".rs", ".java", ".kt", ".rb", ".php",
})
_READ_CAP = 2_000_000


def _mask(value: str) -> str:
    return value[:3] + "…" if len(value) > 3 else "…"


_HOST_CONTEXT = re.compile(r"(?i)(?:://|@|\bhost\b|\bserver\b|\bip\b)[^\n]{0,24}$")


def _ip_is_real(text: str, before: str) -> bool:
    """An address worth naming: a private-range address (the shape that
    leaks a LAN or VPN), or any address sitting in a URL or host position.
    A bare dotted number elsewhere is far more often a version than a host,
    so it is left alone rather than flagged into noise. `before` is the
    line up to the match."""
    parts = [int(p) for p in text.split(".")]
    if any(p > 255 for p in parts) or text.startswith(("0.", "127.")):
        return False
    private = (parts[0] == 10 or (parts[0] == 172 and 16 <= parts[1] <= 31)
               or (parts[0], parts[1]) == (192, 168))
    return private or _HOST_CONTEXT.search(before) is not None


def scan_tracked(project: Path, large_bytes: int = 5_000_000) -> dict[str, Any]:
    listed = run_git(project, "ls-files", "-z")
    if listed is None:
        return {"error": "not a git repository; the repo scan reads tracked files only",
                "files_scanned": 0, "findings": [], "large_files": [], "by_kind": {}}
    paths = [p for p in listed.split("\0") if p]
    findings: list[dict[str, Any]] = []
    large: list[dict[str, Any]] = []
    scanned = 0
    for relative in paths:
        path = project / relative
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size >= large_bytes:
            large.append({"path": relative, "bytes": size})
        if path.suffix.lower() not in _TEXT_SUFFIXES or size > _READ_CAP:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), 1):
            for match in _EMAIL.finditer(line):
                domain = match.group(1).lower()
                local = match.group(0).split("@", 1)[0].lower().replace("-", "").replace("_", "")
                if domain in _PLACEHOLDER_DOMAINS or domain.endswith(_PLACEHOLDER_TLDS) \
                        or local in ("noreply", "donotreply", "nobody", "example", "user", "test"):
                    continue
                findings.append({"path": relative, "line": number, "kind": "email",
                                 "sample": _mask(match.group(0))})
            for match in _HOME.finditer(line):
                name = match.group(1)
                if name.lower().strip("<>{}$") in _HOME_PLACEHOLDERS or name.startswith(("<", "{", "$")):
                    continue
                findings.append({"path": relative, "line": number, "kind": "home-path",
                                 "sample": _mask(name)})
            for match in _IPV4.finditer(line):
                if _ip_is_real(match.group(1), line[:match.start()]):
                    findings.append({"path": relative, "line": number, "kind": "ip-address",
                                     "sample": _mask(match.group(1))})
            for shape in _CREDENTIAL_SHAPES:
                hit = shape.search(line)
                if hit:
                    findings.append({"path": relative, "line": number, "kind": "secret-shape",
                                     "sample": _mask(hit.group(0))})
                    break
    by_kind: dict[str, int] = {}
    for finding in findings:
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
    return {
        "files_tracked": len(paths),
        "files_scanned": scanned,
        "findings": findings[:500],
        "by_kind": by_kind,
        "large_files": sorted(large, key=lambda f: -f["bytes"])[:50],
        "large_bytes_threshold": large_bytes,
        "verdict": "findings" if findings or large else "clean",
    }


# Keys in a repository's own .git/config that run a command the moment a
# host opens the tree - before any trust prompt and before any hook of
# ours (core.fsmonitor RCE, Sep 2026, across seven hosts). Names only; the
# value is hashed, never shown, because a trap's value is the payload.
_TRAP_KEYS = (
    "core.fsmonitor", "core.hookspath", "core.pager", "core.sshcommand", "core.editor",
    "core.gitproxy", "core.askpass", "diff.external", "gpg.program", "credential.helper",
    "sequence.editor", "merge.tool", "difftool.", "mergetool.", "filter.", "alias.",
    "url.", "include.path", "includeif.",
)


def config_traps(project: Path) -> list[dict[str, str]]:
    import hashlib
    import subprocess

    try:
        run = subprocess.run(["git", "-C", str(project), "config", "--local", "--list"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if run.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for line in run.stdout.splitlines():
        key, _, value = line.partition("=")
        lowered = key.strip().lower()
        hit = next((trap for trap in _TRAP_KEYS if lowered == trap or (trap.endswith(".") and lowered.startswith(trap))), None)
        if hit is None:
            continue
        if hit in ("alias.", "filter.", "difftool.", "mergetool.", "url.") and not (
                value.lstrip().startswith("!") or hit in ("filter.", "difftool.", "mergetool.")
                or (hit == "url." and lowered.endswith(".insteadof"))):
            continue
        out.append({"key": key.strip(), "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
                    "why": "runs or redirects a command when the tree is opened or a git verb runs"})
    return out


# Field roundup 2026-09-10, item 9: a pre-approved interpreter wildcard
# (`Bash(python:*)`) or an unpinned `npx` MCP server is a dependency layer
# with no lockfile. Names only - the settings files hold secrets and are
# read for these two keys and nothing else.
_INTERPRETER_WILDCARD = re.compile(
    r"\((?:python3?|node|bash|sh|zsh|pwsh|powershell|npx|npm|pip3?|uv|deno|bun)\b[^)]*\*\)")
_PINNED_VERSION = re.compile(r"@\d")


_EXTERNAL_WRITE_CATEGORIES = ("git-history-or-remote", "release-or-external-write")


def host_permission_findings(project: Path) -> list[dict[str, str]]:
    import json
    import os

    home = Path(os.path.expanduser("~"))
    out: list[dict[str, str]] = []
    # 2026-09-10: the local policy listed the two external-write categories
    # under ask_only, and the host answered every ask itself. Named here so
    # the next doctor run says it before the next push does.
    try:
        policy = json.loads((project / ".godmode-authorization-policy.json").read_text(encoding="utf-8")) or {}
        asked = [c for c in (policy.get("ask_only") or []) if c in _EXTERNAL_WRITE_CATEGORIES]
    except (OSError, ValueError, AttributeError):
        asked = []
    if asked:
        out.append({"code": "ask-only-external-write", "severity": "warning", "scope": "project",
                    "detail": f"ask_only lists {', '.join(asked)}: a push or release asks instead of needing "
                              "the staged capability, and in auto, dontAsk, or bypassPermissions mode the "
                              "host answers that ask itself - the password is not in the path"})
    for label, path in (("user", home / ".claude" / "settings.json"),
                        ("project", project / ".claude" / "settings.json"),
                        ("local", project / ".claude" / "settings.local.json")):
        try:
            allow = ((json.loads(path.read_text(encoding="utf-8")) or {}).get("permissions") or {}).get("allow") or []
        except (OSError, ValueError, AttributeError):
            continue
        for entry in allow:
            if isinstance(entry, str) and _INTERPRETER_WILDCARD.search(entry):
                out.append({"code": "interpreter-wildcard-allow", "severity": "warning", "scope": label,
                            "detail": f"{label} settings pre-approve {entry[:60]}: an interpreter wildcard runs any "
                                      "payload without an ask; name the scripts instead"})
    for label, path, key in (("project", project / ".mcp.json", "mcpServers"),
                             ("user", home / ".claude.json", "mcpServers")):
        try:
            servers = (json.loads(path.read_text(encoding="utf-8")) or {}).get(key) or {}
        except (OSError, ValueError, AttributeError):
            continue
        for name, spec in servers.items():
            if not isinstance(spec, dict):
                continue
            argv = " ".join([str(spec.get("command") or "")] + [str(a) for a in (spec.get("args") or [])])
            if "npx" in argv and not _PINNED_VERSION.search(argv):
                out.append({"code": "unpinned-mcp-server", "severity": "warning", "scope": label,
                            "detail": f"{label} MCP server {str(name)[:40]} runs npx without a pinned version: "
                                      "the tool that runs next session is whatever the registry serves"})
    return out
