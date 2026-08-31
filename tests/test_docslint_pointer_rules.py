"""Pointer rules: rules steer by the affirmative, pointers lead with the trigger."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_docslint import lint_text  # noqa: E402


def _checks(findings):
    return {f["check"] for f in findings}


class ProhibitionRuleTests(unittest.TestCase):
    def test_a_bulleted_bare_prohibition_is_flagged(self) -> None:
        findings = lint_text("GUIDE.md", "- never edit the archive by hand\n")
        self.assertIn("prohibition-without-alternative", _checks(findings))

    def test_a_prohibition_with_an_alternative_is_clean(self) -> None:
        findings = lint_text(
            "GUIDE.md",
            "- never edit the archive by hand; use `godmode remember` instead\n")
        self.assertNotIn("prohibition-without-alternative", _checks(findings))

    def test_prose_narration_is_not_a_rule(self) -> None:
        findings = lint_text("GUIDE.md", "It never leaves the machine.\n")
        self.assertNotIn("prohibition-without-alternative", _checks(findings))


class BuriedPointerTests(unittest.TestCase):
    def test_a_pointer_after_long_prose_is_flagged(self) -> None:
        line = ("When everything else in the recovery story has been tried and "
                "the archive still cannot explain the gap, see RECOVERY.md\n")
        self.assertIn("buried-pointer", _checks(lint_text("GUIDE.md", line)))

    def test_a_front_loaded_pointer_is_clean(self) -> None:
        line = "Recovery gaps: see RECOVERY.md for the rebuild steps.\n"
        self.assertNotIn("buried-pointer", _checks(lint_text("GUIDE.md", line)))


if __name__ == "__main__":
    unittest.main()
