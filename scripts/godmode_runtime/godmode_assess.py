"""Grade a project's own governability, and prove what this host can enforce.

Two questions, both answered with measurements rather than opinion:

* `assess` — can an agent actually comply with this project's rules? A rulebook
  larger than the context an agent will spend reading it is not followed, it is
  sampled, and the sampling heuristic belongs to the model rather than the project.
  That is why the same guidance produces different behaviour on different models.
* `selftest` — is Godmode enforcing anything here, or merely present? Every control
  is exercised against a disposable project and reported with its observed result,
  never with a claim.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from .godmode_atlas import build as build_atlas
from .godmode_charter import ADVISORY, HARD, SOFT, compile_charter
from .godmode_corpus import resolve_roles, segment_document
from .godmode_errors import GodmodeError
from .godmode_status import authority_claims

# What an agent will realistically spend reading rules before starting work.
TYPICAL_COLD_START_TOKENS = 2_500


def _finding(severity: str, code: str, detail: str, remedy: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "detail": detail, "remedy": remedy}


def assess(project: Path, budget: int = TYPICAL_COLD_START_TOKENS) -> dict[str, Any]:
    """Measure whether this project's own guidance can be complied with."""
    findings: list[dict[str, str]] = []
    report: dict[str, Any] = {"project": project.name, "budget": budget}

    resolution = resolve_roles(project)
    segments = []
    for binding in resolution.bindings:
        try:
            segments.extend(segment_document(binding, resolution.project))
        except GodmodeError:
            continue
    required_tokens = sum(segment.tokens for segment in segments)
    ratio = round(required_tokens / budget, 1) if budget else 0.0

    report["authority"] = {
        "documents": len(resolution.bindings),
        "roles": len({b.role for b in resolution.bindings}),
        "segments": len(segments),
        "tokens_to_read_everything": required_tokens,
        "times_over_budget": ratio,
        "missing_roles": sorted({role for role, _ in resolution.missing}),
        "collisions": [{"path": p, "roles": list(r)} for p, r in resolution.collisions],
    }

    if ratio > 1:
        findings.append(_finding(
            "high", "compliance-cliff",
            f"Reading every bound authority document costs about {required_tokens:,} tokens, "
            f"{ratio}x the {budget:,} an agent will spend at cold start. The rules cannot all be "
            "read, so which ones are followed depends on the model rather than on the project.",
            "Rank the corpus to the task with `brief` instead of expecting a full read, and retire "
            "or promote guidance that never fires.",
        ))
    if resolution.collisions:
        findings.append(_finding(
            "high", "role-collision",
            f"{len(resolution.collisions)} file(s) are claimed by more than one role.",
            "Give each document exactly one role in the role bindings.",
        ))

    claims = authority_claims(project)
    total_claims = sum(entry["claims"] for entry in claims)
    report["authority_claims"] = {
        "files": len(claims), "assertions": total_claims, "top": claims[:8],
    }
    if len(claims) > 1:
        findings.append(_finding(
            "high", "competing-authority",
            f"{len(claims)} files assert primacy ({total_claims} assertions). When several sources "
            "claim to be authoritative the effective number is zero: whichever was read last wins, "
            "which is a function of session order rather than correctness.",
            "Keep status in one writable store and generate the rest as read-only views.",
        ))

    try:
        charter = compile_charter(project)
        enforceable = charter["enforcement"][HARD] + charter["enforcement"][SOFT]
        share = round(enforceable / charter["rules"], 3) if charter["rules"] else 0.0
        report["charter"] = {
            "rules": charter["rules"],
            "hard": charter["enforcement"][HARD],
            "soft": charter["enforcement"][SOFT],
            "advisory": charter["enforcement"][ADVISORY],
            "checkable_share": share,
        }
        if charter["rules"] and share < 0.25:
            findings.append(_finding(
                "medium", "unenforceable-guidance",
                f"Only {share:.0%} of {charter['rules']} compiled rules carry any verification "
                "method; the rest are advisory prose that nothing can check.",
                "Give recurring rules a runnable check, so they become gates rather than reminders.",
            ))
    except GodmodeError as exc:
        report["charter"] = {"unavailable": str(exc)[:160]}

    atlas = build_atlas(project)
    diagnosis = atlas.diagnose()
    cycles = atlas.cycles()
    orphans = atlas.orphans()
    report["code"] = {
        "files": diagnosis["files"], "symbols": diagnosis["symbols"],
        "edges": diagnosis["edges"], "unparsed": len(diagnosis["unparsed"]),
        "cycles": len(cycles), "unreached_symbols": len(orphans),
    }
    if cycles:
        findings.append(_finding(
            "medium", "import-cycle",
            f"{len(cycles)} import cycle(s) found by extraction: "
            + "; ".join(" -> ".join(c) for c in cycles[:3]),
            "Break the cycle before the modules involved grow further.",
        ))
    if diagnosis["unparsed"]:
        findings.append(_finding(
            "low", "unparsed-files",
            f"{len(diagnosis['unparsed'])} file(s) could not be parsed, so absence claims about "
            "them are unsafe.",
            "Fix or exclude them, then re-run so the map covers the whole project.",
        ))

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["code"]))
    report["findings"] = findings
    report["verdict"] = (
        "governable" if not findings
        else "at-risk" if any(f["severity"] == "high" for f in findings)
        else "workable"
    )
    return report


def selftest() -> dict[str, Any]:
    """Exercise every control against a disposable project and report what held.

    A control is reported as enforced only after it has been observed refusing
    something. Claiming enforcement without exercising it is the failure this
    command exists to catch.
    """
    from .godmode_anchor import resolve_anchor
    from .godmode_attest import gate, open_session, record_claim, record_step
    from .godmode_chronicle import Chronicle
    from .godmode_drift import capabilities
    from .godmode_errors import ArchiveError
    from .godmode_plan import mutation_verdict, start as plan_start
    from .godmode_status import record_item

    controls: list[dict[str, Any]] = []

    def check(name: str, expectation: str, probe) -> None:
        try:
            held, observed = probe()
        except Exception as exc:  # pragma: no cover - defensive
            controls.append({"control": name, "enforced": False, "expected": expectation,
                             "observed": f"probe failed: {exc}"[:160]})
            return
        controls.append({"control": name, "enforced": bool(held),
                         "expected": expectation, "observed": observed})

    import os
    from unittest import mock

    with tempfile.TemporaryDirectory() as raw:
        base = Path(raw)
        project = base / "project"
        project.mkdir()
        (project / "GODMODE.md").write_text(
            "# Gates\n- Never commit without an explicit ask.\n", encoding="utf-8"
        )
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(base / "state")}, clear=False):
            archive = Chronicle(resolve_anchor(project))
            archive.initialize()
            charter = compile_charter(project)
            session = open_session(archive, "selftest")

            def unattested_blocks():
                hard = [r for r in charter["compiled"] if r["enforcement"] == HARD]
                if not hard:
                    return False, "no HARD rule compiled to test against"
                verdict = gate(archive, session, charter, hard[0]["trigger"])
                return not verdict.allowed, f"gate refused with {len(verdict.missing)} unattested rule(s)"

            def skip_needs_reason():
                try:
                    record_step(archive, session, "probe", "skipped")
                    return False, "a reasonless skip was accepted"
                except ArchiveError:
                    return True, "a skip without a stated reason was refused"

            def uncited_claim_downgrades():
                record = record_claim(archive, project, session, "Everything is wired.", "verified")
                return (record["data"]["grade"] == "hypothesis",
                        f"claimed verified, stored as {record['data']['grade']}")

            def finished_work_stays_finished():
                record_item(archive, "PROBE-1", "probe", "verified")
                try:
                    record_item(archive, "PROBE-1", "probe", "active")
                    return False, "verified work reopened without proof"
                except ArchiveError:
                    return True, "reopening verified work without proof was refused"

            def plan_gates_mutation():
                plan_start(archive, session, "probe", {"objective": "only this field"})
                verdict = mutation_verdict(archive, session)
                return not verdict["allowed"], "mutation closed while the plan contract is incomplete"

            check("attestation gate", "an unattested HARD rule blocks its gate", unattested_blocks)
            check("skip accountability", "a skip must state a reason", skip_needs_reason)
            check("claim binding", "an uncited claim is downgraded", uncited_claim_downgrades)
            check("completed-work immunity", "verified work needs proof to reopen", finished_work_stays_finished)
            check("plan mode", "mutation is closed until the plan is approved", plan_gates_mutation)

    surface = capabilities()
    enforced = sum(1 for c in controls if c["enforced"])
    return {
        "controls": controls,
        "enforced": enforced,
        "total": len(controls),
        "host": surface["host"],
        "unavailable_here": surface["unavailable"],
        "verdict": "enforcing" if enforced == len(controls) else "degraded",
    }


def _self_check() -> None:
    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "docs").mkdir()
        (project / "GODMODE.md").write_text(
            "# Gates\n- Never commit without an explicit ask.\n"
            "This document is the single source of truth.\n", encoding="utf-8"
        )
        (project / "docs" / "STATE.md").write_text(
            "The SSOT for state lives here instead.\n", encoding="utf-8"
        )
        (project / "a.py").write_text("import b\n", encoding="utf-8")
        (project / "b.py").write_text("import a\n", encoding="utf-8")

        report = assess(project, budget=10)
        codes = {f["code"] for f in report["findings"]}
        assert "competing-authority" in codes, report["findings"]
        assert "compliance-cliff" in codes, report["findings"]
        assert "import-cycle" in codes, report["findings"]
        assert report["verdict"] == "at-risk", report["verdict"]
        assert report["authority_claims"]["files"] == 2, report["authority_claims"]

        # A tidy project earns a clean verdict rather than a manufactured finding.
        calm = Path(raw) / "calm"
        (calm / "docs").mkdir(parents=True)
        (calm / "GODMODE.md").write_text("# Gates\n- Never commit without an explicit ask.\n",
                                         encoding="utf-8")
        clean = assess(calm, budget=100_000)
        assert clean["verdict"] in ("governable", "workable"), clean["findings"]

    surface = selftest()
    assert surface["total"] == 5, surface
    assert surface["verdict"] == "enforcing", surface["controls"]

    print("godmode_assess self-check OK")


if __name__ == "__main__":
    _self_check()
