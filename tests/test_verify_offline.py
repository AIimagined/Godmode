"""`godmode verify --offline`: a check that dials out does not count.

Seventeenth and eighteenth field reports: a negative test the agent believed
free made a paid external call, and no gate could see it because the command
line was a test runner (check-shaped, allowed) and the spend happened inside
the process. Under `--offline` the check runs with the netgate socket audit
installed in every Python interpreter it starts and every proxy variable
pointed at a closed local port; any connection the audit sees is a finding,
and a check with findings is attested `blocked`, never `ran`. Stated gap: a
runtime that neither runs Python nor honours proxy variables is unseen, and
whether a provider refunds a cancelled call is its semantics, not this
audit's. Obligation 9792.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from godmode_runtime.godmode_attest import open_session, run_check  # noqa: E402
from tests.test_godmode_runtime import isolated_project  # noqa: E402

DIALS = ("import socket\n"
         "try:\n"
         "    socket.getaddrinfo('localhost', 80)\n"
         "except OSError:\n"
         "    pass\n"
         "print('done')\n")


class OfflineCheckTests(unittest.TestCase):
    def test_a_connection_inside_a_passing_check_blocks_it(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "test")
            outcome = run_check(archive, session, project, "dials",
                                [sys.executable, "-c", DIALS], offline=True)
            self.assertEqual(outcome["exit_code"], 0)
            self.assertFalse(outcome["passed"])
            self.assertEqual(outcome["attested"], "blocked")
            self.assertTrue(outcome["offline"]["connections"], outcome)
            self.assertIn("getaddrinfo", outcome["offline"]["connections"][0]["event"])
            self.assertIn("connection", outcome["detail"])

    def test_a_silent_check_passes_with_an_empty_audit(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "test")
            outcome = run_check(
                archive, session, project, "quiet",
                [sys.executable, "-c", "import os; print(os.environ['HTTPS_PROXY'])"],
                offline=True)
            self.assertTrue(outcome["passed"], outcome)
            self.assertEqual(outcome["offline"]["connections"], [])
            self.assertIn("127.0.0.1:9", outcome["detail"], "proxies point at a closed port")
            self.assertIn("gap", outcome["offline"])

    def test_the_default_run_carries_no_audit(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            session = open_session(archive, "test")
            outcome = run_check(archive, session, project, "dials",
                                [sys.executable, "-c", DIALS])
            self.assertTrue(outcome["passed"])
            self.assertNotIn("offline", outcome)

    def test_the_verb_exposes_the_flag(self) -> None:
        done = subprocess.run(
            [sys.executable, str(SCRIPTS / "godmode.py"), "verify", "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertIn("--offline", done.stdout)


if __name__ == "__main__":
    unittest.main()
