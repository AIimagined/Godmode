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

# `_` is a word character, so `\bproduction\b` does NOT match
# `production_backup` - an adversarial sweep found
# `localhost:5432/production_backup` classified as development and
# therefore mutable WITHOUT a capability, which is the exact inversion this
# classifier exists to prevent. The boundary is widened to any non-alnum
# edge (or string end), so an underscore, hyphen or dot separator still
# yields the marker. `prd` joins the vocabulary for the same reason: it is
# how the environment is abbreviated in real hostnames.
_EDGE = r"(?<![a-z0-9])"      # left: not preceded by an alphanumeric
_EDGE_R = r"(?![a-z0-9])"     # right: not followed by an alphanumeric
_ENV_PRODUCTION = re.compile(
    rf"{_EDGE}(prod(?:uction)?|prd|live|release){_EDGE_R}", re.IGNORECASE)
_ENV_STAGING = re.compile(
    rf"{_EDGE}(stag(?:e|ing)|preprod|uat|qa){_EDGE_R}", re.IGNORECASE)
_ENV_DEV = re.compile(
    rf"{_EDGE}(dev(?:elopment)?|local(?:host)?|test|sandbox|127\.0\.0\.1|::1){_EDGE_R}",
    re.IGNORECASE,
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


def _version_at(project: Path, ref: str) -> str | None:
    """The version `plugin.json` states in the tree a ref points at.

    `None` when the object is not there to read - a shallow clone has the tag
    but not always its tree, and reporting that as drift would turn a fetch
    depth into a release defect. The report says whether this ran, so an
    unreadable tree is a stated gap rather than a silent pass.
    """
    blob = run_git(project, "show", f"{ref}:plugin.json")
    if not blob:
        return None
    try:
        loaded = json.loads(blob)
    except json.JSONDecodeError:
        return "(unreadable)"
    return str(loaded.get("version", "(absent)")) if isinstance(loaded, dict) else "(unreadable)"


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

    # The portable manifest is a version surface like any other. Adding one
    # without registering it here is precisely the silent drift this command
    # exists to catch, and it caught exactly that on the previous release.
    for manifest in ("plugin.json", ".claude-plugin/plugin.json",
                     ".codex-plugin/plugin.json", ".grok-plugin/plugin.json"):
        path = project / manifest
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                version = loaded.get("version", "(absent)") if isinstance(loaded, dict) else "(unreadable)"
                surfaces.append({"surface": manifest, "version": version})
            except json.JSONDecodeError:
                surfaces.append({"surface": manifest, "version": "(unreadable)"})

    tag = run_git(project, "describe", "--tags", "--abbrev=0")
    if tag:
        surfaces.append({"surface": "latest git tag", "version": tag.lstrip("v")})
        # What the tagged tree says about itself, which is not the same
        # question as what the tag is called.
        #
        # v0.2.7 was published against the commit before the version bump. Every
        # surface here agreed - the tag was named v0.2.7 and the working tree
        # said 0.2.7 - and CI passed, while `git checkout v0.2.7` produced a
        # plugin identifying as 0.2.6. Comparing the name to the sources cannot
        # see that, because the name was never wrong.
        tagged = _version_at(project, tag)
        if tagged is not None:
            surfaces.append({"surface": f"plugin.json at tag {tag}", "version": tagged})

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
        # Stated, because the tagged tree is the one surface that can be
        # missing for a reason unrelated to the release, and an agreement
        # reached without it is a weaker claim than one reached with it.
        "tagged_tree_checked": any(
            s["surface"].startswith("plugin.json at tag") for s in surfaces),
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
            loaded = json.loads(config.read_text(encoding="utf-8"))
            # `null` and `[]` parse as valid JSON and are not a config.
            declared = loaded.get("triggers") if isinstance(loaded, dict) else None
            if isinstance(declared, dict) and declared:
                return {str(k): [str(v) for v in vs] for k, vs in declared.items()}
        except (OSError, json.JSONDecodeError, TypeError):
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


# §20 record-based trigger table: an archive record → the counterpart record
# that must accompany it. Path prefixes catch file drift; this table catches
# knowledge drift - work that happened without the record that makes it
# survivable across sessions.
#   change            → a checkpoint after it (unanchored work cannot be rewound)
#   bug close (sprint) → an invariant or lesson (a fix without a guard reverts)
#   decision reversal  → a decision citing the one it reverses (report only)
#   sprint transition  → nothing; the record is its own documentation
#   incident           → a lesson in the same window (report only)


def record_triggers(archive: Any, base_sequence: int = 0) -> dict[str, Any]:
    """Check the record-based trigger table over records after base_sequence.

    Report-only by design: the output names what is satisfied and what is
    missing, and the caller decides whether that blocks. Two rules are further
    marked report_only because their counterpart may legitimately arrive later
    (a reversal citation, an incident lesson); the caller should surface them
    without treating them as gate failures.

    Deterministic: the same archive window always yields the same lists, in
    record-sequence order, so two sessions reading the report agree.
    """
    window = [r for r in archive.read_events() if r["sequence"] > base_sequence]
    all_decisions = [r for r in archive.read_events() if r["kind"] == "decision"]
    satisfied: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    def later(kind_names: tuple[str, ...], after: int) -> bool:
        return any(r["kind"] in kind_names and r["sequence"] > after for r in window)

    for record in window:
        kind, sequence, subject = record["kind"], record["sequence"], record["subject"]
        if kind == "change":
            entry = {"rule": "change-requires-checkpoint", "sequence": sequence,
                     "subject": subject, "requires": "a checkpoint record after this change"}
            (satisfied if later(("checkpoint",), sequence) else missing).append(entry)
        elif kind == "sprint":
            data = record["data"]
            if data.get("item_type") == "bug" and data.get("state") in ("verified", "closed"):
                entry = {"rule": "bug-close-requires-guard", "sequence": sequence,
                         "subject": subject,
                         "requires": "an invariant or lesson record capturing the guard"}
                (satisfied if later(("invariant", "lesson"), sequence) else missing).append(entry)
            else:
                satisfied.append({"rule": "sprint-transition", "sequence": sequence,
                                  "subject": subject,
                                  "requires": "nothing (self-recording)"})
        elif kind == "decision":
            reversed_by_this = [
                d for d in all_decisions
                if d["sequence"] < sequence and d["subject"] == subject
                and d["data"].get("value") != record["data"].get("value")
            ]
            if not reversed_by_this:
                continue
            cites_earlier = any(
                f"seq:{d['sequence']}" in record.get("evidence", [])
                for d in reversed_by_this
            )
            entry = {"rule": "decision-reversal-requires-citation", "sequence": sequence,
                     "subject": subject, "report_only": True,
                     "requires": "a decision record citing (seq:N) the decision it reverses",
                     "reverses": [d["sequence"] for d in reversed_by_this]}
            (satisfied if cites_earlier else missing).append(entry)
        elif kind == "incident":
            entry = {"rule": "incident-requires-lesson", "sequence": sequence,
                     "subject": subject, "report_only": True,
                     "requires": "a lesson record within the same window"}
            in_window_lesson = any(r["kind"] == "lesson" for r in window)
            (satisfied if in_window_lesson else missing).append(entry)

    return {
        "base_sequence": base_sequence,
        "considered": len(window),
        "satisfied": satisfied,
        "missing": missing,
        "verdict": "reconciled" if not missing else "documentation-missing",
    }


def guard_citations_resolve(archive: Any, project: Path) -> dict[str, Any]:
    """Every guard-bearing record's file citations must resolve on disk.

    A registry Guard column that names no runnable test is not a guard, and a
    guard citing a path that no longer exists is a fix that can silently
    revert - the mandatory scan was once found reading an index missing 43
    shipped fixes, which is how two of them were extended blind. Both
    directions are drift: a citation to a deleted file says the guard is
    gone; a guard-bearing record with no file citation at all says it never
    had one.

    Report-only. Renames are ordinary work, and the remedy - re-point the
    citation, never loosen the guard - belongs to the operator.
    """
    project = Path(project)
    dead: list[dict[str, Any]] = []
    unanchored: list[dict[str, Any]] = []
    checked = 0
    for record in archive.read_events():
        if record["kind"] not in {"lesson", "invariant"}:
            continue
        data = record.get("data") or {}
        if record["kind"] == "lesson" and not data.get("generalized_guard"):
            continue
        checked += 1
        cited = [e[len("file:"):] for e in record.get("evidence", [])
                 if e.startswith("file:")]
        if not cited:
            unanchored.append({
                "sequence": record["sequence"], "subject": record["subject"][:60],
                "detail": "declares a guard and cites no file; a guard nothing "
                          "points at cannot be re-run or re-pointed",
            })
            continue
        for relative in cited:
            if not (project / relative).is_file():
                dead.append({
                    "sequence": record["sequence"],
                    "subject": record["subject"][:60],
                    "path": relative,
                    "detail": "cites a file that no longer exists; re-point the "
                              "citation to where the guard lives now, or the fix "
                              "it protects can silently revert",
                })
    return {
        "checked": checked,
        "dead_citations": dead,
        "unanchored_guards": unanchored,
        "verdict": "resolved" if not dead and not unanchored else "guard-drift",
    }
