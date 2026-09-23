#!/usr/bin/env python3
"""G-5: classify every gate-corpus row at two commits and report decision flips.

    python scripts/dev/corpus_differential.py --base <sha> [--head <sha>] [--json out.json]

A change to the classifier is judged by what it does to real commands, not by
whether its own new tests pass. This script takes the corpus
(`tests/fixtures/gate_corpus.json`, read from the working tree unless
`--corpus` names another file) and classifies every row twice: once with the
runtime as it was at `--base`, once as it is at `--head` (default: the
working tree, so an uncommitted change can be checked before it lands).

Each commit's runtime is materialised with `git show <sha>:<path>` into a
throwaway directory - no worktree, no checkout, nothing in the repository
touched - and run in its own interpreter, so the two versions never share an
import cache.

A row whose decision differs is a flip. A flip is explained when the row is
labelled `class: by-design` and carries a `note` saying why; any other flip
is unexplained and the script exits 1. Exit 0 means zero unexplained flips.
A row a runtime cannot classify at all (it raises) is reported as `error`,
which counts as a flip.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = "scripts/godmode_runtime"
DEFAULT_CORPUS = REPO_ROOT / "tests" / "fixtures" / "gate_corpus.json"
WORKTREE = "WORKTREE"

# Runs inside the materialised runtime's own interpreter. Reads rows on
# stdin, writes one decision per row on stdout. A runtime from before tool
# names were accepted is called without one.
_CLASSIFY = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from godmode_runtime.godmode_sentinel import classify_action
root = Path(sys.argv[2])
rows = json.load(sys.stdin)
out = []
for row in rows:
    try:
        try:
            verdict = classify_action(row["operation"], project_root=root,
                                      tool_name=row.get("tool"))
        except TypeError:
            verdict = classify_action(row["operation"], project_root=root)
        if not verdict["protected"]:
            out.append("allow")
        else:
            out.append("refuse" if verdict["tier"] == "R5" else "ask")
    except Exception as exc:
        out.append("error: " + type(exc).__name__)
json.dump(out, sys.stdout)
"""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


def materialise(sha: str, into: Path) -> Path:
    """The runtime package as of `sha`, written under `into`. Returns the
    directory to put on `sys.path`."""
    package = into / "godmode_runtime"
    package.mkdir(parents=True)
    names = [name for name in _git("ls-tree", "--name-only", sha, f"{RUNTIME_DIR}/").split()
             if name.endswith(".py")]
    # One `git cat-file --batch` for every file: the same bytes `git show
    # <sha>:<path>` prints, without a process per file.
    request = "".join(f"{sha}:{name}\n" for name in names).encode("utf-8")
    stream = subprocess.run(["git", "cat-file", "--batch"], cwd=REPO_ROOT, input=request,
                            check=True, capture_output=True).stdout
    cursor = 0
    for name in names:
        header_end = stream.index(b"\n", cursor)
        header = stream[cursor:header_end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise RuntimeError(f"cannot read {sha}:{name}: {header!r}")
        size = int(header[2])
        start = header_end + 1
        (package / Path(name).name).write_bytes(stream[start:start + size])
        cursor = start + size + 1
    return into


def decisions(runtime_parent: Path, rows: list[dict]) -> list[str]:
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _CLASSIFY, str(runtime_parent), str(REPO_ROOT)],
        input=json.dumps(rows), capture_output=True, text=True, encoding="utf-8",
        check=False)
    if done.returncode != 0:
        raise RuntimeError(f"classification failed under {runtime_parent}:\n{done.stderr[-2000:]}")
    return json.loads(done.stdout)


def differential(base: str, head: str, rows: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(prefix="godmode-corpus-diff-") as scratch:
        base_dir = materialise(base, Path(scratch) / "base")
        head_dir = (REPO_ROOT / "scripts") if head == WORKTREE else materialise(
            head, Path(scratch) / "head")
        before = decisions(base_dir, rows)
        after = decisions(head_dir, rows)
    flips = []
    for row, old, new in zip(rows, before, after):
        if old == new:
            continue
        explained = row.get("class") == "by-design" and bool(row.get("note"))
        flips.append({"operation": row["operation"], "tool": row.get("tool"),
                      "base": old, "head": new, "expected": row.get("expected"),
                      "explained": explained, "note": row.get("note")})
    return {"base": base, "head": head, "rows": len(rows), "flips": flips,
            "unexplained": sum(1 for flip in flips if not flip["explained"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="commit to compare against")
    parser.add_argument("--head", default=WORKTREE,
                        help="commit to compare (default: the working tree)")
    parser.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--json", help="also write the full report here")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    rows = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    base = _git("rev-parse", "--verify", f"{args.base}^{{commit}}").strip()
    head = args.head if args.head == WORKTREE else _git(
        "rev-parse", "--verify", f"{args.head}^{{commit}}").strip()
    report = differential(base, head, rows)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"corpus differential {base[:12]} -> {head[:12]}: {report['rows']} rows, "
          f"{len(report['flips'])} flips, {report['unexplained']} unexplained")
    for flip in report["flips"]:
        mark = "explained" if flip["explained"] else "UNEXPLAINED"
        tool = f" [{flip['tool']}]" if flip["tool"] else ""
        print(f"  {mark}: {flip['base']} -> {flip['head']}{tool}: {flip['operation'][:100]}")
        if flip["note"]:
            print(f"      note: {flip['note']}")
    return 1 if report["unexplained"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
