"""The gate cannot be starved into a false allow: every protected class has a fixture that must deny."""
from __future__ import annotations

import sys
import unittest
from unittest import mock
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_evals, godmode_sentinel  # noqa: E402


class MetaGateTests(unittest.TestCase):
    def test_every_category_has_a_fixture(self) -> None:
        # "unclassified-mutation" has no `_TIER_BY_CATEGORY` row (it takes
        # the fallback) and `classify_action` itself never returns it (confirmed by
        # source scan: the string appears in `godmode_sentinel.py` only in
        # comments and in the tier table's own row - no return site
        # assigns it). It is not dead code overall -
        # `hooks/godmode_session_hook.py`'s "no operation described" path
        # still constructs it directly, so it is live at the hook layer -
        # but no command-shaped fixture can reach it through
        # `classify_action`, the only entry point this suite calls, so it
        # is excluded rather than faked.
        categories = {
            c for c, tier in godmode_sentinel._TIER_BY_CATEGORY.items()
            if tier in {"R2", "R3", "R4", "R5"} and c not in godmode_evals._RETIRED_CATEGORIES
        }
        self.assertEqual(categories - set(godmode_evals.META_FIXTURES), set())

    def test_all_cells_pass_on_head(self) -> None:
        cells = godmode_evals.meta_gate_cells(PLUGIN_ROOT)
        failing = [c for c in cells if c["outcome"] != "pass"]
        self.assertEqual(failing, [], failing)

    def test_removing_any_floor_turns_its_cell_red(self) -> None:
        """Every protected category's tier comes from its own row, not the
        fallback. The fallback is swapped for a tier no fixture carries, so
        a row equal to the real fallback (R3) is as observable as any
        other: removing it turns its own cell red."""
        for victim in sorted(godmode_evals.META_FIXTURES):
            with self.subTest(victim=victim):
                table = dict(godmode_sentinel._TIER_BY_CATEGORY)
                table.pop(victim)
                with mock.patch.object(godmode_sentinel, "_TIER_BY_CATEGORY", table),                         mock.patch.object(godmode_sentinel, "_FALLBACK_TIER", _SWAPPED_FALLBACK):
                    cells = godmode_evals.meta_gate_cells(PLUGIN_ROOT)
                self.assertTrue(
                    any(c["outcome"] != "pass" and c["control"] == victim for c in cells),
                    (victim, cells),
                )

    def test_every_floor_applies_rather_than_the_fallback(self) -> None:
        """With the fallback swapped and every row in place, every cell
        still passes: no fixture's tier was the fallback's doing."""
        with mock.patch.object(godmode_sentinel, "_FALLBACK_TIER", _SWAPPED_FALLBACK):
            cells = godmode_evals.meta_gate_cells(PLUGIN_ROOT)
        self.assertEqual([c for c in cells if c["outcome"] != "pass"], [])


# No fixture is tiered R1, so a cell whose tier came from the fallback
# while this is in force cannot pass.
_SWAPPED_FALLBACK = "R1"

if __name__ == "__main__":
    unittest.main()
