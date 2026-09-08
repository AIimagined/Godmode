"""A tag push is a release; CI on the tagged commit is its proof.

0.3.20 (2026-09-08): main and the release tag were pushed on a local suite
that was green on one OS and one interpreter, and the CI matrix went red on
both Windows legs with the tag already public. The rule "CI green before
the tag" existed only as maintainer prose, so nothing could refuse. This
gate refuses a tag push until a `ci` attestation with status `ran`
names the tagged commit and says green. It runs before a staged capability is consumed and
never spends it: the retry after attesting is the same exact operation.

Native on purpose: the proof is a record the operator writes after reading
the CI run, with the run URL as evidence, not a call to a forge API from a
hook. The record can be written falsely, as every attestation can; what it
cannot be is skipped.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

CI_STEP = "ci"
_GREEN = {"green", "passed", "pass", "success"}


def _git(project: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=project, capture_output=True,
                              text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def tag_targets(operation: str, project: Path) -> list[tuple[str, str]]:
    """(tag, commit sha) for every tag the push would publish; [] otherwise."""
    tokens = operation.split()
    if len(tokens) < 2 or tokens[0] != "git" or tokens[1] != "push":
        return []
    if "--tags" in tokens or "--follow-tags" in tokens:
        # Deliberate ceiling: a release cut tags HEAD, so the tags at HEAD
        # stand for the whole set. Enumerate unpushed tags if a cut ever
        # tags elsewhere.
        listed = _git(project, "tag", "--points-at", "HEAD") or ""
        names = listed.split()
    else:
        positional = [t for t in tokens[2:] if not t.startswith("-")]
        names = []
        refspecs = positional[1:]  # positional[0] is the remote
        while refspecs:
            source = refspecs.pop(0)
            if source == "tag" and refspecs:
                names.append(refspecs.pop(0))
                continue
            source = source.lstrip("+").split(":", 1)[0]
            if source.startswith("refs/tags/"):
                names.append(source[len("refs/tags/"):])
            elif _git(project, "rev-parse", "--verify", "-q", f"refs/tags/{source}"):
                names.append(source)
    targets = []
    for name in names:
        sha = _git(project, "rev-parse", f"refs/tags/{name}^{{commit}}")
        if sha:
            targets.append((name, sha))
    return targets


def _ci_attested(archive: Any, sha: str) -> bool:
    for record in archive.select(kind="attestation", subject=CI_STEP, limit=500):
        data = record.get("data") or {}
        if data.get("status") != "ran":
            continue
        result = str(data.get("result", ""))
        if not _GREEN.intersection(result.lower().split()):
            continue
        haystack = " ".join([result, *[str(e) for e in record.get("evidence") or []]])
        if sha[:7] in haystack:
            return True
    return False


def tag_push_refusal(operation: str, project: Path, archive: Any) -> str | None:
    """The reason a tag push must wait, or None when it may proceed."""
    for tag, sha in tag_targets(operation, project):
        if _ci_attested(archive, sha):
            continue
        return (
            f"a tag push is a release and CI on the tagged commit is its proof: "
            f"no `ci` attestation names {sha[:7]} ({tag}) green. When the CI matrix is "
            f"green on that commit, run `godmode attest ci --status ran "
            f"--result \"{tag} {sha[:7]} green\" --evidence <run url>` and retry "
            f"this exact command; a staged capability is untouched."
        )
    return None
