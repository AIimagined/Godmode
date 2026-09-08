"""Grounded claims: evidence carries its version (obligation 10248).

A claim that cites `file:<path>` or `file:<path>#L<a>-L<b>` resolved its
citation once at record time and then silently outlived the lines it
cited. Now the record stores the evidence version (a hash of the file, or
of the cited range), and a stale sweep names every claim whose evidence
changed or vanished, surfaced in the continuity brief, on `claim --stale`,
and as a preflight judgment finding.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime.godmode_attest import (  # noqa: E402
    evidence_versions, open_session, record_claim, stale_claims,
)
from godmode_runtime.godmode_console import Runtime, cmd_claim  # noqa: E402
from godmode_runtime.godmode_reach import reach_finding  # noqa: E402,F401 - module import sanity
from test_godmode_runtime import isolated_project  # noqa: E402


def _write(project: Path, rel: str, text: str) -> None:
    (project / rel).parent.mkdir(parents=True, exist_ok=True)
    (project / rel).write_text(text, encoding="utf-8")


class EvidenceVersionTests(unittest.TestCase):
    def test_a_file_citation_records_the_evidence_version(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/a.py", "x = 1\ny = 2\nz = 3\n")
            session = open_session(archive, "t")
            record = record_claim(archive, project, session, "y is set on line two",
                                  "observed", cites=["file:src/a.py#L2"])
            versions = record["data"]["evidence_versions"]
            self.assertIn("file:src/a.py#L2", versions)
            self.assertEqual(versions["file:src/a.py#L2"]["kind"], "range")
            self.assertEqual(len(versions["file:src/a.py#L2"]["hash"]), 64)

    def test_versions_change_only_when_the_cited_range_changes(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            _write(project, "src/a.py", "x = 1\ny = 2\nz = 3\n")
            before = evidence_versions(project, ["file:src/a.py#L2", "file:src/a.py"])
            _write(project, "src/a.py", "x = 1\ny = 2\nz = 4\n")
            after = evidence_versions(project, ["file:src/a.py#L2", "file:src/a.py"])
            self.assertEqual(before["file:src/a.py#L2"]["hash"], after["file:src/a.py#L2"]["hash"])
            self.assertNotEqual(before["file:src/a.py"]["hash"], after["file:src/a.py"]["hash"])


class StaleSweepTests(unittest.TestCase):
    def test_a_claim_whose_evidence_moved_or_vanished_is_named(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/a.py", "x = 1\ny = 2\n")
            _write(project, "src/b.py", "q = 1\n")
            session = open_session(archive, "t")
            record_claim(archive, project, session, "y is set on line two", "observed",
                         cites=["file:src/a.py#L2"])
            record_claim(archive, project, session, "q is defined in b", "observed",
                         cites=["file:src/b.py"])
            record_claim(archive, project, session, "the design favours one file", "observed",
                         cites=["docs/x.md"])
            self.assertEqual(stale_claims(archive, project), [])
            _write(project, "src/a.py", "x = 1\ny = 99\n")
            (project / "src" / "b.py").unlink()
            stale = stale_claims(archive, project)
            reasons = {s["citation"]: s["reason"] for s in stale}
            self.assertEqual(reasons["file:src/a.py#L2"], "changed")
            self.assertEqual(reasons["file:src/b.py"], "vanished")
            self.assertEqual(len(stale), 2)

    def test_claim_stale_lists_them_from_the_console(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            _write(project, "src/a.py", "x = 1\n")
            session = open_session(archive, "t")
            record_claim(archive, project, session, "x is one", "observed", cites=["file:src/a.py"])
            _write(project, "src/a.py", "x = 2\n")
            runtime = Runtime(anchor=_anchor, archive=archive)
            args = argparse.Namespace(stale=True, text=None, grade="observed", cite=[],
                                      external=False, session=None, transcript=None,
                                      verify=False, timeout=900, refuted_by=None,
                                      resolve=None, outcome=None, blast_radius=None,
                                      confidence=None)
            payload = cmd_claim(args, runtime).payload
            self.assertEqual(payload["stale"], 1)
            self.assertEqual(payload["claims"][0]["reason"], "changed")


if __name__ == "__main__":
    unittest.main()
