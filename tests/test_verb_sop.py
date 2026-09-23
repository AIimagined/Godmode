"""`sop` reports T0-T14 troubleshooting status ordered by the sequence, not by
what happens to be attested, and records an attestation against one step."""
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

from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class VerbSopTests(unittest.TestCase):
    def test_status_starts_at_t0_with_nothing_attested(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "sop-test")
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(
                    ["--project", str(project), "sop", "--session", session]
                )
            payload = json.loads(out.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "in-progress")
        self.assertEqual(payload["next"], "T0")
        self.assertIn("T0", payload["missing"])

    def test_attesting_a_step_moves_it_out_of_missing(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "sop-test")
            attest_out = io.StringIO()
            with mock.patch.object(sys, "stdout", attest_out), mock.patch.object(sys, "stderr", io.StringIO()):
                attest_code = console.main([
                    "--project", str(project), "sop",
                    "--session", session, "--attest", "T0", "--result", "reproduced",
                ])
            attest_payload = json.loads(attest_out.getvalue())
            self.assertEqual(attest_code, 0, attest_payload)
            self.assertEqual(attest_payload["record"]["subject"], "sop:T0")

            # The claim the test's name makes: re-reading status after the
            # attestation must show T0 gone from `missing` and no longer next.
            status_out = io.StringIO()
            with mock.patch.object(sys, "stdout", status_out), mock.patch.object(sys, "stderr", io.StringIO()):
                status_code = console.main(
                    ["--project", str(project), "sop", "--session", session]
                )
            status_payload = json.loads(status_out.getvalue())
        self.assertEqual(status_code, 0, status_payload)
        self.assertNotIn("T0", status_payload["missing"])
        self.assertNotEqual(status_payload["next"], "T0")


if __name__ == "__main__":
    unittest.main()
