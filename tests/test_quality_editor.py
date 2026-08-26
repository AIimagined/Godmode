"""C-63: an editor integration surface for findings.

Nothing is installed into any editor. The surface is two output shapes
editors already consume: `path:line: severity: message` (the GCC shape VS
Code's default problem matcher parses) and a minimal SARIF 2.1.0 document
for the SARIF viewers. Either is one `--format` flag on `quality`.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import re
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


def _seed(project: Path) -> None:
    (project / "docs").mkdir(exist_ok=True)
    (project / "docs" / "notes.md").write_text(
        "See C:\\Users\\someone\\work for the files.\n\nTODO finish this section\n",
        encoding="utf-8")

_GCC_LINE = re.compile(r"^[^:\n]+:\d+: (high|medium|low|advisory): .+$")


def _run(argv, project) -> tuple[int, str]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        code = console.main(["--project", str(project)] + argv)
    return code, out.getvalue()


class EditorFormatTests(unittest.TestCase):
    def test_editor_format_is_one_gcc_shaped_line_per_finding(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            _seed(project)
            code, text = _run(["quality", "--format", "editor"], project)
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 2)
        for line in lines:
            self.assertRegex(line, _GCC_LINE)
        self.assertEqual(code, 1)  # the high finding still reaches the exit

    def test_sarif_format_is_a_2_1_0_document_with_one_result_per_finding(self) -> None:
        with isolated_project() as (project, _state, _anchor, _archive):
            _seed(project)
            _code, json_text = _run(["quality"], project)
            _code, sarif_text = _run(["quality", "--format", "sarif"], project)
        report = json.loads(json_text)
        sarif = json.loads(sarif_text)
        self.assertEqual(sarif["version"], "2.1.0")
        results = sarif["runs"][0]["results"]
        self.assertEqual(len(results), len(report["findings"]))
        self.assertEqual(sarif["runs"][0]["tool"]["driver"]["name"], "godmode")
        levels = {r["level"] for r in results}
        self.assertIn("error", levels)  # the high finding maps to error


if __name__ == "__main__":
    unittest.main()
