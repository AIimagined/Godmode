"""`assurance` emits the assurance-case document generated from live probes.

The document is generated from `selftest`'s own probes (never hand-authored),
so a control cannot be claimed enforced in prose without being exercised.
"""
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


class VerbAssuranceTests(unittest.TestCase):
    def test_assurance_emits_the_generated_document(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(project), "assurance"])
            payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertIn("document", payload)
        self.assertIn("# Assurance Case", payload["document"])
        self.assertIn("Controls and their evidence", payload["document"])


if __name__ == "__main__":
    unittest.main()
