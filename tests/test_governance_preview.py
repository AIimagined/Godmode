"""A governance preview ends with the four sections an operator decides from."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_preview import render_preview  # noqa: E402
from godmode_runtime.godmode_sentinel import classify_action  # noqa: E402


class PreviewTests(unittest.TestCase):
    def test_four_sections_in_order(self) -> None:
        preview = classify_action("git push --force origin main")
        preview["operation"] = "git push --force origin main"
        text = render_preview(preview)
        positions = [text.index(h) for h in ("Context:", "Options:", "Resolution:", "Accepted cost:")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(preview["tier"], text.split("Accepted cost:")[1])

    def test_unprotected_names_no_capability(self) -> None:
        preview = classify_action("git status")
        preview["operation"] = "git status"
        text = render_preview(preview)
        self.assertIn("no capability", text.split("Resolution:")[1].lower())


if __name__ == "__main__":
    unittest.main()
