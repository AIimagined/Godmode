"""Nine test-integrity monitors: detect a change that weakens what tests prove.

A test suite can be made green by fixing the code or by quieting the tests. The
second path is invisible in a pass/fail summary, so these monitors read the change
itself - the diff and the archive - and name every edit that reduced what the suite
can catch. Two classes of finding: `blocking` stops completion (E-05); the rest are
reported so a reviewer sees the shape of the change, not just its colour.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .godmode_anchor import run_git
from .godmode_chronicle import Chronicle
from .godmode_errors import ArchiveError

_TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__)(/|$)|(^|/)test_[^/]+$|_test\.[^/.]+$|\.(test|spec)\.[^/.]+$"
)
_ASSERTION = re.compile(
    r"^\s*(assert\b|self\.assert|expect\s*\(|\.should\b|assert_eq!|ASSERT_|EXPECT_)"
)
_SKIP = re.compile(
    r"@unittest\.skip|pytest\.mark\.(skip|xfail)|@pytest\.skip|\.only\s*\(|\.skip\s*\(|"
    r"\bxit\s*\(|\bxdescribe\s*\(|\bit\.todo\b|#\s*type:\s*ignore.*test|@Disabled|@Ignore\b"
)
_MOCK = re.compile(r"\b(mock|Mock|patch|stub|sinon|jest\.mock|monkeypatch)\b")


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def _in_string(line: str, position: int) -> bool:
    # [private]: quote-parity, not a tokenizer; a marker inside a string literal is
    # fixture data, not a live skip. Multi-line strings still slip through.
    return line.count('"', 0, position) % 2 == 1 or line.count("'", 0, position) % 2 == 1


def _live_match(pattern: re.Pattern[str], line: str) -> bool:
    match = pattern.search(line)
    return bool(match) and not _in_string(line, match.start())


def _changed_files(project: Path, base: str) -> dict[str, str]:
    raw = run_git(project, "diff", "--name-status", "--no-renames", base)
    if raw is None:
        raise ArchiveError("Integrity monitors need a Git repository to diff against")
    files: dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files[parts[-1]] = parts[0][:1]
    return files


def _diff_lines(project: Path, base: str, path: str) -> tuple[list[str], list[str]]:
    raw = run_git(project, "diff", "--unified=0", "--no-color", base, "--", path) or ""
    removed = [l[1:] for l in raw.splitlines() if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in raw.splitlines() if l.startswith("+") and not l.startswith("+++")]
    return removed, added


def _finding(monitor: str, path: str, detail: str, blocking: bool) -> dict[str, Any]:
    return {"monitor": monitor, "path": path, "detail": detail, "blocking": blocking}


def _assertion_diff(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for path in ctx["changed_tests"]:
        removed, added = ctx["diff"][path]
        lost = [l.strip() for l in removed if _ASSERTION.match(l)]
        kept = [l.strip() for l in added if _ASSERTION.match(l)]
        gone = [l for l in lost if l not in kept]
        if len(kept) < len(lost):
            findings.append(_finding(
                "assertion-diff", path,
                f"{len(lost) - len(kept)} assertion(s) removed and not replaced: "
                + "; ".join(gone[:3]),
                blocking=True,
            ))
    return findings


def _skip_quarantine(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for path in ctx["changed_tests"]:
        removed, added = ctx["diff"][path]
        introduced = [l.strip() for l in added if _live_match(_SKIP, l)]
        pre_existing = [l.strip() for l in removed if _live_match(_SKIP, l)]
        new = [l for l in introduced if l not in pre_existing]
        if new:
            findings.append(_finding(
                "skip-quarantine", path,
                "new skip/only/xfail marker(s): " + "; ".join(new[:3]),
                blocking=True,
            ))
    return findings


def _mock_expansion(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for path in ctx["changed_tests"]:
        removed, added = ctx["diff"][path]
        grew = sum(1 for l in added if _MOCK.search(l)) - sum(1 for l in removed if _MOCK.search(l))
        if grew > 0:
            findings.append(_finding(
                "mock-expansion", path,
                f"{grew} more mock reference(s) than before; a real boundary may have been replaced",
                blocking=False,
            ))
    return findings


def _coverage_shape(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    untested = ctx["changed_production"] if not ctx["changed_tests"] else []
    if not untested:
        return []
    return [_finding(
        "coverage-shape", path,
        "production path changed with no test change in the same diff",
        blocking=False,
    ) for path in untested]


def _protected(archive: Chronicle) -> set[str]:
    return {
        record["subject"]
        for record in archive.select(kind="invariant", limit=500)
        if record["data"].get("status") != "retired"
    }


def _requirement_anchor(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    protected = ctx["protected"]
    return [_finding(
        "requirement-anchor", path,
        "changed test is not anchored to any recorded invariant; record one with "
        "`remember --kind invariant` so its purpose survives the author",
        blocking=False,
    ) for path in ctx["changed_tests"] if path not in protected]


def _red_before_green(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    seen_failing = {
        evidence[len("file:"):]
        for record in ctx["archive"].select(kind="attestation", limit=1000)
        if record["subject"].startswith("guard:") and record["data"].get("status") == "ran"
        for evidence in record.get("evidence", [])
        if evidence.startswith("file:")
    }
    return [_finding(
        "red-before-green", path,
        "new test was never observed failing; run `plant` against its target",
        blocking=False,
    ) for path, status in ctx["files"].items()
        if status == "A" and _is_test_path(path) and path not in seen_failing]


def _harness_validity(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    if not ctx["changed_tests"]:
        return []
    ran_any_check = any(
        record["subject"].startswith("check:")
        for record in ctx["archive"].select(kind="attestation", limit=1000)
    )
    if ran_any_check:
        return []
    return [_finding(
        "harness-validity", ", ".join(sorted(ctx["changed_tests"])),
        "tests changed but no runner-attested check exists; run `verify` so the "
        "result is recorded by the runner, not reported by the author",
        blocking=False,
    )]


def _negative_control(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    touched_protected = [p for p in ctx["changed_tests"] if p in ctx["protected"]]
    if not touched_protected:
        return []
    has_control = any(
        "negative-control" in record["subject"]
        for record in ctx["archive"].select(kind="attestation", limit=1000)
    )
    if has_control:
        return []
    return [_finding(
        "negative-control", path,
        "a protected test changed with no sibling negative-control attestation "
        "showing neighbouring behaviour is still allowed",
        blocking=False,
    ) for path in touched_protected]


def _protected_test_gate(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    # [private]: rationale is a recorded decision, not a password capability;
    # wire the sentinel broker in if invariants start guarding money paths.
    approved = {
        record["subject"][len("protected-test-change:"):]
        for record in ctx["archive"].select(kind="decision", limit=500)
        if record["subject"].startswith("protected-test-change:")
    }
    return [_finding(
        "protected-test-gate", path,
        "protected test changed without a recorded rationale; record a decision "
        f"with subject `protected-test-change:{path}` before completion",
        blocking=True,
    ) for path in ctx["changed_tests"] if path in ctx["protected"] and path not in approved]


MONITORS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "assertion-diff": _assertion_diff,
    "skip-quarantine": _skip_quarantine,
    "mock-expansion": _mock_expansion,
    "coverage-shape": _coverage_shape,
    "requirement-anchor": _requirement_anchor,
    "red-before-green": _red_before_green,
    "harness-validity": _harness_validity,
    "negative-control": _negative_control,
    "protected-test-gate": _protected_test_gate,
}


def analyze(archive: Chronicle, project: Path, base: str = "HEAD") -> dict[str, Any]:
    """Run every monitor over the diff against `base` and the archive."""
    files = _changed_files(project, base)
    ctx: dict[str, Any] = {
        "archive": archive,
        "files": files,
        "changed_tests": sorted(p for p in files if _is_test_path(p) and files[p] != "D"),
        "changed_production": sorted(
            p for p in files if not _is_test_path(p) and files[p] != "D"
            and Path(p).suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb"}
        ),
        "protected": _protected(archive),
    }
    ctx["diff"] = {path: _diff_lines(project, base, path) for path in ctx["changed_tests"]}

    findings: list[dict[str, Any]] = []
    for monitor in MONITORS.values():
        findings.extend(monitor(ctx))
    blocking = [f for f in findings if f["blocking"]]
    return {
        "base": base,
        "files_changed": len(files),
        "findings": findings,
        "blocking": bool(blocking),
        "verdict": "blocked" if blocking else "clean",
    }
