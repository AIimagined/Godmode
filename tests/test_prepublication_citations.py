"""The prepublication citation check covers every tracked document a reader
receives, including documents under tests/.

Until 0.3.28 the check skipped tests/ wholesale. Tests are tracked and ship
with the repository, so a documentation file there that cites outside
scholarship reaches readers exactly like one anywhere else.
"""
from __future__ import annotations

import io
import json
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


def _fake_groups(count: int) -> dict[str, list[str]]:
    return {
        "deny-name / forge-url": [],
        "citation": [f"doc{n}.md:1: names external scholarship" for n in range(count)],
        "unpublishable-class": [],
        "link-rot": [],
    }


class MainTruncationTests(unittest.TestCase):
    """Row 34 (2026-09-25 carried-items triage): the report used to print
    only the first 10 findings per group while counting all of them, with
    no signal in the exit code that anything was left out of view."""

    def _run(self, argv: list[str], count: int = 25, citation: list[str] | None = None):
        if citation is None:
            citation = _fake_groups(count)["citation"]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(P, "_tracked", return_value=[]), \
                mock.patch.object(P, "load_policy", return_value={}), \
                mock.patch.object(P, "surface_name_findings", return_value=[]), \
                mock.patch.object(P, "citation_findings", return_value=citation), \
                mock.patch.object(P, "unpublishable_findings", return_value=[]), \
                mock.patch.object(P, "link_findings", return_value=[]), \
                mock.patch.object(sys, "stdout", out), \
                mock.patch.object(sys, "stderr", err):
            code = P.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_default_shows_ten_and_names_the_true_count(self) -> None:
        code, out, err = self._run([], count=25)
        self.assertEqual(code, 1)
        self.assertIn("25 finding(s)", out)
        self.assertIn("showing 10 of 25", out)
        self.assertEqual(err.count("FAIL:"), 10)
        self.assertIn("not ready to publish", err)

    def test_all_flag_shows_every_finding(self) -> None:
        code, out, err = self._run(["--all"], count=25)
        self.assertEqual(code, 1)
        self.assertNotIn("showing", out)
        self.assertEqual(err.count("FAIL:"), 25)

    def test_truncation_still_exits_nonzero(self) -> None:
        code, _out, _err = self._run([], count=11)
        self.assertEqual(code, 1)

    def test_baseline_mode_suppresses_accepted_findings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            baseline_path = Path(raw) / "baseline.json"
            accepted = _fake_groups(3)
            baseline_path.write_text(json.dumps(accepted), encoding="utf-8")
            # 3 findings already accepted, 1 new one on top.
            findings = accepted["citation"] + ["doc-new.md:1: names external scholarship"]
            code, out, _err = self._run(["--baseline", str(baseline_path)], citation=findings)
        self.assertEqual(code, 1)
        self.assertIn("1 finding(s)", out)
        self.assertIn("3 accepted by baseline", out)

    def test_baseline_mode_is_clean_when_nothing_new(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            baseline_path = Path(raw) / "baseline.json"
            accepted = _fake_groups(5)
            baseline_path.write_text(json.dumps(accepted), encoding="utf-8")
            code, out, _err = self._run(["--baseline", str(baseline_path)], citation=accepted["citation"])
        self.assertEqual(code, 0)
        self.assertIn("ready to publish", out)

    def test_write_baseline_records_current_findings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            baseline_path = Path(raw) / "baseline.json"
            self._run(["--baseline", str(baseline_path), "--write-baseline"], count=4)
            written = json.loads(baseline_path.read_text(encoding="utf-8"))
        self.assertEqual(len(written["citation"]), 4)


if __name__ == "__main__":
    unittest.main()
