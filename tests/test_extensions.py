"""C-52: capabilities install as extensions rather than growing the core.

An extension is a directory under the private state home -
`<state-home>/extensions/<name>/` - with an `extension.json` manifest and
an entry module exposing `run(argv, context) -> dict`. `godmode extensions`
lists what is there without importing anything. `extensions run <name>`
imports and runs one, and only when the project's authorization policy
names it: a protected file the gate already guards, so enabling an
extension is an operator act on a governed surface, never a side effect
of placing a directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
import json
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
from godmode_runtime.godmode_extensions import list_extensions  # noqa: E402
from godmode_runtime.godmode_profile import POLICY_FILENAME  # noqa: E402

MANIFEST = {"name": "hello", "version": "0.1.0", "entry": "hello.py",
            "about": "answers with the argv it was given"}
ENTRY = "def run(argv, context):\n    return {'ok': True, 'argv': list(argv), 'project': context['project']}\n"


@contextmanager
def _home_with_extension():
    with tempfile.TemporaryDirectory(prefix="godmode-ext-") as temporary:
        base = Path(temporary)
        home = base / "state"
        ext = home / "extensions" / "hello"
        ext.mkdir(parents=True)
        (ext / "extension.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
        (ext / "hello.py").write_text(ENTRY, encoding="utf-8")
        project = base / "project"
        project.mkdir()
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(home)}, clear=False):
            yield home, project


def _run(argv, project) -> tuple[int, dict]:
    out = io.StringIO()
    with mock.patch.object(sys, "stdout", out), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        code = console.main(["--project", str(project)] + argv)
    return code, json.loads(out.getvalue())


class ExtensionTests(unittest.TestCase):
    def test_listing_names_the_extension_without_importing_it(self) -> None:
        with _home_with_extension() as (home, _project):
            (home / "extensions" / "hello" / "hello.py").write_text(
                "raise RuntimeError('imported')\n", encoding="utf-8")
            listing = list_extensions(home)
        self.assertEqual([e["name"] for e in listing], ["hello"])
        self.assertEqual(listing[0]["version"], "0.1.0")

    def test_run_is_refused_until_the_policy_names_it(self) -> None:
        with _home_with_extension() as (_home, project):
            code, payload = _run(["extensions", "run", "hello", "--", "x"], project)
        self.assertEqual(code, 1)
        self.assertIn("policy", payload["refused"])
        self.assertIn(POLICY_FILENAME, payload["refused"])

    def test_run_executes_a_policy_named_extension(self) -> None:
        with _home_with_extension() as (_home, project):
            (project / POLICY_FILENAME).write_text(
                json.dumps({"extensions": ["hello"]}), encoding="utf-8")
            code, payload = _run(["extensions", "run", "hello", "--", "x", "y"], project)
        self.assertEqual(code, 0)
        self.assertTrue(payload["result"]["ok"])
        self.assertEqual(payload["result"]["argv"], ["x", "y"])
        self.assertEqual(payload["extension"], "hello")


if __name__ == "__main__":
    unittest.main()
