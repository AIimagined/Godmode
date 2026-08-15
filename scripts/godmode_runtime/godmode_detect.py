"""Charter bootstrap: propose starter rules from what a repo already proves.

A brand-new project sees an empty charter and has no idea what to write in it.
This module reads the repo's own evidence - manifests, CI workflow commands,
`.gitignore` build markers, a migrations directory, the default branch - and
turns each fact into one candidate rule line with its provenance attached.

Every detected rule is a guess about a project's own conventions, so it is
never allowed to arrive as a blocking gate: `soft_rule_text` is the only way
this module emits rule text, and it hard-refuses anything but SOFT. Promoting
a candidate to a binding rule stays a human decision made in the charter
document itself, never something detection performs on a project's behalf.

Pure reads only: no subprocess, no network, no writes except the one starter
document `init --detect` creates when none exists yet. The repo walk that
backs detection is capped so an enormous tree cannot turn `init --detect`
into an unbounded scan; the cap is always reported, never silently absorbed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tomllib
from typing import Any

from .godmode_corpus import DEFAULT_ROLES, resolve_roles
from .godmode_errors import GodmodeError

# The whole scan touches at most this many files. A repo with more than this
# many files still gets an answer - just an honestly partial one, and the
# cap is always reported alongside it.
FILE_CAP = 400

STARTER_FILENAME = DEFAULT_ROLES["operating-guide"][0]

# kind -> the descriptive half of its rule line. Data, not branching logic, so
# a new detection kind is one row here rather than a new code path.
RULE_TEMPLATES: dict[str, str] = {
    "test-command": "run tests with `{value}`",
    "lint-command": "run lint with `{value}`",
    "build-command": "run the build with `{value}`",
    "generated-dir": "treat `{value}` as generated output, never hand-edited",
    "migrations-dir": "route schema changes through `{value}`",
    "default-branch": "the default branch is `{value}`",
    "stack": "this project's stack includes {value}",
}


def soft_rule_text(detection: dict[str, Any], enforcement: str = "SOFT") -> str:
    """The only path that turns a Detection into rule text.

    Hard-refuses anything but SOFT: a wrong guess from detection must never
    become a blocking gate uninspected. Promotion is the operator's call,
    made by editing the charter document itself.
    """
    if enforcement != "SOFT":
        raise GodmodeError(
            "detected rules may only be emitted as SOFT; promoting one to a "
            "blocking rule is a human decision made in the charter document"
        )
    template = RULE_TEMPLATES[detection["kind"]]
    body = template.format(**detection)
    return f"- {body} (detected: {detection['source']}) [SOFT - detected, promote after review]"


def _detection(kind: str, value: str, source: str) -> dict[str, Any]:
    detection = {"kind": kind, "value": value, "source": source}
    detection["rule_text"] = soft_rule_text(detection)
    return detection


def _scan_files(project: Path) -> tuple[list[str], bool]:
    """Walk the tree once, capped, in a deterministic order.

    `.git` internals are excluded: they are runtime metadata, not project
    content, and the default-branch reader addresses `.git/HEAD` directly
    rather than counting it against the content budget.
    """
    found: list[str] = []
    capped = False
    for root, dirs, files in os.walk(project):
        dirs.sort()
        if ".git" in dirs:
            dirs.remove(".git")
        for name in sorted(files):
            if len(found) >= FILE_CAP:
                return found, True
            relative = Path(root, name).relative_to(project).as_posix()
            found.append(relative)
    return found, capped


def _detect_package_json(project: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads((project / "package.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out = [_detection("stack", "node", "package.json")]
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        if "test" in scripts:
            out.append(_detection("test-command", "npm test", "package.json scripts.test"))
        if "lint" in scripts:
            out.append(_detection("lint-command", "npm run lint", "package.json scripts.lint"))
        if "build" in scripts:
            out.append(_detection("build-command", "npm run build", "package.json scripts.build"))
    return out


def _detect_pyproject(project: Path) -> list[dict[str, Any]]:
    try:
        data = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return []
    out: list[dict[str, Any]] = []
    tool = data.get("tool")
    if isinstance(tool, dict):
        pytest_cfg = tool.get("pytest")
        if isinstance(pytest_cfg, dict):
            source = (
                "pyproject.toml tool.pytest.ini_options"
                if "ini_options" in pytest_cfg
                else "pyproject.toml tool.pytest"
            )
            out.append(_detection("test-command", "pytest", source))
        if isinstance(tool.get("ruff"), dict):
            out.append(_detection("lint-command", "ruff check .", "pyproject.toml tool.ruff"))
        if isinstance(tool.get("black"), dict):
            out.append(_detection("lint-command", "black --check .", "pyproject.toml tool.black"))
        if isinstance(tool.get("poetry"), dict):
            out.append(_detection("stack", "python", "pyproject.toml tool.poetry"))
    if isinstance(data.get("project"), dict) and not any(d["kind"] == "stack" for d in out):
        out.append(_detection("stack", "python", "pyproject.toml project"))
    return out


def _detect_gitignore(project: Path) -> list[dict[str, Any]]:
    try:
        text = (project / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if line.endswith("/"):
            out.append(_detection("generated-dir", line, ".gitignore"))
    return out


_MIGRATION_CANDIDATES = (
    "migrations",
    "db/migrate",
    "db/migrations",
    "alembic",
    "prisma/migrations",
)


def _detect_migrations(file_set: set[str]) -> list[dict[str, Any]]:
    out = []
    for candidate in _MIGRATION_CANDIDATES:
        prefix = f"{candidate}/"
        if any(name.startswith(prefix) for name in file_set):
            out.append(_detection("migrations-dir", prefix, f"{candidate} (directory present)"))
    return out


_CI_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("test-command", re.compile(r"\btest\b", re.IGNORECASE)),
    ("lint-command", re.compile(r"\blint\b", re.IGNORECASE)),
    ("build-command", re.compile(r"\bbuild\b", re.IGNORECASE)),
)
_RUN_LINE = re.compile(r"^\s*run:\s*(.+?)\s*$")


def _detect_ci(project: Path, file_set: set[str]) -> list[dict[str, Any]]:
    """Line-level `run:` extraction from workflow files. No YAML dependency:
    a full parse is not needed to read one key's scalar value off a line."""
    out = []
    workflow_files = sorted(
        name for name in file_set
        if name.startswith(".github/workflows/") and name.endswith((".yml", ".yaml"))
    )
    for relative in workflow_files:
        try:
            lines = (project / relative).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, raw in enumerate(lines, start=1):
            match = _RUN_LINE.match(raw)
            if not match:
                continue
            command = match.group(1).strip().strip("\"'")
            if not command:
                continue
            for kind, pattern in _CI_KEYWORDS:
                if pattern.search(command):
                    out.append(_detection(kind, command, f"{relative}:{lineno}"))
                    break
    return out


def _detect_default_branch(project: Path) -> list[dict[str, Any]]:
    try:
        text = (project / ".git" / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return []
    match = re.match(r"ref:\s*refs/heads/(.+)$", text)
    if not match:
        return []
    return [_detection("default-branch", match.group(1).strip(), ".git/HEAD")]


_LINT_CONFIG_FILES: dict[str, str] = {
    ".eslintrc": "eslint .",
    ".eslintrc.json": "eslint .",
    ".eslintrc.js": "eslint .",
    ".eslintrc.cjs": "eslint .",
    ".eslintrc.yml": "eslint .",
    ".eslintrc.yaml": "eslint .",
    ".flake8": "flake8",
    "ruff.toml": "ruff check .",
    ".ruff.toml": "ruff check .",
}


def _detect_lint_configs(file_set: set[str]) -> list[dict[str, Any]]:
    return [
        _detection("lint-command", command, name)
        for name, command in _LINT_CONFIG_FILES.items()
        if name in file_set
    ]


def _detect_go_and_rust(file_set: set[str]) -> list[dict[str, Any]]:
    out = []
    if "go.mod" in file_set:
        out.append(_detection("stack", "go", "go.mod"))
        out.append(_detection("test-command", "go test ./...", "go.mod"))
    if "Cargo.toml" in file_set:
        out.append(_detection("stack", "rust", "Cargo.toml"))
        out.append(_detection("test-command", "cargo test", "Cargo.toml"))
    return out


def detect_repo(project: Path, stats: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Scan a repo for evidence of its own conventions.

    Pure reads, capped at `FILE_CAP` files. When `stats` is given it is
    filled with `files_scanned` / `cap` / `capped` so a caller can report the
    cap honestly instead of letting a partial scan pass as a complete one.
    """
    project = Path(project)
    files, capped = _scan_files(project)
    file_set = set(files)
    if stats is not None:
        stats["files_scanned"] = len(files)
        stats["cap"] = FILE_CAP
        stats["capped"] = capped

    detections: list[dict[str, Any]] = []
    if "package.json" in file_set:
        detections.extend(_detect_package_json(project))
    if "pyproject.toml" in file_set:
        detections.extend(_detect_pyproject(project))
    detections.extend(_detect_go_and_rust(file_set))
    if ".gitignore" in file_set:
        detections.extend(_detect_gitignore(project))
    detections.extend(_detect_ci(project, file_set))
    detections.extend(_detect_migrations(file_set))
    detections.extend(_detect_default_branch(project))
    detections.extend(_detect_lint_configs(file_set))
    return detections


_STARTER_HEADER = (
    "# Operating Guide (starter)\n\n"
    "Written by `godmode init --detect` from this repo's own evidence. Every\n"
    "line below is a SOFT candidate with the fact that produced it named next\n"
    "to it - review each one and promote it deliberately; detection alone\n"
    "never becomes a blocking rule.\n\n"
)

_STUB_CONTENT = (
    "# Operating Guide (starter)\n\n"
    "`godmode init --detect` found nothing to propose from this repo's current\n"
    "evidence (no manifest, CI workflow command, .gitignore build marker, or\n"
    "migrations directory). This is an honest, minimal starting point -\n"
    "describe your project's real rules here as you learn them.\n"
)


def _starter_content(detections: list[dict[str, Any]]) -> str:
    lines = [detection["rule_text"] for detection in detections]
    return _STARTER_HEADER + "\n".join(lines) + "\n"


def bootstrap_charter(project: Path) -> dict[str, Any]:
    """`init --detect`'s implementation: propose or report, never overwrite.

    An authority document already bound by `resolve_roles` means a charter
    already exists; detection then only reports candidates and touches
    nothing. With no authority document bound, detection writes one starter
    file - full of SOFT candidates, or an honest stub when it found none.
    """
    project = Path(project)
    resolution = resolve_roles(project)
    stats: dict[str, Any] = {}
    detections = detect_repo(project, stats=stats)

    result: dict[str, Any] = {
        "files_scanned": stats.get("files_scanned", 0),
        "cap": stats.get("cap", FILE_CAP),
        "capped": stats.get("capped", False),
        "detections": len(detections),
    }

    if resolution.bindings:
        result["mode"] = "report"
        result["existing_documents"] = sorted({binding.view(project)["path"] for binding in resolution.bindings})
        result["candidates"] = detections
        result["note"] = (
            "an authority document already exists; detected candidates are "
            "reported for review and nothing was written"
        )
        return result

    target = project / STARTER_FILENAME
    if not detections:
        target.write_text(_STUB_CONTENT, encoding="utf-8")
        result["mode"] = "stub"
        result["path"] = STARTER_FILENAME
        result["note"] = "nothing detected"
        return result

    target.write_text(_starter_content(detections), encoding="utf-8")
    result["mode"] = "created"
    result["path"] = STARTER_FILENAME
    result["rules_written"] = len(detections)
    result["candidates"] = detections
    return result


def _self_check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        (project / "package.json").write_text(
            '{"scripts": {"test": "vitest run", "build": "vite build"}}',
            encoding="utf-8",
        )
        (project / ".gitignore").write_text("dist/\n.env\n", encoding="utf-8")

        detections = detect_repo(project)
        by_kind = {d["kind"]: d for d in detections}
        assert by_kind["test-command"]["value"] == "npm test", by_kind
        assert by_kind["generated-dir"]["value"] == "dist/", by_kind
        assert all("(detected: " in d["rule_text"] for d in detections), detections
        assert all("HARD" not in d["rule_text"] for d in detections), detections

        # The refusal is real, not merely absent: forcing HARD must raise.
        forced = False
        try:
            soft_rule_text(by_kind["test-command"], enforcement="HARD")
        except GodmodeError:
            forced = True
        assert forced, "detection must hard-refuse to emit HARD"

        # First bootstrap writes a starter file; a second run with a charter
        # already present must leave it untouched and report instead.
        result = bootstrap_charter(project)
        assert result["mode"] == "created", result
        written = (project / STARTER_FILENAME).read_text(encoding="utf-8")
        assert "HARD" not in written, written

        again = bootstrap_charter(project)
        assert again["mode"] == "report", again
        assert (project / STARTER_FILENAME).read_text(encoding="utf-8") == written

    with tempfile.TemporaryDirectory() as raw:
        # An empty repo detects nothing and still exits with an honest stub.
        empty_project = Path(raw)
        assert detect_repo(empty_project) == []
        stub = bootstrap_charter(empty_project)
        assert stub["mode"] == "stub", stub
        assert stub["note"] == "nothing detected"

    print("godmode_detect self-check OK")


if __name__ == "__main__":
    _self_check()
