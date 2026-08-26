"""C-05: one severity-ranked list of output-quality findings.

Three detectors already exist and are tested on their own: the docs lint,
the swallow scanner, and the minimality report. Each answers a narrower
question in its own shape. This module computes nothing new - it folds
their findings into one canonical record and sorts worst-first, the same
aggregation-only stance `godmode_minimality` takes over the atlas.

Remediation is guarded structurally. Every finding carries a `remedy` and
`remediation: "proposal"`; there is no apply path in this module, and a
test pins that the tree is byte-identical after a report. The doctrine is
propose-never-install: a remedy the operator has not run is a sentence,
not a change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .godmode_docslint import lint_docs
from .godmode_minimality import minimality_report
from .godmode_swallow import scan_project

# Worst first. `advisory` is the swallow scanner's word for "worth a look,
# never a regression"; `low` is the rank a minimality section maps to when
# its finding is a question rather than a defect.
RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2, "advisory": 3}

# A minimality section is a question about shape, not a broken line; the
# two that name decayed or duplicated authority rank above the ones that
# only ask whether a seam earns its place.
_MINIMALITY_SEVERITY: dict[str, str] = {
    "duplicate-authority": "medium",
    "charter-decay": "medium",
    "duplicate-symbols": "low",
    "speculative-seams": "low",
    "orphan-symbols": "low",
    "unexercised-surfaces": "advisory",
}


def _finding(source: str, severity: str, path: str, line: int,
             message: str, remedy: str, check: str) -> dict[str, Any]:
    return {
        "source": source,
        "severity": severity if severity in RANK else "advisory",
        "path": path,
        "line": int(line or 0),
        "check": check,
        "message": message[:240],
        "remedy": remedy[:240],
        "remediation": "proposal",
    }


def _from_docslint(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _finding("docs", f.get("severity", "medium"), str(f.get("path", "")),
                 f.get("line", 0), str(f.get("why", "")), str(f.get("remedy", "")),
                 str(f.get("check", "")))
        for f in report.get("findings", [])
    ]


def _from_swallow(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _finding("swallow", f.get("severity", "advisory"), str(f.get("path", "")),
                 f.get("line", 0), str(f.get("why", "")), str(f.get("remedy", "")),
                 str(f.get("check", "")))
        for f in report.get("findings", [])
    ]


def _from_minimality(report: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in report.get("sections", []):
        name = str(section.get("section", ""))
        severity = _MINIMALITY_SEVERITY.get(name, "low")
        for item in section.get("items", []):
            if not isinstance(item, dict):
                continue
            message = str(item.get("question") or item.get("why") or item.get("kind") or name)
            path = str(item.get("path") or item.get("a") or item.get("symbol") or "")
            out.append(_finding(
                "minimality", severity, path, item.get("line", 0), message,
                f"answer the {name} question or accept it with `minimality --accept-growth`",
                name))
    return out


def quality_report(project: Path | str, archive: Any = None) -> dict[str, Any]:
    project = Path(project)
    findings = (_from_docslint(lint_docs(project))
                + _from_swallow(scan_project(project))
                + _from_minimality(minimality_report(project, archive)))
    findings.sort(key=lambda f: (RANK[f["severity"]], f["source"], f["path"], f["line"]))
    counts = {level: 0 for level in RANK}
    for finding in findings:
        counts[finding["severity"]] += 1
    return {
        "findings": findings,
        "counts": counts,
        "sources": ["docs", "swallow", "minimality"],
        "remediation": "proposals only - this command executes nothing",
        "verdict": "findings-present" if findings else "clean",
    }


# C-63: the two shapes editors already consume. Nothing is installed into
# any editor - a problem matcher or a SARIF viewer reads what is printed.

def render_editor(report: dict[str, Any]) -> str:
    """`path:line: severity: message` - GCC's shape, which VS Code's default
    problem matcher parses - one finding per line."""
    return "\n".join(
        f"{f['path'] or '<project>'}:{f['line']}: {f['severity']}: {f['message']}"
        for f in report["findings"])


def render_sarif(report: dict[str, Any], tool_version: str) -> dict[str, Any]:
    """The smallest SARIF 2.1.0 document a SARIF viewer accepts."""
    level = {"high": "error", "medium": "warning", "low": "note", "advisory": "note"}
    results = []
    for f in report["findings"]:
        result: dict[str, Any] = {
            "ruleId": f"{f['source']}/{f['check'] or 'finding'}",
            "level": level[f["severity"]],
            "message": {"text": f["message"]},
        }
        if f["path"]:
            result["locations"] = [{"physicalLocation": {
                "artifactLocation": {"uri": f["path"].replace("\\", "/")},
                "region": {"startLine": max(1, f["line"])},
            }}]
        results.append(result)
    # No `$schema` URL: the runtime carries no remote literal, by a test
    # that scans every module for one. SARIF viewers key on `version`.
    return {
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "godmode", "version": tool_version}},
                  "results": results}],
    }
