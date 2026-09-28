"""`godmode roi --releases`: password rounds, refusals by category, preflight
runs and minutes, repeated suite runs, per release tag range."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_roi import release_roi, render_release_roi  # noqa: E402


def _rec(kind: str, subject: str, data: dict, day: int) -> dict:
    return {"kind": kind, "subject": subject, "data": data,
            "recorded_at": f"2026-09-{day:02d}T12:00:00+00:00"}


class ReleaseRoiTests(unittest.TestCase):
    def test_two_stagings_three_refusals_two_preflights(self) -> None:
        records = [
            _rec("action", "capability-issued", {}, 10),
            _rec("action", "capability-consumed", {}, 10),
            _rec("action", "capability-issued", {}, 11),
            _rec("refusal", "local-repository-change", {"category": "local-repository-change"}, 10),
            _rec("refusal", "local-repository-change", {"category": "local-repository-change"}, 11),
            _rec("refusal", "git-history-or-remote", {"category": "git-history-or-remote"}, 11),
            _rec("refusal", "observed", {"category": "observed", "observed": True}, 11),
            _rec("attestation", "preflight", {"status": "ran", "head": "abc", "seconds": 1800}, 10),
            _rec("attestation", "preflight", {"status": "failed", "head": "abc"}, 12),
            _rec("attestation", "preflight", {"status": "ran", "head": "def", "seconds": 60}, 20),
        ]
        tags = [("v1", datetime(2026, 9, 15, tzinfo=timezone.utc))]
        rows = release_roi(records, tags)
        self.assertEqual([r["release"] for r in rows], ["v1", "unreleased"])
        v1, later = rows
        self.assertEqual((v1["passwords"], v1["consumed"]), (2, 1))
        self.assertEqual(v1["refusals"], {"local-repository-change": 2, "git-history-or-remote": 1})
        self.assertEqual(v1["preflights"], 2)
        self.assertEqual(v1["preflight_minutes"], 30.0)
        self.assertEqual(v1["preflight_untimed"], 1)
        self.assertEqual(v1["suite_repeats"], 1)
        self.assertEqual((later["preflights"], later["suite_repeats"], later["passwords"]), (1, 0, 0))
        table = render_release_roi(rows)
        self.assertIn("v1", table)
        self.assertIn("30.0 +1?", table)
        self.assertEqual(len(table.strip().splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
