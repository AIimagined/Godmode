"""Approval quality as a measurable property, from records already written.

The host-approval rows capture what the operator's host approved beside
what godmode decided. A long unbroken streak of approvals with zero
denials is the signature of rubber-stamping - approval running on
automation bias rather than judgment. The pulse names it once, as an
advisory: either widen bounded autonomy deliberately (policy) or slow
the asks down. Never a judgment of any single decision, and honest-empty
when there is too little data to say anything.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS, PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_hostapproval import record_host_approval  # noqa: E402
from godmode_runtime.godmode_metrics import oversight_pulse  # noqa: E402


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-pulse-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield archive


def _approve(archive, index: int, approved: bool = True) -> None:
    record_host_approval(
        archive, host="claude", tool="Bash",
        operation=f"operation number {index}",
        approval_context={"approved": approved},
        godmode_decision="ask")


class OversightPulseTests(unittest.TestCase):
    def test_a_long_unbroken_approval_streak_draws_the_advisory(self) -> None:
        with _archive() as archive:
            for index in range(8):
                _approve(archive, index)
            pulse = oversight_pulse(archive)
            self.assertEqual(pulse["approvals_seen"], 8)
            self.assertEqual(pulse["recent_streak"], 8)
            self.assertIn("automation", pulse["advisory"])

    def test_one_denial_breaks_the_streak(self) -> None:
        with _archive() as archive:
            for index in range(5):
                _approve(archive, index)
            _approve(archive, 5, approved=False)
            for index in range(6, 9):
                _approve(archive, index)
            pulse = oversight_pulse(archive)
            self.assertEqual(pulse["recent_streak"], 3)
            self.assertIsNone(pulse["advisory"])

    def test_too_little_data_is_honest_empty(self) -> None:
        with _archive() as archive:
            for index in range(3):
                _approve(archive, index)
            pulse = oversight_pulse(archive)
            self.assertIsNone(pulse["advisory"])

    def test_no_approval_rows_at_all(self) -> None:
        with _archive() as archive:
            pulse = oversight_pulse(archive)
            self.assertEqual(pulse["approvals_seen"], 0)
            self.assertIsNone(pulse["advisory"])


if __name__ == "__main__":
    unittest.main()
