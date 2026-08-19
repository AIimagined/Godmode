"""Park the operator's observe-mode declaration while hook-subprocess tests run.

Tests that spawn `godmode_session_hook.py`/`godmode_gate_fast.py` against THIS
repository inherit whatever `.godmode-authorization-policy.json` the operator
has declared at its root. With `{"gate_mode": "observe"}` present, the hook
answers every protected call with an OBSERVE-MODE `systemMessage` instead of a
decision envelope, and the same 13 assertions fail on every run - an
environmental failure set that had to be worked around by moving the file
aside by hand ("restore after!").

This fixture is that hand move, made mechanical and self-undoing: the module
that imports it parks the file under a sibling name in `setUpModule` and puts
it back in `tearDownModule`. The tests then pin their own gate mode - enforce,
the shipped default - regardless of the checkout's local declaration.

Deliberately NOT an env-var override inside the hook: the policy file is the
one door into gate posture (CX final review F1 closed exactly the cheap-flip
class), and a test-only env door would ship as a production bypass. Moving
the file is what the operator already does; automating the exact same move
adds no new surface.

If a run dies hard between park and restore, the declaration is left under
`.godmode-authorization-policy.test-parked.json`: the gate ENFORCES (the
tight direction - observe is the loosening), and the parked name shows up
untracked in `git status` instead of vanishing. Rename it back to restore
the declaration.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLICY = _ROOT / ".godmode-authorization-policy.json"
_PARKED = _ROOT / ".godmode-authorization-policy.test-parked.json"


def park_local_policy() -> None:
    """Move the checkout's policy declaration aside, if one exists."""
    if _POLICY.exists():
        _POLICY.replace(_PARKED)


def restore_local_policy() -> None:
    """Put a parked declaration back, if one is waiting."""
    if _PARKED.exists():
        _PARKED.replace(_POLICY)
