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
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one status transition. Reopening finished work needs proof.

    Every writer routes through here - a second writer with its own validation
    is how two truths start.
    """
    if state not in STATES:
        raise ArchiveError(f"Unknown state '{state}'; expected one of {', '.join(STATES)}")
    current = items(archive).get(item)
    if current and current["state"] in TERMINAL and state not in TERMINAL:
        if not proof.strip():
            raise ArchiveError(
                f"'{item}' is {current['state']}; reopening requires --proof naming the code "
                "evidence of regression or an explicit user instruction"
            )
    data: dict[str, Any] = {"title": title, "state": state, "proof": proof}
    if extra:
        data.update({k: v for k, v in extra.items() if k not in data})
    return archive.append("sprint", item, data, evidence=evidence or [])


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


def verify_pending(archive: Chronicle, project: Path) -> dict[str, Any]:
    """Existence-check every pending item before anyone reads the list.

    An item whose every cited artefact has vanished refers to a world that no
    longer exists; it is closed in the same pass with the missing paths as
    evidence, so a phantom cannot reach the user as pending work. Items citing
    nothing are reported as unverifiable rather than silently trusted.
    """
    checked: list[dict[str, Any]] = []
    closed: list[str] = []
    for name, entry in sorted(items(archive).items()):
        if entry["state"] in TERMINAL:
            continue
        cited = [e[len("file:"):] for e in entry["evidence"] if e.startswith("file:")]
        if not cited:
            checked.append({"item": name, "verdict": "unverifiable", "cited": 0})
            continue
        missing = [path for path in cited if not (project / path.split("#")[0]).exists()]
        if missing and len(missing) == len(cited):
            record_item(
                archive, name, entry["title"], "closed",
                evidence=[f"file:{path}" for path in missing],
                extra={"closed_because": "every cited artefact is absent from the tree"},
            )
            closed.append(name)
            checked.append({"item": name, "verdict": "phantom-closed", "missing": missing})
        else:
            checked.append({"item": name, "verdict": "verified", "cited": len(cited)})
    return {"checked": checked, "auto_closed": closed}


def render_view(archive: Chronicle) -> str:
    """The status document, rendered from the store. Read-only downstream."""
    current = items(archive)
    lines = ["# Status", "", "Rendered from the status store; edits here change nothing.", ""]
    by_state: dict[str, list[str]] = {}
    for name, entry in sorted(current.items()):
        by_state.setdefault(entry["state"], []).append(
            f"- **{name}** {entry['title'] or ''} "
            f"({', '.join(entry['evidence'][:2]) or 'no evidence cited'})"
        )
    for state in STATES:
        if state in by_state:
            lines.append(f"## {state} ({len(by_state[state])})")
            lines.extend(by_state[state])
            lines.append("")
    return "\n".join(lines)


def handover(
    archive: Chronicle,
    project: Path,
    session: str | None = None,
    charter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One rolling handover view derived from the store, superseding
    the file-per-session pattern. Latest state is unambiguous; history stays
    queryable through the archive itself."""
    latest_checkpoint = None
    for record in reversed(archive.select(kind="checkpoint", limit=50)):
        latest_checkpoint = {
            "summary": record["subject"],
            "status": record["data"].get("status"),
            "next": record["data"].get("next", ""),
            "recorded_at": record["recorded_at"],
        }
        break
    left = remaining(archive, project, session=session, charter=charter)
    return {
        "checkpoint": latest_checkpoint,
        "remaining": left["remaining"],
        "remaining_count": left["count"],
        "complete_over": left["complete_over"],
        "items": {
            name: {"state": entry["state"], "title": entry["title"]}
            for name, entry in sorted(items(archive).items())
        },
        "verdict": left["verdict"],
    }


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


def remaining(
    archive: Chronicle,
    project: Path,
    session: str | None = None,
    charter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive what is left from the records, instead of recalling it.

    A remaining-work list composed from memory is a claim about the project that
    nothing checked. It reads as complete because a list always does, and the
    omission only surfaces when someone asks "anything left?" - at which point the
    answer arrives labelled honest, which is the tell that the previous one was not
    audited.

    Every source consulted is named, and every source that could not be consulted is
    named too, so the list carries the bounds of its own completeness rather than
    implying it has none.
    """
    from .godmode_attest import attested_rule_ids
    from .godmode_plan import active_plan, gaps as plan_gaps

    consulted: list[str] = []
    unavailable: list[dict[str, str]] = []
    items_left: list[dict[str, Any]] = []

    # A phantom-pending item cannot reach the reader: existence-check first,
    # closing (with evidence) anything whose cited artefacts are all gone.
    verification = verify_pending(archive, project)

    current = items(archive)
    consulted.append("status store (existence-checked)")
    for name, entry in sorted(current.items()):
        if entry["state"] not in TERMINAL:
            items_left.append({"source": "status", "id": name,
                               "detail": f"{entry['title'] or name} is {entry['state']}"})

    obligations = [
        record for record in archive.select(kind="obligation", limit=500)
    ]
    consulted.append("open obligations")
    for record in obligations:
        if str(record["data"].get("status", "open")).lower() not in ("closed", "met", "done"):
            items_left.append({"source": "obligation", "id": record["subject"],
                               "detail": str(record["data"].get("value", ""))[:160]})

    if charter is None:
        unavailable.append({"source": "unattested rules",
                            "why": "no compiled charter supplied to compare against"})
    elif session is None:
        unavailable.append({"source": "unattested rules", "why": "no session to attribute attestations to"})
    else:
        consulted.append("unattested HARD rules")
        covered = attested_rule_ids(archive, session)
        for rule in charter["compiled"]:
            if rule["enforcement"] == "HARD" and rule["id"] not in covered:
                items_left.append({"source": "rule", "id": rule["id"],
                                   "detail": rule["text"][:160]})

    if session is None:
        unavailable.append({"source": "plan contract", "why": "no session supplied"})
        unavailable.append({"source": "downgraded claims", "why": "no session supplied"})
    else:
        consulted.append("plan contract")
        plan = active_plan(archive, session)
        if plan and plan["state"] != "approved":
            for field in plan_gaps(plan["contract"]):
                items_left.append({"source": "plan", "id": plan["id"],
                                   "detail": f"contract field '{field}' is empty"})

        consulted.append("downgraded claims")
        for record in archive.select(kind="claim", limit=500):
            data = record["data"]
            if data.get("session") == session and data.get("downgraded"):
                items_left.append({"source": "claim", "id": record["subject"][:60],
                                   "detail": f"downgraded: {data.get('reason', 'unsupported')}"})

    by_source: dict[str, int] = {}
    for entry in items_left:
        by_source[entry["source"]] = by_source.get(entry["source"], 0) + 1

    return {
        "remaining": items_left,
        "count": len(items_left),
        "by_source": dict(sorted(by_source.items())),
        "phantoms_closed": verification["auto_closed"],
        "sources_consulted": consulted,
        "sources_unavailable": unavailable,
        # The list is only as complete as the sources behind it, so that is stated
        # rather than left for the reader to assume.
        "complete_over": f"{len(consulted)} of {len(consulted) + len(unavailable)} sources",
        "verdict": "nothing-outstanding" if not items_left else "work-outstanding",
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

            # A remaining-work list is derived, and states what it could not see.
            from .godmode_attest import open_session, record_claim
            from .godmode_charter import compile_charter

            (project / "GODMODE.md").write_text(
                "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8")
            charter = compile_charter(project)
            session = open_session(archive, "remaining-check")

            record_item(archive, "S2-01", "wire the adapter", "active")
            record_claim(archive, project, session, "Everything is wired.", "verified")

            left = remaining(archive, project, session=session, charter=charter)
            sources = {entry["source"] for entry in left["remaining"]}
            assert left["verdict"] == "work-outstanding", left
            # The active item, the unattested HARD rule and the downgraded claim are
            # each found without anyone remembering to mention them.
            assert {"status", "rule", "claim"} <= sources, sources
            assert "unattested HARD rules" in left["sources_consulted"], left

            # Without a session, the list narrows and says so rather than shrinking
            # silently into a shorter answer that looks like progress.
            partial = remaining(archive, project)
            assert partial["sources_unavailable"], partial
            assert "of" in partial["complete_over"], partial
            assert partial["count"] < left["count"], (partial["count"], left["count"])

    print("godmode_status self-check OK")


if __name__ == "__main__":
    _self_check()
