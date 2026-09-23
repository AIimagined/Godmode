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

That handles the PROJECT layer. There is also an OPERATOR layer:
`godmode_sentinel.operator_policy_path()` reads
`$GODMODE_STATE_HOME/godmode-authorization-policy.json` when
`GODMODE_STATE_HOME` is set, else `~/.godmode/godmode-authorization-policy.json`.
An operator who has declared one of those (e.g. an `ask_only` list) has it
composed into the effective policy the same way the project file is, and the
hook-subprocess tests inherit it exactly like they inherit the project file.

The fix here is the same shape, not a second mechanism: point
`GODMODE_STATE_HOME` at a fresh, empty temp directory for the duration, so
`operator_policy_path()` resolves to a path that does not exist and the
operator layer reads as absent - without ever touching the operator's real
`~/.godmode`. `restore_local_policy()` puts the prior value (or absence) of
`GODMODE_STATE_HOME` back and removes the temp directory.

This does not touch where a git project's own archive lives: `resolve_anchor`
sends that under the project's `.git` directory regardless of
`GODMODE_STATE_HOME` (see `godmode_anchor.resolve_anchor`); the env var only
ever reaches `application_home()` / `operator_policy_path()` / the
device-scoped agent-id seed, none of which the fixture project's archive
depends on.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_POLICY = _ROOT / ".godmode-authorization-policy.json"
_PARKED = _ROOT / ".godmode-authorization-policy.test-parked.json"

_STATE_HOME_ENV = "GODMODE_STATE_HOME"
_parked_state_home_dir: Path | None = None
_prior_state_home: str | None = None
_state_home_parked = False


def park_local_policy() -> None:
    """Move the checkout's policy declaration aside, if one exists, and
    isolate the operator layer too by pointing GODMODE_STATE_HOME at a
    fresh, empty temp directory - so operator_policy_path() resolves to a
    file that does not exist, regardless of what the operator has actually
    declared under their real ~/.godmode."""
    if _POLICY.exists():
        _POLICY.replace(_PARKED)
    global _parked_state_home_dir, _prior_state_home, _state_home_parked
    if _state_home_parked:
        return
    _prior_state_home = os.environ.get(_STATE_HOME_ENV)
    _parked_state_home_dir = Path(tempfile.mkdtemp(prefix="godmode-state-home-park-"))
    os.environ[_STATE_HOME_ENV] = str(_parked_state_home_dir)
    _state_home_parked = True


def restore_local_policy() -> None:
    """Put a parked declaration back, if one is waiting, and restore
    whatever GODMODE_STATE_HOME held (or its absence) before
    park_local_policy() ran."""
    if _PARKED.exists():
        _PARKED.replace(_POLICY)
    global _parked_state_home_dir, _prior_state_home, _state_home_parked
    if not _state_home_parked:
        return
    if _prior_state_home is None:
        os.environ.pop(_STATE_HOME_ENV, None)
    else:
        os.environ[_STATE_HOME_ENV] = _prior_state_home
    if _parked_state_home_dir is not None:
        shutil.rmtree(_parked_state_home_dir, ignore_errors=True)
    _parked_state_home_dir = None
    _prior_state_home = None
    _state_home_parked = False
