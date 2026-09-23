"""`godmode retest` (field report file Part 5, 2026-09-10): the tests that
pin a changed file, as one command per runner, run and attested on
request. "Pins" is textual and language-neutral: a test file that names
the changed file's path, module, or stem. A changed test file pins
itself. The command is printed even when it is not run, so the reader
can paste it; `--run` executes it through `run_check` and the exit code
becomes the `retest` attestation the done bar can cite.
"""
from __future__ import annotations

import json

import re
from pathlib import Path
from typing import Any

from .godmode_anchor import run_git

_TEST_FILE = re.compile(r"(?i)(^|/)(tests?|spec|__tests__|specs)/|(^|/)(test_[^/]+|[^/]+[._-](test|spec))\.[a-z]+$")
_SKIP_DIRS = ("node_modules/", ".git/", "dist/", "build/", ".venv/", "venv/", ".godmode-repo/")
_PY_RUNNER = ("py",)
_JS_RUNNER = ("ts", "tsx", "js", "jsx", "mjs", "cjs")


def changed_files(project: Path, base: str = "HEAD") -> list[str]:
    out: list[str] = []
    raw = run_git(project, "diff", "--name-only", "--no-renames", base) or ""
    out.extend(line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip())
    untracked = run_git(project, "ls-files", "--others", "--exclude-standard") or ""
    out.extend(line.strip().replace("\\", "/") for line in untracked.splitlines() if line.strip())
    return sorted(set(out))


def _needles(path: str) -> list[str]:
    stem = Path(path).stem
    module = path.rsplit(".", 1)[0].replace("/", ".")
    needles = {path, Path(path).name, stem, module}
    if module.startswith("src.") or module.startswith("scripts."):
        needles.add(module.split(".", 1)[1])
    return [n for n in needles if len(n) >= 4]


def _test_files(project: Path) -> list[str]:
    tracked = run_git(project, "ls-files") or ""
    untracked = run_git(project, "ls-files", "--others", "--exclude-standard") or ""
    names = [line.strip().replace("\\", "/") for line in (tracked + "\n" + untracked).splitlines() if line.strip()]
    return [n for n in names if _TEST_FILE.search(n) and not any(s in n for s in _SKIP_DIRS)]


TEST_MAP_FILENAME = ".godmode-test-map.json"


def committed_test_map(project: Path) -> dict[str, list[str]]:
    """`.godmode-test-map.json` at the project root: source path -> the test
    files that pin it, committed by the project (absorbed from a hook
    toolkit's test-cohesion map, 2026-09-10). Textual pinning cannot see a
    test that reaches a module through a fixture or a CLI; the map can.
    Entries naming a test file that does not exist are dropped, stated."""
    path = Path(project) / TEST_MAP_FILENAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for source, tests in raw.items():
        if not isinstance(tests, list):
            continue
        kept = [str(t).replace("\\", "/") for t in tests if (Path(project) / str(t)).is_file()]
        if kept:
            out[str(source).replace("\\", "/")] = kept
    return out


def pinning_tests(project: Path, changed: list[str]) -> dict[str, list[str]]:
    """test file -> the changed files it pins."""
    tests = _test_files(project)
    out: dict[str, list[str]] = {}
    mapped = committed_test_map(project)
    for path in changed:
        for test in mapped.get(path, []):
            if path not in out.setdefault(test, []):
                out[test].append(path)
    for test in tests:
        if test in changed:
            out.setdefault(test, []).append(test)
        try:
            text = (Path(project) / test).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for path in changed:
            if path == test or _TEST_FILE.search(path):
                continue
            if any(re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", text) for n in _needles(path)):
                out.setdefault(test, []).append(path)
    return out


def retest_module_names(project: Path, files: list[str]) -> set[str]:
    """The dotted module name of every Python test that pins one of
    `files` - the exact form `commands()` builds into a retest command
    line (`t[:-3].replace("/", ".")`).

    Fix round 1, S1: this lived as three independently-typed private
    copies (`godmode_closure._retest_module_names`,
    `godmode_reversals._retest_module_names`, and a fourth ad hoc regex
    scan inside `godmode_graph._retested_by_edges`) - one home here, so
    the file->module bridge cannot drift out of sync with itself again.
    """
    pinned = pinning_tests(project, files)
    return {test[:-3].replace("/", ".") for test in pinned if test.endswith(".py")}


def cited_modules(record: dict[str, Any]) -> set[str] | None:
    """The module names a `check:retest:*` attestation actually covered, or
    `None` when that cannot be determined honestly.

    Fix round 1, S1/S2 (absorbed from `godmode_closure._cited_modules`,
    now the one shared reader). Preferred source: `data["modules"]`,
    written structurally by `godmode_attest.run_check` when its caller
    supplies one - exact, untruncated. Fallback (an older record with no
    `modules` key): the `cmd:` evidence string, whitespace-tokenised - a
    caller matching against a KNOWN module-name set may safely intersect
    against the raw tokens (flag and runner tokens never coincide with a
    real dotted module name), but a caller MINTING node ids from these
    tokens must still filter them to a module-shaped pattern, because a
    flag or an interpreter path is not a module. If the citation is
    exactly as long as `run_check`'s own 160-character cap, it may have
    lost trailing modules entirely with no way to tell which - this
    returns `None` rather than guess, and a caller must treat that as
    "this record proves nothing", never as "the file is covered".
    """
    data = record.get("data") or {}
    modules_field = data.get("modules")
    if isinstance(modules_field, list) and modules_field:
        return {str(module) for module in modules_field}
    citation = next(
        (str(item) for item in record.get("evidence") or [] if str(item).startswith("cmd:")),
        None,
    )
    if citation is None:
        return set()
    if len(citation) - len("cmd:") >= 160:
        return None
    return set(citation.split())


def commands(project: Path, pinned: dict[str, list[str]]) -> list[dict[str, Any]]:
    """One command per runner: unittest for Python tests, vitest or jest
    for JavaScript and TypeScript (whichever the project declares), a
    named gap for anything else."""
    py = sorted(t for t in pinned if t.endswith(".py"))
    js = sorted(t for t in pinned if t.rsplit(".", 1)[-1] in _JS_RUNNER)
    other = sorted(t for t in pinned if t not in py and t not in js)
    out: list[dict[str, Any]] = []
    if py:
        modules = [t[:-3].replace("/", ".") for t in py]
        # `"modules"` (I-6 fix round 1, S1): the exact dotted names carried
        # in `command` below, exposed structurally so a caller attesting
        # this run (`cmd_retest`) can store them on the attestation
        # (`run_check(..., modules=...)`) instead of a reader having to
        # re-parse `command`, which `run_check`'s own citation truncates.
        #
        # `"pinned_sources"` (I-6 fix round 2, D5): every file these
        # `modules` pin (the union of `pinned[t]` for each test `t` here),
        # so `cmd_retest` can pass them to `run_check(..., blob_paths=...)`
        # and hash each one's exact working-tree content at the moment
        # this run actually happened - the proof
        # `godmode_closure._unattested_but_unchanged` needs to trust this
        # attestation for a file with no `edit-recorded` action, even on
        # the dirty tree the normal edit-then-retest flow always has.
        pinned_sources = sorted({source for test in py for source in pinned.get(test, [])})
        out.append({"runner": "unittest", "files": py, "modules": modules,
                    "pinned_sources": pinned_sources,
                    "command": "python -m unittest " + " ".join(modules)})
    if js:
        runner = "vitest"
        try:
            package = (Path(project) / "package.json").read_text(encoding="utf-8", errors="replace")
            if "jest" in package and "vitest" not in package:
                runner = "jest"
        except OSError:  # godmode: swallow-ok: no package.json means the default runner, stated in the command
            pass
        out.append({"runner": runner, "files": js,
                    "command": ("npx vitest run " if runner == "vitest" else "npx jest ") + " ".join(js)})
    if other:
        out.append({"runner": "unknown", "files": other, "command": None,
                    "detail": "no runner known for these; run them yourself and cite the run"})
    return out


def retest_plan(project: Path, base: str = "HEAD") -> dict[str, Any]:
    changed = changed_files(project, base)
    pinned = pinning_tests(project, changed)
    unpinned = [c for c in changed if not _TEST_FILE.search(c) and not any(c in v for v in pinned.values())
                and c.rsplit(".", 1)[-1] in _PY_RUNNER + _JS_RUNNER]
    return {"base": base, "changed": changed, "pinned": pinned, "commands": commands(project, pinned),
            "unpinned": unpinned}
