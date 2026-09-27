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
- In `tests/` the forge-URL class is not reported, because fixtures there test
  forge-URL detection. Deny-listed names are still reported there.

Commit messages are a shipped surface too: a push publishes every message in
the pushed range. `scan_messages` reads the unpushed range (`PUSH_BASE..HEAD`)
with the same two classes plus `private-path`, a path into the private working
tree. `--message-file` scans one message, for a local commit-msg hook. Until
0.3.28 no check read messages at all, so a report path pasted into a commit
body passed every check that existed.

R10 (2026-09-23): `--filter {added,file,all}` (default `added`) and
`--fail-level {harm,error,warning}` (default `harm`) - see `_change_scope`
beside this file. A finding whose kind is not classified `harm` here is
`warning`, never below it, so `--fail-level warning` at `--filter all`
reproduces this check's old, unconditional behaviour exactly (CI's own
default). The allowlist is keyed by path and the exact line text, not path
and line number, so an unrelated edit that moves a line cannot break an
accepted entry; the previous path:line-keyed form (`accepted` as an object)
is still read, for one release, matched the old way.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import _change_scope as scope  # noqa: E402

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


def _private_docs_prefix() -> str:
    """The untracked working-documents archive's path, read from
    `quality/publication.json`'s `unpublishable_prefixes` (first entry) -
    the same policy file `prepublication.py` reads it from - rather than
    duplicated here as a literal (follow-up to R10, 2026-09-25). Empty when
    the policy file is missing or declares nothing, never a guess."""
    import json

    policy_path = ROOT / "quality" / "publication.json"
    if not policy_path.exists():
        return ""
    try:
        data = json.loads(policy_path.read_text(encoding="utf-8"))
    except ValueError:
        return ""
    prefixes = data.get("unpublishable_prefixes", [])
    return prefixes[0] if prefixes else ""


#: Paths excluded from scanning, each with the reason it is excluded. Built
#: from `_private_docs_prefix()`, not a literal dict key, so an empty
#: (unresolved) prefix never becomes a `startswith("")` that matches every
#: path.
_EXCLUDED_PREFIXES = {
    prefix: "working specs and plans; checked separately and never published"
    for prefix in (_private_docs_prefix(),) if prefix
}

#: Paths where forge-URL findings are expected, each with the reason. The
#: exemption covers that one class only: deny-listed names are still reported
#: here, because tests ship to every reader of the repository. (Until 0.3.28
#: tests/ was skipped wholesale on this reason, which let two outside names
#: ship in a test file while the check read clean.)
_FORGE_URL_EXEMPT_PREFIXES = {
    "tests/": "fixtures legitimately carry sample forge URLs to test forge-URL detection",
}

ALLOWLIST_PATH = ROOT / "quality" / "external-name-allowlist.json"
_ALLOWLIST_REL = "quality/external-name-allowlist.json"

#: The allowlist's own path is exempt from the deny-name class only (R10):
#: a path+text entry quotes the exact accepted line, which for a path-prefix
#: entry naming the private working-docs tree or a well-known agent-config
#: filename is the same text the deny list flags - scanning the allowlist
#: for the very fragments it exists to record an exception for is circular,
#: not a leak. forge-url is unaffected; this is the only deny-name exemption
#: outside the deny list's own supply.
_DENY_NAME_EXEMPT_PATHS = {_ALLOWLIST_REL}

#: The published branch. Messages above it are what the next push publishes.
PUSH_BASE = "origin/main"

#: A path into the private working tree: a subagent report directory or the
#: private state folder. It is fine inside the tree, which never ships, but a
#: message that names one publishes it. The private tree's own folder name is
#: on the deny list, so the deny-name class covers it and it is not spelled here.
_PRIVATE_PATH = re.compile(r"[\w./-]*(?:\bsdd/|\.godmode-private/)[^\s`'\")]*", re.IGNORECASE)


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


@dataclass(frozen=True)
class Allowlist:
    """Accepted references. `by_text` is the current form, keyed by
    `(path, exact line text)` - a line moving does not break the entry.
    `by_line` is the previous form, keyed by `path:line`; still read for one
    release (R10, 2026-09-23) so an unmigrated entry is not silently
    dropped, matched the old way.
    """
    by_text: dict[tuple[str, str], str]
    by_line: dict[str, str]

    def __len__(self) -> int:
        return len(self.by_text) + len(self.by_line)

    def accepts(self, path: str, line: int, text: str) -> bool:
        return (path, text.strip()) in self.by_text or f"{path}:{line}" in self.by_line


def load_allowlist() -> Allowlist:
    """Accepted references: an entry here is a recorded decision, not a
    suppression - the reason travels with it and a reviewer can see what was
    accepted and why.
    """
    if not ALLOWLIST_PATH.exists():
        return Allowlist({}, {})
    import json

    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    accepted = data.get("accepted", [])
    if isinstance(accepted, dict):
        # v1 (path:line -> reason): the whole file predates the migration,
        # or was hand-edited back to it. Read it as-is; nothing here writes
        # this shape again.
        return Allowlist({}, {str(k): str(v) for k, v in accepted.items()})
    by_text: dict[tuple[str, str], str] = {}
    for entry in accepted if isinstance(accepted, list) else []:
        if not isinstance(entry, dict):
            continue
        path, text = str(entry.get("path", "")), str(entry.get("text", ""))
        if path and text:
            by_text[(path, text)] = str(entry.get("reason", ""))
    return Allowlist(by_text, {})


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

        forge_exempt = any(rel.startswith(p) for p in _FORGE_URL_EXEMPT_PREFIXES)
        deny_exempt = rel in _DENY_NAME_EXEMPT_PATHS
        for number, line in enumerate(text.splitlines(), start=1):
            if allow.accepts(rel, number, line):
                continue

            for match in ([] if forge_exempt else _FORGE.finditer(line)):
                if match.group("owner").lower() in SELF_OWNERS:
                    continue
                findings.append(Finding(
                    path=rel, line=number, kind="forge-url", matched=match.group(0),
                    remedy=(
                        "Describe the mechanism instead of linking its source. If the "
                        "reference is a formal citation that must be kept, add "
                        "{\"path\": \"" + rel + "\", \"text\": <the exact line, trimmed>, "
                        "\"reason\": ...} to quality/external-name-allowlist.json."
                    ),
                ))

            if deny is not None and not deny_exempt:
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


def _deny_list_path() -> Path | None:
    """Where the deny-names file lives, honouring the env var and then the
    private per-user state home.

    `GODMODE_DENY_NAMES` (an explicit path) always wins when set. Absent
    that, the list falls back to `deny-names.txt` in Godmode's own state
    home (`application_home()` in `scripts/godmode_runtime/godmode_anchor.py`)
    so the class can be measured without exporting a variable in every
    shell. The list itself never lives inside this repository - only the
    lookup for where to find it does.
    """
    raw = os.environ.get("GODMODE_DENY_NAMES")
    if raw:
        path = Path(raw)
        return path if path.exists() else None

    try:
        scripts_dir = ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from godmode_runtime.godmode_anchor import application_home
    except Exception:  # godmode: swallow-ok: import failure keeps prior UNMEASURED behaviour
        return None

    try:
        home_path = application_home() / "deny-names.txt"
    except Exception:  # godmode: swallow-ok: resolution failure keeps prior UNMEASURED behaviour
        return None
    return home_path if home_path.exists() else None


def _deny_from_env() -> list[str] | None:
    path = _deny_list_path()
    if path is None:
        return None
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


#: Internal-process wording in a commit message: review rounds, reviewers,
#: model names, private ledger rows, citations of outside scholarship. A push
#: publishes the message, and these describe how the work was made, not what
#: changed (2026-09-23: "the opus review's seven blocking findings" and "the
#: private R-1 ledger rows" reached the public sprint branch).
_INTERNAL_PROCESS = re.compile(
    r"(?i)\b(?:opus|sonnet|fable)\b|\bfix[- ]round\b|\breview(?:er'?s?)? rounds?\b"
    r"|\breviewer'?s?\b|\bnits\b|\bledger:\d|\bprivate\b[^.\n]{0,40}\bledger\b"
    r"|\bpreprint\b|\barxiv\b|\bet al\.|\boutside paper\b")


def scan_message(label: str, message: str, deny_names: list[str] | None) -> list[Finding]:
    """Every private reference in one commit message."""
    deny = _deny_pattern(deny_names) if deny_names else None
    findings: list[Finding] = []
    remedy = ("Reword the message by what changed. A message is published with the "
              "push, so it may not cite private paths, reports, or deny-listed names.")
    for number, line in enumerate(message.splitlines(), start=1):
        hits = [("private-path", m.group(0)) for m in _PRIVATE_PATH.finditer(line)]
        hits += [("internal-process", m.group(0)) for m in _INTERNAL_PROCESS.finditer(line)]
        hits += [("forge-url", m.group(0)) for m in _FORGE.finditer(line)
                 if m.group("owner").lower() not in SELF_OWNERS]
        if deny is not None:
            hits += [("deny-name", m.group(0)) for m in deny.finditer(line)]
        findings += [Finding(path=label, line=number, kind=kind, matched=text, remedy=remedy)
                     for kind, text in hits]
    return findings


def scan_messages(root: Path, deny_names: list[str] | None,
                  base: str = PUSH_BASE) -> list[Finding] | None:
    """Findings across every unpushed commit message; None when `base` is unknown."""
    known = subprocess.run(["git", "rev-parse", "--verify", "--quiet", base],
                           cwd=str(root), capture_output=True, text=True, timeout=30)
    if known.returncode != 0:
        return None
    out = subprocess.run(["git", "log", "--format=%h%x00%B%x1e", f"{base}..HEAD"],
                         cwd=str(root), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=120)
    if out.returncode != 0:
        raise SystemExit(f"git log failed: {out.stderr.strip()}")
    findings: list[Finding] = []
    for record in out.stdout.split("\x1e"):
        sha, _, body = record.strip("\n").partition("\x00")
        if sha:
            findings += scan_message(f"commit {sha}", body, deny_names)
    return findings


#: Severity per finding kind (R10). Most of this check's own kinds ARE the
#: harm class it exists to catch - secrets, private names leaving the
#: machine, release/publish safety - so `harm` is the majority, not a rare
#: escalation. `internal-process` (how the work was made, not what changed)
#: is process hygiene, not a leak of identity or secrecy.
_CLASS_LEVEL = {
    "forge-url": "harm",
    "deny-name": "harm",
    "private-path": "harm",
    "internal-process": "warning",
}


def classify(kind: str) -> str:
    """The fail level a finding's kind carries; unclassified kinds default
    to `warning`, never below it - nothing here is exempt from CI's
    `--fail-level warning --filter all`."""
    return _CLASS_LEVEL.get(kind, "warning")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    scope.add_scope_args(parser)
    parser.add_argument("--message-file", type=Path, default=None,
                        help="scan one commit message instead of the tree "
                             "(a local commit-msg hook); always treated as "
                             "in-scope - a message is inherently new")
    return parser.parse_args(argv)


def _report_finding(finding: Finding, *, pre_existing: bool, fail_level: str) -> bool:
    """Print one finding and return whether it fails the run."""
    level = classify(finding.kind)
    fails = scope.blocks(level, fail_level) and not pre_existing
    tag = "FAIL" if fails else ("pre-existing" if pre_existing else "info")
    print(f"{tag}: {finding}  [{level}]", file=sys.stderr)
    print(f"      {finding.remedy}", file=sys.stderr)
    return fails


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    deny_names = _deny_from_env()

    if args.message_file:
        found = scan_message(
            "message", args.message_file.read_text(encoding="utf-8", errors="replace"),
            deny_names)
        # A commit message is inherently new content - there is no "line
        # this change did not touch" concept for it, so it is never
        # pre-existing regardless of --filter.
        blocking = [f for f in found if _report_finding(f, pre_existing=False,
                                                          fail_level=args.fail_level)]
        return 1 if blocking else 0

    filt, added = scope.resolve(ROOT, args.filter, args.base)
    paths = shipped_paths(ROOT)
    findings = scan(ROOT, paths, deny_names)
    verdict = report(deny_names, findings)

    print(f"scanned {len(paths)} shipped surfaces")
    print(f"  forge-url   {verdict['forge_class']}")
    print(f"  deny-name {verdict['deny_class']}"
          + ("" if deny_names else "  (set GODMODE_DENY_NAMES to a names file to measure)"))

    messages = scan_messages(ROOT, deny_names)
    if messages is None:
        print(f"  messages    unmeasured  ({PUSH_BASE} is not a known ref)")
    else:
        print(f"  messages    {'findings' if messages else 'clean'}  ({PUSH_BASE}..HEAD)")

    accepted = load_allowlist()
    if len(accepted):
        print(f"  {len(accepted)} accepted reference(s) recorded in the allowlist")
    print(f"  filter={filt} fail-level={args.fail_level}"
          + ("" if filt == args.filter else f" (requested {args.filter}; no diff to measure it, fell back to all)"))

    # Commit-message findings are always in scope (see above) - never
    # pre-existing, and the filter never trims them: an unpushed message is
    # entirely new by definition.
    tree_findings = [(f, scope.in_scope(f.path, f.line, filt, added),
                      filt != "all" and scope.pre_existing(f.path, f.line, added))
                     for f in findings]
    message_findings = [(f, True, False) for f in (messages or [])]

    shown = [(f, pre) for f, in_scope, pre in tree_findings + message_findings if in_scope]
    if shown:
        print()
    blocking = [_report_finding(f, pre_existing=pre, fail_level=args.fail_level)
                for f, pre in shown]
    return 1 if any(blocking) else 0


if __name__ == "__main__":
    raise SystemExit(main())
