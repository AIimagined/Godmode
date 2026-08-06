"""Enumerate the work before reasoning about it, so nothing can be silently skipped.

Given a large change, agents cover part of it and report as though they covered
all of it. The omission is invisible because nothing ever stated what the whole
was. Deciding the scope deterministically first removes the possibility: every
changed artefact is either in a unit of work or filtered out with a stated reason,
and the two sets must account for everything.

Artefacts that can only be judged together are bundled into one unit. A rule about
keeping two files consistent cannot be evaluated from either file alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .godmode_anchor import run_git
from .godmode_charter import traits_of

# Reasons an artefact is out of scope. Each is a statement about the artefact, not
# a budget decision - work is never dropped merely because there is a lot of it.
FILTERS: tuple[tuple[str, str, str], ...] = (
    ("generated", r"(^|/)(dist|build|out|target|coverage|__pycache__|node_modules|vendor)/|\.min\.",
     "generated or vendored output; the source is the thing to review"),
    ("lockfile", r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|uv\.lock|go\.sum)$",
     "lockfile; verify the manifest change instead"),
    ("binary", r"\.(png|jpe?g|gif|webp|ico|svg|pdf|zip|gz|tar|woff2?|ttf|eot|mp4|mp3|wav|bin|exe|dll|so|dylib)$",
     "binary asset; not reviewable as text"),
    ("snapshot", r"(^|/)__snapshots__/|\.snap$",
     "generated snapshot; changes follow from the code under test"),
)

# Suffix families whose members are edited together and must be judged together.
_SIBLING_SUFFIXES = (
    (".ts", ".test.ts"), (".tsx", ".test.tsx"), (".js", ".test.js"),
    (".py", "_test.py"), (".go", "_test.go"),
)
_LOCALE = re.compile(r"^(?P<stem>.+?)[._-](?:[a-z]{2}(?:[-_][A-Za-z]{2})?)(?P<ext>\.[A-Za-z0-9]+)$")


@dataclass(frozen=True)
class Unit:
    """One reviewable unit: artefacts that must be judged together."""

    key: str
    paths: tuple[str, ...]
    traits: tuple[str, ...]
    reason: str

    def view(self) -> dict[str, Any]:
        return {"key": self.key, "paths": list(self.paths),
                "traits": list(self.traits), "bundled_because": self.reason}


def changed_paths(project: Path, since: str | None = None) -> tuple[list[str], str]:
    """Artefacts changed against a ref, or the current working tree."""
    if since:
        raw = run_git(project, "diff", "--name-only", f"{since}...HEAD")
        source = f"diff against {since}"
        if raw is None:
            raw = run_git(project, "diff", "--name-only", since)
            source = f"diff against {since}"
    else:
        tracked = run_git(project, "diff", "--name-only", "HEAD")
        untracked = run_git(project, "ls-files", "--others", "--exclude-standard")
        # Coercing a failed command to an empty string would report "nothing
        # changed" where the truth is "cannot be determined" - an empty result is a
        # claim about the tool, not about the project, until the tool succeeded.
        if tracked is None and untracked is None:
            raw = None
        else:
            raw = "\n".join(part for part in (tracked or "", untracked or "") if part)
        source = "working tree"
    if raw is None:
        return [], "unavailable: not a Git repository or ref not found"
    paths = sorted({line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip()})
    return paths, source


def _filter_reason(path: str) -> tuple[str, str] | None:
    lowered = path.lower()
    for name, pattern, why in FILTERS:
        if re.search(pattern, lowered):
            return name, why
    return None


def _bundle_key(path: str) -> tuple[str, str]:
    """Group artefacts that must be judged together, and say why."""
    name = path.rsplit("/", 1)[-1]
    directory = path.rsplit("/", 1)[0] if "/" in path else ""

    locale = _LOCALE.match(name)
    if locale:
        return f"{directory}/{locale.group('stem')}{locale.group('ext')}", "localized variants of one resource"

    for base, test in _SIBLING_SUFFIXES:
        if name.endswith(test):
            return f"{directory}/{name[: -len(test)]}{base}", "implementation and its test"
        if name.endswith(base) and not name.endswith(test):
            return f"{directory}/{name}", "implementation and its test"

    return path, "single artefact"


def scope(project: Path, since: str | None = None) -> dict[str, Any]:
    """Decide what is in scope before any reasoning begins.

    Completeness is the contract: every changed artefact appears exactly once,
    either inside a unit or in the filtered list with a reason. An agent cannot
    silently skip what has already been enumerated.
    """
    paths, source = changed_paths(project, since)
    filtered: list[dict[str, str]] = []
    grouped: dict[str, list[str]] = {}
    reasons: dict[str, str] = {}

    for path in paths:
        excluded = _filter_reason(path)
        if excluded:
            filtered.append({"path": path, "filter": excluded[0], "why": excluded[1]})
            continue
        key, why = _bundle_key(path)
        grouped.setdefault(key, []).append(path)
        reasons[key] = why

    units: list[Unit] = []
    for key in sorted(grouped):
        members = sorted(grouped[key])
        traits: set[str] = set()
        for member in members:
            traits.update(traits_of(member))
        why = reasons[key] if len(members) > 1 else "single artefact"
        units.append(Unit(key=key, paths=tuple(members), traits=tuple(sorted(traits)), reason=why))

    accounted = sum(len(unit.paths) for unit in units) + len(filtered)
    return {
        "source": source,
        "changed": len(paths),
        "units": [unit.view() for unit in units],
        "unit_count": len(units),
        "filtered": filtered,
        "accounted_for": accounted,
        # If this is ever false the enumeration lost something, which is the exact
        # failure the command exists to prevent - so it is asserted, not assumed.
        "complete": accounted == len(paths),
    }


# Thresholds for size pressure. They mark where review quality measurably drops,
# not where work becomes wrong - which is why crossing one reports and never blocks.
_PRESSURE_UNIT_LINES = 400
_PRESSURE_FILE_LINES = 200
_PRESSURE_NEW_FILES = 5


def _line_count(target: Path) -> int:
    try:
        return len(target.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def minimality(project: Path, base: str = "HEAD") -> dict[str, Any]:
    """Measure the change's size and name what is bigger than it needs to be.

    Size is a smell, not a sin: a large diff is sometimes the honest shape of the
    work, so nothing here blocks. But reviewers systematically under-read what
    they cannot hold in view, and the author is the one person who cannot feel
    that from inside - so the numbers are always in the report, findings or not,
    and the pressure findings name concrete artefacts rather than scolding.
    """
    numstat = run_git(project, "diff", "--numstat", base)
    created = run_git(project, "diff", "--name-only", "--diff-filter=A", base)
    untracked = run_git(project, "ls-files", "--others", "--exclude-standard")
    if numstat is None and untracked is None:
        return {"base": base, "source": "unavailable: not a Git repository or ref not found",
                "files": 0, "added_lines": 0, "largest": None, "new_files": [],
                "findings": [], "verdict": "unavailable"}

    per_file: dict[str, int] = {}
    for line in (numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":  # "-" marks a binary file
            continue
        per_file[parts[2].strip().replace("\\", "/")] = int(parts[0])

    new_files = {p.strip().replace("\\", "/") for p in (created or "").splitlines() if p.strip()}
    for raw in (untracked or "").splitlines():
        rel = raw.strip().replace("\\", "/")
        if not rel:
            continue
        # Untracked files are part of the change unit even before "git add": every
        # line of a new file is an added line the review has to carry.
        per_file[rel] = _line_count(project / rel)
        new_files.add(rel)

    total_added = sum(per_file.values())
    largest = max(per_file.items(), key=lambda item: item[1], default=None)

    findings: list[dict[str, str]] = []
    if total_added > _PRESSURE_UNIT_LINES:
        findings.append({"kind": "large-change",
                         "detail": f"consider splitting: {total_added} lines across "
                                   f"{len(per_file)} files"})
    if len(new_files) > _PRESSURE_NEW_FILES:
        findings.append({"kind": "many-new-files",
                         "detail": f"{len(new_files)} new files: " + ", ".join(sorted(new_files))})
    for path in sorted(per_file):
        if per_file[path] > _PRESSURE_FILE_LINES:
            findings.append({"kind": "large-file-addition",
                             "detail": f"{path}: {per_file[path]} added lines"})

    return {
        "base": base,
        "source": f"diff --numstat against {base}, plus untracked files",
        "files": len(per_file),
        "added_lines": total_added,
        "largest": ({"path": largest[0], "added_lines": largest[1]} if largest else None),
        "new_files": sorted(new_files),
        "findings": findings,
        "verdict": "pressure" if findings else "within-pressure",
    }


def _self_check() -> None:
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "src").mkdir()
        (project / "dist").mkdir()
        (project / "locales").mkdir()

        def write(rel: str, body: str = "x\n") -> None:
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")

        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True, timeout=30)
        write("README.md", "seed\n")
        subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True, timeout=30)
        subprocess.run(["git", "-C", str(project), "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "seed"], check=True, capture_output=True, timeout=30)

        write("src/auth.ts")
        write("src/auth.test.ts")
        write("locales/message_en.json")
        write("locales/message_zh.json")
        write("dist/bundle.js")
        write("package-lock.json")
        write("logo.png")

        report = scope(project)
        assert report["complete"], report
        assert report["changed"] == 7, report["changed"]

        keys = {unit["key"]: unit for unit in report["units"]}
        auth = next(u for u in report["units"] if "auth" in u["key"])
        assert set(auth["paths"]) == {"src/auth.ts", "src/auth.test.ts"}, auth
        assert auth["bundled_because"] == "implementation and its test", auth

        locale = next(u for u in report["units"] if "message" in u["key"])
        assert set(locale["paths"]) == {"locales/message_en.json", "locales/message_zh.json"}, locale
        assert locale["bundled_because"] == "localized variants of one resource", locale

        # Everything excluded says why, so a filter is never a silent omission.
        filtered = {f["path"]: f["filter"] for f in report["filtered"]}
        assert filtered["dist/bundle.js"] == "generated", filtered
        assert filtered["package-lock.json"] == "lockfile", filtered
        assert filtered["logo.png"] == "binary", filtered
        assert all(entry["why"] for entry in report["filtered"]), report["filtered"]

        # Traits carry through, so rule narrowing applies to a whole unit.
        assert "test" in auth["traits"], auth

        # A non-Git directory reports that plainly rather than claiming nothing changed.
        with tempfile.TemporaryDirectory() as bare:
            empty = scope(Path(bare))
            assert empty["changed"] == 0
            assert "unavailable" in empty["source"], empty

    print("godmode_scope self-check OK")


if __name__ == "__main__":
    _self_check()
