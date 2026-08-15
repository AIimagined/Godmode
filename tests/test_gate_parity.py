"""The generated decision table (`hooks/gate_table.json`), checked against
the two things it must never drift from: the full sentinel (every floor
entry it names really is R0), and its own generator (regenerating it must
reproduce it byte-for-byte, json-normalized) - the parity half of U-G2/U-G3.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402

TABLE = PLUGIN_ROOT / "hooks" / "gate_table.json"
BUILDER = PLUGIN_ROOT / "scripts" / "dev" / "build_decision_table.py"
FAST_GATE = PLUGIN_ROOT / "hooks" / "godmode_gate_fast.py"

# Imported the same way tests/test_gate_fast.py does: a direct file-location
# load, not a package import - the fast gate is a hook script, not a package
# member.
_spec = importlib.util.spec_from_file_location("godmode_gate_fast", FAST_GATE)
fast = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(fast)


def payload(command: str, tool: str = "Bash") -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
    }


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


class ParityFastGate(unittest.TestCase):
    """`ParityFloor` above checks the full sentinel's side of the floor -
    every entry really is R0. That is necessary but not sufficient: nothing
    proved the FAST gate actually fast-allows those same entries against the
    same table. 13 of the 19 `read_heads` never appear as a corpus entry, so
    `test_gate_fast.py::Equivalence`'s corpus-driven check never exercises
    them either - a regression in `fast_verdict`'s handling of one of those
    heads (or a floor phrase) could land, and every existing suite would
    still be green. This closes that gap directly: every floor phrase (run
    bare) and every read head (run as `<head> somefile`, matching
    `ParityFloor.test_every_read_head_is_r0_in_full_sentinel`'s own shape)
    must fast-allow against the real, checked-in table."""

    def test_every_floor_entry_fast_allows(self) -> None:
        table = json.loads(TABLE.read_text(encoding="utf-8"))
        bad = [op for op in table["floor"]["claude-code"]
               if fast.fast_verdict(payload(op), table) != "allow"]
        self.assertEqual(bad, [])

    def test_every_read_head_fast_allows(self) -> None:
        table = json.loads(TABLE.read_text(encoding="utf-8"))
        bad = [head for head in table["read_heads"]
               if fast.fast_verdict(payload(f"{head} somefile"), table) != "allow"]
        self.assertEqual(bad, [])


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
