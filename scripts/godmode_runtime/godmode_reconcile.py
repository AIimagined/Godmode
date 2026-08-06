"""Reconcilers: surfaces that must agree, checked instead of trusted.

Version numbers and documentation both rot the same way - one surface gets
updated, its siblings do not, and every later reader trusts whichever copy they
happened to open. Reconciliation is a diff across the surfaces with a non-zero
exit, not a convention.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_errors import ArchiveError

_ENV_PRODUCTION = re.compile(r"\b(prod(?:uction)?|live|release)\b", re.IGNORECASE)
_ENV_STAGING = re.compile(r"\b(stag(?:e|ing)|preprod|uat|qa)\b", re.IGNORECASE)
_ENV_DEV = re.compile(
    r"\b(dev(?:elopment)?|local(?:host)?|test|sandbox|127\.0\.0\.1|::1)\b", re.IGNORECASE
)


def classify_environment(target: str) -> dict[str, Any]:
    """Name the blast radius before the mutation. Unrecognised targets fail closed.

    The verdict is computed here, outside model output, and a repository file
    cannot re-label production as anything else: markers are read from the
    target string the operator supplied, not from project text.
    """
    if _ENV_PRODUCTION.search(target):
        environment = "production"
    elif _ENV_STAGING.search(target):
        environment = "staging"
    elif _ENV_DEV.search(target):
        environment = "development"
    else:
        environment = "unknown"
    return {
        "target": target,
        "environment": environment,
        # Unknown is treated as production: the cost of the wrong guess is asymmetric.
        "mutation_allowed_without_capability": environment == "development",
        "overridable": False,
    }


def version_surfaces(project: Path) -> list[dict[str, str]]:
    surfaces: list[dict[str, str]] = []

    constants = project / "scripts" / "godmode_runtime" / "godmode_constants.py"
    if constants.is_file():
        match = re.search(r'RUNTIME_VERSION\s*=\s*"([^"]+)"', constants.read_text(encoding="utf-8"))
        if match:
            surfaces.append({"surface": "godmode_constants.RUNTIME_VERSION", "version": match.group(1)})

    package = project / "scripts" / "godmode_runtime" / "__init__.py"
    if package.is_file():
        match = re.search(r'__version__\s*=\s*"([^"]+)"', package.read_text(encoding="utf-8"))
        if match:
            surfaces.append({"surface": "godmode_runtime.__version__", "version": match.group(1)})

    hosts = project / "packaging" / "hosts.json"
    if hosts.is_file():
        try:
            version = json.loads(hosts.read_text(encoding="utf-8"))["identity"]["version"]
            surfaces.append({"surface": "packaging/hosts.json identity.version", "version": version})
        except (json.JSONDecodeError, KeyError):
            surfaces.append({"surface": "packaging/hosts.json identity.version", "version": "(unreadable)"})

    changelog = project / "CHANGELOG.md"
    if changelog.is_file():
        match = re.search(r"^## \[(?!Unreleased)([^\]]+)\]", changelog.read_text(encoding="utf-8"),
                          flags=re.MULTILINE)
        if match:
            surfaces.append({"surface": "CHANGELOG.md latest release", "version": match.group(1)})

    for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
                     ".grok-plugin/plugin.json"):
        path = project / manifest
        if path.is_file():
            try:
                version = json.loads(path.read_text(encoding="utf-8")).get("version", "(absent)")
                surfaces.append({"surface": manifest, "version": version})
            except json.JSONDecodeError:
                surfaces.append({"surface": manifest, "version": "(unreadable)"})

    tag = run_git(project, "describe", "--tags", "--abbrev=0")
    if tag:
        surfaces.append({"surface": "latest git tag", "version": tag.lstrip("v")})

    deduped: list[dict[str, str]] = []
    for surface in surfaces:
        if surface not in deduped:
            deduped.append(surface)
    return deduped


def reconcile_versions(project: Path) -> dict[str, Any]:
    surfaces = version_surfaces(project)
    if not surfaces:
        raise ArchiveError("No version surfaces found to reconcile")
    values = {s["version"] for s in surfaces}
    drifted = sorted(values) if len(values) > 1 else []
    return {
        "surfaces": surfaces,
        "distinct_versions": sorted(values),
        "drift": drifted,
        "verdict": "agreed" if not drifted else "version-drift",
    }


# Change → the documentation that must move with it. Extendable per project via
# `.godmode-docs.json` {"triggers": {"path-prefix": ["required-counterpart", ...]}}.
DEFAULT_DOC_TRIGGERS = {
    "scripts/": ["changelog.d/"],
    "hooks/": ["changelog.d/"],
    "packaging/hosts.json": [".claude-plugin/", ".codex-plugin/", ".grok-plugin/"],
    "skills/": ["changelog.d/"],
}


def doc_triggers(project: Path) -> dict[str, list[str]]:
    config = project / ".godmode-docs.json"
    if config.is_file():
        try:
            declared = json.loads(config.read_text(encoding="utf-8")).get("triggers")
            if isinstance(declared, dict) and declared:
                return {str(k): [str(v) for v in vs] for k, vs in declared.items()}
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_DOC_TRIGGERS


def reconcile_docs(project: Path, base: str = "HEAD") -> dict[str, Any]:
    """Enforce the trigger table: a change that mandates a doc move blocks without it."""
    raw = run_git(project, "diff", "--name-only", "--no-renames", base)
    if raw is None:
        raise ArchiveError("The documentation reconciler needs a Git repository")
    untracked = run_git(project, "ls-files", "--others", "--exclude-standard") or ""
    changed = sorted({p for p in raw.splitlines() + untracked.splitlines() if p})
    triggers = doc_triggers(project)
    missing: list[dict[str, Any]] = []
    for prefix, counterparts in sorted(triggers.items()):
        touched = [p for p in changed if p.startswith(prefix)]
        if not touched:
            continue
        satisfied = any(any(p.startswith(c) for c in counterparts) for p in changed)
        if not satisfied:
            missing.append({
                "trigger": prefix,
                "changed": touched[:5],
                "requires_one_of": counterparts,
            })
    return {
        "base": base,
        "changed": len(changed),
        "missing": missing,
        "verdict": "reconciled" if not missing else "documentation-missing",
    }
