"""The generated decision table (`hooks/gate_table.json`), checked against
the two things it must never drift from: the full sentinel (every floor
entry it names really is R0), and its own generator (regenerating it must
reproduce it byte-for-byte, json-normalized) - the parity half of U-G2/U-G3.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

TABLE = PLUGIN_ROOT / "hooks" / "gate_table.json"
BUILDER = PLUGIN_ROOT / "scripts" / "dev" / "build_decision_table.py"


class ParityFloor(unittest.TestCase):
    def test_every_floor_entry_is_r0_in_full_sentinel(self) -> None:
        table = json.loads(TABLE.read_text(encoding="utf-8"))
        bad = [op for op in table["floor"]["claude-code"]
               if classify_action(op, project_root=PLUGIN_ROOT)["tier"] != "R0"]
        self.assertEqual(bad, [])

    def test_every_read_head_is_r0_in_full_sentinel(self) -> None:
        """The non-git half of the floor, held to the same standard as the
        git half above - a read head that stopped being R0 would let the
        fast gate allow what the full sentinel now asks or refuses about."""
        table = json.loads(TABLE.read_text(encoding="utf-8"))
        bad = [head for head in table["read_heads"]
               if classify_action(f"{head} somefile",
                                  project_root=PLUGIN_ROOT)["tier"] != "R0"]
        self.assertEqual(bad, [])

    def test_table_is_fresh(self) -> None:
        regenerated = subprocess.run(
            [sys.executable, str(BUILDER), "--stdout"],
            capture_output=True, text=True, timeout=60, cwd=PLUGIN_ROOT,
        )
        self.assertEqual(regenerated.returncode, 0, regenerated.stderr)
        self.assertEqual(json.loads(regenerated.stdout),
                          json.loads(TABLE.read_text(encoding="utf-8")))


class FreshnessCatchesADroppedFloorEntry(unittest.TestCase):
    """Plant: freshness must actually be capable of failing, not just pass by
    construction. The checked-in `hooks/gate_table.json` is temporarily
    overwritten with a copy missing one floor entry, `ParityFloor.
    test_table_is_fresh`'s exact comparison is re-run against that tampered
    file, and is asserted to now DISAGREE - proving the freshness check is a
    real one, not a tautology that would pass no matter what the file
    contained. The original bytes are restored in `finally`, whether the
    assertion holds or not."""

    def test_a_dropped_floor_entry_breaks_freshness(self) -> None:
        original = TABLE.read_text(encoding="utf-8")
        try:
            table = json.loads(original)
            removed = table["floor"]["claude-code"].pop()
            self.assertTrue(removed)  # sanity: something was actually removed
            TABLE.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")

            regenerated = subprocess.run(
                [sys.executable, str(BUILDER), "--stdout"],
                capture_output=True, text=True, timeout=60, cwd=PLUGIN_ROOT,
            )
            self.assertEqual(regenerated.returncode, 0, regenerated.stderr)
            # This is the same assertion `ParityFloor.test_table_is_fresh`
            # makes - run here against the tampered file, it must fail to
            # hold (assertRaises), which is the freshness test actually
            # catching the planted defect.
            with self.assertRaises(AssertionError):
                self.assertEqual(json.loads(regenerated.stdout),
                                  json.loads(TABLE.read_text(encoding="utf-8")))
        finally:
            TABLE.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
