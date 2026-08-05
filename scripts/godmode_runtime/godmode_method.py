"""Select an analysis method from the shape of the evidence, not from judgment.

Method choice currently happens at the moment an agent is under most pressure to
produce an answer, and the default under pressure is always the cheapest method that
yields a story: one causal chain, stated as fact. So selection here is a lookup
table, and each method carries a completion contract that must be satisfied before
its result may be published.

"Unknown" is never terminal. Closing without a root requires shipping an instrument
in the same pass, so the next occurrence is self-diagnosing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FIVE_WHYS = "5-whys"
PARETO = "pareto"
FISHBONE = "fishbone"
FMEA = "fmea"
FAULT_TREE = "fault-tree"
TIMELINE = "timeline"

METHODS = (FIVE_WHYS, PARETO, FISHBONE, FMEA, FAULT_TREE, TIMELINE)

DEFAULT_SPINES = (
    "input",
    "logic",
    "data",
    "runtime",
    "output",
    "environment",
    "process",
)


@dataclass(frozen=True)
class Shape:
    """What we know about the evidence before choosing how to analyse it."""

    reports: int = 1
    reproducible: bool = True
    ordering_question: bool = False
    components_enumerable: bool = False
    contributing_conditions: int = 0

    def view(self) -> dict[str, Any]:
        return {
            "reports": self.reports,
            "reproducible": self.reproducible,
            "ordering_question": self.ordering_question,
            "components_enumerable": self.components_enumerable,
            "contributing_conditions": self.contributing_conditions,
        }


# Ordered. First match wins, so the table reads as precedence and stays deterministic.
def select(shape: Shape) -> tuple[list[str], str]:
    """Return (method sequence, the reason it was selected)."""
    if shape.ordering_question:
        return [TIMELINE], "an ordering, race or latch-time question is answered on a time axis"
    if shape.reports > 1:
        return (
            [FISHBONE, PARETO, FIVE_WHYS],
            "a pile of reports must be grouped, ranked, then drilled — never drilled first",
        )
    if shape.components_enumerable:
        return [FMEA], "enumerable components and failure modes support a risk-ranked sweep"
    if shape.contributing_conditions > 1:
        return [FAULT_TREE], "one severe failure with several contributing conditions decomposes through gates"
    if not shape.reproducible:
        return (
            [TIMELINE, FIVE_WHYS],
            "an unreproducible single report needs its order reconstructed before any causal chain",
        )
    return [FIVE_WHYS], "a single reproducible report drills straight to a root"


# Every field must be present and non-empty for the method to be complete.
CONTRACTS: dict[str, tuple[str, ...]] = {
    FIVE_WHYS: ("symptom", "links", "root"),
    PARETO: ("clusters", "coverage"),
    FISHBONE: ("spines", "assignments", "chosen_spine"),
    FMEA: ("modes",),
    FAULT_TREE: ("top_event", "gates", "cut_sets"),
    TIMELINE: ("instruments", "events"),
}


def contract(method: str) -> tuple[str, ...]:
    if method not in CONTRACTS:
        raise KeyError(f"Unknown method '{method}'")
    return CONTRACTS[method]


def _link_is_cited(link: Any) -> bool:
    return isinstance(link, dict) and bool(str(link.get("evidence", "")).strip())


def complete(method: str, record: dict[str, Any]) -> dict[str, Any]:
    """Check a method record against its contract. Returns gaps, never raises."""
    gaps: list[str] = []
    for field in contract(method):
        value = record.get(field)
        if value is None or (hasattr(value, "__len__") and len(value) == 0):
            gaps.append(f"missing:{field}")

    if method == FIVE_WHYS:
        links = record.get("links") or []
        # A speculative link cannot advance the chain: every 'why' needs evidence.
        uncited = [index for index, link in enumerate(links, 1) if not _link_is_cited(link)]
        if uncited:
            gaps.append(f"uncited_links:{','.join(str(i) for i in uncited)}")
        if str(record.get("root", "")).strip().lower() in ("unknown", "unclear", ""):
            if not str(record.get("instrument", "")).strip():
                gaps.append("unknown_without_instrument")

    if method == PARETO:
        clusters = record.get("clusters") or []
        # Clustering by symptom makes every report look unique; the key must be a root.
        if any(not str(c.get("root", "")).strip() for c in clusters if isinstance(c, dict)):
            gaps.append("cluster_without_root")
        if any(int(c.get("count", 0)) <= 0 for c in clusters if isinstance(c, dict)):
            gaps.append("cluster_without_count")

    if method == FISHBONE:
        spines = set(record.get("spines") or ())
        assignments = record.get("assignments") or []
        stray = [a for a in assignments if isinstance(a, dict) and a.get("spine") not in spines]
        if stray:
            gaps.append("assignment_outside_spines")

    if method == FMEA:
        modes = record.get("modes") or []
        for mode in modes:
            if not isinstance(mode, dict):
                continue
            if not all(key in mode for key in ("severity", "occurrence", "detection")):
                gaps.append("mode_missing_score")
                break

    if method == TIMELINE:
        instruments = record.get("instruments") or []
        if len(instruments) < 2:
            gaps.append("single_instrument")

    return {"method": method, "complete": not gaps, "gaps": gaps}


def rank_fmea(modes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Risk priority = severity x occurrence x detection. Higher detection = harder to see."""
    ranked = []
    for mode in modes:
        score = int(mode.get("severity", 0)) * int(mode.get("occurrence", 0)) * int(mode.get("detection", 0))
        ranked.append({**mode, "risk": score})
    ranked.sort(key=lambda mode: (-mode["risk"], str(mode.get("name", ""))))
    return ranked


def pareto_order(clusters: list[dict[str, Any]], threshold: float = 0.8) -> dict[str, Any]:
    """Sort roots by report count and mark where the coverage threshold is crossed."""
    ordered = sorted(clusters, key=lambda c: (-int(c.get("count", 0)), str(c.get("root", ""))))
    total = sum(int(c.get("count", 0)) for c in ordered) or 1
    running = 0
    covered: list[dict[str, Any]] = []
    for cluster in ordered:
        running += int(cluster.get("count", 0))
        covered.append({**cluster, "cumulative": round(running / total, 4)})
        if running / total >= threshold:
            break
    return {"ordered": ordered, "fix_first": covered, "threshold": threshold, "reports": total}


def _self_check() -> None:
    # Selection is a lookup: identical shapes always select identically.
    one = Shape(reports=1, reproducible=True)
    assert select(one)[0] == [FIVE_WHYS]
    assert select(Shape(reports=9))[0] == [FISHBONE, PARETO, FIVE_WHYS]
    assert select(Shape(ordering_question=True, reports=9))[0] == [TIMELINE]
    assert select(Shape(components_enumerable=True))[0] == [FMEA]
    assert select(Shape(contributing_conditions=3))[0] == [FAULT_TREE]
    assert select(Shape(reproducible=False))[0] == [TIMELINE, FIVE_WHYS]
    for _ in range(20):
        assert select(one) == select(one)

    # An uncited 'why' cannot advance the chain.
    partial = complete(FIVE_WHYS, {
        "symptom": "token replay",
        "links": [{"why": "rotation reused", "evidence": "src/auth.py:88"}, {"why": "guessing"}],
        "root": "rotation reused",
    })
    assert not partial["complete"] and "uncited_links:2" in partial["gaps"], partial

    whole = complete(FIVE_WHYS, {
        "symptom": "token replay",
        "links": [{"why": "rotation reused", "evidence": "src/auth.py:88"}],
        "root": "rotation reused",
    })
    assert whole["complete"], whole

    # Unknown is not terminal without an instrument.
    stuck = complete(FIVE_WHYS, {"symptom": "s", "links": [{"why": "w", "evidence": "e"}], "root": "unknown"})
    assert "unknown_without_instrument" in stuck["gaps"]
    instrumented = complete(FIVE_WHYS, {
        "symptom": "s", "links": [{"why": "w", "evidence": "e"}],
        "root": "unknown", "instrument": "log token audience at rotation",
    })
    assert instrumented["complete"], instrumented

    # Clustering by symptom is refused; a cluster must name a root.
    assert "cluster_without_root" in complete(PARETO, {
        "clusters": [{"count": 3}], "coverage": 0.8})["gaps"]

    # A timeline built from one instrument is not a timeline.
    assert "single_instrument" in complete(TIMELINE, {
        "instruments": ["log"], "events": [{"at": "t0"}]})["gaps"]

    ranked = rank_fmea([
        {"name": "silent discard", "severity": 8, "occurrence": 3, "detection": 9},
        {"name": "loud failure", "severity": 9, "occurrence": 2, "detection": 1},
    ])
    assert ranked[0]["name"] == "silent discard", ranked

    spread = pareto_order([{"root": "a", "count": 9}, {"root": "b", "count": 1}])
    assert spread["fix_first"][0]["root"] == "a"
    assert len(spread["fix_first"]) == 1, spread

    print("godmode_method self-check OK")


if __name__ == "__main__":
    _self_check()
