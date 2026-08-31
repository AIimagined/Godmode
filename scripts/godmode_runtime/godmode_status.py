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

# The §19 work-item vocabulary. A closed set, because a free-text type cannot be
# gated: "bug" carries a root-cause obligation only if the writer cannot rename
# it to "bugfix" and slip past.
ITEM_TYPES = ("epic", "story", "bug", "spike", "chore", "security", "debt")
# Fibonacci-ish scale. Off-scale numbers are refused rather than rounded, so an
# estimate of 4 becomes a conversation about 3 vs 5 instead of silent precision.
POINT_SCALE = (1, 2, 3, 5, 8, 13, 21)

_AUTHORITY = re.compile(
    r"single source of truth|source of truth|\bSSOT\b|authoritative (?:list|record|doc)",
    re.IGNORECASE,
)
_SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv", "coverage"}
_TEXT_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc"}


def _evidence_cites_incident(archive: Chronicle, evidence: list[str]) -> bool:
    """True when the evidence list points at an incident record.

    Either form counts: an explicit `incident:` reference, or a `seq:N` entry
    whose sequence resolves to a record of kind incident in this archive.
    """
    if any(entry.startswith("incident:") for entry in evidence):
        return True
    cited = {int(entry[4:]) for entry in evidence
             if entry.startswith("seq:") and entry[4:].isdigit()}
    if not cited:
        return False
    return any(record["sequence"] in cited
               for record in archive.select(kind="incident", limit=500))


def record_item(
    archive: Chronicle,
    item: str,
    title: str,
    state: str,
    evidence: list[str] | None = None,
    proof: str = "",
    extra: dict[str, Any] | None = None,
    *,
    item_type: str | None = None,
    points: int | None = None,
    acceptance: str | None = None,
    depends_on: list[str] | None = None,
    branch: str | None = None,
    severity: str | None = None,
    root_cause: str | None = None,
    blocked_on: str | None = None,
) -> dict[str, Any]:
    """Write one status transition. Reopening finished work needs proof.

    Every writer routes through here - a second writer with its own validation
    is how two truths start.

    The §19 fields (item_type, points, acceptance, root_cause) persist across
    transitions: once declared they are inherited by later records for the same
    item, so a bug cannot shed its root-cause obligation by omitting its type on
    the closing write. Oversized stories are flagged, never blocked - sizing is
    advice; the gates below are contracts.
    """
    if state not in STATES:
        raise ArchiveError(f"Unknown state '{state}'; expected one of {', '.join(STATES)}")
    if item_type is not None and item_type not in ITEM_TYPES:
        raise ArchiveError(
            f"Unknown item type '{item_type}'; expected one of {', '.join(ITEM_TYPES)}"
        )
    if points is not None and (isinstance(points, bool) or points not in POINT_SCALE):
        raise ArchiveError(
            f"Points must be one of {', '.join(map(str, POINT_SCALE))}; got {points!r}. "
            "Off-scale estimates are re-estimated, not rounded."
        )

    evidence = evidence or []
    current = items(archive).get(item)
    prior = current or {}
    if current and current["state"] in TERMINAL and state not in TERMINAL:
        if not proof.strip():
            raise ArchiveError(
                f"'{item}' is {current['state']}; reopening requires --proof naming the code "
                "evidence of regression or an explicit user instruction"
            )

    # Effective values: this call's kwargs win; otherwise the item's history.
    effective_type = item_type if item_type is not None else prior.get("item_type")
    effective_points = points if points is not None else prior.get("points")
    effective_acceptance = acceptance if acceptance is not None else prior.get("acceptance")
    effective_root_cause = root_cause if root_cause is not None else prior.get("root_cause")

    if state == "blocked" and not (blocked_on or "").strip():
        raise ArchiveError(
            f"Moving '{item}' to blocked requires blocked_on naming the exact missing "
            "dependency; a blocked item that names no blocker is unactionable"
        )
    if depends_on:
        # Existence-checked at write time, the same discipline pending items
        # already get: a phantom blocker would freeze this item forever with
        # nothing anyone could ever resolve.
        known = items(archive)
        missing = [d for d in depends_on if d != item and d not in known]
        if missing:
            raise ArchiveError(
                f"'{item}' depends on unknown item(s): {', '.join(missing)}. "
                "Record the dependency first, or fix the name."
            )
        if item in depends_on:
            raise ArchiveError(f"'{item}' cannot depend on itself")
        # A dependency chain that loops back makes every member unstartable
        # forever, so the write that would close the loop is the one refused.
        stack = list(depends_on)
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node == item:
                raise ArchiveError(
                    f"'{item}' -> {', '.join(depends_on)} closes a dependency "
                    "cycle; a cycle makes every member unstartable"
                )
            if node in seen:
                continue
            seen.add(node)
            stack.extend(known.get(node, {}).get("depends_on", []) or [])
    if state == "verified" and (effective_acceptance or "").strip() and not evidence:
        raise ArchiveError(
            f"'{item}' declares acceptance criteria; moving to verified requires evidence "
            "showing they were met - a criterion nobody checked is decoration"
        )
    if effective_type == "bug" and state in TERMINAL:
        if not (effective_root_cause or "").strip() and not _evidence_cites_incident(archive, evidence):
            raise ArchiveError(
                f"Closing bug '{item}' requires root_cause naming what actually broke, "
                "or evidence citing an incident record - a bug closed without a cause "
                "is a bug scheduled to reopen"
            )

    findings: list[str] = []
    if effective_type == "story" and isinstance(effective_points, int):
        if effective_points >= 8:
            findings.append("split-recommended")
        if effective_points >= 13:
            findings.append("spike-first-recommended")

    data: dict[str, Any] = {"title": title, "state": state, "proof": proof}
    for key, value in (
        ("item_type", effective_type),
        ("points", effective_points),
        ("acceptance", effective_acceptance),
        ("root_cause", effective_root_cause),
        ("depends_on", depends_on),
        ("branch", branch),
        ("severity", severity),
        ("blocked_on", blocked_on),
    ):
        if value is not None:
            data[key] = value
    if findings:
        data["findings"] = findings
    if extra:
        data.update({k: v for k, v in extra.items() if k not in data})
    return archive.append("sprint", item, data, evidence=evidence)


def items(archive: Chronicle) -> dict[str, dict[str, Any]]:
    """Current state per item. Later records supersede earlier ones."""
    latest: dict[str, dict[str, Any]] = {}
    # select() is chronological, so iterating forward lets the newest record win.
    for record in archive.select(kind="sprint", limit=500):
        data = record["data"]
        if "state" not in data:
            continue
        entry = {
            "title": data.get("title", ""),
            "state": data["state"],
            "proof": data.get("proof", ""),
            "sequence": record["sequence"],
            "evidence": record.get("evidence", []),
        }
        # §19 fields ride along when declared, so gates and point sums read the
        # same view every other consumer does instead of re-parsing records.
        for key in ("item_type", "points", "acceptance", "root_cause", "blocked_on", "depends_on"):
            if key in data:
                entry[key] = data[key]
        latest[record["subject"]] = entry
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
                # A phantom close is not a fix: the stated cause is the vanished
                # evidence, so a bug-typed phantom passes the root-cause gate
                # without pretending the underlying defect was diagnosed.
                root_cause="phantom-closed: every cited artefact is absent from the tree",
            )
            closed.append(name)
            checked.append({"item": name, "verdict": "phantom-closed", "missing": missing})
        else:
            checked.append({"item": name, "verdict": "verified", "cited": len(cited)})
    return {"checked": checked, "auto_closed": closed}


# One table decides the rendered word; renders read it, never re-derive.
# `verified` is reserved for a verified state WITH cited evidence. A
# verified state nobody cited anything for is `declared` - said, not
# shown - so restating a belief can never launder it into a fact.
# Evidence still awaiting the verified transition reads `likely`;
# neither reads `unproven`.
def evidence_tier(entry: dict[str, Any]) -> str:
    has_evidence = bool(entry.get("evidence"))
    if entry.get("state") == "verified":
        return "verified" if has_evidence else "declared"
    return "likely" if has_evidence else "unproven"


def render_view(archive: Chronicle) -> str:
    """The status document, rendered from the store. Read-only downstream."""
    current = items(archive)
    lines = ["# Status", "", "Rendered from the status store; edits here change nothing.", ""]
    by_state: dict[str, list[str]] = {}
    for name, entry in sorted(current.items()):
        by_state.setdefault(entry["state"], []).append(
            f"- [{evidence_tier(entry)}] **{name}** {entry['title'] or ''} "
            f"({', '.join(entry['evidence'][:2]) or 'no evidence cited'})"
        )
    for state in STATES:
        if state in by_state:
            lines.append(f"## {state} ({len(by_state[state])})")
            lines.extend(by_state[state])
            lines.append("")
    # B4-10(b): the one computed line in an otherwise hand-written ledger -
    # observe-mode would-have counts, zero stated rather than implied by an
    # absent line. Deferred import: this module is otherwise chronicle-only.
    from .godmode_roi import would_have_summary
    summary = would_have_summary(archive)
    if summary["total"]:
        lines.append(
            f"Observe would-have events: total={summary['total']} "
            f"r5={summary['r5']} r4={summary['r4']} r3={summary['r3']} "
            f"r2={summary['r2']}"
            + (f" (top: {summary['top']})" if summary["top"] else "")
        )
    else:
        lines.append("Observe would-have events: none recorded.")
    return "\n".join(lines)


def handover(
    archive: Chronicle,
    project: Path,
    session: str | None = None,
    charter: dict[str, Any] | None = None,
    anchor: Any = None,
) -> dict[str, Any]:
    """One rolling handover view derived from the store, superseding
    the file-per-session pattern. Latest state is unambiguous; history stays
    queryable through the archive itself.

    The §20.1 contract adds what the next session cannot reconstruct from
    memory: where the repository stands (public anchor fields only - private
    paths never enter a handover), what the approved objective was, which items
    are actually verified versus merely believed done, the invariants that must
    survive the switch, the files this session touched, and the story points
    still open. Every field is derived from records, none is recalled.
    """
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
    current = items(archive)

    repository = None
    if anchor is not None:
        public = anchor.public_view()
        repository = {
            "branch": public.get("branch"),
            "head": public.get("head"),
            "worktree": public.get("worktree_root"),
        }

    objective = None
    for record in reversed(archive.select(kind="plan", limit=500)):
        if record["data"].get("state") == "approved":
            objective = record["subject"]
            break

    changed_files = sorted({
        path
        for record in archive.select(kind="change", limit=500)
        if session is None or record["data"].get("session") == session
        for path in record["data"].get("files", [])
    })

    return {
        "checkpoint": latest_checkpoint,
        "repository": repository,
        "objective": objective,
        "remaining": left["remaining"],
        "remaining_count": left["count"],
        "complete_over": left["complete_over"],
        "items": {
            name: {"state": entry["state"], "title": entry["title"]}
            for name, entry in sorted(current.items())
        },
        "verified_completed": sorted(
            name for name, entry in current.items()
            if evidence_tier(entry) == "verified"
        ),
        # Said, not shown: verified states with nothing cited. Kept apart so
        # a handover reader knows which completions rest on a statement.
        "declared_completed": sorted(
            name for name, entry in current.items()
            if evidence_tier(entry) == "declared"
        ),
        "unverified": sorted(
            name for name, entry in current.items() if entry["state"] not in TERMINAL
        ),
        "protected_invariants": [
            {"subject": record["subject"],
             "recorded_at": record["recorded_at"],
             "evidence": record.get("evidence", [])}
            for record in archive.select(kind="invariant", limit=500)
        ],
        "changed_files": changed_files,
        "remaining_story_points": sum(
            entry["points"] for entry in current.values()
            if entry["state"] not in TERMINAL and isinstance(entry.get("points"), int)
        ),
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

    # The latest record per subject is the obligation's state: a later
    # `closed` or `retired` record supersedes the original `open` one, so
    # closing through `remember --status closed` actually closes.
    latest_obligation: dict[str, dict[str, Any]] = {}
    for record in archive.select(kind="obligation", limit=500):
        latest_obligation[record["subject"]] = record
    consulted.append("open obligations")
    for record in latest_obligation.values():
        status = str(record["data"].get("status", "open")).lower()
        if status not in ("closed", "met", "done", "retired"):
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
        # A later claim on the same subject supersedes (observed live
        # 2026-08-29: two hypothesis-graded retries sat listed beside their
        # own verified successor). The latest record per subject is the
        # claim's state - the same rule obligations already follow.
        latest_claim: dict[str, dict[str, Any]] = {}
        for record in archive.select(kind="claim", limit=500):
            latest_claim[str(record["subject"])] = record
        for record in latest_claim.values():
            data = record["data"]
            if data.get("session") == session and data.get("downgraded"):
                items_left.append({"source": "claim", "id": record["subject"][:60],
                                   "detail": f"downgraded: {data.get('reason', 'unsupported')}"})

    by_source: dict[str, int] = {}
    for entry in items_left:
        by_source[entry["source"]] = by_source.get(entry["source"], 0) + 1

    # The ready set is derived, never hand-picked: an item is blocked by
    # its blocked_on note or by any dependency not yet terminal; everything
    # else still open is ready. Next action = the top of `ready`.
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for name, entry in sorted(current.items()):
        if entry["state"] in TERMINAL:
            continue
        blockers: list[str] = []
        if (entry.get("blocked_on") or "").strip() and entry["state"] == "blocked":
            blockers.append(entry["blocked_on"])
        for dependency in entry.get("depends_on") or []:
            target = current.get(dependency)
            if target is None or target["state"] not in TERMINAL:
                blockers.append(dependency)
        row = {"id": name, "title": entry["title"], "state": entry["state"]}
        if blockers:
            blocked.append({**row, "blocked_by": ", ".join(blockers)})
        else:
            ready.append(row)

    return {
        "remaining": items_left,
        "ready": ready,
        "blocked": blocked,
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
