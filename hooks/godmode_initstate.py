"""Does this project have Godmode state at all? Answered with stats alone.

Field report 2026-09-23: in a project nobody ran `godmode init` in, the
hooks still loaded the whole runtime (the archive, the classifier, the
anchor and its git calls) only to find nothing there, and under machine
load that pushed them past the host's timeouts until the host's own
diagnostics advised uninstalling the plugin. This module answers the one
question those hooks need first - is there anything here to govern? - with
no subprocess, no pathlib, and nothing from `godmode_runtime`, so a hook can
ask it before importing anything heavy.

It mirrors `godmode_runtime.godmode_anchor.resolve_anchor` (and
`nongit_archive_root`, for an archive stranded by a later `git init`)
without running git: `tests/test_hook_uninitialized_fast_exit.py` pins that
every archive location this module computes is the one `resolve_anchor`
computes for the same directory. It answers `ABSENT` only when every place
an archive could live is missing; any doubt - an unreadable `.git` file, a
`GIT_DIR` override, a directory that does not exist - answers `UNKNOWN`,
and the caller then takes the full path, which is always correct.
"""
from __future__ import annotations

import os

ABSENT = "absent"
PRESENT = "present"
UNKNOWN = "unknown"

# Mirrors godmode_constants.PRODUCT and ARCHIVE_DIRNAME.
_PRODUCT = "Godmode"
_ARCHIVE_DIRNAME = "godmode-state"
_SALT_NAME = "godmode-device.salt"
_GIT_OVERRIDES = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_CEILING_DIRECTORIES")


def _sha256_hex(data: bytes) -> str:
    # The builtin hash module, not `hashlib`: hashlib loads OpenSSL, about
    # 10 ms on a hook that exists to cost nothing.
    try:
        from _sha2 import sha256  # type: ignore[import-not-found]
    except ImportError:
        try:
            from _sha256 import sha256  # type: ignore[import-not-found,no-redef]
        except ImportError:
            from hashlib import sha256  # type: ignore[no-redef]
    return sha256(data).hexdigest()


def canonical(path: str) -> str:
    """`godmode_anchor.canonical_path` without pathlib: `Path.resolve` is
    `os.path.realpath` on every supported Python."""
    return os.path.realpath(os.path.expanduser(path))


def application_home() -> str:
    """`godmode_anchor.application_home()`, the same order."""
    override = os.environ.get("GODMODE_STATE_HOME")
    if override:
        return canonical(override)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return canonical(os.path.join(os.environ["LOCALAPPDATA"], _PRODUCT))
    if os.environ.get("XDG_STATE_HOME"):
        return canonical(os.path.join(os.environ["XDG_STATE_HOME"], _PRODUCT.lower()))
    return canonical(os.path.join(os.path.expanduser("~"), ".local", "state", _PRODUCT.lower()))


def git_project_key(common_dir: str) -> str:
    return _sha256_hex(f"git\0{common_dir}".encode("utf-8"))[:24]


def nongit_project_key(salt: bytes, requested: str) -> str:
    return _sha256_hex(salt + requested.encode("utf-8"))[:24]


def _read_salt(home: str) -> bytes | None:
    """The device salt, or None when there is none. Never creates it: the
    runtime creates it on first use, and a project that has none cannot
    have a non-git archive. Raises OSError/ValueError on anything odd."""
    path = os.path.join(home, _SALT_NAME)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        value = handle.read()
    if len(value) < 16:
        raise ValueError("invalid device salt")
    return value


def _git_location(requested: str) -> tuple[str, str] | None:
    """(worktree root, git common dir) for the first `.git` above
    `requested`, the way git itself would find it; None when there is no
    `.git` at all. Raises ValueError when a `.git` exists but cannot be
    followed - the caller reads that as doubt."""
    current = requested
    for _ in range(128):
        marker = os.path.join(current, ".git")
        if os.path.isdir(marker):
            git_dir = marker
            break
        if os.path.isfile(marker):
            with open(marker, encoding="utf-8", errors="replace") as handle:
                line = next((l.strip() for l in handle if l.strip().startswith("gitdir:")), "")
            pointed = line[len("gitdir:"):].strip()
            if not pointed:
                raise ValueError("a .git file without gitdir")
            git_dir = pointed if os.path.isabs(pointed) else os.path.join(current, pointed)
            if not os.path.isdir(git_dir):
                raise ValueError("a .git file pointing nowhere")
            break
        if os.path.exists(marker):
            raise ValueError("a .git that is neither file nor directory")
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    else:
        raise ValueError("walk bound reached")
    common = git_dir
    commondir_file = os.path.join(git_dir, "commondir")
    if os.path.isfile(commondir_file):
        with open(commondir_file, encoding="utf-8", errors="replace") as handle:
            pointed = handle.readline().strip()
        if pointed:
            common = pointed if os.path.isabs(pointed) else os.path.join(git_dir, pointed)
    if not os.path.isfile(os.path.join(common, "HEAD")) and not os.path.isfile(os.path.join(git_dir, "HEAD")):
        raise ValueError("not a repository git would accept")
    return canonical(current), canonical(common)


def project_state(project: str) -> tuple[str, str | None]:
    """(state, project root) for `project`, a path as a hook received it.

    `project root` is what `resolve_anchor(project).project_root` would be
    (None when the state is `UNKNOWN`). Never raises."""
    try:
        requested = canonical(str(project))
        if not os.path.isdir(requested):
            return UNKNOWN, None
        if any(os.environ.get(name) for name in _GIT_OVERRIDES):
            return UNKNOWN, None
        home = application_home()
        projects = os.path.join(home, "projects")
        located = _git_location(requested)
        if located is not None:
            root, common = located
            if os.path.exists(os.path.join(common, _ARCHIVE_DIRNAME)):
                return PRESENT, root
            if not os.path.isdir(projects):
                return ABSENT, root
            # An unwritable git dir sends the archive to application data
            # under the git-derived key.
            if os.path.exists(os.path.join(projects, git_project_key(common))):
                return PRESENT, root
            # Records written before this directory became a repository
            # (`Chronicle.orphaned`): the full hook has something to say.
            # A repository git refuses to open (dubious ownership) resolves
            # as a plain directory: its archive is the requested path's.
            salt = _read_salt(home)
            if salt is not None and any(
                    os.path.exists(os.path.join(projects, nongit_project_key(salt, path)))
                    for path in {root, requested}):
                return PRESENT, root
            return ABSENT, root
        if not os.path.isdir(projects):
            return ABSENT, requested
        salt = _read_salt(home)
        if salt is None:
            return ABSENT, requested
        if os.path.exists(os.path.join(projects, nongit_project_key(salt, requested))):
            return PRESENT, requested
        return ABSENT, requested
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: doubt is UNKNOWN, and UNKNOWN takes the full path
        return UNKNOWN, None


# The session hook's events, as its argparse `choices` name them.
SESSION_EVENTS = ("stop", "session-start", "pre-compact", "session-end",
                  "pre-action", "user-prompt", "subagent-stop")
# Mirrors the session hook's CAPTURE_PAYLOAD_ENV: a capture run always
# takes the full path.
_CAPTURE_PAYLOAD_ENV = "GODMODE_CAPTURE_HOST_PAYLOADS"
EXIT = "exit"
NOTICE = "notice"
FULL = "full"


def early_session_decision(argv: list[str]) -> tuple[str, dict, bytes | None, str | None]:
    """`(action, payload, stdin bytes, project root)` for a session-hook
    call, decided before the hook itself is compiled or imported.

    `EXIT`: the project has no Godmode state; exit 0 and print nothing.
    `NOTICE`: the same, but a Claude session is starting and hears the
    not-initialized notice. `FULL`: anything else - the full hook decides,
    including every argument argparse would reject, a malformed payload
    (a pre-action one must still be refused) and a payload capture. The
    stdin bytes, when read, are returned so the full hook reads the payload
    once. Never raises."""
    raw: bytes | None = None
    submitted: dict = {}
    try:
        event: str | None = None
        project: str | None = None
        index = 0
        while index < len(argv):
            token = argv[index]
            if token == "--project" and index + 1 < len(argv):
                project = argv[index + 1]
                index += 2
                continue
            if token.startswith("--project="):
                project = token.split("=", 1)[1]
                index += 1
                continue
            if token.startswith("-") or event is not None:
                return FULL, submitted, None, None
            event = token
            index += 1
        if event not in SESSION_EVENTS:
            return FULL, submitted, None, None
        from godmode_stdin import parse_first_json, read_first_json
        raw = read_first_json()
        submitted, malformed = parse_first_json(raw)
        if malformed or os.environ.get(_CAPTURE_PAYLOAD_ENV):
            return FULL, submitted, raw, None
        # The project the full hook resolves: `--project`, else the
        # payload's `cwd`, else the process directory.
        state, root = project_state(project or str(submitted.get("cwd") or "."))
        if state != ABSENT:
            return FULL, submitted, raw, None
        if event == "session-start" and submitted.get("hook_event_name") == "SessionStart":
            return NOTICE, submitted, raw, root
        return EXIT, submitted, raw, root
    except Exception:  # noqa: BLE001  # godmode: swallow-ok: doubt takes the full path, with whatever was read
        return FULL, submitted, raw, None
