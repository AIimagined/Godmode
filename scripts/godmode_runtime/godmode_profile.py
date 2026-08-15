"""Graduated starting profiles for `godmode init --profile` (U-E8).

A brand-new project and a mature one want different STARTING points on the
same tighten-only ratchet the authorization policy already runs
(`.godmode-authorization-policy.json`'s `approval_required`, read by
`godmode_sentinel.local_authorization_policy` / `CapabilityBroker._policy`).
This module sets that starting posture; it invents no new enforcement
surface of its own.

Three profiles:

* `novice`  - ask-heavy. Two categories the classifier otherwise allows at
  its own discretion (`worktree-file-mutation`, `git-branch-create`) are
  added to `approval_required`, so an ordinary file edit or a new branch
  asks instead of proceeding silently.
* `standard` - today's defaults. Manages no key at all, so it is a genuine
  no-op: it neither writes the policy file nor refuses when one already
  exists. Pinned by test.
* `strict`  - full enforcement. `approval_required` gains
  `release-or-external-write` (already protected by the classifier's own
  tier table, named here so the policy file states the posture explicitly).
  `password_required` is never written by a profile - it would widen what
  needs a *minted capability*, and doing that before a password is even
  configured (`godmode authorize setup`) could lock a project out of its
  own release path with no way back in. Strict only *suggests* it in the
  emitted output, the same way U-E6 detection proposes a rule and leaves
  promotion to the operator.

Tighten-only, enforced per key: a profile owns `approval_required` as a
floor, never a ceiling. Applying one computes the union of what is already
on record and what the profile wants; if the file already names a category
the profile's own target does not include, writing the profile's value
would silently drop that ask, and this refuses instead, naming exactly
which categories would be lost - the operator still has the whole file to
hand-edit. `standard` never reaches this check: it does not manage the key,
so an existing, tighter file survives it untouched.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .godmode_errors import AuthorizationError, GodmodeError

POLICY_FILENAME = ".godmode-authorization-policy.json"

PROFILE_NAMES: tuple[str, ...] = ("novice", "standard", "strict")

# profile -> categories it wants present in `approval_required`. `standard`
# is deliberately absent: it manages no key, which is what makes it a no-op
# rather than a profile that happens to want an empty set.
_APPROVAL_REQUIRED_TARGETS: dict[str, tuple[str, ...]] = {
    "novice": ("git-branch-create", "worktree-file-mutation"),
    "strict": ("release-or-external-write",),
}

# strict's advisory-only half of "full enforcement" - printed, never written.
_PASSWORD_SUGGESTED: dict[str, tuple[str, ...]] = {
    "strict": ("release-or-external-write",),
}


def _read_policy(project: Path) -> dict[str, Any]:
    path = project / POLICY_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise GodmodeError(
            f"{POLICY_FILENAME} is unreadable; fix or remove it before applying a profile"
        ) from exc
    if not isinstance(raw, dict):
        raise GodmodeError(f"{POLICY_FILENAME} must contain a JSON object")
    # Same shape check `CapabilityBroker._policy()` already runs on this
    # exact field (`godmode_sentinel.py:2138-2143`) - a fix-round-1 gap: a
    # hand-malformed file (`approval_required: 5`, a bool, a dict) used to
    # reach `set()` unvalidated and either crash with an untyped `TypeError`
    # (a scalar - `set()` needs an iterable) or be silently accepted and
    # "repaired" into a well-formed list (a dict - `set()` iterates its
    # keys), neither of which is what the strict reader would do with the
    # same bytes. Named here, once, before anything downstream ever sees
    # the value, so both failure modes close together.
    approval = raw.get("approval_required")
    if approval is not None and (
        not isinstance(approval, list) or not all(isinstance(item, str) for item in approval)
    ):
        raise AuthorizationError(
            f"{POLICY_FILENAME}'s approval_required must be a list of strings, "
            f"not {type(approval).__name__}"
        )
    return raw


def _write_policy(project: Path, policy: dict[str, Any]) -> None:
    path = project / POLICY_FILENAME
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(policy, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_profile(project: Path, profile: str) -> dict[str, Any]:
    """Set `profile`'s starting posture on `project`'s authorization policy.

    Returns a JSON-safe result naming exactly what was (or was not) changed,
    every line carrying its provenance ("(profile: <name>)") so the operator
    sees what was set without opening the policy file. Raises
    `AuthorizationError` naming the category when applying this profile
    would drop an `approval_required` entry already on record - see the
    module docstring for why that check is per-key and `standard` never
    triggers it.

    Profiles do not compose: each application is checked tighten-only
    against the file exactly as it stands, whatever profile (or hand edit)
    put it there, never against "the profile that logically preceded this
    one." `novice` then `strict` refuses for the same reason `strict` then
    `novice` does - `novice`'s two categories are not in `strict`'s own
    target set, so writing `strict`'s value would drop them - even though
    the union of both would have been a lossless tightening. This is a
    deliberate simplicity trade: refusing a technically-safe union costs an
    operator one hand edit; silently unioning would need this function to
    reconstruct "which categories were profile-authored vs. hand-authored"
    from a file that carries no such provenance, which is exactly the
    ambiguity the tighten-only check exists to never guess at.
    """
    if profile not in PROFILE_NAMES:
        raise GodmodeError(
            f"unknown profile {profile!r}; choose one of {', '.join(PROFILE_NAMES)}"
        )
    project = Path(project)
    posture: list[str] = []

    target = _APPROVAL_REQUIRED_TARGETS.get(profile)
    if target is None:
        # `standard` manages nothing: no read beyond existence is even
        # needed to know this is a no-op.
        return {
            "profile": profile,
            "policy_file": POLICY_FILENAME,
            "written": False,
            "posture": [f"no changes; standard is today's defaults (profile: {profile})"],
        }

    policy = _read_policy(project)
    existing = set(policy.get("approval_required") or [])
    target_set = set(target)
    lost = sorted(existing - target_set)
    if lost:
        raise AuthorizationError(
            f"profile {profile!r} would remove approval_required for "
            f"{', '.join(lost)}, already explicit in {POLICY_FILENAME} "
            "(tighten-only); edit the file by hand if you intend to loosen it"
        )
    merged = sorted(existing | target_set)
    changed = merged != sorted(existing)
    if changed:
        policy["approval_required"] = merged
        _write_policy(project, policy)
    for category in sorted(target_set):
        posture.append(f"approval_required: {category} (profile: {profile})")

    result: dict[str, Any] = {
        "profile": profile,
        "policy_file": POLICY_FILENAME,
        "written": changed,
        "posture": posture,
        "approval_required": merged,
    }
    suggested = _PASSWORD_SUGGESTED.get(profile)
    if suggested:
        result["suggestions"] = [
            f"consider also adding password_required for {category} in {POLICY_FILENAME} "
            f"to require a minted capability, not just an ask (profile: {profile})"
            for category in suggested
        ]
    return result


def _self_check() -> None:
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as raw:
        project = Path(raw)

        standard = apply_profile(project, "standard")
        assert standard["written"] is False, standard
        assert not (project / POLICY_FILENAME).exists()

        novice = apply_profile(project, "novice")
        assert novice["written"] is True, novice
        assert "worktree-file-mutation" in novice["approval_required"], novice
        assert "git-branch-create" in novice["approval_required"], novice
        assert all("(profile: novice)" in line for line in novice["posture"]), novice

        # Idempotent: applying the same profile again changes nothing new.
        again = apply_profile(project, "novice")
        assert again["written"] is False, again

        # Tighten-only: strict cannot follow novice without dropping its
        # categories, and must name them in the refusal.
        raised = False
        try:
            apply_profile(project, "strict")
        except AuthorizationError as exc:
            raised = True
            assert "git-branch-create" in str(exc), exc
            assert "worktree-file-mutation" in str(exc), exc
        assert raised, "strict over an explicit novice policy must refuse"

    with _tempfile.TemporaryDirectory() as raw:
        # The plant this unit ships: strict first, then novice attempts to
        # loosen the category strict already made explicit.
        project = Path(raw)
        apply_profile(project, "strict")
        raised = False
        try:
            apply_profile(project, "novice")
        except AuthorizationError as exc:
            raised = True
            assert "release-or-external-write" in str(exc), exc
        assert raised, "novice over an explicit strict policy must refuse"

    print("godmode_profile self-check OK")


if __name__ == "__main__":
    _self_check()
