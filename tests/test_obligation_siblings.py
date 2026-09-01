"""Obligations that are the same duty in different clothes.

Field report, 2026-09-01 (second project): a version-bearing subject
("live-verify 0.7.109", "live-verify at 0.8.17") mints a NEW obligation
every bump, subject-keyed supersession never links them, and the turn
nag surfaces the corpses beside the living one - accumulating where it
should supersede. Two fixes: the nag collapses salient-term siblings to
the newest, and recording an obligation that overlaps an open one draws
an advisory naming the elder so it gets closed or superseded on the spot.
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
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "hooks", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_session_hook import _open_obligations_touched  # noqa: E402


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-oblsib-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield archive


class SiblingCollapseTests(unittest.TestCase):
    def test_the_nag_surfaces_only_the_newest_sibling(self) -> None:
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.7.109",
                           {"value": "run the live verify pass against the engine"})
            archive.append("obligation", "live-verify engine version 0.8.17",
                           {"value": "run the live verify pass against the engine"})
            archive.append("obligation", "live-verify engine version 0.8.22",
                           {"value": "run the live verify pass against the engine"})
            touched = _open_obligations_touched(
                archive, "next step is the live verify pass against the engine build")
            self.assertEqual(touched, ["live-verify engine version 0.8.22"])

    def test_unrelated_obligations_still_both_surface(self) -> None:
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.8.22",
                           {"value": "run the live verify pass against the engine"})
            archive.append("obligation", "ledger fed per research sweep",
                           {"value": "every shared source lands in the ledger"})
            touched = _open_obligations_touched(
                archive, "ran the live-verify engine version pass and fed the "
                         "research ledger with the shared source")
            self.assertEqual(len(touched), 2)


class RecordTimeAdvisoryTests(unittest.TestCase):
    def test_recording_a_sibling_draws_the_advisory(self) -> None:
        from godmode_runtime.godmode_mistakes import obligation_sibling_advisory
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.8.17",
                           {"value": "run the live verify pass against the engine"})
            advisory = obligation_sibling_advisory(
                archive, "live-verify engine version 0.8.22",
                "run the live verify pass against the engine")
            self.assertIn("0.8.17", advisory)
            self.assertIn("supersede", advisory)

    def test_a_closed_elder_draws_nothing(self) -> None:
        from godmode_runtime.godmode_mistakes import obligation_sibling_advisory
        with _archive() as archive:
            archive.append("obligation", "live-verify engine version 0.8.17",
                           {"value": "run the live verify pass",
                            "status": "closed"})
            advisory = obligation_sibling_advisory(
                archive, "live-verify engine version 0.8.22",
                "run the live verify pass against the engine")
            self.assertIsNone(advisory)


if __name__ == "__main__":
    unittest.main()
