"""C-56: a plan arbiter that adjudicates between competing plans.

Deterministic, and it never picks silently. Each plan is scored on what a
plan can be held to: acceptance criteria stated, verification steps named,
citations that resolve, open questions left. A tie returns `undecided`
with both scores shown - the arbiter's job is to make the difference
legible, not to break a tie the plans themselves do not break.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_arbiter import arbitrate  # noqa: E402

STRONG = """# Plan A

## Acceptance criteria
- every test in tests/test_x.py passes
- the CLI exits 0 on the corpus

## Steps
1. Write the failing test in file:tests/test_x.py
2. Implement in file:src/x.py
3. Run `python -m unittest tests.test_x` and verify the output
"""

WEAK = """# Plan B

## Steps
1. Refactor everything in file:src/does_not_exist.py
2. Maybe add tests later? TBD
3. Figure out the API (TODO)
"""


class ArbitrateTests(unittest.TestCase):
    def test_the_plan_with_criteria_and_resolving_citations_wins_with_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "tests" / "test_x.py").write_text("", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "x.py").write_text("", encoding="utf-8")
            (root / "a.md").write_text(STRONG, encoding="utf-8")
            (root / "b.md").write_text(WEAK, encoding="utf-8")
            report = arbitrate(root, [root / "a.md", root / "b.md"])
        self.assertEqual(report["verdict"], "decided")
        self.assertEqual(report["winner"], "a.md")
        a, b = report["plans"]
        self.assertGreater(a["score"], b["score"])
        self.assertTrue(a["acceptance_criteria"])
        self.assertFalse(b["acceptance_criteria"])
        self.assertEqual(b["unresolved_citations"], ["src/does_not_exist.py"])
        self.assertGreaterEqual(b["open_questions"], 2)
        self.assertTrue(report["reasons"])

    def test_identical_plans_are_undecided_not_arbitrarily_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.md").write_text(WEAK, encoding="utf-8")
            (root / "b.md").write_text(WEAK, encoding="utf-8")
            report = arbitrate(root, [root / "a.md", root / "b.md"])
        self.assertEqual(report["verdict"], "undecided")
        self.assertIsNone(report["winner"])

    def test_undecided_reaches_the_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.md").write_text(WEAK, encoding="utf-8")
            (root / "b.md").write_text(WEAK, encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(root), "arbitrate",
                                     "--plan", str(root / "a.md"), "--plan", str(root / "b.md")])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "undecided")


if __name__ == "__main__":
    unittest.main()
