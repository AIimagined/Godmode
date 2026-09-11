"""Field feedback Part 10, 2026-09-11.

The hook's runner had no npx on PATH, so every `claim --verify` on a
project command reported not found; the not-found line now names the
interpreter form. A hint named a verb that does not exist. A claim cited
a file holding a wrong number the same session had written; the done bar
checks that a citation resolves, never that it is true, so the record now
says when the evidence is the session's own statement. The archive lock
said "busy" twice in one pass; it now waits longer and backs off.
"""
from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for extra in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_attest import SELF_AUTHORED_EVIDENCE_NOTE, record_claim  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class HintNamesARealVerbTests(unittest.TestCase):
    def test_no_hint_names_a_bare_incident_verb(self) -> None:
        # Structural, on purpose: the property is that a string is gone.
        scanned = list((PLUGIN_ROOT / "hooks").glob("*.py")) + list((PLUGIN_ROOT / "scripts").rglob("*.py"))
        offenders = [str(p.relative_to(PLUGIN_ROOT)) for p in scanned
                     if "`godmode incident" in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(offenders, [])
        # Control: the corrected form is present where the hint lives.
        self.assertIn("remember --kind incident --failure-class",
                      (PLUGIN_ROOT / "scripts" / "godmode_runtime" / "godmode_precheck.py").read_text(encoding="utf-8"))


class ArchiveLockPatienceTests(unittest.TestCase):
    def test_the_lock_waits_at_least_twenty_seconds_by_default(self) -> None:
        default = inspect.signature(Chronicle.write_lock).parameters["timeout_seconds"].default
        self.assertGreaterEqual(default, 20.0)


class SelfAuthoredEvidenceTests(unittest.TestCase):
    def test_a_cited_file_this_session_wrote_is_named_as_the_sessions_own_statement(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            (project / "docs").mkdir(exist_ok=True)
            note = project / "docs" / "RCA.md"
            note.write_text("105 error rows over 7 days\n", encoding="utf-8")
            transcript = project / "t.jsonl"
            entry = {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": str(note), "content": "105 error rows"}}]}}
            transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            record = record_claim(archive, project, "s", "the database holds 105 error rows over 7 days",
                                  "observed", cites=["file:docs/RCA.md"], transcript_path=transcript)
            untouched = record_claim(archive, project, "s", "the database holds 105 error rows over 7 days",
                                     "observed", cites=["file:docs/RCA.md"])
        self.assertEqual(record["data"].get("independence"), SELF_AUTHORED_EVIDENCE_NOTE)
        self.assertNotEqual(untouched["data"].get("independence"), SELF_AUTHORED_EVIDENCE_NOTE)


if __name__ == "__main__":
    unittest.main()
