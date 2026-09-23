"""Two exports of one archive are byte-identical; directory listing order does not matter."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for extra in (SCRIPTS, Path(__file__).parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import export  # noqa: E402
from godmode_runtime.godmode_lens import make_snapshot  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExportDeterminismTests(unittest.TestCase):
    def test_twice_identical(self) -> None:
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for n in range(5):
                archive.append("decision", f"d{n}", {"status": "active", "value": f"v{n}"})
            out = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, out, ignore_errors=True)
            export(anchor, archive, out / "one.json")
            export(anchor, archive, out / "two.json")
            self.assertEqual(digest(out / "one.json"), digest(out / "two.json"))
            self.assertIn('"seal"', (out / "one.json").read_text(encoding="utf-8"))

    def test_listing_order_irrelevant(self) -> None:
        # Chronicle.event_paths() feeds read_events(), which export() relies
        # on; export must not depend on how the filesystem happens to
        # enumerate the events directory. Two fresh Chronicle instances (no
        # shared read cache, as two separate `godmode export` process
        # invocations would see) export the same archive; the second one's
        # raw glob() result for the events directory is handed back
        # reversed, simulating a filesystem that enumerates entries in a
        # different order. event_paths() sorts before anything else touches
        # the list, so the export must still be byte-identical.
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            for n in range(5):
                archive.append("decision", f"d{n}", {"status": "active", "value": f"v{n}"})
            out = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, out, ignore_errors=True)

            archive_a = Chronicle(anchor)
            export(anchor, archive_a, out / "a.json")

            archive_b = Chronicle(anchor)
            real_glob = Path.glob

            def reversed_for_events(self_path, pattern, *pos, **kw):
                result = real_glob(self_path, pattern, *pos, **kw)
                if self_path == archive_b.events:
                    return list(reversed(list(result)))
                return result

            with mock.patch.object(Path, "glob", reversed_for_events):
                export(anchor, archive_b, out / "b.json")
            self.assertEqual(digest(out / "a.json"), digest(out / "b.json"))


class ExportTimeStabilityTests(unittest.TestCase):
    def test_stale_baseline_text_is_frozen_across_a_clock_advance(self) -> None:
        # `detect_context_issues` (called from inside `build_context_brief`)
        # embeds elapsed hours into `stale-baseline`'s detail text, computed
        # against the real clock at call time. Two exports of the SAME,
        # unchanged archive taken hours apart - an entirely ordinary use of
        # `godmode export` - must still produce identical bytes, so
        # `export()` has to freeze that text rather than pass it through.
        # `godmode_lens.datetime` (not `godmode_console.datetime`, which is
        # only used for `exported_at`) is patched with a subclass whose
        # `now()` is advanced between the two calls, standing in for real
        # elapsed time without touching production code.
        with isolated_project() as (_project, _state, anchor, archive):
            archive.initialize()
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)

            class AdvancingClock(datetime):
                _now = start

                @classmethod
                def now(cls, tz=None):
                    value = cls._now
                    return value if tz is None else value.astimezone(tz)

            snapshot = make_snapshot(anchor)
            snapshot["captured_at"] = (start - timedelta(hours=30)).isoformat()
            archive.append("inventory", "baseline", snapshot, evidence=[])

            out = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, out, ignore_errors=True)

            with mock.patch("godmode_runtime.godmode_lens.datetime", AdvancingClock):
                export(anchor, archive, out / "one.json")
                AdvancingClock._now = start + timedelta(hours=6)
                export(anchor, archive, out / "two.json")

            self.assertEqual(digest(out / "one.json"), digest(out / "two.json"))
            payload = json.loads((out / "one.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any(issue["code"] == "stale-baseline" for issue in payload["issues"])
            )


if __name__ == "__main__":
    unittest.main()
