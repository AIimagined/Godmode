"""A non-finite metric is a stop, named as one.

Absorbed 2026-08-27 from an upstream experiment loop's "NaN fast-fail":
a metric that reads NaN or infinity is not a plateau and not progress; it
is a run that has lost the ability to measure itself, and the stop
algebra had no predicate for it. `MetricPlateau` skipped unparsable
values silently. `NonFinite` fires on the first one and says which.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_stop import MetricPlateau, NonFinite, Or  # noqa: E402


def _obs(value) -> dict:
    return {"sequence": 1, "kind": "experiment", "data": {"loss": value}}


class NonFiniteTests(unittest.TestCase):
    def test_nan_fires_and_names_the_metric(self) -> None:
        reason = NonFinite("loss")([_obs(float("nan"))])
        self.assertIsNotNone(reason)
        self.assertIn("loss", reason)
        self.assertIn("nan", reason.lower())

    def test_infinity_fires(self) -> None:
        self.assertIsNotNone(NonFinite("loss")([_obs(float("-inf"))]))

    def test_finite_and_absent_do_not_fire(self) -> None:
        stop = NonFinite("loss")
        self.assertIsNone(stop([_obs(0.5), _obs("0.25")]))
        self.assertIsNone(stop([{"sequence": 2, "kind": "action", "data": {}}]))

    def test_composes_with_plateau_in_the_algebra(self) -> None:
        stop = Or(NonFinite("loss"), MetricPlateau("loss", eps=0.01, patience=3))
        self.assertIsNone(stop([_obs(1.0), _obs(0.9)]))
        self.assertIn("NonFinite", stop([_obs(float("nan"))]))


if __name__ == "__main__":
    unittest.main()
