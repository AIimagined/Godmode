"""Godmode command surface."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import shlex
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

from .godmode_anchor import ProjectAnchor, current_host, resolve_anchor
from .godmode_chronicle import Chronicle
from .godmode_hookproof import (
    FAIL_OPEN_HOSTS, degraded_reason, hook_manifest_status, interception_state,
    last_latency_check, last_proof, run_probe,
)
from .godmode_githooks import (
    HOOK_NAMES as GIT_HOOK_NAMES,
    evaluate_git_hook,
    git_hooks_install,
    git_hooks_status,
    git_hooks_uninstall,
    run_git_verify,
)
from .godmode_constants import DEFAULT_CONTEXT_BUDGET, EVENT_KINDS, RUNTIME_VERSION
from .godmode_attest import (
    advisory_decay,
    agent_fingerprint,
    close_session,
    gate,
    latest_session,
    open_session,
    opening_handshake,
    calibration_summary,
    record_claim,
    resolve_claim,
    record_criterion,
    record_differential,
    record_step,
    register_error_pattern,
    register_metric_contract,
)
from .godmode_attest import BLAST_RADIUS_KINDS
from .godmode_assess import assess as assess_project
from .godmode_assess import assurance_case
from .godmode_assess import selftest as run_selftest
from .godmode_atlas import build as build_atlas
from .godmode_atlas import load_index, save_index, slice_file
from .godmode_attest import (
    GRADES, RESOLUTION_OUTCOMES, STATUSES, plant_and_observe, recurrences,
    reflect, run_check,
)
from .godmode_bindings import check as bindings_check
from .godmode_bindings import dependency_gate, release_checksums, sbom_cyclonedx, sbom_spdx
from .godmode_bindings import install_verify as hooks_install_verify
from .godmode_bindings import registration_report as hooks_registration_report
from .godmode_bindings import sbom as build_sbom
from .godmode_bindings import write as bindings_write
from .godmode_charter import ADVISORY, TRIGGERS, applicable_rules, bootstrap_rules, compile_charter, traits_of
from .godmode_drift import capabilities as host_capabilities
from .godmode_changelog import check_fragments, merge_fragments
from .godmode_integrity import analyze as analyze_integrity
from .godmode_evals import (
    adversarial_grid,
    charter_snapshot,
    check_snapshots,
    ranking_snapshot,
    run_behavior_assertions,
    run_routing_evals,
)
from .godmode_guardrails import arbitrate, check_ceilings, rewind_preview, watchdog
from .godmode_locale import check_locales
from .godmode_loop import analyze as analyze_loops
from .godmode_loop import model_blame_allowed
# U-R2/Task-10b - minimal isolated block (one import line, one argparse flag,
# one handler branch), same pattern as the U-V2 register block above.
from .godmode_loop import LOOP_CONFIG_FILENAME, loop_ready
from .godmode_mistakes import analyze as analyze_mistakes
from .godmode_mistakes import stale_runtime
from .godmode_netgate import differential as netgate_differential
from .godmode_parity import absorption_check, parity_matrix, schema_ladder
from .godmode_reconcile import classify_environment, reconcile_docs, reconcile_versions, record_triggers
from .godmode_reconcile import reconcile_capabilities, reconcile_capability_coverage, reconcile_detectors
from .godmode_minimality import (
    accept_growth,
    minimality_report,
    pressure_report,
    write_pressure_baseline,
)
from .godmode_removal import REQUIRED_FIELDS as REMOVAL_FIELDS
from .godmode_report import completion_report, render_markdown
from .godmode_docslint import lint_docs
from .godmode_quality import quality_report, render_editor, render_sarif
from .godmode_examples import check_examples, load_examples
from .godmode_freshness import freshness_report
from .godmode_watchdog import interrupt as watchdog_interrupt, watchdog_report
from .godmode_arbiter import arbitrate as arbitrate_plans
from .godmode_extensions import ExtensionRefused, list_extensions, run_extension
from .godmode_claimscan import scan_public_surfaces

# The plugin's own root: scripts/godmode_runtime/godmode_console.py -> two
# up. Used for artefacts that ship WITH the plugin (the example corpus,
# the ladder) as opposed to anything under the operator's project.
_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
from .godmode_trust import scan_agent_configuration
from .godmode_obligations import review_obligations
from .godmode_atlas import speculative_seams, unfollowed_dependents
from .godmode_precheck import declare_paired_artifact, precheck as run_precheck
from .godmode_fence import (
    BOUNDARY_CONFIG, audit_changes, completion_audit, declared_design, propose_design,
    unaccepted_completions,
)
from .godmode_fence import deletion_verdict, record_deletion_precheck
from .godmode_requests import digest as request_digest, review_requests
from .godmode_census import census, render as render_census
from .godmode_census import uncaptured_corrections
from .godmode_release import compare_releases, render as render_release
from .godmode_loop import _git as _git_tags_raw
from .godmode_report import claims_from_report
from .godmode_contribution import contribution
from .godmode_contribution import render_line as render_contribution
from .godmode_fuzz import fuzz as run_fuzz
from .godmode_metrics import metrics as product_metrics
from .godmode_metrics import render_markdown as render_metrics
from .godmode_roi import render_digest as render_roi_digest
from .godmode_roi import render_roi
from .godmode_roi import roi_digest
from .godmode_roi import roi_report
from .godmode_roi import would_have_summary
from .godmode_trends import render_trends, trends_report
# U-E10 - minimal isolated block (one import line, one subcommand, one
# handler), same pattern as the U-R2 loop-ready block above.
from .godmode_recurrence import DEFAULT_THRESHOLD as RECURRENCE_DEFAULT_THRESHOLD
from .godmode_recurrence import mine_recurring_asks, render as render_recurrence
# B3-1 (GAP-1) - minimal isolated block (one import line, one subcommand,
# one handler), same pattern as the U-E10 recurring-ask block above.
from .godmode_upstream import record_upstream_diff
from .godmode_stages import advance as stage_advance
from .godmode_stages import skip_stage, sop_attest, sop_status, stage_gate
from .godmode_index import IndexStale
from .godmode_index import fresh as index_fresh
from .godmode_index import query as index_query
from .godmode_index import rebuild as index_rebuild
from .godmode_dbmgr import migration_review, schema_inventory, schema_review
from .godmode_removal import record_removal, removal_answer
from .godmode_drift import compare as compare_sessions
from .godmode_method import METHODS as METHOD_NAMES
from .godmode_method import Shape, configured_spines, fault_tree_cut_sets, pareto_order, rank_fmea
from .godmode_method import complete as method_complete
from .godmode_method import contract as method_contract
from .godmode_method import select as select_method
from .godmode_plan import CONTRACT_FIELDS as PLAN_FIELDS
from .godmode_plan import approve as plan_approve
from .godmode_plan import bind_execution, mutation_verdict
from .godmode_plan import SPEC_FIELDS
from .godmode_plan import specify as plan_specify
from .godmode_plan import start as plan_start
from .godmode_scenarios import run as run_scenarios
from .godmode_scope import scope as scope_change
from .godmode_status import ITEM_TYPES, STATES, handover, record_item, remaining, render_view, survey
from .godmode_corpus import build_brief, resolve_roles
from .godmode_detect import bootstrap_charter
from .godmode_profile import PROFILE_NAMES, apply_profile
from .godmode_egress import notice as egress_notice
from .godmode_egress import scan_project as scan_untrusted
from .godmode_egress import scan_staged
from .godmode_scope import minimality
# B3-3 - minimal isolated block (one import line, one subcommand, one
# handler): the silent/swallowed-error scanner, same pattern as the U-E10
# block above.
from .godmode_swallow import scan_project as scan_swallow
from .godmode_swallow import update_baseline as update_swallow_baseline
from .godmode_errors import ArchiveError, GodmodeError
from .godmode_verdict import record_verdict, verdict_for
# U-V2 disposition register - a minimal, isolated block (imports, two
# handlers, one subparser) since other in-flight work also touches this
# file's argparse tree.
from .godmode_register import (
    DELTAS as REGISTER_DELTAS,
    STATES as REGISTER_STATES,
    conflict_findings,
    register_view,
    set_state,
)
# U-E2 cross-project precedent exchange - same minimal, isolated-block
# convention as the register import directly above: its own imports, its
# own handlers, its own subparser.
from .godmode_register import (
    adopt_precedent,
    export_precedents,
    import_precedents,
)
# B5 fleet governance - same minimal, isolated-block convention as the two
# imports above: its own imports, its own handlers, its own subparser. Like
# the register, it stores nothing of its own; every answer is a fold over
# `decision` records carrying a `fleet:` subject.
from .godmode_fleet import (
    acquire_lease,
    agent_id,
    delegate,
    fleet_view,
    release_lease,
    retract as retract_delegation,
)
# B5-B / B6 - citation drift, restore points, and policy replay. Same
# isolated-block convention; all three report and none of them mutate.
from .godmode_reanchor import (
    reanchor_report,
    remap_commit_citations,
    snapshot_commit_citations,
)
from .godmode_rollback import mark_green, rollback_plan
from .godmode_forecast import forecast as forecast_operation, replay as replay_policy
# Sprint 8 - evidence-derived governance. Proposes; never installs.
from .godmode_governance import governance_report, promote as promote_candidate
# Sprint 9 - the host's own approval recorded beside godmode's decision.
from .godmode_hostapproval import approval_divergence, host_approvals
from .godmode_forge import SkillProposal, forge_skill, validate_skill
from .godmode_lens import (
    build_context_brief,
    capacity_checkpoint_due,
    collect_inventory,
    compare_local_reference,
    detect_context_issues,
    explain_context,
    inventory_diff,
    make_snapshot,
    observe_git,
)
from .godmode_lens import why as context_why
from .godmode_sentinel import (
    CapabilityBroker,
    classify_action,
    degradations as sentinel_degradations,
    find_secret_shapes,
    pin_evaluator,
    pinned_evaluators,
    read_password_stdin,
    stage_from_refusal,
    unpin_evaluator,
    unpin_operation_text,
)
from .godmode_sentinel import LICENSE_CLASSIFICATIONS, license_verdict, record_license_attestation


MAX_SUBJECT = 200


def subject_text(value: str) -> str:
    """Validate a subject at parse time, before anything is composed.

    The archive rejects an over-long subject when the record is written, which is
    after the caller has already assembled everything around it. Failing at the
    argument instead means the correction costs one edit rather than a rewrite.
    """
    trimmed = value.strip()
    if not trimmed:
        raise argparse.ArgumentTypeError("must not be empty")
    if len(trimmed) > MAX_SUBJECT:
        raise argparse.ArgumentTypeError(
            f"must be 1-{MAX_SUBJECT} characters; got {len(trimmed)}. "
            "Put the detail in --value or --evidence, and keep the subject a label."
        )
    return trimmed


def _brief_line(payload: Any) -> str:
    """One glanceable line. JSON stays the contract; this is for a human eye.

    Only scalars are rendered. A nested structure summarised into a line stops
    being glanceable and starts being a truncated dict, which is harder to read
    than the JSON it was meant to spare you.
    """
    if not isinstance(payload, dict):
        return str(payload)[:200]

    def scalar(key: str) -> str | None:
        value = payload.get(key)
        if isinstance(value, bool):
            return f"{key}={'yes' if value else 'no'}"
        if isinstance(value, (int, float)):
            return f"{key}={value}"
        if isinstance(value, str) and value:
            return value[:120] if key in _HEADLINE else f"{key}={value[:60]}"
        if isinstance(value, list):
            return f"{key}={len(value)}"
        return None

    parts = [rendered for key in _HEADLINE if (rendered := scalar(key))][:1]
    parts += [rendered for key in _COUNTS if (rendered := scalar(key))]
    parts += [rendered for key in _NOTES if (rendered := scalar(key))][:1]

    if not parts:
        parts = [
            rendered
            for key in list(payload)[:6]
            if not key.startswith("_") and (rendered := scalar(key))
        ][:4]
    return " | ".join(parts) or "(no scalar fields; use --json)"


def _terse_text(payload: Any) -> str:
    """C-11: action first, then the findings, then the brief line.

    `--brief` leads with the verdict; this profile is for the reader who
    wants to act. Line one is the next action - or the explicit statement
    that there is none, because a missing line reads as "nothing to do"
    without ever saying so. Then one line per finding, capped, with the
    cap stated rather than silent. Nothing is computed here that `--json`
    does not already carry.
    """
    if not isinstance(payload, dict):
        return str(payload)[:200]
    action = next(
        (str(payload[key]) for key in _ACTIONS
         if isinstance(payload.get(key), str) and payload[key].strip()),
        "",
    )
    if not action:
        pending = payload.get("next")
        if isinstance(pending, list) and pending and isinstance(pending[0], str):
            action = pending[0]
    verdict = str(payload.get("verdict") or payload.get("state") or "").strip()
    lines = [f"next: {action.strip()[:200]}" if action
             else f"next: nothing - {verdict or 'no findings reported'}"]
    items = next(
        (payload[key] for key in _FINDING_LISTS
         if isinstance(payload.get(key), list) and payload[key]),
        [],
    )
    for item in items[:_TERSE_CAP]:
        if isinstance(item, dict):
            where = str(item.get("path") or item.get("file") or item.get("code") or "")
            line = item.get("line")
            text = str(item.get("message") or item.get("detail") or item.get("why")
                       or item.get("reason") or item.get("summary") or "")
            head = f"{where}:{line}" if where and line else where
            lines.append(f"{head} {text}".strip()[:200])
        else:
            lines.append(str(item)[:200])
    if len(items) > _TERSE_CAP:
        lines.append(f"... {len(items) - _TERSE_CAP} more")
    lines.append(_brief_line(payload))
    return "\n".join(lines)


_ACTIONS = ("next_action", "action", "remedy", "recommendation")
_FINDING_LISTS = ("findings", "regressions", "issues", "missing", "advisories")
_TERSE_CAP = 10

# Fields worth leading with, counting, and closing on.
_HEADLINE = ("verdict", "state", "grade", "class", "message", "error", "check")
_COUNTS = ("passed", "count", "rules", "changed", "records", "adopted", "enforced", "total",
           "drifted", "dependency_count", "symbols", "files", "written",
           "branch", "dirty", "session")
_NOTES = ("reason", "next_action", "detail", "why")


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
    # B4-8 extension (field feedback 3): a not-initialized answer that does
    # not say WHICH project it is answering about reads as global state -
    # in the field it produced a confident wrong verdict. Scope is named.
    project = runtime.anchor.project_root
    orphaned = runtime.archive.orphaned()
    if orphaned:
        raise ArchiveError(
            f"Godmode is not initialized at {project}'s current identity, but "
            f"{orphaned['records']} records exist under its previous one "
            f"({orphaned['reason']}). Run `adopt --confirm` to relink them, or `init` "
            f"to start a separate archive and leave them unreachable."
        )
    raise ArchiveError(
        f"Godmode is not initialized for {project}; run `init` first")


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


# One purpose line per role, so a scaffolded stub explains itself rather than
# arriving as a blank file with a cryptic name.
_ROLE_PURPOSE = {
    "checklist": "Standing verification rows this project re-runs before it ships.",
    "decisions": "Rulings with their reasons, so a later session inherits WHY.",
    "invariants": "Behaviours that must stay true, each owning a guard.",
    "inventory": "What exists and where, so nothing is rebuilt blind.",
    "lessons": "What failed and the rule that prevents its recurrence.",
    "operating-guide": "How to run, test, and release this project.",
    "operator-profile": "Who operates this project and what they authorize.",
    "sprint-truth": "What is actually in flight now, superseding stale plans.",
    "state": "Current reality snapshot: versions, environments, live issues.",
    "code-of-law": "The generated Code of Law: guarded lessons compiled into "
                   "standing law with provenance (`godmode law compile`).",
}
_GLOB_CHARS = re.compile(r"[*?\[]")


def _scaffold_roles(project: Path, archive: Any = None) -> dict[str, Any]:
    """Write one stub per genuinely unbound role; never touch an existing file.

    'Genuinely unbound' matches assess's own corrected reading: a role with
    at least one matched candidate is satisfied, even if its OTHER
    candidates don't exist - scaffolding those too would create redundant
    files nobody asked for. Takes the first candidate pattern per missing
    role, in the order resolve_roles reports it (which mirrors the
    project's declared or default pattern list). A glob-shaped pattern
    (contains */?/[) names a search, not a file to create, and is skipped.
    """
    resolution = resolve_roles(project)
    bound = {b.role for b in resolution.bindings}
    first_pattern: dict[str, str] = {}
    for role, pattern in resolution.missing:
        if role in bound or role in first_pattern:
            continue
        first_pattern[role] = pattern

    written: list[str] = []
    skipped: list[dict[str, str]] = []
    for role in sorted(first_pattern):
        pattern = first_pattern[role]
        if role == "code-of-law":
            # Generated, never stubbed: `law compile` owns this file. On an
            # empty archive it writes the honest empty form (header, zero
            # laws) - which binds the role on day one and states itself.
            if archive is not None:
                from .godmode_law import LAW_FILENAME, compile_laws

                compile_laws(archive, project)
                written.append(LAW_FILENAME)
            else:
                skipped.append({"role": role, "pattern": pattern,
                                "reason": "generated by `godmode law compile`"})
            continue
        if _GLOB_CHARS.search(pattern):
            skipped.append({"role": role, "pattern": pattern, "reason": "glob pattern, not a path"})
            continue
        target = project / pattern
        if target.exists():
            # Resolved as missing but something is there (a directory, or a
            # dangling symlink _expand didn't count as a match) - never
            # overwrite what we did not create.
            skipped.append({"role": role, "pattern": pattern, "reason": "path already exists"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        purpose = _ROLE_PURPOSE.get(role, "Authority document for this role.")
        target.write_text(f"# {role.replace('-', ' ').title()}\n\n{purpose}\n", encoding="utf-8")
        written.append(pattern)
    return {"written": written, "skipped": skipped}


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
    if args.roles:
        payload["roles_scaffolded"] = _scaffold_roles(
            Path(runtime.anchor.project_root), archive=runtime.archive)
    if getattr(args, "detect", False):
        payload["detect"] = bootstrap_charter(Path(runtime.anchor.project_root))
    # U-E8 - minimal isolated block: absent, this is exactly the payload
    # `init` produced before profiles existed (regression pin, see
    # tests/test_profiles.py). Only an explicit `--profile` (including the
    # no-op `standard`) reaches `apply_profile`.
    if getattr(args, "profile", None):
        payload["profile"] = apply_profile(Path(runtime.anchor.project_root), args.profile)
    if not orphaned:
        # The orphaned case already carries next_action with a stronger claim
        # on attention; an ordinary init adds its own, less urgent list.
        payload["next"] = [
            "godmode inspect - see what godmode recorded about this project",
            "godmode resume - start working with continuity",
            "godmode guide - one-page orientation (password, tiers, day-one commands)",
        ]
    return CommandResult(payload)


def cmd_adopt(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "from_docs", False):
        # Obligation 4097: a late install into a mature repo starts with an
        # empty archive while the project's own documents hold months of
        # truth. Seed counts-only adoption records citing each bound
        # authority document, so the brief and the required-sources counter
        # start populated on day one.
        from .godmode_sources import adopt_from_docs

        runtime.archive.initialize()
        return CommandResult(
            adopt_from_docs(runtime.archive, Path(runtime.anchor.project_root)))
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
    if getattr(args, "measure", False):
        # B4-2: what this brief costs, per section, counts only - the bodies
        # the brief would carry are exactly what a measurement must not.
        sections = {}
        for key, value in brief.items():
            rendered = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
            sections[key] = {"bytes": rendered,
                             "tokens_est": max(1, rendered // 4)}
        total = sum(entry["bytes"] for entry in sections.values())
        return CommandResult({
            "project": brief["project"],
            "measure": {
                "sections": sections,
                "total": {"bytes": total, "tokens_est": max(1, total // 4)},
                "estimator": "bytes/4",
            },
        })
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


# filename -> {json path: (type, required)}. Flat by design: a config too deep
# to validate by hand is a config too deep to hand-edit.
_CONFIG_CONTRACTS: dict[str, dict[str, tuple[type, bool]]] = {
    ".godmode-roles.json": {},          # validated by resolve_roles itself
    ".godmode-rca.json": {"spines": (list, False)},
    ".godmode-docs.json": {"triggers": (dict, False)},
    ".godmode-ceilings.json": {"tokens": (int, False), "tool_calls": (int, False),
                               "seconds": (int, False)},
    ".godmode-dependency-policy.json": {"max_dependencies": (int, False),
                                        "banned_licenses": (list, False)},
    ".godmode-privacy.json": {"sensitive_paths": (list, False), "never_leave": (list, False),
                              "baseline_exclude": (list, False)},
    # Task 10b's maturity/stop_contract/budget_s/verdict_path/escalation fields
    # on this same file are validated by `loop_ready` (legal maturity, positive
    # budget, sane thresholds) rather than here - this table's (type, required)
    # shape has no way to spell "int or float", which budget_s legitimately is.
    ".godmode-loop.json": {"repeat_threshold": (int, False)},
    ".godmode-operator.json": {"persona": (str, True), "hard_gates": (list, True),
                               "communication": (str, True), "decision_authority": (str, True)},
    ".godmode-experiment.json": {"hypothesis": (str, True), "command": (str, True),
                                 "success_exit": (int, False), "max_runs": (int, True)},
    # The design boundary. `ui` is required because a boundaries file with no
    # `ui` block declares nothing while looking configured, which is the
    # failure mode this whole surface is built to avoid.
    ".godmode-boundaries.json": {"ui": (dict, True)},
}


def cmd_config_check(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Every `.godmode-*.json` in the tree validates, not every one remembered.

    The contracts below are a schema table, and iterating it meant the command
    checked the files somebody had written a schema for rather than the files
    the project actually ships. `.godmode-docslint.json` governs the docs
    linter here and was absent from the table, so replacing it with unparseable
    text left this command green - the config still named, still loaded by
    whatever reads it, and silently governing nothing.

    Discovery is by glob now, and a file with no contract is still required to
    parse and to be an object. A schema nobody wrote is a weaker check than the
    one below it; no check at all is not a check.
    """
    project = Path(runtime.anchor.project_root)
    checked: list[dict[str, Any]] = []
    problems: list[str] = []
    discovered = {path.name for path in project.glob(".godmode-*.json")}
    for filename in sorted(discovered | set(_CONFIG_CONTRACTS)):
        contract = _CONFIG_CONTRACTS.get(filename, {})
        path = project / filename
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{filename}: invalid JSON at line {exc.lineno}: {exc.msg}")
            checked.append({"file": filename, "state": "unparseable"})
            continue
        if not isinstance(payload, dict):
            problems.append(f"{filename}: $ must be an object")
            checked.append({"file": filename, "state": "invalid"})
            continue
        file_problems = []
        for key, (expected, required) in contract.items():
            if key not in payload:
                if required:
                    file_problems.append(f"{filename}: $.{key} is required ({expected.__name__})")
                continue
            if not isinstance(payload[key], expected):
                file_problems.append(f"{filename}: $.{key} must be {expected.__name__}")
        problems.extend(file_problems)
        checked.append({"file": filename, "state": "invalid" if file_problems else "valid"})
    return CommandResult(
        {"project": str(project), "checked": checked, "problems": problems,
         "known_files": sorted(_CONFIG_CONTRACTS),
         "verdict": "valid" if not problems else "invalid"},
        exit_code=0 if not problems else 1,
    )


OPERATOR_FILENAME = ".godmode-operator.json"
_OPERATOR_FIELDS = {
    "persona": str, "hard_gates": list, "communication": str, "decision_authority": str,
}


def cmd_operator(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """S21-06: typed operator profile, portable, with no personal name anywhere."""
    path = Path(runtime.anchor.project_root) / OPERATOR_FILENAME
    if not path.is_file():
        return CommandResult(
            {"present": False,
             "expected": {k: t.__name__ for k, t in _OPERATOR_FIELDS.items()},
             "note": f"declare {OPERATOR_FILENAME} with the typed fields; no name field exists on purpose"},
            exit_code=1,
        )
    profile = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for field, expected in _OPERATOR_FIELDS.items():
        if field not in profile:
            problems.append(f"missing field: {field}")
        elif not isinstance(profile[field], expected):
            problems.append(f"{field} must be {expected.__name__}")
    for banned in ("name", "full_name", "email"):
        if banned in profile:
            problems.append(f"'{banned}' is not a profile field; identity stays out of records")
    serialized = json.dumps(profile, ensure_ascii=False).lower()
    for source in ("USERNAME", "USER"):
        value = os.environ.get(source, "")
        if len(value) >= 3 and value.lower() in serialized:
            problems.append(f"profile text contains the OS account name; remove it")
            break
    return CommandResult(
        {"present": True, "profile_fields": sorted(k for k in profile),
         "problems": problems, "verdict": "valid" if not problems else "invalid"},
        exit_code=0 if not problems else 1,
    )


def cmd_charter(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.bootstrap:
        return CommandResult(bootstrap_rules(Path(runtime.anchor.project_root)))
    if args.review_advisory:
        _require_archive(runtime)
        if not args.reason or not args.reason.strip():
            raise ArchiveError("--review-advisory needs --reason: why can no mechanical "
                              "check decide this rule?")
        charter = _charter(runtime)
        ids = {r["id"] for r in charter["compiled"] if r["enforcement"] == ADVISORY}
        if args.review_advisory not in ids:
            raise ArchiveError(f"'{args.review_advisory}' is not a currently-compiled "
                              f"ADVISORY rule id; run `charter --full` to list them")
        record = runtime.archive.append(
            "decision", f"charter-advisory-reviewed:{args.review_advisory}",
            {"reason": args.reason.strip()[:400]}, evidence=[])
        return CommandResult({"reviewed": args.review_advisory,
                              "reason": record["data"]["reason"],
                              "sequence": record["sequence"]})
    charter = _charter(runtime)
    if not charter.get("compiled"):
        # Zero rules means every gate passes vacuously - say so instead of
        # letting an empty charter read as a green one.
        charter["detail"] = ("0 rules compiled: gates cannot block anything. Write "
                             "directives into GODMODE.md (or the operating-guide role "
                             "document), or mine candidates with `charter --bootstrap`")
    if args.decay:
        _require_archive(runtime)
        return CommandResult(advisory_decay(runtime.archive, charter, window=args.decay))
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
    handshake = opening_handshake(
        runtime.archive, runtime.anchor, Path(runtime.anchor.project_root)
    )
    # Promoted so --brief shows the handshake's load-bearing facts, not only
    # the session id - the opening state is the feature, not decoration.
    return CommandResult({
        "session": session,
        "branch": handshake.get("branch"),
        "dirty": handshake.get("dirty_files", {}).get("count"),
        "detail": handshake.get("required_sources", {}).get("statement"),
        "handshake": handshake,
    })


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
        project=Path(runtime.anchor.project_root),
    )
    return CommandResult({"record": _event_view(record)})


def cmd_verify(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    outcome = run_check(
        runtime.archive, _session(runtime, args.session), Path(runtime.anchor.project_root),
        args.name, shlex.split(args.command), rule_ids=args.rule,
    )
    # The runner decides, not the caller: a failing check exits non-zero here too.
    # `citation` is returned so a later claim quotes what was stored rather than
    # reconstructing it and guessing the normalisation.
    return CommandResult(outcome, exit_code=0 if outcome["passed"] else 1)


def cmd_plant(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    outcome = plant_and_observe(
        runtime.archive, _session(runtime, args.session), Path(runtime.anchor.project_root),
        args.name, shlex.split(args.command), target=args.file,
        replace=args.replace, with_text=args.with_text, append=args.append,
        rule_ids=args.rule,
    )
    # A guard that never went red is not a guard, so this exits non-zero.
    return CommandResult(outcome, exit_code=0 if outcome["observed_failing"] else 1)


def cmd_gate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    verdict = gate(
        runtime.archive, _session(runtime, args.session), _charter(runtime), args.trigger,
        timeline=_load_timeline(getattr(args, "transcript", None)),
    )
    return CommandResult(verdict.view(), exit_code=0 if verdict.allowed else 1)


def _load_timeline(transcript_path: str | None) -> dict[str, Any] | None:
    """U-T2: best-effort `session_timeline`, never raising into the caller.

    A missing or unreadable transcript is treated exactly like no transcript
    at all - `None` - so the temporal/ordering checks it feeds see a stated
    gap, not an error, and skip themselves rather than penalise a claim over
    an instrument that was never available.
    """
    if not transcript_path:
        return None
    from .godmode_session_log import session_timeline

    try:
        return session_timeline(Path(transcript_path))
    except (OSError, ValueError):
        return None


def cmd_claim(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "text_flag", None) and not args.text:
        args.text = args.text_flag
    if getattr(args, "scan", False):
        # Public-surface enforcement: the sentences on README and its
        # siblings that are claims by definition, minus the ones whose line
        # names a reproduction or whose text a claim record carries.
        report = scan_public_surfaces(Path(runtime.anchor.project_root), runtime.archive)
        return CommandResult(report, exit_code=1 if report["uncovered"] else 0)
    if getattr(args, "resolve", None) is not None:
        if not args.outcome:
            return CommandResult(
                {"refused": "--resolve needs --outcome held|failed|superseded"},
                exit_code=1)
        _require_archive(runtime)
        record = resolve_claim(
            runtime.archive, Path(runtime.anchor.project_root),
            _session(runtime, args.session), args.resolve, args.outcome,
            cites=args.cite,
        )
        data = record["data"]
        return CommandResult(
            {"resolves": data["resolves"], "outcome": data["outcome"],
             "confidence": data["confidence"], "score": data["score"],
             "sequence": record["sequence"]},
            exit_code=0,
        )
    if not args.text:
        return CommandResult({"refused": "claim needs the claim text, or --scan"}, exit_code=1)
    _require_archive(runtime)
    record = record_claim(
        runtime.archive,
        Path(runtime.anchor.project_root),
        _session(runtime, args.session),
        args.text,
        args.grade,
        cites=args.cite,
        external=args.external,
        timeline=_load_timeline(getattr(args, "transcript", None)),
        blast_radius=getattr(args, "blast_radius", None),
        confidence=getattr(args, "confidence", None),
    )
    data = record["data"]
    # A downgrade is a finding, so it must be visible in the exit status too.
    return CommandResult(
        {"claim": data["text"], "grade": data["grade"], "claimed": data["claimed_grade"],
         "downgraded": data["downgraded"], "reason": data.get("reason", ""),
         "unresolved": data["unresolved"], "unsupported": data.get("unsupported", []),
         "blast_radius": data.get("blast_radius"),
         "advisories": data.get("advisories", [])},
        exit_code=1 if data["downgraded"] else 0,
    )


def cmd_criterion(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_criterion(
        runtime.archive,
        _session(runtime, args.session),
        args.task,
        args.text,
        cites=args.cite,
        timeline=_load_timeline(getattr(args, "transcript", None)),
    )
    data = record["data"]
    return CommandResult(
        {"task": data["task"], "text": data["text"], "late": data["late"],
         "advisories": data["advisories"]},
        exit_code=1 if data["late"] else 0,
    )


def cmd_metric_contract_register(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = register_metric_contract(
        runtime.archive, _session(runtime, args.session), args.name, args.anchor,
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "name": args.name, "anchor": data["anchor"]},
        exit_code=0,
    )


def cmd_error_pattern_register(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = register_error_pattern(
        runtime.archive, _session(runtime, args.session), args.tool, args.pattern,
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "tool": data["tool"], "pattern": data["pattern"]},
        exit_code=0,
    )


# U-E3 differential-evidence - minimal isolated block, mirrors the `register`
# block below.
def cmd_differential_record(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_differential(
        runtime.archive, args.subject, args.a, args.b, args.delta, args.method,
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "subject": data["subject"],
         "a_ref": data["a_ref"], "b_ref": data["b_ref"], "delta": data["delta"],
         "method": data["method"]},
        exit_code=0,
    )


def cmd_verdict_record(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_verdict(
        runtime.archive,
        Path(runtime.anchor.project_root),
        args.claim,
        args.value,
        args.witness,
        args.checker,
        run_state=args.run_state,
        acquitted_by=args.acquitted_by,
        timeout=args.timeout,
        tool_error_ack=getattr(args, "tool_error_ack", "") or "",
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "claim": data["claim"],
         "disposition": data["disposition"], "run_state": data["run_state"],
         "acquitted_by": data["acquitted_by"],
         "tool_error_findings": data.get("tool_error_findings", [])},
        exit_code=0 if data["disposition"] == "confirmed" else 1,
    )


def cmd_verdict_show(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = verdict_for(runtime.archive, args.seq)
    if record is None:
        raise ArchiveError(f"No verdict record at seq:{args.seq}")
    return CommandResult(record, exit_code=0)


# U-V2 disposition register - `set` and `supersede` share this handler; the
# only difference is `supersede`'s `--supersedes` is required by argparse,
# since set_state() itself decides whether a value is actually needed.
def cmd_register_set(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = set_state(
        runtime.archive, args.domain, args.key, args.state, args.evidence,
        supersedes=args.supersedes, delta=args.delta,
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "domain": data["register_domain"],
         "key": data["register_key"], "state": data["state"],
         "supersedes": data["supersedes"], "delta": data["delta"]},
        exit_code=0,
    )


def cmd_register_show(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    view = register_view(runtime.archive, args.domain)
    # Computed once, filtered per branch below: a --key query is a conflict
    # blind spot otherwise - fix-round-1 review caught that asking about one
    # key by name returned a clean `state: open` even when the domain-wide
    # check simultaneously flagged that same key as a blocking conflict.
    findings = conflict_findings(runtime.archive, args.domain)
    if args.key:
        entry = view.get(
            args.key,
            {"state": "open", "sequence": None, "evidence": [], "lineage": [], "delta": None},
        )
        key_findings = [f for f in findings if f["key"] == args.key]
        return CommandResult(
            {"domain": args.domain, "key": args.key, **entry, "conflicts": key_findings},
            exit_code=1 if key_findings else 0,
        )
    # A conflict is a HARD halt (E6), so it must be visible in the exit status.
    return CommandResult(
        {"domain": args.domain, "register": view, "conflicts": findings},
        exit_code=1 if findings else 0,
    )


# B5 fleet governance - four handlers over one derived view. A lease
# conflict and a delegation cycle both exit non-zero: an agent scripting
# against this needs the refusal in the exit status, not only in the text.
def cmd_fleet_show(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    view = fleet_view(runtime.archive)
    return CommandResult({"agent": agent_id(), **view}, exit_code=0)


def cmd_fleet_lease(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        record = acquire_lease(
            runtime.archive, args.resource,
            ttl_seconds=args.ttl, holder=args.holder,
        )
    except ArchiveError as error:
        # Refused, not crashed: the conflicting holder is the answer the
        # caller asked for, so it is reported as a result with a failing
        # exit code rather than as a traceback.
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(
        {"resource": args.resource, "holder": record["data"]["holder"],
         "expires_at": record["data"]["expires_at"],
         "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_fleet_release(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        record = release_lease(runtime.archive, args.resource, holder=args.holder)
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(
        {"resource": args.resource, "released_by": record["data"]["holder"],
         "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_fleet_delegate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        record = delegate(
            runtime.archive, child=args.child, task=args.task, parent=args.parent)
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(
        {"parent": record["data"]["parent"], "child": args.child,
         "task": args.task, "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_governance_show(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    # Exit 0 even with candidates present: a proposal is not a failure, and
    # a review surface that fails the build is a review surface people
    # learn to switch off.
    return CommandResult(governance_report(runtime.archive), exit_code=0)


def cmd_governance_promote(args: argparse.Namespace,
                           runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        record = promote_candidate(
            runtime.archive, args.candidate, reason=args.reason)
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(
        {"promoted": args.candidate, "rule": record["data"]["rule"],
         "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_fleet_retract(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        record = retract_delegation(
            runtime.archive, child=args.child, parent=args.parent)
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(
        {"retracted": args.child, "parent": record["data"]["parent"],
         "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_host_approvals(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = approval_divergence(runtime.archive)
    if args.all:
        report["records"] = host_approvals(runtime.archive)
    # Exit 0 on divergence: two boundaries disagreeing is information, not
    # a fault. Neither answers to the other, so neither can be "wrong" here.
    return CommandResult(report, exit_code=0)


def cmd_reanchor(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    # Ordering is the contract: snapshot BEFORE a rewrite, remap after. A
    # snapshot taken afterwards records the new sha and proves nothing
    # about the old one, so the two are separate deliberate acts rather
    # than one command that guesses which the caller meant.
    if getattr(args, "snapshot", False):
        return CommandResult(
            snapshot_commit_citations(runtime.archive, project), exit_code=0)
    if getattr(args, "remap", False):
        report = remap_commit_citations(runtime.archive, project)
        # An unresolved citation is a real loss - no snapshot existed, so
        # nothing records what the sha meant. That belongs in the status.
        return CommandResult(
            report, exit_code=1 if report["unresolved"] else 0)
    report = reanchor_report(runtime.archive, project)
    # Findings are a prompt to re-read evidence, not a failure: exiting
    # non-zero here would make an honest report look like a broken build
    # and invite someone to silence it.
    return CommandResult(report, exit_code=0)


def cmd_rollback_mark(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        record = mark_green(
            runtime.archive, Path(runtime.anchor.project_root),
            command=args.command, exit_code=args.exit_code,
        )
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(
        {"commit": record["data"]["commit"], "command": record["data"]["command"],
         "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_rollback_plan(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    plan = rollback_plan(runtime.archive, Path(runtime.anchor.project_root))
    return CommandResult(plan, exit_code=0)


def cmd_quality(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # C-05. Aggregation only; every remedy is a proposal and nothing here
    # writes. A `high` finding is a defect the reader must answer for, so
    # it - and only it - reaches the exit status; the rest are questions.
    report = quality_report(Path(runtime.anchor.project_root), runtime.archive)
    exit_code = 1 if report["counts"]["high"] else 0
    # C-63: the same findings in a shape an editor consumes. The exit
    # status is the same in every format - a format is a view, not a
    # verdict.
    fmt = getattr(args, "format", "json")
    if fmt == "editor":
        return CommandResult(render_editor(report), exit_code=exit_code)
    if fmt == "sarif":
        return CommandResult(render_sarif(report, RUNTIME_VERSION), exit_code=exit_code)
    return CommandResult(report, exit_code=exit_code)


def cmd_examples(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # C-24. The corpus lives with the plugin, not the project: an example
    # is a claim about what godmode returns, so it is checked against a
    # throwaway project rather than whichever one the reader is standing in.
    corpus = Path(args.corpus) if args.corpus else _PLUGIN_ROOT / "examples"
    if not args.check:
        examples = load_examples(corpus)
        return CommandResult({
            "corpus": str(corpus),
            "examples": [{"name": e["name"], "command": e["command"],
                          "about": e.get("about", "")} for e in examples],
            "count": len(examples),
        })
    report = check_examples(corpus, main)
    report["corpus"] = str(corpus)
    return CommandResult(report, exit_code=1 if report["verdict"] == "stale" else 0)


def cmd_freshness(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # C-10. Stale or unreachable is a finding; partial is a statement of
    # what was not checked, and never fails on its own.
    report = freshness_report(runtime.archive, Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=1 if report["verdict"] == "stale" else 0)


def cmd_watchdog(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # C-55. On demand, between steps; no daemon. `--interrupt` writes the
    # operator-stop flag the stop algebra already honours, only on anomaly.
    report = watchdog_report(runtime.archive)
    report["interrupted"] = False
    if args.interrupt and report["verdict"] == "anomaly":
        flag = watchdog_interrupt(
            Path(runtime.anchor.project_root),
            "; ".join(a["kind"] for a in report["anomalies"]))
        report["interrupted"] = True
        report["flag"] = str(flag)
    return CommandResult(report, exit_code=1 if report["verdict"] == "anomaly" else 0)


def cmd_arbitrate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # C-56. Undecided is a finding: the plans need more before one can be
    # held to, and an exit 0 would read as "either is fine".
    plans = [Path(p) for p in args.plan]
    missing = [str(p) for p in plans if not p.is_file()]
    if missing:
        return CommandResult({"refused": f"plan file(s) not found: {', '.join(missing)}"},
                             exit_code=1)
    report = arbitrate_plans(Path(runtime.anchor.project_root), plans)
    return CommandResult(report, exit_code=0 if report["verdict"] == "decided" else 1)


def cmd_extensions_list(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # C-52. Manifests only; nothing is imported by a listing.
    listed = list_extensions()
    return CommandResult({
        "extensions": listed,
        "count": len(listed),
        "policy": POLICY_FILENAME,
        "note": "an extension runs only when named in the project's policy `extensions` list",
    })


def cmd_extensions_run(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    argv = list(args.argv)
    if argv[:1] == ["--"]:
        argv = argv[1:]
    try:
        result = run_extension(Path(runtime.anchor.project_root), args.name, argv)
    except ExtensionRefused as error:
        return CommandResult({"refused": str(error), "extension": args.name}, exit_code=1)
    return CommandResult({"extension": args.name, "argv": argv, "result": result})


def cmd_forecast(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    try:
        result = forecast_operation(
            runtime.archive, args.operation, project_root=Path(runtime.anchor.project_root))
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    return CommandResult(result, exit_code=0)


def cmd_replay(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = replay_policy(runtime.archive, project_root=Path(runtime.anchor.project_root))
    # A relaxation is the one outcome that means a rule went backwards, so
    # it - and only it - reaches the exit status.
    return CommandResult(report, exit_code=1 if report["relaxed"] else 0)


# U-E2 cross-project precedent exchange - file-carried, advisory-foreign.
# `export`/`import` do the file I/O here (console is the only layer that
# touches stdin/stdout/the filesystem path a human names on the command
# line); the module itself only ever takes and returns strings/dicts, so it
# stays testable without a filesystem.
def cmd_precedent_export(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    blob = export_precedents(runtime.archive, args.domain)
    out_path = Path(args.out)
    out_path.write_text(blob, encoding="utf-8")
    return CommandResult(
        {"domain": args.domain, "out": str(out_path), "bytes": len(blob)}, exit_code=0
    )


def cmd_precedent_import(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    blob = Path(args.file).read_text(encoding="utf-8")
    result = import_precedents(runtime.archive, blob)
    return CommandResult(result, exit_code=0)


def cmd_precedent_adopt(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = adopt_precedent(runtime.archive, args.domain, args.key)
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "domain": data["register_domain"],
         "key": data["register_key"], "state": data["state"]},
        exit_code=0,
    )


def cmd_session_close(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    session = _session(runtime, args.session)
    verdict = close_session(runtime.archive, session, _charter(runtime))
    # What the gates actually did this session, so the friction has a
    # counterpart. Silent when nothing fired.
    report = contribution(runtime.archive, Path(runtime.anchor.project_root), session)
    if report["reportable"]:
        verdict["contribution"] = report
        verdict["summary"] = render_contribution(report)
    return CommandResult(verdict, exit_code=0 if verdict["closed"] else 1)


def cmd_method(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.check_record:
        if not args.check_method:
            raise ArchiveError("--check-record needs --check-method naming the method used")
        record = json.loads(Path(args.check_record).read_text(encoding="utf-8"))
        record.setdefault("spines", list(configured_spines(runtime.anchor.project_root)))
        verdict = method_complete(args.check_method, record)
        # An RCA cannot be published with its method incomplete.
        extras: dict[str, Any] = {}
        if args.check_method == "pareto" and record.get("clusters"):
            extras["pareto"] = pareto_order(record["clusters"])
        if args.check_method == "fmea" and record.get("modes"):
            extras["ranked"] = rank_fmea(record["modes"])
        if args.check_method == "fault-tree" and isinstance(record.get("tree"), dict):
            extras["cut_sets"] = fault_tree_cut_sets(record["tree"])
        return CommandResult({**verdict, **extras}, exit_code=0 if verdict["complete"] else 1)
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


def cmd_status_absorb_docs(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_status import absorb_docs
    target = Path(runtime.anchor.project_root) / args.path
    if not target.is_file():
        return CommandResult({"refused": f"not a file: {args.path}"}, exit_code=1)
    report = absorb_docs(runtime.archive, target, write=args.write)
    return CommandResult(report)


def cmd_status_set(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_item(
        runtime.archive, args.item, args.title, args.state,
        evidence=args.evidence, proof=args.proof,
        item_type=args.type, points=args.points, acceptance=args.acceptance,
        blocked_on=args.blocked_on, root_cause=args.root_cause,
        depends_on=args.depends_on or None, branch=args.branch, severity=args.severity,
    )
    return CommandResult({"record": _event_view(record)})


def cmd_remaining(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    session = args.session or latest_session(runtime.archive)
    report = remaining(runtime.archive, Path(runtime.anchor.project_root),
                       session=session, charter=_charter(runtime))
    return CommandResult(report, exit_code=1 if report["count"] else 0)


def cmd_status_survey(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = survey(runtime.archive, Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=1 if report["verdict"] == "competing-authority" else 0)


def cmd_planmode_specify(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    fields = {field: getattr(args, field) or "" for field in SPEC_FIELDS}
    return CommandResult(
        plan_specify(runtime.archive, _session(runtime, args.session), args.title, fields)
    )


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


def cmd_changelog_check(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = check_fragments(Path(runtime.anchor.project_root), base=args.base)
    return CommandResult(report, exit_code=0 if report["satisfied"] else 1)


def cmd_changelog_merge(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from datetime import date

    return CommandResult(merge_fragments(
        Path(runtime.anchor.project_root), version=args.set_version,
        date=args.date or date.today().isoformat(),
    ))


def cmd_law_compile(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_law import compile_laws

    return CommandResult(compile_laws(
        runtime.archive, Path(runtime.anchor.project_root)))


def cmd_law_show(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_law import debrief_status, top_laws

    return CommandResult({"laws": top_laws(runtime.archive, args.top),
                          "debrief": debrief_status(runtime.archive)})


def cmd_law_amend(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_law import amend_law

    return CommandResult({"amended": amend_law(
        runtime.archive, args.law, args.guard)["sequence"],
        "note": "newest record per subject is the law; run `law compile` to "
                "regenerate the file"})


def cmd_law_candidates(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_law import law_candidates

    return CommandResult({"candidates": law_candidates(runtime.archive)})


def cmd_law_hygiene(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_law import hygiene

    _require_archive(runtime)
    return CommandResult(hygiene(runtime.archive))


def cmd_law_debrief(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_law import debrief

    return CommandResult(debrief(runtime.archive))


def cmd_law_promote(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_law import promote_candidate

    return CommandResult(promote_candidate(
        runtime.archive, args.candidate, guard=args.guard, subject=args.subject))


def cmd_benchmark(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """S7-04/05/06: measure the budgets locally; transmit nothing."""
    import time as _time

    from .godmode_corpus import build_brief as corpus_brief
    from .godmode_lens import build_context_brief

    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    budgets = {"cold_start": 2500, "resume": 1200, "rca": 3500}
    results: dict[str, Any] = {}

    started = _time.perf_counter()
    cold = corpus_brief(project, "resume work on the current objective", budgets["cold_start"])
    results["cold_start"] = {
        "elapsed_ms": round((_time.perf_counter() - started) * 1000, 1),
        "estimated_tokens": cold["budget"]["used"],
        "budget": budgets["cold_start"],
        "within_budget": cold["budget"]["used"] <= budgets["cold_start"],
    }

    started = _time.perf_counter()
    warm = build_context_brief(runtime.anchor, runtime.archive, token_budget=budgets["resume"])
    results["resume"] = {
        "elapsed_ms": round((_time.perf_counter() - started) * 1000, 1),
        "estimated_tokens": warm["estimated_tokens"],
        "budget": budgets["resume"],
        "within_budget": warm["estimated_tokens"] <= budgets["resume"],
    }

    over = [name for name, entry in results.items() if not entry["within_budget"]]
    results["rca"] = {"budget": budgets["rca"],
                      "note": "measured only when an RCA brief is assembled; no synthetic RCA is faked here"}
    results["transmitted"] = "nothing; metrics are computed and printed locally"
    results["verdict"] = "within-budgets" if not over else f"over-budget: {', '.join(over)}"
    return CommandResult(results, exit_code=0 if not over else 1)


def cmd_ceilings(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    spent: dict[str, int] = {}
    for pair in (args.spent or "").split(","):
        if "=" in pair:
            name, value = pair.split("=", 1)
            spent[name.strip()] = int(value)
    verdict = check_ceilings(Path(runtime.anchor.project_root), spent)
    return CommandResult(verdict, exit_code=1 if verdict["exceeded"] else 0)


def cmd_watch(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    verdict = watchdog(runtime.archive, _session(runtime, args.session))
    return CommandResult(verdict, exit_code=1 if verdict["anomaly"] else 0)


def cmd_rewind(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(rewind_preview(runtime.archive, args.to))


def cmd_planmode_arbitrate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(arbitrate(runtime.archive))


def cmd_loop(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    if args.blame:
        verdict = model_blame_allowed(
            runtime.archive.read_events(),
            session=_session(runtime, args.session) if args.session else None,
        )
        return CommandResult(verdict, exit_code=0 if verdict["allowed"] else 1)
    if args.preflight:
        # Task 10b: audit BEFORE cycle one, not after it stalls. `declare_maturity`
        # (inside loop_ready) raises on an illegal maturity - that propagates as
        # the usual GodmodeError refusal, naming the policy, not a finding here.
        declaration_path = Path(runtime.anchor.project_root) / LOOP_CONFIG_FILENAME
        declaration: dict[str, Any] = {}
        if declaration_path.is_file():
            declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
        verdict = loop_ready(declaration)
        return CommandResult(verdict, exit_code=1 if verdict["blocking"] else 0)
    report = analyze_loops(runtime.archive)
    return CommandResult(report, exit_code=1 if report["blocking"] else 0)


def cmd_mistakes(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    if args.process_started:
        verdict = stale_runtime(Path(runtime.anchor.project_root), args.process_started)
        return CommandResult(verdict, exit_code=1 if verdict["stale"] else 0)
    report = analyze_mistakes(runtime.archive)
    return CommandResult(report, exit_code=1 if report["blocking"] else 0)


def cmd_removal_record(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    record = record_removal(
        runtime.archive, args.subject,
        {field: getattr(args, field) for field in REMOVAL_FIELDS},
        evidence=args.evidence,
    )
    return CommandResult({"record": _event_view(record)})


def cmd_removal_why(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    answer = removal_answer(runtime.archive, args.subject)
    if answer is None:
        return CommandResult(
            {"subject": args.subject, "answer": None,
             "note": "no removal record; if this was removed, the memory was never written"},
            exit_code=1,
        )
    return CommandResult({"subject": args.subject, "answer": answer})


def cmd_locale_check(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = check_locales(Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=0 if report["valid"] else 1)


def cmd_integrity(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = analyze_integrity(runtime.archive, Path(runtime.anchor.project_root), base=args.base)
    # E-05: a change that weakens the suite cannot be attested into completion.
    return CommandResult(report, exit_code=1 if report["blocking"] else 0)


def _git_tags(project: Path) -> str:
    return _git_tags_raw(project, "tag", "--list")


def cmd_release(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Which tags have no release, computed rather than remembered.

    The published list is supplied by the caller, never fetched: this runtime
    does not reach the network, and the half that decides is the comparison.
    Absent input reports insufficient data rather than an empty answer, because
    "nothing is published" and "nobody could tell" are different facts.
    """
    project = Path(runtime.anchor.project_root)
    tags = [tag for tag in (_git_tags(project) or "").split() if tag]
    published = list(args.published) if args.published else None
    if args.published_from:
        source = Path(args.published_from)
        try:
            published = [line.strip() for line in
                         source.read_text(encoding="utf-8").split() if line.strip()]
        except OSError:
            published = None
    report = compare_releases(tags, published)
    report["summary"] = render_release(report)
    # Reported, not failed: an unpublished tag is a state to see, and a release
    # is a human act this never performs.
    return CommandResult(report, exit_code=0)


def cmd_minimality(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # No archive means no census/decay sections; the report says so rather
    # than failing, the same policy every other archive-optional report uses.
    archive = runtime.archive if runtime.archive.initialized() else None
    project = Path(runtime.anchor.project_root)
    if getattr(args, "accept_growth", None):
        _require_archive(runtime)
        record = accept_growth(
            runtime.archive, args.accept_growth, reason=args.reason or "")
        return CommandResult(
            {"accepted": args.accept_growth,
             "reason": record["data"]["reason"],
             "sequence": record["sequence"]},
            exit_code=0,
        )
    report = minimality_report(project, archive=archive)
    counts = {section["section"]: section["count"] for section in report["sections"]}
    if getattr(args, "set_baseline", False):
        return CommandResult(
            {"baseline": write_pressure_baseline(project, counts),
             "note": "later growth past these counts is reported until accepted"},
            exit_code=0,
        )
    # C-04: the counts alone were a number nobody compared against anything.
    report["pressure"] = pressure_report(project, counts, archive=archive)
    # Non-zero only on UNACCEPTED growth: accepted growth is a decision the
    # record already carries, and failing on it would punish saying why.
    return CommandResult(
        report,
        exit_code=1 if report["pressure"]["verdict"] == "pressure-grew" else 0,
    )


def cmd_capabilities(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "reconcile", False):
        # U-S2/13b/13c: the capability register, the detector catalog, and
        # the capability-coverage matrix, all held to the same
        # both-directions discipline in one report.
        project = Path(runtime.anchor.project_root)
        caps = reconcile_capabilities(project)
        detectors = reconcile_detectors(project)
        coverage = reconcile_capability_coverage(project)
        report = {"capabilities": caps, "detectors": detectors, "coverage": coverage}
        ok = (caps["verdict"] == "reconciled" and detectors["verdict"] == "reconciled"
              and coverage["verdict"] == "reconciled")
        return CommandResult(report, exit_code=0 if ok else 1)
    if getattr(args, "usage", False):
        # The product's own standard, applied to its own description of
        # itself: which declared surfaces the record shows were used.
        _require_archive(runtime)
        report = census(runtime.archive)
        report["summary"] = render_census(report)
        # A correction the runtime made and nobody wrote down is the surface
        # least likely to be noticed, because the claim was already refused.
        report["corrections"] = uncaptured_corrections(runtime.archive)
        return CommandResult(report, exit_code=0)
    if args.host:
        source = Path(runtime.anchor.project_root) / "packaging" / "hosts.json"
        adapters = json.loads(source.read_text(encoding="utf-8")).get("adapters", {})
        declared = adapters.get(args.host)
        if declared is None:
            known = sorted(k for k in adapters if not k.startswith("_"))
            raise ArchiveError(
                f"No declared adapter for host '{args.host}'; known: {', '.join(known)}"
            )
        payload = {
            "host": args.host,
            "controls": declared["controls"],
            "why": declared.get("why", {}),
            "wiring": declared.get("wiring"),
            "unavailable": sorted(
                k for k, v in declared["controls"].items() if v == "UNAVAILABLE"),
        }
        if args.record:
            # The negotiation is a fact worth keeping: which table this session
            # believed, on which host, decided by declaration rather than memory.
            _require_archive(runtime)
            record = runtime.archive.append(
                "decision", f"capability-negotiation:{args.host}",
                {"controls": declared["controls"], "status": "negotiated"},
                evidence=[f"file:packaging/hosts.json"],
            )
            payload["recorded"] = record["sequence"]
        return CommandResult(payload)
    return CommandResult({
        "project": str(runtime.anchor.project_root),
        **host_capabilities(
            tool_call_interception=interception_state(runtime.archive, current_host())),
    })


def _hooks_health_fields(archive: Any, host: str, level: str) -> dict[str, Any]:
    """CX-5: `hooks status`'s `matched`/`invoked`/`honored`/`version`/
    `degraded_reason`/`latency`/`fail_open_host` fields.

    `matched` - does the SHIPPED manifest declare a matcher/event that would
    reach this host's boundary at all (structural, never live). `invoked` -
    has this host's boundary EVER actually been reached (a proof, of any
    age, exists). `honored` - did the host actually act on the decision the
    hook rendered, per the last proof's own `observed_decision` (every
    probe this codebase writes denies, so `honored` is really "did the host
    demonstrably see and record that denial" - `"unknown"` when no proof
    exists at all to answer from, never a guessed `True`). `version` - the
    godmode version string the last proof was minted under. Every field is
    the honest string `"unknown"`, never `None`, where the underlying fact
    is not inspectable - matching the plan's own wording for this contract
    point.
    """
    manifest = hook_manifest_status()
    proof = last_proof(archive, host)
    if host == "claude":
        matched: Any = manifest["pretool_hook_seen"]
    else:
        entry = hooks_registration_report().get(host)
        matched = bool(entry.get("manifest_present")) if isinstance(entry, dict) else "unknown"
    invoked = proof is not None
    if proof is None:
        honored: Any = "unknown"
        version: Any = "unknown"
    else:
        honored = proof["data"].get("observed_decision") == "deny"
        version = proof["data"].get("hook_version") or "unknown"
    latency = last_latency_check(archive, host)
    return {
        "matched": matched,
        "invoked": invoked,
        "honored": honored,
        "version": version,
        "degraded_reason": degraded_reason(archive, host) if level == "DEGRADED" else None,
        "latency": latency,
        "fail_open_host": host in FAIL_OPEN_HOSTS,
    }



def cmd_hooks_statusline(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """A statusline segment: the one ambient signal that carries information.

    Persona modes decorate every prompt because visibility IS their
    function; godmode stays silent when things are fine - except that a
    disarmed hook cannot report its own absence (silence-audit A3), so the
    operator gets one compact, cheap line to wire into their statusline:
    presence plus the enforcement grade. Plain text on stdout, no JSON,
    because statusline consumers concatenate strings.
    """
    grade = "UNAVAILABLE"
    try:
        if runtime.archive.initialized():
            from .godmode_hookproof import interception_state
            grade = interception_state(runtime.archive, current_host())
    except Exception:  # noqa: BLE001
        grade = "UNAVAILABLE"
    marker = {"HARD": "✓", "DEGRADED": "~", "PARTIAL": "~",
              "SOFT": "?", "UNAVAILABLE": "!"}.get(grade, "?")
    # A string payload prints as-is at the dispatcher - plain text, no
    # JSON, because statusline consumers concatenate strings.
    return CommandResult(f"[GM {marker} {grade}]")


def cmd_hooks(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """CX-1: `status` reads the chronicled proof back; `probe` produces a fresh one.

    Host-neutral by construction - `--host` scopes which host's proof is
    read or written, defaulting to the same detection `host_capabilities`
    itself uses (`GODMODE_HOST`/`CLAUDE_CODE_ENTRYPOINT`), so a bare `godmode
    hooks probe` followed by a bare `godmode hooks status` agree without the
    caller naming a host twice.
    """
    host = getattr(args, "host", None) or current_host()
    if args.hooks_command == "status":
        if getattr(args, "git", False):
            _require_archive(runtime)
            return CommandResult(
                git_hooks_status(runtime.archive, Path(runtime.anchor.project_root)))
        manifest = hook_manifest_status()
        level = interception_state(runtime.archive, host)
        payload = {
            # Scope-explicit (B4-8 ext.): status names the project it is
            # answering about.
            "project": str(runtime.anchor.project_root),
            "plugin_installed": manifest["plugin_installed"],
            "session_hook_seen": manifest["session_hook_seen"],
            "pretool_hook_seen": manifest["pretool_hook_seen"],
            # CX-3: per-host STRUCTURAL detail (manifest present, matches the
            # generator, which events it declares) - never a live host-state
            # read (that stays `hooks install --host <name>`'s job, an
            # explicit action, not a `status` side effect).
            "host_registration": hooks_registration_report(),
            "last_proof": last_proof(runtime.archive, host),
            # CX-5: the five-level grade (was HARD/UNAVAILABLE only).
            "verdict": level,
        }
        payload.update(_hooks_health_fields(runtime.archive, host, level))
        return CommandResult(payload)
    if args.hooks_command == "probe":
        if not runtime.archive.initialized():
            return CommandResult(
                {
                    "probe": "not-run",
                    "project": str(runtime.anchor.project_root),
                    "reason": (f"godmode is not initialized for "
                               f"{runtime.anchor.project_root}; run `godmode init` first"),
                },
                exit_code=1,
            )
        report = run_probe(Path(runtime.anchor.project_root), runtime.archive, host)
        return CommandResult(report, exit_code=0 if report["state"] == "HARD" else 1)
    if args.hooks_command == "wire":
        # Codex CLI 0.150.1 ignores plugin-bundled hook manifests (host bug,
        # 2026-08-28); the project-level file is what its runtime loads.
        from .godmode_host_manifests import (
            write_antigravity_project_hooks, write_codex_project_hooks,
            write_opencode_project_shim)

        plugin_root = Path(__file__).resolve().parents[2]
        wire_host = getattr(args, "host", None) or "codex"
        if wire_host == "codex":
            return CommandResult(write_codex_project_hooks(
                plugin_root, Path(runtime.anchor.project_root),
                force=getattr(args, "force", False)))
        if wire_host == "opencode":
            return CommandResult(write_opencode_project_shim(
                plugin_root, Path(runtime.anchor.project_root),
                force=getattr(args, "force", False)))
        if wire_host == "antigravity":
            return CommandResult(write_antigravity_project_hooks(
                plugin_root, Path(runtime.anchor.project_root),
                force=getattr(args, "force", False)))
        return CommandResult(
            {"error": "hooks wire knows codex (project hooks fallback), "
                      "opencode (Bun shim install), and antigravity "
                      "(.agents/hooks.json merge) today"},
            exit_code=1)
    if args.hooks_command == "install":
        if getattr(args, "git", False):
            _require_archive(runtime)
            project_root = Path(runtime.anchor.project_root)
            if getattr(args, "uninstall", False):
                return CommandResult(git_hooks_uninstall(runtime.archive, project_root))
            report = git_hooks_install(runtime.archive, project_root)
            # M6 (external audit): `declared` alone used to decide the exit
            # code, so an unresolvable hooks directory or a swallowed
            # `chmod` failure - both `declared: True` - reported success.
            # `git_hooks_install` now names its own real outcome in `ok`;
            # this reads that field directly rather than re-deriving it.
            return CommandResult(report, exit_code=0 if report["ok"] else 1)
        state_path = Path(args.state_path) if args.state_path else None
        report = hooks_install_verify(None, host, state_path=state_path)
        # "unverifiable"/"verified" both exit 0 - an honest unknown is not a
        # failure. Only "partial" (some declared hook confirmed missing from
        # the host's own state) fails loudly, per CX-3's binding instruction.
        return CommandResult(report, exit_code=1 if report["verdict"] == "partial" else 0)
    if args.hooks_command == "verify":
        _require_archive(runtime)
        report = run_git_verify(runtime.archive)
        return CommandResult(report, exit_code=0 if report["state"] == "HARD" else 1)
    raise ArchiveError(f"Unknown hooks subcommand {args.hooks_command!r}")


def cmd_assess(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = assess_project(Path(runtime.anchor.project_root), budget=args.token_budget,
                            archive=runtime.archive)
    if not args.full:
        report["authority_claims"].pop("top", None)
    return CommandResult(report, exit_code=1 if report["verdict"] == "at-risk" else 0)


def cmd_trust(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Report what a repository's checked-in agent configuration would run.

    High severity fails the command, because a blanket permission grant or a
    fetch-and-run hook answers a question the operator was never asked. Lower
    findings are reported without failing: a declared server is ordinary, and
    a gate that stopped every clone carrying one would be switched off.
    """
    report = scan_agent_configuration(Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=1 if report["high_severity"] else 0)


def cmd_selftest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = run_selftest()
    return CommandResult(report, exit_code=0 if report["verdict"] == "enforcing" else 1)


def cmd_scope(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.minimality:
        report = minimality(Path(runtime.anchor.project_root), args.since or "HEAD")
        # Non-blocking by design: size is a smell, not a sin.
        return CommandResult(report)
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
    if args.staged:
        report = scan_staged(Path(runtime.anchor.project_root))
        return CommandResult(report, exit_code=0 if report["clean"] else 1)
    if args.action is None:
        raise ArchiveError("egress requires an action or --staged")
    disclosure = egress_notice(args.action, args.purpose,
                               Path(runtime.anchor.project_root), args.path,
                               destination=args.destination, redact=args.redact)
    # A secret inside the requested scope blocks the disclosure rather than
    # redacting quietly: the user decides, having been told.
    return CommandResult(disclosure, exit_code=1 if disclosure["blocked"] else 0)


def cmd_untrusted(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = scan_untrusted(Path(runtime.anchor.project_root))
    # A truncated sweep is not a clean one: findings warn on what was found,
    # truncation warns on what was never read. Either costs the exit code, or
    # a capped scan of an unscanned population would still read as "pass".
    warned = report["files_with_findings"] or report.get("truncated")
    return CommandResult(report, exit_code=1 if warned else 0)


def cmd_swallow(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    project = Path(runtime.anchor.project_root)
    report = scan_swallow(project)
    # RULING B3-3-2: a live regression fails EVERY invocation, including
    # `--update-baseline` - `update_baseline`'s min() protection genuinely
    # holds the ceiling and never baselines the regression away, but an exit
    # code that reads 0 regardless would collapse "regression" and
    # "regression, not rescued" into one observable - the exact silent-
    # failure shape this scanner exists to catch in OTHER code. A truncated
    # sweep is a claim about a population that was never fully read, so it
    # fails the same way; advisory findings alone do not (see module
    # docstring).
    warned = bool(report["regressions"]) or report["truncated"]
    if getattr(args, "update_baseline", False):
        written = update_swallow_baseline(project, report["counts"])
        return CommandResult(
            {"baseline_written": written, "counts": report["counts"]},
            exit_code=1 if warned else 0,
        )
    return CommandResult(report, exit_code=1 if warned else 0)


def cmd_bindings(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    project = Path(runtime.anchor.project_root)
    if args.write:
        return CommandResult(bindings_write(project))
    report = bindings_check(project)
    return CommandResult(report, exit_code=1 if report["drifted"] else 0)


def cmd_sbom(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    project = Path(runtime.anchor.project_root)
    if args.gate:
        verdict = dependency_gate(project)
        return CommandResult(verdict, exit_code=0 if verdict["verdict"] == "within-policy" else 1)
    if args.format == "spdx":
        return CommandResult(sbom_spdx(project))
    if args.format == "cyclonedx":
        return CommandResult(sbom_cyclonedx(project))
    return CommandResult(build_sbom(project))


def cmd_checksums(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = release_checksums(Path(runtime.anchor.project_root))
    if args.verify:
        expected = Path(args.verify).read_text(encoding="utf-8")
        matched = expected == report["manifest"]
        return CommandResult(
            {"files": report["files"], "matched": matched,
             "manifest_sha256": report["manifest_sha256"]},
            exit_code=0 if matched else 1,
        )
    return CommandResult(report)


def cmd_recurrences(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    report = recurrences(runtime.archive)
    # A control that blocked twice on the same cause is a finding about the process,
    # not about that one block.
    return CommandResult(report, exit_code=1 if report["count"] else 0)


def cmd_scenarios(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = run_scenarios(only=args.only)
    # A control that passes its unit test and misses the failure it was written
    # for is the expensive kind of green, so a miss fails the command. A
    # blocking registry finding (U-S1: an unregistered, drifted, or orphaned
    # eval id) is the same kind of green for the registry itself - the
    # findings already ride along in the payload, but they must fail the
    # gate too, or the registry is inert as CI protection.
    ok = report["verdict"] == "all-caught" and not report["registry"]["blocking"]
    return CommandResult(report, exit_code=0 if ok else 1)


def _working_tree_changes(project: Path) -> list[str]:
    """Paths the working tree has changed, as git spells them.

    Defaulting to this is what makes closure runnable at the moment it matters.
    Requiring the caller to list what they just edited is how `affected` ended
    up being a query nobody thought to run.
    """
    raw = _git_tags_raw(project, "status", "--porcelain")
    paths: list[str] = []
    for line in raw.splitlines():
        entry = line[3:].strip() if len(line) > 3 else ""
        if " -> " in entry:  # a rename reports both sides; the new one is what exists
            entry = entry.split(" -> ", 1)[1]
        if entry:
            paths.append(entry.strip('"'))
    return paths


def cmd_atlas(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.atlas_command == "load":
        # Load must not rebuild: the whole point is answering from the saved map
        # while stating how much of it is still true.
        report = load_index(Path(runtime.anchor.project_root) / args.source,
                            Path(runtime.anchor.project_root))
        return CommandResult(report, exit_code=0 if report["confidence"] == 1.0 else 1)
    atlas = build_atlas(Path(runtime.anchor.project_root))
    # The verb leaves a receipt (S13 audit: it fired constantly as a
    # library and never as a verb, and without a record the census could
    # not even ask). Best-effort, counts only, query verbs only - save/map
    # are maintenance, not diagnosis.
    if args.atlas_command in ("affected", "diagnose", "closure", "seams",
                              "cycles"):
        try:
            if runtime.archive.initialized():
                runtime.archive.append(
                    "action", "atlas-query",
                    {"verb": args.atlas_command}, evidence=[])
        except Exception:  # noqa: BLE001
            pass
    if args.atlas_command == "save":
        return CommandResult(save_index(atlas, Path(runtime.anchor.project_root) / args.to))
    if args.atlas_command == "map":
        return CommandResult(atlas.view())
    if args.atlas_command == "affected":
        return CommandResult(atlas.affected(
            args.symbol, depth=args.depth,
            evidence=None if args.include_inferred else "extracted",
            relations=set(args.relations) if args.relations else None))
    if args.atlas_command == "closure":
        # Changed files come from the caller or from the working tree. Reading
        # the tree by default is what makes this runnable at the moment it
        # matters - nobody thinks to list what they just edited, which is the
        # same reason `affected` stayed a query nobody ran.
        changed = list(args.changed) if args.changed else _working_tree_changes(
            Path(runtime.anchor.project_root))
        report = unfollowed_dependents(atlas, changed, depth=args.depth)
        return CommandResult(report, exit_code=1 if report["findings"] else 0)
    if args.atlas_command == "seams":
        report = speculative_seams(atlas)
        return CommandResult(report, exit_code=1 if report["findings"] else 0)
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
    root = Path(runtime.anchor.project_root).resolve()
    target = (root / args.path).resolve()
    # Containment before reading: a `../` or absolute path must not let a
    # bounded read escape the project it claims to be bounded to.
    if not target.is_relative_to(root):
        raise ArchiveError(f"Path escapes the project root and was not read: {args.path}")
    window = slice_file(target, args.start, args.end)
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
        "issues": detect_context_issues(runtime.anchor, records, current, archive=runtime.archive),
        "capacity": capacity_checkpoint_due(runtime.archive),
        "scan_performed": args.scan,
    }
    orphaned = runtime.archive.orphaned()
    if orphaned:
        payload["orphaned_archive"] = orphaned
    return CommandResult(payload)


def cmd_context_structure(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B4-6 MVP: build/refresh the structural index (incremental by content
    hash) and render the bounded outline from it. Names and hashes only."""
    _require_archive(runtime)
    from .godmode_structure import build_structure_index, structure_outline
    report = build_structure_index(
        runtime.archive, Path(runtime.anchor.project_root))
    return CommandResult({
        "report": report,
        "outline": structure_outline(runtime.archive,
                                     limit_lines=args.limit_lines),
    })


def cmd_context_rebuild(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return cmd_inspect(args, runtime)


def cmd_context_why(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    about = getattr(args, "about", None)
    if about:
        return CommandResult(context_why(runtime.anchor, runtime.archive, about))
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
    """Record a handoff, and question the obligations already being carried.

    `--review` asks the other half of the continuity question. Recording what
    must not be forgotten was always here; nothing asked whether a carried
    obligation was still worth doing, so one recorded validly and made moot by
    a later release was restated in every handover until a human noticed.
    """
    if getattr(args, "review", False):
        _require_archive(runtime)
        # Every record, not only checkpoints: retirement is recorded as an
        # `obligation` with a closed status, and filtering to checkpoints meant
        # the closure never reached the reviewer. The mechanism was right and
        # the wiring starved it, so closing something changed nothing.
        records = runtime.archive.read_events()
        report = review_obligations(records)
        # The other direction of the same continuity question. An obligation is
        # something the agent wrote down and kept carrying; a request is
        # something the operator said once, which leaves no artefact at all and
        # so is the half that goes missing without anyone able to name it.
        report["requests"] = review_requests(records)
        # Reported, never failed: a standing obligation that looks stale is a
        # question for the operator, not a verdict the runtime is entitled to.
        return CommandResult(report, exit_code=0)
    if getattr(args, "summary_positional", None) and not args.summary:
        args.summary = args.summary_positional
    # Naming the missing flag rather than letting argparse describe a
    # requirement that only applies when not reviewing.
    if not args.summary or not args.status:
        raise ArchiveError("checkpoint requires --summary and --status (or --review)")
    if args.status in {"complete", "fixed"} and not args.evidence:
        raise ArchiveError("Completion requires at least one --evidence reference")
    result = CommandResult(
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
                    # Recorded so a rewind preview can name the exact commit.
                    "head": runtime.anchor.head,
                },
                args.evidence,
            )
        }
    )
    # B4-7 rider 1: a recorded checkpoint starts the tracked-mutation count
    # over - the suggestion measures distance from THIS moment now.
    from .godmode_guardrails import reset_mutation_counter
    reset_mutation_counter(runtime.archive)
    # What was learned, beside what was verified: an incident newer than the
    # newest lesson is a failure that taught nothing on the record yet.
    # Advisory - the checkpoint itself is already written above.
    last_incident = max(
        (r["sequence"] for r in runtime.archive.select(kind="incident", limit=500)),
        default=None)
    if last_incident is not None:
        last_lesson = max(
            (r["sequence"] for r in runtime.archive.select(kind="lesson", limit=500)),
            default=0)
        if last_incident > last_lesson:
            result.payload["advisories"] = [
                f"incident seq:{last_incident} postdates the newest lesson; "
                "if it taught something, record it now "
                "(godmode remember --kind lesson) while the evidence is fresh"
            ]
    return result


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
    # `remember` defaulted every kind to `active`, and a request is read only
    # when it says `open`: the review and the detector both filter on it. A
    # hand-written request therefore landed in the archive and was read by
    # nothing. The default is now per-kind; an explicit --status still wins,
    # which is what keeps `--kind request --status closed` a closure.
    if args.kind == "incident":
        from .godmode_mistakes import record_incident
        record = record_incident(
            runtime.archive, args.subject, args.value,
            failure_class=getattr(args, "failure_class", None),
            turning_point=getattr(args, "turning_point", False),
            cites=args.evidence,
        )
        return CommandResult({"record": _event_view(record)})
    status = args.status or ("open" if args.kind == "request" else "active")
    data: dict[str, Any] = {"value": args.value, "status": status}
    if args.kind == "obligation" and getattr(args, "standing", False):
        data["standing"] = True
    if args.kind == "lesson":
        data["generalized_guard"] = args.guard
    if args.kind == "assumption":
        # U-S4 assumption gate (`godmode_attest.assumption_gate`) matches
        # records to the session they were stated in; the generic path
        # below stores no session field for any other kind, but this kind
        # exists specifically so the gate has something to find.
        data["session"] = _session(runtime, args.session)
    if args.kind == "request":
        # The digest is what the closure path matches on, and a request written
        # by hand had none - so `--kind request --status closed` closed nothing
        # even once the parser accepted it. Computed from the subject under the
        # same normalisation the hook uses, which is what makes retyping the
        # line enough to close the prompt it came from.
        data["digest"] = request_digest(args.subject)
        data["source"] = getattr(args, "source", "stated")
    payload: dict[str, Any] = {
        "record": _append(runtime, args.kind, args.subject, data, args.evidence)
    }
    # Sibling advisory (field report, 2026-09-01): an obligation recorded
    # over an open one with the same vocabulary is usually the same duty
    # in new clothes - name the elder now, or both nag forever.
    if args.kind == "obligation" and status not in ("closed", "done", "retired"):
        try:
            from .godmode_mistakes import obligation_sibling_advisory
            advisory = obligation_sibling_advisory(
                runtime.archive, args.subject, args.value)
            if advisory:
                payload["advisory"] = advisory
        except Exception:  # noqa: BLE001
            pass
    return CommandResult(payload)



def cmd_loop_contract(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_loop import close_loop, declare_loop, tick_loop
    if args.loop_command == "declare":
        record = declare_loop(runtime.archive, args.name,
                              max_iterations=args.max_iterations,
                              stop_when=args.stop_when)
        return CommandResult({"record": _event_view(record)})
    if args.loop_command == "tick":
        report = tick_loop(runtime.archive, args.name,
                           progress=not args.empty, note=args.note,
                           evidence=args.evidence)
        return CommandResult(report, exit_code=1 if report["escalation"] else 0)
    record = close_loop(runtime.archive, args.name, outcome=args.outcome,
                        evidence=args.evidence)
    return CommandResult({"record": _event_view(record)})


def cmd_digest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_digest import render_digest
    return CommandResult(render_digest(runtime.archive, since=args.since))


def cmd_doctor(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # Scope-explicit (B4-8 ext.): every status answer names the project it
    # is about, in JSON and in prose.
    project = str(runtime.anchor.project_root)
    if not runtime.archive.initialized():
        return CommandResult(
            {
                "project": project,
                "healthy": False,
                "issues": [{"code": "not-initialized", "severity": "error",
                            "detail": f"Not initialized for {project}. Run init."}],
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
    # Best-effort failures the gate continued past this process. Surfaced
    # here because recording them and never showing them would leave the
    # same silence the swallow ratchet exists to remove, one layer along:
    # advisory, since each site continued on purpose.
    for reason in sentinel_degradations():
        issues.append({
            "code": "degraded-best-effort",
            "severity": "warning",
            "detail": f"Continued past a failure while {reason}.",
        })
    # Advisory, never a health flip: a record window where nothing ever
    # failed is evidence about the checks, not about the work.
    from .godmode_attest import dissent_check
    dissent = dissent_check(runtime.archive)
    if dissent:
        issues.append({"code": "no-dissent", "severity": "warning", "detail": dissent})
    if args.deep:
        # S6 (obligation 4436): name every cached runtime that is not this
        # one - stale installs share the archive and race its chain. Behind
        # --deep because it reads the user's home caches, not the project.
        from .godmode_constants import RUNTIME_VERSION
        from .godmode_host_manifests import runtime_census_issues

        issues.extend(runtime_census_issues(RUNTIME_VERSION))
    healthy = not any(issue["severity"] == "error" for issue in issues)
    return CommandResult(
        {
            "project": project,
            "healthy": healthy,
            "archive": verification,
            # Advisory always - calibration never flips health. It reports
            # how well declared confidence has tracked outcomes, and the
            # standing debt of scored claims nothing ever resolved.
            "calibration": calibration_summary(runtime.archive, records=records),
            # Demand-vs-use census: which machinery families the record
            # demanded versus which fired. Dormancy WITH demand is the
            # alarm; idle is health. Advisory - never flips health.
            "utilization": __import__(
                "godmode_runtime.godmode_metrics", fromlist=["utilization"]
            ).utilization(runtime.archive, records=records),
            # Approval quality from the host-approval rows: a long unbroken
            # approval streak reads as automation bias. Advisory always.
            "oversight": __import__(
                "godmode_runtime.godmode_metrics", fromlist=["oversight_pulse"]
            ).oversight_pulse(runtime.archive, records=records),
            "issues": issues,
            "deep_scan": args.deep,
            "network_used": False,
            "background_process": False,
            # The design boundary fails open when undeclared, which is correct
            # - no project that predates it may start refusing edits - but a
            # gap nothing reports is a gap nobody notices, and a guard that
            # governs nothing looks identical to one that governs everything.
            "design_boundary": (
                "declared" if declared_design(runtime.anchor.project_root) else "unconfigured"
            ),
        },
        exit_code=0 if healthy else 1,
    )


def cmd_fence_audit(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Every changed file, against what the plan said it would touch.

    The boundary gate covers tools that announce a `file_path`. This covers the
    result - including work done by a shell command, before the plan was
    approved, or in a session where the plugin was switched off.

    `--complete` (U-B1) asks a finer question of the same gap: not just which
    files changed, but which hunks, parsed straight from `git diff
    --unified=0 HEAD` - so an out-of-fence edit, an unauthorized deletion, and
    a stray debug tag are told apart rather than folded into one path list.
    """
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    if args.complete:
        report = completion_audit(runtime.archive, project)
        return CommandResult(report, exit_code=1 if report["findings"] else 0)
    changed = list(args.changed) if args.changed else _working_tree_changes(project)
    report = audit_changes(runtime.archive, project, changed)
    return CommandResult(report, exit_code=1 if report["untraceable"] else 0)


def cmd_fence_acceptance(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Completions that never cited the acceptance their plan declared."""
    _require_archive(runtime)
    report = unaccepted_completions(runtime.archive)
    return CommandResult(report, exit_code=1 if report["findings"] else 0)


def cmd_fence_delete_check(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B3-6: whether a deletion the fence would otherwise allow may proceed."""
    _require_archive(runtime)
    verdict = deletion_verdict(runtime.archive, args.path,
                               project_root=Path(runtime.anchor.project_root))
    return CommandResult(verdict, exit_code=0 if verdict["allowed"] else 1)


def cmd_fence_delete_precheck(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B3-6: attest the provenance pre-check, reusing C-16's reverse-impact
    traversal, before a tracked file may be deleted."""
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    affected = build_atlas(project).affected(args.path)
    record_deletion_precheck(
        runtime.archive, project, args.path,
        history_read=args.history_read, sole_carrier=args.sole_carrier, affected=affected,
    )
    verdict = deletion_verdict(runtime.archive, args.path, project_root=project)
    return CommandResult(verdict, exit_code=0 if verdict["allowed"] else 1)


def cmd_precheck(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Was this already built, and was it already refused.

    Both answers were already in the archive and nothing read either. The one
    moment they are worth having is before the work starts, which is the one
    moment nobody thinks to ask.

    GAP-2's paired-artifact question rides along on the same diff-listing
    default `fence audit` already uses (`--changed`, or the working tree)
    - precheck already runs before work starts, which is also the moment a
    one-sided diff against a declared pair is still cheap to fix.
    """
    if getattr(args, "preflight", False):
        from .godmode_preflight import push_preflight
        report = push_preflight(Path(runtime.anchor.project_root),
                                suite=getattr(args, "suite", None),
                                archive=runtime.archive)
        return CommandResult(report, exit_code=1 if report["verdict"] == "findings" else 0)
    if not args.about:
        raise ArchiveError("precheck requires --about (or --preflight)")
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    changed = list(args.changed) if args.changed else _working_tree_changes(project)
    report = run_precheck(project, runtime.archive, args.about, changed_files=changed)
    # Patterns the record already holds, delivered before the action -
    # advisory, once per session per pattern, never part of the exit code.
    from .godmode_precheck import recurrence_nudges
    report["recurrence_advisories"] = recurrence_nudges(
        runtime.archive, args.about, changed, _session(runtime, getattr(args, "session", None)))
    # Lessons recorded since the last law compile, load-bearing NOW rather
    # than after the next regen. Marked fresh-uncompiled; advisory only.
    from .godmode_law import fresh_laws
    report["fresh_lessons"] = fresh_laws(runtime.archive, project)
    # Non-zero on a hit so a script can stop, but the payload is a question and
    # never a refusal: prior work is a reason to look, not grounds to decline.
    # A paired-artifact hit never contributes to this exit code either - v1
    # is advisory only, same as every other question this command asks.
    return CommandResult(report, exit_code=1 if report["verdict"] == "prior-work-found" else 0)


def cmd_precheck_declare_pair(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Declare "these two artifacts change together" (GAP-2).

    Writes once; every later `precheck` (and `--changed` sweep) checks
    every diff against it from then on. `--label` names the pair for
    later re-declaration or lookup - it is not free text, it is the key.
    """
    _require_archive(runtime)
    record = declare_paired_artifact(
        runtime.archive, args.label, args.a, args.b, args.reason or "",
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "label": args.label,
         "a": data["a"], "b": data["b"], "reason": data["reason"]},
        exit_code=0,
    )


def cmd_boundaries_propose_ui(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Candidate design globs for a human to accept, narrow, or throw away.

    It prints and never writes. Enforcement reads declared globs only, and a
    scope that installs itself is the auto-detection this boundary exists to
    refuse: it would freeze server-side code that happens to be `.tsx`, miss a
    UI change made in a plain route file, and move on its own the next time
    somebody adds an import.
    """
    root = Path(runtime.anchor.project_root)
    proposed = propose_design(root)
    return CommandResult({
        "proposed": proposed,
        "declared": bool(declared_design(root)),
        "config": BOUNDARY_CONFIG,
        "written": False,
        "next_action": (
            f"write the globs you agree with into {BOUNDARY_CONFIG} as "
            '{"ui": {"declared": [...], "except": [...]}}'
            if proposed else
            "no design surfaces found; leave the boundary undeclared"
        ),
    })


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
    if getattr(args, "git_hook", None):
        return _cmd_guard_git_hook(args, runtime)
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


def _cmd_guard_git_hook(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """CX-4: `guard --git-hook <name>` - the exact call every installed git
    hook script makes. Uninitialized is never a block (an installed hook can
    only exist under a policy this project already declared, but a foreign
    caller running the file standalone, or a project reset after install,
    must still fail open here rather than breaking every git operation).
    """
    name = args.git_hook
    if not runtime.archive.initialized():
        return CommandResult({
            "git_hook": name, "verdict": "allow",
            "project": str(runtime.anchor.project_root),
            "reason": f"godmode is not initialized for "
                      f"{runtime.anchor.project_root}; the git backstop is "
                      f"advisory-only until it is",
        })
    project_root = Path(runtime.anchor.project_root)
    stdin_text: str | None = ""
    if name == "pre-push" and not sys.stdin.isatty():
        # `None` (fix round 1, C2) is the "could not be read at all" signal
        # `_evaluate_pre_push` fails closed on - distinct from "" (genuinely
        # nothing to read; not the tty case, not an unparseable stream).
        try:
            stdin_text = sys.stdin.read()
        except (OSError, ValueError, UnicodeDecodeError):
            stdin_text = None
    report = evaluate_git_hook(runtime.archive, project_root, name, stdin_text)
    return CommandResult(report, exit_code=0 if report["verdict"] == "allow" else 1)


def cmd_license_check(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B3-5: whether an operation naming an external repo may proceed."""
    _require_archive(runtime)
    verdict = license_verdict(runtime.archive, Path(runtime.anchor.project_root),
                              args.operation)
    return CommandResult(verdict, exit_code=0 if verdict["allowed"] else 1)


def cmd_license_attest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B3-5: record a license classification for a repository read or absorbed."""
    _require_archive(runtime)
    record = record_license_attestation(
        runtime.archive, args.repo, args.classification, args.clean_room_note or ""
    )
    return CommandResult({"record": _event_view(record)})


def cmd_protect(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Pin, unpin, or list protected evaluator files (U-B2).

    Pinning is tighten-only and needs no capability - the same reasoning
    `pin_evaluator` itself carries. Unpinning is the operation that can
    defeat the mechanism, so it is gated exactly like every other R5
    operation: a staged capability is tried silently first (the same
    ergonomics the hook already gives every other refusal an answer to),
    then an explicit `--capability`, and only then refused - never executed
    on a bare `--unpin` with nothing behind it.
    """
    _require_archive(runtime)
    project_root = runtime.anchor.project_root
    if args.list:
        pins = pinned_evaluators(runtime.archive)
        return CommandResult({
            "evaluators": [{"path": path, "sha256": digest}
                           for path, digest in sorted(pins.items())],
        })
    if args.pin:
        result = pin_evaluator(runtime.archive, project_root, args.pin)
        return CommandResult({"pinned": True, **result})

    # --unpin
    operation = unpin_operation_text(args.unpin)
    broker = CapabilityBroker(runtime.archive)
    staged = broker.consume_staged(operation)
    if staged is not None:
        result = unpin_evaluator(runtime.archive, project_root, args.unpin)
        return CommandResult({"unpinned": True, "authorized_by": "staged capability",
                              **result})
    if args.capability:
        broker.consume(operation, args.capability)
        result = unpin_evaluator(runtime.archive, project_root, args.unpin)
        return CommandResult({"unpinned": True, "capability_consumed": True, **result})
    return CommandResult(
        {
            "unpinned": False,
            "capability_required": True,
            "reason": (
                "unpinning a protected evaluator needs a capability; stage one with "
                f"`godmode authorize stage --operation {json.dumps(operation)}` - it "
                "needs the password from `godmode authorize setup`, is spent once, "
                "and expires"
            ),
        },
        exit_code=3,
    )


def cmd_authorize_setup(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    broker = CapabilityBroker(runtime.archive)
    if args.password_stdin:
        broker.configure(read_password_stdin())
    else:
        broker.configure_interactive()
    return CommandResult({"configured": True, "storage": "local-only"})


def cmd_authorize_request(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    # Requesting is always available: an agent has no terminal, and the point is to
    # let it ask durably rather than be unable to ask at all.
    return CommandResult(
        CapabilityBroker(runtime.archive).request(args.operation, args.purpose)
    )


def cmd_authorize_list(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    found = CapabilityBroker(runtime.archive).requests(state=args.state)
    return CommandResult({"requests": found, "count": len(found)})


def cmd_authorize_grant(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    broker = CapabilityBroker(runtime.archive)
    password = read_password_stdin() if args.password_stdin else None
    if password is None:
        from .godmode_sentinel import _require_tty

        _require_tty()
        import getpass

        password = getpass.getpass("Godmode approval password: ")
    return CommandResult(broker.grant(args.request, password, args.ttl))


def cmd_authorize_deny(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(CapabilityBroker(runtime.archive).deny(args.request, args.reason))


def cmd_authorize_stage(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Authorise one exact operation and leave it where the hook will find it.

    The gate's refusal used to name a remedy nobody could perform: a host tool
    call carries no field a capability could travel in, so the broker was
    unreachable and the only answer to a false positive was switching the guard
    off. Staging is that answer, with every property of the token kept - the
    password, the exact operation, the expiry, the single use.

    `--from-last-refusal` reads the operation from the gate's own refusal
    record instead of asking the operator to retype what the refusal already
    named verbatim. Nothing about the trust model changes: the password is
    still required, the capability is still spent once and still expires -
    only the typing is gone. The operation is echoed back before the
    password is read, so a stale `--nth` is caught by eye rather than spent
    on the wrong command.
    """
    _require_archive(runtime)
    if args.from_last_refusal:
        operation = stage_from_refusal(runtime.archive, nth=args.nth)
        print(json.dumps(
            {"from_last_refusal": True, "nth": args.nth, "operation": operation},
            ensure_ascii=False,
        ))
    elif args.operation:
        operation = args.operation
    else:
        raise ArchiveError("`authorize stage` requires --operation or --from-last-refusal")
    broker = CapabilityBroker(runtime.archive)
    password = read_password_stdin() if args.password_stdin else None
    if password is None:
        from .godmode_sentinel import _require_tty

        _require_tty()
        import getpass

        password = getpass.getpass("Godmode authorization password: ")
    broker.stage(operation, password, args.ttl)
    preview = classify_action(operation)
    return CommandResult({
        "staged": True,
        "operation": operation,
        "category": preview["category"],
        "tier": preview["tier"],
        "from_last_refusal": args.from_last_refusal,
        "spends_on": "the next attempt at this exact operation, once",
        # The token is not printed. It is already where it needs to be, and a
        # capability on a terminal is a capability in a scrollback buffer.
        "note": "the next matching tool call is permitted; nothing else is",
    })


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
    if args.claim:
        from .godmode_lens import claim_worktree

        outcome = claim_worktree(runtime.archive, runtime.anchor)
        # A collision is surfaced before mutation, as a non-zero exit.
        return CommandResult(outcome, exit_code=1 if outcome["collisions"] else 0)
    if args.release:
        from .godmode_lens import release_worktree

        return CommandResult(release_worktree(runtime.archive, runtime.anchor))
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
    if args.reconcile:
        report = reconcile_versions(Path(runtime.anchor.project_root))
        return CommandResult(report, exit_code=0 if report["verdict"] == "agreed" else 1)
    if not args.name and not args.value:
        # Grok 0.3.4 field report: bare `version` tried to record a fact
        # and failed on a consumer project; the obvious reading of the bare
        # command is "what version am I running" - answer it, write nothing.
        from .godmode_constants import RUNTIME_VERSION

        return CommandResult({"version": RUNTIME_VERSION,
                              "note": "recording a version fact needs --name and --value"})
    return CommandResult(
        {"record": _append(runtime, "version", args.name, {"value": args.value, "status": args.status}, args.evidence)}
    )


def cmd_environment(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    verdict = classify_environment(args.target)
    return CommandResult(
        verdict, exit_code=0 if verdict["mutation_allowed_without_capability"] else 1
    )


def cmd_fuzz(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = run_fuzz(seed=args.seed, iterations=args.iterations)
    # A critical finding is a gate that let something through; anything else is
    # reported without failing the command.
    return CommandResult(report, exit_code=1 if report["critical"] else 0)


def cmd_metrics(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "complexity", False):
        # Tree scan, so opt-in rather than folded into every metrics call.
        from .godmode_metrics import branch_complexity
        return CommandResult(
            branch_complexity(Path(runtime.anchor.project_root)))
    _require_archive(runtime)
    report = product_metrics(
        runtime.archive, Path(runtime.anchor.project_root), window=args.window)
    if args.markdown:
        return CommandResult({"markdown": render_metrics(report)})
    # Below target is a finding about the product, not an error in the command.
    return CommandResult(report, exit_code=1 if report["verdict"] == "below-target" else 0)


def cmd_roi(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """U-E1: counts-only ROI report. U-E7's `--digest` renders the
    would-have-caught view over gate_mode=observe records instead - a
    separate fold (`roi_digest`), never merged into the real-denial counts
    above. JSON with --json, prose otherwise, either way."""
    _require_archive(runtime)
    if getattr(args, "digest", False):
        digest = roi_digest(runtime.archive, sessions=args.sessions)
        # S11-B: the enforce-era section rides the same digest.
        from .godmode_roi import enforce_digest

        enforce = enforce_digest(runtime.archive)
        if enforce:
            digest["enforce"] = enforce
        if getattr(args, "json", False):
            return CommandResult(digest)
        return CommandResult({"report": render_roi_digest(digest)})
    report = roi_report(runtime.archive, sessions=args.sessions)
    if getattr(args, "json", False):
        return CommandResult(report)
    return CommandResult({"report": render_roi(report)})


def cmd_trends(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B4-5: per-session counts as a time series - gaps stated, never
    interpolated; the render holds the causal denylist."""
    _require_archive(runtime)
    report = trends_report(runtime.archive, sessions=args.sessions)
    if getattr(args, "json", False):
        return CommandResult(report)
    report["report"] = render_trends(report)
    return CommandResult(report)


def cmd_observe(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B4-10(c): what an observe-mode trial recorded, read back on request.

    Bare `observe` answers with the tier-shaped summary only - the same
    counts `assess` and the session brief carry, no command text. `--report`
    adds the last N would-have decisions with tier, category, reason and the
    operation text itself: command text appears HERE and nowhere else,
    because this is the one surface the operator reaches by explicitly
    asking for it. Still redaction-scanned - a secret-shaped operation is
    replaced whole (`find_secret_shapes`, the same scanner egress/trust/
    verdict already use; whole-value replacement, never partial masking).
    Zero would-haves renders an empty list beside `total: 0` - absence of
    signal stated, never implied.
    """
    _require_archive(runtime)
    payload: dict[str, Any] = {
        "project": str(runtime.anchor.project_root),
        "would_have": would_have_summary(runtime.archive),
    }
    if getattr(args, "report", False):
        observed = [
            record for record in runtime.archive.select(kind="refusal", limit=500)
            if (record.get("data") or {}).get("observed") is True
        ]
        decisions = []
        for record in observed[-max(1, args.last):]:
            data = record.get("data") or {}
            operation = str(data.get("operation", ""))
            if find_secret_shapes(operation):
                operation = "[redacted: secret-shaped content]"
            decisions.append({
                "sequence": record["sequence"],
                "tier": str(data.get("tier", "R?")),
                "category": str(data.get("category", "")),
                "would_have": str(data.get("would_have", "")),
                "reason": str(data.get("reason", "")),
                "operation": operation,
            })
        payload["decisions"] = decisions
    return CommandResult(payload)


def cmd_recurring(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """U-E10: recurring-ask mining. Proposals only; JSON with --json, prose otherwise."""
    _require_archive(runtime)
    report = mine_recurring_asks(runtime.archive, threshold=args.threshold)
    if getattr(args, "json", False):
        return CommandResult(report)
    return CommandResult({"report": render_recurrence(report)})


def cmd_upstream(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """B3-1 (GAP-1): one `upstream-diff` record per run - a named package's
    (or, via `--path`, a forked/fully-copied external repo's) shipped
    surface diffed against this project's own equivalents. Each `--dispose
    SYMBOL=DISPOSITION:BEHAVIOR_VERDICT` supplies the paired import+behavior
    verdicts for one unmatched symbol; a disposition given with no
    behavior_verdict is refused before the archive is ever touched."""
    _require_archive(runtime)
    dispositions: dict[str, dict[str, str | None]] = {}
    for raw in args.dispose:
        if "=" not in raw:
            raise ArchiveError(
                f"--dispose must be SYMBOL=DISPOSITION:BEHAVIOR_VERDICT, got {raw!r}")
        symbol, _, rest = raw.partition("=")
        disposition, _, behavior_verdict = rest.partition(":")
        dispositions[symbol.strip()] = {
            "disposition": disposition.strip() or None,
            "behavior_verdict": behavior_verdict.strip() or None,
        }
    outcome = record_upstream_diff(
        runtime.archive, Path(runtime.anchor.project_root),
        package=args.diff, path=args.path, language=args.language,
        dispositions=dispositions, evidence=args.evidence,
    )
    report = outcome["report"]
    exit_code = 1 if report["verdict"] == "stated-gap" or report["undispositioned"] else 0
    if getattr(args, "json", False):
        return CommandResult(report, exit_code=exit_code)
    return CommandResult({"upstream_diff": report}, exit_code=exit_code)


def cmd_expunge(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult(runtime.archive.expunge(args.sequence, args.reason))


def cmd_stage(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    session = _session(runtime, args.session)
    if args.skip:
        if not args.reason:
            raise ArchiveError("Skipping a stage requires --reason stating why")
        return CommandResult(skip_stage(runtime.archive, session, args.to, args.reason))
    if args.advance:
        outcome = stage_advance(runtime.archive, project, args.to, session)
        return CommandResult(outcome, exit_code=0 if outcome.get("advanced") else 1)
    verdict = stage_gate(runtime.archive, project, args.to, session=session)
    return CommandResult(verdict, exit_code=0 if verdict["allowed"] else 1)


def cmd_sop(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    session = _session(runtime, args.session)
    if args.attest:
        record = sop_attest(runtime.archive, session, args.attest,
                            result=args.result or "", evidence=args.evidence)
        return CommandResult({"record": _event_view(record)})
    return CommandResult(sop_status(runtime.archive, session))


def cmd_index(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    if args.index_command == "rebuild":
        return CommandResult(index_rebuild(runtime.archive, project))
    if args.index_command == "status":
        state = index_fresh(runtime.archive, project)
        return CommandResult(state, exit_code=0 if state["fresh"] else 1)
    try:
        return CommandResult(index_query(
            runtime.archive, project, args.task, limit=args.limit,
            allow_stale=args.allow_stale,
        ))
    except IndexStale as exc:
        return CommandResult(
            {"error": "IndexStale", "message": str(exc),
             "next": "run `index rebuild`, or pass --allow-stale to read anyway"},
            exit_code=1,
        )


def cmd_database(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "reanchor", False):
        # B4-1: the explicit recovery for a tail-truncated chain - accept
        # what remains and chronicle the acceptance. Never automatic.
        _require_archive(runtime)
        return CommandResult(runtime.archive.reanchor())
    # Naming the missing flags rather than letting argparse require them for
    # the modes that never read them (same pattern as checkpoint --review).
    if getattr(args, "propose", False) and not args.change:
        raise ArchiveError("db --propose requires --change")
    if (not args.inventory and not args.review_migration
            and not getattr(args, "propose", False)
            and not (args.engine and args.change and args.status)):
        raise ArchiveError(
            "db requires --engine, --change and --status (or --reanchor/"
            "--propose/--inventory/--review-migration)")
    if getattr(args, "inventory", False):
        inventory = schema_inventory(Path(runtime.anchor.project_root))
        if getattr(args, "propose", False):
            _require_archive(runtime)
            columns: dict[str, list[str]] = {}
            for pair in args.existing_column:
                table, _, column = pair.partition(":")
                columns.setdefault(table, []).append(column)
            review = schema_review(inventory, {
                "change": args.change, "existing_tables": args.existing_table,
                "existing_columns": columns, "proposed_table": args.proposed_table,
                "proposed_column": args.proposed_column, "review": args.review,
                "rollback": args.rollback or "",
            })
            return CommandResult({"inventory": inventory, "review": review},
                                 exit_code=0 if review["verdict"] == "approved" else 1)
        return CommandResult(inventory)
    if getattr(args, "review_migration", None):
        text = Path(args.review_migration).read_text(encoding="utf-8")
        verdict = migration_review(text)
        return CommandResult(verdict, exit_code=1 if verdict["blocking"] else 0)
    if getattr(args, "propose", False):
        _require_archive(runtime)
        columns: dict[str, list[str]] = {}
        for pair in args.existing_column:
            table, _, column = pair.partition(":")
            columns.setdefault(table, []).append(column)
        result = schema_ladder(runtime.archive, {
            "change": args.change,
            "existing_tables": args.existing_table,
            "existing_columns": columns,
            "proposed_table": args.proposed_table,
            "proposed_column": args.proposed_column,
            "review": args.review,
        })
        return CommandResult(result, exit_code=0 if result["approved"] else 1)
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
    _require_archive(runtime)
    # Routed through the single writer: a sprint record that bypassed the store's
    # validation would be a second truth.
    record = record_item(
        runtime.archive, args.name, args.name, args.status,
        evidence=args.evidence, proof=getattr(args, "proof", "") or "",
        extra={"capacity": args.capacity, "obligations": args.obligation},
    )
    return CommandResult({"record": _event_view(record)})


def cmd_status_render(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    return CommandResult({"document": render_view(runtime.archive)})


def cmd_status_handover(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    view = handover(
        runtime.archive, Path(runtime.anchor.project_root),
        session=_session(runtime, args.session) if args.session else None,
        charter=_charter(runtime) if args.session else None,
        anchor=runtime.anchor,
    )
    session = latest_session(runtime.archive)
    if session:
        report = contribution(runtime.archive, Path(runtime.anchor.project_root), session)
        if report["reportable"]:
            view["contribution"] = report
            view["summary"] = render_contribution(report)
    return CommandResult(view)


def cmd_docs_reconcile(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = reconcile_docs(Path(runtime.anchor.project_root), base=args.base)
    return CommandResult(report, exit_code=0 if report["verdict"] == "reconciled" else 1)


# Boundary tiers for hosts that read AGENTS.md and wire no hooks. One
# table; the emitter renders it and the traceability test reads it - the
# wording is host-neutral because AGENTS.md cannot know which dialect the
# reading agent speaks.
_BOUNDARY_TIERS = (
    ("Always fine", "reads, edits, commits, tests - allow-tier work is "
     "recorded, not asked about"),
    ("Ask first", "push, deploy, database migrations, history rewrites - a "
     "host with an ask dialog asks; a host without one denies and names "
     "`godmode authorize stage` as the remedy"),
    ("Never", "irreversible forms without the authorization password "
     "(force-push, rm -rf on a root, DROP TABLE); secrets in the record; "
     "project state outside this machine"),
)
# Rules teach WHEN, hooks capture WHAT (the compiled half already lives at
# the boundaries). Each moment names exactly one verb; the emitter checks
# the verb against the live subparsers, so a rule cannot describe a command
# that does not exist.
_WHEN_RULES = (
    ("a session starts or resumes", "resume",
     "read the recorded state before trusting memory of it"),
    ("you are about to say done, fixed, or passing", "claim",
     "record it with citations first - the stop gate blocks an unrecorded "
     "done once"),
    ("a check decides anything", "verify",
     "run it as `godmode verify <name> -- <command>` so the outcome is "
     "attested, not evaporated"),
    ("the same command fails twice with edits between", "remember",
     "open an incident (`--kind incident`) - the third try without one is "
     "a fix loop"),
    ("an incident closes", "remember",
     "distill the lesson (`--kind lesson --guard <rule>`) so the next "
     "session inherits the guard"),
    ("work item goes active", "criterion",
     "give it a pass condition before building toward it"),
    ("a review or audit concludes", "verdict",
     "record the verdict so the all-clear is a record, not a sentence"),
)
_AGENTS_BEGIN = "<!-- godmode:agents begin -->"
_AGENTS_END = "<!-- godmode:agents end -->"


def agentsmd_section(parser: argparse.ArgumentParser) -> str:
    """The AGENTS.md section, generated - never hand-typed - so it cannot
    drift from the CLI it describes. Commands come from the registered
    day-one verbs (each checked against the live subparsers), boundaries
    from the one tier table the traceability test also reads."""
    registered = set(_subparser_action(parser).choices)
    lines = [_AGENTS_BEGIN, "## Godmode", "",
             "A local, tamper-evident record of what the agent did, what it "
             "claimed, and what was verified. State lives under the git "
             "metadata directory; nothing leaves the machine.", "",
             "### Commands", ""]
    for name, blurb in _DAY_ONE_VERBS:
        if name not in registered:
            raise ArchiveError(
                f"day-one verb '{name}' is not a registered subparser; "
                "the generated section refuses to describe a command that "
                "does not exist")
        lines.append(f"- `godmode {name}` - {blurb}")
    lines += ["", "### When", ""]
    for moment, verb, blurb in _WHEN_RULES:
        root = verb.split()[0]
        if root not in registered:
            raise ArchiveError(
                f"when-rule verb '{root}' is not a registered subparser; "
                "the generated section refuses to describe a command that "
                "does not exist")
        lines.append(f"- When {moment}: `godmode {verb}` - {blurb}")
    lines += ["", "### Boundaries", ""]
    for tier, detail in _BOUNDARY_TIERS:
        lines.append(f"- **{tier}**: {detail}")
    # The section declares its own context cost (S16 nicety, absorbed from
    # the size-tiered-artifacts convention): a reader budgeting a context
    # window deserves the number where the cost is incurred. Rough bytes/4
    # estimate, rounded to keep the line stable across small edits.
    approximate_tokens = (sum(len(line) for line in lines) // 4 // 50 + 1) * 50
    lines += ["", f"_this section costs roughly {approximate_tokens} tokens_",
              "", _AGENTS_END]
    return "\n".join(lines)


def emit_agentsmd(parser: argparse.ArgumentParser, project_root: Path,
                  archive: Any = None) -> dict[str, Any]:
    """Write or refresh the godmode section of AGENTS.md, touching nothing else.

    Between the markers is godmode's; everything outside them is the
    project's and survives byte-for-byte. Re-emitting is idempotent.
    """
    section = agentsmd_section(parser)
    # The learnings travel too: a hookless agent reads AGENTS.md and a law
    # that never reaches it governs nothing. Bounded by the brief's own
    # top-laws budget; empty reads honestly empty, never a bare heading.
    if archive is not None:
        from .godmode_law import top_laws
        laws = top_laws(archive, 5) if archive.initialized() else []
        lines = ["", "### Learnings", ""]
        if laws:
            lines += [f"- {law['guard']}" for law in laws]
        else:
            lines.append("_no laws recorded yet - they accumulate as this "
                         "project corrects its agents_")
        newline = chr(10)
        section = section.replace(
            newline + _AGENTS_END,
            newline + newline.join(lines) + newline + newline + _AGENTS_END)

    target = project_root / "AGENTS.md"
    if target.is_file():
        existing = target.read_text(encoding="utf-8")
        if _AGENTS_BEGIN in existing and _AGENTS_END in existing:
            head, _, rest = existing.partition(_AGENTS_BEGIN)
            _, _, tail = rest.partition(_AGENTS_END)
            merged = head + section + tail
            action = "refreshed"
        else:
            merged = existing.rstrip("\n") + "\n\n" + section + "\n"
            action = "appended"
    else:
        merged = "# AGENTS\n\n" + section + "\n"
        action = "created"
    target.write_text(merged, encoding="utf-8")
    return {"action": action, "path": "AGENTS.md",
            "commands": len(_DAY_ONE_VERBS), "tiers": len(_BOUNDARY_TIERS)}


_RULES_TARGETS = {
    "cursor": Path(".cursor") / "rules" / "godmode.mdc",
    "copilot": Path(".github") / "instructions" / "godmode.instructions.md",
    "generic": Path("GODMODE-RULES.md"),
}


def emit_rules(project_root: Path, host: str = "generic") -> dict[str, Any]:
    """Render the canonical doctrine into a host's instruction format.

    One source (the same constants the session brief injects), generated
    never hand-edited - the bindings contract applied to instruction
    files, so hook-less hosts read the identity block through the one
    surface they actually load. Idempotent; the whole file is godmode's,
    unlike AGENTS.md where only the marked section is.
    """
    if host not in _RULES_TARGETS:
        raise ArchiveError(
            f"unknown rules host '{host}'; expected one of "
            f"{', '.join(sorted(_RULES_TARGETS))}")
    from .godmode_constants import DOCTRINE_TEXT, RED_FLAGS_TEXT

    when_lines = "\n".join(
        f"- When {moment}: `godmode {verb}` - {blurb}"
        for moment, verb, blurb in _WHEN_RULES)
    body = (
        "<!-- generated by `godmode docs --emit-rules` - edit the canonical "
        "constants, never this file -->\n\n"
        "# Godmode rules\n\n"
        f"{DOCTRINE_TEXT}\n\n{RED_FLAGS_TEXT}\n\n### When\n\n{when_lines}\n")
    target = Path(project_root) / _RULES_TARGETS[host]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return {"host": host, "path": str(_RULES_TARGETS[host]),
            "bytes": len(body)}


def cmd_docs(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "emit_rules", None):
        return CommandResult(emit_rules(
            Path(runtime.anchor.project_root), host=args.emit_rules))
    if getattr(args, "emit_agentsmd", False):
        report = emit_agentsmd(_build_parser(), Path(runtime.anchor.project_root),
                               archive=runtime.archive)
        return CommandResult(report)
    if getattr(args, "lint", False):
        report = lint_docs(Path(runtime.anchor.project_root))
        # High severity means something shipped that was never meant to; the
        # rest is reported without failing the command.
        return CommandResult(report, exit_code=1 if report["high_severity"] else 0)
    if getattr(args, "records", False):
        _require_archive(runtime)
        report = record_triggers(runtime.archive, base_sequence=args.base_sequence)
        return CommandResult(report, exit_code=0 if report["verdict"] == "reconciled" else 1)
    if getattr(args, "reconcile", False):
        return cmd_docs_reconcile(args, runtime)
    # Name the missing flag, not the internal record constraint it would trip.
    if not args.document or not args.status:
        raise ArchiveError("docs requires --document and --status (or --reconcile / --lint)")
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
    if getattr(args, "context", False):
        return CommandResult(
            build_context_brief(
                runtime.anchor, runtime.archive, token_budget=args.token_budget
            )
        )
    report = completion_report(
        runtime.archive, runtime.anchor, Path(runtime.anchor.project_root),
        session=getattr(args, "session", None) or None,
    )
    exit_code = 1 if report["fields"]["status"]["value"] == "blocked" else 0
    if getattr(args, "record_claims", False):
        # Finishing a task is what records the claim. `claim` was never used
        # here because it is a command somebody has to decide to run; saying
        # the work is done is the same assertion, made at the moment it is
        # actually made, and it is graded like any other.
        graded = []
        for assertion in claims_from_report(report):
            recorded = record_claim(
                runtime.archive, Path(runtime.anchor.project_root),
                report.get("session") or "unsessioned",
                assertion["text"], assertion["grade"], cites=assertion["cites"])
            graded.append({"text": assertion["text"],
                           "grade": recorded["data"]["grade"],
                           "downgraded": recorded["data"].get("downgraded", False),
                           "reason": recorded["data"].get("reason", "")})
        report["claims_recorded"] = graded
    if getattr(args, "markdown", False):
        return CommandResult({"markdown": render_markdown(report)}, exit_code=exit_code)
    return CommandResult(report, exit_code=exit_code)


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


def cmd_evals(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    project = Path(runtime.anchor.project_root)
    if args.write_snapshots:
        return CommandResult({
            "routing": check_snapshots(project, write=True),
            "charter": charter_snapshot(project, write=True),
            "ranking": ranking_snapshot(project, write=True),
            "verdict": "snapshots-written",
        })
    routing = run_routing_evals(project)
    snapshots = check_snapshots(project)
    assertions = run_behavior_assertions(project)
    charter = charter_snapshot(project)
    ranking = ranking_snapshot(project)
    payload = {**routing, "snapshots": snapshots, "assertions": assertions,
               "charter": charter, "ranking": ranking}
    # A mode-differing ranking comparison is out of contract, not a failure:
    # the snapshot and this environment hold different instruments, and
    # neither is wrong about the other.
    gates = {
        "routing": routing["verdict"] == "routing-sound",
        "snapshots": snapshots["verdict"] == "behaviour-stable",
        "assertions": assertions["verdict"] == "assertions-held",
        "charter": charter["verdict"] == "charter-stable",
        "ranking": ranking["verdict"] in ("ranking-stable", "ranking-mode-differs"),
    }
    failing = sorted(name for name, held in gates.items() if not held)
    # The headline names what failed. The old spread left routing's own
    # verdict as the top-level one, so --brief printed "routing-sound"
    # while the command exited 1 on a different gate entirely (field
    # report, 2026-08-31).
    payload["routing_verdict"] = routing["verdict"]
    payload["verdict"] = (
        "evals-sound" if not failing
        else "evals-unsound: " + ", ".join(
            f"{name}={payload[name]['verdict'] if name != 'routing' else routing['verdict']}"
            for name in failing)
    )
    return CommandResult(payload, exit_code=0 if not failing else 1)


def cmd_grid(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = adversarial_grid()
    return CommandResult(report, exit_code=0 if report["verdict"] == "controls-held" else 1)


def cmd_netgate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    report = netgate_differential(Path(runtime.anchor.project_root))
    return CommandResult(report, exit_code=0 if report["clean"] else 1)


def cmd_absorb(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    result = absorption_check(runtime.archive, args.path)
    return CommandResult(result, exit_code=0 if result["absorbed"] else 1)


def cmd_parity(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    if getattr(args, "matrix", False):
        result = parity_matrix(
            runtime.anchor.project_root, args.reference,
            archive=runtime.archive if getattr(args, "archive", False) else None,
        )
        runtime.archive.append(
            "decision", "parity-matrix-observation",
            {"aligned": result["aligned"],
             "staleness": result.get("reference_staleness"),
             "verdicts": {name: dim["verdict"] for name, dim in result["dimensions"].items()},
             "status": "observed"},
            evidence=[],
        )
        return CommandResult(result)
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


def cmd_skill_lifecycle(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """S27-01: every skill carries a lifecycle state; stale ones are retired with
    a reason, not left to accumulate."""
    project = Path(runtime.anchor.project_root)
    skills = []
    for evals in sorted(project.glob("skills/*/godmode-evals.json")):
        payload = json.loads(evals.read_text(encoding="utf-8"))
        skills.append({
            "skill": evals.parent.name,
            "lifecycle": payload.get("lifecycle", "active"),
            "reason": payload.get("lifecycle_reason", ""),
        })
    return CommandResult({"skills": skills, "states": ["in-progress", "active", "deprecated"]})


def cmd_skill_retire(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    project = Path(runtime.anchor.project_root)
    evals = project / "skills" / args.name / "godmode-evals.json"
    if not evals.is_file():
        raise ArchiveError(f"No skill '{args.name}' with a godmode-evals.json")
    payload = json.loads(evals.read_text(encoding="utf-8"))
    payload["lifecycle"] = "deprecated"
    payload["lifecycle_reason"] = args.reason
    evals.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _append(runtime, "decision", f"skill-retired:{args.name}",
            {"value": args.reason, "status": "deprecated"}, [f"file:skills/{args.name}"])
    return CommandResult({"skill": args.name, "lifecycle": "deprecated", "reason": args.reason})


def cmd_lessons(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """Bare `lessons` runs the promote-or-retire pipeline, unchanged. B4-7
    adds the flat ledger beside it: `add` writes one typed lesson record
    into the chronicle (no daemon, no database - the sweep source's shape
    reduced to a record and a renderer), `list` reads them back bounded."""
    _require_archive(runtime)
    command = getattr(args, "lessons_command", None)
    if command == "add":
        record = runtime.archive.append(
            "lesson", args.subject,
            {"status": args.status, "generalized_guard": args.guard},
            evidence=[],
        )
        return CommandResult({"record": {
            "sequence": record["sequence"], "subject": args.subject,
            "status": args.status,
        }})
    if command == "list":
        rows = [
            {
                "sequence": record["sequence"],
                "subject": record["subject"],
                "status": str((record.get("data") or {}).get("status", "")),
                "generalized_guard": str(
                    (record.get("data") or {}).get("generalized_guard", "")),
            }
            for record in runtime.archive.select(
                kind="lesson", limit=max(1, args.limit))
        ]
        return CommandResult({"lessons": rows})
    from .godmode_attest import lesson_pipeline

    report = lesson_pipeline(runtime.archive)
    return CommandResult(report, exit_code=0)


def cmd_experiment_run(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_guardrails import run_experiment

    report = run_experiment(
        runtime.archive, Path(runtime.anchor.project_root), budget_s=args.budget_s
    )
    return CommandResult(report, exit_code=0 if report["succeeded"] else 1)


def cmd_experiment_holdout(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # Two arms, one metric, a verdict computed from medians. `underpowered`
    # and `indistinguishable` are findings - the operator asked whether the
    # change moved the metric, and "cannot tell" must not exit as "yes".
    _require_archive(runtime)
    from .godmode_holdout import record_holdout
    try:
        record = record_holdout(
            runtime.archive, Path(runtime.anchor.project_root),
            name=args.name, metric=args.metric, control=args.control,
            treatment=args.treatment, epsilon=args.epsilon,
            lower_is_better=args.lower_is_better)
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=1)
    data = dict(record["data"])
    data["sequence"] = record["sequence"]
    return CommandResult(data, exit_code=0 if data["verdict"] in ("treatment", "control") else 1)


def cmd_experiment_verdict(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """U-R3: adjudicate one experiment cycle - keep/discard/keep-simpler,
    computed from {metric, before, after, epsilon}, commit-linked."""
    _require_archive(runtime)
    from .godmode_guardrails import record_experiment_verdict

    record = record_experiment_verdict(
        runtime.archive,
        Path(runtime.anchor.project_root),
        metric=args.metric,
        before=args.before,
        after=args.after,
        epsilon=args.epsilon,
        cycle_seq=args.cycle_seq,
        simpler=args.simpler,
        acquitted_by=args.acquitted_by,
    )
    data = record["data"]
    return CommandResult(
        {"sequence": record["sequence"], "cycle_seq": data["cycle_seq"],
         "adjudication": data["adjudication"], "improvement": data["improvement"],
         "commit": data["commit"], "run_state": data["run_state"]},
        exit_code=0 if data["adjudication"] in ("keep", "keep-simpler") else 1,
    )


def cmd_skill_validate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(validate_skill(args.path))


def cmd_skill_lint(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_forge import lint_skill
    report = lint_skill(args.path)
    return CommandResult(report, exit_code=0 if report["passed"] else 1)


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
    # CX-3 (Addendum 6's roster-gap fix): Grok's own skill roster looks under
    # `.grok/skills/`, distinct from the project-root `skills/` every other
    # host shares - an explicit `--destination` always wins; only the
    # DEFAULT differs by host.
    destination = args.destination
    if destination is None:
        project_root = Path(runtime.anchor.project_root)
        if current_host() == "grok":
            destination = str(project_root / ".grok" / "skills")
        else:
            destination = str(project_root / "skills")
    created = forge_skill(destination, proposal)
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


# Printed directly by main(), never routed through CommandResult/JSON: a
# static orientation page is prose for a terminal, not data for a caller,
# and JSON-wrapping a multi-line string turns every newline into an
# escaped \n that no one reads comfortably. No runtime/archive needed
# either - unlike every other command here, this one names nothing about
# THIS project.
def _guide_text() -> str:
    """The day-one page, host-aware (Grok 0.3.4 field report: the old
    'runs without asking' line was Claude-shaped and misleading on a host
    with no ask decision, where a recoverable R2/R3 becomes a hard deny)."""
    from .godmode_anchor import current_host
    from .godmode_hostevent import HOSTS_WITH_ASK

    host = current_host()
    if host in HOSTS_WITH_ASK or host == "unknown":
        middle = (
            "WHAT RUNS WITHOUT ASKING     reads, edits, commits - tier R0-R2\n"
            "WHAT ASKS FIRST              push, deploy, db migrations - your "
            "host shows a dialog")
    else:
        middle = (
            f"THIS HOST ({host}) HAS NO ASK  a recoverable refusal (R2/R3) is "
            "DENIED, not asked -\n"
            "                             the refusal names `godmode authorize "
            "stage` as the remedy\n"
            "WHAT RUNS FREELY             reads and allow-tier work; unknown "
            "mutating tools deny")
    return f"""\
GODMODE IN FIVE COMMANDS

  godmode init             start the private local archive for this project
  godmode resume           rebuild what is true now from recorded evidence
  godmode status           the single writable status store
  godmode doctor           health-check the installation and archive
  godmode authorize setup  one-time password for IRREVERSIBLE operations

{middle}
WHAT NEEDS THE PASSWORD      irreversible forms only (force-push, rm -rf on a
                             root, DROP TABLE): the refusal names the exact
                             staging command; in a hosted session run it with a
                             leading '!' from the prompt.

WHERE THINGS LIVE            state under the git metadata dir - never in your
                             tracked files; nothing leaves the machine.

YOUR FIRST WEEK              day one is the gate, doctor, and resume; the
                             loops (laws, roi digest, debrief) fill as the
                             record grows and read honestly empty before that.

MORE                         README.md (concepts) - godmode <cmd> --help (any
                             command) - godmode capabilities (what is enforced
                             on this host)
"""


class _GuideText:
    """Lazy stand-in so every existing GUIDE_TEXT print site stays valid
    while the text itself is computed per host at print time."""

    def __str__(self) -> str:
        return _guide_text()


GUIDE_TEXT = _GuideText()

# S12-A (the listing risk, Grok field report): bare `godmode` used to print
# the argparse firehose - a hundred verbs as the first impression. The
# day-one face names the eight that matter on day one; everything else sits
# behind `--all`, whose listing is GENERATED from the registered subparsers
# so it can never drift from the real CLI.
_DAY_ONE_VERBS = (
    ("init", "start the private local archive for this project"),
    ("resume", "rebuild what is true now from recorded evidence"),
    ("status", "the single writable status store"),
    ("doctor", "health-check the installation and archive"),
    ("forecast", "classify a risky operation before it runs"),
    ("checkpoint", "record a recoverable state with next actions"),
    ("capabilities", "what is actually enforced on this host"),
    ("guide", "the one-page orientation; --tier N for the ladder"),
)


def _subparser_action(parser: argparse.ArgumentParser):
    return next(a for a in parser._actions
                if isinstance(a, argparse._SubParsersAction))


def _day_one_text(parser: argparse.ArgumentParser) -> str:
    from .godmode_anchor import current_host
    from .godmode_hostevent import HOSTS_WITH_ASK

    total = len(_subparser_action(parser).choices)
    host = current_host()
    if host in HOSTS_WITH_ASK or host == "unknown":
        posture = ("risky operations ask first; irreversible ones need the "
                   "one-time password")
    else:
        posture = (f"this host ({host}) has no ask: a recoverable refusal is "
                   "denied and names `godmode authorize stage` as the remedy")
    lines = ["GODMODE - DAY ONE", ""]
    for name, blurb in _DAY_ONE_VERBS:
        lines.append(f"  godmode {name:<13} {blurb}")
    lines += [
        "",
        f"  {posture}",
        "",
        f"  {total - len(_DAY_ONE_VERBS)} more verbs: `godmode --all` lists "
        "every one; `godmode guide --tier 2`",
        "  climbs the ladder when the first eight feel small.",
        "",
    ]
    return "\n".join(lines)


def _all_verbs_text(parser: argparse.ArgumentParser) -> str:
    action = _subparser_action(parser)
    helps = {ca.dest: (ca.help or "") for ca in action._choices_actions}
    lines = ["GODMODE - EVERY VERB", ""]
    for name in sorted(action.choices):
        blurb = helps.get(name, "")
        entry = f"  {name:<18} {blurb}"
        lines.append(entry[:100])
    lines += ["", "  `godmode <verb> --help` documents any of them.", ""]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="godmode",
        description="A local, tamper-evident record of what a coding agent did, "
                    "what it claimed, and what was verified.",
        epilog="Start here: godmode guide  |  day one: init, resume, status, doctor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", default=".", help="Project directory (default: current directory)")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON")
    parser.add_argument("--brief", action="store_true",
                        help="Emit one human-readable line instead of JSON")
    parser.add_argument("--terse", action="store_true",
                        help="Action first: the next step on line one, then one line "
                             "per finding, then the brief line")
    parser.add_argument("--version", action="version", version=f"Godmode {RUNTIME_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    guide_parser = sub.add_parser(
        "guide",
        help="One-page orientation: what godmode does, the five day-one commands, "
             "and when the password matters")
    guide_parser.add_argument(
        "--tier", type=int, choices=(1, 2, 3, 4),
        help="C-61: print one tier of docs/LADDER.md instead of the orientation page")

    init_parser = sub.add_parser("init", help="Initialize the private local archive")
    init_parser.add_argument("--roles", action="store_true",
                             help="Also scaffold a stub for every genuinely unbound "
                                  "authority role (never overwrites an existing file)")
    init_parser.add_argument("--detect", action="store_true",
                             help="Propose a starter charter from repo evidence (SOFT only, never overwrites)")
    init_parser.add_argument("--profile", choices=PROFILE_NAMES,
                             help="Set a STARTING posture on the tighten-only authorization ratchet "
                                  "(novice=ask-heavy, standard=today's defaults/no-op, strict=full "
                                  "enforcement); never loosens a policy value already on record")
    init_parser.set_defaults(handler=cmd_init)
    adopt = sub.add_parser("adopt", help="Relink records stranded by an identity change (e.g. git init)")
    adopt.add_argument("--source", help="Archive root to adopt; defaults to the detected one")
    adopt.add_argument("--confirm", action="store_true", help="Perform the relink, not just preview it")
    adopt.add_argument(
        "--from-docs", action="store_true",
        help="Seed a late install: counts-only adoption records citing each "
             "bound authority document")
    adopt.set_defaults(handler=cmd_adopt)
    roles = sub.add_parser("roles", help="Resolve authority documents by role")
    roles.add_argument("--check", action="store_true", help="Exit non-zero when two roles claim one path")
    roles.set_defaults(handler=cmd_roles)
    brief = sub.add_parser("brief", help="Assemble a bounded, model-independent context brief")
    brief.add_argument("task", help="What this session is about; drives relevance ranking")
    brief.add_argument("--token-budget", type=int, default=DEFAULT_CONTEXT_BUDGET)
    brief.add_argument("--full", action="store_true", help="Include segment bodies, not just the map")
    brief.add_argument("--measure", action="store_true",
                       help="B4-2: bytes + estimated tokens per brief section, "
                            "counts only - no bodies")
    brief.set_defaults(handler=cmd_brief)

    charter = sub.add_parser("charter", help="Compile prose guidance into addressable rules")
    charter.add_argument("--full", action="store_true", help="Include every compiled rule")
    charter.add_argument("--at", metavar="PATH",
                         help="Narrow to the rules that apply to this artefact's characteristics")
    charter.add_argument("--decay", type=int, metavar="N", nargs="?", const=10,
                         help="Surface rules no attestation touched in the last N sessions")
    charter.add_argument("--bootstrap", action="store_true",
                         help="Mine candidate invariants from the project's commit history")
    charter.add_argument("--review-advisory", metavar="RULE_ID",
                         help="Record why an ADVISORY rule stays unenforced (requires --reason)")
    charter.add_argument("--reason", help="The reason text for --review-advisory")

    operator = sub.add_parser("operator", help="Validate the typed operator profile")
    operator.set_defaults(handler=cmd_operator)

    lessons = sub.add_parser("lessons", help="The promote-or-retire pipeline over recorded lessons")
    lessons.set_defaults(handler=cmd_lessons)
    lessons_sub = lessons.add_subparsers(dest="lessons_command")
    lessons_add = lessons_sub.add_parser(
        "add", help="B4-7: record one lesson into the flat ledger")
    lessons_add.add_argument("subject", help="What failed, in one line")
    lessons_add.add_argument("--guard", required=True,
                             help="The rule that prevents its recurrence")
    lessons_add.add_argument("--status", default="open")
    lessons_add.set_defaults(handler=cmd_lessons)
    lessons_list = lessons_sub.add_parser(
        "list", help="B4-7: the recorded lessons, newest last, bounded")
    lessons_list.add_argument("--limit", type=int, default=20)
    lessons_list.set_defaults(handler=cmd_lessons)

    experiment = sub.add_parser(
        "experiment",
        help="The declarative bounded experiment loop from .godmode-experiment.json, "
             "cycle-ledgered with epsilon adjudication (U-R3)",
    )
    experiment_sub = experiment.add_subparsers(dest="experiment_command", required=True)
    experiment_run = experiment_sub.add_parser(
        "run", help="Run one experiment cycle"
    )
    experiment_run.add_argument("--budget-s", type=float, default=None, dest="budget_s",
                                help="U-R1 wall-time budget over this cycle's attempts; overrun "
                                     "truncates early and records run_state=truncated")
    experiment_run.set_defaults(handler=cmd_experiment_run)
    experiment_holdout = experiment_sub.add_parser(
        "holdout",
        help="Two arms, one metric: does the treatment differ from the control by "
             "more than --epsilon? Medians; two observations per arm or `underpowered`")
    experiment_holdout.add_argument("--name", required=True)
    experiment_holdout.add_argument("--metric", required=True)
    experiment_holdout.add_argument("--control", type=float, action="append", default=[],
                                    help="An observation with the change OFF; repeatable")
    experiment_holdout.add_argument("--treatment", type=float, action="append", default=[],
                                    help="An observation with the change ON; repeatable")
    experiment_holdout.add_argument("--epsilon", type=float, required=True)
    experiment_holdout.add_argument("--lower-is-better", action="store_true", dest="lower_is_better")
    experiment_holdout.set_defaults(handler=cmd_experiment_holdout)
    experiment_verdict = experiment_sub.add_parser(
        "verdict",
        help="Adjudicate an experiment cycle: keep/discard/keep-simpler, computed "
             "from --metric/--before/--after/--epsilon, commit-linked",
    )
    experiment_verdict.add_argument("--metric", required=True, help="Name of the measured metric")
    experiment_verdict.add_argument("--before", type=float, required=True)
    experiment_verdict.add_argument("--after", type=float, required=True)
    experiment_verdict.add_argument("--epsilon", type=float, required=True,
                                    help="improvement >= epsilon keeps; short of that discards "
                                         "(a flat, equal result with --simpler is the one exception)")
    experiment_verdict.add_argument("--cycle", type=int, default=None, dest="cycle_seq",
                                    help="seq of the cycle to adjudicate; defaults to the latest recorded cycle")
    experiment_verdict.add_argument("--simpler", action="store_true",
                                    help="Declare the change simpler despite a flat (equal) measurement")
    experiment_verdict.add_argument("--acquitted-by", choices=("independent", "self"), default="self",
                                    help="'self' (default) never grades 'confirmed' (U-V1 drive-vs-acquit); "
                                         "'independent' does, and is held to the same archive-seam rules")
    experiment_verdict.set_defaults(handler=cmd_experiment_verdict)

    config = sub.add_parser("config", help="Validate every .godmode-*.json config file")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("check").set_defaults(handler=cmd_config_check)
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

    plant = sub.add_parser("plant", help="Prove a guard fails by planting a violation")
    plant.add_argument("name")
    plant.add_argument("--command", required=True, help="Guard command, as one quoted string")
    plant.add_argument("--file", required=True, help="File to break, relative to the project")
    plant.add_argument("--replace", help="Text to replace in that file")
    plant.add_argument("--with", dest="with_text", default="", help="Replacement text")
    plant.add_argument("--append", help="Line to append instead of replacing")
    plant.add_argument("--rule", action="append", default=[])
    plant.add_argument("--session")
    plant.set_defaults(handler=cmd_plant)

    gate_parser = sub.add_parser("gate", help="Check a trigger; exit non-zero when a HARD rule is unattested")
    gate_parser.add_argument("--trigger", choices=list(TRIGGERS), required=True)
    gate_parser.add_argument("--session")
    gate_parser.add_argument("--transcript",
                             help="This session's transcript path; enables the U-S4 "
                                  "assumption-gate advisory on --trigger before_approach")
    gate_parser.set_defaults(handler=cmd_gate)

    claim = sub.add_parser(
        "claim",
        help="Record a claim; unsupported claims are downgraded, not warned about",
        epilog=(
            "Citation prefixes --cite accepts (repeatable):\n"
            "  rec:<hash>            an archive record, cited by its hash prefix\n"
            "  file:<path>#L<n>      a line this session actually read\n"
            "  cmd:<command>         a command an attestation on THIS session ran\n"
            "  verdict:<seq>         a CONFIRMED verdict record (U-V1) - refuted or\n"
            "                        malformed does not resolve\n"
            "  diff:<seq>            a differential record (U-E3) whose own a_ref/\n"
            "                        b_ref also resolve - what a root-cause claim\n"
            "                        needs once the archive holds two comparable\n"
            "                        states to diff\n"
            "  line:<name>:<value>   an output line matching a registered metric's\n"
            "                        own anchor (U-T3, `metric-contract register`)\n"
            "  doc:<ref> / url:<ref> a source outside the worktree (declared, not\n"
            "                        locally verifiable - required for --external)\n"
            "  searched:<query>      the sweep behind an absence or a count claim\n"
            "  scanned:<extent>      what a population statement covered\n"
            "  population:<n>       the denominator behind a rate\n"
            "  control:<probe>      the same instrument finding a known-present\n"
            "                        target - proves the search mechanism can find,\n"
            "                        not just that it found nothing this time\n"
            "  second:<method>      an independent second proof of an absence\n"
            "\n"
            "searched:/scanned:/population:/control:/second: resolve as a declared\n"
            "citation (same as doc:/url: - nothing local can mechanically confirm a\n"
            "search was exhaustive) and satisfy `godmode mistakes`' M18/M19/M21\n"
            "detectors. They are a SEPARATE, lighter check from the grading pipeline's\n"
            "own absence-claim gate below: a --grade verified absence claim still\n"
            "needs TWO DISTINCT cmd: citations (or one that positively enumerated\n"
            "something) to avoid being downgraded to hypothesis - a single miss is\n"
            "evidence about where you looked, not about what exists.\n"
            "\n"
            "Example:\n"
            "  godmode claim \"no dead refs in lib/\" --grade verified \\\n"
            "    --cite file:lib/gate.py#L40 \\\n"
            "    --cite \"searched:rg dead_ref lib/ -> 0 hits\" \\\n"
            "    --cite \"control:rg live_ref lib/ -> 14 hits\""
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    claim.add_argument("text", nargs="?", default=None)
    # Field report 2026-09-01: an agent typed `claim --text ...`, got an
    # argparse rejection, and burned a retry. The flag is accepted as an
    # alias for the positional - one meaning, two spellings, because the
    # sibling verbs (checkpoint --summary) taught flag-shaped muscle memory.
    claim.add_argument("--text", dest="text_flag", default=None,
                       help="Alias for the positional claim text")
    claim.add_argument("--scan", action="store_true",
                       help="Instead of recording: list every claim-shaped sentence on "
                            "the public surfaces (README, LISTING, coverage map, llms.txt, "
                            "GODMODE.md) whose line names no reproduction and no claim "
                            "record carries")
    claim.add_argument("--grade", choices=list(GRADES), default="observed")
    claim.add_argument("--confidence", type=float, default=None,
                       help="How sure, 0..1; scored against the outcome when the claim is later resolved")
    claim.add_argument("--resolve", type=int, default=None, metavar="SEQ",
                       help="Close the claim at SEQ with --outcome and evidence; a claim resolves at most once")
    claim.add_argument("--outcome", choices=list(RESOLUTION_OUTCOMES), default=None,
                       help="With --resolve: held (the claim survived the check) or failed")
    claim.add_argument("--cite", action="append", default=[], help="rec:<hash> or file:<path>#L<n>; repeatable")
    claim.add_argument("--external", action="store_true",
                       help="Claim about an external API/library; requires a doc:/url: primary source")
    claim.add_argument("--transcript",
                       help="This session's transcript path; enables the U-T2 red-before-green "
                            "check on a fix claim citing cmd:<command>")
    claim.add_argument("--blast-radius", dest="blast_radius", choices=list(BLAST_RADIUS_KINDS),
                       help="PARTIAL-P2: opt in to the scaled evidence bar - a 'verified' grade "
                            "then needs >=2 INDEPENDENT --cite witnesses (distinct citation "
                            "kinds or distinct resolved artifacts), not just >=1 that resolves")
    claim.add_argument("--session")
    claim.set_defaults(handler=cmd_claim)

    criterion = sub.add_parser(
        "criterion",
        help="Record what passing looks like, before the work it judges (E4)",
    )
    criterion.add_argument("--task", required=True, type=subject_text,
                           help="Slug identifying the work this criterion judges")
    criterion.add_argument("text")
    criterion.add_argument("--cite", action="append", default=[],
                           help="cmd:<command> the criterion will be judged by; repeatable")
    criterion.add_argument("--transcript",
                           help="This session's transcript path; enables the ordering check "
                                "(a criterion recorded after work has started)")
    criterion.add_argument("--session")
    criterion.set_defaults(handler=cmd_criterion)

    # U-T3 anchored-metric contracts - minimal isolated block, mirrors the
    # `register` block below.
    metric_contract = sub.add_parser(
        "metric-contract",
        help="Anchored-metric citation contracts: a numeric claim must cite "
             "the registered line shape (U-T3)",
    )
    metric_contract_sub = metric_contract.add_subparsers(
        dest="metric_contract_command", required=True)
    metric_contract_register = metric_contract_sub.add_parser(
        "register", help="Declare the anchor a claim about this metric must cite")
    metric_contract_register.add_argument("--name", required=True, type=subject_text)
    metric_contract_register.add_argument(
        "--anchor", required=True,
        help="Regex the cited line:<name>:<value> evidence must match")
    metric_contract_register.add_argument("--session")
    metric_contract_register.set_defaults(handler=cmd_metric_contract_register)

    # PARTIAL-P3/B3-7 declared tool error-severity patterns - minimal
    # isolated block, mirrors the `metric-contract` block just above.
    error_pattern = sub.add_parser(
        "error-pattern",
        help="Declare a third-party tool's error-severity vocabulary; "
             "gates 'verdict record --checker' confirming past it unacknowledged",
    )
    error_pattern_sub = error_pattern.add_subparsers(
        dest="error_pattern_command", required=True)
    error_pattern_register = error_pattern_sub.add_parser(
        "register", help="Declare the tool + pattern a checker's own output is matched against")
    error_pattern_register.add_argument("--tool", required=True,
                                        help="Name as it appears in the checker command, e.g. pytest")
    error_pattern_register.add_argument(
        "--pattern", required=True,
        help="Regex matched against the checker's own captured stdout+stderr")
    error_pattern_register.add_argument("--session")
    error_pattern_register.set_defaults(handler=cmd_error_pattern_register)

    # U-E3 differential-evidence - minimal isolated block, mirrors the
    # `register` block below.
    differential = sub.add_parser(
        "differential",
        help="Record a comparison of two archived states; a root-cause claim "
             "cites it (U-E3)",
    )
    differential_sub = differential.add_subparsers(dest="differential_command", required=True)
    differential_record = differential_sub.add_parser(
        "record", help="Record the comparison")
    differential_record.add_argument("--subject", required=True, type=subject_text)
    differential_record.add_argument(
        "--a", dest="a", required=True, help="seq:<n>, file:<path>, or cmd:<...>")
    differential_record.add_argument(
        "--b", dest="b", required=True, help="seq:<n>, file:<path>, or cmd:<...>")
    differential_record.add_argument(
        "--delta", action="append", default=[],
        help="One observed difference; repeatable, up to 20 entries")
    differential_record.add_argument(
        "--method", required=True, help="cmd:<command run to compare> or 'read'")
    differential_record.set_defaults(handler=cmd_differential_record)

    verdict = sub.add_parser(
        "verdict",
        help="Run an independent checker against a witness; the claim's admissibility",
    )
    verdict_sub = verdict.add_subparsers(dest="verdict_command", required=True)
    verdict_record = verdict_sub.add_parser(
        "record",
        help="Run the checker panel and store confirmed/refuted/contested/witness-malformed",
    )
    verdict_record.add_argument("--claim", required=True)
    verdict_record.add_argument("--value", required=True, help="The claimed value the checker verifies")
    verdict_record.add_argument("--witness", required=True, help="file:<path> or seq:<n>")
    verdict_record.add_argument("--checker", required=True, action="append",
                                help="Checker command, as one quoted string; runs against the witness "
                                     "alone. Repeatable - each --checker is one independent panel "
                                     "member; N checkers fold to one disposition (U-E4).")
    verdict_record.add_argument("--run-state", choices=list(("terminated", "truncated")), default="terminated")
    verdict_record.add_argument("--acquitted-by", choices=list(("independent", "self")), default="independent")
    verdict_record.add_argument("--timeout", type=int, default=300)
    verdict_record.add_argument(
        "--tool-error-ack", dest="tool_error_ack", default="",
        help="PARTIAL-P3: required for 'confirmed' when a checker's own output "
             "matched a declared error-pattern (see 'error-pattern register') - "
             "'acknowledged-remediated' or 'acknowledged-deferred: <reason>'")
    verdict_record.set_defaults(handler=cmd_verdict_record)
    verdict_show = verdict_sub.add_parser("show", help="Read back a verdict record by sequence")
    verdict_show.add_argument("--seq", type=int, required=True)
    verdict_show.set_defaults(handler=cmd_verdict_show)

    # B5 fleet governance - minimal isolated block, mirrors the `register`
    # block below. MAX_TTL is enforced in the module, not here, so a caller
    # reaching the function directly gets the same bound as the CLI.
    fleet = sub.add_parser(
        "fleet",
        help="Many-agent governance: identity, leases, delegation provenance",
    )
    fleet_sub = fleet.add_subparsers(dest="fleet_command", required=True)
    fleet_show = fleet_sub.add_parser(
        "show", help="Agents, live leases and the delegation DAG")
    fleet_show.set_defaults(handler=cmd_fleet_show)
    fleet_lease = fleet_sub.add_parser(
        "lease", help="Take an exclusive lease on a resource; refuses if held")
    fleet_lease.add_argument("--resource", required=True)
    fleet_lease.add_argument("--ttl", type=float, default=1800.0,
                             help="Lease term in seconds (default 1800)")
    fleet_lease.add_argument("--holder", default=None,
                             help="Defaults to this agent's own id")
    fleet_lease.set_defaults(handler=cmd_fleet_lease)
    fleet_release = fleet_sub.add_parser(
        "release", help="Give up a lease; only the holder may")
    fleet_release.add_argument("--resource", required=True)
    fleet_release.add_argument("--holder", default=None)
    fleet_release.set_defaults(handler=cmd_fleet_release)
    fleet_delegate = fleet_sub.add_parser(
        "delegate", help="Record a dispatch; refuses a cycle")
    fleet_delegate.add_argument("--child", required=True)
    fleet_delegate.add_argument("--task", default="")
    fleet_delegate.add_argument("--parent", default=None,
                                help="Defaults to this agent's own id")
    fleet_delegate.set_defaults(handler=cmd_fleet_delegate)
    fleet_retract = fleet_sub.add_parser(
        "retract", help="Close a delegation edge; only the parent that opened it may")
    fleet_retract.add_argument("--child", required=True)
    fleet_retract.add_argument("--parent", default=None,
                               help="Defaults to this agent's own id")
    fleet_retract.set_defaults(handler=cmd_fleet_retract)

    # Sprint 8 - the review surface. `show` reads, `promote` is the only
    # path by which anything here becomes binding, and it needs a person.
    governance = sub.add_parser(
        "governance",
        help="Rules this project's own record argues for; proposals only")
    governance_sub = governance.add_subparsers(
        dest="governance_command", required=True)
    governance_show = governance_sub.add_parser(
        "show", help="The current review surface, with provenance per candidate")
    governance_show.set_defaults(handler=cmd_governance_show)
    governance_promote = governance_sub.add_parser(
        "promote", help="Adopt a reviewed candidate; requires a reason")
    governance_promote.add_argument("--candidate", required=True)
    governance_promote.add_argument("--reason", required=True,
                                    help="Who reviewed it, and why")
    governance_promote.set_defaults(handler=cmd_governance_promote)

    # Sprint 9 - what each host approved, beside what godmode decided.
    approvals = sub.add_parser(
        "approvals",
        help="Host approval decisions recorded beside godmode's own, and where they differ")
    approvals.add_argument("--all", action="store_true",
                           help="Include every recorded pair, not only the divergences")
    approvals.set_defaults(handler=cmd_host_approvals)

    # B5-B / B6 - three read-only reports and one attestation.
    reanchor = sub.add_parser(
        "reanchor",
        help="Citations that came loose: cited files changed since, commits gone")
    reanchor.add_argument(
        "--snapshot", action="store_true",
        help="Fingerprint every cited commit BEFORE a history rewrite")
    reanchor.add_argument(
        "--remap", action="store_true",
        help="After a rewrite, find each snapshotted commit's new sha")
    reanchor.set_defaults(handler=cmd_reanchor)

    rollback = sub.add_parser(
        "rollback", help="Restore points proven green, and what it takes to reach one")
    rollback_sub = rollback.add_subparsers(dest="rollback_command", required=True)
    rollback_mark = rollback_sub.add_parser(
        "mark", help="Attest that a command passed at the current commit")
    rollback_mark.add_argument("--command", required=True,
                               help="The command that proved it")
    rollback_mark.add_argument("--exit-code", type=int, required=True,
                               dest="exit_code",
                               help="Its exit code; non-zero is refused")
    rollback_mark.set_defaults(handler=cmd_rollback_mark)
    rollback_show = rollback_sub.add_parser(
        "plan", help="The last green, what changed since, and how to return")
    rollback_show.set_defaults(handler=cmd_rollback_plan)

    quality_parser = sub.add_parser(
        "quality",
        help="Every quality finding - docs, swallowed errors, minimality - "
             "worst first, with a proposed remedy each; executes nothing")
    quality_parser.add_argument(
        "--format", choices=("json", "editor", "sarif"), default="json",
        help="editor: one `path:line: severity: message` per line; "
             "sarif: a SARIF 2.1.0 document")
    quality_parser.set_defaults(handler=cmd_quality)

    examples_parser = sub.add_parser(
        "examples",
        help="The worked-example corpus; --check reproduces every example "
             "against the real console in a throwaway project")
    examples_parser.add_argument("--check", action="store_true")
    examples_parser.add_argument("--corpus", help="Directory of *.example.json (default: the plugin's)")
    examples_parser.set_defaults(handler=cmd_examples)

    freshness_parser = sub.add_parser(
        "freshness",
        help="Are the sources standing records cite still what was graded? "
             "file: and commit: are checked; url: is reported unverifiable, never fresh")
    freshness_parser.set_defaults(handler=cmd_freshness)

    watchdog_parser = sub.add_parser(
        "watchdog",
        help="Anomalies in the newest window of this project's record - repeated "
             "operations, refusal bursts, unattested runs; on demand, no daemon")
    watchdog_parser.add_argument(
        "--interrupt", action="store_true",
        help="On anomaly, write the operator-stop flag the stop algebra honours")
    watchdog_parser.set_defaults(handler=cmd_watchdog)

    arbitrate_parser = sub.add_parser(
        "arbitrate",
        help="Score competing plan files on what a plan can be held to; a tie is "
             "undecided, never broken silently")
    arbitrate_parser.add_argument("--plan", action="append", required=True,
                                  help="A plan file; repeat for each competitor")
    arbitrate_parser.set_defaults(handler=cmd_arbitrate)

    extensions_parser = sub.add_parser(
        "extensions",
        help="Extensions under the private state home; run one only when the "
             "project's policy names it")
    extensions_sub = extensions_parser.add_subparsers(dest="extensions_command")
    extensions_list = extensions_sub.add_parser("list", help="Manifests only; imports nothing")
    extensions_list.set_defaults(handler=cmd_extensions_list)
    extensions_run = extensions_sub.add_parser(
        "run", help="Import and run one policy-named extension")
    extensions_run.add_argument("name")
    extensions_run.add_argument("argv", nargs=argparse.REMAINDER,
                                help="Arguments handed to the extension, after --")
    extensions_run.set_defaults(handler=cmd_extensions_run)
    extensions_parser.set_defaults(handler=cmd_extensions_list)

    forecast_parser = sub.add_parser(
        "forecast", help="What an operation would classify as, plus prior precedent")
    forecast_parser.add_argument("--operation", required=True)
    forecast_parser.set_defaults(handler=cmd_forecast)

    replay_parser = sub.add_parser(
        "replay",
        help="Re-classify recorded operations under today's rules; exits 1 on a relaxation")
    replay_parser.set_defaults(handler=cmd_replay)

    # U-V2 disposition register - minimal isolated block, mirrors the
    # `verdict` block above.
    register = sub.add_parser(
        "register",
        help="Closed-enumeration disposition register, derived from decision records",
    )
    register_sub = register.add_subparsers(dest="register_command", required=True)
    register_set = register_sub.add_parser(
        "set", help="First disposition for a key, from 'open'; no --supersedes")
    register_set.add_argument("--domain", required=True)
    register_set.add_argument("--key", required=True)
    register_set.add_argument("--state", choices=list(REGISTER_STATES), required=True)
    register_set.add_argument("--evidence", action="append", default=[],
                              help="witness:/verdict:/file: citation; repeatable, "
                                   "required unless --state open")
    register_set.add_argument("--delta", choices=list(REGISTER_DELTAS), default=None)
    register_set.set_defaults(handler=cmd_register_set, supersedes=None)
    register_supersede = register_sub.add_parser(
        "supersede",
        help="Leave a closed disposition; --supersedes must name the record it replaces")
    register_supersede.add_argument("--domain", required=True)
    register_supersede.add_argument("--key", required=True)
    register_supersede.add_argument("--state", choices=list(REGISTER_STATES), required=True)
    register_supersede.add_argument("--evidence", action="append", default=[],
                                    help="witness:/verdict:/file: citation; repeatable")
    register_supersede.add_argument("--delta", choices=list(REGISTER_DELTAS), default=None)
    register_supersede.add_argument("--supersedes", type=int, required=True)
    register_supersede.set_defaults(handler=cmd_register_set)
    register_show = register_sub.add_parser("show", help="Read the derived view, or one key's entry")
    register_show.add_argument("--domain", required=True)
    register_show.add_argument("--key", default=None)
    register_show.set_defaults(handler=cmd_register_show)

    # U-E2 cross-project precedent exchange - minimal, isolated block, same
    # convention as the register block directly above.
    precedent = sub.add_parser(
        "precedent",
        help="Cross-project precedent exchange: file-carried, advisory-foreign",
    )
    precedent_sub = precedent.add_subparsers(dest="precedent_command", required=True)
    precedent_export = precedent_sub.add_parser(
        "export", help="Write this project's register entries for one domain to a file")
    precedent_export.add_argument("--domain", required=True)
    precedent_export.add_argument("--out", required=True, help="Path to write the export file")
    precedent_export.set_defaults(handler=cmd_precedent_export)
    precedent_import = precedent_sub.add_parser(
        "import", help="Verify and append another project's exported precedents, as foreign/advisory")
    precedent_import.add_argument("file", help="Path to a file written by `precedent export`")
    precedent_import.set_defaults(handler=cmd_precedent_import)
    precedent_adopt = precedent_sub.add_parser(
        "adopt", help="Promote one imported foreign precedent to a local, binding one")
    precedent_adopt.add_argument("--domain", required=True)
    precedent_adopt.add_argument("--key", required=True)
    precedent_adopt.set_defaults(handler=cmd_precedent_adopt)

    method = sub.add_parser("method", help="Select an analysis method from the evidence shape")
    method.add_argument("--reports", type=int, default=1)
    method.add_argument("--unreproducible", action="store_true")
    method.add_argument("--ordering", action="store_true", help="An ordering, race or latch-time question")
    method.add_argument("--components", action="store_true", help="Components and failure modes are enumerable")
    method.add_argument("--conditions", type=int, default=0, help="Contributing conditions on one failure")
    method.add_argument("--check-method", choices=list(METHOD_NAMES),
                        help="Check a finished RCA record against its method's completion contract")
    method.add_argument("--check-record", help="Path to the RCA record as JSON")
    method.set_defaults(handler=cmd_method)

    status = sub.add_parser("status", help="Single writable status store")
    status_sub = status.add_subparsers(dest="status_command", required=True)
    status_set = status_sub.add_parser("set")
    status_set.add_argument("item")
    status_set.add_argument("--title", default="")
    status_set.add_argument("--state", choices=list(STATES), required=True)
    status_set.add_argument("--proof", default="", help="Required to reopen verified or closed work")
    status_set.add_argument("--type", choices=list(ITEM_TYPES), default=None)
    status_set.add_argument("--points", type=int, default=None)
    status_set.add_argument("--acceptance", default=None)
    status_set.add_argument("--blocked-on", default=None)
    status_set.add_argument("--root-cause", default=None)
    status_set.add_argument("--depends-on", action="append", default=[])
    status_set.add_argument("--branch", default=None)
    status_set.add_argument("--severity", default=None)
    _evidence(status_set)
    status_set.set_defaults(handler=cmd_status_set)
    status_sub.add_parser("survey").set_defaults(handler=cmd_status_survey)
    status_remaining = status_sub.add_parser("remaining")
    status_remaining.add_argument("--session")
    status_remaining.set_defaults(handler=cmd_remaining)
    status_sub.add_parser(
        "render", help="The status document, rendered read-only from the store"
    ).set_defaults(handler=cmd_status_render)
    status_handover = status_sub.add_parser(
        "handover", help="One rolling handover view derived from the store"
    )
    status_handover.add_argument("--session")
    status_handover.set_defaults(handler=cmd_status_handover)
    status_absorb = status_sub.add_parser(
        "absorb-docs",
        help="Map a status-shaped markdown file into proposed status items; "
             "--write records them, the file itself is never touched")
    status_absorb.add_argument("path")
    status_absorb.add_argument("--write", action="store_true")
    status_absorb.set_defaults(handler=cmd_status_absorb_docs)

    # Named `planmode` rather than extending `plan`: `plan` is part of the released
    # command surface and converting it to subcommands would break existing callers.
    planmode = sub.add_parser("planmode", help="Gate mutation behind an approved plan contract")
    planmode_sub = planmode.add_subparsers(dest="planmode_command", required=True)
    planmode_spec = planmode_sub.add_parser(
        "specify", help="Record the what/why; a plan without one is refused"
    )
    planmode_spec.add_argument("--title", required=True, type=subject_text)
    planmode_spec.add_argument("--session")
    for field in SPEC_FIELDS:
        planmode_spec.add_argument(f"--{field.replace('_', '-')}", dest=field, default="")
    planmode_spec.set_defaults(handler=cmd_planmode_specify)
    planmode_start = planmode_sub.add_parser("start")
    planmode_start.add_argument("--title", required=True, type=subject_text)
    planmode_start.add_argument("--session")
    for field in PLAN_FIELDS:
        if field == "accept":
            # E62: executable acceptance is a list of cmd:<command> entries,
            # not prose - repeatable, unlike every other contract field.
            planmode_start.add_argument(
                "--accept", dest="accept", action="append", default=[],
                help="cmd:<command> the plan is judged done by; repeatable")
            continue
        planmode_start.add_argument(f"--{field.replace('_', '-')}", dest=field, default="")
    planmode_start.set_defaults(handler=cmd_planmode_start)
    planmode_approve = planmode_sub.add_parser("approve")
    planmode_approve.add_argument("--session")
    planmode_approve.set_defaults(handler=cmd_planmode_approve)
    planmode_check = planmode_sub.add_parser("check")
    planmode_check.add_argument("--session")
    planmode_check.set_defaults(handler=cmd_planmode_check)
    planmode_sub.add_parser(
        "arbitrate", help="Score every open plan instead of executing the first one stated"
    ).set_defaults(handler=cmd_planmode_arbitrate)
    planmode_bind = planmode_sub.add_parser("bind")
    planmode_bind.add_argument("--summary", required=True)
    planmode_bind.add_argument("--file", action="append", default=[])
    planmode_bind.add_argument("--session")
    planmode_bind.set_defaults(handler=cmd_planmode_bind)

    assess_parser = sub.add_parser("assess", help="Grade whether this project's own rules can be complied with")
    assess_parser.add_argument("--token-budget", type=int, default=2500)
    assess_parser.add_argument("--full", action="store_true")
    assess_parser.set_defaults(handler=cmd_assess)
    sub.add_parser(
        "trust",
        help="Report what checked-in agent configuration would run or permit",
    ).set_defaults(handler=cmd_trust)
    sub.add_parser("selftest", help="Exercise every control and report what actually held").set_defaults(
        handler=cmd_selftest
    )

    bindings = sub.add_parser("bindings", help="Generate host manifests from one source")
    bindings.add_argument("--write", action="store_true", help="Regenerate instead of only checking")
    bindings.set_defaults(handler=cmd_bindings)
    scenarios = sub.add_parser("scenarios", help="Stage known failures and check a control notices")
    scenarios.add_argument("--only", help="Run a single scenario by name")
    scenarios.set_defaults(handler=cmd_scenarios)

    sub.add_parser("recurrences", help="Find controls that blocked twice on the same cause").set_defaults(
        handler=cmd_recurrences
    )
    sbom_parser = sub.add_parser("sbom", help="List what ships and what it depends on")
    sbom_parser.add_argument("--format", choices=["spdx", "cyclonedx"],
                             help="Emit the claim in a standard SBOM format")
    sbom_parser.add_argument("--gate", action="store_true",
                             help="Fail when the dependency policy is violated")
    sbom_parser.set_defaults(handler=cmd_sbom)
    checksums = sub.add_parser("checksums", help="SHA-256 manifest over every tracked file")
    checksums.add_argument("--verify", metavar="FILE",
                           help="Compare a stored manifest against the current tree")
    checksums.set_defaults(handler=cmd_checksums)

    egress = sub.add_parser("egress", help="Disclose exactly what an action would send")
    egress.add_argument("action", nargs="?", default=None)
    egress.add_argument("--staged", action="store_true",
                        help="Scan staged and untracked-but-addable content for secret shapes")
    egress.add_argument("--destination", default=None,
                        help="Named receiving party (provider/remote/server) when known")
    egress.add_argument("--redact", action="store_true",
                        help="Replace blocking items with bare 'redacted' entries instead of blocking")
    egress.add_argument("--purpose", default="unstated")
    egress.add_argument("--path", action="append", default=[], help="Artefact proposed for inclusion; repeatable")
    egress.set_defaults(handler=cmd_egress)
    sub.add_parser("untrusted", help="Report repository text shaped like an instruction").set_defaults(
        handler=cmd_untrusted
    )

    swallow = sub.add_parser(
        "swallow", help="Scan for silent/swallowed-error shapes; ratchets a per-file baseline"
    )
    swallow.add_argument("--update-baseline", action="store_true",
                         help="Tighten the stored baseline to current counts; never raises it")
    swallow.set_defaults(handler=cmd_swallow)

    sub.add_parser("assurance", help="Emit an assurance case generated from live probes").set_defaults(
        handler=cmd_assurance
    )
    reflect_parser = sub.add_parser("reflect", help="Check a claim against what the record already says")
    reflect_parser.add_argument("text")
    reflect_parser.set_defaults(handler=cmd_reflect)

    scope_parser = sub.add_parser("scope", help="Enumerate the work before reasoning about it")
    scope_parser.add_argument("--since", help="Compare against this ref instead of the working tree")
    scope_parser.add_argument("--full", action="store_true")
    scope_parser.add_argument("--minimality", action="store_true",
                              help="Report size pressure on the change; never blocks")
    scope_parser.set_defaults(handler=cmd_scope)

    atlas = sub.add_parser("atlas", help="Map the project's symbols and their relationships")
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=True)
    atlas_sub.add_parser("map").set_defaults(handler=cmd_atlas)
    atlas_affected = atlas_sub.add_parser("affected")
    atlas_affected.add_argument("symbol")
    atlas_affected.add_argument("--depth", type=int, default=2)
    atlas_affected.add_argument("--include-inferred", action="store_true",
                                help="Include guessed relationships; excluded by default")
    atlas_affected.add_argument("--relations", nargs="+", default=None,
                                help="Restrict traversal to relation kinds, e.g. imports calls tested-by documents")
    atlas_affected.set_defaults(handler=cmd_atlas)
    atlas_save = atlas_sub.add_parser("save", help="Persist the atlas with per-file content hashes")
    atlas_save.add_argument("--to", required=True, help="Destination JSON path, relative to the project root")
    atlas_save.set_defaults(handler=cmd_atlas)
    atlas_load = atlas_sub.add_parser("load", help="Load a saved atlas and report hash-derived freshness")
    atlas_load.add_argument("--from", dest="source", required=True, help="Index JSON path, relative to the project root")
    atlas_load.set_defaults(handler=cmd_atlas)
    atlas_closure = atlas_sub.add_parser(
        "closure", help="Dependents of what changed that were not themselves changed")
    atlas_closure.add_argument("--changed", nargs="+", default=None,
                               help="Changed paths; defaults to the working tree")
    atlas_closure.add_argument("--depth", type=int, default=1)
    atlas_closure.set_defaults(handler=cmd_atlas)
    atlas_sub.add_parser(
        "seams", help="Modules that exist for exactly one consumer"
    ).set_defaults(handler=cmd_atlas)
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
    release_parser = sub.add_parser(
        "release", help="Compare local tags against the releases a caller supplies")
    release_parser.add_argument("--published", action="append", default=[],
                                help="A published release tag; repeatable")
    release_parser.add_argument("--published-from",
                                help="File listing published tags, one per line")
    release_parser.set_defaults(handler=cmd_release)
    capabilities_parser = sub.add_parser(
        "capabilities", help="Report what this host can actually enforce")
    capabilities_parser.add_argument(
        "--host", help="A declared adapter host (opencode, cursor, gemini) instead of the live one")
    capabilities_parser.add_argument(
        "--record", action="store_true", help="Record the negotiated table in the archive")
    capabilities_parser.add_argument(
        "--usage", action="store_true",
        help="Report which declared surfaces this project has never used")
    capabilities_parser.add_argument(
        "--reconcile", action="store_true",
        help="Check capabilities.json, its detector catalog, and the capability-coverage "
             "matrix against shipped code and tests")
    capabilities_parser.set_defaults(handler=cmd_capabilities)
    hooks_parser = sub.add_parser(
        "hooks", help="Truthful interception proof: what the pre-tool hook actually saw")
    hooks_sub = hooks_parser.add_subparsers(dest="hooks_command", required=True)
    hooks_status = hooks_sub.add_parser(
        "status", help="Report hook manifest wiring and the last interception proof")
    hooks_status.add_argument(
        "--host", help="Host label to read the proof for (default: detected)")
    hooks_status.add_argument(
        "--git", action="store_true",
        help="CX-4: report the git-hook backstop's own state instead of host hook wiring")
    hooks_status.set_defaults(handler=cmd_hooks)
    hooks_probe = hooks_sub.add_parser(
        "probe",
        help="Send a synthetic marker operation through the real hook and verify it was denied")
    hooks_probe.add_argument(
        "--host", help="Host label to record the proof under (default: detected)")
    hooks_probe.set_defaults(handler=cmd_hooks)
    hooks_sub.add_parser(
        "statusline",
        help="One compact plain-text segment for a terminal statusline: "
             "presence + enforcement grade. Wire it into the host's "
             "statusline config; godmode never paints ambient UI itself"
    ).set_defaults(handler=cmd_hooks_statusline)
    hooks_wire = hooks_sub.add_parser(
        "wire",
        help="Write the project-level .codex/hooks.json fallback - Codex CLI "
             "0.150.1 ignores plugin-bundled hooks but loads project config; "
             "the operator reviews and Trusts each command in codex afterwards")
    hooks_wire.add_argument(
        "--host", help="codex (default: project hooks fallback) or opencode (Bun shim)")
    hooks_wire.add_argument(
        "--force", action="store_true", help="Overwrite a differing existing file")
    hooks_wire.set_defaults(handler=cmd_hooks)
    hooks_install = hooks_sub.add_parser(
        "install",
        help="Verify each declared hook for one host appears in that host's own runtime "
             "state, where inspectable; fails loudly on partial registration. With --git, "
             "installs (or, with --uninstall, removes) the host-independent git-hook "
             "backstop instead")
    hooks_install.add_argument(
        "--host", help="Host to verify: claude, codex, grok, cursor, or gemini")
    hooks_install.add_argument(
        "--state-path",
        help="A captured/fixture copy of the host's own state (Codex's config.toml, "
             "or a `grok inspect --json` capture) instead of auto-discovering one")
    hooks_install.add_argument(
        "--git", action="store_true",
        help="CX-4: install the git-hook backstop (pre-commit/pre-push/pre-rebase/"
             "post-checkout) instead of verifying a host manifest; refuses unless "
             "{\"git_backstop\": true} is declared")
    hooks_install.add_argument(
        "--uninstall", action="store_true",
        help="With --git: remove every godmode-owned git hook instead of installing them")
    hooks_install.set_defaults(handler=cmd_hooks)
    hooks_verify = hooks_sub.add_parser(
        "verify",
        help="CX-4: run a synthetic protected push through the real pre-push hook "
             "mechanics in a throwaway repo, and record a live proof (host=git) if it "
             "actually blocks")
    hooks_verify.add_argument(
        "--git", action="store_true", required=True,
        help="Currently the only verify target")
    hooks_verify.set_defaults(handler=cmd_hooks)
    minimality_parser = sub.add_parser(
        "minimality", help="Rank existing duplicate/orphan/seam/decay surfaces into one report")
    # C-04: the counts get a ceiling, and growth past it is answered for.
    minimality_parser.add_argument("--set-baseline", action="store_true",
                            help="Record the current counts as the ceiling to compare against")
    minimality_parser.add_argument("--accept-growth", default=None, metavar="SECTION",
                            help="Allow a section to exceed its ceiling; needs --reason")
    minimality_parser.add_argument("--reason", default=None,
                            help="What the added surface bought, for --accept-growth")
    minimality_parser.set_defaults(handler=cmd_minimality)
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
    context_structure = context_sub.add_parser(
        "structure",
        help="B4-6: incremental structural index (Python symbols via ast, "
             "file-level otherwise; names and hashes only) + bounded outline")
    context_structure.add_argument("--limit-lines", type=int, default=200,
                                   dest="limit_lines")
    context_structure.set_defaults(handler=cmd_context_structure)
    context_why_parser = context_sub.add_parser(
        "why", help="Show recorded decisions, fixes, dependencies, and invariants about a path or topic"
    )
    context_why_parser.add_argument("--about", type=subject_text, default=None)
    context_why_parser.set_defaults(handler=cmd_context_why)

    inventory = sub.add_parser("inventory", help="Repository inventory operations")
    inventory_sub = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_sub.add_parser("diff").set_defaults(handler=cmd_inventory_diff)

    history = sub.add_parser("history", help="Read structured local history")
    history.add_argument("--kind", choices=sorted(EVENT_KINDS))
    history.add_argument("--subject")
    history.add_argument("--limit", type=int, default=50)
    history.set_defaults(handler=cmd_history)

    plan = sub.add_parser("plan", help="Record a private execution contract")
    plan.add_argument("--title", required=True, type=subject_text)
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
    checkpoint.add_argument(
        "--review", action="store_true",
        help="Report carried obligations a later handoff may have made moot")
    # Field report 2026-09-01: `checkpoint "summary text"` was rejected while
    # the sibling verb `claim` takes its text positionally. One meaning, two
    # spellings, same as claim's --text alias.
    checkpoint.add_argument("summary_positional", nargs="?", default=None,
                            help="Alias for --summary")
    checkpoint.add_argument("--summary", required=False)
    checkpoint.add_argument("--status", required=False)
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

    remember = sub.add_parser(
        "remember",
        help="Record a decision, invariant, lesson, obligation, assumption, or request")
    remember.add_argument(
        "--kind",
        # U-S4 - "assumption" added for the assumption gate
        # (`godmode_attest.assumption_gate`); the record kind itself lives
        # in EVENT_KINDS (godmode_constants.py).
        choices=["decision", "invariant", "lesson", "obligation", "assumption", "request",
                 "incident"],
        required=True)
    remember.add_argument("--failure-class", dest="failure_class", default=None,
                          help="incident only: one of the closed failure classes "
                               "(off-list refused with the list rendered)")
    remember.add_argument("--turning-point", dest="turning_point", action="store_true",
                          help="incident only: the first failure the run never recovered "
                               "from; requires --evidence")
    remember.add_argument("--subject", required=True, type=subject_text)
    remember.add_argument("--value", required=True)
    remember.add_argument("--status", default=None,
                          help="Default: active, or open for a request")
    remember.add_argument("--guard")
    remember.add_argument("--standing", action="store_true",
                          help="Obligations only: a per-task duty with no "
                               "subject to match - surfaces at every stop, "
                               "survives quiet posture (definition-of-done, "
                               "not advisory)")
    remember.add_argument("--source", choices=["stated", "inferred"], default="stated",
                          help="Requests only: whether the operator stated this ask "
                               "or the agent inferred it on their behalf")
    # U-S4 - assumption records only; every other kind is session-agnostic
    # and leaves this unused. Falls back to the latest open session, same as
    # `claim`/`criterion`/`gate`.
    remember.add_argument("--session",
                          help="Assumption records only: defaults to the latest open session")
    _evidence(remember)
    remember.set_defaults(handler=cmd_remember)

    digest_parser = sub.add_parser(
        "digest",
        help="The archive told as dated prose - what happened, in order, "
             "assembled verbatim from record fields; no model, no paraphrase")
    digest_parser.add_argument("--since", type=int, default=0,
                               help="Start the story at this sequence")
    digest_parser.set_defaults(handler=cmd_digest)
    doctor = sub.add_parser("doctor", help="Verify archive and continuity health")
    doctor.add_argument("--deep", action="store_true")
    doctor.set_defaults(handler=cmd_doctor)

    fence = sub.add_parser("fence", help="The editable set this plan declared")
    fence_sub = fence.add_subparsers(dest="fence_command", required=True)
    fence_audit = fence_sub.add_parser(
        "audit", help="Changed files that fall outside the declared editable set")
    fence_audit.add_argument("--changed", nargs="+", default=None,
                             help="Changed paths; defaults to the working tree")
    fence_audit.add_argument("--complete", action="store_true",
                             help="Surgical-diff mode (U-B1): partition `git diff "
                                  "--unified=0 HEAD` by fence membership, flag "
                                  "unauthorized deletions and instrumentation tags")
    fence_audit.set_defaults(handler=cmd_fence_audit)
    fence_sub.add_parser(
        "acceptance", help="Completions that cite no acceptance"
    ).set_defaults(handler=cmd_fence_acceptance)
    fence_delete_check = fence_sub.add_parser(
        "delete-check",
        help="B3-6: whether a deletion the fence would otherwise allow may proceed")
    fence_delete_check.add_argument("--path", required=True)
    fence_delete_check.set_defaults(handler=cmd_fence_delete_check)
    fence_delete_precheck = fence_sub.add_parser(
        "delete-precheck",
        help="B3-6: attest the provenance pre-check before a tracked file is deleted")
    fence_delete_precheck.add_argument("--path", required=True)
    fence_delete_precheck.add_argument(
        "--history-read", required=True,
        help="What the file's git history showed")
    fence_delete_precheck.add_argument(
        "--sole-carrier", required=True,
        help="Whether this file is the sole carrier of a still-open obligation")
    fence_delete_precheck.set_defaults(handler=cmd_fence_delete_precheck)

    precheck_parser = sub.add_parser(
        "precheck", help="Whether this was already built or already refused")
    precheck_parser.add_argument("--about", default=None,
                                 help="The task, in the words you would describe it")
    precheck_parser.add_argument("--changed", nargs="+", default=None,
                                 help="Changed paths, for the paired-artifact check "
                                      "(GAP-2); defaults to the working tree")
    precheck_parser.add_argument("--preflight", action="store_true",
                                 help="Push preflight instead: validate HEAD in a "
                                      "disposable worktree - banned-term scan plus the "
                                      "designated --suite - findings triaged mechanical "
                                      "vs judgment; feeds the password gate, never "
                                      "bypasses it")
    precheck_parser.add_argument("--suite", nargs="+", default=None,
                                 help="With --preflight: the command to run inside the "
                                      "worktree (e.g. python -m unittest ...)")
    precheck_parser.set_defaults(handler=cmd_precheck)

    # A sibling top-level command, not a `precheck` subcommand: `precheck`
    # already ships as a flat leaf (`--about` required directly, no
    # subcommand) and is named in released docs that way - nesting a
    # subcommand under it would make `--about` a required argument of
    # `declare-pair` too and break that documented surface for no reason.
    paired_artifact = sub.add_parser(
        "paired-artifact", help="Artifacts declared to change together (GAP-2)")
    paired_artifact_sub = paired_artifact.add_subparsers(
        dest="paired_artifact_command", required=True)
    paired_artifact_declare = paired_artifact_sub.add_parser(
        "declare", help="Declare two artifacts that must change together")
    paired_artifact_declare.add_argument("--label", required=True,
                                         help="Unique name for this pair")
    paired_artifact_declare.add_argument("--a", required=True, help="First artifact's path")
    paired_artifact_declare.add_argument("--b", required=True, help="Second artifact's path")
    paired_artifact_declare.add_argument("--reason", default="",
                                         help="Why these two must change together")
    paired_artifact_declare.set_defaults(handler=cmd_precheck_declare_pair)

    boundaries = sub.add_parser("boundaries", help="Design surfaces this project protects")
    boundaries_sub = boundaries.add_subparsers(dest="boundaries_command", required=True)
    propose_ui = boundaries_sub.add_parser(
        "propose-ui", help="Propose design globs to declare; prints, never writes")
    propose_ui.set_defaults(handler=cmd_boundaries_propose_ui)
    sub.add_parser("privacy", help="Audit the local privacy boundary").set_defaults(handler=cmd_privacy)

    law = sub.add_parser(
        "law",
        help="The generated per-project Code of Law (Sprint L1: compile guarded "
             "lessons into GODMODE-CODE-OF-LAW.md + wrapper skill)")
    law_sub = law.add_subparsers(dest="law_command", required=True)
    law_compile = law_sub.add_parser(
        "compile", help="Fold every guarded lesson into the bounded law file")
    law_compile.set_defaults(handler=cmd_law_compile)
    law_show = law_sub.add_parser("show", help="The top laws, as the brief carries them")
    law_show.add_argument("--top", type=int, default=5)
    law_show.set_defaults(handler=cmd_law_show)
    law_debrief = law_sub.add_parser(
        "debrief",
        help="The amendment loop: per law, delivered/cited/recurred counts and "
             "triaged recommendations; receipted so staleness is measurable")
    law_debrief.set_defaults(handler=cmd_law_debrief)
    law_amend = law_sub.add_parser(
        "amend", help="Append a reviewed replacement guard for a living law "
                      "(newest record per subject wins)")
    law_amend.add_argument("--law", type=int, required=True)
    law_amend.add_argument("--guard", required=True)
    law_amend.set_defaults(handler=cmd_law_amend)
    law_candidates_parser = law_sub.add_parser(
        "candidates",
        help="Correction candidates clustered by keywords, with recurrence counts")
    law_candidates_parser.set_defaults(handler=cmd_law_candidates)
    law_hygiene = law_sub.add_parser(
        "hygiene",
        help="Maintenance scan: laws with no recorded origin, contradictory "
             "pairs, and guards a recorded check now enforces mechanically - "
             "names candidates, never retires")
    law_hygiene.set_defaults(handler=cmd_law_hygiene)
    law_promote = law_sub.add_parser(
        "promote",
        help="Promote a promotable candidate cluster into a guarded law "
             "(the ladder requires recurrence across 3 distinct sessions)")
    law_promote.add_argument("--candidate", type=int, required=True,
                             help="The cluster's first_seq from `law candidates`")
    law_promote.add_argument("--guard", required=True)
    law_promote.add_argument("--subject", required=True)
    law_promote.set_defaults(handler=cmd_law_promote)

    changelog = sub.add_parser("changelog", help="Fragment-based release notes")
    changelog_sub = changelog.add_subparsers(dest="changelog_command", required=True)
    changelog_check = changelog_sub.add_parser(
        "check", help="Fail when a code change arrives without a changelog.d fragment"
    )
    changelog_check.add_argument("--base", default="HEAD", help="Git ref to diff against")
    changelog_check.set_defaults(handler=cmd_changelog_check)
    changelog_merge = changelog_sub.add_parser(
        "merge", help="Fold changelog.d fragments into CHANGELOG.md for a release"
    )
    changelog_merge.add_argument("--set-version", required=True)
    changelog_merge.add_argument("--date", help="Release date; defaults to today")
    changelog_merge.set_defaults(handler=cmd_changelog_merge)

    benchmark = sub.add_parser("benchmark", help="Measure brief budgets and timings, locally only")
    benchmark.set_defaults(handler=cmd_benchmark)

    ceilings = sub.add_parser("ceilings", help="Check reported spend against declared run ceilings")
    ceilings.add_argument("--spent", default="",
                          help="Comma-separated spend, e.g. tokens=1200,tool_calls=40,seconds=90")
    ceilings.set_defaults(handler=cmd_ceilings)

    watch = sub.add_parser("watch", help="Per-boundary anomaly scan over this session's attestations")
    watch.add_argument("--session")
    watch.set_defaults(handler=cmd_watch)

    rewind = sub.add_parser("rewind", help="Preview a rollback to a prior verified checkpoint")
    rewind.add_argument("--to", type=int, required=True, metavar="SEQ")
    rewind.set_defaults(handler=cmd_rewind)

    loop = sub.add_parser("loop", help="Detect repetition the repeating agent cannot see")
    loop.add_argument("--blame", action="store_true",
                      help="Check whether blaming the model is supported by a non-model control")
    loop.add_argument("--session")
    loop.add_argument("--preflight", action="store_true",
                      help="Task 10b: audit .godmode-loop.json readiness (stop contract, "
                           "budget, verdict path, escalation thresholds) before cycle one")
    loop.set_defaults(handler=cmd_loop)
    # S16: the loop CONTRACT verbs live under the same noun - `godmode loop`
    # bare keeps the detector behavior; declare/tick/close carry the bounded
    # contract (readiness at declaration, graduated stall escalation,
    # terminated-vs-truncated at close).
    loop_sub = loop.add_subparsers(dest="loop_command", required=False)
    loop_declare = loop_sub.add_parser("declare")
    loop_declare.add_argument("name")
    loop_declare.add_argument("--max-iterations", type=int, required=True)
    loop_declare.add_argument("--stop-when", action="append", default=[],
                              help="A condition that ends the loop; repeatable")
    loop_declare.set_defaults(handler=cmd_loop_contract)
    loop_tick = loop_sub.add_parser("tick")
    loop_tick.add_argument("name")
    loop_tick.add_argument("--empty", action="store_true",
                           help="This iteration made no progress")
    loop_tick.add_argument("--note", default="")
    _evidence(loop_tick)
    loop_tick.set_defaults(handler=cmd_loop_contract)
    loop_close = loop_sub.add_parser("close")
    loop_close.add_argument("name")
    loop_close.add_argument("--outcome", choices=["finished", "cut-off"],
                            required=True)
    _evidence(loop_close)
    loop_close.set_defaults(handler=cmd_loop_contract)

    environment = sub.add_parser(
        "environment", help="Classify a mutation target's blast radius; unknown fails closed"
    )
    environment.add_argument("--target", required=True)
    environment.set_defaults(handler=cmd_environment)

    mistakes = sub.add_parser("mistakes", help="Run the mistake-class detectors")
    mistakes.add_argument("--process-started", metavar="ISO",
                          help="Check the running process against source mtimes before an RCA")
    mistakes.set_defaults(handler=cmd_mistakes)

    removal = sub.add_parser("removal", help="Remember why something was deleted")
    removal_sub = removal.add_subparsers(dest="removal_command", required=True)
    removal_record = removal_sub.add_parser(
        "record", help="Record a removal; all six fields are required"
    )
    removal_record.add_argument("--subject", required=True, type=subject_text)
    for field in REMOVAL_FIELDS:
        removal_record.add_argument(f"--{field}", required=True)
    _evidence(removal_record)
    removal_record.set_defaults(handler=cmd_removal_record)
    removal_why = removal_sub.add_parser("why", help="Answer why something was removed")
    removal_why.add_argument("--subject", required=True, type=subject_text)
    removal_why.set_defaults(handler=cmd_removal_why)

    locale = sub.add_parser("locale", help="Localized guidance surfaces")
    locale_sub = locale.add_subparsers(dest="locale_command", required=True)
    locale_check = locale_sub.add_parser(
        "check", help="Validate locales/ variants against their English sources"
    )
    locale_check.set_defaults(handler=cmd_locale_check)

    integrity = sub.add_parser(
        "integrity", help="Run the nine test-integrity monitors over the current diff"
    )
    integrity.add_argument("--base", default="HEAD", help="Git ref to diff against")
    integrity.set_defaults(handler=cmd_integrity)

    guard = sub.add_parser("guard", help="Preview and authorize an exact operation without executing it")
    guard_target = guard.add_mutually_exclusive_group(required=True)
    guard_target.add_argument("--operation")
    guard_target.add_argument(
        "--git-hook", choices=GIT_HOOK_NAMES,
        help="CX-4: evaluate the git-hook backstop for this hook name, reading git's own "
             "hook-specific context (stdin for pre-push; nothing for the others) instead "
             "of an --operation string. What every installed git hook script calls.")
    guard.add_argument("--capability")
    guard.set_defaults(handler=cmd_guard)

    license_parser = sub.add_parser(
        "license", help="B3-5: license/provenance gate for external-repo interaction")
    license_sub = license_parser.add_subparsers(dest="license_command", required=True)
    license_check = license_sub.add_parser(
        "check", help="Whether an operation naming an external repo may proceed")
    license_check.add_argument("--operation", required=True)
    license_check.set_defaults(handler=cmd_license_check)
    license_attest = license_sub.add_parser(
        "attest", help="Record a license classification for a repository read or absorbed")
    license_attest.add_argument("--repo", required=True, help="The repository reference")
    license_attest.add_argument("--classification", required=True,
                                choices=LICENSE_CLASSIFICATIONS)
    license_attest.add_argument(
        "--clean-room-note", default="",
        help="Required for anything other than 'permissive': what was read versus written")
    license_attest.set_defaults(handler=cmd_license_attest)

    protect = sub.add_parser(
        "protect", help="Pin, unpin, or list protected evaluator files (U-B2)")
    protect_target = protect.add_mutually_exclusive_group(required=True)
    protect_target.add_argument("--pin", metavar="PATH",
                                help="Pin a file as a protected evaluator; needs no capability")
    protect_target.add_argument("--unpin", metavar="PATH",
                                help="Unpin a protected evaluator; needs a capability")
    protect_target.add_argument("--list", action="store_true",
                                help="List currently pinned evaluators")
    protect.add_argument("--capability", help="Capability token authorizing --unpin")
    protect.set_defaults(handler=cmd_protect)

    authorize = sub.add_parser("authorize", help="Configure or issue local capabilities")
    authorize_sub = authorize.add_subparsers(dest="authorize_command", required=True)
    _setup_help = ("One-time: set the local password that mints capabilities for "
                   "irreversible operations")
    setup = authorize_sub.add_parser("setup", help=_setup_help, description=_setup_help)
    setup.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting",
    )
    setup.set_defaults(handler=cmd_authorize_setup)
    request = authorize_sub.add_parser("request",
                                       help="Record a request an agent cannot grant itself")
    request.add_argument("--operation", required=True)
    request.add_argument("--purpose", default="")
    request.set_defaults(handler=cmd_authorize_request)

    staging = authorize_sub.add_parser(
        "stage", help="Authorize one exact operation for the next tool call")
    staging.add_argument("--operation")
    staging.add_argument(
        "--from-last-refusal", action="store_true",
        help="Stage the operation named by the gate's own most recent refusal")
    staging.add_argument(
        "--nth", type=int, default=1,
        help="With --from-last-refusal, pick the nth-most-recent refusal (default 1)")
    staging.add_argument("--ttl", type=int, default=None)
    staging.add_argument("--password-stdin", action="store_true")
    staging.set_defaults(handler=cmd_authorize_stage)

    listing = authorize_sub.add_parser("requests", help="Show recorded requests and outcomes")
    listing.add_argument("--state", choices=["requested", "granted", "denied"])
    listing.set_defaults(handler=cmd_authorize_list)

    granting = authorize_sub.add_parser("grant", help="Approve a recorded request")
    granting.add_argument("--request", required=True)
    granting.add_argument("--ttl", type=int, default=None)
    granting.add_argument("--password-stdin", action="store_true")
    granting.set_defaults(handler=cmd_authorize_grant)

    denial = authorize_sub.add_parser("deny", help="Refuse a request, on the record")
    denial.add_argument("--request", required=True)
    denial.add_argument("--reason", required=True)
    denial.set_defaults(handler=cmd_authorize_deny)

    _issue_help = ("Mint a capability token for one exact operation (prefer stage, which "
                   "parks it for the hook)")
    issue = authorize_sub.add_parser("issue", help=_issue_help, description=_issue_help)
    issue.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from standard input instead of prompting",
    )
    issue.add_argument("--operation", required=True)
    issue.add_argument("--ttl", type=int, default=None)
    issue.set_defaults(handler=cmd_authorize_issue)
    actions = sub.add_parser("actions", help="Read capability audit events")
    actions.add_argument("--limit", type=int, default=50)
    actions.set_defaults(handler=cmd_actions)

    branches = sub.add_parser("branches", help="Inspect branches and worktrees")
    branches.add_argument("--record", action="store_true")
    branches.add_argument("--claim", action="store_true",
                          help="Declare this agent active here; exits 1 if another agent already is")
    branches.add_argument("--release", action="store_true", help="Release this agent's claim")
    branches.set_defaults(handler=cmd_branches)

    version = sub.add_parser("version", help="Record a version fact, or reconcile every surface")
    version.add_argument("--reconcile", action="store_true",
                         help="Diff the version across every surface that states one")
    version.add_argument("--name", default="")
    version.add_argument("--value", default="")
    version.add_argument("--status", default="observed")
    _evidence(version)
    version.set_defaults(handler=cmd_version)

    database = sub.add_parser("db", help="Record database governance state")
    # Not parser-required since --reanchor (B4-1): the record path validates
    # them itself, same pattern as checkpoint's --review.
    database.add_argument("--engine")
    database.add_argument("--change")
    database.add_argument("--status")
    database.add_argument(
        "--reanchor", action="store_true",
        help="B4-1: accept a tail-truncated chain as the chain - rewrites "
             "the sidecar anchor to the records that remain and chronicles "
             "the acceptance (an explicit operator decision)")
    database.add_argument("--rollback")
    database.add_argument("--propose", action="store_true",
                          help="Run the schema decision ladder instead of recording state")
    database.add_argument("--proposed-table")
    database.add_argument("--proposed-column")
    database.add_argument("--existing-table", action="append", default=[])
    database.add_argument("--existing-column", action="append", default=[], metavar="TABLE:COLUMN")
    database.add_argument("--review", default="")
    database.add_argument("--inventory", action="store_true",
                          help="Read-only sqlite schema inventory over the tree")
    database.add_argument("--review-migration", metavar="FILE",
                          help="Static review of a migration SQL file")
    _evidence(database)
    database.set_defaults(handler=cmd_database)

    fuzz_parser = sub.add_parser(
        "fuzz", help="Feed the classifiers seeded garbage and require them to fail closed")
    fuzz_parser.add_argument("--seed", type=int, default=0)
    fuzz_parser.add_argument("--iterations", type=int, default=200)
    fuzz_parser.set_defaults(handler=cmd_fuzz)

    metrics_parser = sub.add_parser(
        "metrics", help="Measure whether the product works, from local records only")
    metrics_parser.add_argument(
        "--complexity", action="store_true",
        help="Per-function branch complexity (decision points + 1, from the "
             "ast) over the project's Python; worst offenders first, advisory")
    metrics_parser.add_argument("--window", type=int, default=500)
    metrics_parser.add_argument("--markdown", action="store_true")
    metrics_parser.set_defaults(handler=cmd_metrics)

    roi_parser = sub.add_parser(
        "roi", help="Counts-only ROI report: burn beside gate activity, no causal claims")
    roi_parser.add_argument("--sessions", type=int, default=None,
                            help="Limit the fold to the most recent N sessions")
    roi_parser.add_argument(
        "--digest", action="store_true",
        help="U-E7: would-have-caught view over gate_mode=observe records only "
             "(would-have-denied/would-have-asked by category), never merged "
             "with the real denial counts above")
    roi_parser.set_defaults(handler=cmd_roi)

    trends_parser = sub.add_parser(
        "trends",
        help="B4-5: per-session token/tool-call/test-run counts as a time "
             "series - unmeasured sessions stated as gaps, never interpolated",
    )
    trends_parser.add_argument(
        "--sessions", type=int, default=None,
        help="Bound the series to the most recent N measurement records",
    )
    trends_parser.set_defaults(handler=cmd_trends)

    observe_parser = sub.add_parser(
        "observe",
        help="B4-10: what an observe-mode trial recorded - tier-shaped "
             "would-have counts; --report lists the decisions themselves",
    )
    observe_parser.add_argument(
        "--report", action="store_true",
        help="List the last N would-have decisions with tier, category, "
             "reason and (redaction-scanned) operation text",
    )
    observe_parser.add_argument(
        "--last", type=int, default=20,
        help="How many decisions --report lists (default: 20)",
    )
    observe_parser.set_defaults(handler=cmd_observe)

    recurring_parser = sub.add_parser(
        "recurring",
        help="U-E10: mine the request ledger for asks repeated across sessions - "
             "SOFT charter-rule proposals only, nothing auto-written",
    )
    recurring_parser.add_argument(
        "--threshold", type=int, default=RECURRENCE_DEFAULT_THRESHOLD,
        help="Distinct sessions a normalized ask must recur in to be reported "
             f"(default: {RECURRENCE_DEFAULT_THRESHOLD})",
    )
    recurring_parser.set_defaults(handler=cmd_recurring)

    upstream_parser = sub.add_parser(
        "upstream",
        help="B3-1: diff a named package's (or a forked/copied tree's) shipped "
             "surface against this project's own equivalents - GAP-1",
    )
    upstream_target = upstream_parser.add_mutually_exclusive_group(required=True)
    upstream_target.add_argument(
        "--diff", metavar="PACKAGE",
        help="Installed package name to resolve and diff (Python first-class; "
             "Node best-effort with --language node)")
    upstream_target.add_argument(
        "--path", metavar="VENDORED_TREE",
        help="Local path to a forked/fully-copied external repo - carries the "
             "same diff-against-upstream duty as a lockfile dependency")
    upstream_parser.add_argument(
        "--language", choices=("python", "node"), default="python",
        help="Resolution language for --diff (default: python)")
    upstream_parser.add_argument(
        "--dispose", action="append", default=[],
        metavar="SYMBOL=DISPOSITION:BEHAVIOR_VERDICT",
        help="Record adopt/extend/diverge-deliberately/n-slash-a-different-surface "
             "paired with confirmed-we-have-it/confirmed-we-dont/unverified for "
             "one unmatched symbol; repeatable")
    _evidence(upstream_parser)
    upstream_parser.set_defaults(handler=cmd_upstream)

    expunge_parser = sub.add_parser(
        "expunge",
        help="Erase a leaked secret from a record, re-sealing the chain with an auditable tombstone",
    )
    expunge_parser.add_argument("--sequence", type=int, required=True)
    expunge_parser.add_argument("--reason", required=True)
    expunge_parser.set_defaults(handler=cmd_expunge)

    stage = sub.add_parser("stage", help="Lifecycle stage gate: check, advance, or skip with reason")
    stage.add_argument("--to", required=True)
    stage.add_argument("--advance", action="store_true")
    stage.add_argument("--skip", action="store_true")
    stage.add_argument("--reason", default="")
    stage.add_argument("--session")
    stage.set_defaults(handler=cmd_stage)

    sop = sub.add_parser("sop", help="T0-T14 troubleshooting SOP status and attestation")
    sop.add_argument("--attest", metavar="Tn")
    sop.add_argument("--result", default="")
    sop.add_argument("--session")
    _evidence(sop)
    sop.set_defaults(handler=cmd_sop)

    index_parser = sub.add_parser("index", help="Derived SQLite index over corpus, charter, and archive")
    index_sub = index_parser.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild").set_defaults(handler=cmd_index)
    index_sub.add_parser("status").set_defaults(handler=cmd_index)
    index_q = index_sub.add_parser("query")
    index_q.add_argument("--task", required=True)
    index_q.add_argument("--limit", type=int, default=10)
    index_q.add_argument("--allow-stale", action="store_true")
    index_q.set_defaults(handler=cmd_index)

    sprint = sub.add_parser("sprint", help="Record private sprint state")
    sprint.add_argument("--name", required=True)
    sprint.add_argument("--status", required=True)
    sprint.add_argument("--capacity", type=int)
    sprint.add_argument("--obligation", action="append", default=[])
    _evidence(sprint)
    sprint.set_defaults(handler=cmd_sprint)

    docs = sub.add_parser("docs", help="Record documentation obligations, or reconcile the trigger table")
    docs.add_argument("--emit-agentsmd", dest="emit_agentsmd", action="store_true",
                      help="Write or refresh the godmode section of AGENTS.md - generated "
                           "from the registered verbs and the boundary tier table, "
                           "merge-not-overwrite")
    docs.add_argument("--emit-rules", dest="emit_rules", default=None,
                      choices=["cursor", "copilot", "generic"],
                      help="Render the canonical doctrine, red flags, and When "
                           "rules into a host's instruction-file format - one "
                           "source, generated never hand-edited")
    docs.add_argument("--lint", action="store_true",
                      help="Check public prose for leaked rationale and unverifiable claims")
    docs.add_argument("--reconcile", action="store_true",
                      help="Fail when a change mandates a documentation move that did not happen")
    docs.add_argument("--base", default="HEAD")
    docs.add_argument("--records", action="store_true",
                      help="Check the record-based trigger table (change->checkpoint, bug->lesson, ...)")
    docs.add_argument("--base-sequence", type=int, default=0)
    docs.add_argument("--document", default="")
    docs.add_argument("--status", default="")
    docs.add_argument("--note")
    _evidence(docs)
    docs.set_defaults(handler=cmd_docs)

    report = sub.add_parser("report", help="Mandatory task-completion report (12 labelled fields)")
    report.add_argument("--context", action="store_true",
                        help="Emit the sanitized bounded context brief (previous behavior) instead")
    report.add_argument("--markdown", action="store_true",
                        help="Render the TASK COMPLETION REPORT markdown table")
    report.add_argument("--session", default=None, help="Session id; defaults to the latest session")
    report.add_argument("--record-claims", dest="record_claims", action="store_true",
                        help="Record the report's own assertions as graded claims")
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
    parity.add_argument("--matrix", action="store_true",
                        help="Full eleven-dimension decision matrix instead of category gaps")
    parity.add_argument("--archive", action="store_true",
                        help="Apply the recorded-invariant adoption floor (E-14) to the matrix")
    parity.set_defaults(handler=cmd_parity)

    netgate = sub.add_parser("netgate", help="Prove the CLI surfaces make zero network connections")
    netgate.set_defaults(handler=cmd_netgate)

    evals = sub.add_parser("evals", help="Execute the authored skill evals: routing accuracy plus snapshot diff")
    evals.add_argument("--write-snapshots", action="store_true",
                       help="Accept current routing outcomes as the new baseline fixtures")
    evals.set_defaults(handler=cmd_evals)

    grid = sub.add_parser("grid", help="Attack every enforcement control; report each cell's observed result")
    grid.set_defaults(handler=cmd_grid)

    absorb = sub.add_parser("absorb", help="Check whether a synced file is truly absorbed (reader + guard)")
    absorb.add_argument("--path", required=True)
    absorb.set_defaults(handler=cmd_absorb)

    skill = sub.add_parser("skill", help="Validate or forge a project skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser(
        "lifecycle", help="List each skill's lifecycle state"
    ).set_defaults(handler=cmd_skill_lifecycle)
    skill_retire = skill_sub.add_parser("retire", help="Deprecate a skill with a recorded reason")
    skill_retire.add_argument("--name", required=True)
    skill_retire.add_argument("--reason", required=True)
    skill_retire.set_defaults(handler=cmd_skill_retire)
    skill_validate = skill_sub.add_parser("validate")
    skill_validate.add_argument("--path", required=True)
    skill_validate.set_defaults(handler=cmd_skill_validate)
    skill_lint = skill_sub.add_parser(
        "lint", help="Three structural facets: scope, delivery, safety; verdict is structural only")
    skill_lint.add_argument("--path", required=True)
    skill_lint.set_defaults(handler=cmd_skill_lint)
    skill_forge = skill_sub.add_parser("forge")
    skill_forge.add_argument(
        "--destination", default=None,
        help="Skill output directory. Default: .grok/skills/ on Grok (CX-3, Addendum 6's "
             "roster-gap fix), else skills/ under the project root.")
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
    # Output flags are global, so argparse would demand they precede the
    # subcommand. Requiring a remembered argument order is the same friction that
    # suppresses use in the first place, so they are lifted out of wherever they
    # were written and position stops mattering.
    raw = list(sys.argv[1:] if argv is None else argv)
    lifted = [flag for flag in ("--brief", "--json", "--terse") if flag in raw]
    raw = [token for token in raw if token not in ("--brief", "--json", "--terse")]

    parser = _build_parser()
    # S12-A: presentation only - no verb changes behavior. Bare invocation
    # shows the day-one face instead of an argparse error; `--all` shows the
    # generated full listing. Any real command token falls through to
    # argparse untouched.
    if not raw and not lifted:
        print(_day_one_text(parser), end="")
        return 0
    if raw == ["--all"]:
        print(_all_verbs_text(parser), end="")
        return 0
    args = parser.parse_args(lifted + raw)
    if args.command == "guide":
        tier = getattr(args, "tier", None)
        if tier is None:
            print(GUIDE_TEXT, end="")
            return 0
        # C-61: one tier at a time, so the day-one reader is never handed
        # the fleet tier by accident. The doc is the authority; this only
        # cuts it at the tier headings.
        ladder = (_PLUGIN_ROOT / "docs" / "LADDER.md").read_text(encoding="utf-8")
        parts = re.split(r"^(?=## Tier \d\b)", ladder, flags=re.M)
        section = next((p for p in parts if p.startswith(f"## Tier {tier}")), None)
        if section is None:
            parser.error(f"docs/LADDER.md has no `## Tier {tier}` section")
        print(section.rstrip() + "\n", end="")
        return 0
    if hasattr(args, "token_budget") and not 200 <= args.token_budget <= 10_000:
        parser.error("--token-budget must be between 200 and 10000")
    # S21-01: mode changes exposure, never enforcement. `guided` explains a
    # refusal in plain language; `expert` reports one line; gates are identical.
    mode = os.environ.get("GODMODE_MODE", "standard")
    if mode == "expert" and not getattr(args, "json", False):
        args.brief = True
    return _dispatch(args, mode=mode)


def _reports_error(payload: Any) -> bool:
    """B4-8(a): a payload carrying an error verdict IS a failure, whatever
    exit code its handler set. Truthy `error` key is the shape every such
    site already uses (`{"error": "PrivacyError", ...}`)."""
    return isinstance(payload, dict) and bool(payload.get("error"))


def _dispatch(args: argparse.Namespace, mode: str = "standard") -> int:
    """Run one parsed command and map its result to the exit vocabulary:
    0 ok / 1 findings-red (ran, found problems - set by the handler) /
    2 error (the command itself failed, whether raised OR reported in the
    payload body). B4-8(a): enforced here, at the one seam every command
    shares, so a handler that catches its own failure and reports it in the
    body with exit 0 - the field defect - still exits nonzero, and commands
    added later inherit the contract without opting in.
    """
    try:
        runtime = _runtime(args.project)
        handler: Callable[[argparse.Namespace, Runtime], CommandResult] = args.handler
        result = handler(args, runtime)
        if result.exit_code == 0 and _reports_error(result.payload):
            result = CommandResult(result.payload, exit_code=2)
        if mode == "guided" and result.exit_code != 0 and isinstance(result.payload, dict):
            missing = (result.payload.get("missing")
                       or result.payload.get("exceeded")
                       or result.payload.get("half_done_pairs")
                       or [f.get("detail") for f in result.payload.get("findings", [])
                           if isinstance(f, dict) and f.get("blocking")])
            result.payload["guidance"] = {
                "what_was_missing": missing or result.payload.get("reason")
                or result.payload.get("detail") or "see the fields above",
                "why_this_gate_exists": "each gate encodes a failure that actually recurred; "
                                        "passing it is cheaper than re-living the failure",
                "next": result.payload.get("next")
                or result.payload.get("next_action")
                or "satisfy the named gap and re-run the same command",
            }
        if getattr(args, "brief", False):
            print(_brief_line(result.payload))
            return result.exit_code
        if getattr(args, "terse", False):
            print(_terse_text(result.payload))
            return result.exit_code
        if isinstance(result.payload, str):
            # A handler that has already rendered text - an editor-shaped
            # listing, say - is printed as-is; JSON-encoding it would wrap
            # every line in one quoted string no consumer could parse.
            print(result.payload)
            return result.exit_code
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
        if getattr(args, "brief", False):
            print(f"{payload['error']}: {payload['message']}", file=sys.stderr)
        else:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
