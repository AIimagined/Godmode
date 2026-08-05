"""Godmode command surface."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import shlex
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable

from .godmode_anchor import ProjectAnchor, resolve_anchor
from .godmode_chronicle import Chronicle
from .godmode_constants import DEFAULT_CONTEXT_BUDGET, EVENT_KINDS, RUNTIME_VERSION
from .godmode_attest import (
    agent_fingerprint,
    close_session,
    gate,
    latest_session,
    open_session,
    record_claim,
    record_step,
)
from .godmode_assess import assess as assess_project
from .godmode_assess import assurance_case
from .godmode_assess import selftest as run_selftest
from .godmode_atlas import build as build_atlas
from .godmode_atlas import slice_file
from .godmode_attest import GRADES, STATUSES, reflect, run_check
from .godmode_charter import TRIGGERS, applicable_rules, compile_charter, traits_of
from .godmode_drift import capabilities as host_capabilities
from .godmode_drift import compare as compare_sessions
from .godmode_method import Shape
from .godmode_method import contract as method_contract
from .godmode_method import select as select_method
from .godmode_plan import CONTRACT_FIELDS as PLAN_FIELDS
from .godmode_plan import approve as plan_approve
from .godmode_plan import bind_execution, mutation_verdict
from .godmode_plan import start as plan_start
from .godmode_scope import scope as scope_change
from .godmode_status import STATES, record_item, survey
from .godmode_corpus import build_brief, resolve_roles
from .godmode_egress import notice as egress_notice
from .godmode_egress import scan_project as scan_untrusted
from .godmode_errors import ArchiveError, GodmodeError
from .godmode_forge import SkillProposal, forge_skill, validate_skill
from .godmode_lens import (
    build_context_brief,
    collect_inventory,
    compare_local_reference,
    detect_context_issues,
    explain_context,
    inventory_diff,
    make_snapshot,
    observe_git,
)
from .godmode_sentinel import (
    CapabilityBroker,
    classify_action,
    find_secret_shapes,
    read_password_stdin,
)


@dataclass
class CommandResult:
    payload: Any
    exit_code: int = 0


@dataclass
class Runtime:
    anchor: ProjectAnchor
    archive: Chronicle


def _runtime(project: str) -> Runtime:
    anchor = resolve_anchor(project)
    return Runtime(anchor=anchor, archive=Chronicle(anchor))


def _require_archive(runtime: Runtime) -> None:
    if runtime.archive.initialized():
        return
    # "Not initialized" is the wrong answer when records exist under a previous
    # identity: the history is intact and one command away, so say that instead of
    # implying the project is new.
    orphaned = runtime.archive.orphaned()
    if orphaned:
        raise ArchiveError(
            f"Godmode is not initialized at this project's current identity, but "
            f"{orphaned['records']} records exist under its previous one "
            f"({orphaned['reason']}). Run `adopt --confirm` to relink them, or `init` "
            f"to start a separate archive and leave them unreachable."
        )
    raise ArchiveError("Godmode is not initialized for this project; run `init` first")


def _event_view(record: dict[str, Any]) -> dict[str, Any]:
    data = record["data"]
    if record["kind"] == "inventory":
        data = {
            "captured_at": data.get("captured_at"),
            "files": data.get("files"),
            "categories": data.get("categories", {}),
            "skipped": data.get("skipped", {}),
        }
    return {
        "sequence": record["sequence"],
        "recorded_at": record["recorded_at"],
        "kind": record["kind"],
        "subject": record["subject"],
        "data": data,
        "evidence": record.get("evidence", []),
        "record_hash": record["record_hash"],
    }


def _append(
    runtime: Runtime,
    kind: str,
    subject: str,
    data: dict[str, Any],
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    _require_archive(runtime)
    return _event_view(
        runtime.archive.append(kind, subject, data, evidence=evidence or [])
    )


def cmd_init(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    already = runtime.archive.initialized()
    # Checked before initialize(), because initialize() creates the events directory
    # and would make an adoptable archive look like a populated one.
    orphaned = runtime.archive.orphaned()
    runtime.archive.initialize()
    payload = {
        "initialized": True,
        "already_initialized": already,
        "identity": runtime.anchor.public_view(),
        "archive": "<git-metadata>" if runtime.anchor.is_git else "<os-application-data>",
        "network_used": False,
    }
    if orphaned:
        payload["orphaned_archive"] = orphaned
        payload["next_action"] = (
            "Records exist under this project's previous identity. Run `adopt` to relink "
            "them, or continue and they stay unreachable."
        )
    return CommandResult(payload)


def cmd_adopt(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    orphaned = runtime.archive.orphaned()
    source = args.source or (orphaned or {}).get("source")
    if not source:
        return CommandResult({"adopted": 0, "reason": "no stranded archive found for this project"})
    if not args.confirm:
        return CommandResult(
            {"preview": orphaned or {"source": source}, "confirm_with": "--confirm"},
            exit_code=1,
        )
    runtime.archive.initialize()
    return CommandResult(runtime.archive.adopt(Path(source)))


def cmd_roles(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # Deliberately usable before `init`: a project must be able to see how its
    # authority documents resolve before Godmode holds any state for it.
    resolution = resolve_roles(Path(runtime.anchor.project_root))
    payload = resolution.view()
    if args.check and not resolution.healthy:
        return CommandResult(payload, exit_code=1)
    return CommandResult(payload)


def cmd_brief(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # The artefact every host adapter requests at session open. Identical project
    # state plus an identical task must yield an identical brief on every model.
    brief = build_brief(Path(runtime.anchor.project_root), args.task, args.token_budget)
    brief["project"] = {
        "branch": runtime.anchor.branch,
        "head": runtime.anchor.head,
        "worktree": runtime.anchor.worktree_root is not None,
    }
    if not args.full:
        for entry in brief["context"]:
            entry.pop("body", None)
    return CommandResult(brief)


def _charter(runtime: Runtime) -> dict[str, Any]:
    return compile_charter(Path(runtime.anchor.project_root))


def _session(runtime: Runtime, explicit: str | None) -> str:
    session = explicit or latest_session(runtime.archive)
    if not session:
        raise ArchiveError("No open session; run `session open` first")
    return session


def cmd_charter(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    charter = _charter(runtime)
    if args.at:
        # Narrowing happens here, deterministically, rather than by injecting every
        # rule and relying on the reader to ignore what does not apply.
        scoped = applicable_rules(charter, args.at)
        if not args.full:
            scoped["applicable"] = [
                {"id": r["id"], "enforcement": r["enforcement"], "why": r["why"],
                 "text": r["text"][:120]}
                for r in scoped["applicable"]
            ]
        return CommandResult(scoped)
    if not args.full:
        charter.pop("compiled", None)
    return CommandResult(charter)


def cmd_session_open(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    session = open_session(runtime.archive, args.label)
    return CommandResult({"session": session, "agent": agent_fingerprint()})


def cmd_attest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_step(
        runtime.archive,
        _session(runtime, args.session),
        args.step,
        args.status,
        result=args.result,
        evidence=args.evidence,
        rule_ids=args.rule,
        reason=args.reason,
    )
    return CommandResult({"record": _event_view(record)})


def cmd_verify(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    outcome = run_check(
        runtime.archive, _session(runtime, args.session), Path(runtime.anchor.project_root),
        args.name, shlex.split(args.command), rule_ids=args.rule,
    )
    # The runner decides, not the caller: a failing check exits non-zero here too.
    return CommandResult(outcome, exit_code=0 if outcome["passed"] else 1)


def cmd_gate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    verdict = gate(runtime.archive, _session(runtime, args.session), _charter(runtime), args.trigger)
    return CommandResult(verdict.view(), exit_code=0 if verdict.allowed else 1)


def cmd_claim(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_claim(
        runtime.archive,
        Path(runtime.anchor.project_root),
        _session(runtime, args.session),
        args.text,
        args.grade,
        cites=args.cite,
    )
    data = record["data"]
    # A downgrade is a finding, so it must be visible in the exit status too.
    return CommandResult(
        {"claim": data["text"], "grade": data["grade"], "claimed": data["claimed_grade"],
         "downgraded": data["downgraded"], "reason": data.get("reason", ""),
         "unresolved": data["unresolved"], "unsupported": data.get("unsupported", [])},
        exit_code=1 if data["downgraded"] else 0,
    )


def cmd_session_close(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    verdict = close_session(runtime.archive, _session(runtime, args.session), _charter(runtime))
    return CommandResult(verdict, exit_code=0 if verdict["closed"] else 1)


def cmd_method(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    shape = Shape(
        reports=args.reports,
        reproducible=not args.unreproducible,
        ordering_question=args.ordering,
        components_enumerable=args.components,
        contributing_conditions=args.conditions,
    )
    sequence, reason = select_method(shape)
    return CommandResult(
        {
            "shape": shape.view(),
            "sequence": sequence,
            "reason": reason,
            "contracts": {method: list(method_contract(method)) for method in sequence},
        }
    )


def cmd_status_set(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_item(
        runtime.archive, args.item, args.title, args.state,
        evidence=args.evidence, proof=args.proof,
    )
    return CommandResult({"record": _event_view(record)})


def cmd_status_survey(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = survey(runtime.archive, Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=1 if report["verdict"] == "competing-authority" else 0)


def cmd_planmode_start(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    contract = {field: getattr(args, field) or "" for field in PLAN_FIELDS}
    started = plan_start(runtime.archive, _session(runtime, args.session), args.title, contract)
    return CommandResult(started, exit_code=1 if started["gaps"] else 0)


def cmd_planmode_approve(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    verdict = plan_approve(runtime.archive, _session(runtime, args.session))
    return CommandResult(verdict, exit_code=0 if verdict["approved"] else 1)


def cmd_planmode_check(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    verdict = mutation_verdict(runtime.archive, _session(runtime, args.session))
    return CommandResult(verdict, exit_code=0 if verdict["allowed"] else 1)


def cmd_planmode_bind(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    bound = bind_execution(runtime.archive, _session(runtime, args.session), args.summary, args.file)
    return CommandResult(bound, exit_code=1 if bound["outside_scope"] else 0)


def cmd_drift(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = compare_sessions(runtime.archive)
    return CommandResult(report, exit_code=1 if report["verdict"] == "drift-detected" else 0)


def cmd_capabilities(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(host_capabilities())


def cmd_assess(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = assess_project(Path(runtime.anchor.project_root), budget=args.token_budget)
    if not args.full:
        report["authority_claims"].pop("top", None)
    return CommandResult(report, exit_code=1 if report["verdict"] == "at-risk" else 0)


def cmd_selftest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = run_selftest()
    return CommandResult(report, exit_code=0 if report["verdict"] == "enforcing" else 1)


def cmd_scope(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = scope_change(Path(runtime.anchor.project_root), args.since)
    if not args.full:
        report["units"] = [
            {"key": u["key"], "paths": u["paths"], "bundled_because": u["bundled_because"]}
            for u in report["units"]
        ]
    # An enumeration that lost an artefact is the failure this command prevents.
    return CommandResult(report, exit_code=0 if report["complete"] else 1)


def cmd_assurance(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult({"document": assurance_case()})


def cmd_reflect(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = reflect(runtime.archive, args.text)
    # A suspected conflict is a lead for a human, so it is surfaced in the exit
    # status without being asserted as a contradiction.
    return CommandResult(report, exit_code=1 if report.get("conflicts") else 0)


def cmd_egress(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    disclosure = egress_notice(args.action, args.purpose,
                               Path(runtime.anchor.project_root), args.path)
    # A secret inside the requested scope blocks the disclosure rather than
    # redacting quietly: the user decides, having been told.
    return CommandResult(disclosure, exit_code=1 if disclosure["blocked"] else 0)


def cmd_untrusted(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = scan_untrusted(Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=1 if report["files_with_findings"] else 0)


def cmd_atlas(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    atlas = build_atlas(Path(runtime.anchor.project_root))
    if args.atlas_command == "map":
        return CommandResult(atlas.view())
    if args.atlas_command == "affected":
        return CommandResult(atlas.affected(args.symbol, depth=args.depth,
                                            evidence=None if args.include_inferred else "extracted"))
    if args.atlas_command == "cycles":
        found = atlas.cycles()
        return CommandResult({"cycles": found}, exit_code=1 if found else 0)
    if args.atlas_command == "duplicates":
        pairs = atlas.duplicates(threshold=args.threshold)
        return CommandResult({"pairs": pairs, "threshold": args.threshold})
    if args.atlas_command == "orphans":
        found = atlas.orphans()
        return CommandResult({"orphans": found, "count": len(found)})
    report = atlas.diagnose()
    return CommandResult(report, exit_code=0 if report["trustworthy"] else 1)


def cmd_slice(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    window = slice_file(Path(runtime.anchor.project_root) / args.path, args.start, args.end)
    return CommandResult(window)


def cmd_inspect(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    snapshot = make_snapshot(runtime.anchor)
    evidence = [runtime.anchor.head] if runtime.anchor.head else []
    record = runtime.archive.append(
        "inventory", "repository-snapshot", snapshot, evidence=evidence
    )
    return CommandResult(
        {
            "record": _event_view(record),
            "git": {
                "branch": snapshot.get("branch"),
                "head": snapshot.get("head"),
                "changes": len(snapshot["git"].get("changes", [])),
                "worktrees": len(snapshot["git"].get("worktrees", [])),
            },
        }
    )


def cmd_resume(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    current = None
    if args.refresh:
        current = make_snapshot(runtime.anchor)
        runtime.archive.append(
            "inventory",
            "resume-refresh",
            current,
            evidence=[runtime.anchor.head] if runtime.anchor.head else [],
        )
    return CommandResult(
        build_context_brief(
            runtime.anchor,
            runtime.archive,
            current_inventory=current,
            token_budget=args.token_budget,
        )
    )


def cmd_context_status(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    records = runtime.archive.read_events()
    current = collect_inventory(runtime.anchor.project_root) if args.scan else None
    payload = {
        "archive": runtime.archive.verify(records),
        "identity": runtime.anchor.public_view(),
        "issues": detect_context_issues(runtime.anchor, records, current),
        "scan_performed": args.scan,
    }
    orphaned = runtime.archive.orphaned()
    if orphaned:
        payload["orphaned_archive"] = orphaned
    return CommandResult(payload)


def cmd_context_rebuild(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return cmd_inspect(args, runtime)


def cmd_context_why(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(explain_context(runtime.anchor, runtime.archive))


def cmd_inventory_diff(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    previous = runtime.archive.latest("inventory")
    current = collect_inventory(runtime.anchor.project_root)
    return CommandResult(
        {
            "baseline_sequence": previous["sequence"] if previous else None,
            "diff": inventory_diff(previous["data"] if previous else None, current),
            "current_files": current["files"],
        }
    )


def cmd_history(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    records = runtime.archive.select(kind=args.kind, subject=args.subject, limit=args.limit)
    return CommandResult({"records": [_event_view(record) for record in records]})


def cmd_plan(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if not args.step:
        raise ArchiveError("Plan requires at least one --step")
    record = _append(
        runtime,
        "plan",
        args.title,
        {
            "status": "active",
            "steps": [{"text": step, "status": "pending"} for step in args.step],
            "obligations": args.obligation,
        },
        args.evidence,
    )
    return CommandResult({"record": record})


def cmd_build(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.status in {"complete", "fixed"} and not args.evidence:
        raise ArchiveError("Completion requires at least one --evidence reference")
    record = _append(
        runtime,
        "change",
        args.summary,
        {
            "status": args.status,
            "files": args.file,
            "hypothesis": args.hypothesis,
            "outcome": args.outcome,
        },
        args.evidence,
    )
    return CommandResult({"record": record})


def cmd_checkpoint(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.status in {"complete", "fixed"} and not args.evidence:
        raise ArchiveError("Completion requires at least one --evidence reference")
    return CommandResult(
        {
            "record": _append(
                runtime,
                "checkpoint",
                args.summary,
                {
                    "status": args.status,
                    "next": args.next_action,
                    "hypothesis": args.hypothesis,
                    "outcome": args.outcome or args.status,
                },
                args.evidence,
            )
        }
    )


def cmd_checklist_update(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.status in {"complete", "done"} and not args.evidence:
        raise ArchiveError("A completed checklist item requires --evidence")
    return CommandResult(
        {
            "record": _append(
                runtime,
                "checklist",
                args.item,
                {"status": args.status, "note": args.note},
                args.evidence,
            )
        }
    )


def cmd_remember(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    data: dict[str, Any] = {"value": args.value, "status": args.status}
    if args.kind == "lesson":
        data["generalized_guard"] = args.guard
    return CommandResult(
        {"record": _append(runtime, args.kind, args.subject, data, args.evidence)}
    )


def cmd_doctor(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if not runtime.archive.initialized():
        return CommandResult(
            {
                "healthy": False,
                "issues": [{"code": "not-initialized", "severity": "error", "detail": "Run init."}],
                "network_used": False,
            },
            exit_code=1,
        )
    records = runtime.archive.read_events()
    verification = runtime.archive.verify(records)
    current = collect_inventory(runtime.anchor.project_root) if args.deep else None
    issues = detect_context_issues(runtime.anchor, records, current)
    secret_locations: list[str] = []
    for path in runtime.archive.root.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        secret_locations.extend(f"{path.name}:{item}" for item in find_secret_shapes(value))
    if secret_locations:
        issues.append(
            {
                "code": "secret-shaped-state",
                "severity": "error",
                "detail": f"Potential secret material at {', '.join(secret_locations[:5])}.",
            }
        )
    healthy = not any(issue["severity"] == "error" for issue in issues)
    return CommandResult(
        {
            "healthy": healthy,
            "archive": verification,
            "issues": issues,
            "deep_scan": args.deep,
            "network_used": False,
            "background_process": False,
        },
        exit_code=0 if healthy else 1,
    )


def cmd_privacy(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    findings: list[str] = []
    scanned = 0
    for path in runtime.archive.root.rglob("*.json"):
        scanned += 1
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        findings.extend(f"{path.name}:{item}" for item in find_secret_shapes(value))
    return CommandResult(
        {
            "private": not findings,
            "files_scanned": scanned,
            "findings": findings,
            "network": "disabled",
            "telemetry": "absent",
            "prompt_capture": "absent",
            "source_body_capture": "absent",
        },
        exit_code=0 if not findings else 1,
    )


def cmd_guard(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    preview = classify_action(args.operation)
    preview["operation"] = args.operation
    preview["executes_operation"] = False
    if not preview["protected"]:
        preview["authorized"] = True
        preview["capability_required"] = False
        return CommandResult(preview)
    preview["capability_required"] = True
    if not args.capability:
        preview["authorized"] = False
        preview["next"] = "Review the impact, then run authorize issue for this exact operation."
        return CommandResult(preview, exit_code=3)
    CapabilityBroker(runtime.archive).consume(args.operation, args.capability)
    preview["authorized"] = True
    preview["capability_consumed"] = True
    return CommandResult(preview)


def cmd_authorize_setup(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    broker = CapabilityBroker(runtime.archive)
    if args.password_stdin:
        broker.configure(read_password_stdin())
    else:
        broker.configure_interactive()
    return CommandResult({"configured": True, "storage": "local-only"})


def cmd_authorize_issue(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    preview = classify_action(args.operation)
    broker = CapabilityBroker(runtime.archive)
    if args.password_stdin:
        token = broker.issue(args.operation, read_password_stdin(), args.ttl)
    else:
        token = broker.issue_interactive(args.operation, args.ttl)
    return CommandResult(
        {
            "capability": token,
            "category": preview["category"],
            "expires_in_seconds": args.ttl,
            "scope": "exact operation digest",
            "uses": 1,
        }
    )


def cmd_actions(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(
        {"actions": [_event_view(record) for record in runtime.archive.select(kind="action", limit=args.limit)]}
    )


def cmd_branches(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    observation = observe_git(runtime.anchor)
    if args.record:
        runtime.archive.append(
            "branch",
            "git-topology",
            observation,
            evidence=[runtime.anchor.head] if runtime.anchor.head else [],
        )
    return CommandResult({"recorded": args.record, **observation})


def cmd_version(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(
        {"record": _append(runtime, "version", args.name, {"value": args.value, "status": args.status}, args.evidence)}
    )


def cmd_database(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(
        {
            "record": _append(
                runtime,
                "database",
                args.change,
                {"engine": args.engine, "status": args.status, "rollback": args.rollback},
                args.evidence,
            )
        }
    )


def cmd_sprint(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(
        {
            "record": _append(
                runtime,
                "sprint",
                args.name,
                {"status": args.status, "capacity": args.capacity, "obligations": args.obligation},
                args.evidence,
            )
        }
    )


def cmd_docs(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(
        {
            "record": _append(
                runtime,
                "documentation",
                args.document,
                {"status": args.status, "note": args.note},
                args.evidence,
            )
        }
    )


def cmd_report(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(
        build_context_brief(
            runtime.anchor, runtime.archive, token_budget=args.token_budget
        )
    )


def cmd_export(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    output = Path(args.output).expanduser().resolve(strict=False)
    if output.exists() and not args.overwrite:
        raise ArchiveError("Export target exists; pass --overwrite to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_context_brief(runtime.anchor, runtime.archive, token_budget=args.token_budget)
    payload["exported_at"] = datetime.now(timezone.utc).isoformat()
    payload["raw_archive_included"] = False
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    temporary = output.with_name(f".{output.name}.godmode.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(output)
    return CommandResult(
        {"exported": True, "output": str(output), "raw_archive_included": False}
    )


def cmd_parity(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    result = compare_local_reference(runtime.anchor.project_root, args.reference)
    runtime.archive.append(
        "decision",
        "local-parity-observation",
        {
            "reference_digest": result["reference_digest"],
            "category_gaps": result["category_gaps"],
            "status": "observed",
        },
        evidence=[],
    )
    return CommandResult(result)


def cmd_skill_validate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(validate_skill(args.path))


def cmd_skill_forge(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    proposal = SkillProposal(
        name=args.name,
        purpose=args.purpose,
        gap_evidence=args.gap_evidence,
        repeated_uses=args.repeated_uses,
        positive_triggers=tuple(args.positive),
        negative_triggers=tuple(args.negative),
        assertions=tuple(args.assertion),
    )
    created = forge_skill(args.destination, proposal)
    runtime.archive.append(
        "decision",
        f"skill-created:{args.name}",
        {
            "status": "created",
            "skill": args.name,
            "destination_digest": __import__("hashlib").sha256(str(created).encode()).hexdigest(),
            "repeated_uses": args.repeated_uses,
        },
        evidence=[],
    )
    return CommandResult({"created": True, "path": str(created), "validation": validate_skill(created)})


def _evidence(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence", action="append", default=[], help="Evidence reference or digest; repeatable")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="godmode",
        description="Local-first context continuity and guarded coding workflows.",
    )
    parser.add_argument("--project", default=".", help="Project directory (default: current directory)")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON")
    parser.add_argument("--version", action="version", version=f"Godmode {RUNTIME_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize the private local archive").set_defaults(handler=cmd_init)
    adopt = sub.add_parser("adopt", help="Relink records stranded by an identity change (e.g. git init)")
    adopt.add_argument("--source", help="Archive root to adopt; defaults to the detected one")
    adopt.add_argument("--confirm", action="store_true", help="Perform the relink, not just preview it")
    adopt.set_defaults(handler=cmd_adopt)
    roles = sub.add_parser("roles", help="Resolve authority documents by role")
    roles.add_argument("--check", action="store_true", help="Exit non-zero when two roles claim one path")
    roles.set_defaults(handler=cmd_roles)
    brief = sub.add_parser("brief", help="Assemble a bounded, model-independent context brief")
    brief.add_argument("task", help="What this session is about; drives relevance ranking")
    brief.add_argument("--token-budget", type=int, default=DEFAULT_CONTEXT_BUDGET)
    brief.add_argument("--full", action="store_true", help="Include segment bodies, not just the map")
    brief.set_defaults(handler=cmd_brief)

    charter = sub.add_parser("charter", help="Compile prose guidance into addressable rules")
    charter.add_argument("--full", action="store_true", help="Include every compiled rule")
    charter.add_argument("--at", metavar="PATH",
                         help="Narrow to the rules that apply to this artefact's characteristics")
    charter.set_defaults(handler=cmd_charter)

    session = sub.add_parser("session", help="Open or close an attested session")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_open = session_sub.add_parser("open")
    session_open.add_argument("--label", default="session")
    session_open.set_defaults(handler=cmd_session_open)
    session_close = session_sub.add_parser("close")
    session_close.add_argument("--session")
    session_close.set_defaults(handler=cmd_session_close)

    attest = sub.add_parser("attest", help="Record that a mandated step ran, found nothing, or was skipped")
    attest.add_argument("step")
    attest.add_argument("--status", choices=list(STATUSES), required=True)
    attest.add_argument("--result", default="")
    attest.add_argument("--reason", default="", help="Required when the status is 'skipped'")
    attest.add_argument("--rule", action="append", default=[], help="Rule id this step satisfies; repeatable")
    attest.add_argument("--session")
    _evidence(attest)
    attest.set_defaults(handler=cmd_attest)

    verify = sub.add_parser("verify", help="Run a declared check and attest its exit code")
    verify.add_argument("name")
    verify.add_argument("--rule", action="append", default=[], help="Rule id this check satisfies; repeatable")
    verify.add_argument("--session")
    # Not argparse.REMAINDER: a REMAINDER positional swallows the options that
    # follow the first positional, so --rule would land inside the command.
    verify.add_argument("--command", required=True, help="Command to run, as one quoted string")
    verify.set_defaults(handler=cmd_verify)

    gate_parser = sub.add_parser("gate", help="Check a trigger; exit non-zero when a HARD rule is unattested")
    gate_parser.add_argument("--trigger", choices=list(TRIGGERS), required=True)
    gate_parser.add_argument("--session")
    gate_parser.set_defaults(handler=cmd_gate)

    claim = sub.add_parser("claim", help="Record a claim; unsupported claims are downgraded, not warned about")
    claim.add_argument("text")
    claim.add_argument("--grade", choices=list(GRADES), default="observed")
    claim.add_argument("--cite", action="append", default=[], help="rec:<hash> or file:<path>#L<n>; repeatable")
    claim.add_argument("--session")
    claim.set_defaults(handler=cmd_claim)

    method = sub.add_parser("method", help="Select an analysis method from the evidence shape")
    method.add_argument("--reports", type=int, default=1)
    method.add_argument("--unreproducible", action="store_true")
    method.add_argument("--ordering", action="store_true", help="An ordering, race or latch-time question")
    method.add_argument("--components", action="store_true", help="Components and failure modes are enumerable")
    method.add_argument("--conditions", type=int, default=0, help="Contributing conditions on one failure")
    method.set_defaults(handler=cmd_method)

    status = sub.add_parser("status", help="Single writable status store")
    status_sub = status.add_subparsers(dest="status_command", required=True)
    status_set = status_sub.add_parser("set")
    status_set.add_argument("item")
    status_set.add_argument("--title", default="")
    status_set.add_argument("--state", choices=list(STATES), required=True)
    status_set.add_argument("--proof", default="", help="Required to reopen verified or closed work")
    _evidence(status_set)
    status_set.set_defaults(handler=cmd_status_set)
    status_sub.add_parser("survey").set_defaults(handler=cmd_status_survey)

    # Named `planmode` rather than extending `plan`: `plan` is part of the released
    # command surface and converting it to subcommands would break existing callers.
    planmode = sub.add_parser("planmode", help="Gate mutation behind an approved plan contract")
    planmode_sub = planmode.add_subparsers(dest="planmode_command", required=True)
    planmode_start = planmode_sub.add_parser("start")
    planmode_start.add_argument("--title", required=True)
    planmode_start.add_argument("--session")
    for field in PLAN_FIELDS:
        planmode_start.add_argument(f"--{field.replace('_', '-')}", dest=field, default="")
    planmode_start.set_defaults(handler=cmd_planmode_start)
    planmode_approve = planmode_sub.add_parser("approve")
    planmode_approve.add_argument("--session")
    planmode_approve.set_defaults(handler=cmd_planmode_approve)
    planmode_check = planmode_sub.add_parser("check")
    planmode_check.add_argument("--session")
    planmode_check.set_defaults(handler=cmd_planmode_check)
    planmode_bind = planmode_sub.add_parser("bind")
    planmode_bind.add_argument("--summary", required=True)
    planmode_bind.add_argument("--file", action="append", default=[])
    planmode_bind.add_argument("--session")
    planmode_bind.set_defaults(handler=cmd_planmode_bind)

    assess_parser = sub.add_parser("assess", help="Grade whether this project's own rules can be complied with")
    assess_parser.add_argument("--token-budget", type=int, default=2500)
    assess_parser.add_argument("--full", action="store_true")
    assess_parser.set_defaults(handler=cmd_assess)
    sub.add_parser("selftest", help="Exercise every control and report what actually held").set_defaults(
        handler=cmd_selftest
    )

    egress = sub.add_parser("egress", help="Disclose exactly what an action would send")
    egress.add_argument("action")
    egress.add_argument("--purpose", default="unstated")
    egress.add_argument("--path", action="append", default=[], help="Artefact proposed for inclusion; repeatable")
    egress.set_defaults(handler=cmd_egress)
    sub.add_parser("untrusted", help="Report repository text shaped like an instruction").set_defaults(
        handler=cmd_untrusted
    )

    sub.add_parser("assurance", help="Emit an assurance case generated from live probes").set_defaults(
        handler=cmd_assurance
    )
    reflect_parser = sub.add_parser("reflect", help="Check a claim against what the record already says")
    reflect_parser.add_argument("text")
    reflect_parser.set_defaults(handler=cmd_reflect)

    scope_parser = sub.add_parser("scope", help="Enumerate the work before reasoning about it")
    scope_parser.add_argument("--since", help="Compare against this ref instead of the working tree")
    scope_parser.add_argument("--full", action="store_true")
    scope_parser.set_defaults(handler=cmd_scope)

    atlas = sub.add_parser("atlas", help="Map the project's symbols and their relationships")
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=True)
    atlas_sub.add_parser("map").set_defaults(handler=cmd_atlas)
    atlas_affected = atlas_sub.add_parser("affected")
    atlas_affected.add_argument("symbol")
    atlas_affected.add_argument("--depth", type=int, default=2)
    atlas_affected.add_argument("--include-inferred", action="store_true",
                                help="Include guessed relationships; excluded by default")
    atlas_affected.set_defaults(handler=cmd_atlas)
    atlas_sub.add_parser("cycles").set_defaults(handler=cmd_atlas)
    atlas_dupes = atlas_sub.add_parser("duplicates")
    atlas_dupes.add_argument("--threshold", type=float, default=0.72)
    atlas_dupes.set_defaults(handler=cmd_atlas)
    atlas_sub.add_parser("orphans").set_defaults(handler=cmd_atlas)
    atlas_sub.add_parser("diagnose").set_defaults(handler=cmd_atlas)

    sliced = sub.add_parser("slice", help="Read a bounded window that declares its own edges")
    sliced.add_argument("path")
    sliced.add_argument("--start", type=int, default=1)
    sliced.add_argument("--end", type=int)
    sliced.set_defaults(handler=cmd_slice)

    sub.add_parser("drift", help="Compare step sets across sessions and agents").set_defaults(
        handler=cmd_drift
    )
    sub.add_parser("capabilities", help="Report what this host can actually enforce").set_defaults(
        handler=cmd_capabilities
    )
    inspect = sub.add_parser("inspect", help="Capture an on-demand repository snapshot")
    inspect.set_defaults(handler=cmd_inspect)
    resume = sub.add_parser("resume", help="Build a bounded continuity brief")
    resume.add_argument("--refresh", action="store_true", help="Capture a fresh snapshot first")
    resume.add_argument("--token-budget", type=int, default=DEFAULT_CONTEXT_BUDGET)
    resume.set_defaults(handler=cmd_resume)

    context = sub.add_parser("context", help="Inspect or rebuild context continuity")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    context_status = context_sub.add_parser("status")
    context_status.add_argument("--scan", action="store_true")
    context_status.set_defaults(handler=cmd_context_status)
    context_sub.add_parser("rebuild").set_defaults(handler=cmd_context_rebuild)
    context_sub.add_parser("why").set_defaults(handler=cmd_context_why)

    inventory = sub.add_parser("inventory", help="Repository inventory operations")
    inventory_sub = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_sub.add_parser("diff").set_defaults(handler=cmd_inventory_diff)

    history = sub.add_parser("history", help="Read structured local history")
    history.add_argument("--kind", choices=sorted(EVENT_KINDS))
    history.add_argument("--subject")
    history.add_argument("--limit", type=int, default=50)
    history.set_defaults(handler=cmd_history)

    plan = sub.add_parser("plan", help="Record a private execution contract")
    plan.add_argument("--title", required=True)
    plan.add_argument("--step", action="append", default=[])
    plan.add_argument("--obligation", action="append", default=[])
    _evidence(plan)
    plan.set_defaults(handler=cmd_plan)

    build = sub.add_parser("build", help="Record an implementation result")
    build.add_argument("--summary", required=True)
    build.add_argument("--status", choices=["started", "changed", "complete", "fixed", "failed"], default="changed")
    build.add_argument("--file", action="append", default=[])
    build.add_argument("--hypothesis")
    build.add_argument("--outcome")
    _evidence(build)
    build.set_defaults(handler=cmd_build)

    checkpoint = sub.add_parser("checkpoint", help="Record a recoverable handoff point")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--status", required=True)
    checkpoint.add_argument("--next", dest="next_action", action="append", default=[])
    checkpoint.add_argument("--hypothesis")
    checkpoint.add_argument("--outcome")
    _evidence(checkpoint)
    checkpoint.set_defaults(handler=cmd_checkpoint)

    checklist = sub.add_parser("checklist", help="Update a cumulative private check")
    checklist_sub = checklist.add_subparsers(dest="checklist_command", required=True)
    checklist_update = checklist_sub.add_parser("update")
    checklist_update.add_argument("--item", required=True)
    checklist_update.add_argument("--status", choices=["pending", "active", "blocked", "complete", "done"], required=True)
    checklist_update.add_argument("--note")
    _evidence(checklist_update)
    checklist_update.set_defaults(handler=cmd_checklist_update)

    remember = sub.add_parser("remember", help="Record a decision, invariant, lesson, or obligation")
    remember.add_argument("--kind", choices=["decision", "invariant", "lesson", "obligation"], required=True)
    remember.add_argument("--subject", required=True)
    remember.add_argument("--value", required=True)
    remember.add_argument("--status", default="active")
    remember.add_argument("--guard")
    _evidence(remember)
    remember.set_defaults(handler=cmd_remember)

    doctor = sub.add_parser("doctor", help="Verify archive and continuity health")
    doctor.add_argument("--deep", action="store_true")
    doctor.set_defaults(handler=cmd_doctor)
    sub.add_parser("privacy", help="Audit the local privacy boundary").set_defaults(handler=cmd_privacy)

    guard = sub.add_parser("guard", help="Preview and authorize an exact operation without executing it")
    guard.add_argument("--operation", required=True)
    guard.add_argument("--capability")
    guard.set_defaults(handler=cmd_guard)

    authorize = sub.add_parser("authorize", help="Configure or issue local capabilities")
    authorize_sub = authorize.add_subparsers(dest="authorize_command", required=True)
    setup = authorize_sub.add_parser("setup")
    setup.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting",
    )
    setup.set_defaults(handler=cmd_authorize_setup)
    issue = authorize_sub.add_parser("issue")
    issue.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting",
    )
    issue.add_argument("--operation", required=True)
    issue.add_argument("--ttl", type=int, default=180)
    issue.set_defaults(handler=cmd_authorize_issue)
    actions = sub.add_parser("actions", help="Read capability audit events")
    actions.add_argument("--limit", type=int, default=50)
    actions.set_defaults(handler=cmd_actions)

    branches = sub.add_parser("branches", help="Inspect branches and worktrees")
    branches.add_argument("--record", action="store_true")
    branches.set_defaults(handler=cmd_branches)

    version = sub.add_parser("version", help="Record a project version fact")
    version.add_argument("--name", required=True)
    version.add_argument("--value", required=True)
    version.add_argument("--status", default="observed")
    _evidence(version)
    version.set_defaults(handler=cmd_version)

    database = sub.add_parser("db", help="Record database governance state")
    database.add_argument("--engine", required=True)
    database.add_argument("--change", required=True)
    database.add_argument("--status", required=True)
    database.add_argument("--rollback")
    _evidence(database)
    database.set_defaults(handler=cmd_database)

    sprint = sub.add_parser("sprint", help="Record private sprint state")
    sprint.add_argument("--name", required=True)
    sprint.add_argument("--status", required=True)
    sprint.add_argument("--capacity", type=int)
    sprint.add_argument("--obligation", action="append", default=[])
    _evidence(sprint)
    sprint.set_defaults(handler=cmd_sprint)

    docs = sub.add_parser("docs", help="Record documentation obligations")
    docs.add_argument("--document", required=True)
    docs.add_argument("--status", required=True)
    docs.add_argument("--note")
    _evidence(docs)
    docs.set_defaults(handler=cmd_docs)

    report = sub.add_parser("report", help="Emit a sanitized bounded report")
    report.add_argument("--token-budget", type=int, default=700)
    report.set_defaults(handler=cmd_report)
    export = sub.add_parser("export", help="Write a sanitized context report")
    export.add_argument("--output", required=True)
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--token-budget", type=int, default=700)
    export.set_defaults(handler=cmd_export)

    sub.add_parser("explain-context", help="Explain included and excluded continuity data").set_defaults(handler=cmd_context_why)
    parity = sub.add_parser("parity", help="Compare neutral structure with an explicit local reference")
    parity.add_argument("--reference", required=True)
    parity.set_defaults(handler=cmd_parity)

    skill = sub.add_parser("skill", help="Validate or forge a project skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_validate = skill_sub.add_parser("validate")
    skill_validate.add_argument("--path", required=True)
    skill_validate.set_defaults(handler=cmd_skill_validate)
    skill_forge = skill_sub.add_parser("forge")
    skill_forge.add_argument("--destination", required=True)
    skill_forge.add_argument("--name", required=True)
    skill_forge.add_argument("--purpose", required=True)
    skill_forge.add_argument("--gap-evidence", required=True)
    skill_forge.add_argument("--repeated-uses", type=int, required=True)
    skill_forge.add_argument("--positive", action="append", default=[])
    skill_forge.add_argument("--negative", action="append", default=[])
    skill_forge.add_argument("--assertion", action="append", default=[])
    skill_forge.set_defaults(handler=cmd_skill_forge)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy code page, so any non-ASCII character in a
    # project's own documents would abort the command on output. Project content is
    # not ours to constrain; the encoding is.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover - exotic stream
                pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "token_budget") and not 200 <= args.token_budget <= 10_000:
        parser.error("--token-budget must be between 200 and 10000")
    try:
        runtime = _runtime(args.project)
        handler: Callable[[argparse.Namespace, Runtime], CommandResult] = args.handler
        result = handler(args, runtime)
        print(
            json.dumps(
                result.payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":") if args.json else None,
                indent=None if args.json else 2,
            )
        )
        return result.exit_code
    except GodmodeError as exc:
        payload = {"error": exc.__class__.__name__, "message": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
