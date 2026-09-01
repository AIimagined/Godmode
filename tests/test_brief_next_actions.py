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
from godmode_runtime.godmode_metrics import next_actions  # noqa: E402


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


class DocSprawlTests(unittest.TestCase):
    """The SPRINT-SSOT disease self-surfaces: many large status-shaped
    markdown files at session start draw one brief line with the numbers
    and the migration verb. Below threshold, silence - two sprint files
    are a convention, not a disease."""

    def test_sprawl_past_threshold_rides_the_brief(self) -> None:
        import json
        import subprocess
        with _project() as (root, archive):
            for index in range(7):
                (root / f"SPRINT-AREA-{index}.md").write_text(
                    ("# sprint\n" + "- item\n" * 400), encoding="utf-8")
            hook = Path(__file__).resolve().parents[1] / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "session-start", "--project", str(root)],
                input="{}", capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
                env=dict(os.environ))
            brief = json.loads(done.stdout).get("brief") or {}
            sprawl = brief.get("doc_sprawl") or {}
            self.assertEqual(sprawl.get("files"), 7)
            self.assertIn("status", sprawl.get("advisory", ""))

    def test_two_files_stay_silent(self) -> None:
        import json
        import subprocess
        with _project() as (root, archive):
            (root / "SPRINT-A.md").write_text("# a\n" + "- x\n" * 400, encoding="utf-8")
            (root / "HANDOVER-B.md").write_text("# b\n" + "- x\n" * 400, encoding="utf-8")
            hook = Path(__file__).resolve().parents[1] / "hooks" / "godmode_session_hook.py"
            done = subprocess.run(
                [sys.executable, str(hook), "session-start", "--project", str(root)],
                input="{}", capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
                env=dict(os.environ))
            brief = json.loads(done.stdout).get("brief") or {}
            self.assertNotIn("doc_sprawl", brief)


class BriefOrderingTests(unittest.TestCase):
    def test_priority_sections_serialize_before_inventory(self) -> None:
        # The context cap truncates from the tail; the commands must
        # outlive the inventory.
        import io
        import json as _json
        from contextlib import redirect_stdout
        import sys as _sys
        hooks_dir = str(Path(__file__).resolve().parents[1] / "hooks")
        if hooks_dir not in _sys.path:
            _sys.path.insert(0, hooks_dir)
        from godmode_session_hook import _emit_claude_context
        brief = {"zeta_bulk": ["x"] * 50, "next_actions": ["do the thing"],
                 "alpha_bulk": ["y"] * 50, "calibration": {"advisory": "hot"}}
        out = io.StringIO()
        with redirect_stdout(out):
            _emit_claude_context(brief)
        context = _json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertLess(context.index("next_actions"), context.index("alpha_bulk"))
        self.assertLess(context.index("calibration"), context.index("zeta_bulk"))
