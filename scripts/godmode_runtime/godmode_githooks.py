"""CX-4: git-hook enforcement backstop - a second boundary, host-independent.

CX-1/CX-2/CX-3 all enforce at a HOST's own boundary (Claude's PreToolUse,
Codex's pre_tool_use, ...). Every one of them shares the same weakness: they
only fire while that host is the thing driving the terminal. A human running
`git push --force` by hand, or an agent shelling out from a host this project
has no adapter for yet, never touches any of them.

This module writes real, project-local git hooks
(`pre-commit`/`pre-push`/`pre-rebase`/`post-checkout`) that call back into
this exact CLI (`godmode guard --git-hook <name> --json`) and fail closed on
a protected verdict - at git's own chokepoint, independent of whatever host
(or no host at all) invoked git. It is opt-in, tighten-only, and honest about
a hard structural limit: **each hook only sees what git itself hands it**.

**What each hook can and cannot see (stated once, read everywhere):**

- `pre-push` reads the ref-update lines git writes to its stdin
  (`<local-ref> <local-sha> <remote-ref> <remote-sha>`, one per updated ref)
  and can run `git merge-base --is-ancestor` against the shas it was given.
  It CANNOT see the `--force`/`--force-with-lease` flag itself - git does not
  pass it. A non-fast-forward update (the remote sha is not an ancestor of
  the local sha) is treated as the force-push surrogate this boundary can
  honestly detect; every push is protected regardless (see `_decide` - a
  plain `git push` is already protected under the interactive gate this
  reuses), so a non-fast-forward push is not treated as a *different*
  category, only reported with what evidence produced its operation text.
- `pre-commit` sees only the staged file-name list (`git diff --cached
  --name-only`), never diff content. It can detect a pinned evaluator about
  to be committed; it cannot see WHAT changed in any file.
- `pre-rebase` receives at most an upstream ref and a branch name, and
  cannot determine whether the commits about to be rewritten were already
  pushed anywhere. Every rebase is treated as protected, uniformly, rather
  than guessing which ones are "safe" from information this hook does not
  have.
- `post-checkout` runs AFTER git has already switched the working tree - a
  nonzero exit here can never prevent the checkout, only report a problem
  loudly (specifically: a pinned evaluator's on-disk content no longer
  matches its pinned hash). `hooks status --git` and this module's own
  verdict payload both say so explicitly rather than implying a boundary
  that does not exist.

**Enforcement gate.** Install refuses unless the project has declared
`{"git_backstop": true}` in `.godmode-authorization-policy.json`, read
through `declared_gate_ratchet` (tighten-only, the same mechanism U-B3-5's
absorption gate already uses) - so once observed declared, the declaration
stays visible even if the key is later edited away. `guard --git-hook`
re-checks the SAME declaration at run time (not merely at install time): a
foreign process running an installed hook file after the policy was
declared-then-removed still honors the ratchet's high-water mark, and a hook
file that somehow survives without ever having been installed under a
declared policy enforces nothing.

**Capability escape valve.** A protected verdict under declared policy is
not an unconditional wall: exactly like the interactive gate, a matching
one-use capability staged with `godmode authorize stage --operation <exact
text>` is consumed silently first (`CapabilityBroker.consume_staged`, the
same broker every other R5-shaped refusal in this codebase already answers
through). Only a protected operation with nothing staged actually blocks.

**Never overwritten: foreign hooks.** A hook file already present that does
not carry this module's own marker comment is left untouched, always -
`install` reports it as `skipped_foreign` rather than clobbering someone
else's pre-existing hook. `.sample` files (git's own uninstalled templates)
are never even looked at: this module only ever reads/writes the exact hook
filename, never anything with a suffix.

**Known, disclosed bypass (fix round 1, I1).** `git push --no-verify` (and
any client that skips or reroutes hooks, e.g. `git -c
core.hooksPath=<elsewhere>`) skips every client-side hook including this
one - git's own documented escape hatch, not a defect here. This backstop
raises the floor for the default/cooperative path; it is **not** an
unbypassable wall for a caller with ordinary git-CLI access. Only
host-level interception (CX-1/CX-2/CX-3, where a matching adapter exists)
closes that specific gap. `KNOWN_BYPASS` states the same sentence in
`git_hooks_status`'s own output, so a reader of `hooks status --git` sees
it without having to find this docstring.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .godmode_hookproof import (
    SUBJECT_PROBE_FAILED, SUBJECT_UNINSTALLED, interception_state,
    record_interception_proof,
)
from .godmode_sentinel import (
    POLICY_FILENAME,
    CapabilityBroker,
    classify_action,
    declared_gate_ratchet,
    pin_file_digest,
    pinned_evaluators,
)

# The four client-side git hooks this backstop writes. Every other client
# hook git supports is left alone: these four are the ones whose exit code
# can plausibly stop (pre-commit/pre-push/pre-rebase) or at least loudly
# flag (post-checkout) the operation classes this product already governs.
HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "pre-rebase", "post-checkout")

# The one policy key this whole boundary rides. Riding `declared_gate_ratchet`
# (godmode_sentinel.py) rather than inventing a second small policy file -
# the exact DUPDRIFT lesson that function's own docstring already names.
POLICY_KEY = "git_backstop"

MARKER_PREFIX = "# godmode-git-hook:"
HASH_PREFIX = "# godmode-hook-hash:"

_ZERO_SHA = re.compile(r"^0+$")

# scripts/godmode_runtime/godmode_githooks.py -> parents[2] is the package
# root - the same __file__-relative resolution `godmode_hookproof.py` and
# `godmode_host_manifests.py` already use, never `${CLAUDE_PLUGIN_ROOT}` or
# any other host-specific variable a git hook has no way to expand anyway.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _resolved_godmode_py() -> Path:
    return _PACKAGE_ROOT / "scripts" / "godmode.py"


def _git(*args: str, cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout
    )


def _git_hooks_dir(project_root: Path) -> Path | None:
    """The real hooks directory git itself would use, worktree-correct.

    `git rev-parse --git-path hooks` (not a hand-assembled `.git/hooks`) so a
    linked worktree, whose hooks live under the MAIN repository's common git
    dir rather than the worktree's own `.git` file, still resolves to the one
    directory git actually consults.
    """
    result = _git("rev-parse", "--git-path", "hooks", cwd=project_root)
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(project_root) / path
    try:
        return path.resolve()
    except OSError:
        return path


def _canonical_body(text: str) -> str:
    """Every line of `text` EXCEPT the digest header line itself, normalized
    by a single `splitlines()`/`"\\n".join()` round-trip.

    This is the exact string `_hook_script` hashes to produce the digest it
    writes into `HASH_PREFIX`, and the exact string `_hook_file_state`
    re-hashes from the REAL on-disk file to check that digest against - so
    the comparison is "does this file's actual body match what its own
    header claims", never two independently-regenerated "ideal" strings
    that happen to share a recipe (the defect fix round 1 closed: the old
    comparison recomputed `expected_digest` from `(name, godmode_py)` alone
    and never read the file's real bytes at all, so a hand-edit that left
    the header line untouched - e.g. `exit $?` -> `exit 0  # tampered` -
    was invisible to it). Content-based filtering (not positional) means an
    edit that inserts, deletes, or reorders header comment lines is caught
    too, not only a body-logic edit.
    """
    return "\n".join(line for line in text.splitlines() if not line.startswith(HASH_PREFIX))


def _hook_script(name: str, godmode_py: Path) -> str:
    """The full sh-compatible hook file body, marker + hash header included.

    Forward-slashed and quoted: Windows Python accepts forward slashes in a
    path unconditionally, and a quoted path with either slash style survives
    POSIX `sh` unchanged - resolving the path once, at install time, into a
    form that is safe on both interpreters, rather than trying to detect the
    running platform inside the hook script itself.

    `python3` is tried before `python` (`command -v`, POSIX-portable);
    neither found fails closed with a message on stderr and a nonzero exit,
    rather than silently letting the git operation through un-checked.

    KNOWN, DISCLOSED BYPASS: `git push --no-verify` (and any client that
    skips or reroutes hooks, e.g. `git -c core.hooksPath=<elsewhere>`) skips
    every client-side hook including this one - git's own documented
    escape hatch, not a defect here. This backstop raises the floor for the
    default/cooperative path; it is not an unbypassable wall for a caller
    with ordinary git-CLI access. Only host-level interception (CX-1/CX-2/
    CX-3) closes that specific gap, and only where a matching adapter
    exists.
    """
    python_path = str(godmode_py).replace("\\", "/")
    logic = (
        "if command -v python3 >/dev/null 2>&1; then\n"
        "    PYTHON=python3\n"
        "elif command -v python >/dev/null 2>&1; then\n"
        "    PYTHON=python\n"
        "else\n"
        "    echo \"godmode: no python3 or python found on PATH; git-hook backstop "
        "cannot run (failing closed)\" >&2\n"
        "    exit 1\n"
        "fi\n"
        f'"$PYTHON" "{python_path}" guard --git-hook {name} --json\n'
        "exit $?\n"
    )
    header_lines = [
        "#!/bin/sh",
        f"{MARKER_PREFIX} {name}",
        "# Generated by `godmode hooks install --git`; reinstall to update this file,",
        "# never hand-edit it - any edit (including whitespace-only) changes this",
        "# file's canonical-body hash, which `hooks status --git` recomputes from the",
        "# ACTUAL on-disk bytes below (never trusted from the header alone) and",
        "# reports as godmode-modified on any mismatch, however small.",
        "# pre-push forwards stdin unchanged (git writes ref-update lines to it);",
        "# every other hook name here is invoked with none read. KNOWN BYPASS:",
        "# `git push --no-verify` (or a hooksPath override) skips this file entirely -",
        "# git's own escape hatch, not a defect; see `godmode hooks status --git`.",
    ]
    without_hash = "\n".join(header_lines) + "\n" + logic
    digest = hashlib.sha256(_canonical_body(without_hash).encode("utf-8")).hexdigest()
    full_lines = header_lines[:2] + [f"{HASH_PREFIX} {digest}"] + header_lines[2:]
    return "\n".join(full_lines) + "\n" + logic


def _extract_marker(text: str) -> tuple[str | None, str | None]:
    name = None
    digest = None
    for line in text.splitlines()[:12]:
        if name is None and line.startswith(MARKER_PREFIX):
            name = line[len(MARKER_PREFIX):].strip()
        elif digest is None and line.startswith(HASH_PREFIX):
            digest = line[len(HASH_PREFIX):].strip()
    return name, digest


def _hook_file_state(path: Path, expected_name: str) -> dict[str, Any]:
    """`absent` / `foreign` / `unreadable` / `godmode` / `godmode-modified`.

    `foreign` covers both "no marker at all" and "a marker for a different
    hook name" - a file this module would never itself have written under
    THIS name, either way, and therefore never safe to overwrite blindly.
    `.sample` files are never reached here: callers only ever pass the exact
    hook filename, never a suffixed one.

    Tamper detection (fix round 1, C1): `recorded_digest` is read from the
    file's OWN header line, and the value it is checked AGAINST -
    `actual_digest` - is the sha256 of THIS file's real, current, on-disk
    canonical body (`_canonical_body`). No independently-regenerated "ideal"
    string enters this comparison at all (the fixed defect: the old version
    compared the header's digest against `_hook_script(name, godmode_py)`'s
    own freshly-recomputed digest - a constant that never read the file on
    disk, so a body edit that left the header line untouched was invisible
    to it). A file whose body was edited without also recomputing and
    rewriting its own header line - the ordinary case, and the reviewer's
    own exact repro (`exit $?` -> `exit 0  # tampered`) - fails this check
    every time, including a whitespace-only edit: nothing here normalizes
    content beyond a bare newline split/join.
    """
    if not path.is_file():
        return {"state": "absent"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"state": "unreadable"}
    marker_name, recorded_digest = _extract_marker(text)
    if marker_name is None or marker_name != expected_name:
        return {"state": "foreign"}
    if recorded_digest is None:
        # A godmode marker survived, but its hash line itself is gone -
        # cannot be "current" with no claim left to verify against.
        return {"state": "godmode-modified", "hash": None}
    actual_digest = hashlib.sha256(_canonical_body(text).encode("utf-8")).hexdigest()
    if actual_digest == recorded_digest:
        return {"state": "godmode", "hash": recorded_digest}
    return {"state": "godmode-modified", "hash": recorded_digest}


# --------------------------------------------------------------------------
# install / status / uninstall
# --------------------------------------------------------------------------


def git_hooks_install(archive: Any, project_root: Path) -> dict[str, Any]:
    """Write the four hooks under declared policy; refuse otherwise.

    Never overwrites a foreign hook (`skipped_foreign`, never a silent
    clobber). Re-running this after an earlier install is an ordinary
    reinstall/update for any hook this module already owns.
    """
    # M6 (external audit): this whole function used to report success by a
    # single proxy - `declared` - that only ever answers "is the policy
    # opted in", never "did the install actually happen". Both the
    # unresolvable-hooks-directory branch and a swallowed `chmod` failure
    # below returned/left `declared: True` with nothing to contradict it,
    # which the CLI (`godmode_console.cmd_hooks`) then read straight into
    # `exit_code=0 if report["declared"] else 1` - a caller could not tell
    # "installed" from "declared but nothing was written" without also
    # comparing `installed` against `HOOK_NAMES` by hand. `ok` is now this
    # function's own, explicit answer to "did the install succeed", true
    # only when every non-foreign hook was both written AND made
    # executable; the CLI reads this field directly instead of re-deriving
    # it.
    declared = declared_gate_ratchet(archive, project_root, POLICY_KEY)
    if not declared:
        return {
            "declared": False,
            "ok": False,
            "installed": [],
            "skipped_foreign": [],
            "reason": (
                f'install refused: declare {{"{POLICY_KEY}": true}} in {POLICY_FILENAME} '
                "first (tighten-only - once observed declared, it stays declared even if "
                "the key is later removed or edited away)"
            ),
        }
    hooks_dir = _git_hooks_dir(project_root)
    if hooks_dir is None:
        return {
            "declared": True,
            "ok": False,
            "installed": [],
            "skipped_foreign": [],
            "reason": "not resolvable as a git repository (`git rev-parse --git-path "
                      "hooks` failed); nothing to install into",
        }
    hooks_dir.mkdir(parents=True, exist_ok=True)
    godmode_py = _resolved_godmode_py()
    installed: list[str] = []
    foreign: list[str] = []
    chmod_failed: list[str] = []
    for name in HOOK_NAMES:
        path = hooks_dir / name
        state = _hook_file_state(path, name)["state"]
        if state in ("foreign", "unreadable"):
            foreign.append(name)
            continue
        content = _hook_script(name, godmode_py)
        path.write_bytes(content.encode("utf-8"))
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            # Previously swallowed: the hook file was written but is not
            # executable, so git will never actually run it - reported now
            # (`chmod_failed`) rather than counted as an install success.
            chmod_failed.append(name)
        installed.append(name)
    if installed:
        archive.append(
            "action", "git-hooks-installed",
            {"host": "git", "installed_count": len(installed), "foreign_count": len(foreign),
             "chmod_failed_count": len(chmod_failed)},
            evidence=[],
        )
    result: dict[str, Any] = {
        "declared": True, "installed": installed, "skipped_foreign": foreign,
        "hooks_dir": str(hooks_dir), "ok": not chmod_failed,
    }
    if chmod_failed:
        result["chmod_failed"] = chmod_failed
        result["reason"] = (
            f"{len(chmod_failed)} hook(s) written but could not be made executable "
            f"({', '.join(chmod_failed)}); git will not run a non-executable hook"
        )
    return result


def git_hooks_uninstall(archive: Any, project_root: Path) -> dict[str, Any]:
    """Remove every godmode-owned hook; a foreign hook is left exactly alone.

    Chronicled (counts only, per privacy doctrine - never the hook names)
    via the SAME `hook-uninstalled` subject CX-1's `interception_state`
    already treats as supersession, so an uninstalled git backstop also
    correctly stops contributing to any HARD claim that record's freshness
    logic reads. The `git_backstop` declaration itself is untouched: the
    ratchet (`declared_gate_ratchet`) keeps it visible regardless.
    """
    hooks_dir = _git_hooks_dir(project_root)
    removed: list[str] = []
    if hooks_dir is not None:
        for name in HOOK_NAMES:
            path = hooks_dir / name
            state = _hook_file_state(path, name)["state"]
            if state not in ("godmode", "godmode-modified"):
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed.append(name)
    record = archive.append(
        "action", SUBJECT_UNINSTALLED,
        {"host": "git", "removed_count": len(removed)}, evidence=[],
    )
    return {
        "removed_count": len(removed),
        "record_sequence": record["sequence"],
        "declared_still_visible": declared_gate_ratchet(archive, project_root, POLICY_KEY),
    }


_BOUNDARY_NOTES: dict[str, str] = {
    "pre-push": "reads stdin ref-update lines and `git merge-base --is-ancestor` on the "
                "shas git hands it; CANNOT see the --force/--force-with-lease flag itself, "
                "only its non-fast-forward sha-level consequence",
    "pre-commit": "sees the staged file-name list only (`git diff --cached --name-only`); "
                  "detects a pinned evaluator about to be committed, nothing about content",
    "pre-rebase": "sees only that a rebase is starting, never whether the commits it would "
                  "rewrite were already pushed anywhere; treats every rebase as protected, "
                  "uniformly, rather than guessing",
    "post-checkout": "runs AFTER the checkout already happened; a nonzero exit here reports "
                     "a problem (a pinned evaluator's content changed) and cannot undo it",
}

# I1 (fix round 1): the one bypass every one of the four hooks above shares,
# stated once here rather than re-derived per hook, and surfaced in
# `git_hooks_status`'s own output - not just in prose a reader has to find.
# `--no-verify` is git's own documented flag; naming it is not conceding a
# defect, it is the "never report a tier it cannot demonstrate" doctrine
# applied to this boundary specifically.
KNOWN_BYPASS = (
    "git push --no-verify (and any client that skips or reroutes hooks, e.g. "
    "`git -c core.hooksPath=<elsewhere>`) skips every client-side hook including "
    "this one - git's own documented escape hatch. This backstop raises the floor "
    "for the default/cooperative path; it is not an unbypassable wall for a caller "
    "with ordinary git-CLI access. Only host-level interception (CX-1/CX-2/CX-3), "
    "where a matching adapter exists, closes that specific gap."
)


def _git_registration_grade(hooks: dict[str, dict[str, Any]]) -> str:
    """CX-5: `"partial"`/`"none"` - the git backstop's own registration signal.

    `godmode_hookproof.py` cannot compute this itself (it would need to
    import this module, which already imports IT - a real cycle). `"none"`
    (UNAVAILABLE) when no godmode-owned hook file exists at all; `"partial"`
    the moment at least one does, tampered or not - a `godmode-modified`
    hook is still structurally registered (this backstop's own tamper
    detector, not `interception_state`'s registration grading, is what
    catches the tamper; a fresh `verify --git` proof additionally catches it
    via `trusted_hook_hash` drift once one exists). There is no `"soft"`
    tier for git: the skills+CLI floor Addendum 4 describes does not apply
    to a host-independent backstop with no plugin of its own to install.
    """
    states = {entry.get("state") for entry in hooks.values()}
    return "partial" if states & {"godmode", "godmode-modified"} else "none"


def git_hooks_status(archive: Any, project_root: Path) -> dict[str, Any]:
    """Per-hook state, the declared policy, and the honesty notes for each boundary."""
    declared = declared_gate_ratchet(archive, project_root, POLICY_KEY)
    hooks_dir = _git_hooks_dir(project_root)
    if hooks_dir is None:
        return {
            "declared": declared, "hooks_dir": None,
            "hooks": {name: {"state": "no-git"} for name in HOOK_NAMES},
            "boundary_notes": dict(_BOUNDARY_NOTES), "known_bypass": KNOWN_BYPASS,
            # CX-5: no git directory at all is the same UNAVAILABLE grade as
            # no godmode hook file - `registration="none"` since `hooks` is
            # entirely synthetic `"no-git"` markers here, never a real state.
            "interception": interception_state(archive, "git", registration="none"),
        }
    hooks = {name: _hook_file_state(hooks_dir / name, name) for name in HOOK_NAMES}
    return {
        "declared": declared, "hooks_dir": str(hooks_dir), "hooks": hooks,
        "boundary_notes": dict(_BOUNDARY_NOTES), "known_bypass": KNOWN_BYPASS,
        # CX-5: the five-level grade for the git backstop specifically -
        # `verify --git` is what can move this to HARD; a tampered or
        # missing hook file caps it at PARTIAL/UNAVAILABLE via the
        # registration override above, regardless of any stale proof.
        "interception": interception_state(
            archive, "git", registration=_git_registration_grade(hooks)),
    }


# --------------------------------------------------------------------------
# guard --git-hook evaluation
# --------------------------------------------------------------------------


def _decide(archive: Any, project_root: Path, hook_name: str, operation: str) -> dict[str, Any]:
    """Classify one synthesized operation and decide allow/block.

    Reuses the exact classifier and capability broker the interactive gate
    already answers through - a plain `git push` is already protected there
    (`git-history-or-remote`), so this backstop's "protected" set is not a
    second, independently-tuned list to keep in sync with the first.
    """
    declared = declared_gate_ratchet(archive, project_root, POLICY_KEY)
    verdict = classify_action(operation, project_root=project_root, archive=archive)
    result: dict[str, Any] = {
        "git_hook": hook_name,
        "category": verdict["category"],
        "tier": verdict["tier"],
        "protected": verdict["protected"],
        "policy_declared": declared,
        "operation_digest": verdict["operation_digest"],
    }
    if not verdict["protected"]:
        result["verdict"] = "allow"
        return result
    if not declared:
        result["verdict"] = "allow"
        result["reason"] = (
            f"protected under the interactive gate, but {POLICY_KEY!r} is not declared in "
            f"{POLICY_FILENAME}; the git backstop stays advisory-only until it is"
        )
        return result
    consumed = CapabilityBroker(archive).consume_staged(operation)
    if consumed is not None:
        result["verdict"] = "allow"
        result["capability_consumed"] = True
        return result
    result["verdict"] = "block"
    result["reason"] = (
        "refused by the declared git_backstop policy; stage a one-use capability for "
        f"this exact operation first: `godmode authorize stage --operation {operation!r}`"
    )
    return result


def _parse_pre_push_refs(
    stdin_text: str,
) -> tuple[list[tuple[str, str, str, str]], bool]:
    """`(updates, malformed)`.

    Fix round 1, C2: the old version silently dropped any line that did not
    split into exactly 4 fields, so an all-garbled stdin produced the same
    `updates == []` an honestly-empty push does - indistinguishable, and
    silently allowed by `_evaluate_pre_push`'s empty-updates branch. That is
    exactly the pattern the plan's Global Constraint forbids: "Malformed
    output/timeout/silence is NEVER an implicit allow." `malformed` is now
    checked and returned BEFORE anything is dropped, so a garbled line can
    never be folded into "nothing to push" - the caller fails closed on it
    instead (under declared policy; see `_evaluate_pre_push`).
    """
    updates: list[tuple[str, str, str, str]] = []
    for line in stdin_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) != 4:
            return updates, True
        updates.append((parts[0], parts[1], parts[2], parts[3]))
    return updates, False


def _is_fast_forward(project_root: Path, ancestor_sha: str, descendant_sha: str) -> bool:
    result = _git(
        "merge-base", "--is-ancestor", ancestor_sha, descendant_sha,
        cwd=project_root, timeout=15,
    )
    return result.returncode == 0


def _malformed_stdin_result(
    archive: Any, project_root: Path, hook_name: str, detail: str,
) -> dict[str, Any]:
    """Fix round 1, C2: malformed/unreadable stdin fails closed under
    declared policy, and stays advisory-only otherwise - the policy check
    runs BEFORE any allow/block decision, never after a parse-result
    shortcut. Chronicled either way (counts-only: host + hook name, never
    the offending bytes), so the anomaly is visible even when the backstop
    isn't opted in yet.
    """
    declared = declared_gate_ratchet(archive, project_root, POLICY_KEY)
    try:
        archive.append(
            "action", "git-hook-malformed-input",
            {"host": "git", "git_hook": hook_name[:40], "enforced": declared},
            evidence=[],
        )
    except Exception:  # noqa: BLE001
        pass
    result: dict[str, Any] = {
        "git_hook": hook_name, "policy_declared": declared,
        "protected": True, "category": "malformed-git-hook-input",
    }
    if not declared:
        result["verdict"] = "allow"
        result["reason"] = (
            f"malformed-stdin: {detail}; {POLICY_KEY!r} is not declared in "
            f"{POLICY_FILENAME}, so this stays advisory-only (the git backstop is "
            "not opted in)"
        )
        return result
    result["verdict"] = "block"
    result["reason"] = (
        f"refused: malformed-stdin ({detail}) fails closed under declared policy - "
        "silence or unparseable input is never treated as permission"
    )
    return result


def _evaluate_pre_push(
    archive: Any, project_root: Path, stdin_text: str | None,
) -> dict[str, Any]:
    if stdin_text is None:
        return _malformed_stdin_result(
            archive, project_root, "pre-push", "stdin could not be read")
    updates, malformed = _parse_pre_push_refs(stdin_text)
    if malformed:
        return _malformed_stdin_result(
            archive, project_root, "pre-push",
            "a stdin line did not parse as an exact 4-field ref update")
    if not updates:
        return {
            "git_hook": "pre-push", "verdict": "allow", "ref_updates": 0,
            "reason": "stdin was read and contained no ref-update lines (a real empty "
                      "push)",
        }
    results = []
    for local_ref, local_sha, remote_ref, remote_sha in updates:
        if _ZERO_SHA.match(local_sha):
            operation = f"git push --delete origin {remote_ref}"
        elif _ZERO_SHA.match(remote_sha):
            operation = f"git push origin {local_ref}:{remote_ref}"
        elif not _is_fast_forward(project_root, remote_sha, local_sha):
            # The force-push surrogate this hook can honestly detect: it did
            # not see a --force flag, it saw history that could only have
            # reached this state THROUGH one.
            operation = f"git push --force origin {local_ref}:{remote_ref}"
        else:
            operation = f"git push origin {local_ref}:{remote_ref}"
        results.append(_decide(archive, project_root, "pre-push", operation))
    blocking = next((r for r in results if r["verdict"] == "block"), None)
    result = dict(blocking if blocking is not None else results[-1])
    result["ref_updates"] = len(updates)
    result["detects"] = _BOUNDARY_NOTES["pre-push"]
    return result


def _staged_paths(project_root: Path) -> list[str] | None:
    """The staged file-name list, or `None` when the inspection itself
    failed - never `[]` for that case.

    H2 (external audit): `git diff --cached --name-only` failing (a
    corrupt index, a git binary that cannot run, a repository git itself
    cannot open) used to be converted to an empty list here, which reads
    to `_evaluate_pre_commit` as "no staged changes" - allow, exit 0,
    every pinned-file check and capability consumption skipped, on a
    commit `_evaluate_pre_commit` never actually inspected. A failed
    inspection is not an empty result; the two are now distinguishable at
    the type level so the caller cannot fold them back together by
    accident the way `bool([])`/`bool(None)` both being falsy would invite.
    """
    result = _git("diff", "--cached", "--name-only", cwd=project_root, timeout=10)
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _inspection_failed_result(
    archive: Any, project_root: Path, hook_name: str, detail: str,
) -> dict[str, Any]:
    """H2 counterpart to `_malformed_stdin_result`: a hook's own inspection
    of repository state (not stdin this time) failed. Same shape, same
    rule - fails closed under declared policy, stays advisory-only
    otherwise, chronicled either way, and NEVER exits 0 by falling through
    to "nothing here" the way an empty list would have."""
    declared = declared_gate_ratchet(archive, project_root, POLICY_KEY)
    try:
        archive.append(
            "action", "git-hook-inspection-failed",
            {"host": "git", "git_hook": hook_name[:40], "enforced": declared},
            evidence=[],
        )
    except Exception:  # noqa: BLE001
        pass
    result: dict[str, Any] = {
        "git_hook": hook_name, "policy_declared": declared,
        "protected": True, "category": "inspection-failed",
    }
    if not declared:
        result["verdict"] = "allow"
        result["reason"] = (
            f"inspection-failed: {detail}; {POLICY_KEY!r} is not declared in "
            f"{POLICY_FILENAME}, so this stays advisory-only (the git backstop is "
            "not opted in)"
        )
        return result
    result["verdict"] = "block"
    result["reason"] = (
        f"refused: inspection-failed ({detail}) fails closed under declared policy - "
        "a failed inspection is never treated as an empty, harmless result"
    )
    return result


def _evaluate_pre_commit(archive: Any, project_root: Path) -> dict[str, Any]:
    staged = _staged_paths(project_root)
    if staged is None:
        return _inspection_failed_result(
            archive, project_root, "pre-commit",
            "`git diff --cached --name-only` exited nonzero")
    if not staged:
        return {
            "git_hook": "pre-commit", "verdict": "allow", "staged_files": 0,
            "reason": "no staged changes visible to pre-commit",
        }
    results = [_decide(archive, project_root, "pre-commit", f"edit file {path}")
               for path in staged]
    blocking = next((r for r in results if r["verdict"] == "block"), None)
    result = dict(blocking if blocking is not None else results[-1])
    result["staged_files"] = len(staged)
    result["detects"] = _BOUNDARY_NOTES["pre-commit"]
    return result


def _evaluate_pre_rebase(archive: Any, project_root: Path) -> dict[str, Any]:
    # One coarse operation text for every rebase: pre-rebase's own visibility
    # cannot distinguish which upstream/branch is "safe", so a staged
    # capability here is a one-time "allow the next rebase", not "allow
    # rebasing THIS branch onto THAT upstream" - stated, not implied.
    result = _decide(archive, project_root, "pre-rebase", "git rebase")
    result["detects"] = _BOUNDARY_NOTES["pre-rebase"]
    return result


def _evaluate_post_checkout(archive: Any, project_root: Path) -> dict[str, Any]:
    declared = declared_gate_ratchet(archive, project_root, POLICY_KEY)
    pins = pinned_evaluators(archive)
    tampered = []
    for path, expected_hash in pins.items():
        target = Path(project_root) / path
        actual = pin_file_digest(target) if target.is_file() else None
        if actual != expected_hash:
            tampered.append(path)
    base = {
        "git_hook": "post-checkout", "pinned_checked": len(pins),
        "policy_declared": declared, "detects": _BOUNDARY_NOTES["post-checkout"],
    }
    if not tampered or not declared:
        base["verdict"] = "allow"
        if tampered:
            base["reason"] = (
                f"{len(tampered)} pinned evaluator(s) changed via this checkout, but "
                f"{POLICY_KEY!r} is not declared; reported, not enforced"
            )
        return base
    base.update({
        "verdict": "block", "protected": True, "category": "pinned-evaluator-mutation",
        "tampered_pinned_count": len(tampered),
        "reason": "a pinned evaluator's content changed via this checkout; the checkout "
                  "already happened - this only reports it loudly (see 'detects')",
    })
    return base


def evaluate_git_hook(
    archive: Any, project_root: Path, name: str, stdin_text: str | None = ""
) -> dict[str, Any]:
    if name == "pre-push":
        return _evaluate_pre_push(archive, project_root, stdin_text)
    if name == "pre-commit":
        return _evaluate_pre_commit(archive, project_root)
    if name == "pre-rebase":
        return _evaluate_pre_rebase(archive, project_root)
    if name == "post-checkout":
        return _evaluate_post_checkout(archive, project_root)
    raise ValueError(f"unknown git hook name {name!r}; expected one of {HOOK_NAMES}")


# --------------------------------------------------------------------------
# verify --git
# --------------------------------------------------------------------------


def run_git_verify(archive: Any, *, host: str = "git", timeout: int = 30) -> dict[str, Any]:
    """CX-4's own live proof, mirroring `godmode_hookproof.run_probe`.

    Builds a fully throwaway bare-remote + working-repo pair, declares the
    policy and installs the real `pre-push` hook INSIDE that scratch repo
    only (an isolated, temporary godmode state - `GODMODE_STATE_HOME`
    pointed at a directory inside the same temp dir, restored in `finally`
    regardless of outcome), then attempts an ordinary, unauthorized
    `git push`. A plain push is already protected under the interactive
    gate this backstop reuses, so this does not need to manufacture a
    non-fast-forward scenario to prove the mechanism actually blocks
    something real: exit code AND unchanged remote ref are both checked
    (never inferred from silence).

    Only on a confirmed block does this write a CX-1 proof record - into the
    CALLER's real archive, `host="git"` - via
    `godmode_hookproof.record_interception_proof`. A failed attempt writes
    `SUBJECT_PROBE_FAILED` (host="git") instead, so a later, verify-less
    `hooks status --git`/`hooks status` read via `interception_state`
    reflects the failure too, not only this one response.
    """
    nonce = uuid.uuid4().hex[:12]
    result: dict[str, Any] = {"host": host, "nonce": nonce, "state": "UNAVAILABLE"}

    def _fail(detail: str) -> dict[str, Any]:
        result["detail"] = detail[:200]
        try:
            archive.append(
                "action", SUBJECT_PROBE_FAILED,
                {"host": host, "reason": "git-verify-failed"}, evidence=[],
            )
        except Exception:  # noqa: BLE001
            pass
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="godmode-git-verify-") as raw:
            base = Path(raw)
            remote = base / "remote.git"
            work = base / "work"
            for command in (["init", "-q", "--bare", str(remote)], ["init", "-q", str(work)]):
                completed = _git(*command, cwd=base, timeout=timeout)
                if completed.returncode != 0:
                    return _fail(f"scratch git setup failed: {completed.stderr.strip()}")
            _git("config", "user.email", "godmode-verify@example.invalid", cwd=work, timeout=timeout)
            _git("config", "user.name", "godmode-verify", cwd=work, timeout=timeout)
            _git("checkout", "-q", "-b", "main", cwd=work, timeout=timeout)
            (work / "README.md").write_text("verify\n", encoding="utf-8")
            _git("add", "README.md", cwd=work, timeout=timeout)
            committed = _git("commit", "-q", "-m", "initial", cwd=work, timeout=timeout)
            if committed.returncode != 0:
                return _fail(f"scratch commit failed: {committed.stderr.strip()}")
            _git("remote", "add", "origin", str(remote), cwd=work, timeout=timeout)

            previous_state_home = os.environ.get("GODMODE_STATE_HOME")
            os.environ["GODMODE_STATE_HOME"] = str(base / "state")
            try:
                from .godmode_anchor import resolve_anchor
                from .godmode_chronicle import Chronicle

                scratch_archive = Chronicle(resolve_anchor(work))
                scratch_archive.initialize()
                (work / POLICY_FILENAME).write_text(
                    json.dumps({POLICY_KEY: True}), encoding="utf-8")
                install_report = git_hooks_install(scratch_archive, work)
                if "pre-push" not in install_report.get("installed", []):
                    return _fail(
                        f"scratch install did not write pre-push: {install_report}")
                pushed = _git("push", "origin", "main", cwd=work, timeout=timeout)
            finally:
                if previous_state_home is None:
                    os.environ.pop("GODMODE_STATE_HOME", None)
                else:
                    os.environ["GODMODE_STATE_HOME"] = previous_state_home

            remote_ref = _git(
                "rev-parse", "--verify", "-q", "refs/heads/main", cwd=remote, timeout=timeout)
            blocked = pushed.returncode != 0 and remote_ref.returncode != 0
            if not blocked:
                return _fail(
                    "the installed pre-push hook did not block an unauthorized push "
                    f"(push_exit={pushed.returncode}, remote_ref_exists="
                    f"{remote_ref.returncode == 0})"
                )
    except (OSError, subprocess.TimeoutExpired) as exc:  # noqa: BLE001
        return _fail(f"scratch git verify raised: {exc}")

    proof = record_interception_proof(archive, host=host, tool="git-push", request_id=nonce)
    result["state"] = "HARD"
    result["proof_sequence"] = proof["sequence"]
    return result
