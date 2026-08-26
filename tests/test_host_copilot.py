"""VS Code Copilot is a host, detected the way it actually presents.

Absorbed 2026-08-27 from an upstream plugin's fix: VS Code Copilot never
sets `COPILOT_PLUGIN_DATA`; it sets `CLAUDE_PLUGIN_ROOT` pointing into a
`.vscode/agent-plugins/` install path, and nothing else. Before this,
that read as "unknown" here and as "claude" in tools that keyed on the
plugin root alone. `current_host` and `detect_host` share one chain, so
the two can never disagree about which host a record was produced for.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_anchor import current_host  # noqa: E402
from godmode_runtime.godmode_hostevent import detect_host  # noqa: E402

_CLEAR = {"GODMODE_HOST": "", "GROK_AGENT": "", "CLAUDE_CODE_ENTRYPOINT": "",
          "COPILOT_PLUGIN_DATA": "", "CLAUDE_PLUGIN_ROOT": ""}


def _env(**values: str):
    env = {k: v for k, v in {**_CLEAR, **values}.items() if v}
    cleared = {k: "" for k in _CLEAR}
    return mock.patch.dict(os.environ, {**cleared, **env}, clear=False)


class CopilotHostTests(unittest.TestCase):
    def test_copilot_plugin_data_reads_as_copilot(self) -> None:
        with _env(COPILOT_PLUGIN_DATA="C:/x/copilot-data"):
            self.assertEqual(current_host(), "copilot")
            self.assertEqual(detect_host({}), "copilot")

    def test_vscode_agent_plugins_root_alone_reads_as_copilot(self) -> None:
        with _env(CLAUDE_PLUGIN_ROOT="C:/Users/me/.vscode/agent-plugins/godmode"):
            self.assertEqual(current_host(), "copilot")
            self.assertEqual(detect_host({}), "copilot")

    def test_claude_code_still_wins_when_it_declares_itself(self) -> None:
        with _env(CLAUDE_CODE_ENTRYPOINT="cli",
                  CLAUDE_PLUGIN_ROOT="C:/Users/me/.claude/plugins/cache/x"):
            self.assertEqual(current_host(), "claude")
            self.assertEqual(detect_host({}), "claude")

    def test_a_plugin_root_outside_vscode_is_not_copilot(self) -> None:
        with _env(CLAUDE_PLUGIN_ROOT="C:/Users/me/.claude/plugins/cache/x"):
            self.assertEqual(current_host(), "unknown")


if __name__ == "__main__":
    unittest.main()
