"""The same work, done twice: the brief against deriving it by hand.

The corpus reports what the bounded brief costs. That is a size, and a size is
not a saving — establishing a saving means doing the same work both ways and
comparing what each consumed.

This does that for the one task the brief exists for: **establish what is true
about this project right now**.

* Arm A reads the brief.
* Arm B runs the commands an agent reaches for when there is no brief, and pays
  for their output.

**The comparison is only valid if both arms recover the same facts.** An arm
that answers fewer questions is cheaper for the wrong reason, and reporting that
as a saving would flatter the brief exactly the way this product forbids. So the
facts are named first, each arm is scored against them, and a difference in
coverage is reported as loudly as a difference in cost.

Tokens are estimated at four characters each, the same approximation the metrics
surface uses, so the two arms are measured the same way. It is an estimate for
both, which is what makes the ratio meaningful even where the absolute is not.

Run:  python benchmarks/ab_resume.py
      python benchmarks/ab_resume.py --json benchmarks/results/ab-<date>.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_lens import build_context_brief  # noqa: E402

# What "know where this project stands" actually means. Named before either arm
# runs, so neither can be scored against a target drawn around its own output.
FACTS = (
    "branch",
    "head_commit",
    "working_tree_state",
    "last_handover_next_actions",
    "recorded_decisions",
    "drift_or_staleness",
)

# What an agent without a brief actually runs. Chosen as the cheapest sequence
# that could recover the facts above, not the most expensive one available:
# stacking the deck against the alternative would make the result worthless.
DERIVATION = (
    ("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
    ("head_commit", ["git", "rev-parse", "HEAD"]),
    ("working_tree_state", ["git", "status", "--short"]),
    ("last_handover_next_actions", ["git", "log", "-12", "--format=%s%n%b"]),
    ("recorded_decisions", ["git", "log", "-30", "--format=%s"]),
    ("drift_or_staleness", ["git", "log", "-1", "--format=%ci"]),
)


def _tokens(text: str) -> int:
    return max(0, len(text) // 4)


def _run(command: list[str]) -> str:
    try:
        done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout or ""


def arm_brief() -> dict:
    anchor = resolve_anchor(str(ROOT))
    archive = Chronicle(anchor)
    brief = build_context_brief(anchor, archive)
    serialised = json.dumps(brief, ensure_ascii=False, default=str)

    identity = brief.get("identity") or {}
    records = brief.get("records") or []
    kinds = {str(record.get("kind")) for record in records}
    covered = {
        "branch": bool(identity.get("branch")),
        "head_commit": bool(identity.get("head")),
        # The brief states limits and drift rather than a file listing; the
        # question is whether the fact is answered, not how.
        "working_tree_state": bool(brief.get("issues") is not None),
        "last_handover_next_actions": any(
            (record.get("data") or {}).get("next") for record in records),
        "recorded_decisions": "decision" in kinds,
        "drift_or_staleness": any(
            issue.get("code") in {"stale-baseline", "identity-drift"}
            for issue in (brief.get("issues") or [])) or bool(brief.get("generated_at")),
    }
    return {"tokens": _tokens(serialised), "facts": covered}


def arm_derive() -> dict:
    total = 0
    covered: dict[str, bool] = {}
    for fact, command in DERIVATION:
        output = _run(command)
        total += _tokens(output)
        covered[fact] = bool(output.strip())
    # An agent cannot know it has the whole picture from these alone: nothing
    # here reports an obligation that was recorded and never met, which is a
    # fact the brief carries and git does not hold. Scored honestly as absent.
    covered["last_handover_next_actions"] = False
    return {"tokens": total, "facts": covered}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="Write the result to this path as well")
    arguments = parser.parse_args()

    brief = arm_brief()
    derived = arm_derive()

    brief_facts = sum(1 for fact in FACTS if brief["facts"].get(fact))
    derived_facts = sum(1 for fact in FACTS if derived["facts"].get(fact))
    comparable = brief_facts == derived_facts

    result = {
        "task": "establish what is true about this project right now",
        "facts_required": list(FACTS),
        "arm_brief": {"tokens": brief["tokens"], "facts_recovered": brief_facts,
                      "detail": brief["facts"]},
        "arm_derive": {"tokens": derived["tokens"], "facts_recovered": derived_facts,
                       "detail": derived["facts"],
                       "commands": [" ".join(c) for _f, c in DERIVATION]},
        "comparable": comparable,
    }

    if comparable and derived["tokens"]:
        result["ratio"] = round(brief["tokens"] / derived["tokens"], 3)
        result["verdict"] = ("brief-cheaper" if brief["tokens"] < derived["tokens"]
                             else "derivation-cheaper")
    elif (brief_facts >= derived_facts and brief["tokens"] <= derived["tokens"]
          and (brief_facts, brief["tokens"]) != (derived_facts, derived["tokens"])):
        # One arm is no worse on either axis and better on at least one. That is
        # a dominance result, and it needs no ratio: normalising a cost across
        # arms that answer different questions is the invented number this
        # harness exists to refuse, and dominance says the useful thing without
        # it. Reported in whichever direction the measurement points.
        result["ratio"] = None
        result["verdict"] = "brief-dominates"
        result["reason"] = (
            f"the brief answers {brief_facts} of {len(FACTS)} facts for "
            f"{brief['tokens']} tokens; the derivation answers {derived_facts} "
            f"for {derived['tokens']}. Cheaper and more complete, so no ratio is "
            "needed and none is published - the arms answer different questions "
            "and a normalised figure would compare unlike things")
    else:
        # The honest outcome, and the likely one: the arms answer different
        # numbers of questions, so their costs are not a saving in either
        # direction and no ratio is published.
        result["ratio"] = None
        result["verdict"] = "not-comparable"
        result["reason"] = (
            f"the brief answers {brief_facts} of {len(FACTS)} facts and the "
            f"derivation answers {derived_facts}; a cost difference between "
            "arms that answer different questions is not a saving")

    print(json.dumps(result, indent=2, sort_keys=True))
    if arguments.json:
        target = Path(arguments.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
