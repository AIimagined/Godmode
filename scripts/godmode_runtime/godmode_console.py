"""Godmode command surface."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
import shlex
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Iterator

from .godmode_anchor import (
    ProjectAnchor, current_host, is_linked_worktree, primary_checkout_root, resolve_anchor,
)
from .godmode_chronicle import Chronicle, record_trust, record_writer, superseded_sequences
from .godmode_chronicle import _sequence_of as sequence_of
from .godmode_hookproof import (
    FAIL_OPEN_HOSTS, codex_runtime_premise, degraded_reason, hook_manifest_status,
    interception_state, last_latency_check, last_proof, run_probe,
)
from .godmode_githooks import (
    HOOK_NAMES as GIT_HOOK_NAMES,
    evaluate_git_hook,
    git_hooks_install,
    git_hooks_status,
    git_hooks_uninstall,
    run_git_verify,
)
from .godmode_constants import (DEFAULT_CONTEXT_BUDGET, EVENT_KINDS,
                                FORGET_PASS_SUBJECT, RUNTIME_VERSION)
from .godmode_attest import (
    split_command,
    unsupported_shell_grammar,
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
from .godmode_atlas import direction_findings, load_index, save_index, slice_file
from .godmode_attest import (
    GRADES, RESOLUTION_OUTCOMES, STATUSES, plant_and_observe, recurrences,
    reflect, run_check,
)
from .godmode_bindings import check as bindings_check
from .godmode_bindings import dependency_gate, release_checksums, sbom_cyclonedx, sbom_spdx
from .godmode_bindings import install_verify as hooks_install_verify
from .godmode_bindings import registration_report as hooks_registration_report
from .godmode_bindings import _PACKAGE_ROOT
from .godmode_bindings import sbom as build_sbom
from .godmode_bindings import write as bindings_write
from .godmode_bonds import (
    MAX_PROPOSALS_PER_SPRINT as BONDS_MAX_PROPOSALS_PER_SPRINT,
    bond_test as bonds_bond_test,
    propose as bonds_propose,
    ratify as bonds_ratify,
)
from .godmode_skillimpact import evaluate_forged_skill, validate_pattern_seqs
from .godmode_ownership import check as ownership_check
from .godmode_installmanifest import recorded_paths as installed_paths
from .godmode_charter import ADVISORY, TRIGGERS, applicable_rules, bootstrap_rules, compile_charter, traits_of
from .godmode_drift import capabilities as host_capabilities
from .godmode_changelog import check_fragments, merge_fragments
from .godmode_integrity import analyze as analyze_integrity
from .godmode_evals import (
    WITHHOLD_MEMORY_ENV,
    adversarial_grid,
    charter_snapshot,
    check_snapshots,
    cross_model_matrix,
    determinism as eval_determinism,
    ranking_snapshot,
    ratchet as eval_ratchet,
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
from . import godmode_graph
from . import godmode_looprecords
from .godmode_retest import retest_module_names
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
from .godmode_stages import (
    SOPS, ensure_sop_record, named_sop_attest, named_sop_status, skip_stage, sop_attest,
    sop_status, stage_gate,
)
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
from .godmode_profile import POLICY_FILENAME, PROFILE_NAMES, apply_profile
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
# C-9 - reviewer vs builder roles for the done-bar's own checks. A
# different "governance" than the review surface above: this one is a
# fixed table, not derived from the archive.
from .godmode_donebar import checks_table as donebar_checks_table
from .godmode_donebar import escalate as escalate_donebar_check
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
from .godmode_preview import render_preview
from .godmode_sentinel import (
    CapabilityBroker,
    attended,
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


def _positive_int(value: str) -> int:
    """Fix round 1, Q3: `atlas graph query --depth 0` (or negative) used to
    be silently promoted to depth 1 by `_bfs`'s own `max(1, depth)` - a
    caller asking to exclude neighbours entirely got them anyway. Refused
    at the parser instead, before `godmode_graph.query`'s own `ValueError`
    guard would otherwise have to surface as a bare traceback."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer; got {value!r}")
    return parsed


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
        # F5, fix round 1: so an operator can SEE that `--as-operator`
        # actually landed as `operator` (or a declared session landed as
        # `checker`) rather than silently falling back to `agent`.
        "writer": record_writer(record),
        "trust": record_trust(record),
    }


def _confirm_operator_interactively() -> bool:
    """The y/N fallback for an operator who has not run `authorize setup`.

    Called only from here, before `_append`/`Chronicle.append` is ever
    entered - never from inside the write lock (fix round 1, F0:
    `derive_writer` must never prompt, since a prompt below `append()` can
    block while holding it)."""
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, ValueError):
        interactive = False
    if not interactive:
        return False
    try:
        reply = input(
            "Confirm this write as operator (outranks agent/checker/hook "
            "records for this subject) [y/N]: "
        ).strip().lower()
    except (EOFError, OSError):  # godmode: swallow-ok: an unreadable prompt is not a "yes"
        return False
    return reply in ("y", "yes")


def _resolve_operator_verified(runtime: Runtime, args: argparse.Namespace) -> bool:
    """`--as-operator` is a claim; this is the ONE place it becomes a
    credential (fix round 1, F0) - reusing the existing password broker
    rather than adding a second check.

    Prefers the password path (`CapabilityBroker.confirm_operator`, the
    same scrypt-plus-`hmac.compare_digest` check `authorize stage`/`grant`
    already use) whenever `authorize setup` has been run; otherwise falls
    back to the interactive y/N confirmation, exactly as the pre-fix
    `Chronicle._operator_confirmed` did - just driven from here instead of
    from inside the write lock.
    """
    if not getattr(args, "as_operator", False):
        return False
    _require_archive(runtime)
    from .godmode_sentinel import _require_tty

    broker = CapabilityBroker(runtime.archive)
    if broker.configured():
        password = read_password_stdin() if getattr(args, "password_stdin", False) else None
        if password is None:
            _require_tty()
            import getpass

            password = getpass.getpass("Godmode authorization password: ")
        return broker.confirm_operator(password)
    return _confirm_operator_interactively()


def _append(
    runtime: Runtime,
    kind: str,
    subject: str,
    data: dict[str, Any],
    evidence: list[str] | None = None,
    *,
    role: str | None = None,
    as_operator: bool = False,
    operator_verified: bool | None = None,
) -> dict[str, Any]:
    _require_archive(runtime)
    return _event_view(
        runtime.archive.append(
            kind, subject, data, evidence=evidence or [],
            role=role, as_operator=as_operator, operator_verified=operator_verified,
        )
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
    adopted = None
    if orphaned and orphaned.get("adoptable"):
        # opencode field report 2026-09-10: a project that ran `git init`
        # after godmode was initialised had to find `adopt` by itself.
        # init relinks the stranded records; adopt stays for the
        # non-empty case, which needs a decision.
        adopted = runtime.archive.adopt(Path(orphaned["source"]))
    payload = {
        "initialized": True,
        "already_initialized": already,
        "identity": runtime.anchor.public_view(),
        "archive": "<git-metadata>" if runtime.anchor.is_git else "<os-application-data>",
        "network_used": False,
    }
    if orphaned and adopted:
        payload["adopted"] = adopted
        payload["next_action"] = (
            f"{orphaned['records']} records written before this project became a git "
            "repository were relinked to its git identity; nothing more to do."
        )
    elif orphaned:
        payload["orphaned_archive"] = orphaned
        payload["next_action"] = (
            "Records exist under this project's previous identity and this archive already "
            "holds records of its own. Run `adopt --confirm` to relink them, or continue and "
            "they stay unreachable."
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
    #
    # NS-12c: a brief requested from inside a memory-withheld eval run is built
    # without this project's lessons and compiled law, and says so in
    # `withheld_roles`. The mode arrives in the environment because the subject
    # here is a subprocess the harness spawned, not a caller that could pass an
    # argument; outside such a run the variable is simply absent.
    withhold_memory = os.environ.get(WITHHOLD_MEMORY_ENV) == "1"
    brief = build_brief(Path(runtime.anchor.project_root), args.task, args.token_budget,
                        withhold_memory=withhold_memory)
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


def cmd_config_mode(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """R1: print this project's mode with no `value`, or set it. `advise`
    (the default; a missing or unreadable mode file reads as `advise`)
    leaves every quality-class Stop gate advisory; `strict` is today's
    exact behaviour, unchanged. The harm gates (tag/release/push checks on
    the pre-action path) never read this - they enforce in either mode."""
    from .godmode_projectmode import project_mode, set_project_mode
    if args.value is None:
        return CommandResult({"mode": project_mode(runtime.archive)})
    set_project_mode(runtime.archive, args.value)
    return CommandResult({"mode": args.value})


OPERATOR_FILENAME = ".godmode-operator.json"
_OPERATOR_FIELDS = {
    "persona": str, "hard_gates": list, "communication": str, "decision_authority": str,
}


def cmd_operator(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """S21-06: typed operator profile, portable, with no personal name anywhere."""
    if getattr(args, "policy", False):
        # Obligation 10274: which layer decided each authorization key.
        from .godmode_sentinel import explain_policy
        return CommandResult(explain_policy(runtime.archive))
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
    role = getattr(args, "role", None) or "agent"
    # B1 (rereview round 1): `checker` must be OPERATOR-GRANTED, never a
    # bare self-declaration - verified through the exact same path as
    # every other `--as-operator` write (`_resolve_operator_verified`:
    # `authorize setup`'s password via `--password-stdin`/an interactive
    # prompt through `CapabilityBroker.confirm_operator`, or the y/N
    # fallback when no password is configured). Nothing short of that
    # verification lets `--role checker` through.
    operator_verified = _resolve_operator_verified(runtime, args)
    if role == "checker" and not operator_verified:
        raise ArchiveError(
            "`session open --role checker` requires operator verification: "
            "re-run with --as-operator (and --password-stdin, or answer the "
            "interactive prompt). A checker role is something the human "
            "operator grants; a session cannot declare it for itself."
        )
    session = open_session(
        runtime.archive, args.label, role=role, operator_verified=operator_verified)
    # B1: this process's OWN session id, so a later write in the SAME
    # process can prove which session it belongs to
    # (`Chronicle._chronicled_session_role` matches by this id, never by
    # merely being the archive's latest `session` record - a concurrent
    # process's checker session must not be inheritable by accident).
    os.environ["GODMODE_SESSION"] = session
    handshake = opening_handshake(
        runtime.archive, runtime.anchor, Path(runtime.anchor.project_root), transcript_path=getattr(args, "transcript", None)
    )
    # Promoted so --brief shows the handshake's load-bearing facts, not only
    # the session id - the opening state is the feature, not decoration.
    enforcement = handshake.get("enforcement") or {}
    grade = str(enforcement.get("tool_call_interception") or "UNAVAILABLE")
    reach = (f"host {enforcement.get('host', '?')} | pre-tool gate {grade}"
             + (" (fail-open: a refusal reaches the model after the call)" if enforcement.get("fail_open_host") else "")
             + ("; the day-one path is six verbs: init, session open, resume, remember, claim, checkpoint"
                if grade in ("PARTIAL", "SOFT", "UNAVAILABLE", "DEGRADED") else ""))
    return CommandResult({
        "reach": reach,
        "session": session,
        "role": role,
        "branch": handshake.get("branch"),
        "dirty": handshake.get("dirty_files", {}).get("count"),
        "detail": handshake.get("required_sources", {}).get("statement"),
        "handshake": handshake,
    })


def cmd_attest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    args.step = _one_text(args, "step", "step_flag", "attest step")
    if not args.step:
        raise ArchiveError("attest needs the step name: `godmode attest <step> --status ran` or --step <step>")
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
    if getattr(args, "falsifiers", False):
        # I-3: every hypothesis/incident falsifier aged past the threshold
        # with nothing run behind it - `--dry-run` lists them, otherwise
        # each due command runs through the same runner and attestation
        # `--command` uses, one at a time, so each gets its own record.
        from .godmode_falsifiers import due_falsifiers

        due = due_falsifiers(runtime.archive)
        if getattr(args, "dry_run", False):
            return CommandResult({"due": due, "count": len(due)},
                                 exit_code=1 if due else 0)
        project = Path(runtime.anchor.project_root)
        session = _session(runtime, args.session)
        ran = []
        for row in due:
            ran.append(run_check(
                runtime.archive, session, project,
                f"falsifier:{row['kind']}-{row['sequence']}",
                split_command(row["refuted_by"]),
                timeout=getattr(args, "timeout", 900),
                offline=bool(getattr(args, "offline", False)),
            ))
        return CommandResult(
            {"ran": ran, "count": len(ran)},
            exit_code=0 if all(r["passed"] for r in ran) else 1,
        )
    if not args.command:
        raise ArchiveError(
            "verify needs --command \"<the check to run>\", or --falsifiers "
            "to run the due falsifiers instead")
    outcome = run_check(
        runtime.archive, _session(runtime, args.session), Path(runtime.anchor.project_root),
        args.name, split_command(args.command), rule_ids=args.rule,
        timeout=getattr(args, "timeout", 900),
        offline=bool(getattr(args, "offline", False)),
    )
    # The runner decides, not the caller: a failing check exits non-zero here too.
    # `citation` is returned so a later claim quotes what was stored rather than
    # reconstructing it and guessing the normalisation.
    return CommandResult(outcome, exit_code=0 if outcome["passed"] else 1)


def cmd_plant(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    outcome = plant_and_observe(
        runtime.archive, _session(runtime, args.session), Path(runtime.anchor.project_root),
        args.name, split_command(args.command), target=args.file,
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


def _read_payload(path_str: str, allowed_keys: frozenset[str]) -> dict[str, Any]:
    """Read and strict-decode a `--payload` file.

    Review Q1/finding 4: every failure here - a missing/unreadable file, a
    read that is not valid text - becomes an `ArchiveError`, which
    `_dispatch` maps to the CLI's normal exit-2 error vocabulary. Before
    this helper existed, `Path(...).read_text()` was unguarded and a
    typo'd path surfaced as a raw traceback at exit 1 - the same exit code
    as a refused/downgraded record, indistinguishable to a caller reading
    only the exit status.

    Re-review round-1 residual: a non-UTF-8 file (a `>`/`Out-File` redirect
    on Windows PowerShell 5.1 writes UTF-16LE by default) raised
    `UnicodeDecodeError` - a `ValueError` subclass, not an `OSError` - so it
    slipped past the guard above and still tracebacked at exit 1. Both are
    now caught the same way: "the file could not be read as the payload it
    claims to be" is one failure class, not two. `UnicodeDecodeError` has no
    `strerror` attribute at all (unlike `OSError`) - reading it unguarded
    would itself raise `AttributeError`, so the fallback uses `getattr`.
    """
    from .godmode_strictjson import strict_loads

    path = Path(path_str)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        raise ArchiveError(f"--payload {path_str}: {detail}") from exc
    return strict_loads(text, allowed_keys)


# Review finding 4: `strict_loads` refuses an unknown *key*; these refuse a
# wrong-shaped *value* for a key it already accepted - a payload's
# `"checked": "exit code"` used to be silently laundered through a bare
# `list(...)` into four one-character entries instead of being refused.
def _payload_str(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ArchiveError(f"payload field {key!r} must be a string")
    return value


def _payload_list_str(payload: dict[str, Any], key: str) -> list[str]:
    value = payload[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ArchiveError(f"payload field {key!r} must be a list of strings")
    return value


def _payload_list_int(payload: dict[str, Any], key: str) -> list[int]:
    value = payload[key]
    if not isinstance(value, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    ):
        raise ArchiveError(f"payload field {key!r} must be a list of integers")
    return value


def _payload_dict_str_str(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload[key]
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ArchiveError(f"payload field {key!r} must be an object of string to string")
    return value


def _payload_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise ArchiveError(f"payload field {key!r} must be a boolean")
    return value


def _payload_int(payload: dict[str, Any], key: str) -> int:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArchiveError(f"payload field {key!r} must be an integer")
    return value


def _payload_number(payload: dict[str, Any], key: str) -> float:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArchiveError(f"payload field {key!r} must be a number")
    return float(value)


def _payload_checker(payload: dict[str, Any], key: str) -> list[str]:
    """`checker` accepts one command (string) or a panel (list of strings) -
    `record_verdict`'s own `checker_cmd: str | list[str]` shape."""
    value = payload[key]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return list(value)
    raise ArchiveError(f"payload field {key!r} must be a string or a non-empty list of strings")


_CLAIM_PAYLOAD_KEYS = frozenset({"text", "grade", "cites", "confidence", "external", "depends_on"})


def cmd_claim(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "payload", None):
        payload = _read_payload(args.payload, _CLAIM_PAYLOAD_KEYS)
        if "text" in payload:
            args.text_flag = _payload_str(payload, "text")
        if "grade" in payload:
            args.grade = _payload_str(payload, "grade")
        if "cites" in payload:
            args.cite = _payload_list_str(payload, "cites")
        if "confidence" in payload:
            args.confidence = _payload_number(payload, "confidence")
        if "external" in payload:
            args.external = _payload_bool(payload, "external")
        if "depends_on" in payload:
            args.depends_on = _payload_list_int(payload, "depends_on")
    args.text = _one_text(args, "text", "text_flag", "claim text")
    if getattr(args, "stale", False):
        # Grounded claims (obligation 10248): every claim whose recorded
        # evidence version no longer matches the tree.
        from .godmode_attest import stale_claims
        _require_archive(runtime)
        found = stale_claims(runtime.archive, Path(runtime.anchor.project_root))
        return CommandResult({
            "stale": len(found),
            "claims": found,
            "remedy": ("re-read the cited evidence and either re-record the claim "
                       "(`godmode claim ... --cite file:<path>#L<a>-L<b>`) or "
                       "resolve it superseded (`godmode claim --resolve <seq> "
                       "--outcome superseded`)") if found else None,
        }, exit_code=1 if found else 0)
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
             "sequence": record["sequence"],
             # An advisory nobody sees is an advisory that never happened:
             # the reversal-accounting ask lived in the record while the
             # printed payload dropped it (installed-cache test, 2026-09-03).
             **({"advisories": data["advisories"]}
                if data.get("advisories") else {})},
            exit_code=0,
        )
    if not args.text:
        return CommandResult({"refused": "claim needs the claim text, or --scan"}, exit_code=1)
    _require_archive(runtime)
    # --verify collapses the verify-then-claim two-step (field battery,
    # 2026-09-03: "improves auditability but the workflow is cumbersome"):
    # every cmd: citation is run through the attested checker FIRST, so the
    # recorded claim stands on attestations instead of drawing the
    # unbacked-cmd advisory. A failing check still records - as a claim
    # about a failing check, downgraded by its own evidence.
    check_results: list[dict[str, Any]] = []
    if getattr(args, "verify", False):
        for cite in list(args.cite or []):
            if not str(cite).startswith("cmd:"):
                continue
            # Incident 12606: a cited command runs as argv with no shell, so an
            # operator becomes a literal argument. A redirect fails loudly, but
            # an and-chain exits ZERO on its first conjunct and grades the claim
            # `verified` without ever evaluating the rest - a false green from
            # the mechanism meant to prevent them. Refuse by name instead.
            offending = unsupported_shell_grammar(str(cite)[len("cmd:"):])
            if offending:
                return CommandResult({
                    "refused": (
                        f"the citation contains {offending!r}, which a cited "
                        f"command cannot use: it is run as argv with no shell, "
                        f"so the operator would become a literal argument. An "
                        f"and-chain is the dangerous case - it exits zero on "
                        f"its first part and never runs the rest."),
                    "citation": str(cite)[:160],
                    "remedy": ("cite one command, or put the multi-step check in "
                               "a script and cite that script by path"),
                }, exit_code=1)
            outcome = run_check(
                runtime.archive, _session(runtime, args.session),
                Path(runtime.anchor.project_root),
                f"claim-verify-{len(check_results) + 1}",
                split_command(str(cite)[len("cmd:"):]),
                timeout=getattr(args, "timeout", 900) or 900,
            )
            check_results.append({"citation": outcome.get("citation"),
                                  "passed": outcome.get("passed"),
                                  "exit_code": outcome.get("exit_code"),
                                  "executed": outcome.get("exit_code") != 127})
            # The claim cites exactly what was attested - shell-splitting
            # can normalise the command string, and a near-miss cite would
            # resolve nothing.
            attested = outcome.get("citation")
            if attested and attested != cite:
                args.cite = [attested if c == cite else c
                             for c in (args.cite or [])]
    # Field feedback 2026-09-11: a claim arrived `--grade verified` beside
    # a cited check that had just failed, and the record said "verified".
    # A check run red this instant caps the grade at observed, whatever
    # the caller asserted.
    held_results: list[dict[str, Any]] = []
    if getattr(args, "verify", False):
        from .godmode_heldback import run_held_checks
        held_results = run_held_checks(runtime.archive, _session(runtime, args.session),
                                       Path(runtime.anchor.project_root),
                                       timeout=getattr(args, "timeout", 900) or 900)
    if check_results and any(not c.get("passed") for c in check_results) and args.grade == "verified":
        args.grade = "observed"
    if held_results and any(not r["passed"] for r in held_results) and args.grade == "verified":
        # The held-back oracle (2026-09-10): a check the agent did not
        # choose went red; the claim cannot be verified on the checks it did.
        args.grade = "observed"
    record = record_claim(
        runtime.archive,
        Path(runtime.anchor.project_root),
        _session(runtime, args.session),
        args.text,
        args.grade,
        cites=args.cite,
        external=args.external,
        transcript_path=getattr(args, "transcript", None),
        timeline=_load_timeline(getattr(args, "transcript", None)),
        blast_radius=getattr(args, "blast_radius", None),
        confidence=getattr(args, "confidence", None),
        refuted_by=getattr(args, "refuted_by", None),
        depends_on=getattr(args, "depends_on", None) or None,
        fixes=getattr(args, "fixes", None),
    )
    data = record["data"]
    if check_results:
        data = dict(data)
        data["verified_checks"] = check_results
    # Field report 2026-09-03 ("JSON noise with no signal about what was
    # verified"): the grade is honest but mute - one sentence names what was
    # executed versus taken on the author's word, so "observed" never reads
    # as "checked" and the path to "verified" is in the payload itself.
    cmd_count = sum(1 for c in (args.cite or []) if str(c).startswith("cmd:"))
    if check_results:
        from .godmode_attest import falsifiable

        passed = sum(1 for c in check_results if c.get("passed"))
        executed = sum(1 for c in check_results if c.get("executed", True))
        missing = [str(c.get("citation") or "")[:50] for c in check_results if not c.get("executed", True)]
        support = (f"{executed}/{len(check_results)} cited command(s) executed just now, "
                   f"{passed} passed")
        if missing:
            support += (f"; not found on this machine: {missing[0]} - a runner the shell "
                        "cannot start proves nothing; run it where it exists, then cite it")
            if re.search(r"(?i)\bcmd:(?:npx|npm|pnpm|yarn)\b", missing[0]):
                # Part 10 (2026-09-11): the hook's runner had no npx on PATH;
                # `node node_modules/vitest/vitest.mjs` attested for real.
                support += ("; a package shim is often absent from the hook's PATH - cite the "
                            "interpreter form instead, e.g. `node node_modules/<package>/<entry>.mjs`")
        elif passed < executed:
            support += "; a check that ran red caps the grade at observed"
        decoration = [str(c.get("citation") or "") for c in check_results
                      if not falsifiable(str(c.get("citation") or ""))]
        if decoration:
            support += (f"; {len(decoration)} of them cannot fail for the claim's negation "
                        f"({decoration[0][:50]}) - the grade stays below verified until a check "
                        "whose exit code contradicts the claim is cited")
    elif cmd_count:
        support = (f"nothing executed - {cmd_count} cmd cite(s) taken on the "
                   "record's word; re-run with --verify to execute them")
    else:
        support = ("nothing executed - no cmd: citation to run; the grade "
                   "rests on document/file overlap only")
    if held_results:
        held_red = sum(1 for r in held_results if not r["passed"])
        support += "; " + (
            f"{len(held_results)} held-back check(s) ran, {held_red} red"
            + (" - a check the agent did not choose disagrees; the grade stays observed" if held_red else ""))
    # Sixth field report 2026-09-05 (obligation 9313): the grade was honest
    # but the reader had to know the ladder to act on it. Name the next
    # grade and the exact flag that earns it; --brief shows the same line.
    if data["grade"] == "verified":
        next_grade, next_action = None, "verified is the top grade; nothing further to earn"
    elif cmd_count:
        next_grade = "verified"
        next_action = (f"verified: re-run with --grade verified --verify; the {cmd_count} "
                       "cmd cite(s) execute and attest")
    else:
        next_grade = "verified"
        next_action = ('verified: re-run with --grade verified --cite '
                       '"cmd:<the deciding check>" --verify')
    # A downgrade is a finding, so it must be visible in the exit status too.
    return CommandResult(
        {"claim": data["text"], "grade": data["grade"], "claimed": data["claimed_grade"],
         "support": support, "next_grade": next_grade, "next_action": next_action,
         "downgraded": data["downgraded"], "reason": data.get("reason", ""),
         "unresolved": data["unresolved"], "unsupported": data.get("unsupported", []),
         "blast_radius": data.get("blast_radius"),
         "advisories": data.get("advisories", []),
         **({"independence": data["independence"]} if data.get("independence") else {}),
         **({"verified_checks": check_results} if check_results else {})},
        exit_code=1 if data["downgraded"] else 0,
    )


def cmd_criterion(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    args.text = _one_text(args, "text", "text_flag", "criterion text")
    if not args.text:
        raise ArchiveError("criterion needs its text: `godmode criterion --task <slug> \"<what passing looks like>\"` or --text")
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


def cmd_status_bare(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """`godmode status` with no sub-command is `status survey`."""
    survey = _build_parser().parse_args(["status", "survey"])
    for key in ("json", "brief", "terse", "project"):
        if hasattr(args, key):
            setattr(survey, key, getattr(args, key))
    return survey.handler(survey, runtime)


def cmd_perimeter(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_attest import active_perimeter, perimeter_digest, record_perimeter, unrun_perimeter

    _require_archive(runtime)
    session = _session(runtime, args.session)
    if args.action == "add":
        if not args.command:
            raise ArchiveError("perimeter add needs the command: `godmode perimeter add \"python -c 'import app'\"`")
        record = record_perimeter(runtime.archive, args.command, session)
        return CommandResult({"sequence": record["sequence"], "command": record["subject"],
                              "digest": record["data"]["digest"],
                              "next": "godmode perimeter run - session close refuses until it has run this session"})
    if args.action == "retire":
        if not args.command:
            raise ArchiveError("perimeter retire needs the command it retires")
        command = " ".join(str(args.command).split())
        record = runtime.archive.append("perimeter", command, {"status": "retired", "digest": perimeter_digest(command),
                                                                "session": session}, evidence=[])
        return CommandResult({"sequence": record["sequence"], "retired": command})
    if args.action == "list":
        unrun = {entry["digest"] for entry in unrun_perimeter(runtime.archive, session)}
        rows = [{**entry, "ran_this_session": entry["digest"] not in unrun} for entry in active_perimeter(runtime.archive)]
        return CommandResult({"perimeter": rows, "unrun": len(unrun)})
    outcomes = []
    for entry in active_perimeter(runtime.archive):
        outcome = run_check(runtime.archive, session, Path(runtime.anchor.project_root),
                            f"perimeter:{entry['digest']}", split_command(entry["command"]),
                            timeout=args.timeout)
        outcomes.append({"command": entry["command"], "passed": outcome["passed"],
                         "citation": outcome.get("citation")})
    failed = [o for o in outcomes if not o["passed"]]
    return CommandResult({"ran": len(outcomes), "failed": len(failed), "outcomes": outcomes},
                         exit_code=1 if failed or not outcomes else 0)


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


_VERDICT_PAYLOAD_KEYS = frozenset({
    "claim", "value", "witness", "checker", "checked", "not_checked",
    "criteria", "run_state", "acquitted_by", "timeout", "tool_error_ack",
})


def _parse_name_value_pairs(entries: list[str], *, flag: str) -> dict[str, str]:
    """`--criterion name=evidence`, repeatable - same `name=value` shape as `--ceilings`.

    Review finding 5: a repeated name used to overwrite the earlier value
    silently, and an empty name (`--criterion =evidence`) was accepted -
    the exact "silent duplicate-key" failure `strict_loads` refuses one
    screen away, permitted here on the flag path. Both are refused now.
    """
    parsed: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise ArchiveError(f"{flag} must be name=evidence; got {entry!r}")
        name, evidence = entry.split("=", 1)
        if not name:
            raise ArchiveError(f"{flag} name cannot be empty; got {entry!r}")
        if name in parsed:
            raise ArchiveError(f"{flag} named {name!r} twice; pass it once")
        parsed[name] = evidence
    return parsed


def cmd_verdict_record(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    criteria: dict[str, str] | None = None
    if getattr(args, "payload", None):
        payload = _read_payload(args.payload, _VERDICT_PAYLOAD_KEYS)
        if "criteria" in payload and getattr(args, "criterion", None):
            # Review finding 6: this used to discard --criterion without a
            # word whenever --payload also carried 'criteria'. Refuse the
            # ambiguous combination instead of picking a silent winner.
            raise ArchiveError(
                "--payload supplies 'criteria' and --criterion was also "
                "given on the command line; pass criteria one way - drop "
                "--criterion, or drop 'criteria' from the payload"
            )
        if "claim" in payload:
            args.claim = _payload_str(payload, "claim")
        if "value" in payload:
            args.value = _payload_str(payload, "value")
        if "witness" in payload:
            args.witness = _payload_str(payload, "witness")
        if "checker" in payload:
            args.checker = _payload_checker(payload, "checker")
        if "checked" in payload:
            args.checked = _payload_list_str(payload, "checked")
        if "not_checked" in payload:
            args.not_checked = _payload_list_str(payload, "not_checked")
        if "criteria" in payload:
            criteria = _payload_dict_str_str(payload, "criteria")
        if "run_state" in payload:
            args.run_state = _payload_str(payload, "run_state")
        if "acquitted_by" in payload:
            args.acquitted_by = _payload_str(payload, "acquitted_by")
        if "timeout" in payload:
            args.timeout = _payload_int(payload, "timeout")
        if "tool_error_ack" in payload:
            args.tool_error_ack = _payload_str(payload, "tool_error_ack")
    if criteria is None:
        criteria = _parse_name_value_pairs(getattr(args, "criterion", []) or [],
                                           flag="--criterion")
    # Review finding 3: name exactly the flags that are missing, not all
    # four unconditionally - argparse used to give this precision
    # (`required=True`) before --payload needed it made optional.
    missing = [flag for flag, value in (
        ("--claim", args.claim), ("--value", args.value),
        ("--witness", args.witness), ("--checker", args.checker),
    ) if not value]
    if missing:
        return CommandResult(
            {"refused": f"verdict record needs {', '.join(missing)} "
                        "(or --payload supplying all four)"},
            exit_code=1,
        )
    record = record_verdict(
        runtime.archive,
        Path(runtime.anchor.project_root),
        args.claim,
        args.value,
        args.witness,
        args.checker,
        checked=getattr(args, "checked", []) or [],
        not_checked=getattr(args, "not_checked", []) or [],
        criteria=criteria,
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
         "checked": data.get("checked", []), "not_checked": data.get("not_checked", []),
         "criteria": data.get("criteria", {}),
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


def cmd_governance_checks(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # No archive needed: the check -> role table is fixed, not derived
    # from this project's own record (unlike the candidates `show` reads).
    return CommandResult({"checks": donebar_checks_table()}, exit_code=0)


def cmd_governance_escalate(args: argparse.Namespace,
                            runtime: Runtime) -> CommandResult:
    """A builder's recorded reason for skipping one done-bar check for a
    few turns. Exits 2, not 1, on refusal: a reviewer check or an unknown
    name is not a conflict to report, it is the command itself failing."""
    _require_archive(runtime)
    try:
        record = escalate_donebar_check(
            runtime.archive, args.check, reason=args.reason)
    except ArchiveError as error:
        return CommandResult({"refused": str(error)}, exit_code=2)
    data = record["data"]
    return CommandResult(
        {"escalated": args.check, "reason": data["reason"],
         "session": data["session"], "expires_turns": data["expires_turns"],
         "sequence": record["sequence"]},
        exit_code=0,
    )


def cmd_governance_bare(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """`governance` with no subcommand: `--checks` needs none, so it is
    served here rather than forcing a subcommand just to reach it."""
    if getattr(args, "checks", False):
        return cmd_governance_checks(args, runtime)
    return CommandResult(
        {"error": "GodmodeError",
         "message": "run `governance show`, `governance promote`, "
                    "`governance escalate`, or `governance --checks`"},
        exit_code=2,
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
    report = quality_report(Path(runtime.anchor.project_root), runtime.archive,
                            deep=bool(getattr(args, "deep", False)))
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
        # NS-13g: an RCA carrying the ritual's checklist (inline, or a label
        # naming archived `rca:<label>:<step>` items) is incomplete when it
        # skipped a step, and the step is named.
        extras: dict[str, Any] = {}
        rca = record.get("rca")
        # Present at all means read: an empty inline checklist is six
        # incomplete steps, not "no checklist".
        if "rca" in record and rca is not None:
            from .godmode_checklist import archived_rca, rca_gaps
            steps = (archived_rca(runtime.archive, str(rca)) if isinstance(rca, str)
                     else rca if isinstance(rca, dict) else {})
            rca_missing = rca_gaps(steps, contract_complete=verdict["complete"])
            extras["rca_checklist"] = {"steps": sorted(steps), "gaps": rca_missing}
            if rca_missing:
                verdict = {**verdict, "complete": False,
                           "gaps": list(verdict["gaps"]) + rca_missing}
        # An RCA cannot be published with its method incomplete.
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
    observed_in = str(getattr(args, "observed_in", "unknown") or "unknown")
    # Field report file 2026-09-10, Part 4: the decisive step of a latency
    # task was a production build re-measured before any fix; the method
    # was going to bless two wrong fixes from dev numbers.
    environment = {
        "observed_in": observed_in,
        "question": None if observed_in == "production" else (
            "was this observed in the environment where it matters? Reproduce on a production build "
            "(or the shipped configuration) before choosing a fix; dev servers double-invoke effects and "
            "serve bundles users never run. Pass --observed-in production once it is."),
    }
    return CommandResult(
        {
            "measurement_environment": environment,
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
                       session=session, charter=_charter(runtime),
                       since_days=getattr(args, "since", None))
    if getattr(args, "digest", False):
        report["digest"] = session_digest(runtime, session, getattr(args, "transcript", None))
    return CommandResult(report, exit_code=1 if report["count"] else 0)


def session_digest(runtime: Runtime, session: str | None, transcript: str | None) -> dict[str, Any]:
    """PRD P-5 / §8: the fields a reviewer needs, from records and the host
    transcript, in one object. Every field is a count or a position."""
    from .godmode_attest import calibration_digest, obligations_digest
    from .godmode_episodes import loop_episodes
    from .godmode_hookproof import interception_state
    from .godmode_iteration import measured_spend
    from .godmode_anchor import current_host

    archive = runtime.archive
    episodes = loop_episodes(transcript)
    claims = archive.select(kind="claim", limit=500)
    in_session = [c for c in claims if (c.get("data") or {}).get("session") == session]
    parked = 0
    try:
        echo = archive.root / "godmode-claim-echo.json"
        if echo.exists():
            parked = len((json.loads(echo.read_text(encoding="utf-8")) or {}).get("sentences") or [])
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a parked file that cannot be read counts as none parked
        parked = 0
    # Fix round 1: a `refusal` record carries no `session` field at all -
    # `godmode_session_hook.py` writes it mid-tool-call with no notion of
    # the chronicle's own `S-<hash>` session key - so an exact-match filter
    # on `data["session"]` matched zero refusals in every real archive and
    # counted 0 forever. `select()` also caps at 500 records regardless of
    # the limit passed in (`min(limit, 500)`), so a session with more
    # refusals than that would silently lose the rest; `read_events()` is
    # the chronicle's only unbounded read, and it has already parsed every
    # record for chain verification, so filtering it here loads no payload
    # the cap-500 path would not also have loaded.
    #
    # Fix rounds 2-3 (session-tagged refusals, `record_refusal` +
    # `resolve_host_session`) were withdrawn in round 4: no hook ever opens
    # a session with a host session id (only the CLI's `session open
    # --host-session-id` and tests did), so in a live host every refusal
    # would resolve to a `host:<id>` tag, never match this function's
    # `S-<hash>` session key, and fall out of the sequence-range fallback
    # below - the live per-session count would read 0 after release. Back
    # to round 1's rule only: membership is decided purely by sequence
    # position, which is exact for sessions that do not overlap in time
    # (see the Limits note in this fix's changelog fragment for the case
    # that remains open - two sessions genuinely concurrent on one
    # checkout).
    all_records = archive.read_events()
    session_start = 0
    session_end = None  # exclusive upper bound; None means "to the end"
    if session is not None:
        found_start = False
        for record in all_records:
            if record["kind"] != "session":
                continue
            if not found_start:
                if f"S-{record['record_hash'][:12]}" == session:
                    session_start = record["sequence"]
                    found_start = True
                continue
            # The next session-kind record after the match bounds this
            # session from a LATER one also present in the archive - needed
            # for an explicit, non-latest `session` argument; the latest
            # session (the common case) has no later boundary, so this
            # never triggers and `session_end` stays None.
            session_end = record["sequence"]
            break

    def _belongs(record: dict[str, Any]) -> bool:
        return (record["sequence"] >= session_start
                and (session_end is None or record["sequence"] < session_end))

    refusals = [r for r in all_records if r["kind"] == "refusal" and _belongs(r)]
    gate = {"would-deny": sum(1 for r in refusals if (r.get("data") or {}).get("observed") and (r.get("data") or {}).get("would_have") == "deny"),
            "would-ask": sum(1 for r in refusals if (r.get("data") or {}).get("observed") and (r.get("data") or {}).get("would_have") == "ask"),
            "denied": sum(1 for r in refusals if not (r.get("data") or {}).get("observed"))}
    grades = {}
    for c in in_session:
        grades[str((c.get("data") or {}).get("grade"))] = grades.get(str((c.get("data") or {}).get("grade")), 0) + 1
    obligations = obligations_digest(archive)
    spend = measured_spend(transcript)
    # NS-10d: a host-reported usage total takes priority over the
    # transcript-measured figure above. Fix round 2 (review S4/N1/N4): this
    # now calls the SAME `usage_ledger_totals` `check_ceilings`'s caller
    # uses, rather than a separate ad-hoc sum here - round 1 windowed this
    # by `_belongs()`'s sequence range keyed on `session` (`kind="session"`
    # only, `None` on every hook-only archive, degenerating to "the whole
    # archive" exactly like the ceiling's own round-1 bug), and summed both
    # Stop and SessionEnd records with no de-dup. `usage_ledger_totals`
    # windows by the hook's own session-anchor boundary and prefers Stop
    # over SessionEnd, so the digest and the ceiling never disagree about
    # what "this session" spent. Gated on the total itself being nonzero,
    # not merely on a record existing (S3): a zero-valued usage record must
    # not erase a real transcript-measured figure with
    # `source: host, tokens: 0`.
    #
    # Final review S6 (Task 7/12 D2): every OTHER field in this digest
    # (`refusals`, `gate`, `grades`) is windowed by THIS call's own
    # `session_start`/`session_end` - the boundary an explicit, older
    # `--session` argument resolves to, above - but `usage_ledger_totals`
    # used to ignore that entirely and window by the newest hook-session
    # anchor regardless, so a digest for an older session reported the
    # CURRENT session's host spend under `"source": "host"`. Passed through
    # only when `session` was actually given; `None` (the common case: no
    # `--session`, or the caller wants the latest one) keeps the previous
    # "newest anchor" behaviour exactly, via `usage_ledger_totals`'s own
    # `start=None` default.
    from .godmode_guardrails import usage_ledger_totals
    usage_totals = usage_ledger_totals(
        archive,
        start=session_start if session is not None else None,
        end=session_end if session is not None else None,
    )
    host_tokens = usage_totals["total_tokens"]
    if host_tokens:
        spend_view = {
            "tokens": host_tokens, "source": "host", "messages": 0,
            "records": usage_totals["records"],
            "input_tokens": usage_totals["input_tokens"], "output_tokens": usage_totals["output_tokens"],
            "cache_read_tokens": usage_totals["cache_read_tokens"],
        }
    else:
        spend_view = {"tokens": spend["tokens"], "source": spend["source"], "messages": spend["messages"]}
    next_action = None
    if episodes["loop_detected"]:
        e = episodes["loop_detected"][0]
        next_action = f"a loop of {e['attempts']} attempts on one error class; record the premise as failed and re-read the artifact"
    elif obligations["open"]:
        next_action = f"{obligations['open']} obligation(s) open; `godmode status remaining` lists them"
    elif parked:
        next_action = f"{parked} claim(s) parked unrecorded; record or soften them"
    return {
        "session": session,
        "loop_episodes": len(episodes["episodes"]),
        "loops_detected": len(episodes["loop_detected"]),
        "error_classes": len({e["signature"] for e in episodes["episodes"]}),
        "last_new_information_turn": episodes["last_new_information_turn"],
        "claims": {"recorded": len(in_session), "by_grade": grades, "parked": parked},
        "obligations": obligations,
        "gate": gate,
        "spend": spend_view,
        "host": {"name": current_host(), "grade": interception_state(archive, current_host()) if archive.initialized() else "UNAVAILABLE"},
        "calibration": calibration_digest(archive),
        "next_action": next_action or "nothing open on the record",
    }


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


def cmd_retest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_retest import retest_plan

    project = Path(runtime.anchor.project_root)
    plan = retest_plan(project, base=args.base)
    if not args.run:
        return CommandResult(plan, exit_code=0)
    _require_archive(runtime)
    session = _session(runtime, args.session)
    outcomes = []
    for entry in plan["commands"]:
        if not entry.get("command"):
            continue
        argv = split_command(entry["command"])
        if argv and argv[0] == "python":
            argv[0] = sys.executable
        outcome = run_check(runtime.archive, session, project, f"retest:{entry['runner']}", argv,
                            timeout=args.timeout, modules=entry.get("modules"),
                            blob_paths=entry.get("pinned_sources"))
        outcomes.append({"runner": entry["runner"], "passed": outcome["passed"], "citation": outcome.get("citation")})
    plan["outcomes"] = outcomes
    failed = [o for o in outcomes if not o["passed"]]
    if not failed:
        # I-6 fix round 2 (D2): the moment this project's own tests just ran
        # green is exactly the moment a saved atlas index is trustworthy to
        # write - best-effort, never affects this command's own exit code.
        from .godmode_closure import refresh_atlas_index
        refresh_atlas_index(project)
    return CommandResult(plan, exit_code=1 if failed else 0)


def cmd_ratchet(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_ratchet import declared_ratchets, last_values, run_ratchets

    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    if args.action == "list":
        declared = declared_ratchets(project)
        previous = last_values(runtime.archive)
        return CommandResult({"declared": [{"name": n, "last": (previous.get(n) or {}).get("value")}
                                           for n in declared]})
    report = run_ratchets(runtime.archive, project, timeout=args.timeout)
    return CommandResult(report, exit_code=0 if report["ok"] else 1)


def cmd_release_notes(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_constants import RUNTIME_VERSION
    from .godmode_release_notes import build_notes, check_notes

    version = str(args.version or RUNTIME_VERSION)
    project = Path(runtime.anchor.project_root)
    if args.action == "build":
        report = build_notes(project, version, force=bool(args.force))
        return CommandResult(report, exit_code=0 if report.get("written") else 1)
    report = check_notes(project, version)
    return CommandResult(report, exit_code=0 if report["ok"] else 1)


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

    record = amend_law(
        runtime.archive, args.law, args.guard,
        as_operator=getattr(args, "as_operator", False),
        operator_verified=_resolve_operator_verified(runtime, args),
    )
    if record["pending"]:
        note = ("amendment recorded but PENDING: written without operator "
                "trust, so the law's last authorised guard stays in force "
                "until a second actor approves this one or the operator "
                "re-issues it with --as-operator; run `law compile` to see "
                "the [AMENDMENT PENDING] marker")
    else:
        note = "this record is the law; run `law compile` to regenerate the file"
    return CommandResult({"amended": record["sequence"],
                          "pending": record["pending"], "note": note})


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


def _loop_threshold(runtime: Runtime) -> int:
    """PRD §13 question 1, answered: novice 4, standard 6, strict 8."""
    from .godmode_episodes import THRESHOLDS
    try:
        from .godmode_sentinel import local_authorization_policy
        profile = str(local_authorization_policy(runtime.archive).get("profile") or "standard")
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable policy means the standard threshold
        profile = "standard"
    return THRESHOLDS.get(profile, THRESHOLDS["standard"])


def cmd_loop(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "transcript", None):
        from .godmode_episodes import backtrack_context, loop_episodes
        from .godmode_profile import PROFILE_NAMES  # noqa: F401
        threshold = _loop_threshold(runtime)
        report = loop_episodes(args.transcript, threshold=threshold)
        if getattr(args, "episodes", False):
            report["backtrack"] = [backtrack_context(runtime.archive, e) for e in report["loop_detected"]]
        if report["loop_detected"] and runtime.archive.initialized():
            try:
                runtime.archive.append("action", "would-have-stopped-loop", {
                    "episodes": len(report["loop_detected"]),
                    "attempts": report["loop_detected"][0]["attempts"],
                    "signature": report["loop_detected"][0]["signature"]}, evidence=[])
            except Exception:  # noqa: BLE001  # godmode: swallow-ok: the observe receipt is best-effort; the report still answers
                pass
        return CommandResult(report, exit_code=1 if report["loop_detected"] else 0)
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
    return CommandResult(f"[GODMODE {marker} {grade}]")


def time_hook(project: Path, event: str, runs: int = 3, host: str | None = None) -> dict[str, Any]:
    """Wall-clock of the real hook script on a synthetic payload (the Grok
    timing probe, ledgered 2026-09-07: a host measured 14.8 s for a
    session start that ran in 0.6 s here). Reported beside the declared
    timeout so a host that is slow to launch interpreters is named as
    such, not guessed at."""
    import subprocess
    import time as _time

    from .godmode_hookproof import _pretool_timeout_ms

    hook = _PLUGIN_ROOT / "hooks" / "godmode_session_hook.py"
    payload = {"session-start": {"hook_event_name": "SessionStart", "cwd": str(project)},
               "pre-action": {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                              "tool_input": {"command": "git status --short"}, "cwd": str(project)},
               "stop": {"hook_event_name": "Stop", "cwd": str(project), "stop_hook_active": False}}[event]
    elapsed: list[int] = []
    for _ in range(runs):
        started = _time.perf_counter()
        subprocess.run([sys.executable, "-I", "-B", str(hook), event, "--project", str(project)],
                       input=json.dumps(payload), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
        elapsed.append(int((_time.perf_counter() - started) * 1000))
    ordered = sorted(elapsed)
    declared = _pretool_timeout_ms(host or current_host()) if event == "pre-action" else None
    return {"event": event, "runs": runs, "elapsed_ms": elapsed, "median_ms": ordered[len(ordered) // 2],
            "declared_timeout_ms": declared,
            "verdict": ("over the declared timeout" if declared and ordered[len(ordered) // 2] > declared
                        else "within the declared timeout" if declared else "no declared timeout for this event")}


def cmd_hygiene(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_hygiene import hygiene
    _require_archive(runtime)
    report = hygiene(runtime.archive.select(limit=500), cap=int(getattr(args, "cap", 80) or 80))
    return CommandResult(report, exit_code=0)


def cmd_forget(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """NS-11e + NS-11g (0.3.28 Plan 5 Task 7): expire episodic records past
    TTL into a rotated cold segment, report supersession chains, and flag
    same-subject value contradictions among active records. `--dry-run`
    performs every read a real pass would but writes nothing (proved by a
    digest over the record files, the cold segments and the cold registry).

    Fix round 1 (review A, B5): `--now` is accepted on a PREVIEW only. A
    fabricated clock in the far future makes every episodic record eligible
    at once, so `godmode forget --now 2999-01-01` was a one-call lever that
    emptied the hot tier of every `action`, `refusal` and `attestation` -
    unauthenticated, from any agent, with no gate row behind it. A write
    pass now always uses the real time; the preview is where a fabricated
    one belongs, because a preview writes nothing.
    """
    from .godmode_forget import forget
    _require_archive(runtime)
    now = getattr(args, "now", None)
    dry_run = bool(getattr(args, "dry_run", False))
    if now is not None and not dry_run:
        raise ArchiveError(
            "`--now` fabricates the clock every TTL is measured against, so it is "
            "accepted only on a preview: run `godmode forget --dry-run --now "
            f"{now}` to see what that time would expire, or drop `--now` to run "
            "the real pass against the real clock"
        )
    report = forget(runtime.archive, now=now, dry_run=dry_run)
    return CommandResult(report)


def cmd_oracle(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_heldback import held_checks, hold_check, run_held_checks
    _require_archive(runtime)
    if args.oracle_command == "hold":
        if getattr(args, "password_stdin", False):
            password = read_password_stdin()
        else:
            from .godmode_sentinel import _require_tty
            _require_tty()
            import getpass
            password = getpass.getpass("Godmode authorization password: ")
        return CommandResult(hold_check(runtime.archive, args.command, password))
    if args.oracle_command == "list":
        return CommandResult({"held": [{"digest": c["digest"]} for c in held_checks(runtime.archive)],
                              "note": "commands stay under the git metadata directory; the digest is the handle"})
    results = run_held_checks(runtime.archive, _session(runtime, getattr(args, "session", None)),
                              Path(runtime.anchor.project_root), timeout=int(getattr(args, "timeout", 900) or 900))
    red = [r for r in results if not r["passed"]]
    return CommandResult({"ran": len(results), "red": len(red), "results": results},
                         exit_code=1 if red else 0)


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
        if getattr(args, "write", False) and not getattr(args, "matrix", False):
            # Fix round 1, nit 5: `--write` outside `--matrix` used to be
            # silently accepted and ignored (the non-matrix branch below
            # never reads it) - an operator asking to write got a read-only
            # report with no signal anything was skipped.
            return CommandResult(
                {"error": "--write only applies with --matrix; "
                          "hooks status --write alone has nothing to write"},
                exit_code=2)
        if getattr(args, "matrix", False):
            # R-4 + R-0 guard: `docs/HOST-FEATURE-REACH.md` generated from
            # `godmode_reach`'s own tables and `godmode_host_manifests.
            # HOST_CAPABILITIES` - never hand-typed. The R-0 guard
            # (`MatrixGuardError`) refuses before touching the file if a
            # hook host cites neither a reference nor a replicating test.
            from .godmode_reach import MatrixGuardError, generate_matrix_document

            doc_path = Path(__file__).resolve().parents[2] / "docs" / "HOST-FEATURE-REACH.md"
            current_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
            try:
                generated = generate_matrix_document(current_text)
            except MatrixGuardError as exc:
                return CommandResult(
                    {"matrix": "refused", "path": str(doc_path), "reason": str(exc)},
                    exit_code=2)
            changed = generated != current_text
            if getattr(args, "write", False):
                if changed:
                    doc_path.write_text(generated, encoding="utf-8", newline="\n")
                return CommandResult(
                    {"matrix": "written" if changed else "current", "path": str(doc_path)})
            return CommandResult(
                {"matrix": "drifted" if changed else "current", "path": str(doc_path)},
                exit_code=1 if changed else 0)
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
            # Feature reach per host (2026-09-09, obligation 10119): which
            # hook-borne feature can fire on this host and why not.
            "reach": __import__(
                "godmode_runtime.godmode_reach", fromlist=["reach_table"]
            ).reach_table().get(host, {}),
            # R-3a: the named fallback tier (hook/shim/mcp/none) instead of
            # leaving a host with no hook dispatch to read as
            # "unverifiable" - `validate_tiers()` is what fails a row
            # missing one.
            "tier": __import__(
                "godmode_runtime.godmode_reach", fromlist=["host_tier"]
            ).host_tier(host),
            # R-5: absent/in-sync/drifted per host, from the exact same
            # rendering and comparisons `hooks wire --all` uses - status
            # can never claim a state wiring itself would disagree with.
            "wire_state": __import__(
                "godmode_runtime.godmode_wire", fromlist=["wire_status"]
            ).wire_status(Path(runtime.anchor.project_root)),
        }
        payload.update(_hooks_health_fields(runtime.archive, host, level))
        if host == "codex":
            # N-13: the installed-runtime premise, read fresh (never cached
            # or guessed) so `hooks status` never claims a premise this
            # machine did not just check.
            payload["premise"] = codex_runtime_premise()
        # C-6: read what the installer/`bindings --write`/`hooks wire`
        # actually recorded (`<project>/.godmode/godmode/install-manifest.
        # json`) instead of guessing from a glob - and flag any recorded
        # path that no longer exists on disk.
        recorded = installed_paths(runtime.anchor.project_root, "godmode")
        missing = [p for p in recorded
                   if not (Path(runtime.anchor.project_root) / p).exists()]
        payload["install_manifest"] = {"recorded": recorded, "missing": missing}
        return CommandResult(payload)
    if args.hooks_command == "time":
        return CommandResult(time_hook(Path(runtime.anchor.project_root), args.event,
                                       runs=max(1, int(args.runs)), host=host))
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
        from . import godmode_wire

        plugin_root = Path(__file__).resolve().parents[2]
        wire_host_arg = getattr(args, "host", None)
        wire_host = wire_host_arg or "codex"
        wire_all = getattr(args, "all", False)
        dry_run = getattr(args, "dry_run", False)
        if wire_all and wire_host_arg:
            # N6: `--all` used to silently win over an explicit `--host`,
            # so an operator who meant to scope to one host got every host
            # wired instead with no indication their flag was ignored.
            return CommandResult(
                {"error": "hooks wire --all wires every known host; pass either "
                          "--all or --host, not both"},
                exit_code=1,
            )
        if wire_all or dry_run:
            # R-5: one function, two modes - `--all` and `--dry-run` both
            # go through `godmode_wire.wire()`, the same code an apply
            # uses, so a preview can never diverge from what applying it
            # actually does.
            hosts = list(godmode_wire.WIRE_HOSTS) if wire_all else [wire_host]
            unknown = [h for h in hosts if h not in godmode_wire.WIRE_HOSTS]
            if unknown:
                # N7: an unknown host (e.g. `--dry-run --host grok`) used to
                # reach `_plan_host` and raise `GodmodeError`; give the same
                # friendly message the non-dry-run fallback below does.
                return CommandResult(
                    {"error": "hooks wire knows codex (project hooks fallback), "
                              "opencode (Bun shim install), antigravity "
                              "(.agents/hooks.json merge), copilot "
                              "(.github/hooks/godmode.json + copilot-instructions.md "
                              "merge), and kiro (.kiro/hooks.json merge) today"},
                    exit_code=1,
                )
            if "codex" in hosts and is_linked_worktree(runtime.anchor):
                # N-13: refuse before any write, for the whole batch - a
                # linked worktree wiring its own `.codex/hooks.json` would
                # drift from the primary checkout the operator actually
                # trusts commands in, so nothing else in the batch writes
                # either.
                primary = primary_checkout_root(runtime.anchor)
                return CommandResult(
                    {"refused": "hooks wire --host codex refuses from a linked "
                                "worktree; run it from the primary checkout",
                     "host": "codex",
                     "primary_checkout": str(primary) if primary else None},
                    exit_code=2,
                )
            report = godmode_wire.wire(
                Path(runtime.anchor.project_root), hosts,
                dry_run=dry_run, force=getattr(args, "force", False))
            return CommandResult(
                report, exit_code=0 if report["summary"] == "safe to apply" else 1)
        if wire_host == "codex" and is_linked_worktree(runtime.anchor):
            # N-13: refuse before any write - a linked worktree wiring its
            # own `.codex/hooks.json` would drift from the primary checkout
            # the operator actually trusts commands in.
            primary = primary_checkout_root(runtime.anchor)
            return CommandResult(
                {"refused": "hooks wire --host codex refuses from a linked "
                            "worktree; run it from the primary checkout",
                 "host": "codex",
                 "primary_checkout": str(primary) if primary else None},
                exit_code=2,
            )
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
        if wire_host in godmode_wire.WIRE_HOSTS:
            # NS-6 (Task 6): Copilot and Kiro have no legacy dedicated
            # writer function - `hooks wire --host copilot|kiro` routes
            # straight through `godmode_wire.wire()`, the same code `--all`
            # and `--dry-run` already use, rather than growing a fourth
            # `write_*_project_*` function this task's own plan never asks
            # for. Any future `WIRE_HOSTS` addition with no dedicated
            # branch above falls through here the same way.
            report = godmode_wire.wire(
                Path(runtime.anchor.project_root), [wire_host],
                dry_run=False, force=getattr(args, "force", False))
            return CommandResult(
                report, exit_code=0 if report["summary"] == "safe to apply" else 1)
        return CommandResult(
            {"error": "hooks wire knows codex (project hooks fallback), "
                      "opencode (Bun shim install), antigravity "
                      "(.agents/hooks.json merge), copilot "
                      "(.github/hooks/godmode.json + copilot-instructions.md "
                      "merge), and kiro (.kiro/hooks.json merge) today"},
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


def cmd_ownership(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """C-6: which gate rule owns each path, and whether the decision table
    the fast gate reads is still fresh against the sentinel that generated
    it - the 0.3.27 miss. Exit 1 on a stale table; the walk itself never
    fails the exit code (an unowned path is reported, not refused)."""
    project = Path(runtime.anchor.project_root)
    report = ownership_check(project, diff_only=getattr(args, "diff_only", False))
    return CommandResult(report, exit_code=0 if report["table_fresh"] else 1)


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
    if getattr(args, "against", None):
        from .godmode_registry import match_feedback, parse_registry, registry_path

        project = Path(runtime.anchor.project_root)
        path = registry_path(project, getattr(args, "registry", None))
        if path is None:
            return CommandResult({"refused": "no fixed registry found (docs/FIXED-REGISTRY.md or --registry PATH)"},
                                 exit_code=1)
        rows = parse_registry(path)
        matches = match_feedback(str(args.against), rows)
        return CommandResult({"registry": str(path.relative_to(project)).replace("\\", "/"), "rows": len(rows),
                              "matches": matches,
                              "next": ("run each match's guard before treating the report as new; a green guard "
                                       "over a recurrence means the guard pinned the incident, not the class")
                              if matches else "no registry row shares two distinctive words with this text"},
                             exit_code=0)
    _require_archive(runtime)
    if getattr(args, "propose", False):
        from .godmode_registry import proposed_rows
        rows = proposed_rows(runtime.archive.select(limit=500))
        return CommandResult({"proposed": rows,
                              "next": ("each row is a class the record waived three times with one reason; "
                                       "add it to the fixed registry with a guard, or name why it is not a class")
                              if rows else "no reason recurs three times across waived work"},
                             exit_code=0)
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
    if getattr(args, "direction", False):
        # A static check, not a build: it reads source files directly, so it
        # never pays for (or waits on) an atlas build, and it needs no
        # subcommand - `atlas --direction` alone is a complete gate.
        project_root = Path(runtime.anchor.project_root)
        if not (project_root / "hooks").is_dir() or not (project_root / "scripts" / "godmode_runtime").is_dir():
            # No hooks/ and scripts/godmode_runtime/ trees to compare means
            # the check has nothing to say - reported as inapplicable, not
            # as a clean scan that never actually looked at anything.
            return CommandResult({
                "applicable": False,
                "message": "no hooks/ and scripts/godmode_runtime/ directories found; "
                           "dependency-direction check does not apply here",
            })
        findings = direction_findings(project_root)
        return CommandResult({"applicable": True, "findings": findings},
                             exit_code=1 if findings else 0)
    if args.atlas_command is None:
        raise GodmodeError("atlas requires a subcommand (e.g. map, diagnose) or --direction")
    if args.atlas_command == "load":
        # Load must not rebuild: the whole point is answering from the saved map
        # while stating how much of it is still true.
        report = load_index(Path(runtime.anchor.project_root) / args.source,
                            Path(runtime.anchor.project_root))
        return CommandResult(report, exit_code=0 if report["confidence"] == 1.0 else 1)
    if args.atlas_command == "graph":
        # NS-3: a projection of the ARCHIVE's own records, never the symbol
        # atlas `build_atlas` below produces - no project scan is needed
        # (or wanted; `godmode_graph.rebuild` takes the archive alone), so
        # this branch returns before the symbol atlas ever builds.
        _require_archive(runtime)
        return _atlas_graph(args, runtime)
    if args.atlas_command == "loop":
        # NS-1: loop records over the archive alone, same reasoning as
        # "graph" above - no symbol atlas is needed.
        _require_archive(runtime)
        return _atlas_loop(args, runtime)
    if args.atlas_command == "law":
        # NS-4: falsification bonds over the ARCHIVE's own records, same
        # shape as `graph` above - no symbol atlas is needed, so this
        # branch also returns before `build_atlas` ever runs.
        _require_archive(runtime)
        return _atlas_law(args, runtime)
    atlas = build_atlas(Path(runtime.anchor.project_root),
                        budget_seconds=args.budget if args.budget > 0 else None)
    result = _atlas_query(args, runtime, atlas)
    if atlas.gap and isinstance(result.payload, dict):
        # A bounded map answers every query with the bound attached; a
        # dependents list from a half-read repo is otherwise indistinguishable
        # from a complete one.
        result.payload["gap"] = atlas.gap
    return result


def _atlas_graph(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """`atlas graph rebuild|query|verify` - NS-3's typed, time-valid
    evidence graph, a projection of the archive's own records
    (`godmode_graph.py`), never a second store."""
    graph_command = getattr(args, "graph_command", None)
    if graph_command is None:
        raise GodmodeError("atlas graph requires a subcommand (rebuild, query, verify)")
    if graph_command == "rebuild":
        built = godmode_graph.rebuild(runtime.archive)
        godmode_graph.save_snapshot(built, runtime.archive)
        return CommandResult({
            "nodes": len(built["nodes"]), "edges": len(built["edges"]), "hash": built["hash"],
        })
    if graph_command == "verify":
        outcome = godmode_graph.verify(runtime.archive)
        return CommandResult(outcome, exit_code=0 if outcome["verified"] else 1)
    if graph_command == "query":
        # Scale rule (design NS-3): BFS bounded by depth over a CACHED
        # snapshot; full recompute only happens on `rebuild`, never per
        # query - so this loads the last snapshot rather than rebuilding.
        snapshot = godmode_graph.load_snapshot(runtime.archive)
        if snapshot is None:
            return CommandResult({
                "refused": True,
                "reason": "no graph snapshot found; run atlas graph rebuild",
            }, exit_code=1)
        return _atlas_graph_query(args, runtime, snapshot)
    raise GodmodeError(f"Unknown atlas graph subcommand: {graph_command}")


def _atlas_graph_query(args: argparse.Namespace, runtime: Runtime, snapshot: dict[str, Any]) -> CommandResult:
    """`atlas graph query <node>` over the loaded `snapshot`.

    Fix round 1, S1: `must_retest` alone can never answer "what must this
    change retest" for a FILE, because `rebuild` only ever mints
    `module:`/`attestation:` nodes (no `file:` node kind exists in the
    graph itself - see `godmode_graph.py`'s own divergence note). This
    bridges a `file:<path>` node (or a bare node id that resolves as a
    real project-relative path when it names nothing in the snapshot) to
    its `module:` node ids through `godmode_retest.retest_module_names` -
    the SAME file->module bridge `godmode_closure` and `godmode_reversals`
    use, imported here rather than reimplemented - and unions their
    `must_retest` sets. A node id that resolves to neither a snapshot node
    NOR a bridged module reports `"unknown_node": true`, so an empty
    result is never mistaken for "nothing depends on it".
    """
    node = args.node
    nodes = snapshot.get("nodes") or {}
    path = node[len("file:"):] if node.startswith("file:") else None
    if path is None and node not in nodes:
        # A bare id that names nothing in the snapshot may still be a
        # project-relative path the caller did not bother to prefix.
        candidate = (Path(runtime.anchor.project_root) / node)
        if candidate.is_file():
            path = node
    bridged_module_ids: list[str] = []
    if path is not None:
        modules = retest_module_names(Path(runtime.anchor.project_root), [path])
        bridged_module_ids = sorted(f"module:{module}" for module in modules)
    direct_hit = node in nodes
    bridge_hits = [module_id for module_id in bridged_module_ids if module_id in nodes]
    if not direct_hit and not bridge_hits:
        return CommandResult({
            "node": node, "depth": args.depth, "impact": [], "must_retest": [],
            "unknown_node": True,
            "refused": True, "reason": f"unknown node: {node}",
        }, exit_code=1)
    impact: dict[str, int] = {}
    must_retest: dict[str, int] = {}

    def _merge(target: dict[str, int], entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            distance = int(entry["distance"])
            existing = target.get(entry["node"])
            if existing is None or distance < existing:
                target[entry["node"]] = distance

    if direct_hit:
        direct = godmode_graph.query(snapshot, node, depth=args.depth)
        _merge(impact, direct["impact"])
        _merge(must_retest, direct["must_retest"])
    for module_id in bridge_hits:
        bridged = godmode_graph.query(snapshot, module_id, depth=args.depth)
        _merge(must_retest, bridged["must_retest"])
    return CommandResult({
        "node": node, "depth": args.depth,
        "impact": [{"node": n, "distance": d} for n, d in sorted(impact.items(), key=lambda kv: (kv[1], kv[0]))],
        "must_retest": [{"node": n, "distance": d}
                        for n, d in sorted(must_retest.items(), key=lambda kv: (kv[1], kv[0]))],
    })


def _atlas_loop(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """`atlas loop advance|resume` - NS-1's loop records
    (`godmode_looprecords.py`): a chained failure signature per attempt,
    refused (exit 2, `loop_halt` recorded) the third time it repeats, and
    reopened only by `resume` evidence from a different actor than the
    one who hit the halt. Budgets - an operator's own stop flag, then
    steps, tokens, wall time - are checked before the signature test ever
    runs; each exhaustion is its own named halt reason.
    """
    loop_command = getattr(args, "loop_command", None)
    if loop_command is None:
        raise GodmodeError("atlas loop requires a subcommand (advance, resume)")
    project_root = Path(runtime.anchor.project_root)
    if loop_command == "advance":
        result = godmode_looprecords.advance(
            runtime.archive, project_root, task=args.task,
            failing_test_ids=args.failing, diff_from_git=args.diff_from_git,
        )
        return CommandResult(result, exit_code=2 if result["halted"] else 0)
    if loop_command == "resume":
        result = godmode_looprecords.resume(
            runtime.archive, task=args.task, evidence_cite=args.evidence)
        return CommandResult(result, exit_code=0 if result["resumed"] else 2)
    raise GodmodeError(f"Unknown atlas loop subcommand: {loop_command}")
def _atlas_law(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """`atlas law propose|bond-test|ratify` - NS-4's falsification bonds.

    Kept as its own console hunk, separate from `remember --kind lesson`
    and `godmode_law.py`'s enforce predicates (a different Plan 5 task owns
    those): every write here goes through `godmode_bonds`, which is the
    only place that knows the proposal cap, the bond-session matching, and
    the proposer/checker separateness check.
    """
    law_command = getattr(args, "atlas_law_command", None)
    if law_command is None:
        raise GodmodeError("atlas law requires a subcommand (propose, bond-test, ratify)")
    if law_command == "propose":
        outcome = bonds_propose(
            runtime.archive, args.target, args.diff, list(args.cite or []),
            project=Path(runtime.anchor.project_root),
        )
        return CommandResult(outcome)
    if law_command == "bond-test":
        outcome = bonds_bond_test(
            runtime.archive, Path(runtime.anchor.project_root),
            args.name, split_command(args.command), args.file,
            replace=args.replace, with_text=args.with_text, append=args.append,
            rule_ids=args.rule,
        )
        # A bond that never went red proves nothing - the same "exit
        # non-zero on an unproven guard" contract `cmd_plant` already uses.
        return CommandResult(outcome, exit_code=0 if outcome["failed_as_expected"] else 1)
    if law_command == "ratify":
        outcome = bonds_ratify(
            runtime.archive, args.proposal_seq,
            project=Path(runtime.anchor.project_root),
            diff_path=getattr(args, "diff", None),
            patterns=list(getattr(args, "pattern", None) or []),
        )
        return CommandResult(outcome)
    raise GodmodeError(f"Unknown atlas law subcommand: {law_command}")


def _atlas_query(args: argparse.Namespace, runtime: Runtime, atlas: Any) -> CommandResult:
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
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: deliberate broad handler: this boundary never raises into the host
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
        # NS-3: a closure decision is a claim about impact, and an
        # unverified (or stale) evidence graph makes that claim on
        # evidence that may no longer match the archive. Only gated when
        # an archive actually exists - a project with none has never had
        # a graph to verify, and closure's atlas-only behaviour there is
        # unchanged.
        if runtime.archive.initialized():
            verification = godmode_graph.verify(runtime.archive)
            if not verification["verified"]:
                return CommandResult({
                    "refused": True,
                    "reason": "graph unverified: run atlas graph rebuild",
                    "verify": verification,
                }, exit_code=1)
        # Changed files come from the caller or from the working tree. Reading
        # the tree by default is what makes this runnable at the moment it
        # matters - nobody thinks to list what they just edited, which is the
        # same reason `affected` stayed a query nobody ran.
        listed = list(args.changed or []) + list(getattr(args, "changed_positional", None) or [])
        changed = listed if listed else _working_tree_changes(
            Path(runtime.anchor.project_root))
        report = unfollowed_dependents(atlas, changed, depth=args.depth)
        from .godmode_atlas import prose_mentions
        report["prose"] = prose_mentions(Path(runtime.anchor.project_root), changed)
        if report["prose"]:
            report["prose_note"] = ("documents and comments that name a symbol the change defines - "
                                    "read each for a sentence that was true before the change and is false now")
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
    brief = build_context_brief(
        runtime.anchor,
        runtime.archive,
        current_inventory=current,
        token_budget=args.token_budget,
    )
    # Grok field report 2026-09-10: `resume --brief` printed `records=3`.
    # The scalars a model can work from ride the top of the payload.
    try:
        from .godmode_lens import ledger_block, precedence_block, catch_up_block
        ledger = ledger_block(runtime.archive)
        from .godmode_anchor import run_git
        dirty = len([l for l in (run_git(Path(runtime.anchor.project_root), "status", "--porcelain") or "").splitlines() if l.strip()])
        checkpoints = [r for r in runtime.archive.select(kind="checkpoint", limit=50)]
        next_steps = ((checkpoints[-1].get("data") or {}).get("next") or []) if checkpoints else []
        # NS-8m: declared state (named directly by a plan/checkpoint record)
        # lists before inferred state (computed by scanning the archive), and
        # a disagreement between the two is named rather than silently
        # resolved. `precedence_block` reuses the same `dirty` count computed
        # here so the scalar and the precedence row agree.
        precedence = precedence_block(runtime.archive, dirty=dirty)
        catch_up = catch_up_block(runtime.archive)
        brief = {
            "goal": ledger.get("goal"),
            "current_step": ledger.get("current_step"),
            "next": (next_steps[0] if next_steps else None),
            "dirty": dirty,
            "open_obligations": ledger.get("open_obligations"),
            "precedence": precedence["precedence"],
            "conflicts": precedence["conflicts"],
            "catch_up": catch_up["catch_up"],
            **brief,
        }
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: the brief still prints when the scalars cannot be derived
        pass
    return CommandResult(brief)


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
    if getattr(args, "rebaseline", False):
        # Drift above was measured against the OLD baseline; the new one is
        # written after, so the report shows what was accepted. Refused
        # without --scan: accepting a tree nobody measured is not review.
        if not args.scan:
            raise GodmodeError("--rebaseline needs --scan: measure the drift "
                               "before accepting it as the new baseline")
        snapshot = make_snapshot(runtime.anchor)
        record = runtime.archive.append(
            "inventory", "repository-snapshot", snapshot,
            evidence=[runtime.anchor.head] if runtime.anchor.head else [])
        payload["rebaselined"] = _event_view(record)
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


def _supersession_chains(
    records: list[dict[str, Any]],
    *,
    universe: list[dict[str, Any]] | None = None,
    focus_subject: str | None = None,
) -> list[str]:
    """NS-10e: every supersession lineage touching `records`, oldest to
    newest, rendered as `"seq -> seq -> seq"` - the explicit chain
    `history --subject` shows in place of a flat list a reader could
    otherwise only read as "the newest one silently overwrote the rest".

    Fix round 1 (B3): the walk itself resolves both ends of a `supersedes`
    citation from `universe` (the archive, or an archive-wide same-kind
    slice `cmd_history` passes in) rather than `records` alone - the
    review's own headline case (chronicle.py's docstring: "a lesson
    restated under a new subject") has its successor OUTSIDE a
    `--subject` selection by definition, so restricting the walk to
    `records` made the cross-subject case, the one NS-10e exists for,
    render no chain at all. A chain is still rendered only when at least
    one of its own sequences is a record `records` (the caller's actual
    selection) returned - `universe` only resolves the dangling end, it
    never pulls in an unrelated lineage nothing in the selection touches.

    `focus_subject` (usually the `--subject` the caller queried) marks
    which subject needs no annotation: a step whose own subject differs
    from it is rendered `"seq (subject)"` rather than bare `seq`, so the
    cross-subject hop is visible in the line itself instead of silently
    implied. `None` (no `--subject` given) annotates nothing, matching
    the pre-fix, subject-blind rendering.
    """
    universe = records if universe is None else universe
    # Round 1 nit: the same guarded coercion `godmode_chronicle` uses, not a
    # bare `int()`. B3 widened this walk's input from one subject's slice to
    # the whole archive, so one malformed `sequence` anywhere would otherwise
    # raise out of every `history --subject`, not just its own subject's.
    by_sequence = {sequence_of(r): r for r in universe if "sequence" in r}
    returned_sequences = {sequence_of(r) for r in records if "sequence" in r}
    successor: dict[int, int] = {}
    has_predecessor: set[int] = set()
    for record in universe:
        target = (record.get("data") or {}).get("supersedes")
        if target is None:
            continue
        try:
            target = int(target)
        except (TypeError, ValueError):
            continue
        if target not in by_sequence:
            # Asymmetry worth naming: `superseded_sequences` excludes an
            # unresolvable target UNCONDITIONALLY, while a chain whose
            # target is outside this universe simply renders nothing. A
            # record the readers already treat as retired can therefore
            # show no chain under a narrowed `history --kind K --subject X`
            # - reachable only via a cross-kind or forged edge.
            continue
        sequence = sequence_of(record)
        successor[target] = sequence
        has_predecessor.add(sequence)
    chains: list[str] = []
    for root in sorted(seq for seq in successor if seq not in has_predecessor):
        path = [root]
        seen = {root}
        current = root
        while current in successor and successor[current] not in seen:
            current = successor[current]
            path.append(current)
            seen.add(current)
        if not (returned_sequences & seen):
            continue
        labels: list[str] = []
        for seq in path:
            record = by_sequence.get(seq)
            subject = str(record.get("subject", "")) if record else ""
            if focus_subject is not None and subject and subject != focus_subject:
                labels.append(f"{seq} ({subject})")
            else:
                labels.append(str(seq))
        chains.append(" → ".join(labels))
    return chains


def cmd_history(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    seq = getattr(args, "seq", None)
    if seq is not None:
        # Fix round 1 (review B, N6): `--seq` names ONE record, so a filter
        # alongside it can only narrow a set of one - it was silently
        # ignored, which reads as "no such record" for a filter that simply
        # never ran. Refused by name instead.
        conflicting = [name for name in ("kind", "subject")
                       if getattr(args, name, None) is not None]
        if conflicting:
            raise ArchiveError(
                "`history --seq` names one record by sequence, so "
                + ", ".join(f"--{name}" for name in conflicting)
                + " cannot narrow it - drop the filter, or drop --seq and filter the "
                  "whole history"
            )
        # NS-11g (0.3.28 Plan 5 Task 7): the one lookup that reaches the
        # cold tier - `Chronicle.find_by_sequence` checks the hot events
        # directory first, then any `events-cold-<n>.jsonl` segment a
        # `godmode forget` pass has rotated the record into. Fix round 1
        # (review A, B4): it re-hashes what it finds and refuses a record
        # that no longer matches, so `--seq` can never serve a forged cold
        # record as genuine.
        record = runtime.archive.find_by_sequence(seq)
        if record is None:
            raise ArchiveError(f"No record with sequence {seq}")
        return CommandResult({"records": [_event_view(record)]})
    records = runtime.archive.select(kind=args.kind, subject=args.subject, limit=args.limit)
    payload: dict[str, Any] = {"records": [_event_view(record) for record in records]}
    if args.subject is not None:
        # NS-10e: a chain, never an overwrite - only meaningful once a
        # single --subject's own history is in view. Fix round 1 (B3): the
        # dangling end of a cross-subject edge is resolved from the full,
        # same-kind archive (`read_events()` is cached), not just this
        # `--subject` selection - see `_supersession_chains`'s docstring.
        universe = runtime.archive.read_events()
        if args.kind is not None:
            universe = [r for r in universe if r.get("kind") == args.kind]
        chains = _supersession_chains(records, universe=universe, focus_subject=args.subject)
        if chains:
            payload["chain"] = chains
    return CommandResult(payload)


def _latest_plan(runtime: Runtime) -> dict[str, Any] | None:
    plans = runtime.archive.select(kind="plan", limit=200)
    return plans[-1] if plans else None


def cmd_plan(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    done = list(getattr(args, "done", None) or [])
    if done or getattr(args, "close", False):
        # 2026-09-10: a plan's steps stayed pending forever because nothing
        # could finish one; the scope gate then named nineteen built steps
        # as open. A finished step or a closed plan is a new plan record
        # cloned from the latest, so the history keeps every state.
        _require_archive(runtime)
        latest = _latest_plan(runtime)
        if latest is None:
            raise ArchiveError("no plan on record to finish a step of")
        data = dict(latest.get("data") or {})
        steps = [dict(s) for s in (data.get("steps") or [])]
        finished: list[str] = []
        for wanted in done:
            hit = None
            if str(wanted).isdigit() and 1 <= int(wanted) <= len(steps):
                hit = steps[int(wanted) - 1]
            else:
                needle = str(wanted).strip().lower()
                matches = [s for s in steps if needle and needle in str(s.get("text", "")).lower()]
                if len(matches) == 1:
                    hit = matches[0]
                elif len(matches) > 1:
                    raise ArchiveError(f"--done {wanted!r} matches {len(matches)} steps; name one, or its number")
            if hit is None:
                raise ArchiveError(f"--done {wanted!r} matches no step of the latest plan; steps are numbered 1.."
                                   f"{len(steps)}")
            hit["status"] = "done"
            finished.append(str(hit.get("text", ""))[:80])
        if getattr(args, "close", False):
            for step in steps:
                step["status"] = "done"
            data["status"] = "closed"
        data["steps"] = steps
        pending = sum(1 for s in steps if s.get("status") != "done")
        record = _append(
            runtime, "plan", str(latest.get("subject", "plan")), data, args.evidence,
            as_operator=getattr(args, "as_operator", False),
            operator_verified=_resolve_operator_verified(runtime, args),
        )
        return CommandResult({"record": record, "finished": finished, "pending": pending,
                              "closed": data.get("status") == "closed"})
    args.title = _one_text(args, "title_positional", "title", "plan title")
    if not args.title:
        raise ArchiveError("plan needs its title: `godmode plan \"<title>\" --step ...` or --title")
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
        as_operator=getattr(args, "as_operator", False),
        operator_verified=_resolve_operator_verified(runtime, args),
    )
    return CommandResult({"record": record})


def cmd_build(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    args.summary = _one_text(args, "summary_positional", "summary", "build summary")
    if not args.summary:
        raise ArchiveError("build needs its summary: `godmode build \"<what changed>\"` or --summary")
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
    args.summary = _one_text(args, "summary_positional", "summary", "checkpoint summary")
    # Naming the missing flag rather than letting argparse describe a
    # requirement that only applies when not reviewing.
    if not args.summary or not args.status:
        raise ArchiveError("checkpoint requires --summary and --status (or --review)")
    if args.status in {"complete", "fixed"} and not args.evidence:
        raise ArchiveError("Completion requires at least one --evidence reference")
    # C-8: a checkpoint's --evidence is what a later `verify()` read of the
    # archive treats as backing this handoff, so a `file:`/`seq:`/`cmd:`
    # reference that never resolves is refused here rather than sealed onto
    # the record - the same referential checks `record_claim` already uses
    # (Plan 6's `require_seq_cite`, and `_citation_resolves` for the other
    # two prefixes), reused rather than re-derived.
    from .godmode_fingerprint import require_seq_cite
    from .godmode_attest import _citation_resolves
    project = Path(runtime.anchor.project_root)
    # Best-effort, not required: a `cmd:` reference narrows to a run from
    # THIS session when one is open, same as every other citation check,
    # but a checkpoint with no session open (or a `file:`/`seq:` only
    # reference) must not be refused over that alone.
    session = latest_session(runtime.archive)
    for ref in args.evidence or []:
        ref = str(ref)
        if ref.startswith("seq:"):
            require_seq_cite(runtime.archive, ref)
        elif ref.startswith(("file:", "cmd:")):
            if not _citation_resolves(project, runtime.archive, ref, session):
                raise ArchiveError(f"checkpoint evidence {ref} does not resolve")
    # Field report 2026-09-02: a handoff summary is naturally longer than
    # the archive's 200-char subject slot, and the refusal took three tries
    # to decode. The subject is a label - derived from the opening words
    # when the summary overflows - and the FULL summary rides in the data,
    # so nothing is lost to the cap.
    subject = args.summary
    for owed in getattr(args, "owes", None) or []:
        # Field report file 2026-09-10, Part 3: a temporary privilege bump
        # and two throwaway specs were restored from a state file, not from
        # the gate. The debt is an obligation; the scope gate names it.
        text = " ".join(str(owed).split())
        if text:
            runtime.archive.append("obligation", f"temporary: {text}"[:200],
                                   {"status": "open", "value": text, "restore": True,
                                    "session": _session(runtime, getattr(args, "session", None))}, evidence=[])
    data: dict[str, Any] = {
        "status": args.status,
        "next": args.next_action,
        "hypothesis": args.hypothesis,
        "outcome": args.outcome or args.status,
        # Recorded so a rewind preview can name the exact commit.
        "head": runtime.anchor.head,
    }
    if len(subject.strip()) > MAX_SUBJECT:
        subject = " ".join(args.summary.split()[:8])[:MAX_SUBJECT].strip()
        data["summary"] = args.summary
    result = CommandResult(
        {
            "record": _append(
                runtime,
                "checkpoint",
                subject,
                data,
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
    advisories: list[str] = []
    last_incident = max(
        (r["sequence"] for r in runtime.archive.select(kind="incident", limit=500)),
        default=None)
    if last_incident is not None:
        last_lesson = max(
            (r["sequence"] for r in runtime.archive.select(kind="lesson", limit=500)),
            default=0)
        if last_incident > last_lesson:
            advisories.append(
                f"incident seq:{last_incident} postdates the newest lesson; "
                "if it taught something, record it now "
                "(godmode remember --kind lesson) while the evidence is fresh")
    # Field reports 23-25: a 22-file regression sat two days under
    # checkpoints whose status said "code-green" with no evidence, while
    # the newest attestation was eight days old. Both facts were already
    # on the record; nothing said them. Named here from the data alone.
    try:
        from .godmode_precheck import changes_since_last_green, _named_files
        known = changes_since_last_green(runtime.archive, Path(runtime.anchor.project_root))
        if known["changed"]:
            cited = " ".join(
                " ".join(str(e) for e in (r.get("evidence") or []))
                for r in runtime.archive.select(limit=500)
                if r.get("kind") in ("attestation", "claim"))
            unnamed = [p for p in known["changed"] if p not in cited]
            if unnamed:
                if known["attested"]:
                    age = (f"{known['age_days']} day(s) ago"
                           if known["age_days"] is not None else "at an unknown time")
                    advisories.append(
                        f"{len(unnamed)} file(s) changed since the last attested check "
                        f"'{known['attested']}' ({age}, {known['head']}) and named by no "
                        f"attestation or claim: {_named_files(unnamed)}")
                else:
                    advisories.append(
                        f"no attested check on record for this tree; {len(unnamed)} "
                        f"changed file(s) named by no attestation or claim: "
                        f"{_named_files(unnamed)}")
        if _GREEN_WORDS.search(str(args.status or "")) and not args.evidence:
            advisories.append(
                f"status says '{args.status}' with no evidence; the run this "
                "status describes is attested by `godmode verify <name> "
                "--command \"<check>\"`, and only that record can be re-run")
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an advisory never fails the checkpoint it rides
        pass
    if advisories:
        result.payload["advisories"] = advisories
    return result


_GREEN_WORDS = re.compile(r"(?i)\b(?:green|pass(?:ed|es|ing)?|verified|all\s+tests|suite\s+\d)\b")


def cmd_checklist_update(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.status in {"complete", "done"} and not args.evidence:
        raise ArchiveError("A completed checklist item requires --evidence")
    payload: dict[str, Any] = {
        "record": _append(
            runtime,
            "checklist",
            args.item,
            {"status": args.status, "note": args.note},
            args.evidence,
        )
    }
    # A row with no runnable command is a suggestion, not a gate (field
    # corpus, 2026-09-03): a complete row whose evidence is all prose or
    # file paths cannot be re-proved by anyone later. Advisory, never a
    # refusal - some rows are legitimately human-verified.
    if args.status in {"complete", "done"}:
        runnable = any(
            str(cite).startswith(("cmd:", "seq:"))
            for cite in (args.evidence or []))
        if not runnable:
            payload["advisories"] = [
                "no runnable command in this row's evidence - a row nobody "
                "can re-run is a suggestion, not a gate; add cmd:<the check "
                "that re-proves it> or seq:<its attestation> when one exists"]
    return CommandResult(payload)


def cmd_checklist_template(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """NS-13g: the RCA ritual as checklist rows; `method --check-record` reads them
    back when the RCA record names the label (`"rca": "<label>"`)."""
    from .godmode_checklist import template_items
    return CommandResult({
        "template": args.template, "label": args.label,
        "items": template_items(args.template, args.label),
        "read_by": (f'method --check-method <m> --check-record <file> with "rca": "{args.label}" '
                    "in the record - a skipped step reads incomplete:<step>"),
    })


from .godmode_requests import CLOSED_STATUSES as _CLOSED_REQUEST_STATUSES  # noqa: E402


def _require_request_closure_target(runtime: Runtime, subject: str) -> None:
    from .godmode_requests import digest as request_text_digest
    from .godmode_requests import open_stated_requests, read_request_window
    if not runtime.archive.initialized():
        return
    _requests, _ = read_request_window(runtime.archive)
    opened = open_stated_requests(_requests)
    wanted = subject.strip()
    for record in opened:
        identifier = str((record.get("data") or {}).get("digest", ""))
        if wanted in (str(record.get("subject", "")).strip(), identifier) or \
                request_text_digest(wanted) == identifier:
            return
    if not opened:
        raise ArchiveError(f"no open ask matches '{wanted[:80]}' - there are no open asks on record")
    listed = "; ".join(
        f"{record.get('subject')} '{' '.join(str(w) for w in ((record.get('data') or {}).get('keywords') or [])[:6])}'"
        for record in opened[-8:])
    raise ArchiveError(
        f"no open ask matches '{wanted[:80]}' - a closure must name the ask's id. Open: {listed}. "
        "Close one with `godmode remember --kind request --subject \"ask:<hex>\" --status closed`")


# NS-10e kinds that already carry their own evolution/accumulation
# mechanism (`record_pattern`'s occurrence merge, `record_incident`'s
# one-shot report) - `cmd_remember` returns from their own branches before
# the generic `data` dict below is ever built, so a `--supersedes` on
# either would silently do nothing rather than refuse. Named once so the
# refusal and the flag's own help text can never drift apart.
_SUPERSEDES_UNSUPPORTED_KINDS = frozenset({"incident", "pattern"})


def _validate_supersedes(runtime: Runtime, kind: str, supersedes: int, writer: str) -> None:
    """NS-10e: `--supersedes <seq>` must name a record that actually
    exists, is the SAME kind as the one being written, is not already
    itself superseded, and (fix round 1, B1) is not more trusted than the
    writer about to supersede it - none of which a single record's own
    `data` can answer (see `godmode_invariants._register_invariants`'s own
    note on why the register's sibling check needs archive history), so
    this runs here, against the archive, before the write - never inside
    `KIND_INVARIANTS`.

    `writer` is resolved by the CALLER (`cmd_remember`, via `Chronicle.
    resolve_writer`) the exact same way the append below it will resolve
    its own - this function never re-derives it, so the two can never
    read the same write as two different writers (the bug this fix
    closes: supersession sat upstream of Task 5's trust rule and let an
    `agent` write erase an `operator` record that NS-8k's own status-flip
    refusal would never have let it touch).
    """
    _require_archive(runtime)
    all_records = runtime.archive.read_events()
    target = next(
        (r for r in all_records if int(r.get("sequence", 0) or 0) == supersedes), None)
    if target is None:
        raise ArchiveError(
            f"--supersedes {supersedes} names no record on this archive; "
            "`godmode history --limit 50` to find the sequence you meant")
    if target.get("kind") != kind:
        raise ArchiveError(
            f"--supersedes {supersedes} is a {target.get('kind')!r} record; "
            f"a --kind {kind} record can only supersede another {kind!r} "
            f"record - write it as --kind {target.get('kind')}, or name a "
            f"{kind!r} sequence instead")
    if supersedes in superseded_sequences(all_records):
        raise ArchiveError(
            f"--supersedes {supersedes} is already superseded by a later "
            f"record; `godmode history --kind {kind} --subject "
            f"\"{target.get('subject', '')}\"` to find the current one and "
            "supersede that instead")
    target_writer = record_writer(target)
    target_trust = record_trust(target)
    writer_trust = record_trust({"writer": writer})
    if target_trust > writer_trust:
        raise ArchiveError(
            f"--supersedes {supersedes} is a {target_writer!r} record "
            f"(trust {target_trust}); this write would land as {writer!r} "
            f"(trust {writer_trust}), which does not outrank it - "
            "supersession is stronger than a status flip and NS-8k already "
            "refuses a lower-trust status change against a higher-trust "
            "record, so this refuses too. Retry with --as-operator (and "
            f"its verification) to write as {target_writer!r} or higher, "
            f"or have a {target_writer!r}-or-higher writer make the change")


def cmd_remember(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    # `remember` defaulted every kind to `active`, and a request is read only
    # when it says `open`: the review and the detector both filter on it. A
    # hand-written request therefore landed in the archive and was read by
    # nothing. The default is now per-kind; an explicit --status still wins,
    # which is what keeps `--kind request --status closed` a closure.
    text = _one_text(args, "text", "value", "remember text")
    if args.value is None and text:
        args.value = text
    if args.subject is None and text:
        args.subject = " ".join(text.split()[:8])[:MAX_SUBJECT].strip()
    # Field report 28 (2026-09-10): the repair skill shows `--kind lesson
    # --subject --guard` and the CLI refused it for lacking --value; the
    # guard IS the lesson's value when no other is given.
    if args.kind == "lesson" and args.value is None and getattr(args, "guard", None):
        args.value = args.guard
    if args.subject is not None and args.value is None and args.status:
        # A status change carries no new value: the paste-ready closure the
        # stop hook prescribes (`--kind request --subject "ask:<hex>"
        # --status closed`) was refused here for lacking --value, so the
        # exact line every surface printed closed nothing (field-caught at
        # the 0.3.18 gate, 2026-09-04 - five open asks, four of them served).
        args.value = f"status set to {args.status}"
    if args.subject is None or args.value is None:
        raise ArchiveError(
            "remember needs either the whole record as one quoted string "
            "(godmode remember --kind lesson \"<what happened and what to "
            "do>\") or --subject plus --value")
    _absorb_verdicts: tuple[str | None, str | None] | None = None
    if args.kind == "decision" and str(args.subject or "").startswith("absorb:"):
        # H6: an absorb decision that says adopt or extend funds code, so it
        # must cite a source file that was actually opened - never a README,
        # a doc, or a release note. A surface read may still park, skip,
        # diverge, or say unread.
        from .godmode_absorb import parse_verdicts, validate_absorb
        gaps = validate_absorb(str(args.value or ""), list(args.evidence or []), runtime.archive)
        if gaps:
            raise ArchiveError(
                "absorb decision refused: " + ", ".join(gaps)
                + " - adopt/extend must cite a source file opened (file:<path>, or "
                  "receipt:<source>:<path> from `godmode read`) that is not README, "
                  "docs or notes; a README-only read may say unread, skip or diverge")
        # Fix round 1: a validated write is lifted into the record's data so
        # `godmode_parity.upstream_verdicts` sees a CLI-recorded decision the
        # same way it sees one written by direct archive access.
        _absorb_verdicts = parse_verdicts(str(args.value or ""))
    supersedes = getattr(args, "supersedes", None)
    if supersedes is not None and args.kind in _SUPERSEDES_UNSUPPORTED_KINDS:
        raise ArchiveError(
            f"--supersedes is not supported for --kind {args.kind}; pattern "
            "records accumulate occurrences on their own subject "
            "(`--occurrence seq:<n>`), and incidents are one-shot reports - "
            "supersede a decision, invariant, lesson, obligation, "
            "assumption or request instead")
    if args.kind != "lesson":
        # NS-10j fix round 1 (M1): the same treatment `--enforce` gets
        # further down, for the same stated reason - a silent drop is a
        # worse failure than a loud one. The four structured flags were
        # read INSIDE the `--kind lesson` branch, so `remember --kind
        # incident --root-cause "..."` built a record with the root cause
        # simply never stored and the operator who typed it never learned
        # otherwise. Checked HERE, above the per-kind branches, because
        # `incident` and `pattern` return before that branch is reached.
        # Every stray flag is named, so the refusal says which one.
        stray_structured = [
            flag for flag, dest in (
                ("--root-cause", "root_cause"), ("--correction", "correction"),
                ("--reflection", "reflection"), ("--falsifier", "falsifier"))
            if getattr(args, dest, None)
        ]
        if stray_structured:
            raise ArchiveError(
                f"{', '.join(stray_structured)} only applies to `--kind "
                f"lesson` (got --kind {args.kind!r}): these are NS-10j's "
                "structured lesson fields and there is no lesson here to "
                "carry them - an incident's own falsifier is `--refuted-by`, "
                "a different field with different semantics")
    if args.kind != "incident" and (getattr(args, "repro", None)
                                    or getattr(args, "no_repro", None) is not None):
        raise ArchiveError(
            f"--repro/--no-repro only apply to --kind incident (got --kind {args.kind!r}); "
            "a reproduction belongs to the failure it reproduces")
    if args.kind == "incident":
        from .godmode_mistakes import record_incident, repro_command, run_repro, validate_incident
        # NS-13e: reproduce first. The incident carries the command that
        # shows the failure, and the runner records its exit code now - or
        # the record says why there is none.
        repro_cmd = (str(getattr(args, "repro", None) or "").strip()
                     or repro_command(args.evidence))
        no_repro = getattr(args, "no_repro", None)
        if not repro_cmd and no_repro is None:
            raise ArchiveError(
                "an incident needs its reproduction command: --repro \"<the command "
                "that fails>\" (or --evidence \"repro:<command>\"); it runs now and its "
                "exit code is recorded. With no reproduction yet, say why: "
                "--no-repro \"<reason>\" (recorded as underspecified-ask)")
        if repro_cmd and no_repro is not None:
            raise ArchiveError("--repro and --no-repro are exclusive: an incident has a "
                               "reproduction command or a reason it has none")
        _require_archive(runtime)
        # Validate before running: a record that will be refused must not
        # execute its command or leave an orphan check behind.
        validate_incident(getattr(args, "failure_class", None),
                          getattr(args, "turning_point", False), args.evidence)
        repro = (run_repro(runtime.archive, _session(runtime, getattr(args, "session", None)),
                           Path(runtime.anchor.project_root), repro_cmd)
                 if repro_cmd else None)
        record = record_incident(
            runtime.archive, args.subject, args.value,
            failure_class=getattr(args, "failure_class", None),
            turning_point=getattr(args, "turning_point", False),
            cites=args.evidence,
            predicts=getattr(args, "predicts", None),
            refuted_by=getattr(args, "refuted_by", None),
            hypothesis=getattr(args, "hypothesis", None),
            repro=repro,
            no_repro=no_repro,
        )
        payload: dict[str, Any] = {"record": _event_view(record)}
        if repro is not None:
            payload["repro"] = {k: repro[k] for k in ("command", "exit_code", "state")}
        return CommandResult(payload)
    if args.kind == "pattern":
        from .godmode_mistakes import record_pattern
        pattern_class = getattr(args, "pattern_class", None)
        if not pattern_class:
            raise ArchiveError(
                "remember --kind pattern needs --class naming the failure "
                "class this recurring failure belongs to")
        occurrence_seq: int | None = None
        raw_occurrence = getattr(args, "occurrence", None)
        if raw_occurrence:
            text = str(raw_occurrence)
            if not text.startswith("seq:"):
                raise ArchiveError(
                    "--occurrence needs the form seq:<n>, naming the record "
                    "that shows this instance of the pattern")
            try:
                occurrence_seq = int(text.split(":", 1)[1])
            except ValueError as exc:
                raise ArchiveError(
                    f"--occurrence 'seq:<n>' is not a number: {text!r}"
                ) from exc
        record = record_pattern(
            runtime.archive, args.subject, args.value, pattern_class,
            occurrence=occurrence_seq, cites=args.evidence,
        )
        return CommandResult({"record": _event_view(record)})
    status = args.status or ("open" if args.kind in ("request", "review") else "active")
    data: dict[str, Any] = {"value": args.value, "status": status}
    if args.kind == "review":
        # NS-11e fix round 1 (review B, B4): a flagged contradiction is closed
        # the way an ask is - by subject and status - and the finding's own
        # `kind`/`sequences` are carried forward from the record being closed
        # rather than retyped. The invariant requires them, and a hand-typed
        # set that differs by one sequence is a closure the next pass does not
        # recognise, so the contradiction re-opens forever. A `review` is
        # written by `godmode forget`, never minted here.
        #
        # Fix round 2 (R2-B5): WHICH review this closes is answerable, because
        # one subject can carry several open reviews at once - `open_reviews`
        # keys on (subject, exact sequence set), and a later pass that finds a
        # third disagreeing record files a SECOND review with a wider set.
        # Carrying the newest one forward unconditionally made every older
        # open review unclosable by any CLI path and left it in `hygiene`,
        # `status.remaining()` and the brief forever. `--review seq:<n>` names
        # one; with none named, the single open review on the subject is the
        # unambiguous answer, and two or more refuse rather than guess.
        from .godmode_chronicle import open_reviews as _open_reviews
        records = runtime.archive.read_events()
        prior = None
        named_review = getattr(args, "review", None)
        if named_review:
            text = str(named_review).strip()
            if not text.startswith("seq:"):
                raise ArchiveError(
                    "--review needs the form seq:<n>, naming the review record "
                    "this closes - `godmode history --kind review` lists them")
            try:
                named_sequence = int(text.split(":", 1)[1])
            except ValueError as exc:
                raise ArchiveError(
                    f"--review 'seq:<n>' is not a number: {text!r}") from exc
            for record in records:
                if (record.get("kind") == "review"
                        and int(record.get("sequence") or 0) == named_sequence):
                    prior = record
                    break
            if prior is None:
                raise ArchiveError(
                    f"No review record at seq:{named_sequence} - "
                    "`godmode history --kind review` lists the flagged contradictions")
            if str(prior.get("subject") or "") != args.subject:
                raise ArchiveError(
                    f"seq:{named_sequence} is a review on subject "
                    f"{str(prior.get('subject') or '')!r}, not {args.subject!r} - "
                    "--subject must name the subject the review was filed against")
        else:
            still_open = [entry for entry in _open_reviews(records)
                          if entry["subject"] == args.subject]
            if len(still_open) > 1:
                listing = "; ".join(
                    f"seq:{entry['sequence']} flags {entry['sequences']}"
                    for entry in still_open)
                raise ArchiveError(
                    f"{len(still_open)} reviews are open on subject {args.subject!r} "
                    "and they flag different records - name the one this closes "
                    f"with `--review seq:<n>`: {listing}")
            if still_open:
                target = still_open[0]["sequence"]
                prior = next((record for record in records
                              if int(record.get("sequence") or 0) == target), None)
            else:
                for record in reversed(records):
                    if record.get("kind") == "review" and record.get("subject") == args.subject:
                        prior = record
                        break
        if prior is None:
            raise ArchiveError(
                f"No review record on subject {args.subject!r} to update - "
                "`godmode history --kind review` lists the flagged contradictions, "
                "and `godmode forget` is what writes one")
        prior_data = prior.get("data") or {}
        data["kind"] = str(prior_data.get("kind") or "")
        data["sequences"] = [int(s) for s in (prior_data.get("sequences") or [])
                             if isinstance(s, int) and not isinstance(s, bool)]
        data["reason"] = str(prior_data.get("reason") or "")
    # Resolved once, here, and reused at the `_append` call below - B1 fix
    # round 1 needs this write's own trust rank BEFORE the write, to gate
    # `--supersedes`; calling `_resolve_operator_verified` a second time at
    # `_append` would re-prompt for (or re-check) the operator password for
    # the exact same write.
    operator_verified = _resolve_operator_verified(runtime, args)
    if supersedes is not None:
        writer = runtime.archive.resolve_writer(
            as_operator=getattr(args, "as_operator", False),
            operator_verified=operator_verified)
        _validate_supersedes(runtime, args.kind, supersedes, writer)
        data["supersedes"] = supersedes
    if _absorb_verdicts is not None:
        imp, beh = _absorb_verdicts
        if imp is not None:
            data["import_verdict"] = imp
        if beh is not None:
            data["behaviour_verdict"] = beh
    if args.kind == "assumption":
        # The same contract `--turning-point` holds for an incident: both are
        # causal claims, and a causal claim with no citation is an assertion
        # wearing a record's clothes.
        from .godmode_mistakes import validate_load_bearing
        load_bearing = bool(getattr(args, "load_bearing", False))
        validate_load_bearing(load_bearing, args.evidence)
        if load_bearing:
            data["load_bearing"] = True
    if args.kind in ("obligation", "lesson") and getattr(args, "standing", False):
        data["standing"] = True
    if args.kind == "obligation" and getattr(args, "blocked_by", None):
        # NS-8n: an obligation names what blocks it. The existence,
        # self-dependency and cycle checks are the same ones sprint items
        # get (`godmode_status._check_dependencies`), keyed here by
        # obligation subject rather than item id.
        from .godmode_status import _check_dependencies
        blocked_by = [str(b) for b in args.blocked_by if str(b).strip()]
        existing_ids: dict[str, list[str]] = {}
        # `select(kind="obligation", limit=500)` hard-caps at 500 and keeps
        # only the newest that many - past that cap, an older obligation a
        # new one names as its blocker reads as phantom (existence check
        # fails a real blocker), and a cycle running back through it is
        # silently admitted. `read_events()` filtered here is uncapped, so
        # every obligation the archive holds is checked, not just the
        # newest 500.
        for record in runtime.archive.read_events():
            if record.get("kind") != "obligation":
                continue
            existing_ids[str(record["subject"])] = list(
                (record.get("data") or {}).get("blocked_by") or [])
        _check_dependencies(existing_ids, args.subject, blocked_by)
        data["blocked_by"] = blocked_by
    if args.kind == "lesson":
        data["generalized_guard"] = args.guard
        # NS-10j (0.3.28 Plan 5 Task 2): opt into the structured schema only
        # when at least one of the four new fields is given - a plain
        # `--guard`-only lesson (enforce predicates, standing guards) is the
        # pre-existing advisory shape and stays untouched by this rule.
        structured_fields = {
            "root_cause": getattr(args, "root_cause", None),
            "correction": getattr(args, "correction", None),
            "reflection": getattr(args, "reflection", None),
            "refuted_by": getattr(args, "falsifier", None),
        }
        if any(value for value in structured_fields.values()):
            for key, value in structured_fields.items():
                if value:
                    data[key] = value
            from .godmode_lessons import normalize_lesson_write
            normalize_lesson_write(data)
    elif getattr(args, "enforce", None):
        # I-1 fix round 1 (nit 5): a silent drop is a worse failure than a
        # loud one - `--enforce` on a non-lesson kind used to build the
        # record with the flag simply never read, so an operator who
        # believed a guard would execute never learned otherwise. Refused
        # the way `--enforce` with no `--guard` is refused, just below.
        # NS-10j's four structured flags get the same treatment, checked
        # above the per-kind branches (`stray_structured`).
        raise ArchiveError(
            f"--enforce only applies to `--kind lesson` (got --kind "
            f"{args.kind!r}): it attaches a guard to that lesson's own "
            "write, and there is no lesson here for it to attach to")
    if args.kind == "lesson" and getattr(args, "enforce", None):
        # I-1: an enforce predicate with no guard would refuse a matching
        # write and have nothing to tell it to do instead - the guard IS
        # the remedy the refusal carries.
        if not str(args.guard or "").strip():
            raise ArchiveError(
                "--enforce needs --guard: a refused write is told to do "
                "the guard instead, so an enforce predicate with no guard "
                "text has no remedy to give it")
        from .godmode_law import parse_enforce_spec
        data["enforce"] = parse_enforce_spec(args.enforce)
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
        # Field report 27 (2026-09-10): a closure typed with the ask's own
        # words as the subject matched no digest, closed nothing, and was
        # accepted silently - the ask kept nagging. A closure that names no
        # open ask is refused with the open list, paste-ready.
        if str(status).lower() in _CLOSED_REQUEST_STATUSES:
            _require_request_closure_target(runtime, args.subject)
        else:
            # A reopen typed by hand carried none of the fields the open-ask
            # census keys on, so it reopened nothing (2026-09-10). Copy them
            # from the newest record of the same ask.
            prior = None
            for record in runtime.archive.select(kind="request", limit=400):
                if str(record.get("subject", "")) == str(args.subject):
                    prior = record
            if prior is not None:
                previous = prior.get("data") or {}
                for key in ("digest", "keywords", "session", "source", "text_digest"):
                    if key in previous:
                        data[key] = previous[key]
                data["reopened"] = True
            if getattr(args, "intent_preserved", None):
                # Two calibration signals, no longer one (2026-09-11): a
                # reopen that keeps the decision and rewords it, versus one
                # that replaces it.
                data["intent_preserved"] = str(args.intent_preserved)
    payload: dict[str, Any] = {
        "record": _append(
            runtime, args.kind, args.subject, data, args.evidence,
            as_operator=getattr(args, "as_operator", False),
            operator_verified=operator_verified,
        )
    }
    # Sibling advisory (field report, 2026-09-01): an obligation recorded
    # over an open one with the same vocabulary is usually the same duty
    # in new clothes - name the elder now, or both nag forever.
    if args.kind == "obligation" and status not in ("closed", "done", "retired"):
        try:
            from .godmode_mistakes import (
                obligation_sibling_advisory, reinvention_advisory)
            advisory = obligation_sibling_advisory(
                runtime.archive, args.subject, args.value)
            if advisory:
                payload["advisory"] = advisory
            # The reinvention check rides the same write: a build-shaped
            # duty overlapping a SHIPPED capability names the elder now,
            # not mid-implementation (operator challenge, 2026-09-03).
            rebuilt = reinvention_advisory(
                runtime.archive, args.subject, args.value)
            if rebuilt:
                payload.setdefault("advisories", []).append(rebuilt)
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: deliberate broad handler: this boundary never raises into the host
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


def cmd_topology(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_topology import trace_topology
    return CommandResult(trace_topology(runtime.archive))


def cmd_digest(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    from .godmode_digest import render_digest
    return CommandResult(render_digest(runtime.archive, since=args.since))


def _guide_growth(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Lessons and invariants recorded in the last seven days - counts only."""
    from datetime import datetime, timedelta, timezone
    week = datetime.now(timezone.utc) - timedelta(days=7)
    lessons = invariants = 0
    for record in records:
        if record.get("kind") not in ("lesson", "invariant"):
            continue
        stamp = str(record.get("recorded_at") or "")
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when >= week:
            if record["kind"] == "lesson":
                lessons += 1
            else:
                invariants += 1
    return {"lessons": lessons, "invariants": invariants,
            "note": "zero growth means nothing was learned this week - or "
                    "nothing surprised; fast growth means patching, not "
                    "generalizing"}


def _launcher_mode_issues(package_root: Path, posix: bool | None = None) -> list[str]:
    """2026-09-10 (macOS): a launcher or shim copied without its mode bit
    fails as `Permission denied` before any interpreter is asked, and
    nothing else in the wiring can say so. POSIX only; Windows runs the
    cmd half and has no mode bit to lose. `posix` is overridable so the
    check is testable on every OS."""
    if not (os.name != "nt" if posix is None else posix):
        return []
    issues: list[str] = []
    for relative in ("hooks/run-hook.cmd", "bin/godmode"):
        launcher = package_root / relative
        if launcher.is_file() and not os.access(launcher, os.X_OK):
            issues.append(
                f"{relative} lost its executable bit; every hook through it is "
                f"inert until `chmod +x \"{launcher}\"`")
    return issues


# NS-10g: every shipped hook entry point wired into every generated host
# manifest. The vocabulary of entry points is never hand-written here - it is
# read straight off `godmode_host_manifests`'s own constants
# (`SESSION_HOOK`/`GATE_FAST_HOOK`/`POST_EDIT_HOOK`), the same three every
# builder in that module already calls `_shell_entry` with.
#
# `godmode_bindings.check()`/`registration_report()` already diff a shipped
# manifest against what the generator would produce "right now" - but that
# comparison is structurally blind to this exact bug class for a
# merge-into-shared host (Codex, Grok): `_render_hook_artifact` builds their
# `expected` value by reading the SAME on-disk `hooks/hooks.json` the
# comparison then checks, patching only the PreToolUse matcher
# (`merge_host_tools_into_shared`). Delete an event key from that file by
# hand and it vanishes from both sides of that diff in the same edit -
# `current` stays true. This reads the actual shipped file for every host
# instead, against each host's own `allowed_events` (never re-typed here),
# so an event a host declares but ships no hook for is caught regardless of
# which side of a generator diff it would have hidden on.
def _hook_event_blocks(manifest: dict, host: str) -> dict:
    """The event -> block-list mapping a shipped manifest actually carries.

    Every host but Antigravity nests it under a top-level `hooks` key
    (`build_cursor_manifest`, `build_gemini_fragment`, and the shared
    `hooks/hooks.json` Codex/Grok merge into all agree). Antigravity nests
    one level deeper, under `godmode` (`build_antigravity_fragment`'s own
    shape) - `enabled` sits beside the events there as a flag, never an
    event itself, excluded the same way `antigravity_emitted_events`
    already excludes it.
    """
    if host == "antigravity":
        godmode = manifest.get("godmode")
        return {k: v for k, v in godmode.items() if k != "enabled"} if isinstance(godmode, dict) else {}
    hooks = manifest.get("hooks")
    return hooks if isinstance(hooks, dict) else {}


def _collect_command_strings(value: object, out: list[str]) -> None:
    """Every string under a `command`/`commandWindows` key, anywhere inside
    `value` - recursive because a block nests its `hooks` entries inside
    matcher groups, themselves items of an event's own list."""
    if isinstance(value, dict):
        for key, sub in value.items():
            if key in ("command", "commandWindows") and isinstance(sub, str):
                out.append(sub)
            else:
                _collect_command_strings(sub, out)
    elif isinstance(value, list):
        for item in value:
            _collect_command_strings(item, out)


_HOOK_FILENAME_RE = re.compile(r"[\w.-]+\.py")


def _wired_hook_issues(package_root: Path) -> list[dict]:
    """NS-10g acceptance: a hook shipped but absent from a host manifest
    that declares its event is `orphan`; a manifest command naming a hook
    file that does not exist under `hooks/` is `dangling`. Both `warning`
    severity - advisory, since a gap here degrades one host's coverage,
    never this process's own integrity - and both name the host and the
    event so the fix is one `godmode bindings --write` (an accidental
    removal) or one restored file (a renamed/deleted script) away.
    """
    from . import godmode_host_manifests as host_manifests
    from .godmode_bindings import _hook_manifest_specs, _load

    issues: list[dict] = []
    try:
        source = _load(package_root)
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: no binding source means nothing to cross-check
        return issues
    entry_points = (
        Path(host_manifests.SESSION_HOOK).name,
        Path(host_manifests.GATE_FAST_HOOK).name,
        Path(host_manifests.POST_EDIT_HOOK).name,
    )
    hooks_dir = package_root / "hooks"
    for host, spec in sorted(_hook_manifest_specs(source).items()):
        target = package_root / spec["path"]
        if not target.is_file():
            continue
        try:
            manifest = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        blocks = _hook_event_blocks(manifest, host)
        allowed_events = host_manifests.HOOK_ARTIFACTS.get(host, {}).get("allowed_events") or ()
        for event in sorted(allowed_events):
            commands: list[str] = []
            _collect_command_strings(blocks.get(event), commands)
            if not any(name in cmd for name in entry_points for cmd in commands):
                issues.append({
                    "code": "hook-orphan",
                    "severity": "warning",
                    "detail": (
                        f"{host}'s {spec['path']} declares {event} but no shipped hook "
                        "command answers it; run `godmode bindings --write` to restore "
                        "it, or add the entry back by hand."
                    ),
                })
        for event, event_blocks in blocks.items():
            commands = []
            _collect_command_strings(event_blocks, commands)
            named = {match for cmd in commands for match in _HOOK_FILENAME_RE.findall(cmd)}
            for name in sorted(named):
                if not (hooks_dir / name).is_file():
                    issues.append({
                        "code": "hook-dangling",
                        "severity": "warning",
                        "detail": (
                            f"{host}'s {spec['path']} names {name} under {event}, which "
                            f"does not exist at hooks/{name}; restore the file or "
                            "regenerate the manifest with `godmode bindings --write`."
                        ),
                    })
    return issues


def _doctor_host(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """`doctor --host <name>`: the wiring a field machine can check itself.

    Ninth field report 2026-09-05 (Codex): a stale install path in a hook
    config, an unwritable archive home under the sandbox, and a PowerShell
    shim where a binary was expected were each found by hand. One answer
    covers them: does the host's hook artifact exist and parse, which
    interpreter answers, is the archive writable from here, and what grade
    of interception is on record.
    """
    import shutil
    import subprocess
    import tempfile
    from .godmode_host_manifests import HOOK_ARTIFACTS
    from .godmode_hookproof import interception_state

    known = sorted(set(HOOK_ARTIFACTS) | {"claude"})
    host = str(args.host).strip().lower()
    if host not in known:
        return CommandResult(
            {"refused": f"unknown host {host!r}; known: {', '.join(known)}"}, exit_code=1)
    registration = hooks_registration_report()
    entry = registration.get(host) or {}
    artifact_path = entry.get("path")
    artifact_file = (_PACKAGE_ROOT / artifact_path) if artifact_path else None
    present = bool(artifact_file and artifact_file.is_file())
    parses = False
    if present:
        try:
            json.loads(artifact_file.read_text(encoding="utf-8"))
            parses = True
        except (OSError, json.JSONDecodeError):
            parses = False
    interpreters: dict[str, bool] = {}
    for candidate in ("python3", "python", "py"):
        found = shutil.which(candidate)
        ok = False
        if found:
            try:
                ok = subprocess.run([found, "-c", "import sys"], capture_output=True,
                                    timeout=20).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
        interpreters[candidate] = ok
    # 2026-09-10 (macOS): the launcher walks these when PATH has none of
    # the above; doctor reports the same walk so the answer matches.
    if os.name != "nt":
        for home in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                     "/opt/local/bin/python3",
                     os.path.expanduser("~/.pyenv/shims/python3"),
                     "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
                     os.path.expanduser("~/.local/bin/python3"), "/usr/bin/python3"):
            if os.access(home, os.X_OK):
                try:
                    interpreters[home] = subprocess.run(
                        [home, "-c", "import sys"], capture_output=True,
                        timeout=20).returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    interpreters[home] = False
    writable = False
    writable_detail = ""
    try:
        runtime.archive.root.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".w", suffix=".tmp", dir=str(runtime.archive.root))
        os.close(handle)
        os.unlink(temporary)
        writable = True
    except OSError as exc:
        writable_detail = f"{exc.strerror or exc}; set GODMODE_STATE_HOME to a writable directory"
    grade = interception_state(runtime.archive, host) if runtime.archive.initialized() else "UNAVAILABLE"
    issues: list[str] = []
    # Ninth field report 2026-09-05: a project's own .codex/hooks.json
    # pointed at a 0.3.4 install path that no longer existed. Every path a
    # project-level hook command names must exist, or the hook is dead
    # wiring and the host fails open in silence.
    project_files = {"codex": ".codex/hooks.json", "antigravity": ".agents/hooks.json",
                     "cursor": ".cursor/hooks.json",
                     "copilot": ".github/hooks/godmode.json",
                     "kiro": ".kiro/hooks.json"}
    project_hooks: dict[str, Any] | None = None
    relative = project_files.get(host)
    if relative:
        candidate = Path(runtime.anchor.project_root) / relative
        if candidate.is_file():
            missing: list[str] = []
            commands: list[str] = []
            try:
                doc = json.loads(candidate.read_text(encoding="utf-8"))
                event_groups = list((doc.get("hooks") or {}).values())
                # Antigravity's shape keeps the event lists under the
                # `godmode` key; a dead path there was invisible here.
                event_groups += [value for value in (doc.get("godmode") or {}).values()
                                 if isinstance(value, list)]
                for groups in event_groups:
                    for group in groups if isinstance(groups, list) else []:
                        for handler in (group.get("hooks") or []) if isinstance(group, dict) else []:
                            command = str((handler or {}).get("command", ""))
                            if command:
                                commands.append(command)
            except (OSError, json.JSONDecodeError, AttributeError):
                missing.append(f"{relative} does not parse")
            for command in commands:
                for target in re.findall(r'"([^"]+)"', command) + [
                        t for t in command.split() if "/hooks/" in t or t.endswith(".py")]:
                    target = target.strip().rstrip(";")
                    if not target or target.startswith("$") or "<" in target:
                        continue
                    if not Path(target).exists():
                        missing.append(target)
            missing = sorted(set(missing))
            project_hooks = {"path": relative, "commands": len(commands),
                             "targets_exist": not missing, "missing": missing}
            for item in missing:
                issues.append(f"{relative} names a path that does not exist: {item}")
    issues.extend(_launcher_mode_issues(_PACKAGE_ROOT))
    if not present:
        issues.append(f"hook artifact missing for {host}: {artifact_path or 'no artifact registered'}")
    elif not parses:
        issues.append(f"hook artifact does not parse: {artifact_path}")
    if not any(interpreters.values()):
        issues.append("no python3, python or py answers `-c \"import sys\"` on PATH; set GODMODE_PYTHON")
    if not writable:
        issues.append(f"archive not writable at {runtime.archive.root}: {writable_detail}")
    if entry.get("gap"):
        issues.append(f"documented gap: {entry['gap']}")
    return CommandResult({
        "host": host,
        "hook_artifact": {"path": artifact_path, "present": present, "parses": parses,
                          "current": entry.get("current")},
        "interpreters": interpreters,
        "archive_writable": writable,
        "archive_root": "<local-state>",
        "interception": grade,
        # Reach, not wiring (2026-09-09, obligation 10119): the features
        # that cannot fire on this host, and why, on day one.
        "reach": __import__(
            "godmode_runtime.godmode_reach", fromlist=["host_reach"]
        ).host_reach(host),
        **({"project_hooks": project_hooks} if project_hooks is not None else {}),
        "issues": issues,
        "healthy": not issues,
    }, exit_code=0)


def _secret_scan_targets(root: Path) -> Iterator[tuple[str, Any]]:
    """Every JSON value under `root` a secret-shape scan should examine:
    each `*.json` file whole, and each line of a `*.jsonl` cold segment
    (NS-11g, 0.3.28 Plan 5 Task 7) as its own record - a secret rotated
    into a cold segment by `godmode forget` must stay exactly as findable
    here as it was while hot, one file-glob was never the security
    boundary."""
    for path in root.rglob("*.json"):
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    for path in root.rglob("*.jsonl"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                yield f"{path.name}:{line_number}", json.loads(line)
            except json.JSONDecodeError:
                continue


def cmd_doctor(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "host", None):
        return _doctor_host(args, runtime)
    # Scope-explicit (B4-8 ext.): every status answer names the project it
    # is about, in JSON and in prose.
    project = str(runtime.anchor.project_root)
    if not runtime.archive.initialized():
        issues = [{"code": "not-initialized", "severity": "error",
                   "detail": f"Not initialized for {project}. Run init."}]
        try:
            stranded = runtime.archive.orphaned()
        except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable previous location is not a finding
            stranded = None
        if stranded:
            # opencode field report 2026-09-10: after `git init` the
            # records sat under the previous identity and doctor said
            # only "run init" - init relinks them, and this says so.
            issues.append({"code": "archive-predates-git-init", "severity": "warning",
                           "detail": f"{stranded['records']} records exist under this project's "
                                     f"previous identity ({stranded['reason']}); `godmode init` "
                                     "relinks them"})
        return CommandResult(
            {
                "project": project,
                "healthy": False,
                "issues": issues,
                "network_used": False,
            },
            exit_code=1,
        )
    # verify=False: doctor's own forced full walk just below is the
    # verification. A default read_events() call verifies internally too
    # (accelerated, `use_checkpoint` defaulting True there) and RAISES on
    # any break it finds - which would stop doctor before it ever reached
    # the walk that is supposed to be the recovery path. Reading unverified
    # here and verifying explicitly next keeps doctor reachable no matter
    # what an accelerated read would have found.
    records = runtime.archive.read_events(verify=False)
    # I-1 fix round 3 (B1 deployment note): fold and persist the enforce
    # sidecar (`godmode-enforce.index.json`) from doctor's own unlocked
    # full walk, before any write ever needs to pay that walk while
    # holding `write_lock()`. On an archive that has never had this
    # sidecar, that walk measured ~13s on 18,964 records - held inside a
    # lock whose acquire deadline is 20s, stalling every concurrent writer
    # (hooks included) for the window. Running `godmode doctor` once after
    # upgrading removes the window entirely. Best-effort: this is a cache
    # warm, never a health finding, and doctor's own health answer must
    # not depend on it succeeding.
    try:
        runtime.archive.seed_enforce_index()
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: sidecar warm is an optimization, never a doctor finding
        pass
    # C-8 fix round 1: `doctor` is the one command this codebase schedules
    # to do a genuinely FULL walk (never accelerated by a registered
    # checkpoint) - `use_checkpoint=False` forces it, so tampering before
    # any checkpoint still surfaces here, and any checkpoint that now
    # verifies gets added to the registry for other reads to trust.
    verification = runtime.archive.verify(records, use_checkpoint=False)
    current = collect_inventory(runtime.anchor.project_root) if args.deep else None
    issues = detect_context_issues(runtime.anchor, records, current)
    if not verification.get("ok", True):
        # N1 fix (re-review): the forced full walk above is the one
        # compensating control for the accelerated read's pre-boundary
        # blind spot (S2) - a walk that finds a broken chain and is then
        # never consulted for health defeats that control entirely. The
        # walk's own message names the exact record; surface it verbatim.
        issues.append({
            "code": "archive-chain-broken",
            "severity": "error",
            "detail": verification.get("message", "chain verification failed"),
        })
    # NS-11g (0.3.28 Plan 5 Task 7): `doctor`'s own forced full walk above
    # is hot-only - it trusts the cold registry's recorded hash at each
    # rotation boundary (see `verify()`'s gap-bridging comment) rather than
    # re-reading cold bytes on this call too, or `godmode forget` would
    # cost a full history re-hash every time it merely checks whether
    # anything is due. `verify_cold()` is the thorough cross-tier check
    # this schedules instead - only when a cold tier actually exists, so a
    # project untouched by `godmode forget` pays nothing extra here.
    if runtime.archive.cold_segment_paths():
        cold_verification = runtime.archive.verify_cold()
        if not cold_verification.get("ok", True):
            issues.append({
                "code": "cold-segment-broken",
                "severity": "error",
                "detail": cold_verification.get("message", "cold segment verification failed"),
            })
    # Fix round 2 (N11): both verifiers walk only the segments the registry
    # NAMES, so an `events-cold-*.jsonl` on disk that no entry claims is
    # invisible to both and to `cold_segment_paths()`. Not a chain break -
    # nothing reads it - but an unowned file holding real records in the
    # archive directory is precisely the thing `doctor` exists to say out
    # loud rather than leave for someone to find.
    owned = {path.name for path in runtime.archive.cold_segment_paths()}
    unowned = sorted(path.name for path in runtime.archive.root.glob("events-cold-*.jsonl")
                     if path.name not in owned)
    if unowned:
        issues.append({
            "code": "cold-segment-unowned",
            "severity": "warning",
            "detail": (f"Cold segment file(s) {', '.join(unowned[:5])} are in the archive "
                       "but no entry in godmode-cold-registry.json claims them - nothing "
                       "reads or verifies them. Left over from an interrupted rotation, "
                       "or a registry that was replaced; move them aside once "
                       "`godmode verify` and `godmode doctor` are both clean."),
        })
    secret_locations: list[str] = []
    for label, value in _secret_scan_targets(runtime.archive.root):
        secret_locations.extend(f"{label}:{item}" for item in find_secret_shapes(value))
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
    # NS-10g: every shipped hook wired into every generated host manifest -
    # cheap and structural, so it runs every time, not only under --deep.
    try:
        issues.extend(_wired_hook_issues(_PACKAGE_ROOT))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a wiring check that cannot run is not itself a finding
        pass
    if args.deep:
        # S6 (obligation 4436): name every cached runtime that is not this
        # one - stale installs share the archive and race its chain. Behind
        # --deep because it reads the user's home caches, not the project.
        from .godmode_constants import RUNTIME_VERSION
        from .godmode_host_manifests import runtime_census_issues

        issues.extend(runtime_census_issues(RUNTIME_VERSION))
    try:
        stranded = runtime.archive.orphaned()
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: an unreadable previous location is not a finding
        stranded = None
    if stranded:
        issues.append({"code": "archive-predates-git-init", "severity": "warning",
                       "detail": f"{stranded['records']} records exist under this project's previous "
                                 f"identity ({stranded['reason']}); "
                                 + ("`godmode init` relinks them" if stranded.get("adoptable")
                                    else "`godmode adopt --confirm` relinks them")})
    common_dir = getattr(runtime.anchor, "git_common_dir", None)
    if common_dir and not str(runtime.archive.root).startswith(str(common_dir)):
        issues.append({"code": "archive-in-application-data", "severity": "info",
                       "detail": "git metadata is not writable from this host, so the archive lives "
                                 "in application data keyed by the git identity; records follow "
                                 "the repository, not the checkout path"})
    if not getattr(runtime.anchor, "is_git", True):
        # Grok field report 2026-09-10: identity showed branch and head as
        # null and doctor said healthy. Without git, rewind, the integrity
        # diff, the commit-score plateau and the dirty-diff ask cannot run.
        issues.append({"code": "not-a-git-repository", "severity": "warning",
                       "detail": "this project is not a git repository: rewind, integrity over a diff, "
                                 "the commit-score plateau, the dirty-diff ask and the preflight cannot run; "
                                 "claims still hash files. `git init` restores them"})
    try:
        from .godmode_repo_privacy import host_permission_findings
        issues.extend(host_permission_findings(Path(project)))
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: a host settings file that cannot be read is not a finding
        pass
    try:
        from .godmode_acl import state_home_acl
        acl = state_home_acl(runtime.archive.root)
        if acl["verdict"] == "permissive":
            issues.append({"code": "state-home-acl", "severity": "warning", "detail": acl["detail"]})
        elif acl["verdict"] == "unmeasured":
            issues.append({"code": "state-home-acl", "severity": "info", "detail": acl["detail"]})
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: the ACL check reports, never blocks doctor
        pass
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
            # Guide growth (harness health scorecard, absorbed 2026-09-03):
            # rules and lessons added in the last seven days - a guide that
            # never grows is a system that has stopped learning from its
            # misses, and one that grows too fast is patching instead of
            # generalizing.
            "guide_growth_7d": _guide_growth(records),
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
            # Verb reach (2026-09-09, obligation 10121): how many console
            # verbs no skill line or hook nudge names. Ratcheted ceilings.
            "verb_reach": __import__(
                "godmode_runtime.godmode_verbreach", fromlist=["doctor_metric"]
            ).doctor_metric(verbs=__import__(
                "godmode_runtime.godmode_verbreach", fromlist=["parser_verbs"]
            ).parser_verbs(_build_parser())),
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
    if getattr(args, "designate_suite", None):
        # The ratchet form: recorded once, every later preflight runs it
        # unprompted. Three CI-red releases proved a per-call flag is
        # willpower, not a control.
        _require_archive(runtime)
        record = runtime.archive.append(
            "criterion", "preflight-suite",
            {"command": args.designate_suite,
             "value": "the designated pre-push suite; preflight runs it on "
                      "every cut"})
        return CommandResult({"designated": args.designate_suite,
                              "sequence": record["sequence"]})
    if getattr(args, "preflight", False):
        from .godmode_preflight import push_preflight
        report = push_preflight(Path(runtime.anchor.project_root),
                                suite=getattr(args, "suite", None),
                                archive=runtime.archive,
                                dirty=bool(getattr(args, "dirty", False)),
                                suite_shards=int(getattr(args, "suite_shards", 1) or 1),
                                shard_index=(None if getattr(args, "shard_index", None) is None
                                             else int(args.shard_index)),
                                session=_session(runtime, getattr(args, "session", None)))
        return CommandResult(report, exit_code=1 if report["verdict"] == "findings" else 0)
    if not args.about:
        # A missing argument is a usage refusal like every other verb's,
        # not an archive fault: exit 1 with the shape on stdout.
        return CommandResult(
            {"refused": "precheck needs --about \"<what you are about to do>\", "
                        "or --preflight"}, exit_code=1)
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
    if getattr(args, "repo", False):
        # Field report 27: a docs-privacy pass got every finding from
        # `git ls-files` and grep by hand. This is that pass, over the
        # tracked tree, with the values masked.
        from .godmode_repo_privacy import scan_tracked
        report = scan_tracked(Path(runtime.anchor.project_root), int(getattr(args, "large_bytes", 5_000_000)))
        return CommandResult(report, exit_code=0 if report.get("verdict") == "clean" else 1)
    _require_archive(runtime)
    findings: list[str] = []
    scanned = 0
    for label, value in _secret_scan_targets(runtime.archive.root):
        scanned += 1
        findings.extend(f"{label}:{item}" for item in find_secret_shapes(value))
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
    preview["brief"] = render_preview(preview)
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
    if getattr(args, "without_preflight", None) and not attended():
        # NS-10k: accepting a push over a red preflight is the operator's own
        # judgement call, spent on their say-so - the unattended row has
        # nobody to make that call, so the flag itself is refused rather
        # than silently honored on nobody's authority.
        raise ArchiveError(
            "refusing: --without-preflight is not available in the unattended tier "
            "(no operator is presumed present to accept that risk). Run this from "
            "an attended session, or set GODMODE_ATTENDED=1 if one truly is one."
        )
    staged_digest = None
    if args.from_last_refusal:
        operation, staged_digest = stage_from_refusal(runtime.archive, nth=args.nth, with_digest=True)
        print(json.dumps(
            {"from_last_refusal": True, "nth": args.nth, "operation": operation},
            ensure_ascii=False,
        ))
    elif args.operation:
        operation = args.operation
    else:
        raise ArchiveError("`authorize stage` requires --operation or --from-last-refusal")
    from .godmode_preflight import preflight_gate

    blocked = preflight_gate(runtime.archive, Path(runtime.anchor.project_root), operation)
    if blocked and not getattr(args, "without_preflight", None):
        # Codex audit 2026-09-10: 37 red CI runs, most on steps only CI ran.
        # A push is staged only over a green preflight at this HEAD.
        raise ArchiveError(f"refusing to stage a push: {blocked}")
    if blocked:
        runtime.archive.append("action", "preflight-skipped",
                               {"reason": str(args.without_preflight)[:200], "operation": operation[:120]},
                               evidence=[])
    broker = CapabilityBroker(runtime.archive)
    password = read_password_stdin() if args.password_stdin else None
    if password is None:
        from .godmode_sentinel import _require_tty

        _require_tty()
        import getpass

        password = getpass.getpass("Godmode authorization password: ")
    broker.stage(operation, password, args.ttl, operation_digest=staged_digest)
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
    from .godmode_branchrole import branch_role, loosens

    role = getattr(args, "role", None)
    if role and not args.record:
        raise ArchiveError("--role is declared on a record; pass --record with it")
    observation = observe_git(runtime.anchor)
    operator_verified = False
    if args.record:
        if role:
            if not runtime.anchor.branch:
                raise ArchiveError("--role needs a checked-out branch to declare it for")
            # Review B2: declaring a spike switches the plan-first gate and
            # the missing-test finding off, so it is the operator's call,
            # never the agent's. Tightening needs no one's permission.
            if loosens(runtime.anchor.branch, role):
                operator_verified = _resolve_operator_verified(runtime, args)
                if not operator_verified:
                    raise ArchiveError(
                        f"declaring {runtime.anchor.branch} throwaway switches off its "
                        "plan and test gates; only the operator can: re-run with "
                        "--as-operator at a terminal")
            # NS-13h: the role is stored on the git-topology record itself;
            # the newest declaration for a branch wins.
            observation = {**observation, "branch": runtime.anchor.branch, "role": role}
        runtime.archive.append(
            "branch",
            "git-topology",
            observation,
            evidence=[runtime.anchor.head] if runtime.anchor.head else [],
            as_operator=operator_verified, operator_verified=operator_verified or None,
        )
    return CommandResult({"recorded": args.record, **observation,
                          "role": branch_role(runtime.archive, runtime.anchor.branch)})


def cmd_version(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if args.reconcile:
        report = reconcile_versions(Path(runtime.anchor.project_root))
        # "staged" is the pre-tag release window: every source surface
        # unanimous and strictly ahead of the tag. CI runs before the tag
        # moves (the release ritual), so this window is lawful, not drift.
        return CommandResult(
            report,
            exit_code=0 if report["verdict"] in ("agreed", "staged") else 1)
    if not args.name and not args.value:
        # Grok 0.3.4 field report: bare `version` tried to record a fact
        # and failed on a consumer project; the obvious reading of the bare
        # command is "what version am I running" - answer it, write nothing.
        from .godmode_constants import RUNTIME_VERSION

        return CommandResult({"version": RUNTIME_VERSION,
                              "note": "recording a version fact needs --name and --value"})
    return CommandResult(
        {"record": _append(
            runtime, "version", args.name, {"value": args.value, "status": args.status}, args.evidence,
            as_operator=getattr(args, "as_operator", False),
            operator_verified=_resolve_operator_verified(runtime, args),
        )}
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
        # S-3: the whole archive, not `select`'s newest 500 refusals - an
        # observed decision behind 500 real refusals would read as absent.
        observed = [
            record for record in runtime.archive.read_events()
            if record["kind"] == "refusal"
            and (record.get("data") or {}).get("observed") is True
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
    """U-E10: recurring-ask mining. Proposals only; JSON with --json, prose otherwise.

    NS-11e (0.3.28 Plan 5 Task 7): also carries `forget_due` - when the last
    `godmode forget` pass ran and what it did - so the recurring surface is
    where an overdue forgetting pass is noticed, the same way a recurring ask
    is.

    Fix round 1 (review A, B8): this READS the pass's own record
    (`action` / `forget-pass`, written by every real pass) instead of running
    a `forget --dry-run` on every invocation. The dry run cost a full
    verified archive read plus two digest sweeps - measured at roughly
    20-35 s on this project's own archive, for a report nobody asked to have
    recomputed. `godmode forget --dry-run` is still the way to see what is
    due right now; this surface answers when a pass last ran.
    """
    _require_archive(runtime)
    report = mine_recurring_asks(runtime.archive, threshold=args.threshold)
    passes = runtime.archive.select(kind="action", subject=FORGET_PASS_SUBJECT, limit=1)
    if passes:
        data = passes[-1].get("data") or {}
        report["forget_due"] = {
            "last_pass": str(data.get("ran_at") or passes[-1].get("recorded_at") or ""),
            "last_pass_seq": int(passes[-1].get("sequence", 0) or 0),
            "expired": int(data.get("expired", 0) or 0),
            "contradictions": int(data.get("contradictions", 0) or 0),
            "detail": "run `godmode forget --dry-run` for what is due now",
        }
    else:
        report["forget_due"] = {
            "last_pass": None,
            "detail": "no `godmode forget` pass is on record - run "
                      "`godmode forget --dry-run` to see what a first pass would do",
        }
    if getattr(args, "json", False):
        return CommandResult(report)
    rendered = render_recurrence(report)
    due = report["forget_due"]
    if due["last_pass"]:
        rendered += (
            f"\nLast `godmode forget` pass: {due['last_pass']} "
            f"(seq {due['last_pass_seq']}; {due['expired']} expired, "
            f"{due['contradictions']} contradiction(s)). "
            "`godmode forget --dry-run` reports what is due now.\n"
        )
    else:
        rendered += f"\n{due['detail']}.\n"
    return CommandResult({"report": rendered})


def upstream_skill_hits(tree: Path, keyword: str, limit: int = 40) -> list[dict[str, Any]]:
    """Skill and doc files in `tree` that mention `keyword`, with the first
    matching lines. Text only, no record: a reading list."""
    import re as _re

    pattern = _re.compile(_re.escape(keyword), _re.IGNORECASE)
    roots = [tree / "skills", tree / "docs", tree / ".agents", tree / ".claude", tree / ".codex", tree]
    seen: set[Path] = set()
    hits: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates = root.rglob("*.md") if root != tree else tree.glob("*.md")
        for path in sorted(candidates):
            if path in seen or any(part in ("node_modules", ".git", ".godmode-repo") for part in path.parts):
                continue
            seen.add(path)
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            matches = [(n, line.strip()[:120]) for n, line in enumerate(lines, 1) if pattern.search(line)]
            if matches:
                hits.append({"path": str(path.relative_to(tree)).replace("\\", "/"), "matches": len(matches),
                             "lines": [f"{n}: {text}" for n, text in matches[:3]]})
            if len(hits) >= limit:
                return hits
    return hits


def cmd_upstream(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    if getattr(args, "skills", None):
        if not args.path:
            raise ArchiveError("upstream --skills needs --path <upstream tree> to read")
        hits = upstream_skill_hits(Path(args.path), str(args.skills))
        return CommandResult({"keyword": args.skills, "tree": args.path, "files": hits,
                              "next": ("read each listed file before the parity verdict; record it with "
                                       "`godmode remember --kind decision --subject \"absorb:<item>\"`")},
                             exit_code=0 if hits else 1)
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
    name = getattr(args, "name", None)
    if name:
        # NS-13c + I-8: a named SOP's standing record is written at first use,
        # so the procedure a session followed is on record beside its steps.
        standing = ensure_sop_record(runtime.archive, name)
        if args.attest:
            record = named_sop_attest(runtime.archive, session, name, args.attest,
                                      result=args.result or "", evidence=args.evidence)
            return CommandResult({"record": _event_view(record),
                                  "standing_record": standing["sequence"]})
        return CommandResult({**named_sop_status(runtime.archive, session, name),
                              "standing_record": standing["sequence"]})
    if args.attest:
        record = sop_attest(runtime.archive, session, args.attest,
                            result=args.result or "", evidence=args.evidence)
        return CommandResult({"record": _event_view(record)})
    return CommandResult(sop_status(runtime.archive, session))


def cmd_hypothesis(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """NS-13f: competing hypotheses, each with a kill experiment."""
    from .godmode_hypothesis import add_hypothesis, hypothesis_status, kill_hypothesis

    _require_archive(runtime)
    if args.hypothesis_command == "add":
        record = add_hypothesis(runtime.archive, args.cause, args.kills,
                                confirms=args.confirms, next_experiment=args.next_experiment,
                                subject=args.subject)
        return CommandResult({"record": _event_view(record),
                              "cite_as": f"hyp:{record['sequence']}",
                              "next": f"godmode hypothesis kill {record['sequence']}"})
    if args.hypothesis_command == "kill":
        outcome = kill_hypothesis(runtime.archive, _session(runtime, args.session),
                                  Path(runtime.anchor.project_root), args.sequence,
                                  timeout=args.timeout)
        return CommandResult(outcome)
    return CommandResult(hypothesis_status(runtime.archive))


def cmd_index(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    project = Path(runtime.anchor.project_root)
    if args.index_command == "rebuild":
        return CommandResult(index_rebuild(runtime.archive, project))
    if args.index_command == "status":
        state = index_fresh(runtime.archive, project)
        return CommandResult(state, exit_code=0 if state["fresh"] else 1)
    if args.index_command == "patterns":
        from .godmode_mistakes import list_patterns
        return CommandResult({"patterns": list_patterns(runtime.archive)})
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
     "open an incident (`--kind incident --repro \"<failing command>\"`) - the third try without one is "
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


_TIME_VOLATILE_ISSUE_CODES = frozenset({"stale-baseline", "stale-lock"})


def _freeze_time_derived_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Replace a wall-clock-derived issue `detail` with a stable one.

    `detect_context_issues` computes `stale-baseline`'s detail from elapsed
    hours since a recorded timestamp, and `stale-lock`'s from elapsed
    minutes a sidecar file's mtime has aged - both against the real clock at
    call time, with no way for `export()` to freeze that clock without
    changing `build_context_brief`'s signature for its other callers. Left
    alone, the same unchanged archive exported hours apart would embed a
    different number and fail byte-identity. `code`, `severity`, and (for
    `stale-baseline`) `confidence` are derived from record counts, not the
    clock, and are kept as-is; only the elapsed-time text is replaced.
    """
    code = issue.get("code")
    if code not in _TIME_VOLATILE_ISSUE_CODES:
        return issue
    frozen = dict(issue)
    if code == "stale-baseline":
        frozen["detail"] = (
            f"Inventory baseline is stale; confidence {issue.get('confidence')}."
        )
    else:
        frozen["detail"] = "A write lock has been held past the staleness threshold."
    return frozen


def export(
    anchor: ProjectAnchor,
    archive: Chronicle,
    destination: Path,
    *,
    token_budget: int = DEFAULT_CONTEXT_BUDGET,
) -> dict[str, Any]:
    """Write the sanitized context brief to `destination` (N-9: export half).

    Two calls over an unchanged archive write byte-identical files WITHIN A
    STABLE WINDOW (final review N8): `stale-baseline`/`stale-lock` issue
    TEXT is frozen to a stable equivalent below, but issue PRESENCE is
    still live state - `(moment - captured).total_seconds() > 86_400` for
    the former, `archive.lock_is_held()` for the latter - so two exports
    straddling that 24h boundary, or one taken while a writer holds the
    lock, can still differ in which issues appear at all, not merely in
    their wording. The brief
    itself is exactly what `build_context_brief` produces; three things are
    canonicalised here, all inside this function so `build_context_brief`'s
    contract for its other callers (e.g. `godmode report --context`) is
    untouched. First, any timestamp stamped at build time (`generated_at`)
    names when THIS export ran, not a fact recorded in the archive, so it
    cannot appear in a file that is supposed to be byte-identical between
    runs - it is returned to the caller instead, alongside `exported_at`,
    and neither reaches the file. Second, `stale-baseline`/`stale-lock`
    issue text embeds elapsed time against the real clock (see
    `_freeze_time_derived_issue`); that text is replaced with a stable
    equivalent, and `estimated_tokens` is recomputed against the frozen
    payload so its value does not silently vary with the digit count of the
    text it replaced. Third, the file is serialised with sorted keys and a
    fixed separator so dict-ordering accidents (dict literal order differs
    across code paths, e.g. the degraded-brief branch) cannot vary the bytes
    even when the content is the same. A `seal` field is then added,
    covering the canonical bytes of every other field in the payload (not
    "everything before it" - `sort_keys=True` places `seal` wherever it
    alphabetically sorts, not last), so a change anywhere else in the file
    surfaces as a single mismatched field rather than a silent diff.
    """
    destination = Path(destination)
    brief = build_context_brief(anchor, archive, token_budget=token_budget)
    generated_at = brief.pop("generated_at", None)
    exported_at = datetime.now(timezone.utc).isoformat()
    brief["raw_archive_included"] = False
    if "issues" in brief:
        brief["issues"] = [_freeze_time_derived_issue(issue) for issue in brief["issues"]]
    if "estimated_tokens" in brief:
        brief["estimated_tokens"] = max(
            1, len(json.dumps(brief, ensure_ascii=False)) // 4
        )
    sealed_body = json.dumps(
        brief, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    seal = hashlib.sha256(sealed_body.encode("utf-8")).hexdigest()
    brief["seal"] = seal
    text = json.dumps(
        brief, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.godmode.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(destination)
    return {
        "exported": True,
        "output": str(destination),
        "raw_archive_included": False,
        "exported_at": exported_at,
        "generated_at": generated_at,
        "seal": seal,
    }


def cmd_export(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    output = Path(args.output).expanduser().resolve(strict=False)
    if output.exists() and not args.overwrite:
        raise ArchiveError("Export target exists; pass --overwrite to replace it")
    result = export(runtime.anchor, runtime.archive, output, token_budget=args.token_budget)
    return CommandResult(result)


def cmd_evals(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    project = Path(runtime.anchor.project_root)
    # NS-12c: with the lessons-and-law layer withheld, what is scored is the
    # skill rather than everything this project has already been corrected
    # about. The mode reaches every runner below explicitly - nothing here
    # reads it back out of the environment.
    withhold_memory = bool(getattr(args, "withhold_memory", False))
    if args.write_snapshots:
        if withhold_memory:
            # The committed fixtures are with-memory artefacts. Freezing a
            # withheld run over them would quietly redefine what the snapshot
            # means, and every later with-memory run would read as drift.
            raise ArchiveError(
                "--write-snapshots records the with-memory fixtures; it cannot "
                "accept a --withhold-memory run. Drop --withhold-memory, or "
                "record that mode with --write-baseline --withhold-memory.")
        return CommandResult({
            "routing": check_snapshots(project, write=True),
            "charter": charter_snapshot(project, write=True),
            "ranking": ranking_snapshot(project, write=True),
            "verdict": "snapshots-written",
        })
    if getattr(args, "write_baseline", False):
        report = eval_ratchet(project, write=True, withhold_memory=withhold_memory)
        return CommandResult(report, exit_code=0 if report["verdict"] == "clean" else 1)
    if getattr(args, "ratchet", False):
        report = eval_ratchet(project, withhold_memory=withhold_memory)
        return CommandResult(report, exit_code=0 if report["verdict"] == "clean" else 1)
    if getattr(args, "determinism", False):
        report = eval_determinism(project)
        return CommandResult(report, exit_code=0 if report["verdict"] == "deterministic" else 1)
    routing = run_routing_evals(project, withhold_memory=withhold_memory)
    # The routing fixtures froze routes taken WITH memory; a withheld run is a
    # different measurement, so it is reported as its own mode instead of
    # being diffed against them (the same rule the ranking snapshot applies to
    # a differing scorer or freshness instrument).
    snapshots = check_snapshots(project) if not withhold_memory else {
        "fixtures": str(project / "evals" / "fixtures"),
        "withhold_memory": True, "diffs": [],
        "verdict": "snapshot-mode-withheld",
    }
    assertions = run_behavior_assertions(project, withhold_memory=withhold_memory)
    charter = charter_snapshot(project)
    ranking = ranking_snapshot(project, withhold_memory=withhold_memory)
    # NS-12f: one row per skill per declared model. A dict, so `--brief`
    # (scalars only) leaves the headline untouched.
    models = cross_model_matrix(project, withhold_memory=withhold_memory)
    payload = {**routing, "snapshots": snapshots, "assertions": assertions,
               "charter": charter, "ranking": ranking, "models": models}
    # A mode-differing ranking comparison is out of contract, not a failure:
    # the snapshot and this environment hold different instruments, and
    # neither is wrong about the other.
    gates = {
        "routing": routing["verdict"] == "routing-sound",
        "snapshots": snapshots["verdict"] in ("behaviour-stable", "snapshot-mode-withheld"),
        "assertions": assertions["verdict"] == "assertions-held",
        "charter": charter["verdict"] == "charter-stable",
        "ranking": ranking["verdict"] in (
            "ranking-stable", "ranking-mode-differs", "ranking-mode-withheld"),
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


_LINE_RANGE = re.compile(r"^(\d+)-(\d+)$")


def _parse_line_range(raw: str | None) -> tuple[int, int] | None:
    if raw is None:
        return None
    match = _LINE_RANGE.match(raw.strip())
    if not match:
        raise ArchiveError(f"--lines must be 'a-b' (e.g. 12-40), not {raw!r}")
    return int(match.group(1)), int(match.group(2))


def cmd_read(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    """I-2: record what was actually opened - a receipt an absorb decision
    can later cite instead of, or alongside, a `file:` evidence line."""
    _require_archive(runtime)
    from .godmode_receipts import record_receipt
    lines = _parse_line_range(getattr(args, "lines", None))
    record = record_receipt(
        runtime.archive, runtime.anchor.project_root, args.source, args.path,
        lines=lines, root=getattr(args, "root", None),
    )
    return CommandResult({"record": _event_view(record)})


def cmd_parity(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    if getattr(args, "sources", False):
        # I-2: per-source files-opened and a surface-only flag, read straight
        # off recorded receipts - no --reference needed for this view.
        from .godmode_receipts import sources_report
        return CommandResult(sources_report(runtime.archive))
    if not args.reference:
        raise ArchiveError(
            "parity needs --reference (an explicit local reference to compare "
            "against), or --sources to report read receipts instead")
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
            {"value": args.reason, "status": "deprecated"}, [f"file:skills/{args.name}"],
            as_operator=getattr(args, "as_operator", False),
            operator_verified=_resolve_operator_verified(runtime, args))
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
    if command == "promote":
        from .godmode_errors import ArchiveError
        from .godmode_lessons import promote as lessons_promote

        try:
            outcome = lessons_promote(
                runtime.archive, args.lesson_seq, list(args.cite or []), args.rerun_hash)
        except ArchiveError as error:
            return CommandResult({"refused": str(error)}, exit_code=1)
        return CommandResult(outcome)
    if command == "approve":
        from .godmode_errors import ArchiveError
        from .godmode_lessons import approve as lessons_approve

        try:
            outcome = lessons_approve(runtime.archive, args.promotion_seq, args.rerun_hash)
        except ArchiveError as error:
            return CommandResult({"refused": str(error)}, exit_code=1)
        return CommandResult(outcome)
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


def cmd_skill_names(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_forge import lint_skill_names
    root = Path(runtime.anchor.project_root) / args.root
    report = lint_skill_names(root)
    return CommandResult(report, exit_code=0 if report["passed"] else 1)


def cmd_skill_validate(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    return CommandResult(validate_skill(args.path))


def cmd_skill_lint(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    from .godmode_forge import lint_skill
    report = lint_skill(args.path)
    return CommandResult(report, exit_code=0 if report["passed"] else 1)


_SUCCESS_EVIDENCE_CITE = re.compile(r"^seq:\d+$")


def cmd_skill_forge(args: argparse.Namespace, runtime: Runtime) -> CommandResult:
    _require_archive(runtime)
    # NS-11d: the procedural layer's promotion bar names its evidence, not
    # just its count - `SkillProposal.repeated_uses` (below) already refuses
    # under three; this is the second half, refused here rather than in the
    # dataclass because `SkillProposal` is also built directly (with no
    # archive in reach) by `tests/test_forge_fixtures.py` and
    # `tests/test_godmode_runtime.py`.
    success_evidence = [str(item) for item in (args.success_evidence or [])]
    if len(success_evidence) < 3:
        raise ArchiveError(
            "skill forge needs --success-evidence seq:<n> at least three "
            "times (NS-11d): a method becomes a skill candidate only after "
            "three recorded successes of one task type, each cited by the "
            f"archive record that proves it; got {len(success_evidence)}"
        )
    malformed = [item for item in success_evidence if not _SUCCESS_EVIDENCE_CITE.match(item)]
    if malformed:
        raise ArchiveError(
            "--success-evidence entries must be 'seq:<n>' citations naming "
            "the record that proves that success; malformed: "
            + ", ".join(malformed)
        )
    # B3: a shape check is not a resolution check. `seq:1 seq:1 seq:1` and
    # `seq:999999` are both well-formed, and both used to create the skill -
    # so the flag counted citations without ever asking whether any of them
    # named a record, which is the bare count NS-11d exists to refuse
    # wearing three copies of the same prefix. Two rules, both decidable
    # from what is in reach here (the archive, required at the top of this
    # function - which is why the check lives in the CLI and not in
    # `SkillProposal`):
    #
    #   1. THREE DISTINCT sequences. One success cited three times is one
    #      success.
    #   2. Each one RESOLVES. A sequence nothing was ever appended at is
    #      not evidence of anything.
    #
    # What is deliberately NOT checked, and is not claimed anywhere in the
    # shipped text either: that the cited records are successes *of this
    # skill's task type*. No record shape in this archive carries a task
    # type a proposal could be matched against - a `decision`, an `action`
    # and an `attestation` are all equally "a record" here - so relatedness
    # would be a guess dressed as a guard. Named in `SKILL.md` as an
    # operator's judgement rather than pretended to in code.
    # Distinctness is over the SEQUENCES, not the strings: `seq:1` and
    # `seq:01` are two spellings of one record.
    cited = [int(item.split(":", 1)[1]) for item in success_evidence]
    if len(set(cited)) < 3:
        raise ArchiveError(
            "--success-evidence needs three DISTINCT records (NS-11d): one "
            "success cited three times is one success; got "
            f"{len(set(cited))} distinct of {len(cited)}"
        )
    from .godmode_fingerprint import existing_sequences
    existing = existing_sequences(runtime.archive)
    dangling = [item for item, sequence in zip(success_evidence, cited)
                if sequence not in existing]
    if dangling:
        raise ArchiveError(
            "--success-evidence must cite records that exist (NS-11d): "
            "`godmode history` lists them. No record at: "
            + ", ".join(sorted(set(dangling)))
        )
    # NS-12a (Task 9, fix round 2 R3): `--pattern` is `type=int, action=
    # "append"`, so `0` and `-1` are accepted by argparse and refused only
    # by the record's own invariant - which runs AFTER `forge_skill` has
    # written the skill to disk and `evaluate_forged_skill` has decided its
    # outcome. Checked here, before anything is created, so a documented
    # flag value cannot buy a forged skill with no record of the attempt.
    pattern_seqs = validate_pattern_seqs(list(getattr(args, "pattern", None) or []))
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
    # NS-12a + NS-12d (Task 9): a forged skill is scored against the eval
    # harness before it is kept - `evaluate_forged_skill` removes it and
    # raises when the skill does not strictly improve (score 0.0, the
    # fixed "before" for something that did not exist a moment ago) over
    # the best any earlier accepted skill_impact recorded for this same
    # target name. `eval_project` is `destination`'s own parent because
    # `forge_skill` always writes into a directory literally named
    # `skills` (the project root's own, or `.grok/skills` on Grok - CX-3),
    # and `godmode_evals.load_suites` always reads `<project>/skills/*`.
    eval_project = Path(destination).expanduser().resolve(strict=False).parent
    impact = evaluate_forged_skill(
        runtime.archive, eval_project, created, patterns=pattern_seqs,
    )
    if impact["outcome"] != "accepted":
        raise ArchiveError(
            f"Forged skill {args.name!r} scored {impact['score_after']} "
            f"(no strict improvement over "
            f"{impact['best_recorded'] if impact['best_recorded'] is not None else impact['score_before']}); "
            f"removed, recorded rejected at seq:{impact['sequence']} "
            "(skill_impact)."
        )
    runtime.archive.append(
        "decision",
        f"skill-created:{args.name}",
        {
            "status": "created",
            "skill": args.name,
            "destination_digest": __import__("hashlib").sha256(str(created).encode()).hexdigest(),
            "repeated_uses": args.repeated_uses,
            "success_evidence": success_evidence,
        },
        evidence=success_evidence,
    )
    return CommandResult({
        "created": True, "path": str(created), "validation": validate_skill(created),
        "skill_impact": impact,
    })


def _evidence(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evidence", action="append", default=[], help="Evidence reference or digest; repeatable")


def _operator_flags(parser: argparse.ArgumentParser) -> None:
    """NS-8k, fix round 1 (F0): the CLI surface `derive_writer`'s
    `operator` value needed. Shared by every verb that writes a record the
    single-writer guard or the status trust order can act on (`remember`,
    `plan --close`, `version`, `skill retire`, and `session open`, the fifth
    and the odd one out: the others claim `operator` trust for the record
    they are writing, while `session open --role checker` uses the same
    verification to GATE a grant stamped into a different, later record)."""
    parser.add_argument(
        "--as-operator", dest="as_operator", action="store_true",
        help="Claim this write as the human operator - outranks agent/checker/"
             "hook records for this subject (NS-8k) and is exempt from the "
             "single-writer close guard (NS-11h). A claim alone is not a "
             "credential: when `authorize setup` has configured a password, "
             "it is verified via --password-stdin or an interactive prompt - "
             "and refused outright (no silent downgrade to agent) if neither "
             "is available, e.g. a non-interactive process with no "
             "--password-stdin. With no password configured at all, an "
             "interactive y/N confirmation is used instead.")
    parser.add_argument(
        "--password-stdin", dest="password_stdin", action="store_true",
        help="Read the operator authorization password from stdin instead of "
             "an interactive prompt; only consulted with --as-operator")


def _one_text(args: argparse.Namespace, positional: str, flag: str, label: str) -> str | None:
    """The one shape every record verb shares (obligation 10372, field
    report 22): the primary text is accepted positionally or through the
    verb's named flag, one meaning in two spellings. Given both ways with
    different text it is ambiguous and refused, never silently picked."""
    spoken = getattr(args, positional, None)
    named = getattr(args, flag, None)
    if spoken and named and spoken != named:
        raise ArchiveError(
            f"{label} was given twice and differently - positional {spoken!r} "
            f"and flag {named!r}; pass it one way")
    return named or spoken or None


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
    # Field report 2026-09-03: an agent guessed `npx godmode resume`,
    # hit a squatted npm name, and got silence. godmode is not an npm
    # package; the ONLY resolvable spelling is this file's own path, so
    # the orientation screen states it before anything else.
    entry = Path(__file__).resolve().parents[1] / "godmode.py"
    import sys as _sys
    lines = ["GODMODE - DAY ONE", "",
             f'  run as: "{_sys.executable}" "{entry}" <verb>   (godmode is '
             "not on npm; `godmode` below abbreviates that command)", ""]
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
    operator.add_argument("--policy", action="store_true",
                          help="Explain the effective authorization policy: the "
                               "operator layer above the project file, and which "
                               "layer decided each key (tightest wins)")
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
    lessons_promote = lessons_sub.add_parser(
        "promote",
        help="NS-2 + NS-10j: cite a structured lesson for graduation, with an "
             "independent re-run hash; refused naming any missing structured field")
    lessons_promote.add_argument("lesson_seq", type=int, help="The lesson record's own sequence number")
    lessons_promote.add_argument("--cite", "--evidence", dest="cite", action="append", default=[],
                                 help="Evidence citation; repeatable, at least one required")
    lessons_promote.add_argument("--rerun-hash", dest="rerun_hash", required=True,
                                 help="sha256 hex digest of this held-out re-run's own evidence")
    lessons_promote.set_defaults(handler=cmd_lessons)
    lessons_approve = lessons_sub.add_parser(
        "approve",
        help="NS-2: approve a promotion with an independent re-run - refused when the "
             "approver is the promoter, or the rerun hash repeats the promotion's own")
    lessons_approve.add_argument("promotion_seq", type=int, help="The lesson_promotion's own sequence number")
    lessons_approve.add_argument("--rerun-hash", dest="rerun_hash", required=True,
                                 help="sha256 hex digest of THIS checker's own independent re-run")
    lessons_approve.set_defaults(handler=cmd_lessons)

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
    config_mode = config_sub.add_parser(
        "mode",
        help="Print this project's mode, or set it (R1: enforce harm, advise "
             "on quality). `advise` (default) leaves every quality-class Stop "
             "gate advisory; `strict` is today's exact behaviour, unchanged. "
             "The harm gates (tag/release/push checks) never read this.")
    config_mode.add_argument("value", nargs="?", choices=("advise", "strict"), default=None,
                             help="Omit to print the current mode")
    config_mode.set_defaults(handler=cmd_config_mode)
    charter.set_defaults(handler=cmd_charter)

    session = sub.add_parser("session", help="Open or close an attested session")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_open = session_sub.add_parser("open")
    session_open.add_argument("--label", default="session")
    session_open.add_argument("--transcript", default=None,
                              help="This session's host transcript; reads in it count toward the required sources")
    session_open.add_argument(
        "--role", choices=["agent", "checker"], default="agent",
        help="Declares this session's role (NS-8k). `checker` is OPERATOR-"
             "GRANTED, not self-declared: it requires --as-operator "
             "verification (see below) and is refused otherwise. Chronicled "
             "on the session record itself (with `role_granted_by: "
             "operator` and `writer: operator` when granted) and exported "
             "as GODMODE_SESSION for this process; a later write only reads "
             "as `checker` when it names THIS process's own session id and "
             "that record carries the operator grant (see "
             "`Chronicle._chronicled_session_role`) - naming a DIFFERENT "
             "session's id, verified or not, mints nothing here.")
    _operator_flags(session_open)
    session_open.set_defaults(handler=cmd_session_open)
    session_close = session_sub.add_parser("close")
    session_close.add_argument("--session")
    session_close.set_defaults(handler=cmd_session_close)

    attest = sub.add_parser("attest", help="Record that a mandated step ran, found nothing, or was skipped")
    attest.add_argument("step", nargs="?", default=None)
    attest.add_argument("--step", dest="step_flag", default=None,
                        help="Alias for the positional step name")
    attest.add_argument("--status", choices=list(STATUSES), required=True)
    attest.add_argument("--result", default="")
    attest.add_argument("--reason", default="", help="Required when the status is 'skipped'")
    attest.add_argument("--rule", action="append", default=[], help="Rule id this step satisfies; repeatable")
    attest.add_argument("--session")
    _evidence(attest)
    attest.set_defaults(handler=cmd_attest)

    verify = sub.add_parser("verify", help="Run a declared check and attest its exit code")
    # Optional: `--falsifiers` names none of its own checks (each due one
    # gets `falsifier:<kind>-<seq>`), so the positional is unused in that mode.
    verify.add_argument("name", nargs="?", default=None)
    verify.add_argument("--rule", action="append", default=[], help="Rule id this check satisfies; repeatable")
    verify.add_argument("--session")
    # Not argparse.REMAINDER: a REMAINDER positional swallows the options that
    # follow the first positional, so --rule would land inside the command.
    # Not `required=True`: `--falsifiers` runs commands it reads off the
    # archive, not one typed here - `cmd_verify` refuses the bare call.
    verify.add_argument("--command", default=None, help="Command to run, as one quoted string")
    # A full-suite attestation is a legitimate half-hour command; the fixed
    # 900s default killed honest runs (self-observed 2026-09-02, twice).
    verify.add_argument("--timeout", type=int, default=900,
                        help="Seconds before the check is recorded as timed "
                             "out (default 900)")
    verify.add_argument("--offline", action="store_true",
                        help="Run under the netgate socket audit with every proxy "
                             "variable pointed at a closed local port; any "
                             "connection seen blocks the attestation")
    verify.add_argument("--falsifiers", action="store_true",
                        help="I-3: run every due falsifier instead - a hypothesis "
                             "claim's or an incident's `refuted_by` command aged "
                             "past two days with no attestation behind it; each "
                             "runs and attests on its own")
    verify.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="With --falsifiers: list the due falsifiers instead "
                             "of running them")
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
    claim.add_argument("--fixes", type=int, default=None, metavar="SEQ",
                       help="The incident this claim fixes: it verifies only when the incident "
                            "holds a red reproduction run and the same repro command is cited "
                            "and green now (with --verify); otherwise it caps at observed")
    claim.add_argument("--depends-on", dest="depends_on", type=int, action="append", default=[],
                       metavar="SEQ", help="A claim this one rests on; the weaker grade is inherited")
    claim.add_argument("--cite", "--evidence", dest="cite", action="append", default=[],
                       help="rec:<hash> or file:<path>#L<n>; repeatable (--evidence is the same flag)")
    claim.add_argument("--external", action="store_true",
                       help="Claim about an external API/library; requires a doc:/url: primary source")
    claim.add_argument("--transcript",
                       help="This session's transcript path; enables the U-T2 red-before-green "
                            "check on a fix claim citing cmd:<command>")
    claim.add_argument("--verify", action="store_true",
                       help="Run every cmd: citation through the attested "
                            "checker first, so the claim stands on "
                            "attestations in one command")
    claim.add_argument("--stale", action="store_true",
                       help="List claims whose cited file evidence changed or "
                            "vanished since they were recorded (grounded claims)")
    claim.add_argument("--timeout", type=int, default=900,
                       help="--verify only: seconds per check (default 900)")
    claim.add_argument("--refuted-by", dest="refuted_by", default=None,
                       help="Hypotheses only: the one command or observation "
                            "that would refute this claim")
    claim.add_argument("--blast-radius", dest="blast_radius", choices=list(BLAST_RADIUS_KINDS),
                       help="PARTIAL-P2: opt in to the scaled evidence bar - a 'verified' grade "
                            "then needs >=2 INDEPENDENT --cite witnesses (distinct citation "
                            "kinds or distinct resolved artifacts), not just >=1 that resolves")
    claim.add_argument(
        "--payload", default=None,
        help="Path to a strict JSON file supplying text/grade/cites/confidence/external/"
             "depends_on instead of the flags above; duplicate keys, unknown fields and "
             "trailing data are refused")
    claim.add_argument("--session")
    claim.set_defaults(handler=cmd_claim)

    criterion = sub.add_parser(
        "criterion",
        help="Record what passing looks like, before the work it judges (E4)",
    )
    criterion.add_argument("--task", required=True, type=subject_text,
                           help="Slug identifying the work this criterion judges")
    criterion.add_argument("text", nargs="?", default=None)
    criterion.add_argument("--text", dest="text_flag", default=None,
                           help="Alias for the positional criterion text")
    criterion.add_argument("--cite", "--evidence", dest="cite", action="append", default=[],
                           help="cmd:<command> the criterion will be judged by; repeatable "
                                "(--evidence is the same flag)")
    criterion.add_argument("--transcript",
                           help="This session's transcript path; enables the ordering check "
                                "(a criterion recorded after work has started)")
    criterion.add_argument("--session")
    criterion.set_defaults(handler=cmd_criterion)

    perimeter = sub.add_parser(
        "perimeter",
        help="Perimeter checks (a boot, an import walk, a typed route) that must run this "
             "session before `session close` - the check a green unit suite never performs")
    perimeter.add_argument("action", choices=["add", "list", "run", "retire"])
    perimeter.add_argument("command", nargs="?", default=None,
                           help="For add/retire: the exact command (quote it)")
    perimeter.add_argument("--session")
    perimeter.add_argument("--timeout", type=int, default=900)
    perimeter.set_defaults(handler=cmd_perimeter)

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
    # --claim/--value/--witness/--checker are not argparse-required: --payload
    # can supply all four instead (strict payload, see below); cmd_verdict_record
    # refuses with a named remedy when neither route filled them in.
    verdict_record.add_argument("--claim", default=None)
    verdict_record.add_argument("--value", default=None, help="The claimed value the checker verifies")
    verdict_record.add_argument("--witness", default=None, help="file:<path> or seq:<n>")
    verdict_record.add_argument("--checker", action="append", default=[],
                                help="Checker command, as one quoted string; runs against the witness "
                                     "alone. Repeatable - each --checker is one independent panel "
                                     "member; N checkers fold to one disposition (U-E4).")
    verdict_record.add_argument("--checked", action="append", default=[],
                                help="One thing the panel actually checked; repeatable")
    verdict_record.add_argument("--not-checked", dest="not_checked", action="append", default=[],
                                help="One thing the panel did NOT check; repeatable - a 'confirmed' "
                                     "disposition is refused while this is non-empty (N-11)")
    verdict_record.add_argument("--criterion", action="append", default=[],
                                help="name=evidence, repeatable - a 'confirmed' disposition is refused "
                                     "if any named criterion's evidence is empty (N-11)")
    verdict_record.add_argument(
        "--payload", default=None,
        help="Path to a strict JSON file supplying claim/value/witness/checker/checked/"
             "not_checked/criteria/run_state/acquitted_by/timeout/tool_error_ack instead "
             "of the flags above; duplicate keys, unknown fields and trailing data are refused")
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
    # C-9: `--checks` needs no subcommand, so the subcommand itself is
    # optional now - `governance` with neither prints the short usage note
    # `cmd_governance_bare` returns instead of argparse's own error.
    governance.add_argument(
        "--checks", action="store_true",
        help="Print the done-bar check -> role table (reviewer/builder)")
    governance.set_defaults(handler=cmd_governance_bare)
    governance_sub = governance.add_subparsers(
        dest="governance_command", required=False)
    governance_show = governance_sub.add_parser(
        "show", help="The current review surface, with provenance per candidate")
    governance_show.set_defaults(handler=cmd_governance_show)
    governance_promote = governance_sub.add_parser(
        "promote", help="Adopt a reviewed candidate; requires a reason")
    governance_promote.add_argument("--candidate", required=True)
    governance_promote.add_argument("--reason", required=True,
                                    help="Who reviewed it, and why")
    governance_promote.set_defaults(handler=cmd_governance_promote)
    governance_escalate = governance_sub.add_parser(
        "escalate",
        help="Record a builder's reason for skipping one done-bar check")
    governance_escalate.add_argument("check")
    governance_escalate.add_argument(
        "--reason", required=True,
        help="Why this check does not apply here, for a few turns")
    governance_escalate.set_defaults(handler=cmd_governance_escalate)

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
        "--deep", action="store_true",
        help="run the minimality section too (atlas build and pairwise duplicate "
             "scan; minutes on a large tree); the report names its seconds per section")
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
    method.add_argument("--observed-in", dest="observed_in", default="unknown",
                        choices=["production", "staging", "dev", "unknown"],
                        help="Where the failure was observed; anything but production carries the "
                             "measurement-environment question into the answer")
    method.add_argument("--unreproducible", action="store_true")
    method.add_argument("--ordering", action="store_true", help="An ordering, race or latch-time question")
    method.add_argument("--components", action="store_true", help="Components and failure modes are enumerable")
    method.add_argument("--conditions", type=int, default=0, help="Contributing conditions on one failure")
    method.add_argument("--check-method", choices=list(METHOD_NAMES),
                        help="Check a finished RCA record against its method's completion contract")
    method.add_argument("--check-record", help="Path to the RCA record as JSON")
    method.set_defaults(handler=cmd_method)

    status = sub.add_parser("status", help="Single writable status store")
    # Field report file 2026-09-10, Part 3: a bare `status` errored; it
    # now prints the survey, the same as `status survey`.
    status_sub = status.add_subparsers(dest="status_command", required=False)
    status.set_defaults(handler=cmd_status_bare)
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
    status_remaining.add_argument(
        "--since", type=int, metavar="DAYS",
        help="Hide open items older than DAYS (count reported as stale_hidden); "
             "the age split is always reported")
    status_remaining.add_argument("--digest", action="store_true",
                                  help="The session digest: loop episodes, error classes, parked claims, "
                                       "obligations open/attested/waived, measured spend, host grade, next action")
    status_remaining.add_argument("--transcript", default=None,
                                  help="--digest: the host transcript to read loop episodes and spend from")
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
    ownership = sub.add_parser(
        "ownership",
        help="Show which gate rule owns each path or command, and refuse a stale decision table",
    )
    ownership.add_argument("--check", action="store_true", help="Walk the repo and report ownership")
    ownership.add_argument("--diff-only", action="store_true",
                            help="Scope the walk to working-tree changes only")
    ownership.set_defaults(handler=cmd_ownership)
    scenarios = sub.add_parser("scenarios", help="Stage known failures and check a control notices")
    scenarios.add_argument("--only", help="Run a single scenario by name")
    scenarios.set_defaults(handler=cmd_scenarios)

    recurrences_parser = sub.add_parser(
        "recurrences",
        help="Find controls that blocked twice on the same cause; with --against, match a new report "
             "against the fixed registry's symptom column")
    recurrences_parser.add_argument("--registry", metavar="PATH", default=None,
                                    help="The fixed-registry markdown table (default: docs/FIXED-REGISTRY.md)")
    recurrences_parser.add_argument("--against", metavar="TEXT", default=None,
                                    help="A new report or feedback text to match against registry symptoms")
    recurrences_parser.add_argument("--propose", action="store_true",
                                    help="Registry rows the record proposes: a reason that waived work three times")
    recurrences_parser.set_defaults(handler=cmd_recurrences)
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

    hygiene_parser = sub.add_parser(
        "hygiene", help="Near-duplicate and contradicting lessons and decisions, as a review list")
    hygiene_parser.add_argument("--cap", type=int, default=80,
                                help="Newest active records considered per kind (default 80)")
    hygiene_parser.set_defaults(handler=cmd_hygiene)

    forget_parser = sub.add_parser(
        "forget",
        help="Expire old episodes into a cold, still-chained segment (action and "
             "refusal after 30 days, attestation after 90; a record cited by a live "
             "claim, a checkpoint, a law guard or a pin never expires); report "
             "supersession chains; flag same-subject value contradictions",
    )
    forget_parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what a real pass would do and record nothing (the disposable "
             "read caches a plain read refreshes are still refreshed)")
    forget_parser.add_argument(
        "--now", default=None,
        help="ISO-8601 timestamp to measure every TTL against; accepted with "
             "--dry-run only, so a fabricated clock can never expire anything")
    forget_parser.set_defaults(handler=cmd_forget)

    oracle_parser = sub.add_parser(
        "oracle", help="Held-back checks the operator designates; the done bar runs them, the agent never picks them")
    oracle_sub = oracle_parser.add_subparsers(dest="oracle_command", required=True)
    oracle_hold = oracle_sub.add_parser("hold", help="Designate a held-back check (password)")
    oracle_hold.add_argument("--command", required=True, help="The check to hold back")
    oracle_hold.add_argument("--password-stdin", action="store_true",
                             help="Read the password from standard input instead of prompting")
    oracle_hold.set_defaults(handler=cmd_oracle)
    oracle_sub.add_parser("list", help="The held-back checks by digest").set_defaults(handler=cmd_oracle)
    oracle_run = oracle_sub.add_parser("run", help="Run every held-back check and attest each outcome")
    oracle_run.add_argument("--timeout", type=int, default=900)
    oracle_run.set_defaults(handler=cmd_oracle)

    scope_parser = sub.add_parser("scope", help="Enumerate the work before reasoning about it")
    scope_parser.add_argument("--since", help="Compare against this ref instead of the working tree")
    scope_parser.add_argument("--full", action="store_true")
    scope_parser.add_argument("--minimality", action="store_true",
                              help="Report size pressure on the change; never blocks")
    scope_parser.set_defaults(handler=cmd_scope)

    atlas = sub.add_parser("atlas", help="Map the project's symbols and their relationships")
    atlas.add_argument("--budget", type=float, default=120.0,
                       help="Seconds the build may spend before it stops and states the gap "
                            "(default 120; 0 means no ceiling)")
    atlas.add_argument("--direction", action="store_true",
                       help="Check dependency direction: hooks import the runtime only through "
                            "the declared surface, and the runtime never imports hooks; "
                            "exits 1 on any finding. Standalone - no subcommand needed.")
    atlas.set_defaults(handler=cmd_atlas)
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=False)
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
    # Field report 26: the fix-shaped nudge says `godmode atlas closure
    # <files>` and the parser only took `--changed`; the documented shape
    # was refused. One meaning, two spellings, like the record verbs.
    atlas_closure.add_argument("changed_positional", nargs="*", default=None,
                               help="Changed paths (alias for --changed)")
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
    atlas_graph = atlas_sub.add_parser(
        "graph", help="NS-3: a typed, time-valid evidence graph derived from the archive's own records")
    atlas_graph.set_defaults(handler=cmd_atlas)
    atlas_graph_sub = atlas_graph.add_subparsers(dest="graph_command", required=False)
    atlas_graph_sub.add_parser(
        "rebuild", help="Derive the graph fresh from the archive and save its snapshot"
    ).set_defaults(handler=cmd_atlas)
    atlas_graph_query = atlas_graph_sub.add_parser(
        "query", help="BFS impact and required retests over the last saved snapshot")
    atlas_graph_query.add_argument(
        "node", help="Node id (e.g. obligation:<subject>, module:<dotted.name>) or file:<path>")
    atlas_graph_query.add_argument("--depth", type=_positive_int, default=3)
    atlas_graph_query.set_defaults(handler=cmd_atlas)
    atlas_graph_sub.add_parser(
        "verify", help="Rebuild fresh and fail (exit 1) when the hash disagrees with the last snapshot"
    ).set_defaults(handler=cmd_atlas)
    atlas_loop = atlas_sub.add_parser(
        "loop", help="NS-1: loop records - a chained failure signature per retry attempt")
    atlas_loop.set_defaults(handler=cmd_atlas)
    atlas_loop_sub = atlas_loop.add_subparsers(dest="loop_command", required=False)
    atlas_loop_advance = atlas_loop_sub.add_parser(
        "advance",
        help="Record one retry attempt's failure signature; refused (exit 2) "
             "the third time it repeats, or when a declared budget is exhausted")
    atlas_loop_advance.add_argument("--task", required=True, help="The task this attempt belongs to")
    atlas_loop_advance.add_argument(
        "--failing", nargs="+", default=[], metavar="ID",
        help="Failing test ids this attempt produced; part of the failure signature")
    atlas_loop_advance.add_argument(
        "--diff-from-git", action="store_true", dest="diff_from_git",
        help="Derive the diff shape (files touched, hunk count) from the working "
             "tree's own unstaged diff instead of an empty one")
    atlas_loop_advance.set_defaults(handler=cmd_atlas)
    atlas_loop_resume = atlas_loop_sub.add_parser(
        "resume",
        help="Reopen a halted task; refused unless the cited evidence was "
             "written by a different actor than the one who halted it")
    atlas_loop_resume.add_argument("--task", required=True, help="The halted task to reopen")
    atlas_loop_resume.add_argument(
        "--evidence", required=True, metavar="CITE",
        help="seq:<n> citation of a record written by a different actor than "
             "whoever wrote the halt")
    atlas_loop_resume.set_defaults(handler=cmd_atlas)

    atlas_law = atlas_sub.add_parser(
        "law", help="NS-4: falsification bonds gate ratification - the checker must prove it can fail")
    atlas_law.set_defaults(handler=cmd_atlas)
    # `dest="atlas_law_command"`, distinct from the unrelated top-level
    # `law` verb's own `law_command` dest just below - two separate
    # subparser trees, never confused in one parsed Namespace.
    atlas_law_sub = atlas_law.add_subparsers(dest="atlas_law_command", required=False)
    atlas_law_propose = atlas_law_sub.add_parser(
        "propose",
        help=f"Propose a law/guard/skill change (capped at {BONDS_MAX_PROPOSALS_PER_SPRINT} open at a time)")
    atlas_law_propose.add_argument("--target", required=True, help="Path the proposal changes")
    atlas_law_propose.add_argument("--diff", required=True, help="Path to the diff file this proposal applies")
    atlas_law_propose.add_argument("--cite", "--evidence", dest="cite", action="append", default=[],
                                   help="Evidence citation; repeatable, at least one required")
    atlas_law_propose.set_defaults(handler=cmd_atlas)
    atlas_law_bond_test = atlas_law_sub.add_parser(
        "bond-test",
        help="Prove THIS checker session can fail, by planting a synthetic bad case (same shape as `plant`)")
    atlas_law_bond_test.add_argument("name")
    atlas_law_bond_test.add_argument("--command", required=True, help="Checker command, as one quoted string")
    atlas_law_bond_test.add_argument("--file", required=True, help="File to break, relative to the project")
    atlas_law_bond_test.add_argument("--replace", help="Text to replace in that file")
    atlas_law_bond_test.add_argument("--with", dest="with_text", default="", help="Replacement text")
    atlas_law_bond_test.add_argument("--append", help="Line to append instead of replacing")
    atlas_law_bond_test.add_argument("--rule", action="append", default=[])
    atlas_law_bond_test.set_defaults(handler=cmd_atlas)
    atlas_law_ratify = atlas_law_sub.add_parser(
        "ratify", help="Accept a proposal - refused without a fresh, passing bond in this checker session")
    atlas_law_ratify.add_argument("proposal_seq", type=int, help="The improvement_proposal's own sequence number")
    atlas_law_ratify.add_argument(
        "--diff", default=None,
        help="Required when the proposal targets a skills/<name>/... path (NS-12d): "
             "the SAME diff file --diff hashed at propose time; applied and scored "
             "before the verdict is written, and restored on anything short of a "
             "strict score improvement")
    atlas_law_ratify.add_argument(
        "--pattern", dest="pattern", action="append", type=int, default=[],
        help="A pattern record's own sequence this skill_impact cites; repeatable")
    atlas_law_ratify.set_defaults(handler=cmd_atlas)

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
    hooks_status.add_argument(
        "--matrix", action="store_true",
        help="R-4: regenerate docs/HOST-FEATURE-REACH.md's tables from "
             "godmode_reach and HOST_CAPABILITIES instead of reporting one "
             "host's wiring; refuses (exit 2) if a hook host cites no "
             "reference and no replicating test (R-0 guard)")
    hooks_status.add_argument(
        "--write", action="store_true",
        help="Only valid with --matrix: write the regenerated doc instead "
             "of only reporting whether it has drifted (exit 1 if so); "
             "refused (exit 2) without --matrix")
    hooks_status.set_defaults(handler=cmd_hooks)
    hooks_probe = hooks_sub.add_parser(
        "probe",
        help="Send a synthetic marker operation through the real hook and verify it was denied")
    hooks_probe.add_argument(
        "--host", help="Host label to record the proof under (default: detected)")
    hooks_probe.set_defaults(handler=cmd_hooks)
    hooks_time = hooks_sub.add_parser(
        "time", help="Time the real hook on a synthetic payload, against the declared timeout")
    hooks_time.add_argument("--event", choices=["session-start", "pre-action", "stop"], default="pre-action")
    hooks_time.add_argument("--runs", type=int, default=3)
    hooks_time.add_argument("--host", help="Host whose declared timeout to compare against (default: detected)")
    hooks_time.set_defaults(handler=cmd_hooks)
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
        "--host", help="codex (default: project hooks fallback), opencode (Bun shim), "
                       "antigravity, copilot, or kiro")
    hooks_wire.add_argument(
        "--force", action="store_true",
        help="Overwrite a differing (CONFLICT) existing file; cannot force past one "
             "that is malformed or an unrecognized shape (INVALID) - fix or remove it")
    hooks_wire.add_argument(
        "--all", action="store_true",
        help="R-5: wire every known host (codex, antigravity, opencode, copilot, kiro) "
             "through the one code path [CREATE]/[UPDATE]/[OK]/[CONFLICT]/[INVALID] lines "
             "report, dry-run or not")
    hooks_wire.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Preview wiring with the exact code path an apply would use; writes nothing")
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
    context_status.add_argument(
        "--rebaseline", action="store_true",
        help="With --scan: after reporting drift, record the current tree as "
             "the new inventory baseline (what `context rebuild` does) - "
             "measure and accept in one call")
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
        "why", help="Show recorded decisions, fixes, dependencies, invariants, and "
                    "recent episodes about a path or topic"
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
    history.add_argument("--seq", type=int, default=None,
                         help="Read one record by sequence number, hot or cold "
                              "(NS-11g: reaches a godmode-forget-rotated cold segment)")
    history.set_defaults(handler=cmd_history)

    plan = sub.add_parser("plan", help="Record a private execution contract")
    plan.add_argument("title_positional", nargs="?", default=None, type=subject_text,
                      help="Alias for --title")
    plan.add_argument("--title", required=False, type=subject_text)
    plan.add_argument("--step", action="append", default=[])
    plan.add_argument("--obligation", action="append", default=[])
    plan.add_argument("--done", action="append", default=[], metavar="STEP",
                      help="Finish a step of the latest plan, by number or by a unique substring; repeatable")
    plan.add_argument("--close", action="store_true",
                      help="Finish every step of the latest plan and close it")
    _operator_flags(plan)
    _evidence(plan)
    plan.set_defaults(handler=cmd_plan)

    build = sub.add_parser("build", help="Record an implementation result")
    build.add_argument("summary_positional", nargs="?", default=None,
                       help="Alias for --summary")
    build.add_argument("--summary", required=False)
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
    checkpoint.add_argument("--owes", action="append", default=[],
                            help="A temporary change this checkpoint leaves behind that must be restored "
                                 "(an admin role bump, a throwaway spec); recorded as an open obligation "
                                 "the scope gate names until it is closed. Repeatable.")
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
    checklist_template = checklist_sub.add_parser(
        "template", help="Print a checklist template's items as paste-ready update rows")
    checklist_template.add_argument("template", choices=["rca"])
    checklist_template.add_argument("--for", dest="label", default="incident",
                                    help="The label the items are filed under: <template>:<label>:<step>")
    checklist_template.set_defaults(handler=cmd_checklist_template)

    remember = sub.add_parser(
        "remember",
        help="Record a decision, invariant, lesson, obligation, assumption, or request",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "closing an ask:\n"
            "  The stop hook names each open operator ask as ask:<hex>, the first\n"
            "  twelve characters of the ask's digest. Close one with exactly the line\n"
            "  it prints:\n"
            '    godmode remember --kind request --subject "ask:<hex>" --status closed\n'
            "  No --value is needed for a status change. `godmode history --kind\n"
            "  request` lists the recorded asks with their subjects."))
    remember.add_argument(
        "--kind",
        # U-S4 - "assumption" added for the assumption gate
        # (`godmode_attest.assumption_gate`); the record kind itself lives
        # in EVENT_KINDS (godmode_constants.py).
        # NS-11e fix round 1 (review B, B4): "review" - the contradiction
        # `godmode forget` files. It is never MINTED here (the pass writes
        # it, and `cmd_remember` refuses a subject with no review on
        # record); this is the closure path, so `--status acknowledged` /
        # `dismissed` has a verb to go through.
        choices=["decision", "invariant", "lesson", "obligation", "assumption", "request",
                 "incident", "pattern", "review"],
        required=True)
    remember.add_argument("--failure-class", dest="failure_class", default=None,
                          help="incident only: one of the closed failure classes "
                               "(off-list refused with the list rendered)")
    remember.add_argument("--load-bearing", dest="load_bearing", action="store_true",
                          help="assumptions only: this is the premise the work rests on; "
                               "requires --evidence naming what fails without it")
    remember.add_argument("--turning-point", dest="turning_point", action="store_true",
                          help="incident only: the first failure the run never recovered "
                               "from; requires --evidence")
    # Field report 2026-09-02: an agent dictated `remember --kind incident
    # "<prose>"` the way `claim` accepts prose, hit a usage error, and the
    # incident never reached the record. A refusal that loses the record is
    # worse than a derived subject - the positional text form now works for
    # every kind, deriving the subject from the opening words.
    remember.add_argument("text", nargs="?", default=None,
                          help="Dictation form: the whole record as one quoted "
                               "string; the subject is derived from its opening "
                               "words when --subject is not given")
    remember.add_argument("--subject", default=None, type=subject_text)
    remember.add_argument("--value", default=None)
    remember.add_argument("--status", default=None,
                          help="Default: active, or open for a request or a review; a "
                               "review closes with acknowledged or dismissed")
    remember.add_argument("--guard")
    # NS-10j (0.3.28 Plan 5 Task 2): a lesson's structured schema. All four
    # optional; giving at least one opts the write into the schema check
    # (`godmode_lessons.normalize_lesson_write`) - a plain `--guard`-only
    # lesson (the pre-existing advisory shape: enforce predicates, standing
    # guards) is untouched. `--falsifier`, not `--refuted-by`: that flag
    # already means something else for `--kind incident`.
    remember.add_argument("--root-cause", dest="root_cause", default=None,
                          help="Lessons (NS-10j): why the failure happened")
    remember.add_argument("--correction", dest="correction", default=None,
                          help="Lessons (NS-10j): what was actually done to fix it")
    remember.add_argument("--reflection", dest="reflection", default=None,
                          help="Lessons (NS-10j): what generalizes beyond this one instance")
    remember.add_argument("--falsifier", dest="falsifier", default=None,
                          help="Lessons (NS-10j): what observation would show the guard "
                               "is wrong (stored as this lesson's own 'refuted_by' - "
                               "distinct from --refuted-by, which is --kind incident's "
                               "own field)")
    remember.add_argument("--blocked-by", dest="blocked_by", action="append", default=[],
                          help="Obligations only: the id of another obligation blocking "
                               "this one (repeatable); `status remaining` lists this "
                               "obligation under its blocker; a blocker that does not "
                               "exist, or one that would close a cycle, is refused")
    remember.add_argument("--standing", action="store_true",
                          help="Obligations: a per-task duty with no subject "
                               "to match - surfaces at every stop, survives "
                               "quiet posture (definition-of-done, not "
                               "advisory). Lessons: the guard is pinned into "
                               "the brief ahead of the newest guards, and "
                               "never drops off as newer lessons arrive")
    remember.add_argument(
        "--enforce", default=None,
        help="Lessons only, requires --guard: "
             "'kind=<record kind>;predicate=<field op value>' - a later "
             "write of that kind whose data matches the predicate ('field "
             "== literal', 'field contains literal', or 'field matches "
             "<regex>', read over the incoming record's data) is refused "
             "with this lesson's guard as the remedy; a malformed spec is "
             "refused now, at remember time. Kind may not be 'refusal', "
             "'action', or 'checkpoint' (the gate's own audit trail, "
             "exempt from enforcement - see below). Literals cap at 256 "
             "characters. A 'matches' regex may carry at most ONE "
             "quantifier ('+', '*', '?', '{n}', '{n,}', '{n,m}') anywhere "
             "in the pattern, bound to a single atom or character class, "
             "never a group, and no alternation ('|') inside a group - a "
             "second quantifier, a grouped one or a grouped alternation is "
             "refused at remember time, with a remedy naming 'contains'. "
             "A scanned field over 4096 characters is truncated for "
             "'contains'/'==', but a 'matches' rule REFUSES the write "
             "outright when its field is that long, fail-closed, rather "
             "than risk a truncated regex inventing a match. A write made "
             "by a hook (a session's own hook process, never a role a "
             "caller can declare) is always exempt from every enforce "
             "rule")
    remember.add_argument("--predicts", default=None,
                          help="Incident only: a check the hypothesis requires to come out a particular way")
    remember.add_argument("--refuted-by", dest="refuted_by", default=None,
                          help="Incident only: the one command or observation that "
                               "would refute this hypothesis; an unrun one ages into "
                               "a preflight finding after two days (see `verify "
                               "--falsifiers`)")
    remember.add_argument("--repro", default=None,
                          help="Incident: the command that reproduces the failure. It runs "
                               "now (argv, no shell) and its exit code is recorded; a fix "
                               "claim (`claim --fixes <seq>`) verifies only when it is green "
                               "later. Same as --evidence \"repro:<command>\"")
    remember.add_argument("--no-repro", dest="no_repro", default=None,
                          help="Incident: why there is no reproduction command yet; the "
                               "incident is then classed underspecified-ask")
    remember.add_argument("--hypothesis", default=None,
                          help="Incident only: the explanation itself, in your own "
                               "words - what --refuted-by is a falsifier for. The "
                               "two-reversals gate (a third edit after two red "
                               "retests of one check) only lifts once an incident "
                               "names both")
    remember.add_argument("--intent-preserved", dest="intent_preserved", choices=["kept", "replaced"],
                          default=None, help="On a reopen: the agent's decision was kept and reworded, or replaced")
    remember.add_argument("--class", dest="pattern_class", default=None,
                          help="Pattern only: one of the closed failure classes "
                               "(off-list refused with the list rendered) - the "
                               "same vocabulary a preflight finding's own class "
                               "is drawn from")
    remember.add_argument("--occurrence", dest="occurrence", default=None,
                          help="Pattern only: seq:<n> naming the record that "
                               "shows one instance of this recurring failure; "
                               "a second occurrence on the same --subject "
                               "appends to the existing pattern instead of "
                               "creating a duplicate")
    remember.add_argument("--review", dest="review", default=None,
                          help="Review only: seq:<n> naming the review record this "
                               "one closes. One subject can carry several open "
                               "reviews at once (a later pass finds a third "
                               "disagreeing record and flags a wider set), so with "
                               "two or more open the close refuses and lists them "
                               "rather than guessing; with exactly one open, this "
                               "is optional")
    remember.add_argument("--source", choices=["stated", "inferred"], default="stated",
                          help="Requests only: whether the operator stated this ask "
                               "or the agent inferred it on their behalf")
    remember.add_argument("--supersedes", type=int, default=None, metavar="SEQ",
                          help="NS-10e: this record replaces the record at sequence "
                               "SEQ - same --kind, not already itself superseded. "
                               "`history --subject <s>` then renders the chain "
                               "(seq -> seq) instead of a flat, ambiguous overwrite; "
                               "every latest-per-subject reader stops treating SEQ "
                               "as current. Not for --kind incident or pattern, "
                               "which already have their own evolution mechanism")
    # U-S4 - assumption records only; every other kind is session-agnostic
    # and leaves this unused. Falls back to the latest open session, same as
    # `claim`/`criterion`/`gate`.
    remember.add_argument("--session",
                          help="Assumption records only: defaults to the latest open session")
    _operator_flags(remember)
    _evidence(remember)
    remember.set_defaults(handler=cmd_remember)

    topology_parser = sub.add_parser(
        "topology",
        help="The archive's record-kind transitions as a map - transitions "
             "seen mostly in failing sessions are named as warnings; "
             "association, not cause")
    topology_parser.set_defaults(handler=cmd_topology)
    digest_parser = sub.add_parser(
        "digest",
        help="The archive told as dated prose - what happened, in order, "
             "assembled verbatim from record fields; no model, no paraphrase")
    digest_parser.add_argument("--since", type=int, default=0,
                               help="Start the story at this sequence")
    digest_parser.set_defaults(handler=cmd_digest)
    doctor = sub.add_parser("doctor", help="Verify archive and continuity health")
    doctor.add_argument("--deep", action="store_true")
    doctor.add_argument(
        "--host", help="Check one host's wiring instead: hook artifact present and "
                       "parsing, interpreter on PATH, archive writable, interception grade")
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
    precheck_parser.add_argument("--dirty", action="store_true",
                                 help="--preflight only: validate a snapshot of the "
                                      "working tree's tracked changes instead of "
                                      "refusing a dirty tree (field report 22: the "
                                      "gate could only run after a gated commit)")
    precheck_parser.add_argument("--preflight", action="store_true",
                                 help="Push preflight instead: validate HEAD in a "
                                      "disposable worktree - banned-term scan plus the "
                                      "designated --suite - findings triaged mechanical "
                                      "vs judgment; feeds the password gate, never "
                                      "bypasses it")
    precheck_parser.add_argument("--suite", nargs="+", default=None,
                                 help="With --preflight: the command to run inside the "
                                      "worktree (e.g. python -m unittest ...)")
    precheck_parser.add_argument("--suite-shards", dest="suite_shards", type=int, default=1,
                                 help="With --preflight: run a `discover` suite as N sequential "
                                      "shards (one process over the whole suite is killed for "
                                      "memory on small machines)")
    precheck_parser.add_argument("--shard-index", dest="shard_index", type=int, default=None,
                                 help="With --preflight --suite-shards N: run only this "
                                      "shard (0 to N-1) and attest it as one leg, not as "
                                      "the suite - the shape a CI matrix runs in parallel; "
                                      "an index outside the range is refused, never clamped")
    precheck_parser.add_argument("--designate-suite", metavar="CMD",
                                 help="Record the suite durably: every later "
                                      "--preflight runs it without being asked - "
                                      "the ratchet form of --suite")
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
    privacy = sub.add_parser("privacy", help="Audit the local privacy boundary")
    privacy.add_argument("--repo", action="store_true",
                         help="Scan the TRACKED tree instead of the archive: emails, home paths, "
                              "IP addresses, secret shapes, and files at or over --large-bytes, "
                              "each named by path and line with the value masked")
    privacy.add_argument("--large-bytes", type=int, default=5_000_000,
                         help="--repo: report tracked files at or over this size (default 5000000)")
    privacy.set_defaults(handler=cmd_privacy)

    law = sub.add_parser(
        "law",
        help="The generated per-project Code of Law (Sprint L1: compile guarded "
             "lessons into GODMODE-CODE-OF-LAW.md + wrapper skill)")
    law_sub = law.add_subparsers(dest="law_command", required=True)
    law_compile = law_sub.add_parser(
        "compile",
        help="Fold every guarded lesson into the bounded law file (on a "
             "pre-gate archive's first run this also appends one migration "
             "record grandfathering the laws recorded before the authority "
             "gate; it is the only write this verb makes)")
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
    _operator_flags(law_amend)
    law_amend.set_defaults(handler=cmd_law_amend)
    law_candidates_parser = law_sub.add_parser(
        "candidates",
        help="Correction candidates clustered by keywords, with recurrence counts")
    law_candidates_parser.set_defaults(handler=cmd_law_candidates)
    law_hygiene = law_sub.add_parser(
        "hygiene",
        # Fix round 1 (nit 1): the help said "scan" while the verb had
        # started writing. It bounds the live candidate set, which appends
        # one `lesson_candidate` shelf note when that set is over cap, so
        # the help says so rather than leaving an operator to find out
        # from the archive.
        help="Maintenance pass: laws with no recorded origin, contradictory "
             "pairs, guards a recorded check now enforces mechanically, and "
             "candidate clusters past the promotion bar with no promotion - "
             "names candidates, never retires. Also bounds the live "
             "candidate set, appending one shelf note when it is over cap "
             "(reported under shelved_candidates); that note is the only "
             "write this verb makes, and it deletes nothing")
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

    retest = sub.add_parser(
        "retest",
        help="Every test that pins a changed file (names its path, module, or stem), as one command "
             "per runner; --run executes it and attests the exit code as `retest`")
    retest.add_argument("--base", default="HEAD")
    retest.add_argument("--run", action="store_true")
    retest.add_argument("--session")
    retest.add_argument("--timeout", type=int, default=900)
    retest.set_defaults(handler=cmd_retest)

    ratchet = sub.add_parser(
        "ratchet",
        help="Run the project's declared debt counters (.godmode-ratchets.json: name -> command), "
             "record each value, name every counter that rose")
    ratchet.add_argument("action", choices=["run", "list"])
    ratchet.add_argument("--timeout", type=int, default=600)
    ratchet.set_defaults(handler=cmd_ratchet)

    release_notes = sub.add_parser(
        "release-notes",
        help="Build a version's release note from its CHANGELOG section, or check an existing one: "
             "present, every entry covered, no empty section, no process narration, a Verifying section")
    release_notes.add_argument("action", choices=["build", "check"])
    release_notes.add_argument("version", nargs="?", default=None,
                               help="Version, e.g. 0.3.25; defaults to the runtime version")
    release_notes.add_argument("--force", action="store_true", help="build: overwrite an existing note")
    release_notes.set_defaults(handler=cmd_release_notes)

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
    loop.add_argument("--transcript", default=None,
                        help="Read iteration episodes from this host transcript (PRD P-1/P-3): "
                             "error signature, overlapping hunks, no new files, no new assertion")
    loop.add_argument("--episodes", action="store_true",
                        help="With --transcript: list every episode and the backtrack context for each loop")
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
        "integrity", help="Run the thirteen test-integrity monitors over the current diff"
    )
    integrity.add_argument("--base", default="HEAD",
                           help="Git ref to diff the working tree against, or a range A..B / A...B")
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
    staging.add_argument("--without-preflight", metavar="REASON", default=None,
                         help="Stage a push without a green preflight at HEAD; the reason is recorded")
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
    branches.add_argument("--role", choices=("maintained", "throwaway"),
                          help="With --record: declare this branch's role (maintained branches "
                               "need a plan for multi-file changes and a test with a code change; "
                               "declaring a branch throwaway needs --as-operator)")
    _operator_flags(branches)
    branches.set_defaults(handler=cmd_branches)

    version = sub.add_parser("version", help="Record a version fact, or reconcile every surface")
    version.add_argument("--reconcile", action="store_true",
                         help="Diff the version across every surface that states one")
    version.add_argument("--name", default="")
    version.add_argument("--value", default="")
    version.add_argument("--status", default="observed")
    _operator_flags(version)
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
             "SOFT charter-rule proposals only, nothing auto-written; also reports "
             "`forget_due`, when the last `godmode forget` pass ran and what it did",
    )
    # NS-11e (review B, N8): `forget_due` is part of what this verb reports,
    # so the help says so rather than leaving a new key undocumented.
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
        "--skills", metavar="KEYWORD", default=None,
        help="With --path: list the upstream tree's skill and doc files (SKILL.md, docs/*.md, "
             "*.md under skills/, .agents/, .claude/) that mention KEYWORD, with line numbers - the "
             "parity read the field asked for (Part 5, 2026-09-10); records nothing")
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

    sop = sub.add_parser("sop", help="Troubleshooting (T0-T14), PDCA, OODA and research SOP "
                                     "status and attestation")
    sop.add_argument("--name", choices=sorted(SOPS),
                     help="A named SOP; omitted, the T0-T14 troubleshooting SOP")
    sop.add_argument("--attest", metavar="STEP",
                     help="The step to attest: Tn for troubleshooting, else the named SOP's step id")
    sop.add_argument("--result", default="")
    sop.add_argument("--session")
    _evidence(sop)
    sop.set_defaults(handler=cmd_sop)

    hypothesis = sub.add_parser(
        "hypothesis", help="Competing hypotheses, each with a kill experiment a fix must survive")
    hypothesis_sub = hypothesis.add_subparsers(dest="hypothesis_command", required=True)
    hypothesis_add = hypothesis_sub.add_parser("add", help="Record an open hypothesis")
    hypothesis_add.add_argument("--cause", required=True, help="The mechanism it proposes")
    hypothesis_add.add_argument("--kills", required=True, metavar="CMD",
                                help="The check the hypothesis predicts will pass; a non-zero "
                                     "exit fires the kill (argv, no shell)")
    hypothesis_add.add_argument("--confirms", action="append", default=[], metavar="CITE",
                                help="Evidence for it; repeatable")
    hypothesis_add.add_argument("--next", dest="next_experiment", default=None,
                                help="The next experiment that would discriminate it")
    hypothesis_add.add_argument("--subject", default=None)
    hypothesis_kill = hypothesis_sub.add_parser(
        "kill", help="Run the kill experiment and record whether it ran and fired")
    hypothesis_kill.add_argument("sequence", type=int)
    hypothesis_kill.add_argument("--timeout", type=int, default=900)
    hypothesis_kill.add_argument("--session")
    hypothesis_sub.add_parser("status", help="Every hypothesis at its current state")
    hypothesis.set_defaults(handler=cmd_hypothesis)

    index_parser = sub.add_parser("index", help="Derived SQLite index over corpus, charter, and archive")
    index_sub = index_parser.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("rebuild").set_defaults(handler=cmd_index)
    index_sub.add_parser("status").set_defaults(handler=cmd_index)
    index_q = index_sub.add_parser("query")
    index_q.add_argument("--task", required=True)
    index_q.add_argument("--limit", type=int, default=10)
    index_q.add_argument("--allow-stale", action="store_true")
    index_q.set_defaults(handler=cmd_index)
    index_sub.add_parser(
        "patterns",
        help="One row per pattern subject, folded to its latest record "
             "(occurrences, workaround, class) - `history --kind pattern` "
             "is the unfolded evolution log",
    ).set_defaults(handler=cmd_index)

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
    parity.add_argument("--reference", default=None,
                        help="Required unless --sources is given")
    parity.add_argument("--matrix", action="store_true",
                        help="Full eleven-dimension decision matrix instead of category gaps")
    parity.add_argument("--archive", action="store_true",
                        help="Apply the recorded-invariant adoption floor (E-14) to the matrix")
    # I-2: per-source files-opened and a surface-only flag, off recorded read
    # receipts - stands alone, no --reference comparison involved.
    parity.add_argument("--sources", action="store_true",
                        help="Report files-opened and surface-only per source from read receipts")
    parity.set_defaults(handler=cmd_parity)

    netgate = sub.add_parser("netgate", help="Prove the CLI surfaces make zero network connections")
    netgate.set_defaults(handler=cmd_netgate)

    evals = sub.add_parser("evals", help="Execute the authored skill evals: routing accuracy plus snapshot diff")
    evals.add_argument("--write-snapshots", action="store_true",
                       help="Accept current routing outcomes as the new baseline fixtures")
    evals_mode = evals.add_mutually_exclusive_group()
    evals_mode.add_argument("--ratchet", action="store_true",
                       help="Compare per-skill routing scores against the committed baseline; fail on any regression")
    evals_mode.add_argument("--write-baseline", action="store_true",
                       help="Raise the committed routing-score baseline to the current scores (refused on any regression)")
    evals_mode.add_argument("--determinism", action="store_true",
                       help="Run the offline routing harness twice and name any case whose route differs")
    evals.add_argument("--withhold-memory", action="store_true",
                       help="Score with this project's lessons and compiled law withheld from the subject brief, "
                            "so the number measures the skill rather than the memory; the baseline keeps a "
                            "separate block per mode and the two are never compared")
    evals.set_defaults(handler=cmd_evals)

    grid = sub.add_parser("grid", help="Attack every enforcement control; report each cell's observed result")
    grid.set_defaults(handler=cmd_grid)

    absorb = sub.add_parser("absorb", help="Check whether a synced file is truly absorbed (reader + guard)")
    absorb.add_argument("--path", required=True)
    absorb.set_defaults(handler=cmd_absorb)

    read_cmd = sub.add_parser(
        "read", help="Record a read receipt: what was opened, and a digest of the slice")
    read_cmd.add_argument("--source", required=True,
                          help="Operator-chosen name for the source read (e.g. a vendor or component name)")
    read_cmd.add_argument("--path", required=True,
                          help="Path opened, relative to the project or to --root")
    read_cmd.add_argument("--root", default=None,
                          help="Directory the source lives in; required to read a path outside the project")
    read_cmd.add_argument("--lines", default=None,
                          help="Line range actually read, as 'a-b' (1-based, inclusive)")
    read_cmd.set_defaults(handler=cmd_read)

    skill = sub.add_parser("skill", help="Validate or forge a project skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_sub.add_parser(
        "lifecycle", help="List each skill's lifecycle state"
    ).set_defaults(handler=cmd_skill_lifecycle)
    skill_retire = skill_sub.add_parser("retire", help="Deprecate a skill with a recorded reason")
    skill_retire.add_argument("--name", required=True)
    skill_retire.add_argument("--reason", required=True)
    _operator_flags(skill_retire)
    skill_retire.set_defaults(handler=cmd_skill_retire)
    skill_validate = skill_sub.add_parser("validate")
    skill_validate.add_argument("--path", required=True)
    skill_validate.set_defaults(handler=cmd_skill_validate)
    skill_names = skill_sub.add_parser(
        "names", help="Project-wide skill-name collision check - the host "
                      "resolves a collision silently, keeping one twin")
    skill_names.add_argument("--root", default="skills",
                             help="Skills directory (default: skills)")
    skill_names.set_defaults(handler=cmd_skill_names)
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
    skill_forge.add_argument(
        "--success-evidence", action="append", default=[],
        help="NS-11d: cite a real archive record proving one recorded success "
             "of the task type this skill covers (`seq:<n>`, from `godmode "
             "history`); at least three, and refused unless they are three "
             "DISTINCT sequences that each name a record that exists. That "
             "the records are successes of this task type is your judgement "
             "- no record shape here carries a task type to check it against")
    skill_forge.add_argument("--positive", action="append", default=[])
    skill_forge.add_argument("--negative", action="append", default=[])
    skill_forge.add_argument("--assertion", action="append", default=[])
    skill_forge.add_argument(
        "--pattern", dest="pattern", action="append", type=int, default=[],
        help="A pattern record's own sequence this skill_impact cites; repeatable")
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
            except (OSError, ValueError):  # pragma: no cover - exotic stream  # godmode: swallow-ok: pragma: no cover - exotic stream
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
