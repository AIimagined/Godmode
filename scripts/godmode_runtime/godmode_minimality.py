"""Minimality report: one ranked view over surfaces that already measure it.

Aggregation only - no new analysis. Four checks each answer a narrow
question (are there two of this? is anything unreached? does a module serve
only one caller? has a charter rule gone dormant?) and nobody read all four
together, so the ranked-by-count view they deserved never got built until
now.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .godmode_atlas import build as build_atlas, speculative_seams
from .godmode_attest import advisory_decay
from .godmode_census import census
from .godmode_charter import compile_charter
from .godmode_errors import GodmodeError


def minimality_report(project: Path, archive: Any = None) -> dict[str, Any]:
    """Rank existing minimality-pressure surfaces into one report.

    Every count here is produced by a check that already exists and is
    tested on its own; this only sorts and totals what those checks already
    found. An archive-less or empty project reports honest zeros with the
    basis stated, never a manufactured finding.
    """
    project = Path(project)
    atlas = build_atlas(project)
    duplicates = atlas.duplicates()
    orphans = atlas.orphans()
    seams = speculative_seams(atlas)["findings"]

    sections: list[dict[str, Any]] = [
        {"section": "duplicate-symbols", "count": len(duplicates), "items": duplicates[:10],
         "basis": "godmode_atlas.Atlas.duplicates (near-duplicate symbol bodies)"},
        {"section": "orphan-symbols", "count": len(orphans), "items": orphans[:10],
         "basis": "godmode_atlas.Atlas.orphans (unreached symbols)"},
        {"section": "speculative-seams", "count": len(seams), "items": seams[:10],
         "basis": "godmode_atlas.speculative_seams (single-consumer modules)"},
    ]

    unused: list[dict[str, Any]] = []
    dormant: list[dict[str, Any]] = []
    unused_basis = "no archive supplied; census not run"
    dormant_basis = "no archive supplied; advisory_decay not run"
    if archive is not None:
        try:
            unused = census(archive)["unused"]
            unused_basis = "godmode_census.census (declared surfaces never recorded here)"
        except Exception:  # noqa: BLE001 - this section degrades, never fails, the report
            unused_basis = "census could not run against this archive"
        try:
            charter = compile_charter(project)
            decay = advisory_decay(archive, charter)
            dormant = decay["dormant"]
            dormant_basis = "godmode_attest.advisory_decay (rules untouched in the recent window)"
        except GodmodeError:
            dormant_basis = "no charter compiled for this project; advisory_decay not run"

    sections.append({"section": "unexercised-surfaces", "count": len(unused), "items": unused[:10],
                     "basis": unused_basis})
    sections.append({"section": "charter-decay", "count": len(dormant), "items": dormant[:10],
                     "basis": dormant_basis})

    ranked = sorted(sections, key=lambda s: s["count"], reverse=True)
    total = sum(s["count"] for s in sections)
    return {
        "sections": ranked,
        "total_findings": total,
        "verdict": "minimal" if total == 0 else "reinvention-pressure-present",
    }
