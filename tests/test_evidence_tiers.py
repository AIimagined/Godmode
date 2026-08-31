"""Evidence tiers: rendered wording never outruns the cited evidence.

One table decides the word: `verified` is reserved for a verified state
WITH evidence; a verified state nobody cited anything for renders as
`declared` - said, not shown - so a restatement can never launder a
belief into a fact; `likely` is evidence still awaiting the verified
transition; `unproven` is neither. The renders read the table, they
never re-derive it.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_status import (  # noqa: E402
    evidence_tier,
    handover,
    items,
    record_item,
    render_view,
)
from test_godmode_runtime import isolated_project  # noqa: E402


class TierTableTests(unittest.TestCase):
    def test_verified_with_evidence_is_verified(self) -> None:
        self.assertEqual(
            evidence_tier({"state": "verified", "evidence": ["cmd:pytest"]}),
            "verified",
        )

    def test_verified_without_evidence_is_declared(self) -> None:
        # The anti-co-signing rule: a verified state nothing was cited for
        # is a statement about belief, and it renders as exactly that.
        self.assertEqual(
            evidence_tier({"state": "verified", "evidence": []}), "declared"
        )

    def test_open_with_evidence_is_likely(self) -> None:
        self.assertEqual(
            evidence_tier({"state": "active", "evidence": ["file:x.py"]}),
            "likely",
        )

    def test_open_without_evidence_is_unproven(self) -> None:
        self.assertEqual(
            evidence_tier({"state": "proposed", "evidence": []}), "unproven"
        )


class RenderTests(unittest.TestCase):
    def test_render_marks_each_item_with_its_tier(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "shown", "with proof", "verified",
                        evidence=["cmd:pytest -q"])
            record_item(archive, "said", "without proof", "verified")
            record_item(archive, "open-item", "still moving", "proposed")
            view = render_view(archive)
            self.assertIn("[verified] **shown**", view)
            self.assertIn("[declared] **said**", view)
            self.assertIn("[unproven] **open-item**", view)

    def test_handover_separates_shown_from_said(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            record_item(archive, "shown", "with proof", "verified",
                        evidence=["cmd:pytest -q"])
            record_item(archive, "said", "without proof", "verified")
            view = handover(archive, project)
            self.assertEqual(view["verified_completed"], ["shown"])
            self.assertEqual(view["declared_completed"], ["said"])

    def test_tier_survives_the_items_projection(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            record_item(archive, "x", "t", "verified", evidence=["cmd:true"])
            self.assertEqual(evidence_tier(items(archive)["x"]), "verified")


if __name__ == "__main__":
    unittest.main()
