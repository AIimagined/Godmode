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
