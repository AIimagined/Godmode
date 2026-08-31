"""Both-ends mining: the certain tail feeds the fast path, the split tail feeds pins."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEV = PLUGIN_ROOT / "scripts" / "dev"
if str(DEV) not in sys.path:
    sys.path.insert(0, str(DEV))

from build_decision_table import both_ends_pick  # noqa: E402

CORPUS = (
    [{"command": "jq . file.json", "verdict": "allow"}] * 6
    + [{"command": "sed -n 1p f", "verdict": "allow"}] * 3
    + [{"command": "git checkout x", "verdict": "allow"},
       {"command": "git checkout -- .", "verdict": "deny"},
       {"command": "git checkout -b y", "verdict": "ask"}]
    + [{"command": "curl -s http://x", "verdict": "allow"},
       {"command": "curl -X POST http://x", "verdict": "ask"}]
)


class BothEndsTests(unittest.TestCase):
    def test_certain_end_is_all_allow_ranked_by_frequency(self) -> None:
        picked = both_ends_pick(CORPUS)
        heads = [c["head"] for c in picked["fast_path_candidates"]]
        self.assertEqual(heads[:2], ["jq", "sed"])
        self.assertNotIn("git", heads)
        self.assertNotIn("curl", heads)

    def test_ambiguous_end_is_ranked_by_how_split_it_is(self) -> None:
        picked = both_ends_pick(CORPUS)
        heads = [c["head"] for c in picked["pin_candidates"]]
        self.assertEqual(heads[0], "git")   # three distinct verdicts
        self.assertEqual(heads[1], "curl")  # two

    def test_empty_and_malformed_rows_are_skipped(self) -> None:
        picked = both_ends_pick([{"command": "", "verdict": "allow"},
                                 {"command": "ls", "verdict": ""}])
        self.assertEqual(picked["fast_path_candidates"], [])
        self.assertEqual(picked["pin_candidates"], [])


if __name__ == "__main__":
    unittest.main()
