"""C-10: a source-freshness preflight that says what it could not check.

A standing record cites its sources. Two citation classes can be checked
locally and already are, by `godmode_reanchor`: a `file:` committed after
the record was written is stale, and a `commit:` no longer reachable is
gone. This module layers on those two checks rather than re-deriving them,
and adds the honesty the preflight is for: a `url:` citation cannot be
checked because godmode never touches the network, so it is reported as
*unverifiable* - never as fresh - and every class the report could not
check is named in `not_checked`.

`partial` is true whenever anything was left unchecked. It is not a
failure: an honest partial exits 0, because the alternative - a preflight
that stays quiet about what it skipped - is the thing this replaces.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .godmode_reanchor import (
    DEFAULT_KINDS, is_git_project, stale_records, unreachable_commit_citations,
)

_LOCAL = ("file", "commit")


def _citations(archive: Any) -> list[str]:
    if not archive.initialized():
        return []
    out: list[str] = []
    for record in archive.read_events(verify=False):
        if record.get("kind") not in DEFAULT_KINDS:
            continue
        out.extend(str(c) for c in (record.get("evidence") or []))
    return out


def freshness_report(archive: Any, project: Path | str) -> dict[str, Any]:
    project = Path(project)
    checked = {"file": 0, "commit": 0}
    unverifiable = {"url": 0, "other": 0}
    for citation in _citations(archive):
        prefix, separator, _rest = citation.partition(":")
        if not separator:
            unverifiable["other"] += 1
        elif prefix in _LOCAL:
            checked[prefix] += 1
        elif prefix == "url":
            unverifiable["url"] += 1
        else:
            unverifiable["other"] += 1

    git = is_git_project(project)
    stale = stale_records(archive, project) if git and archive.initialized() else []
    unreachable = (unreachable_commit_citations(archive, project)
                   if git and archive.initialized() else [])

    not_checked: list[str] = []
    if unverifiable["url"]:
        not_checked.append(
            f"url: {unverifiable['url']} citation(s) - godmode never uses the "
            "network; verify these by hand")
    if unverifiable["other"]:
        not_checked.append(
            f"other: {unverifiable['other']} citation(s) with no local check "
            "(not file:, commit:, or url:)")
    if not git and (checked["file"] or checked["commit"]):
        not_checked.append(
            "file:/commit: citations - not a git project, so there is no "
            "history to compare against")
        checked = {"file": 0, "commit": 0}

    return {
        "checked": checked,
        "unverifiable": unverifiable,
        "not_checked": not_checked,
        "partial": bool(not_checked),
        "stale_files": stale,
        "unreachable_commits": unreachable,
        "verdict": "stale" if stale or unreachable else "fresh",
        "note": "partial is not a failure; it is the list of what was not checked",
    }
