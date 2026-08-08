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
    # deliberate simplification: quote-parity, not a tokenizer; a marker inside a string literal is
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
    # deliberate simplification: rationale is a recorded decision, not a password capability;
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
    # Ran last and unconditionally: the monitors above ask what a change means,
    # and this asks the earlier question of whether the write arrived intact at
    # all. A file that no longer parses cannot be reasoned about by any of them.
    findings.extend(source_damage(project, base))
    blocking = [f for f in findings if f["blocking"]]
    return {
        "base": base,
        "files_changed": len(files),
        "findings": findings,
        "blocking": bool(blocking),
        "verdict": "blocked" if blocking else "clean",
    }


# Damage an agent does to source with its own tools.
#
# The nine monitors above watch what a change does to the meaning of the tests.
# These watch something earlier and dumber: whether the write itself arrived
# intact. A scripted edit reported success while a shell halved its backslashes
# and turned a word-boundary into a literal backspace byte, so every pattern in
# the file silently matched nothing. It was found by a test failing later, never
# by the write - and twice more in the same session, the same way.
#
# Only what this diff touched is examined. A pre-existing oddity elsewhere is
# not this pass's finding, and reporting it trains the reader to skip the whole
# report.
_TEXT_SUFFIXES = frozenset({
    ".py", ".md", ".json", ".yml", ".yaml", ".txt", ".toml", ".cfg", ".ini",
    ".ts", ".tsx", ".js", ".jsx", ".sh", ".ps1",
})

# Tab, newline and carriage return are ordinary. Everything else below 0x20,
# plus DEL, is residue no editor produces - a backspace inside a regex is the
# signature of a shell that mangled it on the way to disk.
_ALLOWED_CONTROL = frozenset({0x09, 0x0a, 0x0d})


def _changed_paths(project: Path, base: str) -> list[str]:
    raw = run_git(project, "diff", "--name-only", base) or ""
    tracked = [line.strip() for line in raw.splitlines() if line.strip()]
    untracked = (run_git(project, "ls-files", "--others", "--exclude-standard") or "")
    tracked += [line.strip() for line in untracked.splitlines() if line.strip()]
    return sorted(set(tracked))


def source_damage(project: Path, base: str = "HEAD") -> list[dict[str, Any]]:
    """Files this change touched that no longer parse, or carry control bytes."""
    project = Path(project)
    findings: list[dict[str, Any]] = []

    for relative in _changed_paths(project, base):
        path = project / relative
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue

        # Reported per file rather than per byte: one mangled write usually
        # leaves several, and a finding per occurrence buries the file.
        for number, line in enumerate(raw.split(b"\n"), 1):
            bad = sorted({byte for byte in line
                          if byte < 0x20 and byte not in _ALLOWED_CONTROL} |
                         ({0x7f} if 0x7f in line else set()))
            if bad:
                listed = ", ".join(f"0x{byte:02x}" for byte in bad)
                findings.append(_finding(
                    "control-characters", relative,
                    f"line {number} carries {listed}, which no editor writes - "
                    "the signature of a shell or script mangling content on the "
                    "way to disk",
                    True))
                break

        if path.suffix.lower() == ".py":
            try:
                compile(raw.decode("utf-8", errors="replace"), str(path), "exec")
            except SyntaxError as exc:
                findings.append(_finding(
                    "unparseable-source", relative,
                    f"no longer parses after this change: {exc.msg} at line {exc.lineno}",
                    True))
            except ValueError as exc:
                findings.append(_finding(
                    "unparseable-source", relative, f"cannot be compiled: {exc}", True))

    findings.extend(tooling_damage(project, base))
    findings.extend(guard_quality(project, base))
    return findings


# Files whose change carries no meaning, and changes that make every later
# result suspect.
#
# An anchored edit that matches nothing reports success and leaves the file as
# it was; the failure is invisible because the tool said yes. A dependency
# change under a running process leaves stale artefacts that mimic a code
# regression, so a test run after it is evidence about the old tree.
_DEPENDENCY_FILES = frozenset({
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "requirements.txt", "pyproject.toml", "poetry.lock", "Pipfile.lock",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "Gemfile.lock",
})


def _meaningful_change(project: Path, base: str, relative: str) -> bool:
    """Whether a diff changed anything but whitespace."""
    raw = run_git(project, "diff", "--ignore-all-space", "--ignore-blank-lines",
                  base, "--", relative)
    if raw is None:
        return True
    return bool(raw.strip())


def tooling_damage(project: Path, base: str = "HEAD") -> list[dict[str, Any]]:
    """Changes that reported success without meaning, and changes that invalidate later runs."""
    project = Path(project)
    findings: list[dict[str, Any]] = []
    changed = _changed_paths(project, base)

    for relative in changed:
        if Path(relative).name in _DEPENDENCY_FILES:
            findings.append(_finding(
                "dependency-changed", relative,
                "dependencies changed; a process started before this is serving "
                "the old tree, so restart or reinstall before treating any later "
                "run as evidence",
                # Reported, not blocked: editing a lockfile is ordinary, and a
                # gate that stops it is a gate that gets switched off.
                False))
            continue
        path = project / relative
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        # Untracked files have no diff to compare against; they are new, not no-ops.
        if run_git(project, "ls-files", "--error-unmatch", relative) is None:
            continue
        if not _meaningful_change(project, base, relative):
            findings.append(_finding(
                "no-op-change", relative,
                "appears in this change but differs only in whitespace - an "
                "anchored edit that matched nothing reports success and leaves "
                "the file as it was",
                False))
    return findings


# Verifications that pass while proving less than their reader will assume.
#
# A guard whose name promises "every" and whose body asserts one case reads as
# coverage in every listing that quotes it - and the name is what a later reader
# trusts, while the assertion is what actually holds. A test that writes outside
# a temporary directory is writing somewhere real; a mistake ledger records a
# write-endpoint smoke test aimed at a live project id, which returned 200 and
# destroyed the draft it was verifying.
# The quantifier binds the subject, so it sits at the front of the name.
# Matching it anywhere reported `test_a_change_is_not_reported_as_a_no_op` and
# `test_a_session_that_was_never_corrected` - ordinary English mid-sentence,
# not a claim about a set. Four false positives on this project's own tests,
# which is the rate at which a reader starts skipping the monitor.
_UNIVERSAL_NAME = re.compile(
    r"^\s*(?:async\s+)?def\s+test_(?:a_|the_)?"
    r"(?:every|all|never|no|each|any)_[a-z0-9_]*\s*\(", re.M)
_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_[a-z0-9_]+)\s*\(", re.M)
# A body that touches a collection covers more than one case without a loop:
# `assert offenders == []` is universal, and demanding an explicit loop would
# report the strongest form of the assertion as the weakest.
_COVERS_MANY = re.compile(
    r"\bfor\s+\w+\s+in\b|\bassertEqual\(\s*\w+\s*,\s*\[\s*\]|==\s*\[\s*\]"
    r"|\ball\(|\bany\(|assertCountEqual|assertListEqual|\[[^\]]*for\s+\w+\s+in")
_WRITE_CALL = re.compile(
    r"\.write_text\(|\.write_bytes\(|\bopen\([^)]*['\"][wa]|\bshutil\.(?:copy|move|rmtree)\("
    r"|\bos\.remove\(|\bPath\([^)]*\)\.unlink\(")
# A path that is already temporary, by fixture or by construction.
_TEMPORARY = re.compile(
    r"tmp_path|tmpdir|TemporaryDirectory|mkdtemp|gettempdir|NamedTemporaryFile"
    r"|isolated_project|_project\(|holder\.|self\.project|/tmp/")


def guard_quality(project: Path, base: str = "HEAD") -> list[dict[str, Any]]:
    """Guards that pass while covering less than their name or scope implies."""
    project = Path(project)
    findings: list[dict[str, Any]] = []

    for relative in _changed_paths(project, base):
        if not _is_test_path(relative) or not relative.endswith(".py"):
            continue
        path = project / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        bodies = _test_bodies(text)
        for name, body in bodies.items():
            if _UNIVERSAL_NAME.search(f"def {name}(") and not _COVERS_MANY.search(body):
                findings.append(_finding(
                    "universal-name-single-case", relative,
                    f"`{name}` promises a universal and asserts one case; the name "
                    "is what a later reader trusts, so either cover the set or "
                    "narrow the name",
                    False))
            writes = [line for line in body.splitlines() if _WRITE_CALL.search(line)]
            if writes and not any(_TEMPORARY.search(line) for line in writes) \
                    and not _TEMPORARY.search(body):
                findings.append(_finding(
                    "test-writes-real-path", relative,
                    f"`{name}` writes to a path that is not temporary: "
                    f"{writes[0].strip()[:70]} - a write-endpoint test aimed at "
                    "real data destroys what it was verifying",
                    False))
    return findings


def _test_bodies(text: str) -> dict[str, str]:
    """Each test function's source, split on the next definition."""
    matches = list(_TEST_DEF.finditer(text))
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        bodies[match.group(1)] = text[match.start():end]
    return bodies
