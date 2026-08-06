"""Resolve a stable, worktree-aware Godmode project anchor."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import secrets
import subprocess
from typing import Any

from .godmode_constants import ARCHIVE_DIRNAME, PRODUCT, SCHEMA_VERSION
from .godmode_errors import IdentityError


def canonical_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise IdentityError(f"Cannot resolve project path: {path}") from exc


def run_git(project: Path, *arguments: str) -> str | None:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=environment,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _secure_create(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def application_home() -> Path:
    override = os.environ.get("GODMODE_STATE_HOME")
    if override:
        return canonical_path(Path(override))
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return canonical_path(Path(os.environ["LOCALAPPDATA"]) / PRODUCT)
    if os.environ.get("XDG_STATE_HOME"):
        return canonical_path(Path(os.environ["XDG_STATE_HOME"]) / PRODUCT.lower())
    return canonical_path(Path.home() / ".local" / "state" / PRODUCT.lower())


def _device_salt(home: Path) -> bytes:
    salt_path = home / "godmode-device.salt"
    if not salt_path.exists():
        try:
            _secure_create(salt_path, secrets.token_bytes(32))
        except FileExistsError:
            pass
    try:
        value = salt_path.read_bytes()
    except OSError as exc:
        raise IdentityError(f"Cannot read device identity at {salt_path}") from exc
    if len(value) < 16:
        raise IdentityError("Godmode device identity is invalid")
    return value


def _remote_hashes(project: Path) -> list[str]:
    remotes = run_git(project, "remote")
    if not remotes:
        return []
    hashes: list[str] = []
    for remote in sorted(filter(None, remotes.splitlines())):
        address = run_git(project, "remote", "get-url", remote)
        if address:
            hashes.append(hashlib.sha256(address.encode("utf-8")).hexdigest())
    return hashes


@dataclass(frozen=True)
class ProjectAnchor:
    schema_version: int
    project_root: str
    project_key: str
    is_git: bool
    git_common_dir: str | None
    worktree_root: str | None
    branch: str | None
    head: str | None
    remote_hashes: list[str]
    archive_root: str

    def public_view(self) -> dict[str, Any]:
        data = asdict(self)
        data["project_root"] = "."
        data["git_common_dir"] = "<git-metadata>" if self.git_common_dir else None
        data["worktree_root"] = "." if self.worktree_root else None
        data["archive_root"] = "<local-state>"
        return data


def resolve_anchor(project: str | Path) -> ProjectAnchor:
    requested = canonical_path(Path(project))
    if not requested.exists() or not requested.is_dir():
        raise IdentityError(f"Project directory does not exist: {requested}")

    top = run_git(requested, "rev-parse", "--show-toplevel")
    common = run_git(requested, "rev-parse", "--git-common-dir")
    if top and common:
        project_root = canonical_path(Path(top))
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = project_root / common_path
        common_path = canonical_path(common_path)
        project_key = hashlib.sha256(
            f"git\0{common_path}".encode("utf-8")
        ).hexdigest()[:24]
        return ProjectAnchor(
            schema_version=SCHEMA_VERSION,
            project_root=str(project_root),
            project_key=project_key,
            is_git=True,
            git_common_dir=str(common_path),
            worktree_root=str(project_root),
            branch=run_git(project_root, "branch", "--show-current") or None,
            head=run_git(project_root, "rev-parse", "HEAD"),
            remote_hashes=_remote_hashes(project_root),
            archive_root=str(canonical_path(common_path / ARCHIVE_DIRNAME)),
        )

    home = application_home()
    salt = _device_salt(home)
    project_key = hashlib.sha256(
        salt + str(requested).encode("utf-8")
    ).hexdigest()[:24]
    return ProjectAnchor(
        schema_version=SCHEMA_VERSION,
        project_root=str(requested),
        project_key=project_key,
        is_git=False,
        git_common_dir=None,
        worktree_root=None,
        branch=None,
        head=None,
        remote_hashes=[],
        archive_root=str(canonical_path(home / "projects" / project_key)),
    )


def host_capabilities() -> dict[str, Any]:
    """State honestly what this host can enforce. An unknown is reported, not assumed.

    HARD means the control is decided outside model judgment. SOFT means it is
    surfaced and checked after the fact. UNAVAILABLE means the environment cannot
    support it, and any claim resting on it stays unverified.
    """
    import sys

    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    host = os.environ.get("GODMODE_HOST") or os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "unknown"
    controls = {
        "attestation_gate": "HARD",
        "claim_downgrade": "HARD",
        "plan_mode_mutation_gate": "HARD",
        "status_reopen_guard": "HARD",
        "authority_claim_detection": "HARD",
        "interactive_authorization": "HARD" if interactive else "UNAVAILABLE",
        "agent_identity": "HARD" if os.environ.get("GODMODE_MODEL") else "SOFT",
        "tool_call_interception": "UNAVAILABLE",
    }
    return {
        "host": host,
        "interactive": interactive,
        "controls": controls,
        "unavailable": sorted(k for k, v in controls.items() if v == "UNAVAILABLE"),
        "note": "UNAVAILABLE controls are not enforced here; claims resting on them stay unverified",
    }


def nongit_archive_root(project: str | Path) -> Path:
    """Where this path's archive would live if the project were not a Git repository.

    Running `git init` inside an existing project moves the archive from the
    application-data directory into Git metadata, orphaning everything recorded
    before. The old archive is still on disk; only the pointer moved. This resolves
    that previous location so the records can be found and adopted rather than lost.
    """
    requested = canonical_path(Path(project))
    home = application_home()
    project_key = hashlib.sha256(
        _device_salt(home) + str(requested).encode("utf-8")
    ).hexdigest()[:24]
    return canonical_path(home / "projects" / project_key)


def anchor_fingerprint(anchor: ProjectAnchor) -> str:
    stable = {
        "project_key": anchor.project_key,
        "is_git": anchor.is_git,
        "git_common_dir": anchor.git_common_dir,
        "worktree_root": anchor.worktree_root,
        "branch": anchor.branch,
        "head": anchor.head,
        "remote_hashes": anchor.remote_hashes,
    }
    encoded = json.dumps(
        stable, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
