"""Branch complexity: decision points + 1, hand-verified, deterministic."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_metrics import branch_complexity  # noqa: E402

FIXTURE = '''
def flat():
    return 1

def branchy(x, items):
    if x and items:            # +1 if, +1 bool-op
        for item in items:     # +1
            try:
                x = item or x  # +1 bool-op
            except ValueError: # +1
                pass
    return [i for i in items if i]  # +1 comprehension filter
'''


class BranchComplexityTests(unittest.TestCase):
    def test_hand_verified_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sample.py").write_text(FIXTURE, encoding="utf-8")
            report = branch_complexity(Path(tmp))
            by_name = {f["function"]: f["complexity"] for f in report["worst"]}
            self.assertEqual(by_name["flat"], 1)
            self.assertEqual(by_name["branchy"], 7)

    def test_worst_first_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "sample.py").write_text(FIXTURE, encoding="utf-8")
            first = branch_complexity(Path(tmp))
            second = branch_complexity(Path(tmp))
            self.assertEqual(first, second)
            self.assertEqual(first["worst"][0]["function"], "branchy")

    def test_ignored_directories_stay_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hidden = Path(tmp) / "node_modules"
            hidden.mkdir()
            (hidden / "dep.py").write_text(FIXTURE, encoding="utf-8")
            report = branch_complexity(Path(tmp))
            self.assertEqual(report["functions_counted"], 0)


if __name__ == "__main__":
    unittest.main()
