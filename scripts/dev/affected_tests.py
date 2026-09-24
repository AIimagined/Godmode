#!/usr/bin/env python3
"""Select and run the test modules affected by the current changes.

    python scripts/dev/affected_tests.py [--base <ref>] [--list] [--all] [--jobs N] [module ...]

Running the full suite (413 modules, ~40 minutes) on every edit is too slow
for iteration. This picks a much smaller set: test modules that are
themselves changed, that import a changed module directly, or that import
a module that imports a changed module (one level through) - plus a small
fixed smoke set that stays selected regardless, so an edit that isn't
caught by the import heuristic still gets some coverage.

"Changed" is `git diff --name-only <base>` (default base: `origin/main`, the published state; local `main` can lag) plus
untracked files. Imports are read with `ast`, mirroring how the tests
themselves put `scripts/`, `scripts/godmode_runtime/`, `hooks/` and
`tests/` on `sys.path` (see e.g. tests/test_absorb_docs.py): module names
are matched to files under those four directories by stem.

A non-Python changed file (docs, json, yml, ...) selects a test module if
that file's basename appears anywhere in the test module's source - cheap,
but enough to catch fixture-path and doc-reference tests.
"""

from __future__ import annotations

import ast
import argparse
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"
MODULE_DIRS = [REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "godmode_runtime",
               REPO_ROOT / "hooks", TESTS_DIR]

# Small, fixed, fast+broad set: always run, so an edit the import heuristic
# misses still gets some coverage. Picked by hand after timing candidates -
# each is well under a second and exercises a wide surface (the full CLI
# verb table, the boundary/protection registry, the atlas registry).
SMOKE_SET = ["tests.test_command_reference_drift", "tests.test_boundary_registry",
             "tests.test_atlas_registry",
             # These scan every test module, so no import edge ever selects
             # them, yet any new test can break them.
             "tests.test_attendance_scrub", "tests.test_godmode_skill_eval",
             "tests.test_godmode_spec_lifecycle"]


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=REPO_ROOT, check=True,
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [line for line in out.splitlines() if line]


def changed_files(base: str) -> set[Path]:
    diffed = _git("diff", "--name-only", base)
    untracked = _git("ls-files", "--others", "--exclude-standard")
    return {REPO_ROOT / rel for rel in diffed + untracked}


def module_map() -> dict[str, Path]:
    """stem -> file, across the directories tests put on sys.path."""
    mapping: dict[str, Path] = {}
    for directory in MODULE_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.py"):
            mapping[path.stem] = path
    return mapping


HUB_LIMIT = 10


def module_imports(path: Path) -> set[str]:
    """Stems this file imports, best-effort (import X / from X import Y)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.update(node.module.split("."))
            names.update(alias.name for alias in node.names)
    return names


def select(changed: set[Path], modules: dict[str, Path]) -> list[str]:
    """Test module names (dotted, e.g. tests.test_x) affected by `changed`."""
    changed_py = {p for p in changed if p.suffix == ".py"}
    changed_stems = {stem for stem, path in modules.items() if path in changed_py}

    imports_of = {stem: module_imports(path) & set(modules) for stem, path in modules.items()}
    direct = {stem for stem, imps in imports_of.items() if imps & changed_stems}
    # Deliberate ceiling: a hub (imported by more than HUB_LIMIT modules, e.g. the console or the
    # shared test helper) is not walked through, or one edit selects the whole suite.
    # The full suite at release is the backstop.
    importers = {stem: sum(stem in imps for imps in imports_of.values()) for stem in modules}
    relay = {stem for stem in direct if importers[stem] <= HUB_LIMIT}
    one_through = {stem for stem, imps in imports_of.items() if imps & relay}

    changed_non_py = {p.name for p in changed if p.suffix != ".py"}

    selected: set[str] = set()
    for stem, path in modules.items():
        if path.parent != TESTS_DIR or not path.name.startswith("test_"):
            continue
        if stem in changed_stems or stem in direct or stem in one_through:
            selected.add(stem)
            continue
        if changed_non_py:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(name in text for name in changed_non_py):
                selected.add(stem)

    result = sorted(f"tests.{stem}" for stem in selected)
    for name in SMOKE_SET:
        if name not in result:
            result.append(name)
    return sorted(set(result))


def all_modules() -> list[str]:
    return sorted(f"tests.{path.stem}" for path in TESTS_DIR.glob("test_*.py"))


# These plant files into the repository tree itself and restore them after, so
# they run alone once the pool is done: a module copying or scanning the tree
# at the same moment would see the plant (e.g. test_gate_falsifiability's copy).
TREE_WRITERS = {"tests.test_capability_register", "tests.test_riders_b4f"}


def run_parallel(modules: list[str], jobs: int) -> int:
    """Each module in its own process, `jobs` at a time; a failing module's
    full output is printed, so its FAIL/ERROR lines reach the caller.
    Each module runs in isolation, as it would alone."""
    from concurrent.futures import ThreadPoolExecutor

    def run(module: str) -> tuple[str, subprocess.CompletedProcess]:
        return module, subprocess.run([sys.executable, "-m", "unittest", module], cwd=REPO_ROOT,
                                      capture_output=True, text=True, encoding="utf-8", errors="replace")

    failed = []

    def report(module: str, done: subprocess.CompletedProcess) -> None:
        if done.returncode:
            failed.append(module)
            print(f"==== {module} (exit {done.returncode})\n{done.stdout}{done.stderr}", flush=True)

    pooled = [m for m in modules if m not in TREE_WRITERS]
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for module, done in pool.map(run, pooled):
            report(module, done)
    for module in [m for m in modules if m in TREE_WRITERS]:
        report(*run(module))
    print(f"{len(modules) - len(failed)} of {len(modules)} module(s) passed"
          + (f"; FAILED: {' '.join(failed)}" if failed else ""))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="origin/main", help="ref to diff against (default: origin/main)")
    parser.add_argument("--list", action="store_true", help="print selected modules and exit")
    parser.add_argument("--all", action="store_true", help="every test module, not only the affected ones")
    parser.add_argument("--jobs", type=int, default=1, help="modules to run at once (default: 1)")
    parser.add_argument("modules", nargs="*", help="run these modules instead of selecting")
    args = parser.parse_args(argv)

    if args.modules:
        modules = args.modules
    elif args.all:
        modules = all_modules()
    else:
        modules = select(changed_files(args.base), module_map())
    if args.list:
        # Bytes, so a Windows console does not turn the newlines into CRLF for `$(...)`.
        sys.stdout.buffer.write(("\n".join(modules) + "\n").encode())
        return 0
    if args.jobs > 1:
        return run_parallel(modules, args.jobs)
    print(f"running {len(modules)} module(s):\n  " + "\n  ".join(modules))
    done = subprocess.run([sys.executable, "-m", "unittest", *modules], cwd=REPO_ROOT)
    return done.returncode


if __name__ == "__main__":
    raise SystemExit(main())
