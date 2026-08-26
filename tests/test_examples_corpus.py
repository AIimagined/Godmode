"""C-24: worked examples as a first-class, reproducible fixture corpus.

`docs/DEMO.md` pins its commands against the parser; that proves a command
exists, not what it returns. `examples/*.example.json` is a corpus where
each example names a command, the keys its payload must carry, and the
exit code it must return - and `godmode examples --check` runs every one
against the real console in a throwaway project. A worked example that
drifts from the code fails the check instead of misleading a reader.
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
from godmode_runtime.godmode_examples import check_examples, load_examples  # noqa: E402

EXAMPLES = PLUGIN_ROOT / "examples"


@contextmanager
def _state_home():
    with tempfile.TemporaryDirectory() as temporary:
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": temporary}, clear=False):
            yield Path(temporary)


class ExamplesCorpusTests(unittest.TestCase):
    def test_the_shipped_corpus_has_examples_and_every_one_reproduces(self) -> None:
        examples = load_examples(EXAMPLES)
        self.assertGreaterEqual(len(examples), 3)
        for example in examples:
            for key in ("name", "command", "expect_keys", "expect_exit"):
                self.assertIn(key, example, example)
        with _state_home():
            report = check_examples(EXAMPLES)
        failed = [r for r in report["results"] if not r["ok"]]
        self.assertEqual(failed, [], failed)
        self.assertEqual(report["verdict"], "reproduced")

    def test_a_stale_example_fails_the_check_and_names_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _state_home():
            corpus = Path(temporary)
            (corpus / "stale.example.json").write_text(json.dumps({
                "name": "stale",
                "command": ["doctor"],
                "expect_keys": ["healthy", "a_key_doctor_never_returns"],
                "expect_exit": 0,
            }), encoding="utf-8")
            report = check_examples(corpus)
        self.assertEqual(report["verdict"], "stale")
        self.assertEqual(report["results"][0]["name"], "stale")
        self.assertIn("a_key_doctor_never_returns", report["results"][0]["missing_keys"])

    def test_the_check_is_a_command_and_stale_reaches_the_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, _state_home():
            corpus = Path(temporary)
            (corpus / "stale.example.json").write_text(json.dumps({
                "name": "stale", "command": ["doctor"],
                "expect_keys": ["nope"], "expect_exit": 0,
            }), encoding="utf-8")
            project = corpus / "p"
            project.mkdir()
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                code = console.main(["--project", str(project), "examples",
                                     "--check", "--corpus", str(corpus)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "stale")


if __name__ == "__main__":
    unittest.main()
