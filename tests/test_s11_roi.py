"""S11-B: the posture loop reads the enforce era."""
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
from godmode_runtime.godmode_roi import enforce_digest  # noqa: E402


class EnforceDigestTests(unittest.TestCase):
    def test_quiet_archive_returns_none(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            self.assertIsNone(enforce_digest(archive))

    def test_asks_and_silences_are_counted_and_drift_named(self) -> None:
        with isolated_project() as (_p, _s, _a, archive):
            archive.initialize()
            for _ in range(3):
                archive.append("action", "gate-asked",
                               {"tier": "R4", "category": "worktree-discard",
                                "tool": "Bash"}, evidence=[])
            archive.append("action", "interpreter-opaque-inline",
                           {"category": "interpreter-opaque-inline",
                            "tier": "R2", "gate": "allow",
                            "silenced_by": "ask_only"}, evidence=[])
            report = enforce_digest(archive)
        self.assertEqual(report["asked_by_category"]["worktree-discard"], 3)
        self.assertEqual(
            report["silenced_by_category"]["interpreter-opaque-inline"], 1)
        self.assertIn("worktree-discard", report["re_proposal"]["ask_only"])
        self.assertIn("worktree-discard", report["drift"]["added"])


if __name__ == "__main__":
    unittest.main()
