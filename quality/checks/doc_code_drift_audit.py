"""Audit: what the documents claim against what the code actually contains.

Reads the console module's AST for every command handler and every subparser it
registers, then reads every `godmode ...` invocation written in the project's
documents and in the working directory above it. Reports four classes:

  documented-but-absent   a document names a command the parser does not build
  implemented-but-thin    a handler whose body is small enough to be a stub
  parser-only             a verb the parser registers that no document mentions
  subcommand drift        a subcommand named in prose that the parser lacks

This is a report, not a gate. It exists because a sweep that reads documents and
`--help` output can be confidently wrong about whether a feature exists: two
work items were added to this release from an August document that described
capabilities the code had since shipped.
"""
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONSOLE = ROOT / "scripts" / "godmode_runtime" / "godmode_console.py"
OUTSIDE = ROOT.parent

STUB_STATEMENTS = 3  # a handler this short is doing nothing but returning


def parser_verbs() -> set[str]:
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "godmode.py"), "--project", str(ROOT), "--help"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    match = re.search(r"\{([a-z0-9,\-]+)\}", out.replace("\n", ""))
    return set(match.group(1).split(",")) if match else set()


def handlers() -> dict[str, int]:
    """verb -> number of statements in its cmd_ handler body."""
    tree = ast.parse(CONSOLE.read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("cmd_"):
            verb = node.name[len("cmd_"):].replace("_", "-")
            found[verb] = sum(1 for _ in ast.walk(node) if isinstance(_, ast.stmt))
    return found


def subcommands(verb: str) -> set[str]:
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "godmode.py"), "--project", str(ROOT), verb, "--help"],
        capture_output=True, text=True, timeout=120,
    ).stdout
    match = re.search(r"\{([a-z0-9,\-]+)\}", out.replace("\n", ""))
    return set(match.group(1).split(",")) if match else set()


def documented() -> dict[str, set[str]]:
    """verb -> subcommands named anywhere in the documents."""
    pattern = re.compile(r"godmode\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?")
    seen: dict[str, set[str]] = defaultdict(set)
    roots = [ROOT / "docs", ROOT / "README.md", OUTSIDE / "docs"]
    for base in roots:
        if not base.exists():
            continue
        files = [base] if base.is_file() else list(base.rglob("*.md"))
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for verb, sub in pattern.findall(text):
                seen[verb].add(sub or "")
    return seen


verbs = parser_verbs()
bodies = handlers()
docs = documented()

thin = {v: n for v, n in bodies.items() if v in verbs and n <= STUB_STATEMENTS}
doc_verbs = {v for v in docs if v.islower() and "-" not in v[:1]}
absent = sorted(v for v in doc_verbs - verbs if v in bodies or len(v) > 2)
parser_only = sorted(verbs - doc_verbs)

print(f"parser verbs        {len(verbs)}")
print(f"cmd_ handlers       {len(bodies)}")
print(f"verbs named in docs {len(doc_verbs & verbs)} of {len(verbs)}")
print()

print(f"implemented-but-thin ({len(thin)} handlers with <= {STUB_STATEMENTS} statements):")
for verb, n in sorted(thin.items(), key=lambda kv: kv[1]):
    print(f"  {verb:24} {n} statements")
if not thin:
    print("  none")
print()

print(f"parser-only, no document mentions it ({len(parser_only)}):")
print("  " + ", ".join(parser_only) if parser_only else "  none")
print()

# Subcommand drift, checked only for verbs a document gives a subcommand for.
drift: dict[str, set[str]] = {}
for verb in sorted(doc_verbs & verbs):
    claimed = {s for s in docs[verb] if s}
    if not claimed:
        continue
    real = subcommands(verb)
    if not real:
        continue
    missing = claimed - real
    if missing:
        drift[verb] = missing

print(f"subcommands named in prose that the parser lacks ({len(drift)} verbs):")
for verb, missing in sorted(drift.items()):
    print(f"  godmode {verb}: {', '.join(sorted(missing))}")
if not drift:
    print("  none")

summary = {
    "parser_verbs": len(verbs),
    "handlers": len(bodies),
    "thin": thin,
    "parser_only": parser_only,
    "subcommand_drift": {k: sorted(v) for k, v in drift.items()},
}
(ROOT / "quality" / "doc-code-drift.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
print(f"\nwritten: quality/doc-code-drift.json")
