"""Environment markers must survive real separator characters.

Found by an adversarial sweep: `\\bproduction\\b` does NOT match
`production_backup`, because `_` is a word character and there is no
boundary between them. `localhost:5432/production_backup` therefore
classified as *development* - and development is the one tier where
`mutation_allowed_without_capability` is True. A production database
reachable on localhost was the exact inversion the classifier exists to
prevent, and it was reachable through a hostname anyone might really use.

The fix widens the boundary to any non-alphanumeric edge, which keeps the
important negative: `my-product-catalog` must never read as production
just because `product` starts with `prod`.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_reconcile import classify_environment  # noqa: E402


class SeparatorBoundaryTests(unittest.TestCase):
    def test_underscore_separated_production_is_production(self) -> None:
        v = classify_environment("localhost:5432/production_backup")
        self.assertEqual(v["environment"], "production")
        self.assertFalse(v["mutation_allowed_without_capability"])

    def test_common_abbreviation_is_production(self) -> None:
        self.assertEqual(
            classify_environment("postgres://prd-orders.internal")["environment"],
            "production")

    def test_a_word_merely_starting_with_prod_is_not_production(self) -> None:
        # The negative that makes the widened boundary safe rather than
        # merely stricter: 'product', 'productivity', 'reproduce' are
        # ordinary words, not environment markers.
        for target in ("my-product-catalog.internal",
                       "productivity-tools.example",
                       "reproduce-bug-42.example"):
            self.assertEqual(classify_environment(target)["environment"],
                             "unknown", target)


class PrecedenceTests(unittest.TestCase):
    def test_a_conflicting_target_resolves_to_the_stricter_tier(self) -> None:
        # 'staging-prod-mirror' carries both markers; production wins, which
        # is the asymmetric-cost choice the module documents.
        v = classify_environment("postgres://staging-prod-mirror.internal")
        self.assertEqual(v["environment"], "production")
        self.assertFalse(v["mutation_allowed_without_capability"])

    def test_an_unnamed_target_still_fails_closed(self) -> None:
        v = classify_environment("postgres://10.0.0.5/orders")
        self.assertEqual(v["environment"], "unknown")
        self.assertFalse(v["mutation_allowed_without_capability"])
        self.assertFalse(v["overridable"])

    def test_ordinary_development_targets_are_unaffected(self) -> None:
        for target in ("localhost:5432/app", "dev.example.internal/orders"):
            v = classify_environment(target)
            self.assertEqual(v["environment"], "development", target)
            self.assertTrue(v["mutation_allowed_without_capability"], target)


if __name__ == "__main__":
    unittest.main()
