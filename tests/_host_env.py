"""Strip every host-detection marker from the environment for a test.

Eighth and tenth field reports 2026-09-05: running the suite inside a Grok
session (GROK_PLUGIN_ROOT, GROK_HOOK_EVENT) or an Antigravity session
(ANTIGRAVITY_AGENT, ANTIGRAVITY_CONVERSATION_ID) made Claude- and
Codex-shaped tests detect the ambient host - 31 failures in one run. Host
detection reads the environment on purpose; the tests must not inherit
whatever the runner exported.
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


def scrubbed_environment(**extra: str) -> mock._patch_dict:
    """A `mock.patch.dict(os.environ, ...)` that removes every host marker
    and then applies `extra`. Use as a context manager or start()/stop()."""
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment.update(extra)
    return mock.patch.dict(os.environ, environment, clear=True)
