"""Registry-aware recurrence and the design-read nudge (Part 6, 2026-09-10)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_registry import (design_mentions, design_verdict_sentences,  # noqa: E402
                                              match_feedback, parse_registry)
from test_godmode_runtime import isolated_project  # noqa: E402
import godmode_session_hook as hook  # noqa: E402

REGISTRY = """# Fixed registry

| ID / KF | Symptom (user-visible) | Root cause (short) | Fix location | Guard (test / proof) | Fixed |
|---|---|---|---|---|---|
| HEAL-CONTENT-EROSION (vid-24, 2026-08-12) | The rendered MP4 end-slate showed a different drawing than the canvas; the logo art the user approved was missing from the downloaded video | heal rewrote content | lib/heal.ts | lib/__tests__/healErosion.test.ts | yes |
| AUTO-HIDE-ON-COMPLETE (2026-08-12) | The Live Status console stayed open after render completed | two branches | app/status.tsx | app/__tests__/status.test.ts | yes |
"""


class RegistryMatchTests(unittest.TestCase):
    def test_a_new_report_matches_the_row_whose_symptom_it_shares(self) -> None:
        with isolated_project() as (project, _s, _a, _archive):
            (project / "docs").mkdir()
            (project / "docs" / "FIXED-REGISTRY.md").write_text(REGISTRY, encoding="utf-8")
            rows = parse_registry(project / "docs" / "FIXED-REGISTRY.md")
            self.assertEqual([r["id"][:20] for r in rows], ["HEAL-CONTENT-EROSION", "AUTO-HIDE-ON-COMPLET"])
            matches = match_feedback("logo missing again in the downloaded video, the end slate drawing differs from canvas", rows)
            self.assertEqual(len(matches), 1, matches)
            self.assertTrue(matches[0]["id"].startswith("HEAL-CONTENT-EROSION"))
            self.assertIn("healErosion", matches[0]["guard"])
            self.assertEqual(match_feedback("please rename the helper", rows), [])

    def test_the_prompt_hook_names_the_row_once_per_session(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "docs").mkdir()
            (project / "docs" / "FIXED-REGISTRY.md").write_text(REGISTRY, encoding="utf-8")
            prompt = "the logo is missing again from the downloaded video and the end slate drawing is wrong"
            first = hook._registry_nudge(archive, project, prompt, "s1")
            self.assertIsNotNone(first)
            self.assertIn("HEAL-CONTENT-EROSION", first)
            self.assertIn("healErosion", first)
            self.assertIsNone(hook._registry_nudge(archive, project, prompt, "s1"))


class DesignReadTests(unittest.TestCase):
    def test_a_product_decision_verdict_over_an_unread_inventory_line_is_named(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "docs").mkdir()
            (project / "docs" / "INVENTORY.md").write_text(
                "# Inventory\n\n- Version chips: only edits applied by the user in the canvas or through chat "
                "count as versions; pipeline saves (generate, heal, audio) never create a version chip.\n",
                encoding="utf-8")
            reply = ("Version chips v2/v3 without edits: pipeline saves (generate, heal, audio) count as versions. "
                     "Collapse or label them is a product decision.")
            self.assertEqual(len(design_verdict_sentences(reply)), 1)
            hits = design_mentions(project, reply)
            self.assertTrue(hits and hits[0]["path"] == "docs/INVENTORY.md", hits)
            unread = project / "t.jsonl"
            unread.write_text(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": str(project / "app.tsx")}}]}}) + "\n",
                encoding="utf-8")
            notices = hook._design_read_nudge({"transcript_path": str(unread)}, reply, project)
            self.assertEqual(len(notices), 1, notices)
            self.assertIn("docs/INVENTORY.md:3", notices[0])
            read = project / "r.jsonl"
            read.write_text(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": str(project / "docs" / "INVENTORY.md")}}]}}) + "\n",
                encoding="utf-8")
            self.assertEqual(hook._design_read_nudge({"transcript_path": str(read)}, reply, project), [])


if __name__ == "__main__":
    unittest.main()
