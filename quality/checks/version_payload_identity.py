"""Check: the declared version still names the payload that shipped after the tag.

`godmode_reconcile.reconcile_versions` (`scripts/godmode_runtime/godmode_reconcile.py`)
proves every version *surface* agrees with every other - `plugin.json`, the
runtime constant, the changelog, the tag. It has one blind spot by design: a
release can tag `v0.3.26`, and every one of those surfaces can go on agreeing
with each other and with the tag while three commits land afterward that
rewrite `hooks/godmode_gate_fast.py`. Nothing there disagrees, because the
question "does the tag still describe what HEAD ships" was never asked.

This asks it. `check()` reads three facts:

- the latest `v*` tag reachable from HEAD, by semver order (not commit-graph
  distance - `git describe` answers a different question);
- the version `plugin.json` declares at HEAD;
- whether any commit strictly after that tag touched a payload path.

"Payload" is what actually ships to a user: `skills/`, `hooks/`, `scripts/`,
`bin/`, `adapters/`, and the manifest files (`plugin.json` and every host
plugin/hook manifest, `capabilities.json`, `packaging/hosts.json`).
`docs/`, `tests/`, `benchmarks/`, `quality/`, `changelog.d/`, and
`docs/releases/` are deliberately excluded - a documentation-only commit
after a tag is not a reason to have bumped the version, and flagging one
would train this check to be ignored.

**This is a release check, not a unit-suite gate.** A sprint branch commits
payload changes continuously while the version stays at the last released
number until release prep bumps it (see `docs/RELEASE-CHECKLIST.md`) - that
window is expected to read `identity-drift` right up until the bump commit,
and a mid-sprint branch reading drift is not a defect in the branch. Wiring
this into `python -m unittest discover` or into the CI workflow would fail
every ordinary commit on every sprint branch that has not bumped yet; it is
run by hand (or from the checklist) immediately before cutting a tag, when
"drift" is the fact that matters.

Run it directly: `python quality/checks/version_payload_identity.py`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

#: What ships to a user. Order does not matter; membership does.
PAYLOAD_PREFIXES: tuple[str, ...] = (
    "skills/",
    "hooks/",
    "scripts/",
    "bin/",
    "adapters/",
    "plugin.json",
    "capabilities.json",
    ".claude-plugin/",
    ".codex-plugin/",
    ".grok-plugin/",
    ".cursor-plugin/",
    ".gemini-plugin/",
    "packaging/hosts.json",
)


def _run_git(root: Path, *arguments: str, timeout: int = 30) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _semver_key(tag: str) -> tuple[int, ...]:
    """Order by version, not by string or commit-graph proximity."""
    parts: list[int] = []
    for chunk in tag.lstrip("vV").split("."):
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def latest_tag(root: Path) -> str | None:
    """The highest-semver `v*` tag reachable from HEAD, or None.

    `git describe --tags` answers "nearest tag by commit count", which is a
    different question on any history where tags were not created strictly
    in commit order (a backport, a hotfix branch merged late). Reachability
    is checked explicitly with `merge-base --is-ancestor` so an unreachable
    tag - one that exists in the repo but is not an ancestor of HEAD - is
    never picked as "latest".
    """
    raw = _run_git(root, "tag", "--list", "v*")
    if raw is None:
        return None
    candidates = [line for line in raw.splitlines() if line.strip()]
    reachable = [tag for tag in candidates if _is_ancestor(root, tag, "HEAD")]
    if not reachable:
        return None
    return max(reachable, key=_semver_key)


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def declared_version(root: Path) -> str | None:
    """What `plugin.json` at the working tree's HEAD states as its version.

    This is the same manifest `godmode_reconcile.version_surfaces` treats as
    the plugin's own version surface - the root `plugin.json`, not a host
    mirror under `.claude-plugin/` etc., which are reconciled to agree with
    it rather than being a second source of truth.
    """
    path = root / "plugin.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    return str(version) if version is not None else None


def payload_commits_after(root: Path, tag: str) -> list[dict[str, str]]:
    """Commits strictly after `tag` (exclusive) up to HEAD that touch payload.

    `git log tag..HEAD -- <paths>` already restricts to commits that touched
    at least one of the listed paths, so no post-filtering is needed; the
    path list is exactly `PAYLOAD_PREFIXES`, each one a `git log` pathspec.
    """
    raw = _run_git(
        root, "log", "--no-renames", "--pretty=%H\x1f%s",
        f"{tag}..HEAD", "--", *PAYLOAD_PREFIXES,
    )
    if not raw:
        return []
    commits: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x1f")
        commits.append({"sha": sha, "subject": subject})
    return commits


def check(root: Path) -> dict[str, Any]:
    """The identity fact: does the declared version still name the payload."""
    root = Path(root)
    tag = latest_tag(root)
    version = declared_version(root)

    if tag is None:
        return {
            "tag": None,
            "tag_version": None,
            "declared_version": version,
            "payload_commits": [],
            "verdict": "no-tags",
            "reason": "no v* tag is reachable from HEAD; there is nothing to "
                      "compare the declared version against",
        }

    tag_version = tag.lstrip("vV")
    commits = payload_commits_after(root, tag)

    if version == tag_version and commits:
        verdict = "identity-drift"
        reason = (
            f"plugin.json still declares {version}, matching tag {tag}, but "
            f"{len(commits)} commit(s) after that tag touched shipped payload"
        )
    else:
        verdict = "ok"
        if not commits:
            reason = f"no payload commits since {tag}"
        else:
            reason = f"declared version {version} has moved past tag {tag} ({tag_version})"

    return {
        "tag": tag,
        "tag_version": tag_version,
        "declared_version": version,
        "payload_commits": commits,
        "verdict": verdict,
        "reason": reason,
    }


def main(root: Path | None = None) -> int:
    report = check(root or ROOT)
    print(f"version/payload identity: tag={report['tag']} "
          f"declared={report['declared_version']} verdict={report['verdict']}")
    print(f"  {report['reason']}")
    if report["payload_commits"]:
        print(f"  payload commits since {report['tag']}:")
        for commit in report["payload_commits"][:10]:
            print(f"    {commit['sha'][:12]}  {commit['subject']}")
    if report["verdict"] == "identity-drift":
        print("\nFAIL: bump the declared version before tagging", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
