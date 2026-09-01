"""The brief ends with commands, not inventory.

Fifteen sessions of "claim unused" shared one shape: the session-start
brief described state and the model read it as scenery. A next_actions
section turns the same state into the bounded list of commands the state
itself demands - an unresolved scored claim names its own `claim
--resolve N`, a dormant-with-demand census family names the one verb that
feeds it. At most five entries, strings only, and an empty archive
produces no section rather than an error.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
for entry in (SCRIPTS, PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import record_claim  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_lens import next_actions  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-nextact-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


class NextActionsTests(unittest.TestCase):
    def test_unresolved_scored_claim_names_its_resolve(self) -> None:
        with _project() as (root, archive):
            (root / "README.md").write_text("x", encoding="utf-8")
            record = record_claim(archive, root, "S-t", "the bed holds",
                                  "observed", cites=["file:README.md"],
                                  confidence=0.8)
            actions = next_actions(archive, root)
            wanted = f"claim --resolve {record['sequence']}"
            self.assertTrue(any(wanted in a for a in actions), actions)

    def test_dormant_family_names_its_verb(self) -> None:
        with _project() as (root, archive):
            from godmode_runtime.godmode_status import record_item
            record_item(archive, "feat-x", "a feature", "active")
            actions = next_actions(archive, root)
            self.assertTrue(any("criterion" in a for a in actions), actions)

    def test_bounded_and_stringly(self) -> None:
        with _project() as (root, archive):
            (root / "README.md").write_text("x", encoding="utf-8")
            for index in range(8):
                record_claim(archive, root, f"S-{index}", f"claim number {index} holds up",
                             "observed", cites=["file:README.md"],
                             confidence=0.7)
            actions = next_actions(archive, root)
            self.assertLessEqual(len(actions), 5)
            self.assertTrue(all(isinstance(a, str) for a in actions))

    def test_empty_archive_is_quiet(self) -> None:
        with _project() as (root, archive):
            self.assertEqual(next_actions(archive, root), [])


class BriefCalibrationTests(unittest.TestCase):
    def test_a_live_calibration_advisory_rides_the_brief(self) -> None:
        # Three high-confidence claims resolved failed put the last-5 mean
        # under 0.5; the session-start brief must carry that advisory so
        # the next session opens knowing its own confidence runs hot.
        import json
        import subprocess
        from godmode_runtime.godmode_attest import record_claim, resolve_claim
        with _project() as (root, archive):
            (root / "README.md").write_text("x", encoding="utf-8")
            for index in range(3):
                record = record_claim(
                    archive, root, "S-c", f"hot claim number {index} holds",
                    "observed", cites=["file:README.md"], confidence=0.95)
                resolve_claim(archive, root, "S-c", record["sequence"],
                              "failed", cites=["file:README.md"])
            environment = dict(os.environ)
            environment["GODMODE_STATE_HOME"] = os.environ["GODMODE_STATE_HOME"]
            hook = Path(__file__).resolve().parents[1] / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "session-start",
                 "--project", str(root)],
                input="{}", capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
                env=environment)
            self.assertEqual(done.returncode, 0, done.stderr)
            body = json.loads(done.stdout)
            brief = body.get("brief") or {}
            self.assertIn("calibration", brief)
            self.assertTrue(brief["calibration"].get("advisory"))


if __name__ == "__main__":
    unittest.main()
