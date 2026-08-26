"""C-11: a terse, action-first output profile.

`--brief` already gives one glanceable line, and it leads with the verdict.
`--terse` is the profile for the reader who wants to act, not to read: the
next action on line one, then one line per finding, then the same brief
line `--brief` would have printed. Nothing new is computed - it is the same
payload `--json` carries, reordered so the first line is the one to do.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import _terse_text  # noqa: E402


@contextmanager
def isolated_project():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        project = base / "project"
        state = base / "private-state"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
            anchor = resolve_anchor(project)
            archive = Chronicle(anchor)
            yield project, state, anchor, archive


class TerseTextTests(unittest.TestCase):
    def test_the_action_is_the_first_line(self) -> None:
        payload = {
            "verdict": "findings-present",
            "findings": [
                {"path": "docs/a.md", "line": 3, "message": "open marker"},
                {"path": "docs/b.md", "line": 9, "message": "local path"},
            ],
            "next_action": "run `godmode docs --lint` and clear the two findings",
        }
        lines = _terse_text(payload).splitlines()
        self.assertEqual(lines[0], "next: run `godmode docs --lint` and clear the two findings")
        self.assertIn("docs/a.md:3 open marker", lines)
        self.assertIn("docs/b.md:9 local path", lines)
        self.assertTrue(lines[-1].startswith("findings-present"), lines[-1])

    def test_no_action_is_said_not_implied(self) -> None:
        lines = _terse_text({"verdict": "clean", "findings": []}).splitlines()
        self.assertEqual(lines[0], "next: nothing - clean")

    def test_findings_are_capped_and_the_cap_is_stated(self) -> None:
        payload = {"findings": [{"path": f"f{i}.py", "line": i, "message": "x"}
                                for i in range(30)], "verdict": "findings-present"}
        text = _terse_text(payload)
        self.assertIn("... 20 more", text)
        self.assertEqual(text.count(" x"), 10)

    def test_terse_is_a_global_flag(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                console.main(["--project", str(project), "--terse", "doctor"])
        first = out.getvalue().splitlines()[0]
        self.assertTrue(first.startswith("next: "), first)


if __name__ == "__main__":
    unittest.main()
