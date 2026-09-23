"""The prepublication citation check covers every tracked document a reader
receives, including documents under tests/.

Until 0.3.28 the check skipped tests/ wholesale. Tests are tracked and ship
with the repository, so a documentation file there that cites outside
scholarship reaches readers exactly like one anywhere else.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CHECKS = PLUGIN_ROOT / "quality" / "checks"
if str(CHECKS) not in sys.path:
    sys.path.insert(0, str(CHECKS))

import prepublication as P  # noqa: E402

_CITED = "A method first shown by Someone et al. in a paper.\n"


class CitationScopeTests(unittest.TestCase):
    def _findings(self, files: dict[str, str]) -> list[str]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for rel, body in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            with mock.patch.object(P, "ROOT", root):
                return P.citation_findings(sorted(files), {"citation_exempt": []})

    def test_a_citation_in_a_test_document_is_reported(self) -> None:
        findings = self._findings({"tests/fixtures/notes.md": _CITED})
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("tests/fixtures/notes.md:1", findings[0])

    def test_the_untracked_working_archive_stays_out_of_scope(self) -> None:
        self.assertEqual(self._findings({P.UNPUBLISHED_PREFIX + "plans/x.md": _CITED}), [])

    def test_a_published_document_is_still_reported(self) -> None:
        self.assertEqual(len(self._findings({"docs/guide.md": _CITED})), 1)


if __name__ == "__main__":
    unittest.main()
