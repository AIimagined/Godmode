"""One writable status store, so two documents cannot disagree.

When many documents each claim to be the source of truth, the effective number of
sources of truth is zero: whichever was read most recently wins, which is a function
of session order rather than correctness. This module keeps status in one place and
detects competing authority claims elsewhere in the project.

It also makes finished work stay finished: an item verified complete cannot be
reopened without either an explicit user action or code proof of regression.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

STATES = ("proposed", "ready", "active", "blocked", "review", "verified", "closed")
TERMINAL = ("verified", "closed")

_AUTHORITY = re.compile(
    r"single source of truth|source of truth|\bSSOT\b|authoritative (?:list|record|doc)",
    re.IGNORECASE,
)
_SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv", "coverage"}
_TEXT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc"}


def record_item(
    archive: Chronicle,
    item: str,
    title: str,
    state: str,
    evidence: list[str] | None = None,
    proof: str = "",
) -> dict[str, Any]:
    """Write one status transition. Reopening finished work needs proof."""
    if state not in STATES:
        raise ArchiveError(f"Unknown state '{state}'; expected one of {', '.join(STATES)}")
    current = items(archive).get(item)
    if current and current["state"] in TERMINAL and state not in TERMINAL:
        if not proof.strip():
            raise ArchiveError(
                f"'{item}' is {current['state']}; reopening requires --proof naming the code "
                "evidence of regression or an explicit user instruction"
            )
    return archive.append(
        "sprint",
        item,
        {"title": title, "state": state, "proof": proof},
        evidence=evidence or [],
    )


def items(archive: Chronicle) -> dict[str, dict[str, Any]]:
    """Current state per item. Later records supersede earlier ones."""
    latest: dict[str, dict[str, Any]] = {}
    # select() is chronological, so iterating forward lets the newest record win.
    for record in archive.select(kind="sprint", limit=500):
        data = record["data"]
        if "state" not in data:
            continue
        latest[record["subject"]] = {
            "title": data.get("title", ""),
            "state": data["state"],
            "proof": data.get("proof", ""),
            "sequence": record["sequence"],
            "evidence": record.get("evidence", []),
        }
    return latest


def authority_claims(project: Path, limit: int = 5000) -> list[dict[str, Any]]:
    """Find every artefact asserting primacy, so the collision is visible."""
    found: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(project.rglob("*")):
        if scanned >= limit:
            break
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = [
            {"line": index, "text": line.strip()[:160]}
            for index, line in enumerate(text.splitlines(), 1)
            if _AUTHORITY.search(line)
        ]
        if hits:
            found.append(
                {
                    "path": path.relative_to(project).as_posix(),
                    "claims": len(hits),
                    "first": hits[0],
                }
            )
    found.sort(key=lambda entry: (-entry["claims"], entry["path"]))
    return found


def survey(archive: Chronicle, project: Path) -> dict[str, Any]:
    current = items(archive)
    claims = authority_claims(project)
    by_state: dict[str, int] = {}
    for entry in current.values():
        by_state[entry["state"]] = by_state.get(entry["state"], 0) + 1
    return {
        "items": len(current),
        "by_state": dict(sorted(by_state.items())),
        "authority_claims": {
            "files": len(claims),
            "total": sum(entry["claims"] for entry in claims),
            "top": claims[:10],
        },
        "verdict": "single-writer" if len(claims) <= 1 else "competing-authority",
    }


def _self_check() -> None:
    import os
    import tempfile
    from unittest import mock

    from .godmode_anchor import resolve_anchor

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        (project / "docs").mkdir(parents=True)
        (project / "docs" / "A.md").write_text(
            "This file is the single source of truth for sprints.\n", encoding="utf-8"
        )
        (project / "docs" / "B.md").write_text(
            "The SSOT for sprints lives here instead.\n", encoding="utf-8"
        )

        claims = authority_claims(project)
        assert len(claims) == 2, claims

        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()

            record_item(archive, "S1-01", "Set repository topics", "active")
            record_item(archive, "S1-01", "Set repository topics", "verified",
                        evidence=["file:docs/A.md#L1"])
            assert items(archive)["S1-01"]["state"] == "verified"

            # Finished work stays finished unless proof is supplied.
            try:
                record_item(archive, "S1-01", "Set repository topics", "active")
                raise AssertionError("reopening verified work without proof must be refused")
            except ArchiveError:
                pass

            record_item(archive, "S1-01", "Set repository topics", "active",
                        proof="topics absent from the live repository metadata")
            assert items(archive)["S1-01"]["state"] == "active"

            report = survey(archive, project)
            assert report["verdict"] == "competing-authority", report
            assert report["authority_claims"]["files"] == 2

    print("godmode_status self-check OK")


if __name__ == "__main__":
    _self_check()
