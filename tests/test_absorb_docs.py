"""The door through the adoption wall: a status-shaped markdown file
becomes proposed status items.

Dry-run by default (the mapping is shown, nothing written); --write
records the items through the same record_item path status set uses.
Checkboxes carry state: checked is done, unchecked is pending; headings
scope the titles. Godmode still never rewrites the file - it becomes a
view the moment the store owns the truth, but that switch is the
operator's edit, not this verb's.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_status import absorb_docs  # noqa: E402

DOC = """# Sprint SSOT

## Engine work
- [ ] wire the parser to the new lexer
- [x] ship the tokenizer rewrite

## Cleanup
- [ ] delete the legacy adapter
"""


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-absorbdocs-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


class AbsorbDocsTests(unittest.TestCase):
    def test_dry_run_maps_without_writing(self) -> None:
        with _project() as (root, archive):
            doc = root / "SPRINT-SSOT.md"
            doc.write_text(DOC, encoding="utf-8")
            report = absorb_docs(archive, doc, write=False)
            self.assertEqual(report["proposed"], 3)
            self.assertEqual(report["written"], 0)
            titles = [item["title"] for item in report["items"]]
            self.assertIn("wire the parser to the new lexer", titles)
            states = {item["title"]: item["state"] for item in report["items"]}
            self.assertEqual(states["ship the tokenizer rewrite"], "review")
            self.assertEqual(states["delete the legacy adapter"], "proposed")
            self.assertFalse(any(True for r in archive.read_events(verify=False)
                                 if r.get("kind") == "sprint"))

    def test_write_records_items_with_section_scope(self) -> None:
        with _project() as (root, archive):
            doc = root / "SPRINT-SSOT.md"
            doc.write_text(DOC, encoding="utf-8")
            report = absorb_docs(archive, doc, write=True)
            self.assertEqual(report["written"], 3)
            recorded = [r for r in archive.read_events(verify=False)
                        if r.get("kind") == "sprint"]
            self.assertEqual(len(recorded), 3)
            subjects = " ".join(r["subject"] for r in recorded)
            self.assertIn("engine-work", subjects)

    def test_a_file_with_no_items_is_a_stated_gap(self) -> None:
        with _project() as (root, archive):
            doc = root / "NOTES.md"
            doc.write_text("just prose, no checkboxes\n", encoding="utf-8")
            report = absorb_docs(archive, doc, write=False)
            self.assertEqual(report["proposed"], 0)
            self.assertIn("no status-shaped items", report["note"])


if __name__ == "__main__":
    unittest.main()
