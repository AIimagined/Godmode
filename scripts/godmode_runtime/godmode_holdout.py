"""A controlled holdout over the experiment ledger.

Absorbed 2026-08-27 from an upstream plugin's holdout harness, in this
runtime's shape: the ledger already adjudicates one cycle against its own
baseline (`record_experiment_verdict`: before, after, epsilon). A holdout
asks the other question - with a change on for some runs and off for
others, do the arms differ by more than epsilon?

Medians, so one bad run does not decide. At least two observations per
arm, or the verdict is `underpowered` rather than a guess. Arms within
epsilon read `indistinguishable`, a real answer and the honest one for
most changes. Nothing here runs anything: the observations are handed in,
already measured, and the record carries the commit they were judged at.
"""
from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from .godmode_anchor import run_git
from .godmode_errors import ArchiveError

MIN_PER_ARM = 2


def record_holdout(archive: Any, project: Path | str, *, name: str, metric: str,
                   control: list[float], treatment: list[float], epsilon: float,
                   lower_is_better: bool = False) -> dict[str, Any]:
    eps = float(epsilon)
    if not eps > 0:
        raise ArchiveError("epsilon must be a positive number; a non-positive epsilon adjudicates nothing")
    if not name.strip() or not metric.strip():
        raise ArchiveError("a holdout needs a name and a metric")
    arms = {"control": [float(v) for v in control], "treatment": [float(v) for v in treatment]}
    for label, values in arms.items():
        if any(v != v or v in (float("inf"), float("-inf")) for v in values):
            raise ArchiveError(f"{label} carries a non-finite observation; nothing to adjudicate")
    n = {label: len(values) for label, values in arms.items()}
    medians = {label: (median(values) if values else None) for label, values in arms.items()}

    if min(n.values()) < MIN_PER_ARM:
        verdict, difference = "underpowered", None
    else:
        difference = medians["treatment"] - medians["control"]
        better = -difference if lower_is_better else difference
        if better >= eps:
            verdict = "treatment"
        elif better <= -eps:
            verdict = "control"
        else:
            verdict = "indistinguishable"

    data = {
        "name": name.strip()[:120],
        "metric": metric.strip()[:80],
        "n": n,
        "medians": medians,
        "difference": difference,
        "epsilon": eps,
        "lower_is_better": bool(lower_is_better),
        "min_per_arm": MIN_PER_ARM,
        "verdict": verdict,
        "commit": run_git(Path(project), "rev-parse", "HEAD"),
        "shape": "holdout",
    }
    # The same kind an experiment cycle's adjudication uses: a holdout is a
    # verdict over two arms, not a new record shape.
    return archive.append("verdict", f"holdout:{data['name']}", data)
