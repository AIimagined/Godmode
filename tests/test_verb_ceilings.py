"""`ceilings` refuses reported spend that crosses a declared run ceiling."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class VerbCeilingsTests(unittest.TestCase):
    def test_spend_over_a_declared_ceiling_is_reported_exceeded(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tool_calls": 10}), encoding="utf-8"
            )
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(
                    ["--project", str(project), "ceilings", "--spent", "tool_calls=20"]
                )
            payload = json.loads(out.getvalue())
        self.assertEqual(code, 1, payload)
        self.assertEqual(payload["verdict"], "over-ceiling")
        self.assertEqual(
            [entry["ceiling"] for entry in payload["exceeded"]], ["tool_calls"]
        )

    def test_spend_within_declared_ceilings_is_not_exceeded(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            (project / ".godmode-ceilings.json").write_text(
                json.dumps({"tool_calls": 100}), encoding="utf-8"
            )
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(
                    ["--project", str(project), "ceilings", "--spent", "tool_calls=5"]
                )
            payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "within-ceilings")
        self.assertEqual(payload["exceeded"], [])


if __name__ == "__main__":
    unittest.main()
