"""C-56: a plan arbiter. Deterministic, and it never picks silently.

Two plans for the same work, and a reader who wants to know which one to
hold the agent to. The arbiter scores each on what a plan can be held to:

- acceptance criteria stated (the plan says what "done" means),
- verification steps named (the plan says how it will be checked),
- `file:` citations that resolve in the project (the plan is about this
  tree, not an imagined one),
- open questions left (`?`, TBD, TODO, maybe - the plan is not finished).

The score is a small integer sum so every point is legible in `reasons`.
A tie returns `undecided` with both scores shown: the arbiter's job is to
make the difference between plans visible, not to break a tie the plans
themselves do not break.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

_ACCEPTANCE = re.compile(r"(?im)^\s*#+\s*acceptance|acceptance criteria|done when|must pass")
_VERIFY = re.compile(r"(?i)\b(verify|verified|verification|assert|tests?|unittest|pytest)\b")
_QUESTION = re.compile(r"(?i)\?|\bTBD\b|\bTODO\b|\bmaybe\b")
_CITE = re.compile(r"\bfile:([^\s`)\],]+)")


def _normalise(citation: str) -> str:
    head, separator, tail = citation.rpartition(":")
    if separator and tail.isdigit():
        citation = head
    return citation.replace("\\", "/").lstrip("./")


def score_plan(project: Path, plan: Path) -> dict[str, Any]:
    text = plan.read_text(encoding="utf-8")
    lines = text.splitlines()
    acceptance = bool(_ACCEPTANCE.search(text))
    verification = sum(1 for line in lines if _VERIFY.search(line))
    cited = [_normalise(c) for c in _CITE.findall(text)]
    resolved = [c for c in cited if (project / c).exists()]
    unresolved = [c for c in cited if not (project / c).exists()]
    open_questions = sum(1 for line in lines if _QUESTION.search(line))
    score = (3 * int(acceptance) + min(verification, 5)
             + len(resolved) - len(unresolved) - open_questions)
    return {
        "plan": plan.name,
        "acceptance_criteria": acceptance,
        "verification_steps": verification,
        "resolved_citations": resolved,
        "unresolved_citations": unresolved,
        "open_questions": open_questions,
        "score": score,
    }


def _reasons(scored: dict[str, Any]) -> list[str]:
    name = scored["plan"]
    out = [f"{name}: acceptance criteria {'stated' if scored['acceptance_criteria'] else 'absent'} "
           f"({'+3' if scored['acceptance_criteria'] else '+0'})",
           f"{name}: {scored['verification_steps']} verification step(s) "
           f"(+{min(scored['verification_steps'], 5)}, capped at 5)"]
    if scored["resolved_citations"]:
        out.append(f"{name}: {len(scored['resolved_citations'])} citation(s) resolve "
                   f"(+{len(scored['resolved_citations'])})")
    if scored["unresolved_citations"]:
        out.append(f"{name}: {len(scored['unresolved_citations'])} citation(s) do not resolve "
                   f"(-{len(scored['unresolved_citations'])}): "
                   + ", ".join(scored["unresolved_citations"]))
    if scored["open_questions"]:
        out.append(f"{name}: {scored['open_questions']} open question(s) "
                   f"(-{scored['open_questions']})")
    return out


def arbitrate(project: Path | str, plans: list[Path]) -> dict[str, Any]:
    project = Path(project)
    scored = [score_plan(project, Path(plan)) for plan in plans]
    ranked = sorted(scored, key=lambda s: (-s["score"], s["plan"]))
    decided = len(ranked) >= 2 and ranked[0]["score"] > ranked[1]["score"]
    if len(ranked) == 1:
        decided = True
    reasons = [reason for plan in ranked for reason in _reasons(plan)]
    if not decided and len(ranked) >= 2:
        reasons.append(f"tie at {ranked[0]['score']}: the plans do not differ on "
                       "anything a plan can be held to; the arbiter does not break ties")
    return {
        "plans": ranked,
        "winner": ranked[0]["plan"] if decided else None,
        "verdict": "decided" if decided else "undecided",
        "reasons": reasons,
    }
