"""Host events that exist and were unwired (obligation 10120, program item 3).

Cursor documents beforeSubmitPrompt, afterFileEdit, preCompact, sessionEnd
and subagentStop; Antigravity documents PreInvocation and PostToolUse;
Gemini documents AfterTool and AfterAgent. None was wired, so the prompt-,
edit- and stop-borne features had no path on those hosts. Each artifact
now declares them, routed to the hook branch that already serves the same
feature on Claude. Channel and live proof stay stated as gaps in the reach
table until a probe inside the host chronicles them.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_host_manifests as hm  # noqa: E402


def _commands(blocks):
    return [entry["command"] for block in blocks for entry in block["hooks"]]


class CursorEventsTests(unittest.TestCase):
    def test_cursor_declares_its_prompt_edit_compact_end_and_subagent_events(self) -> None:
        manifest = hm.build_cursor_manifest()
        hooks = manifest["hooks"]
        expected = {
            "beforeSubmitPrompt": "godmode_session_hook.py user-prompt",
            "afterFileEdit": "godmode_post_edit.py",
            "preCompact": "godmode_session_hook.py pre-compact",
            "sessionEnd": "godmode_session_hook.py session-end",
            "subagentStop": "godmode_session_hook.py subagent-stop",
        }
        for event, tail in expected.items():
            self.assertIn(event, hooks, event)
            self.assertTrue(any(c.endswith(tail) for c in _commands(hooks[event])),
                            (event, _commands(hooks[event])))
        self.assertEqual(set(hooks), set(hm.CURSOR_HOOK_EVENTS))


class AntigravityEventsTests(unittest.TestCase):
    def test_antigravity_declares_pre_invocation_and_post_tool_use(self) -> None:
        entry = hm.build_antigravity_fragment()["godmode"]
        self.assertIn("PreInvocation", entry)
        self.assertTrue(any(c.endswith("godmode_session_hook.py user-prompt")
                            for c in _commands(entry["PreInvocation"])))
        self.assertIn("PostToolUse", entry)
        self.assertTrue(any(c.endswith("godmode_post_edit.py")
                            for c in _commands(entry["PostToolUse"])))
        self.assertEqual(hm.antigravity_emitted_events(hm.build_antigravity_fragment()),
                         hm.ANTIGRAVITY_HOOK_EVENTS)


class GeminiEventsTests(unittest.TestCase):
    def test_gemini_declares_after_tool_and_after_agent_in_milliseconds(self) -> None:
        fragment = hm.build_gemini_fragment()
        hooks = fragment["hooks"]
        self.assertIn("AfterTool", hooks)
        self.assertIn("AfterAgent", hooks)
        after_tool = hooks["AfterTool"][0]["hooks"][0]
        after_agent = hooks["AfterAgent"][0]["hooks"][0]
        self.assertTrue(after_tool["command"].endswith("godmode_post_edit.py"))
        self.assertTrue(after_agent["command"].endswith("godmode_session_hook.py stop"))
        for entry in (after_tool, after_agent):
            self.assertGreaterEqual(entry["timeout"], 1000, "Gemini timeouts are milliseconds")
        self.assertEqual(hm.gemini_emitted_events(fragment), hm.GEMINI_HOOK_EVENTS)


if __name__ == "__main__":
    unittest.main()
