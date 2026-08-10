"""Changelog fragments: a change carries its own release note or fails the gate.

One shared CHANGELOG.md turns every parallel branch into a merge conflict, and a
note written at release time is written from memory. So each change adds a fragment
under `changelog.d/<slug>.<category>.md`, the release gate refuses code changes
that arrive without one, and `merge` folds the fragments into CHANGELOG.md under
the version being cut.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git
from .godmode_errors import ArchiveError

FRAGMENT_DIR = "changelog.d"
CATEGORIES = ("added", "changed", "fixed", "removed", "deprecated", "security")
# Paths whose changes do not need a release note.
_EXEMPT = re.compile(
    r"(^|/)(changelog\.d/|CHANGELOG\.md$|tests?/|docs/|\.github/)|\.md$|\.txt$"
)


def _fragment_category(path: Path) -> str:
    parts = path.name.split(".")
    if len(parts) < 3 or parts[-2] not in CATEGORIES:
        raise ArchiveError(
            f"Fragment {path.name} must be named <slug>.<category>.md with category "
            f"one of: {', '.join(CATEGORIES)}"
        )
    return parts[-2]


def check_fragments(project: Path, base: str = "HEAD") -> dict[str, Any]:
    """The release gate: a code change without a fragment does not pass."""
    raw = run_git(project, "diff", "--name-only", "--no-renames", base)
    if raw is None:
        raise ArchiveError("The changelog gate needs a Git repository to diff against")
    tracked = run_git(project, "ls-files", "--others", "--exclude-standard") or ""
    changed = [p for p in (raw.splitlines() + tracked.splitlines()) if p]
    needs_note = sorted(p for p in changed if not _EXEMPT.search(p))
    fragments = sorted(
        p for p in changed if p.startswith(f"{FRAGMENT_DIR}/") and p.endswith(".md")
    )
    for fragment in fragments:
        _fragment_category(Path(fragment))

    # A fragment is a staging area; the artifact it exists to produce is a
    # CHANGELOG entry, and `changelog merge` consumes every fragment to write
    # one. So a commit that merges fragments and ships code together has
    # changed code, has recorded the note this gate protects, and carries no
    # fragment - because it spent them. Reading that as an unnoted change is
    # right about the fragments and wrong about the question.
    #
    # Splitting the release into two commits avoids it, and this repository has
    # always done that by habit. Habit is not a check: a gate that passes only
    # when somebody remembers the customary commit order refuses a correct
    # release the first time somebody does it in one.
    entry_added = _changelog_gained_an_entry(project, base)

    satisfied = not needs_note or bool(fragments) or entry_added
    return {
        "changes_needing_note": needs_note,
        "fragments": fragments,
        "satisfied": satisfied,
        # Named so a reader seeing `satisfied` with an empty fragment list does
        # not have to guess which of the two answers let it through.
        "satisfied_by": (
            "no-change-needing-note" if not needs_note
            else "fragment" if fragments
            else "changelog-entry" if entry_added
            else None
        ),
        "verdict": "satisfied" if satisfied else "missing-fragment",
    }


def _changelog_gained_an_entry(project: Path, base: str) -> bool:
    """Whether this diff *adds* a bullet or a version heading to CHANGELOG.md.

    Deliberately not "CHANGELOG.md was touched". Fixing a typo in a released
    entry is not a note for today's code, and accepting any edit to the file
    would turn this gate off for anybody who reflowed a paragraph.
    """
    diff = run_git(project, "diff", "-U0", base, "--", "CHANGELOG.md")
    if not diff:
        return False

    # Net bullets, not added ones. An edited bullet appears in a diff as one
    # addition and one deletion, so counting additions alone reads a corrected
    # typo in a released entry as a note for today's code - which would leave
    # the gate on in name and off in effect.
    gained = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            body = line[1:].lstrip()
            gained += 1 if body.startswith("- ") or body.startswith("## [") else 0
        elif line.startswith("-"):
            body = line[1:].lstrip()
            gained -= 1 if body.startswith("- ") or body.startswith("## [") else 0
    return gained > 0


def _existing_section(body: str, version: str) -> tuple[str | None, str, str]:
    """The section already recorded for `version`, and the text either side."""
    opening = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*$", body, flags=re.MULTILINE)
    if not opening:
        return None, "", ""
    following = re.search(r"^## \[", body[opening.end():], flags=re.MULTILINE)
    end = opening.end() + following.start() if following else len(body)
    return body[opening.start():end], body[:opening.start()], body[end:]


def _parse_entries(section: str | None) -> dict[str, list[str]]:
    """Bullets already recorded, kept verbatim so a re-merge never reformats
    prose that has already been published."""
    if not section:
        return {}
    entries: dict[str, list[str]] = {}
    category: str | None = None
    current: list[str] = []

    def flush() -> None:
        if category and current:
            text = "\n".join(current).rstrip()
            if text:
                entries.setdefault(category, []).append(text)

    for line in section.splitlines():
        heading = re.match(r"^### (?P<name>.+?)\s*$", line)
        if heading:
            flush()
            current = []
            category = heading.group("name").strip().lower()
            continue
        if line.startswith("- "):
            flush()
            current = [line]
            continue
        if current:
            current.append(line)
    flush()
    return entries


def merge_fragments(project: Path, version: str, date: str) -> dict[str, Any]:
    """Fold every fragment into CHANGELOG.md under a new version heading."""
    directory = project / FRAGMENT_DIR
    fragments = sorted(directory.glob("*.md")) if directory.is_dir() else []
    if not fragments:
        raise ArchiveError(f"No fragments to merge in {FRAGMENT_DIR}/")

    grouped: dict[str, list[str]] = {}
    for fragment in fragments:
        text = fragment.read_text(encoding="utf-8").strip()
        if text:
            grouped.setdefault(_fragment_category(fragment), []).append(text)

    changelog = project / "CHANGELOG.md"
    body = changelog.read_text(encoding="utf-8") if changelog.is_file() else "# Changelog\n"

    # A release is rarely cut in one pass: a fragment arrives after the first
    # merge, usually because a gate caught something. Inserting a second
    # heading for the same version made the changelog ambiguous about its own
    # subject, and one shipped in a tagged release with every gate green,
    # because nothing had asked whether a version appears once.
    existing, before, after = _existing_section(body, version)
    for category, entries in _parse_entries(existing).items():
        grouped.setdefault(category, [])
        # Earlier entries keep their position; the late arrival follows.
        grouped[category] = entries + grouped[category]

    lines = [f"## [{version}] - {date}", ""]
    for category in CATEGORIES:
        if category in grouped and grouped[category]:
            lines.append(f"### {category.capitalize()}")
            lines.append("")
            for entry in grouped[category]:
                first, *rest = entry.splitlines()
                lines.append(f"- {first}" if not first.startswith("- ") else first)
                lines.extend(f"  {line}" if line.strip() and not line.startswith("  ")
                             else line for line in rest)
            lines.append("")
    section = "\n".join(lines)

    if existing is not None:
        body = before + section + "\n" + after
    else:
        # Insert above the most recent release; keep any [Unreleased] header on top.
        match = re.search(r"^## \[(?!Unreleased)", body, flags=re.MULTILINE)
        if match:
            body = body[: match.start()] + section + "\n" + body[match.start():]
        else:
            body = body.rstrip("\n") + "\n\n" + section + "\n"
    changelog.write_text(body, encoding="utf-8")

    for fragment in fragments:
        fragment.unlink()
    return {"merged": len(fragments), "version": version, "changelog": "CHANGELOG.md"}
