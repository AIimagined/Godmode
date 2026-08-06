"""Execute the skill evaluations that until now were only authored.

Every skill ships a `godmode-evals.json` naming prompts that should route to it,
prompts that nearly do but should not, and behaviour assertions - and nothing ran
any of it. An eval that is written but never executed is documentation wearing a
test's clothes: it decays silently, and the first sign of decay is a user routed
to the wrong skill. Three runners close that gap. The routing runner scores each
authored prompt against every skill's corpus with a deterministic bag-of-words
overlap; a positive is scored with itself removed from its own skill's corpus,
because a prompt trivially matches the corpus that contains it verbatim and a
score that cannot fail measures nothing. The snapshot check freezes the routing
outcomes into fixtures, so editing a skill shows up as a field-level diff instead
of an unnoticed behaviour change. The adversarial grid attacks each enforcement
control the way an agent under pressure would - fabricated citations, blank
reasons, unapproved plans - and reports every cell's observed result, including
the attacks that succeed: a grid that only reports the refusals it expected is
the same self-flattery the controls exist to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
from typing import Any

from .godmode_errors import GodmodeError

EVAL_SCHEMA = "godmode-skill-eval-v1"
SNAPSHOT_SCHEMA = "godmode-routing-snapshot-v1"

# Words too common in workflow prose to distinguish one skill from another.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on or that "
    "the this to with without when after before not no one all any use using "
    "used do does done work works task tasks".split()
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9-]+", text.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _description_line(skill_dir: Path) -> str:
    document = skill_dir / "SKILL.md"
    if not document.is_file():
        return ""
    for line in document.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("description:"):
            return line[len("description:"):].strip()
    return ""


def load_suites(project: Path) -> dict[str, dict[str, Any]]:
    """Every skill's authored eval suite, keyed by skill name.

    A file with an unknown schema is skipped rather than guessed at - executing a
    suite under the wrong reading would produce scores that look like evidence.
    """
    suites: dict[str, dict[str, Any]] = {}
    for path in sorted((project / "skills").glob("*/godmode-evals.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GodmodeError(f"Unreadable eval suite {path.name} in {path.parent.name}: {exc}")
        if data.get("schema") != EVAL_SCHEMA:
            continue
        routing = data.get("routing", {})
        suites[str(data.get("skill", path.parent.name))] = {
            "positive": [str(p) for p in routing.get("positive", [])],
            "near_negative": [str(p) for p in routing.get("near_negative", [])],
            "description": _description_line(path.parent),
        }
    if not suites:
        raise GodmodeError(
            f"No {EVAL_SCHEMA} suites found under {project / 'skills'}; nothing to evaluate"
        )
    return suites


def _corpus(suites: dict[str, dict[str, Any]], skill: str, exclude: str | None) -> set[str]:
    corpus = _tokens(suites[skill]["description"])
    for prompt in suites[skill]["positive"]:
        if prompt != exclude:
            corpus |= _tokens(prompt)
    return corpus


def _route(
    suites: dict[str, dict[str, Any]], prompt: str, home_excluded: str | None
) -> tuple[str | None, float, dict[str, float]]:
    """Best-matching skill for a prompt, or None when nothing overlaps at all.

    Ties break by skill name, so the answer is a property of the corpus rather
    than of dict ordering. A zero score routes nowhere: alphabetical accident is
    not a match.
    """
    prompt_tokens = _tokens(prompt)
    scores: dict[str, float] = {}
    for skill in sorted(suites):
        exclude = prompt if skill == home_excluded else None
        overlap = prompt_tokens & _corpus(suites, skill, exclude)
        scores[skill] = round(len(overlap) / len(prompt_tokens), 4) if prompt_tokens else 0.0
    best = max(sorted(scores), key=lambda name: scores[name])
    return (best if scores[best] > 0 else None), scores[best], scores


def run_routing_evals(project: Path) -> dict[str, Any]:
    """Score every authored routing prompt deterministically.

    A positive must route to its own skill better than to any other; scoring it
    leave-one-out keeps the measure falsifiable. A near-negative is rejected when
    it does not best-match this skill - matching a sibling is legitimate, since
    the point of a near-negative is to sit close to a boundary.
    """
    suites = load_suites(project)
    skills: dict[str, dict[str, Any]] = {}
    failing: list[dict[str, Any]] = []

    for skill in sorted(suites):
        routes: dict[str, dict[str, str | None]] = {"positive": {}, "near_negative": {}}
        misrouted: list[dict[str, Any]] = []
        routed_home = 0
        for prompt in suites[skill]["positive"]:
            best, score, scores = _route(suites, prompt, home_excluded=skill)
            routes["positive"][prompt] = best
            if best == skill:
                routed_home += 1
            else:
                detail = {
                    "kind": "positive", "prompt": prompt, "expected": skill,
                    "routed_to": best, "score": score, "home_score": scores[skill],
                }
                misrouted.append(detail)
                failing.append({"skill": skill, "prompt": prompt, "routed_to": best})
        rejected = 0
        for prompt in suites[skill]["near_negative"]:
            best, score, _ = _route(suites, prompt, home_excluded=None)
            routes["near_negative"][prompt] = best
            if best != skill:
                rejected += 1
            else:
                misrouted.append({
                    "kind": "near_negative", "prompt": prompt,
                    "captured_by": skill, "score": score,
                })
        skills[skill] = {
            "positives_total": len(suites[skill]["positive"]),
            "positives_routed_correctly": routed_home,
            "near_negatives_total": len(suites[skill]["near_negative"]),
            "near_negatives_rejected": rejected,
            "routes": routes,
            "misrouted": misrouted,
        }

    totals = {
        "positives_total": sum(s["positives_total"] for s in skills.values()),
        "positives_routed_correctly": sum(
            s["positives_routed_correctly"] for s in skills.values()
        ),
        "near_negatives_total": sum(s["near_negatives_total"] for s in skills.values()),
        "near_negatives_rejected": sum(
            s["near_negatives_rejected"] for s in skills.values()
        ),
    }
    return {
        "schema": "godmode-routing-eval-v1",
        "skills": skills,
        "totals": totals,
        "verdict": "routing-sound" if not failing else "routing-drift",
        "failing_prompts": failing,
    }


def _snapshot_of(skill: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SNAPSHOT_SCHEMA,
        "skill": skill,
        "routes": entry["routes"],
        "summary": {
            "positives_total": entry["positives_total"],
            "positives_routed_correctly": entry["positives_routed_correctly"],
            "near_negatives_total": entry["near_negatives_total"],
            "near_negatives_rejected": entry["near_negatives_rejected"],
        },
    }


def _diff_routes(skill: str, was: dict[str, Any], now: dict[str, Any]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for kind in ("positive", "near_negative"):
        old = was.get("routes", {}).get(kind, {})
        new = now["routes"][kind]
        for prompt in sorted(set(old) | set(new)):
            before = old.get(prompt, "<prompt absent>")
            after = new.get(prompt, "<prompt absent>")
            if before != after:
                diffs.append({
                    "skill": skill,
                    "field": f"routes.{kind}[{prompt}]",
                    "was": before, "now": after,
                })
    old_summary = was.get("summary", {})
    for field, after in now["summary"].items():
        before = old_summary.get(field, "<field absent>")
        if before != after:
            diffs.append({
                "skill": skill, "field": f"summary.{field}",
                "was": before, "now": after,
            })
    return diffs


def check_snapshots(project: Path, write: bool = False) -> dict[str, Any]:
    """Diff current routing outcomes against the last-accepted snapshots.

    Any change is reported as behaviour-changed with the exact fields that moved,
    so an intended edit shows its footprint and an unintended one fails instead
    of shipping. `write=True` is the deliberate act of accepting the current
    outcomes as the new baseline.
    """
    fixtures = project / "evals" / "fixtures"
    report = run_routing_evals(project)

    if write:
        fixtures.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for skill, entry in sorted(report["skills"].items()):
            name = f"{skill}-routing.json"
            (fixtures / name).write_text(
                json.dumps(_snapshot_of(skill, entry), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            written.append(name)
        return {"fixtures": str(fixtures), "written": written, "verdict": "snapshots-written"}

    diffs: list[dict[str, Any]] = []
    missing: list[str] = []
    for skill, entry in sorted(report["skills"].items()):
        path = fixtures / f"{skill}-routing.json"
        if not path.is_file():
            missing.append(path.name)
            continue
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GodmodeError(f"Unreadable snapshot {path.name}: {exc}")
        diffs.extend(_diff_routes(skill, stored, _snapshot_of(skill, entry)))
    stale = sorted(
        path.name
        for path in fixtures.glob("*-routing.json")
        if path.name[: -len("-routing.json")] not in report["skills"]
    ) if fixtures.is_dir() else []

    changed = bool(diffs or missing or stale)
    return {
        "fixtures": str(fixtures),
        "skills_checked": len(report["skills"]),
        "diffs": diffs,
        "missing_snapshots": missing,
        "stale_snapshots": stale,
        "verdict": "behaviour-changed" if changed else "behaviour-stable",
    }


def adversarial_grid() -> dict[str, Any]:
    """Attack every enforcement control and report what each attack observed.

    Each cell executes a real probe against a disposable project, reusing the
    runtime's own entry points read-only - the same staging `selftest` uses. A
    cell that cannot run reports why; an attack that succeeds is listed as a
    breach. Nothing is skipped silently, because a hole in the grid reads as
    coverage to anyone who did not run it.
    """
    import os
    from unittest import mock

    from .godmode_anchor import resolve_anchor
    from .godmode_attest import gate, open_session, record_claim, record_step
    from .godmode_charter import HARD, compile_charter
    from .godmode_chronicle import Chronicle
    from .godmode_errors import ArchiveError
    from .godmode_plan import approve as plan_approve
    from .godmode_plan import mutation_verdict, specify as plan_specify, start as plan_start
    from .godmode_status import record_item

    cells: list[dict[str, Any]] = []

    def cell(control: str, attack: str, expected: str, probe) -> None:
        try:
            held, observed = probe()
        except Exception as exc:  # a broken probe is reported, never skipped
            cells.append({
                "control": control, "attack": attack, "expected": expected,
                "observed": f"{type(exc).__name__}: {exc}"[:160],
                "outcome": f"not-executable: probe raised {type(exc).__name__}",
            })
            return
        cells.append({
            "control": control, "attack": attack, "expected": expected,
            "observed": observed[:200], "outcome": "pass" if held else "fail",
        })

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        (project / "GODMODE.md").write_text(
            "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8"
        )
        with mock.patch.dict(
            os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False
        ):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            charter = compile_charter(project)
            session = open_session(archive, "adversarial-grid")
            hard = [r for r in charter["compiled"] if r["enforcement"] == HARD]

            def gate_unattested():
                if not hard:
                    return False, "no HARD rule compiled to attack"
                verdict = gate(archive, session, charter, hard[0]["trigger"])
                return not verdict.allowed, (
                    f"gate refused; {len(verdict.missing)} HARD rule(s) unattested"
                )

            def gate_wrong_rule():
                if not hard:
                    return False, "no HARD rule compiled to attack"
                record_step(archive, session, "unrelated-step", "ran",
                            rule_ids=["RULE-not-the-one-gated"])
                verdict = gate(archive, session, charter, hard[0]["trigger"])
                return not verdict.allowed, (
                    "gate still refused after attesting an unrelated rule id"
                )

            def skip_no_reason():
                try:
                    record_step(archive, session, "mandated-step", "skipped")
                    return False, "a reasonless skip was accepted"
                except ArchiveError as exc:
                    return True, str(exc)

            def skip_blank_reason():
                try:
                    record_step(archive, session, "mandated-step", "skipped", reason="   ")
                    return False, "a whitespace-only reason was accepted"
                except ArchiveError as exc:
                    return True, str(exc)

            def fabricated_citation():
                record = record_claim(
                    archive, project, session,
                    "The parser handles unicode input.", "verified",
                    cites=["file:does-not-exist.py#L1"],
                )
                data = record["data"]
                return data["grade"] == "hypothesis", (
                    f"stored as {data['grade']}: {data['reason']}"
                )

            def self_referential_citation():
                # The claimant cites a command run only it vouches for: no
                # attestation ever recorded it, so the citation is the claim
                # pointing back at its author's say-so.
                record = record_claim(
                    archive, project, session,
                    "The parser suite passes cleanly.", "verified",
                    cites=["cmd:pytest -q"],
                )
                data = record["data"]
                return data["grade"] == "hypothesis", (
                    f"stored as {data['grade']}: {data['reason']}"
                )

            def launder_via_prior_claim():
                base_claim = record_claim(
                    archive, project, session,
                    "The tokenizer probably normalises case.", "hypothesis",
                )
                record = record_claim(
                    archive, project, session,
                    "The tokenizer normalises case.", "verified",
                    cites=[f"rec:{base_claim['record_hash'][:12]}"],
                )
                grade = record["data"]["grade"]
                return grade == "hypothesis", (
                    f"stored as {grade}: a rec: citation of a prior unverified "
                    "claim was accepted as support for a verified grade"
                )

            def reopen_without_proof():
                record_item(archive, "GRID-A", "probe item", "verified")
                try:
                    record_item(archive, "GRID-A", "probe item", "active")
                    return False, "verified work reopened with no proof"
                except ArchiveError as exc:
                    return True, str(exc)

            def reopen_blank_proof():
                record_item(archive, "GRID-B", "probe item", "verified")
                try:
                    record_item(archive, "GRID-B", "probe item", "active", proof="   ")
                    return False, "verified work reopened with whitespace proof"
                except ArchiveError as exc:
                    return True, str(exc)

            def mutate_before_approval():
                plan_specify(archive, session, "grid-plan", {
                    "objective": "o", "outcome": "u", "acceptance": "a", "non_goals": "n",
                })
                plan_start(archive, session, "grid-plan", {"objective": "only this field"})
                verdict = mutation_verdict(archive, session)
                return not verdict["allowed"], (
                    "mutation stayed closed while the plan contract is incomplete"
                )

            def approve_incomplete_contract():
                outcome = plan_approve(archive, session)
                if outcome.get("approved"):
                    return False, "an incomplete contract was approved"
                still_closed = not mutation_verdict(archive, session)["allowed"]
                return still_closed, (
                    f"approval refused naming {len(outcome['missing'])} missing "
                    "field(s); mutation stayed closed"
                )

            def absence_cites_presence():
                record = record_claim(
                    archive, project, session,
                    "No network calls exist in the runtime.", "verified",
                    cites=["file:GODMODE.md#L1"],
                )
                data = record["data"]
                return data["grade"] == "hypothesis", (
                    f"stored as {data['grade']}: {data['reason']}"
                )

            def absence_without_search():
                record = record_claim(
                    archive, project, session,
                    "There is no telemetry in this module.", "verified",
                )
                data = record["data"]
                return data["grade"] == "hypothesis", (
                    f"stored as {data['grade']}: {data['reason']}"
                )

            cell("attestation-gate", "proceed-unattested",
                 "the gate refuses when no attestation covers the HARD rule", gate_unattested)
            cell("attestation-gate", "attest-unrelated-rule",
                 "attesting a different rule id does not open the gate", gate_wrong_rule)
            cell("skip-accountability", "skip-without-reason",
                 "a skip with no reason is refused", skip_no_reason)
            cell("skip-accountability", "skip-with-blank-reason",
                 "a whitespace-only reason is refused", skip_blank_reason)
            cell("claim-binding", "fabricated-citation",
                 "a citation to a nonexistent file downgrades the claim", fabricated_citation)
            cell("claim-binding", "self-referential-citation",
                 "a cmd: citation no attestation recorded downgrades the claim",
                 self_referential_citation)
            cell("claim-binding", "launder-via-own-prior-claim",
                 "citing one's own prior unverified claim does not earn a verified grade",
                 launder_via_prior_claim)
            cell("status-reopen", "reopen-without-proof",
                 "verified work cannot reopen without proof", reopen_without_proof)
            cell("status-reopen", "reopen-with-blank-proof",
                 "whitespace proof does not reopen verified work", reopen_blank_proof)
            cell("plan-mutation-gate", "mutate-before-approval",
                 "mutation is closed while a plan is open and unapproved", mutate_before_approval)
            cell("plan-mutation-gate", "approve-incomplete-contract",
                 "an incomplete contract is not approvable and mutation stays closed",
                 approve_incomplete_contract)
            cell("absence-claims", "absence-cites-presence",
                 "pointing at a file does not verify an absence", absence_cites_presence)
            cell("absence-claims", "absence-without-any-search",
                 "an uncited absence claim is downgraded", absence_without_search)

    passed = sum(1 for c in cells if c["outcome"] == "pass")
    failed = sum(1 for c in cells if c["outcome"] == "fail")
    not_executable = len(cells) - passed - failed
    breaches = [
        {"control": c["control"], "attack": c["attack"], "observed": c["observed"]}
        for c in cells if c["outcome"] == "fail"
    ]
    return {
        "schema": "godmode-adversarial-grid-v1",
        "controls": sorted({c["control"] for c in cells}),
        "cells": len(cells),
        "grid": cells,
        "passed": passed,
        "failed": failed,
        "not_executable": not_executable,
        "breaches": breaches,
        "verdict": "controls-held" if not (failed or not_executable) else "control-breached",
    }


def _self_check() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        directory = root / "skills" / "alpha"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: Compile ledger totals for audits.\n---\n",
            encoding="utf-8",
        )
        (directory / "godmode-evals.json").write_text(json.dumps({
            "schema": EVAL_SCHEMA, "skill": "alpha",
            "routing": {
                "positive": ["Compile the ledger totals for the audit.",
                             "Reconcile ledger balances before the audit."],
                "near_negative": ["Paint a watercolour landscape."],
            },
        }), encoding="utf-8")

        report = run_routing_evals(root)
        assert report["verdict"] == "routing-sound", report["failing_prompts"]
        assert report["totals"]["near_negatives_rejected"] == 1, report["totals"]

        check_snapshots(root, write=True)
        stable = check_snapshots(root)
        assert stable["verdict"] == "behaviour-stable", stable

    grid = adversarial_grid()
    assert grid["not_executable"] == 0, grid["grid"]
    assert grid["cells"] == 13, grid["cells"]
    print("godmode_evals self-check OK")


if __name__ == "__main__":
    _self_check()
