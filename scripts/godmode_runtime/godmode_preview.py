"""The four-part preview an operator decides a protected action from."""
from __future__ import annotations

from typing import Any

ACCEPTED_COST = {
    "R0": "nothing outside the working tree changes; a wrong call costs a re-run.",
    "R1": "a read or a working-tree write; a wrong call costs one revert.",
    "R2": "a local repository change; a wrong call costs a reset of local history.",
    "R3": "a process, environment or unknown-command effect; a wrong call may need a restart or a manual clean-up.",
    "R4": "a filesystem or database change outside the tree; a wrong call may lose data with no revert.",
    "R5": "history or a remote changes for everyone; a wrong call needs a reflog, a re-push or a re-release to undo.",
}


def render_preview(preview: dict[str, Any]) -> str:
    tier = str(preview.get("tier") or "R0")
    protected = bool(preview.get("protected"))
    lines = ["Context:",
             f"  operation: {preview.get('operation', '')}",
             f"  category: {preview.get('category', 'none')}  tier: {tier}",
             "Options:",
             "  1. proceed with a staged capability for this exact operation" if protected else "  1. proceed",
             "  2. choose a non-protected route that reaches the same goal",
             "  3. stop and record why",
             "Resolution:"]
    if protected:
        lines.append(f"  the gate {'denies outright' if tier == 'R5' else 'asks'}; a staged capability is required")
    else:
        lines.append("  the gate allows; no capability is required")
    lines += ["Accepted cost:", f"  {tier}: {ACCEPTED_COST.get(tier, ACCEPTED_COST['R0'])}"]
    return "\n".join(lines)
