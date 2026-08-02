"""Godmode command surface."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable

from .godmode_anchor import ProjectAnchor, resolve_anchor
from .godmode_chronicle import Chronicle
from .godmode_constants import DEFAULT_CONTEXT_BUDGET, EVENT_KINDS, RUNTIME_VERSION
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
from .godmode_sentinel import CapabilityBroker, classify_action, find_secret_shapes


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
    if not runtime.archive.initialized():
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
    runtime.archive.initialize()
    return CommandResult(
        {
            "initialized": True,
            "already_initialized": already,
            "identity": runtime.anchor.public_view(),
            "archive": "<git-metadata>" if runtime.anchor.is_git else "<os-application-data>",
            "network_used": False,
        }
    )


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
    return CommandResult(
        {
            "archive": runtime.archive.verify(records),
            "identity": runtime.anchor.public_view(),
            "issues": detect_context_issues(runtime.anchor, records, current),
            "scan_performed": args.scan,
        }
    )


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
    broker.configure_interactive()
    return CommandResult({"configured": True, "storage": "local-only"})


def cmd_authorize_issue(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    preview = classify_action(args.operation)
    token = CapabilityBroker(runtime.archive).issue_interactive(
        args.operation, args.ttl
    )
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
    authorize_sub.add_parser("setup").set_defaults(handler=cmd_authorize_setup)
    issue = authorize_sub.add_parser("issue")
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
