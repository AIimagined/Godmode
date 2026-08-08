"""Public prose held to the standard the runtime already holds claims to.

`record_claim` refuses an assertion about project state that cites nothing.
Documentation asserts constantly and cites nothing, and until now nothing
checked it - so a README could carry an unfalsifiable superlative, or a
justification for a decision nobody questioned, and only a reader would notice.

The seed case was exactly that: a licence section arguing Apache over MIT.
Nobody had asked. Internal deliberation on a public surface costs every reader
attention, invites a debate the project does not need, and belongs in a
decision record where it is answered once.

Four classes, each with a remedy rather than a scold:

* rationale-leak - defending a choice against an alternative nobody raised;
* unverifiable-claim - a superlative no reader can check;
* counterfactual-claim - asserting what would have happened otherwise;
* internal-leak / unfinished-marker / local-path - notes, markers, and machine
  paths that were never meant to ship.

Private surfaces are never linted: a decision record is exactly where the
rationale belongs, so flagging it there would invert the point.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from .godmode_constants import RUNTIME_VERSION
from typing import Any

CONFIG_FILENAME = ".godmode-docslint.json"

# Documents a stranger reads. Everything else is working material.
_PUBLIC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})
# `changelog.d` is deliberately absent: a fragment is merged verbatim into a
# public changelog, so treating it as working material meant its prose was only
# checked after it had shipped, when changing it is a rewrite of history rather
# than an edit. It is public prose that has not been published yet.
_PRIVATE_PARTS = frozenset({
    ".godmode-private", ".research", ".planning", ".sprints", ".checkpoints",
    ".handovers", ".evidence", ".decisions", ".lessons", ".git", "node_modules",
    "tests", "evals",
})

CHECKS: dict[str, dict[str, Any]] = {
    "rationale-leak": {
        "pattern": re.compile(
            r"(?i)\b(?:chosen|picked|selected|opted|went)\s+(?:for\s+)?"
            r"(?:over|instead\s+of|rather\s+than)\b"
            r"|\b(?:we|i)\s+(?:chose|picked|selected|use[d]?|prefer(?:red)?)\b[^.]{0,60}"
            r"\b(?:over|instead\s+of|rather\s+than)\b"
            r"|\bwas\s+chosen\s+(?:over|instead\s+of|rather\s+than)\b"),
        "why": "defends a choice against an alternative the reader did not raise",
        "remedy": "state the choice plainly; move the reasoning to a decision record",
        "severity": "medium",
    },
    "unverifiable-claim": {
        # Anchored on a copula, because the target is a claim about the product
        # ("is the most secure"), not the ordinary English word: a code of
        # conduct saying "what is best for the community" asserts nothing about
        # software, and flagging it would teach the reader to skip the check.
        "pattern": re.compile(
            r"(?i)\b(?:is|are|remains?|stays?|becomes?)\s+(?:by\s+far\s+)?the\s+"
            r"(?:most|best|fastest|safest|strongest|leading|simplest|only)\b"
            r"|\b(?:world[- ]class|industry[- ]leading|state[- ]of[- ]the[- ]art|"
            r"unmatched|unparalleled|bulletproof|rock[- ]solid)\b"),
        "why": "a superlative the reader cannot check, and the runtime would downgrade",
        "remedy": "replace with the measurement, or drop the comparison",
        "severity": "medium",
    },
    "counterfactual-claim": {
        "pattern": re.compile(
            r"(?i)\b(?:prevented|averted|would\s+have\s+(?:caused|broken|failed|cost)|"
            r"saved\s+you|stopped\s+\d+\s+(?:bugs|errors|incidents|defects))\b"),
        # Negation exempts the line: "refusals recorded, not disasters averted"
        # is the disclaimer, not the boast. Flagging the sentence that refuses
        # the claim would teach a writer to delete the honesty and keep the
        # claim - the precise inversion of the point.
        "unless": re.compile(
            r"(?i)\b(?:never|not|rather\s+than|instead\s+of|cannot|can(?:no|')t|"
            r"unmeasurable|unknowable)\b"),
        "why": "asserts what would have happened, which nothing here can measure",
        "remedy": "report what was recorded instead of what it might have prevented",
        "severity": "high",
    },
    "internal-leak": {
        "pattern": re.compile(
            r"(?i)\b(?:as\s+(?:we|i)\s+discussed|per\s+our\s+(?:chat|call|discussion)|"
            r"internal\s+note|for\s+now,?\s+until\s+(?:we|i))\b"),
        "why": "internal deliberation on a public surface",
        "remedy": "delete it, or record it as a decision with its rationale",
        "severity": "medium",
    },
    "unfinished-marker": {
        "pattern": re.compile(r"\b(?:TODO|FIXME|XXX|HACK|WIP|TBD)\b(?!\s*:?\s*\|)"),
        "why": "an unfinished marker shipped to readers",
        "remedy": "finish it, or move it to the tracker",
        "severity": "medium",
    },
    "local-path": {
        "pattern": re.compile(
            r"(?i)(?:[a-z]:\\users\\[^\s\\]+|/(?:home|Users)/[a-z0-9._-]{2,})"),
        "why": "a machine-specific path that will not exist for the reader",
        "remedy": "use a relative path or a placeholder",
        "severity": "high",
    },
}


def _config(project: Path) -> dict[str, Any]:
    path = Path(project) / CONFIG_FILENAME
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _is_public(path: Path, project: Path) -> bool:
    if path.suffix.lower() not in _PUBLIC_SUFFIXES:
        return False
    try:
        relative = path.relative_to(project)
    except ValueError:
        return False
    return not any(part in _PRIVATE_PARTS for part in relative.parts)


def lint_text(path: str, text: str, ignore: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Findings for one document's text. Code blocks are skipped: a fenced
    example may legitimately contain any of these shapes."""
    findings: list[dict[str, Any]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith(("    ", "\t")):
            continue
        for name, check in CHECKS.items():
            if name in ignore:
                continue
            exemption = check.get("unless")
            if exemption is not None and exemption.search(line):
                continue
            match = check["pattern"].search(line)
            if match:
                findings.append({
                    "path": path,
                    "line": number,
                    "check": name,
                    "severity": check["severity"],
                    "why": check["why"],
                    "remedy": check["remedy"],
                    "excerpt": line.strip()[:160],
                })
    return findings


def _headings(text: str) -> list[tuple[str, int]]:
    """Every ATX heading with the line it sits on, ignoring fenced blocks."""
    found: list[tuple[str, int]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(r"\s{0,3}#{1,6}\s+(?P<title>.+?)\s*#*\s*$", line)
        if match:
            found.append((match.group("title").strip(), number))
    return found


def _section_is_empty(text: str, start: int) -> bool:
    """Whether the section opened at `start` carries any content.

    Bounded by the next heading or by the end of the file, because a trailing
    section has no following heading and is exactly where an off-by-one would
    hide the finding.
    """
    lines = text.splitlines()
    for line in lines[start:]:
        if re.match(r"\s{0,3}#{1,6}\s+", line):
            return True
        if line.strip():
            return False
    return True


def _contract_findings(relative: str, text: str,
                       contracts: dict[str, Any]) -> list[dict[str, Any]]:
    """Sections a document must carry, checked for present *and* not empty."""
    findings: list[dict[str, Any]] = []
    headings = _headings(text)
    by_title = {title.casefold(): line for title, line in headings}
    for pattern, required in contracts.items():
        if not _matches(relative, pattern):
            continue
        for title in required:
            line = by_title.get(str(title).casefold())
            if line is None:
                findings.append({
                    "path": relative, "line": 1, "check": "missing-section",
                    "severity": "high",
                    "why": f"the contract for `{pattern}` requires a "
                              f"`{title}` section and the document has none",
                    "remedy": f"add a `{title}` heading, or change the contract "
                              "if the obligation no longer holds",
                })
            elif _section_is_empty(text, line):
                findings.append({
                    "path": relative, "line": line, "check": "empty-section",
                    "severity": "high",
                    "why": f"`{title}` is present but carries no content",
                    "remedy": "write the section, or remove the heading rather "
                              "than leaving a promise the reader cannot collect",
                })
    return findings


def _matches(relative: str, pattern: str) -> bool:
    """`**` spans directories; a pattern without a slash matches the basename,
    so `RELEASE_NOTES_*.md` need not be written as a path to be useful."""
    if fnmatch.fnmatch(relative, pattern):
        return True
    if "**/" in pattern and fnmatch.fnmatch(relative, pattern.replace("**/", "")):
        return True
    return "/" not in pattern and fnmatch.fnmatch(relative.rsplit("/", 1)[-1], pattern)


def _declared_contracts(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Usable contracts, and a finding for each one that cannot be used.

    A mistyped contract is reported rather than dropped: an operator who
    believes their documents are under a check that never ran is worse off than
    one who declared nothing.
    """
    declared = config.get("contracts")
    if declared is None:
        return {}, []
    if not isinstance(declared, dict):
        return {}, [{
            "path": CONFIG_FILENAME, "line": 1, "check": "malformed-contract",
            "severity": "medium",
            "why": "`contracts` must map a path pattern to a list of section titles",
            "remedy": "correct the declaration; no contract was applied",
        }]
    usable: dict[str, Any] = {}
    problems: list[dict[str, Any]] = []
    for pattern, required in declared.items():
        if isinstance(required, list) and all(isinstance(t, str) for t in required):
            usable[pattern] = required
        else:
            problems.append({
                "path": CONFIG_FILENAME, "line": 1, "check": "malformed-contract",
                "severity": "medium",
                "why": f"the contract for `{pattern}` is not a list of section titles",
                "remedy": "give it a list of headings; this contract was not applied",
            })
    return usable, problems



# A number in public prose that the runtime can count for itself.
#
# The README badge read 359 tests while the suite ran 527, and
# `documentation_parity` reported every trigger satisfied, because a badge is
# not a tracked trigger. A stale public numeric claim passed every gate this
# product has.
#
# Only countables with an exact local answer are listed. A figure the runtime
# cannot compute is left alone rather than guessed at: a checker that invents an
# expected value teaches the reader to ignore it.
_TEST_FUNCTION = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.MULTILINE)


def _count_tests(project: Path) -> int | None:
    tests = project / "tests"
    if not tests.is_dir():
        return None
    total = 0
    for path in sorted(tests.rglob("test_*.py")):
        try:
            total += len(_TEST_FUNCTION.findall(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return total or None


def _count_hosts(project: Path) -> int | None:
    manifest = project / "packaging" / "hosts.json"
    if not manifest.is_file():
        return None
    try:
        hosts = json.loads(manifest.read_text(encoding="utf-8")).get("hosts")
    except (OSError, json.JSONDecodeError):
        return None
    return len(hosts) if isinstance(hosts, dict) and hosts else None


COUNTABLES: dict[str, Any] = {
    "tests": _count_tests,
    # `hosts` is deliberately absent. The manifest lists three plugin hosts and
    # the project also ships three adapters, so no single number in the tree is
    # the answer and the checker would have reported a true badge as stale.
    # A figure without an exact local answer is left alone.
}

# A changelog entry or a shipped release note states what was true when it was
# written. Comparing a historical record against today's count reports every
# past release as wrong, which is the fastest way to teach a reader to ignore
# the check.
_HISTORICAL = re.compile(r"(?i)(?:^|/)(?:CHANGELOG|HISTORY|RELEASE_NOTES_)")

# Both shapes a figure appears in: a shields.io style badge segment, and an
# ordinary sentence.
_BADGE_FIGURE = re.compile(r"/badge/(?P<name>[a-z]+)-(?P<value>\d+)")
_PROSE_FIGURE = re.compile(r"(?<![\w.])(?P<value>\d+)\s+(?P<name>[a-z]+)\b")


# This project pinning a version of itself. An install snippet is the one place
# a reader copies verbatim, so a stale pin here hands them an old build - and
# the figure check above deliberately skips fenced blocks, which is exactly
# where every install snippet lives. The README pinned `@v0.2.0` through seven
# releases and nothing said so.
#
# Unlike a count, this has one exact local answer, which is why it is checkable
# at all: `hosts` and the command total were both left out for want of one.
_SELF_PIN = re.compile(r"AIimagined/Godmode@v(?P<value>\d+\.\d+\.\d+)")


def _self_pin_findings(relative: str, text: str, current: str) -> list[dict[str, Any]]:
    """Snippets pinning a version of this project that is no longer current."""
    if _HISTORICAL.search(relative):
        return []
    findings: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in _SELF_PIN.finditer(line):
            pinned = match.group("value")
            if pinned == current:
                continue
            findings.append({
                "path": relative, "line": number, "check": "stale-self-pin",
                "severity": "medium",
                "why": f"pins this project at v{pinned}; the current version is "
                       f"v{current}",
                "remedy": f"update the pin to v{current}, or say why this "
                          "snippet documents an older release",
                "excerpt": line.strip()[:160],
            })
    return findings


def _figure_findings(relative: str, text: str, project: Path) -> list[dict[str, Any]]:
    """Numeric claims the runtime can check, compared against the real count."""
    if _HISTORICAL.search(relative):
        return []
    actual: dict[str, int] = {}
    for name, counter in COUNTABLES.items():
        value = counter(project)
        if isinstance(value, int):
            actual[name] = value
    if not actual:
        return []

    findings: list[dict[str, Any]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for pattern in (_BADGE_FIGURE, _PROSE_FIGURE):
            for match in pattern.finditer(line):
                name = match.group("name").lower()
                if name not in actual:
                    continue
                claimed = int(match.group("value"))
                if claimed == actual[name]:
                    continue
                findings.append({
                    "path": relative, "line": number, "check": "stale-figure",
                    "severity": "medium",
                    "why": f"claims {claimed} {name}; this project counts {actual[name]}",
                    "remedy": f"update the figure to {actual[name]}, or stop stating a "
                              "number that changes on every commit",
                    "excerpt": line.strip()[:160],
                })
    return findings


def lint_docs(project: Path) -> dict[str, Any]:
    """Lint every public document in the project.

    Two directions, not one. The negative checks ask whether a document
    contains something it should not; the declared contracts ask whether it
    contains something it must. A linter with only the first half can never
    report worse than the truth, and every one of its false negatives flatters.
    """
    project = Path(project)
    config = _config(project)
    ignore = tuple(config.get("ignore_checks") or ())
    contracts, findings = _declared_contracts(config)
    scanned = 0
    for path in sorted(project.rglob("*")):
        if not path.is_file() or not _is_public(path, project):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        relative = path.relative_to(project).as_posix()
        findings.extend(lint_text(relative, text, ignore=ignore))
        if contracts:
            findings.extend(_contract_findings(relative, text, contracts))
        findings.extend(_figure_findings(relative, text, project))
        findings.extend(_self_pin_findings(relative, text, RUNTIME_VERSION))
    high = [f for f in findings if f["severity"] == "high"]
    return {
        "documents_scanned": scanned,
        "findings": findings,
        "high_severity": len(high),
        "ignored_checks": list(ignore),
        # Stated so a report cannot be read as "checked against a contract"
        # when none was declared.
        "contracts_applied": sorted(contracts),
        "verdict": "clean" if not findings else "findings",
    }
