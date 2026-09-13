"""Check: guidance stays small, and every hard rule stays attested.

Two properties, one check, because they fail together. Guidance grows by
accretion - each addition is reasonable and the total stops being read - and a
rule nobody reads is an advisory whatever it claims to be.

**The budgets come from a measurement, not from a round number.** Measured
2026-09-13: `GODMODE.md` 49 lines; the largest skill body 96
(`godmode-investigation`); the compiled code of law 119, which is generated
from the rest and so is not budgeted separately. The ceilings below are those
figures plus a stated allowance, so the check fails on growth rather than on
today's content. Raising one is a decision to record, not a number to nudge.

**Attestation is already holding and is asserted rather than assumed.** The
compiler grades 16 rules, 7 of them HARD, and every HARD rule carries a
verification method. That is the state this check pins: a HARD rule added
without one is the regression worth catching, because a rule whose only
justification is convention is unattested and should fail the same gate as an
uncited claim.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from godmode_runtime.godmode_charter import compile_charter  # noqa: E402

#: file -> (ceiling, measured-at-write-time). The second number is kept so a
#: reader can see how much margin the ceiling actually represents.
BUDGETS: dict[str, tuple[int, int]] = {
    "GODMODE.md": (70, 49),
}

#: Every skill body shares one ceiling: they are peers, and a per-skill
#: exception list is how a budget stops meaning anything.
SKILL_BODY_BUDGET = 120
SKILL_BODY_MEASURED_MAX = 96


def guidance_findings(root: Path = ROOT) -> list[str]:
    problems: list[str] = []

    for name, (ceiling, measured) in BUDGETS.items():
        path = root / name
        if not path.exists():
            problems.append(f"{name}: missing; the budget names a file that is not there")
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > ceiling:
            problems.append(
                f"{name}: {lines} lines over the {ceiling} ceiling "
                f"(was {measured} when the ceiling was set). Split it by topic, "
                f"or record a decision raising the ceiling.")

    skills = root / "skills"
    if skills.exists():
        for body in sorted(skills.glob("*/SKILL.md")):
            lines = len(body.read_text(encoding="utf-8").splitlines())
            if lines > SKILL_BODY_BUDGET:
                problems.append(
                    f"skills/{body.parent.name}/SKILL.md: {lines} lines over the "
                    f"{SKILL_BODY_BUDGET} ceiling (largest was "
                    f"{SKILL_BODY_MEASURED_MAX} when it was set). Move detail "
                    f"into a reference file and keep the body a route.")

    return problems


def attestation_findings(root: Path = ROOT) -> list[str]:
    compiled = compile_charter(root)["compiled"]
    hard = [r for r in compiled if r.get("enforcement") == "HARD"]
    unattested = [r for r in hard if r.get("verify") in (None, "", "none")]
    return [
        f"{r.get('source', '?')}: HARD rule with no verification method. "
        f"Name the check that proves it, or grade it ADVISORY."
        for r in unattested
    ]


def main() -> int:
    problems = guidance_findings() + attestation_findings()
    compiled = compile_charter(ROOT)["compiled"]
    hard = sum(1 for r in compiled if r.get("enforcement") == "HARD")
    print(f"rules {len(compiled)}  hard {hard}  budgets {len(BUDGETS) + 1}")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print("ok: guidance within budget, every hard rule attested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
