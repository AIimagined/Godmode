"""The swallow ratchet holds at the preflight gate (obligation 10273).

The scanner and its committed baseline existed; nothing at the gate read
them, so a count could rise on a push. A file whose swallow count exceeds
its committed ceiling is a mechanical finding now, named with the remedy.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_preflight import swallow_ratchet_finding  # noqa: E402
from godmode_runtime.godmode_swallow import BASELINE_FILENAME  # noqa: E402


class SwallowRatchetGateTests(unittest.TestCase):
    def test_a_count_above_the_committed_ceiling_is_a_mechanical_finding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / BASELINE_FILENAME).write_text(json.dumps({"counts": {}}), encoding="utf-8")
            (project / "leaky.py").write_text(
                "def f():\n    try:\n        g()\n    except Exception:\n        pass\n",
                encoding="utf-8")
            finding = swallow_ratchet_finding(project)
            self.assertIsNotNone(finding)
            self.assertEqual(finding["check"], "swallow-ratchet")
            self.assertIn("leaky.py", finding["detail"])
            self.assertIn("swallow-ok", finding["detail"])

    def test_a_clean_tree_raises_no_finding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            (project / BASELINE_FILENAME).write_text(json.dumps({"counts": {}}), encoding="utf-8")
            (project / "tidy.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            self.assertIsNone(swallow_ratchet_finding(project))

    def test_this_repository_holds_its_own_ratchet(self) -> None:
        self.assertIsNone(swallow_ratchet_finding(PLUGIN_ROOT))


if __name__ == "__main__":
    unittest.main()
