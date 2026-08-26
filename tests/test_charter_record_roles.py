"""A record is not a directive, whatever voice it is written in.

Field report (2026-08-27, another project): the session brief announced
"508 unattested hard rules". 308 of them came from `docs/LESSONS.md` - a
ledger of 851 lessons, many written imperatively ("never X again"), each
compiled as a HARD standing rule because the classifier reads text shape
alone. A lessons ledger, a state file, a sprint ledger, a decisions log and
an inventory are records of what happened or what exists. The roles that
carry directives are the operating guide, the operator profile, the
invariants and the checklist. A record role compiles to ADVISORY at most,
so the same sentence is HARD in CLAUDE.md and ADVISORY in LESSONS.md.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_charter import RECORD_ROLES, compile_charter  # noqa: E402

# Matches the classifier's `never ... without` HARD shape.
DIRECTIVE = "Never merge a change without a failing test first.\n"


def _rules(charter: dict, path: str) -> list[dict]:
    return [r for r in charter["compiled"] if r["source"].startswith(path)]


class RecordRoleTests(unittest.TestCase):
    def test_the_same_sentence_is_hard_in_the_guide_and_advisory_in_the_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "CLAUDE.md").write_text("# Guide\n\n" + DIRECTIVE, encoding="utf-8")
            (root / "docs" / "LESSONS.md").write_text("# Lessons\n\n- " + DIRECTIVE, encoding="utf-8")
            charter = compile_charter(root)
        guide = _rules(charter, "CLAUDE.md")
        ledger = _rules(charter, "docs/LESSONS.md")
        self.assertEqual([r["enforcement"] for r in guide], ["HARD"], guide)
        self.assertEqual([r["enforcement"] for r in ledger], ["ADVISORY"], ledger)
        self.assertEqual(ledger[0]["capped_from"], "HARD")

    def test_every_record_role_is_capped(self) -> None:
        self.assertEqual(RECORD_ROLES, frozenset(
            {"lessons", "state", "sprint-truth", "decisions", "inventory"}))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            for name in ("STATE.md", "SPRINT-SSOT.md", "DECISIONS.md",
                         "FEATURE-INVENTORY.md", "LESSONS.md"):
                (root / "docs" / name).write_text("# x\n\n- " + DIRECTIVE, encoding="utf-8")
            charter = compile_charter(root)
        self.assertEqual(charter["enforcement"]["HARD"], 0, charter["enforcement"])
        self.assertGreaterEqual(charter["rules"], 5)


if __name__ == "__main__":
    unittest.main()
