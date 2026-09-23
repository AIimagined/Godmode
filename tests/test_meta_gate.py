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
        # "unclassified-mutation" sits in `_TIER_BY_CATEGORY` as a numeric
        # floor but `classify_action` itself never returns it (confirmed by
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

    def test_removing_a_load_bearing_rule_turns_its_cell_red(self) -> None:
        """Every category whose literal fixture tier differs from R3 - the
        fallback `_risk_tier` (`godmode_sentinel.py`) returns for a row
        `_TIER_BY_CATEGORY` does not name - turns its own cell red when
        that row is removed, with one verified exception:
        `password-in-transcript` is tiered by a hardcoded literal in an
        early `classify_action` return (the `_PASSWORD_PIPED_LITERAL`
        check) that never reads `_TIER_BY_CATEGORY` at all, so removing its
        row changes nothing. It is not silently dropped from coverage -
        it is named and independently verified green in
        `test_undetectable_categories_are_exactly_the_known_blind_spot`
        below.
        """
        detectable = {
            category for category, fixtures in godmode_evals.META_FIXTURES.items()
            if fixtures[0]["tier"] != "R3"
        } - {"password-in-transcript"}
        for victim in sorted(detectable):
            with self.subTest(victim=victim):
                table = dict(godmode_sentinel._TIER_BY_CATEGORY)
                table.pop(victim)
                with mock.patch.object(godmode_sentinel, "_TIER_BY_CATEGORY", table):
                    cells = godmode_evals.meta_gate_cells(PLUGIN_ROOT)
                self.assertTrue(
                    any(c["outcome"] != "pass" and c["control"] == victim for c in cells),
                    (victim, cells),
                )

    def test_undetectable_categories_are_exactly_the_known_blind_spot(self) -> None:
        """A category whose literal floor is already R3 - `_risk_tier`'s
        own fallback for an unmapped category - shows no observable change
        in `classify_action`'s output when its `_TIER_BY_CATEGORY` row is
        removed: the row is decorative against tampering, a real ceiling
        on this gate, not a gap in this suite's coverage.
        `password-in-transcript` joins that set for a different, verified
        reason (see the previous test's docstring). Both halves are named
        here, pinned against a literal expected set, and each is
        independently confirmed to still pass its cell after its row is
        removed - so the blind spot is recorded rather than implied.
        """
        floor_matches_fallback = {
            category for category, fixtures in godmode_evals.META_FIXTURES.items()
            if fixtures[0]["tier"] == "R3"
        }
        undetectable = floor_matches_fallback | {"password-in-transcript"}
        self.assertEqual(undetectable, {
            "agent-trust-mutation", "container-host-escape", "database-mutation",
            "git-branch-mutation", "git-history-or-remote", "hook-as-code-write",
            "process-control", "release-freeze-mutation", "scripted-source-edit",
            "unparsed-substitution", "worktree-discard", "password-in-transcript",
        })
        for victim in sorted(undetectable):
            with self.subTest(victim=victim):
                table = dict(godmode_sentinel._TIER_BY_CATEGORY)
                table.pop(victim)
                with mock.patch.object(godmode_sentinel, "_TIER_BY_CATEGORY", table):
                    cells = godmode_evals.meta_gate_cells(PLUGIN_ROOT)
                self.assertTrue(
                    all(c["outcome"] == "pass" for c in cells if c["control"] == victim),
                    (victim, cells),
                )


if __name__ == "__main__":
    unittest.main()
