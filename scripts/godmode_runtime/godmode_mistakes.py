"""Mistake-class detectors: the recurring failures, distilled into checks.

Each detector targets one class from the lesson corpus - not hypothetical
failure modes but the ones that actually recurred. They read the archive and
the tree; none needs a model's cooperation to fire.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from .godmode_chronicle import Chronicle
from .godmode_constants import CODE_SUFFIXES, IGNORED_DIRECTORY_NAMES

_CLAIM_SPLIT = re.compile(r";\s+|\b(?:and also|as well as)\b|\n\s*\d+[.)]\s")
_VERBISH = re.compile(r"\b(?:is|are|was|were|works|passes|fixed|fails|blocks|returns)\b")


def label_as_fact(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M1: a status label used as evidence must trace to the record that assigned it."""
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        evidence = record.get("evidence", [])
        labels = [e for e in evidence if e.startswith("status:") or e.startswith("label:")]
        traced = any(e.startswith("seq:") for e in evidence)
        if labels and not traced:
            findings.append({
                "detector": "label-as-fact", "blocking": True,
                "detail": f"claim '{record['subject'][:60]}' rests on {labels[0]} without "
                          "citing the seq: record that assigned the label",
                "citations": [f"seq:{record['sequence']}"],
            })
    return findings


def ritual_without_reading(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M2: a mandated artefact regenerated but never queried is a box-tick."""
    documented: dict[str, int] = {}
    for record in records:
        if record["kind"] == "documentation":
            documented[record["subject"]] = record["sequence"]
    if not documented:
        return []
    cited: set[str] = set()
    for record in records:
        for evidence in record.get("evidence", []):
            for name in documented:
                if name in evidence:
                    cited.add(name)
    return [{
        "detector": "ritual-without-reading", "blocking": False,
        "detail": f"'{name}' was regenerated (seq:{sequence}) and never cited afterwards; "
                  "generated-but-unread is a box-tick, not a step",
        "citations": [f"seq:{sequence}"],
    } for name, sequence in sorted(documented.items()) if name not in cited]


def invariant_vs_instance(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M6: a guard narrower than its ruling protects one surface of many."""
    findings = []
    for record in records:
        if record["kind"] != "lesson" or not record["data"].get("generalized_guard"):
            continue
        files = [e for e in record.get("evidence", []) if e.startswith("file:")]
        if len(files) == 1:
            findings.append({
                "detector": "invariant-vs-instance", "blocking": True,
                "detail": f"lesson '{record['subject'][:60]}' declares a generalized guard "
                          f"but cites one surface ({files[0]}); enumerate the siblings or "
                          "narrow the ruling",
                "citations": [f"seq:{record['sequence']}"],
            })
    return findings


def stale_runtime(project: Path, process_started: str) -> dict[str, Any]:
    """M8: diagnosing against a process older than the code it runs is blocked."""
    started = datetime.fromisoformat(process_started)
    newest_path, newest_ns = None, 0
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_SUFFIXES:
            continue
        if any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
            continue
        stat_ns = path.stat().st_mtime_ns
        if stat_ns > newest_ns:
            newest_path, newest_ns = path, stat_ns
    newest_at = datetime.fromtimestamp(newest_ns / 1e9, tz=started.tzinfo)
    stale = newest_at > started
    return {
        "process_started": process_started,
        "newest_source": newest_path.relative_to(project).as_posix() if newest_path else None,
        "newest_mtime": newest_at.isoformat(),
        "stale": stale,
        "verdict": "restart-before-rca" if stale else "runtime-is-current",
        "detail": ("the running process predates the newest source change; restart it "
                   "before any diagnosis, or the RCA describes a program that no longer exists"
                   if stale else "the process is newer than every source file"),
    }


def claim_splitting(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M13: one report carrying several independent claims hides the weak one."""
    findings = []
    for record in records:
        if record["kind"] != "claim":
            continue
        text = str(record["data"].get("text", record["subject"]))
        parts = [p for p in _CLAIM_SPLIT.split(text) if _VERBISH.search(p or "")]
        if len(parts) >= 2:
            findings.append({
                "detector": "claim-splitting", "blocking": True,
                "detail": f"'{text[:80]}' bundles {len(parts)} independent claims; split "
                          "them so each is graded on its own evidence",
                "citations": [f"seq:{record['sequence']}"],
            })
    return findings


def analyze(archive: Chronicle) -> dict[str, Any]:
    records = archive.read_events()
    findings = (
        label_as_fact(records)
        + ritual_without_reading(records)
        + invariant_vs_instance(records)
        + claim_splitting(records)
    )
    blocking = [f for f in findings if f["blocking"]]
    return {
        "records_scanned": len(records),
        "findings": findings,
        "blocking": bool(blocking),
        "verdict": "mistake-class-detected" if blocking else "clean",
    }
