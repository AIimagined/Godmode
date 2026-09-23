"""A standing law never drops off the brief because newer laws arrived.

The brief carries the k newest guarded lessons. A guard recorded as
standing was stored without the flag and would have fallen off after
three newer guards - an enforcing guard that evaporates is advice.
"""
from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from _law_fixtures import OPERATOR_RECORD_FIELDS  # noqa: E402
from scripts.godmode_runtime.godmode_law import top_laws  # noqa: E402


class FakeArchive:
    def __init__(self, records):
        self._records = records

    def read_events(self):
        return list(self._records)


def lesson(seq, subject, standing=False):
    """NS-2 fix round 1 (B1): `top_laws` now asks how a guard earned its
    place - approval lineage, or operator trust. These are hand-built
    record dicts against a fake archive (no `Chronicle` to append to), so
    they carry the carve-out's own sealed fields directly
    (`OPERATOR_RECORD_FIELDS`, spread at the RECORD level, never into
    `data` - `writer` is a top-level field of the sealed record, which is
    exactly why a payload cannot back-fill it). What this file is about is
    ordering and the standing pin, not admission."""
    data = {"status": "active", "generalized_guard": f"guard {seq}", "value": "v"}
    if standing:
        data["standing"] = True
    return {"kind": "lesson", "sequence": seq, "subject": subject, "data": data,
            "recorded_at": "2026-09-16", **OPERATOR_RECORD_FIELDS}


class StandingLawTests(unittest.TestCase):
    def test_standing_survives_three_newer(self) -> None:
        archive = FakeArchive([
            lesson(10, "standing one", standing=True),
            lesson(11, "newer a"), lesson(12, "newer b"), lesson(13, "newer c"),
        ])
        seqs = [law["seq"] for law in top_laws(archive, 3)]
        self.assertIn(10, seqs)
        self.assertEqual(seqs[0], 10)

    def test_non_standing_still_capped(self) -> None:
        archive = FakeArchive([lesson(1, "a"), lesson(2, "b"), lesson(3, "c"), lesson(4, "d")])
        self.assertEqual(len(top_laws(archive, 3)), 3)


class ConsolePersistsStandingTests(unittest.TestCase):
    def test_remember_kind_lesson_standing_persists_the_flag(self) -> None:
        # The console half of the same contract: `--standing` on a lesson
        # must reach the stored record, not just the in-memory dict shape
        # `top_laws` reads above.
        from test_godmode_runtime import isolated_project  # noqa: E402

        with isolated_project() as (project, _s, _a, archive):
            archive.initialize()
            from godmode_runtime.godmode_console import main

            main(["--project", str(project), "remember", "--kind", "lesson",
                  "--subject", "standing-law", "--value", "keep it pinned",
                  "--guard", "always pin this guard", "--standing"])
            written = [r for r in archive.read_events() if r["kind"] == "lesson"]
        self.assertEqual(len(written), 1, written)
        self.assertIs(written[0]["data"]["standing"], True)


if __name__ == "__main__":
    unittest.main()
