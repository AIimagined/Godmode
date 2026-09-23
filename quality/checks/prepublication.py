"""Check: the tree is ready to be made public, by this project's own rules.

One command that runs every surface rule at once, so "is this safe to publish"
is a check with an exit code rather than a judgement made per file, by memory,
under time pressure. Written after a release put documents on a public remote
that the project's rules did not allow there, and after the same rules were
re-stated several times because nothing enforced them.

What a project considers publishable is its own decision. This check reads that
decision from configuration and enforces it; it takes no position of its own.

Four classes, each failing separately so the report says which rule broke:

- `deny-name`   a name from the project's runtime-supplied list. Delegated to
  the surface-name check, including its forge-URL class.
- `citation`    a marker of external scholarship - a preprint identifier or an
  author-and-others form - in a shipped document.
- `untracked-class` a path class the project declared unpublishable that is
  nonetheless tracked.
- `link-rot`    a shipped document linking to a path that is no longer tracked,
  which is what removing a file without fixing its inbound links produces.

The list of unpublishable path classes lives in `quality/publication.json`
beside this check, because a path prefix is not sensitive - the names inside
those paths are, and those stay outside the repository.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "quality" / "publication.json"

#: Markers of external scholarship. Deliberately narrow: a preprint identifier
#: and the author-and-others form are unambiguous, where a bare word like
#: "paper" or "study" appears in ordinary prose and would make this noise.
_CITATION = re.compile(r"(?i)\barxiv[:\s/]|\bet\s+al\.")

_DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
_LINK = re.compile(r"\]\((?!https?://|#)([^)]+)\)")

#: The untracked working-documents archive, the one tree outside publication.
#: Named once here so its tests import it rather than restating the path.
UNPUBLISHED_PREFIX = "docs/superpowers/"


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=str(ROOT),
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise SystemExit(f"git ls-files failed: {out.stderr.strip()}")
    return [line for line in out.stdout.splitlines() if line]


def load_policy() -> dict:
    if not POLICY.exists():
        return {"unpublishable_prefixes": [], "citation_exempt": []}
    return json.loads(POLICY.read_text(encoding="utf-8"))


def citation_findings(tracked: list[str], policy: dict) -> list[str]:
    exempt = set(policy.get("citation_exempt", []))
    out: list[str] = []
    for rel in tracked:
        if rel in exempt or Path(rel).suffix.lower() not in _DOC_SUFFIXES:
            continue
        # Tests ship to every reader, so a citation there is a finding too; only
        # the untracked working-documents archive is outside the published tree.
        if rel.startswith(UNPUBLISHED_PREFIX):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if _CITATION.search(line):
                out.append(f"{rel}:{number}: names external scholarship")
    return out


def unpublishable_findings(tracked: list[str], policy: dict) -> list[str]:
    prefixes = policy.get("unpublishable_prefixes", [])
    return [
        f"{rel}: tracked, but '{prefix}' is declared unpublishable"
        for rel in tracked
        for prefix in prefixes
        if rel.startswith(prefix)
    ]


def link_findings(tracked: list[str]) -> list[str]:
    known = set(tracked)
    out: list[str] = []
    for rel in tracked:
        if Path(rel).suffix.lower() not in _DOC_SUFFIXES:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        base = Path(rel).parent
        for number, line in enumerate(text.splitlines(), 1):
            for target in _LINK.findall(line):
                target = target.split("#", 1)[0].strip()
                if not target or target.startswith(("mailto:", "/")):
                    continue
                # Resolve against the document's directory, then back to a
                # repo-relative path. The first cut normalised the string
                # instead of the path, so `../X` from `.github/` became
                # `.github/.X` and reported a dangling link to a file that was
                # tracked and present - the check, not the repository.
                try:
                    absolute = (ROOT / base / target).resolve()
                    resolved = absolute.relative_to(ROOT.resolve()).as_posix()
                except (ValueError, OSError):
                    continue
                if resolved not in known and not (ROOT / resolved).exists():
                    out.append(f"{rel}:{number}: links to a path that is not tracked: {resolved}")
    return out


def surface_name_findings() -> list[str]:
    """Delegated, so there is one implementation of that rule rather than two."""
    sys.path.insert(0, str(ROOT / "quality" / "checks"))
    import no_external_source_names as N

    names = N._deny_from_env()
    findings = N.scan(ROOT, N.shipped_paths(ROOT), names)
    verdict = N.report(names, findings)
    out = [str(f) for f in findings]
    messages = N.scan_messages(ROOT, names)
    if messages is None:
        out.append(f"commit messages: UNMEASURED - {N.PUSH_BASE} is not a known ref, "
                   "so the unpushed messages were not read.")
    else:
        out += [str(f) for f in messages]
    if verdict["deny_class"] == "unmeasured":
        out.append("deny-name: UNMEASURED - no list supplied, so this class "
                   "checked nothing. Set GODMODE_DENY_NAMES or place "
                   "deny-names.txt in the Godmode state home to measure it.")
    return out


def main() -> int:
    policy = load_policy()
    tracked = _tracked()

    groups = {
        "deny-name / forge-url": surface_name_findings(),
        "citation": citation_findings(tracked, policy),
        "unpublishable-class": unpublishable_findings(tracked, policy),
        "link-rot": link_findings(tracked),
    }

    print(f"prepublication check over {len(tracked)} tracked files")
    failed = False
    for label, findings in groups.items():
        if findings:
            failed = True
            print(f"  {label}: {len(findings)} finding(s)")
            for finding in findings[:10]:
                print(f"    FAIL: {finding}", file=sys.stderr)
        else:
            print(f"  {label}: clean")

    if failed:
        print("\nnot ready to publish", file=sys.stderr)
        return 1
    print("\nready to publish by the declared policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
