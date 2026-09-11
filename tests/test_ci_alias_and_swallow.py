"""Two field reports of 2026-09-11.

Four tests green on the reference machine went red on the CI runners,
which hand the temp directory out as an 8.3 short name: the preflight
shards now run under that alias so the local gate sees what the runners
see. And an agent's throwaway query script swallowed the database's
"no such column" and printed 0 rows; the reply said the table held no
errors. A script written this session that discards an exception is
named at Stop, and a database error in tool output is an operational
error like a missing module.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_oracle import operational_error_in  # noqa: E402
from godmode_runtime.godmode_preflight import aliased_temp_environment  # noqa: E402
import godmode_session_hook as hook  # noqa: E402


class AliasedTempTests(unittest.TestCase):
    def test_the_alias_names_the_same_directory_by_another_spelling(self) -> None:
        env = aliased_temp_environment()
        if env is None:
            self.skipTest("no short name, and no junction or symlink could be made here")
        self.assertNotEqual(env["TEMP"].lower(), tempfile.gettempdir().lower())
        self.assertEqual(os.path.realpath(env["TEMP"]).lower(),
                         os.path.realpath(tempfile.gettempdir()).lower())
        self.assertEqual(env["TMP"], env["TEMP"])
        self.assertEqual(env["TMPDIR"], env["TEMP"])


class DatabaseErrorTests(unittest.TestCase):
    def test_a_schema_error_is_an_operational_error(self) -> None:
        for text in ("sqlite3.OperationalError: no such column: host",
                     'psycopg2.errors.UndefinedColumn: column "host" does not exist',
                     "no such table: kinetiq_events"):
            self.assertIsNotNone(operational_error_in(text), text)
        self.assertIsNone(operational_error_in("105 rows"))


def _transcript(path: Path, name: str, content: str) -> Path:
    entry = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"file_path": name, "content": content}}]}}
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return path


class SwallowedScriptTests(unittest.TestCase):
    def test_a_script_that_discards_its_exception_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            transcript = _transcript(
                Path(raw) / "t.jsonl", "C:/tmp/query_errors.py",
                "import sqlite3\ntry:\n    rows = conn.execute('select host from t').fetchall()\n"
                "except Exception:\n    rows = []\nprint(len(rows))\n")
            note = hook._swallowed_script_nudge(str(transcript))
        self.assertIsNotNone(note)
        self.assertIn("query_errors.py", note)
        self.assertIn("not a measurement", note)

    def test_a_script_that_reports_its_exception_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            transcript = _transcript(
                Path(raw) / "t.jsonl", "C:/tmp/query_errors.py",
                "try:\n    rows = conn.execute('select 1').fetchall()\n"
                "except Exception as error:\n    print('query failed:', error)\n    raise\n")
            self.assertIsNone(hook._swallowed_script_nudge(str(transcript)))


if __name__ == "__main__":
    unittest.main()
