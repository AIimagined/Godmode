"""Branch roles: which branches carry the plan-and-test discipline.

A branch is `maintained` (its code is kept: an unplanned multi-file change
is refused, and a code change without a test change is named) or
`throwaway` (a spike: neither applies). The role is declared on the
git-topology record, `godmode branches --record --role <role>`, and the
newest declaration for a branch wins. With no declaration, the name
decides: `main` and `sprint/*` are maintained, `spike/*` is throwaway, and
any other branch is undeclared - the plan gate still applies to it (only a
throwaway is exempt), the missing-test finding does not (only a maintained
branch is held to it).

Declaring a branch throwaway switches both off, so that declaration counts
only when a verified operator wrote it (`--as-operator`); declaring a
branch maintained counts from anyone.
"""

from __future__ import annotations

from typing import Any

MAINTAINED = "maintained"
THROWAWAY = "throwaway"
ROLES = (MAINTAINED, THROWAWAY)

TOPOLOGY_KIND = "branch"
TOPOLOGY_SUBJECT = "git-topology"


def default_role(branch: str | None) -> str | None:
    """The role a branch has by name alone, or None."""
    if not branch:
        return None
    if branch == "main" or branch.startswith("sprint/"):
        return MAINTAINED
    if branch.startswith("spike/"):
        return THROWAWAY
    return None


def loosens(branch: str | None, role: str) -> bool:
    """Whether declaring `role` for `branch` can switch a gate off: every
    throwaway declaration. Such a declaration counts only from a verified
    operator; one that tightens (maintained) counts from anyone.

    Compared with the role, never with the branch name's default (review
    round 2, F2): on `spike/*` an operator may have declared the branch
    maintained, and an agent restating it as a spike would undo that.
    Restating a spike by name is a no-op the default already gives."""
    return role == THROWAWAY


def declared_role(archive: Any, branch: str | None) -> str | None:
    """The newest role declared for `branch` on a git-topology record that
    is allowed to decide it. A loosening declaration written with less than
    operator trust is skipped (review B2): the agent the plan-first gate
    and the missing-test finding hold to account cannot declare its own
    branch a spike."""
    if archive is None or not branch:
        return None
    from .godmode_chronicle import TRUST_ORDER, record_trust

    for record in reversed(archive.select(kind=TOPOLOGY_KIND, subject=TOPOLOGY_SUBJECT,
                                          limit=500)):
        data = record.get("data") or {}
        if data.get("branch") != branch or data.get("role") not in ROLES:
            continue
        if loosens(branch, data["role"]) and record_trust(record) < TRUST_ORDER["operator"]:
            continue
        return data["role"]
    return None


def branch_role(archive: Any, branch: str | None) -> dict[str, Any]:
    """`{"branch", "role", "source"}`; `source` is `declared`, `default`
    (from the name) or `undeclared` (role None)."""
    declared = declared_role(archive, branch)
    if declared is not None:
        return {"branch": branch, "role": declared, "source": "declared"}
    by_name = default_role(branch)
    if by_name is not None:
        return {"branch": branch, "role": by_name, "source": "default"}
    return {"branch": branch, "role": None, "source": "undeclared"}
