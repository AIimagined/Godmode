"""`rewind` previews a rollback to a prior *verified* checkpoint, never executes it."""
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


class VerbRewindTests(unittest.TestCase):
    def test_previews_without_executing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "checkpoint", "reached a good state",
                {"status": "verified", "head": "deadbeefcafe"}, evidence=[],
            )
            seq = record["sequence"]
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(project), "rewind", "--to", str(seq)])
            payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["checkpoint"]["sequence"], seq)
        self.assertTrue(payload["protected"])
        self.assertIn("git checkout deadbeefcafe", payload["operation"])

    def test_refuses_an_unverified_checkpoint(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            record = archive.append(
                "checkpoint", "still broken", {"status": "captured"}, evidence=[],
            )
            seq = record["sequence"]
            err = io.StringIO()
            with mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", err):
                code = console.main(["--project", str(project), "rewind", "--to", str(seq)])
            error_text = err.getvalue()
        self.assertNotEqual(code, 0)
        self.assertIn("not a verified state", error_text)


if __name__ == "__main__":
    unittest.main()
