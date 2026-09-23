"""Strip every host-detection marker from the environment for a test.

Eighth and tenth field reports 2026-09-05: running the suite inside a Grok
session (GROK_PLUGIN_ROOT, GROK_HOOK_EVENT) or an Antigravity session
(ANTIGRAVITY_AGENT, ANTIGRAVITY_CONVERSATION_ID) made Claude- and
Codex-shaped tests detect the ambient host - 31 failures in one run. Host
detection reads the environment on purpose; the tests must not inherit
whatever the runner exported.

Fix round 1 (NS-10k, task-14-review.md B1): the same problem, one layer
deeper. `godmode_sentinel.attended()` reads `CI` directly, and GitHub
Actions sets `CI=true` for every step with no scrubbing
(`.github/workflows/godmode-verify.yml`). A hook test that inherits
`os.environ` into a subprocess, or an in-process broker test that calls
`issue()`/`grant()` directly, silently flips onto the unattended row the
instant it runs in CI - green locally (no `CI`), red only after push.
`scrubbed_environment` strips `CI` and forces `GODMODE_ATTENDED=1`, so
every test built on it - attended or not - starts from a pinned, known row
rather than whatever the runner's own environment happens to carry. This
is opt-in per module: only a module that imports `scrubbed_environment` (or
`scrubbed_env`, its plain-dict sibling for building an explicit
subprocess `env=`) gets the pin: `.github/workflows/godmode-verify.yml`
also sets `GODMODE_ATTENDED: "1"` in the job env as a second, suite-wide
layer, since the CI runner's own `CI=true` would otherwise reach any module
that does not import from here (`tests/test_attendance_scrub.py` names the
ones its static scan can see - see the round-2 and round-3 paragraphs below
for what that scan cannot, which is why the job-wide layer exists at all).

Fix round 2 (NS-10k, task-14-rereview.md B1): "every module built on it"
undersold how many call sites drive the hook without importing either
helper - `tests/test_observe_mode.py` and `tests/test_launcher_root_fallback.py`
now do (fixed this round), and the six `HOST_MARKERS`-only modules
(`test_advisory_channel`, `test_antigravity_allow`, `test_cursor_stop`,
`test_hook_stdin`, `test_launcher_isolation`, `test_subagent_stop`) plus
`test_turn_tripwires` now build their explicit subprocess `env=` from
`scrubbed_env()` instead of filtering `HOST_MARKERS` by hand. A test that
specifically wants the unattended row passes `CI="1"` or
`GODMODE_ATTENDED="0"` as `extra` (see `scrubbed_env`'s docstring for why
`CI="1"` alone is enough now). `tests/test_attendance_scrub.py` scans for
modules that spawn a hook via `subprocess` (directly, or through a helper
function's parameter) with neither helper imported and used - a static,
best-effort accounting of what this scan can prove, not a guarantee that
every indirection is covered (an in-process `attended()` call with no
subprocess involved is outside what it looks for at all).

Fix round 3 (NS-10k, task-14-rereview2.md B-A): `GODMODE_ATTENDED` is the
*first* signal `attended()` reads, ahead of `CI` - `.github/workflows/
godmode-verify.yml` sets it job-wide as a second, suite-wide layer for
modules that never call `scrubbed_env`/`scrubbed_environment` at all, but
under the old `_ATTENDANCE_MARKERS = ("CI",)` that same ambient value
survived a scrubbed module's own `clear=True` patch (`os.environ` is
cleared and replaced with a dict built from `os.environ`, so an unscrubbed
key rides along), and `attended()` read it before the scrub's own `CI`
handling ever got a look. A scrubbed module run under that job env was
pinned attended by accident, not by the pin below, and the `CI="1"` escape
hatch (R2) was silently defeated on the one machine the job env exists
for. `GODMODE_ATTENDED` now scrubs alongside `CI`, so the pin decides
either way, on every machine.
"""
from __future__ import annotations

import os
from unittest import mock

HOST_MARKERS = (
    "GODMODE_HOST", "GROK_AGENT", "GROK_PLUGIN_ROOT", "GROK_HOOK_EVENT",
    "CLAUDE_CODE_ENTRYPOINT", "PLUGIN_ROOT", "ANTIGRAVITY_AGENT",
    "ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_PROJECT_ID",
    "COPILOT_AGENT", "CODEX_SANDBOX", "GEMINI_CLI",
)

# Read directly by `godmode_sentinel.attended()`, not a host marker in the
# sense above (no host sets it to identify itself) - scrubbed here anyway
# because a CI runner (`CI`) or the verify job's own env
# (`GODMODE_ATTENDED`, fix round 3) sets it ambiently and the harness must
# not inherit either.
_ATTENDANCE_MARKERS = ("CI", "GODMODE_ATTENDED")


def scrubbed_env(**extra: str) -> dict:
    """A plain environment dict with every host marker and ambient
    attendance signal removed, pinned to the attended row
    (`GODMODE_ATTENDED=1`), then `extra` layered on last. Use this to build
    an explicit `env=` for a single subprocess call; use
    `scrubbed_environment` instead to patch the current process's
    `os.environ` (e.g. so a call with no `env=` inherits the scrub too).

    Fix round 2 (NS-10k, task-14-rereview.md R2): the attended pin used to
    be set unconditionally and `extra` applied on top of it, so
    `scrubbed_env(CI="1")` still carried `GODMODE_ATTENDED=1` alongside the
    requested `CI=1` - and `attended()` checks `GODMODE_ATTENDED` first, so
    the override never took effect. A caller naming `CI` or
    `GODMODE_ATTENDED` in `extra` is asking for the unattended row (or an
    explicit attended one); the pin is dropped in that case so `extra`
    alone decides, instead of losing silently to a pin `attended()` reads
    first.
    """
    environment = {
        k: v for k, v in os.environ.items()
        if k not in HOST_MARKERS and k not in _ATTENDANCE_MARKERS
    }
    if "CI" not in extra and "GODMODE_ATTENDED" not in extra:
        environment["GODMODE_ATTENDED"] = "1"
    environment.update(extra)
    return environment


def scrubbed_environment(**extra: str) -> mock._patch_dict:
    """A `mock.patch.dict(os.environ, ...)` built from `scrubbed_env(**extra)`
    - see its docstring for the attendance-pin/`extra` interaction. Use as a
    context manager or start()/stop()."""
    return mock.patch.dict(os.environ, scrubbed_env(**extra), clear=True)
