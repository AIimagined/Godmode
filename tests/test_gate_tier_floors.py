"""Every row of the gate's tier table decides a real verdict.

`tests/test_meta_gate.py` pins the protected rows (R2-R5) through the meta
gate's fixtures. This module pins the rest - the unprotected rows, whose
tier the approver never sees but the ledger records - and checks that no
row is left without a pin, so a row can no longer sit in the table equal
to the fallback and change nothing when it is deleted.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_evals, godmode_sentinel  # noqa: E402

# Unprotected rows: one command each, the tier typed by hand.
LOW_TIER_PINS: dict[str, tuple[str, dict, str]] = {
    "read-only-inspection": ("git status", {}, "R0"),
    "local-compute-or-state": ("python build_tool.py", {}, "R1"),
    "git-branch-create": ("git checkout -b feature-x", {}, "R1"),
    "interpreter-inline-read-only": ('python -c "print(1)"', {"inline_scan": True}, "R1"),
}

# Rows decided outside `classify_action`, each pinned where it is read.
PINNED_ELSEWHERE = {
    # Read by the Edit/Write loop in `hooks/godmode_session_hook.py`;
    # `tests/test_two_reversals.py` asserts the verdict carries R2.
    "fix-loop-reversal",
}

# A tier none of the pins above carries, swapped in for the fallback.
_SWAPPED_FALLBACK = "R4"


def _verdict(command: str, kwargs: dict) -> dict:
    return godmode_sentinel.classify_action(command, project_root=PLUGIN_ROOT, **kwargs)


class TierFloorTests(unittest.TestCase):
    def test_every_row_is_pinned(self) -> None:
        pinned = set(godmode_evals.META_FIXTURES) | set(LOW_TIER_PINS) | PINNED_ELSEWHERE
        self.assertEqual(set(godmode_sentinel._TIER_BY_CATEGORY) - pinned, set())

    def test_each_pin_lands_in_its_category(self) -> None:
        for category, (command, kwargs, tier) in LOW_TIER_PINS.items():
            with self.subTest(category=category):
                verdict = _verdict(command, kwargs)
                self.assertEqual(verdict["category"], category, verdict)
                self.assertEqual(verdict["tier"], tier, verdict)

    def test_the_row_decides_not_the_fallback(self) -> None:
        with mock.patch.object(godmode_sentinel, "_FALLBACK_TIER", _SWAPPED_FALLBACK):
            for category, (command, kwargs, tier) in LOW_TIER_PINS.items():
                with self.subTest(category=category):
                    self.assertEqual(_verdict(command, kwargs)["tier"], tier)

    def test_removing_a_row_changes_its_verdict(self) -> None:
        for category, (command, kwargs, tier) in LOW_TIER_PINS.items():
            with self.subTest(category=category):
                table = dict(godmode_sentinel._TIER_BY_CATEGORY)
                table.pop(category)
                with mock.patch.object(godmode_sentinel, "_TIER_BY_CATEGORY", table), \
                        mock.patch.object(godmode_sentinel, "_FALLBACK_TIER", _SWAPPED_FALLBACK):
                    self.assertEqual(_verdict(command, kwargs)["tier"], _SWAPPED_FALLBACK)

    def test_a_category_with_no_row_takes_the_fallback(self) -> None:
        """`unknown-command` has no row on purpose."""
        self.assertNotIn("unknown-command", godmode_sentinel._TIER_BY_CATEGORY)
        verdict = _verdict("frobnicate > /etc/hosts", {})
        self.assertEqual(verdict["category"], "unknown-command")
        self.assertEqual(verdict["tier"], "R3")
        with mock.patch.object(godmode_sentinel, "_FALLBACK_TIER", _SWAPPED_FALLBACK):
            self.assertEqual(_verdict("frobnicate > /etc/hosts", {})["tier"], _SWAPPED_FALLBACK)


if __name__ == "__main__":
    unittest.main()
