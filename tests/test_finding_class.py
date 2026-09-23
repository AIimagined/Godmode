"""Findings carry a class; trends shows a class that recurs across preflight rounds."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime import godmode_preflight  # noqa: E402
from godmode_runtime.godmode_trends import trends_report  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class FindingClassTests(unittest.TestCase):
    def test_blank_class_is_malformed(self) -> None:
        findings = [{"check": "suite", "detail": "x", "class": ""}]
        malformed = godmode_preflight.malformed_findings(findings)
        self.assertEqual([m["check"] for m in malformed], ["malformed-finding"])

    def test_unknown_class_is_malformed(self) -> None:
        malformed = godmode_preflight.malformed_findings([{"check": "suite", "detail": "x", "class": "bad-luck"}])
        self.assertEqual(len(malformed), 1)

    def test_recurrence_across_two_rounds(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for round_no in (1, 2):
                archive.append("attestation", "preflight", {"status": "ran", "session": f"S{round_no}", "head": "abc",
                                                            "validated": False, "findings": 3, "gates": 5,
                                                            "judgment": ["suite"], "classes": {"environment-failure": 3}})
            rows = trends_report(archive, sessions=5)["findings_by_class"]
            hit = [r for r in rows if r["class"] == "environment-failure"]
            self.assertTrue(hit and hit[-1]["recurring"], rows)


if __name__ == "__main__":
    unittest.main()
