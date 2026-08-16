"""Resolve a stable, worktree-aware Godmode project anchor."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
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
    # Deferred: only the once-per-device salt-creation path needs it, and
    # `secrets` transitively imports `hmac` - both paid on every hot-path
    # call (resolve_anchor, on every tool call) until this moved.
    salt_path = home / "godmode-device.salt"
    if not salt_path.exists():
        try:
            import secrets
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


def _head_identity(requested: Path) -> tuple[int, int] | None:
    """(mtime_ns, size) of the file whose change means "re-resolve the anchor".

    Not `.git/HEAD` itself: measured empirically, a commit on the current
    branch does NOT touch `.git/HEAD` (it stays `ref: refs/heads/main`
    byte-for-byte; the SHA it resolves to lives in `refs/heads/main`, updated
    separately) - only a checkout does, by rewriting which ref HEAD names.
    `.git/logs/HEAD` (the reflog) is the file that actually appends on both:
    git writes a new line to it on every commit AND every checkout, which is
    exactly the two operations resolve_anchor's cached fields (branch, head)
    can change under. Falls back to `.git/HEAD` when no reflog exists (fresh
    repo before its first commit, or `core.logAllRefUpdates=false`) - staler,
    but still correct for its one case (an as-yet-unrepeatable identity).

    Ceiling named, not hidden: `_remote_hashes` can go stale between calls
    (a `git remote add` does not touch HEAD or its reflog), so a cached
    anchor's `remote_hashes` may lag until the next commit or checkout
    invalidates the whole entry. Narrower and rarer than the branch/head
    class this cache exists for; upgrade path if it ever matters is watching
    `.git/config`'s identity too.

    Subprocess-free by construction (stat only) - a cache whose staleness
    check itself spawns git would defeat the point.
    """
    current = requested
    for _ in range(64):  # bounded: a runaway upward walk is a bug, not a feature
        marker = current / ".git"
        if marker.exists():
            git_dir = marker
            if marker.is_file():
                # Worktree indirection: the file's one line is
                # "gitdir: /path/to/main/.git/worktrees/<name>".
                try:
                    content = marker.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return None
                prefix = "gitdir:"
                line = next((l for l in content.splitlines()
                            if l.strip().startswith(prefix)), "")
                pointed = line.strip()[len(prefix):].strip()
                if not pointed:
                    return None
                git_dir = Path(pointed)
                if not git_dir.is_absolute():
                    git_dir = current / git_dir
            reflog = git_dir / "logs" / "HEAD"
            target = reflog if reflog.exists() else (
                git_dir / "HEAD" if git_dir.is_dir() else git_dir)
            try:
                stat = target.stat()
                return (stat.st_mtime_ns, stat.st_size)
            except OSError:
                return None
        if current.parent == current:
            break
        current = current.parent
    return None


def _anchor_cache_path(requested: Path) -> Path:
    # Cache-only content, safe to delete at any time: lives beside the
    # per-device salt, keyed by a hash of the resolved path so two projects
    # never collide.
    home = application_home()
    key = hashlib.sha256(str(requested).encode("utf-8")).hexdigest()[:24]
    return home / "anchor-cache" / f"{key}.json"


def _load_cached_anchor(requested: Path, identity: tuple[int, int]) -> ProjectAnchor | None:
    path = _anchor_cache_path(requested)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict) or list(raw.get("_head_identity", [])) != list(identity):
        return None
    fields = {k: v for k, v in raw.items() if k != "_head_identity"}
    try:
        return ProjectAnchor(**fields)
    except TypeError:
        return None  # schema drifted since the entry was written; re-resolve


def _store_cached_anchor(requested: Path, identity: tuple[int, int],
                         anchor: ProjectAnchor) -> None:
    path = _anchor_cache_path(requested)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(anchor)
        payload["_head_identity"] = list(identity)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # a cache write failure costs one extra resolve next call, not correctness


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

    # A cache hit answers without spawning git at all. `identity` is None for
    # a non-git directory (no `.git` found in the walk), which routes
    # straight past the cache into the existing non-git branch below - there
    # is nothing to cache there; that branch never shells to git.
    identity = _head_identity(requested)
    if identity is not None:
        cached = _load_cached_anchor(requested, identity)
        if cached is not None:
            return cached

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
        anchor = ProjectAnchor(
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
        if identity is not None:
            _store_cached_anchor(requested, identity, anchor)
        return anchor

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


def current_host() -> str:
    """The host label this process believes it is running under.

    Declared, not detected: `GODMODE_HOST` is the explicit override; a host
    that sets `CLAUDE_CODE_ENTRYPOINT` (Claude Code always does) is read from
    that one fact instead. Neither present reads as "unknown" rather than a
    guess - the same "an unknown is reported, not assumed" discipline
    `host_capabilities` applies to every control it names.
    """
    return os.environ.get("GODMODE_HOST") or os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "unknown"


def host_capabilities(*, tool_call_interception: str | None = None) -> dict[str, Any]:
    """State honestly what this host can enforce. An unknown is reported, not assumed.

    HARD means the control is decided outside model judgment. SOFT means it is
    surfaced and checked after the fact. UNAVAILABLE means the environment cannot
    support it, and any claim resting on it stays unverified.

    `tool_call_interception` arrives PRE-COMPUTED rather than being read here
    from an archive: this module is imported by nearly everything (see
    `godmode_drift.py`'s own note - "imported by everything, importing
    nothing runtime") and `godmode_hookproof.py` (CX-1's proof reader) needs
    `Chronicle`, which itself imports this module - so this module importing
    `godmode_hookproof`, even lazily inside a function, would be exactly the
    cycle that note exists to prevent (Godmode's own import-cycle guard
    checks source text, not runtime laziness, so a deferred import inside a
    function is not a way around it - nor should it be; the dependency really
    would exist). A caller with an archive in scope computes
    `godmode_hookproof.interception_state(archive, current_host())` itself
    and passes the answer straight through; a caller with none leaves the
    default, the same honest `UNAVAILABLE` as "no proof exists".
    """
    import sys

    interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    host = current_host()
    interception = tool_call_interception or "UNAVAILABLE"
    controls = {
        "attestation_gate": "HARD",
        "claim_downgrade": "HARD",
        "plan_mode_mutation_gate": "HARD",
        "status_reopen_guard": "HARD",
        "authority_claim_detection": "HARD",
        "interactive_authorization": "HARD" if interactive else "UNAVAILABLE",
        "agent_identity": "HARD" if os.environ.get("GODMODE_MODEL") else "SOFT",
        # HARD only when a chronicled, live proof record shows the pre-tool
        # boundary demonstrably received and denied a probe this session
        # (see godmode_hookproof.py) - never from an environment variable.
        # CX-1 replaced the previous GODMODE_PRETOOL_GATE sniff for exactly
        # this reason: nothing ever set it, so the claim could be silently
        # wrong while the gate really was live, and trivially fakeable by
        # anyone who exported the variable by hand.
        "tool_call_interception": interception,
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
