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

Behaviour assertions get the same treatment as routing: an assertion may carry a
`check` - an argv string plus expectations on exit code and output - and then it
runs, for real, against this project. A bare string stays legal and is reported
declared-only, because pretending an unexecutable sentence passed would be the
exact dishonesty the runner exists to remove; the counts make the gap visible
instead. Two further snapshot families extend the routing idiom to the other
behaviours that can drift silently: the charter snapshot freezes every compiled
rule (id, trigger, enforcement, verify, and a hash of its text, so a wording
edit is visible without duplicating the prose into a second file), and the
ranking snapshot freezes which segments the context brief selects, in order, for
a fixed set of tasks - the spec's own test for whether retrieval still behaves.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any

from . import godmode_graders
from .godmode_errors import GodmodeError

EVAL_SCHEMA = "godmode-skill-eval-v1"
SNAPSHOT_SCHEMA = "godmode-routing-snapshot-v1"
ASSERTION_SCHEMA = "godmode-behavior-assertions-v1"
CHARTER_SNAPSHOT_SCHEMA = "godmode-charter-snapshot-v1"
RANKING_SNAPSHOT_SCHEMA = "godmode-ranking-snapshot-v1"
COMPARISON_SCHEMA = "godmode-eval-comparison-v1"

# One probe may not hang the whole eval run; a minute is generous for a local CLI.
ASSERTION_TIMEOUT_SECONDS = 60

# The fixed task set the ranking snapshot is taken over. Fixed on purpose: a
# snapshot over varying tasks measures the tasks, not the ranking. Three tasks
# with distinct vocabularies exercise different regions of the corpus.
RANKING_TASKS = (
    "fix a failing test without breaking the guard suite",
    "prepare a release: changelog, version surfaces, and docs",
    "investigate a regression in context continuity after a branch switch",
)
RANKING_BUDGET = 1200

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
            "behavior_assertions": list(data.get("behavior_assertions", [])),
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


def _run_check(project: Path, check: dict[str, Any]) -> tuple[bool, str]:
    """Execute one assertion's declared probe and say what was observed.

    The command is an argv string, split with shlex and run without a shell:
    a probe that needs shell features is a probe whose behaviour differs per
    machine, which is the opposite of an eval. `python` maps to the interpreter
    running the evals, because the probe must test this runtime, not whichever
    binary PATH happens to resolve today.

    A check may name a `grader` from the closed vocabulary in
    `godmode_graders` instead of (or in addition to considering) a bare
    substring: `{"grader": "json_match", "expected": "..."}`. `match` accepts
    an optional `prefix: true`. An unknown grader name is a definition error,
    reported rather than silently treated as a pass or a fail.
    """
    command = str(check.get("command", "")).strip()
    if not command:
        return False, "check declares no command"
    argv = shlex.split(command)
    if argv[0] == "python":
        argv[0] = sys.executable
    try:
        proc = subprocess.run(
            argv, cwd=str(project), capture_output=True, text=True,
            timeout=ASSERTION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"probe did not run: {type(exc).__name__}: {exc}"[:200]
    output = (proc.stdout or "") + (proc.stderr or "")
    expected_exit = int(check.get("expect_exit", 0))
    if proc.returncode != expected_exit:
        return False, (
            f"exit {proc.returncode}, expected {expected_exit}; output: "
            f"{output.strip()[:160]}"
        )
    grader_name = check.get("grader")
    if grader_name is not None:
        expected = check.get("expected", "")
        kwargs: dict[str, Any] = {}
        if "prefix" in check:
            kwargs["prefix"] = bool(check["prefix"])
        try:
            held = godmode_graders.grade(str(grader_name), output, expected, **kwargs)
        except GodmodeError as exc:
            return False, f"grader definition error: {exc}"
        if not held:
            return False, (
                f"grader {grader_name!r} did not match; output: {output.strip()[:160]}"
            )
        return True, f"exit {proc.returncode}, grader {grader_name!r} matched"
    needle = check.get("expect_contains")
    if needle is not None and str(needle) not in output:
        return False, f"output lacks {str(needle)!r}; output: {output.strip()[:160]}"
    observed = f"exit {proc.returncode}"
    if needle is not None:
        observed += f", output contains {str(needle)!r}"
    return True, observed


def run_behavior_assertions(project: Path) -> dict[str, Any]:
    """Run every executable behaviour assertion; count the rest honestly.

    An assertion object carrying a `check` is executed for real - its command
    runs from the project root and its exit code and output are held against the
    declared expectations. A bare string cannot be executed, so it is reported
    declared-only rather than imagined as passing: the per-skill counts keep the
    gap between promised and proven behaviour in plain sight, which is the whole
    reason to run assertions instead of admiring them.
    """
    suites = load_suites(project)
    skills: dict[str, dict[str, Any]] = {}
    totals = {"executable": 0, "passed": 0, "failed": 0, "declared_only": 0}

    for skill in sorted(suites):
        assertions: list[dict[str, Any]] = []
        passed = failed = declared_only = 0
        for entry in suites[skill]["behavior_assertions"]:
            if isinstance(entry, dict) and entry.get("check"):
                check = entry["check"]
                held, observed = _run_check(project, check)
                if held:
                    passed += 1
                else:
                    failed += 1
                assertions.append({
                    "assert": str(entry.get("assert", "")).strip(),
                    "mode": "executable",
                    "command": str(check.get("command", "")),
                    "observed": observed,
                    "outcome": "pass" if held else "fail",
                })
            else:
                declared_only += 1
                text = entry if isinstance(entry, str) else str(entry.get("assert", ""))
                assertions.append({
                    "assert": text.strip(),
                    "mode": "declared-only",
                    "outcome": "not-run",
                })
        skills[skill] = {
            "assertions": assertions,
            "executable": passed + failed,
            "passed": passed,
            "failed": failed,
            "declared_only": declared_only,
        }
        totals["executable"] += passed + failed
        totals["passed"] += passed
        totals["failed"] += failed
        totals["declared_only"] += declared_only

    return {
        "schema": ASSERTION_SCHEMA,
        "skills": skills,
        "totals": totals,
        "verdict": "assertions-held" if totals["failed"] == 0 else "assertion-failed",
    }


def compare_eval_results(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two result records that each carry an `id` (U-S1).

    A result's `id` is `name.local.vN` (see `godmode_scenarios.scenario_id`):
    the version is part of what identifies the eval, not a label alongside
    it. Two records with different ids are describing different eval
    definitions - a different digest, a different version, or an unrelated
    eval entirely - so any "score went up/down" claim across them would be
    comparing different things and calling it drift. The comparison is
    refused outright rather than computed and hoped nobody notices; two
    records that share an id are compared field-by-field so the delta names
    exactly what moved.
    """
    id_before, id_after = before.get("id"), after.get("id")
    if id_before != id_after:
        return {
            "schema": COMPARISON_SCHEMA,
            "comparable": False,
            "verdict": "refused",
            "reason": "scores are comparable only within an id",
            "ids": [id_before, id_after],
        }
    changed = {
        key: {"was": before.get(key), "now": after.get(key)}
        for key in sorted(set(before) | set(after))
        if key != "id" and before.get(key) != after.get(key)
    }
    return {
        "schema": COMPARISON_SCHEMA,
        "comparable": True,
        "id": id_before,
        "verdict": "compared",
        "changed": changed,
    }


def _charter_view(project: Path) -> dict[str, Any]:
    """The compiled rule set, serialized for snapshotting.

    Each rule keeps its enforcement-bearing fields plus a hash of its text: the
    hash makes a wording edit visible without copying the prose into a second
    file that would then drift from the first.
    """
    from .godmode_charter import compile_charter

    charter = compile_charter(project)
    rules = {
        rule["id"]: {
            "trigger": rule["trigger"],
            "enforcement": rule["enforcement"],
            "verify": rule["verify"],
            "text_hash": hashlib.sha256(
                rule["text"].encode("utf-8")).hexdigest()[:16],
        }
        for rule in charter["compiled"]
    }
    return {
        "schema": CHARTER_SNAPSHOT_SCHEMA,
        "rules": rules,
        "summary": {"rules": charter["rules"], "enforcement": charter["enforcement"]},
    }


def charter_snapshot(project: Path, write: bool = False) -> dict[str, Any]:
    """Diff the compiled charter against its last-accepted snapshot.

    Editing a prose rule must show up as a diff (K-13): a reworded rule compiles
    to a new id, so it reports as one rule removed and one added; a rule whose
    text survived but now classifies differently - a compiler change - reports
    field-level, the same way routing snapshots do. `write=True` accepts the
    current rule set as the new baseline.
    """
    fixture = project / "evals" / "fixtures" / "charter-rules.json"
    current = _charter_view(project)

    if write:
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"fixture": str(fixture), "rules": len(current["rules"]),
                "verdict": "snapshot-written"}

    if not fixture.is_file():
        return {"fixture": str(fixture), "missing_snapshot": True,
                "added": sorted(current["rules"]), "removed": [], "changed": [],
                "verdict": "charter-changed"}
    try:
        stored = json.loads(fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GodmodeError(f"Unreadable snapshot {fixture.name}: {exc}")

    old, new = stored.get("rules", {}), current["rules"]
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed: list[dict[str, Any]] = []
    for rule_id in sorted(set(old) & set(new)):
        for field, after in new[rule_id].items():
            before = old[rule_id].get(field, "<field absent>")
            if before != after:
                changed.append({"rule": rule_id, "field": field,
                                "was": before, "now": after})
    old_summary = stored.get("summary", {})
    for field, after in current["summary"].items():
        before = old_summary.get(field, "<field absent>")
        if before != after:
            changed.append({"rule": "<summary>", "field": field,
                            "was": before, "now": after})

    stable = not (added or removed or changed)
    return {
        "fixture": str(fixture),
        "missing_snapshot": False,
        "rules_checked": len(new),
        "added": added,
        "removed": removed,
        "changed": changed,
        "verdict": "charter-stable" if stable else "charter-changed",
    }


def _ranking_view(project: Path) -> dict[str, Any]:
    """The ordered segment selection the brief makes for each fixed task."""
    from .godmode_corpus import build_brief

    tasks: dict[str, list[list[Any]]] = {}
    scorer = None
    for task in RANKING_TASKS:
        brief = build_brief(project, task, RANKING_BUDGET)
        scorer = brief["scorer"]
        tasks[task] = [
            [entry["path"], entry["lines"][0]] for entry in brief["context"]
        ]
    return {
        "schema": RANKING_SNAPSHOT_SCHEMA,
        "scorer": scorer,
        "budget": RANKING_BUDGET,
        "tasks": tasks,
    }


def ranking_snapshot(project: Path, write: bool = False) -> dict[str, Any]:
    """Diff the brief's ranking for the fixed task set against its snapshot.

    The spec's own acceptance for retrieval is "snapshot the ranking for a fixed
    task set": what is recorded is exactly what a model would be given - which
    segments, in which order - so a corpus or scorer change that silently
    reshuffles context fails here instead of surfacing as a confused agent. The
    scorer name is part of the snapshot because fts5 and the fallback are
    different rankers, and pretending their outputs are interchangeable would
    hide exactly the drift this exists to catch.
    """
    fixture = project / "evals" / "fixtures" / "ranking.json"
    current = _ranking_view(project)

    if write:
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"fixture": str(fixture), "tasks": len(RANKING_TASKS),
                "verdict": "snapshot-written"}

    if not fixture.is_file():
        return {"fixture": str(fixture), "missing_snapshot": True, "diffs": [],
                "verdict": "ranking-changed"}
    try:
        stored = json.loads(fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GodmodeError(f"Unreadable snapshot {fixture.name}: {exc}")

    diffs: list[dict[str, Any]] = []
    for field in ("scorer", "budget"):
        before = stored.get(field, "<field absent>")
        if before != current[field]:
            diffs.append({"field": field, "was": before, "now": current[field]})
    old_tasks = stored.get("tasks", {})
    for task in sorted(set(old_tasks) | set(current["tasks"])):
        before = old_tasks.get(task, "<task absent>")
        after = current["tasks"].get(task, "<task absent>")
        if before != after:
            diffs.append({"field": f"tasks[{task}]", "was": before, "now": after})

    return {
        "fixture": str(fixture),
        "missing_snapshot": False,
        "tasks_checked": len(current["tasks"]),
        "diffs": diffs,
        "verdict": "ranking-stable" if not diffs else "ranking-changed",
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

    # U-S1: grader vocabulary is reachable from a behaviour-assertion check,
    # and two result records compare only when their ids agree.
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        gamma = root / "skills" / "gamma"
        gamma.mkdir(parents=True)
        (gamma / "SKILL.md").write_text(
            "---\nname: gamma\ndescription: Probe grader wiring.\n---\n", encoding="utf-8")
        (gamma / "godmode-evals.json").write_text(json.dumps({
            "schema": EVAL_SCHEMA, "skill": "gamma",
            "routing": {"positive": [], "near_negative": []},
            "behavior_assertions": [
                {"assert": "the grader vocabulary matches a prefixed exit",
                 "check": {"command": "python -c \"print('gm1.ok')\"",
                           "grader": "match", "expected": "gm1.", "prefix": True}},
            ],
        }), encoding="utf-8")
        graded = run_behavior_assertions(root)
        assert graded["verdict"] == "assertions-held", graded
        assert graded["skills"]["gamma"]["passed"] == 1, graded

    same = compare_eval_results(
        {"id": "hollow-guard.local.v1", "caught": True},
        {"id": "hollow-guard.local.v1", "caught": False},
    )
    assert same["verdict"] == "compared" and same["changed"], same

    different = compare_eval_results(
        {"id": "hollow-guard.local.v1", "caught": True},
        {"id": "hollow-guard.local.v2", "caught": True},
    )
    assert different["verdict"] == "refused", different
    assert different["reason"] == "scores are comparable only within an id", different

    print("godmode_evals self-check OK")


if __name__ == "__main__":
    _self_check()
