"""Check: shipped surfaces carry no name a project has asked to keep out of them.

Whether a project publishes the names of things it read, referenced, learned
from, or depends on is the project's decision, not this tool's. Some projects
publish all of it; some publish none of it. This check enforces whatever the
project declared and takes no position of its own.

Two classes, failing differently:

- `forge-url`  a link to a code-hosting forge under an owner that is not this
  project's own. Structural, so it runs with no configuration.
- `deny-name`  a name the project supplied at runtime through
  GODMODE_DENY_NAMES, one per line. When no list is supplied the class reports
  `unmeasured`, never `clean` - an absent instrument is graded distinctly from
  a negative result (R8). A project that wants nothing hidden simply supplies
  no list and the class stays quiet.

The list lives outside the repository by design: its contents are the thing it
protects, so committing it would publish exactly what it exists to withhold.

Deliberate limits, stated so they are not mistaken for coverage:

- A bare `owner/repo` pair in prose is not matched. A regex for it fires on
  every relative path in the tree, and a guard that cries wolf gets disabled.
  The supplied list is what catches those, when one is supplied.
- `tests/` is not scanned. Fixtures there legitimately carry sample forge URLs
  because some of them test forge-URL detection. The cost is that a real leak
  inside a test body is invisible here.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Forge hosts. A link to a language's documentation or a standards body is not
#: a source identity, so only code-hosting forges are matched.
_FORGE = re.compile(
    r"https?://(?:www\.)?(?:github|gitlab|bitbucket|codeberg|sourcehut|git\.sr\.ht)\.(?:com|org|ht)/"
    r"(?P<owner>[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)

#: Our own account. A self-reference is not an outside identity.
SELF_OWNERS = {"aiimagined"}

#: Text extensions worth reading. A binary or a lockfile is not a surface.
_TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".cfg",
    ".ini", ".sh", ".cmd", ".ps1", ".js", ".ts", ".mjs",
}

#: Paths excluded from scanning, each with the reason it is excluded.
_EXCLUDED_PREFIXES = {
    "tests/": "fixtures legitimately carry sample forge URLs to test forge-URL detection",
    "docs/superpowers/": "working specs and plans; checked separately and never published",
}

ALLOWLIST_PATH = ROOT / "quality" / "external-name-allowlist.json"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    matched: str
    remedy: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.path}:{self.line}: {self.kind}: {self.matched}"


def _tracked(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=str(root), capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise SystemExit(f"git ls-files failed: {out.stderr.strip()}")
    return [root / line for line in out.stdout.splitlines() if line]


def shipped_paths(root: Path) -> list[Path]:
    """Tracked text files that reach a reader, minus the documented exclusions."""
    kept: list[Path] = []
    for path in _tracked(root):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if path.name.endswith(".lock") or path.name == "uv.lock":
            continue
        kept.append(path)
    return kept


def load_allowlist() -> dict[str, str]:
    """Accepted references, mapping `path:line` to the reason it is accepted.

    An entry here is a recorded decision, not a suppression: the reason travels
    with it and a reviewer can see what was accepted and why.
    """
    if not ALLOWLIST_PATH.exists():
        return {}
    import json

    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return dict(data.get("accepted", {}))


def _deny_pattern(names: list[str]) -> re.Pattern[str] | None:
    cleaned = [re.escape(n.strip()) for n in names if n.strip()]
    if not cleaned:
        return None
    # Word boundaries so `roma` does not fire on `aromatic`.
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(cleaned) + r")(?![A-Za-z0-9])", re.IGNORECASE)


def scan(root: Path, paths: list[Path], deny_names: list[str] | None) -> list[Finding]:
    """Every outside-project identity in `paths`, as findings carrying a remedy."""
    deny = _deny_pattern(deny_names) if deny_names else None
    allow = load_allowlist()
    findings: list[Finding] = []

    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()

        for number, line in enumerate(text.splitlines(), start=1):
            if f"{rel}:{number}" in allow:
                continue

            for match in _FORGE.finditer(line):
                if match.group("owner").lower() in SELF_OWNERS:
                    continue
                findings.append(Finding(
                    path=rel, line=number, kind="forge-url", matched=match.group(0),
                    remedy=(
                        "Describe the mechanism instead of linking its source. If the "
                        "reference is a formal citation that must be kept, add "
                        f"\"{rel}:{number}\" to quality/external-name-allowlist.json "
                        "with the reason."
                    ),
                ))

            if deny is not None:
                found = deny.search(line)
                if found:
                    findings.append(Finding(
                        path=rel, line=number, kind="deny-name", matched=found.group(0),
                        remedy=(
                            "This name is on the project's deny list for shipped "
                            "surfaces. Restate the item by what it does."
                        ),
                    ))
    return findings


def report(deny_names: list[str] | None, findings: list[Finding]) -> dict[str, str]:
    """Per-class verdict. An unsupplied list is `unmeasured`, never `clean`."""
    forge = [f for f in findings if f.kind == "forge-url"]
    denied = [f for f in findings if f.kind == "deny-name"]
    return {
        "forge_class": "findings" if forge else "clean",
        "deny_class": (
            "unmeasured" if not deny_names else ("findings" if denied else "clean")
        ),
    }


def _deny_from_env() -> list[str] | None:
    raw = os.environ.get("GODMODE_DENY_NAMES")
    if not raw:
        return None
    path = Path(raw)
    if not path.exists():
        return None
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def main() -> int:
    deny_names = _deny_from_env()
    paths = shipped_paths(ROOT)
    findings = scan(ROOT, paths, deny_names)
    verdict = report(deny_names, findings)

    print(f"scanned {len(paths)} shipped surfaces")
    print(f"  forge-url   {verdict['forge_class']}")
    print(f"  deny-name {verdict['deny_class']}"
          + ("" if deny_names else "  (set GODMODE_DENY_NAMES to a names file to measure)"))

    accepted = load_allowlist()
    if accepted:
        print(f"  {len(accepted)} accepted reference(s) recorded in the allowlist")

    if findings:
        print()
        for finding in findings:
            print(f"FAIL: {finding}", file=sys.stderr)
            print(f"      {finding.remedy}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
