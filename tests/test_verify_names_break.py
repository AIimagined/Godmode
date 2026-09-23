"""verify names where the chain broke: the record sequence and file line.

A tamper report that says only "broken" sends the reader to grep. The
first failing record, its file and its 1-based line are the report.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402


class VerifyNamesBreakTests(unittest.TestCase):
    def setUp(self) -> None:
        self._ctx = isolated_project()
        _project, _state, _anchor, self.archive = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)
        self.archive.initialize()
        for n in range(3):
            self.archive.append("decision", f"s{n}", {"status": "active", "value": f"v{n}"})
        self.paths = self.archive.event_paths()

    def test_intact(self) -> None:
        result = self.archive.verify()
        self.assertTrue(result["ok"])
        self.assertTrue(result["valid"])
        self.assertIsNone(result["first_broken_sequence"])
        self.assertIsNone(result["first_broken_path"])
        self.assertIsNone(result["first_broken_line"])
        self.assertEqual(result["record_count"], 3)
        self.assertEqual(result["records"], 3)

    def test_edited_field_names_second_record(self) -> None:
        path = self.paths[1]
        record = json.loads(path.read_text(encoding="utf-8"))
        record["data"]["value"] = "tampered"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        result = self.archive.verify()
        self.assertFalse(result["ok"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["first_broken_sequence"], record["sequence"])
        self.assertEqual(result["first_broken_path"], path.name)
        self.assertIsInstance(result["first_broken_line"], int)
        self.assertIn(str(record["sequence"]), result["message"])
        self.assertIn(path.name, result["message"])
        # `records` is the total landed on disk (3); `record_count` is only
        # the prefix that verified good before the break (1: just the
        # first, untouched record) - the two mean different things now.
        self.assertEqual(result["records"], 3)
        self.assertEqual(result["record_count"], 1)
        # The named line must actually be the broken field's own line, not
        # merely any line containing the text somewhere in the file.
        lines = path.read_text(encoding="utf-8").splitlines()
        named_line = lines[result["first_broken_line"] - 1]
        self.assertIn('"record_hash"', named_line)

    def test_missing_events_dir_is_intact_empty(self) -> None:
        # The project exists (resolve_anchor requires that); the archive
        # itself is simply never initialized, so its events directory is
        # never created - the missing-archive case `verify()` must read as
        # an intact, empty archive rather than an error.
        with isolated_project() as (_project, _state, _anchor, empty):
            self.assertFalse(empty.events.exists())
            result = empty.verify()
        self.assertTrue(result["ok"])
        self.assertTrue(result["valid"])
        self.assertEqual(result["record_count"], 0)
        self.assertEqual(result["records"], 0)


if __name__ == "__main__":
    unittest.main()
