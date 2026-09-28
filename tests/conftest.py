"""pytest-only session setup: isolate the operator's policy layers once.

`tests/_gate_mode_isolation.py` parks the checkout's
`.godmode-authorization-policy.json` and points `GODMODE_STATE_HOME` at an
empty directory so hook-subprocess tests see the shipped default posture,
not whatever this operator has declared. Modules used to do that each for
themselves; here it is done once for the whole run, and the modules' own
calls stay valid because the helper nests (one frame per park, popped by
the matching restore).

`python -m unittest discover` never loads this file; there the modules'
own `setUpModule`/`tearDownModule` calls do the same work per module.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The same import spelling the modules use, so every park and restore in
# the run shares one frame stack.
from tests._gate_mode_isolation import park_local_policy, restore_local_policy  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_operator_policy():
    park_local_policy()
    try:
        yield
    finally:
        restore_local_policy()
