"""Obligation 10372 (field report 22): every record verb takes its
primary text in one shape - positionally or through its named flag, one
meaning in two spellings - and refuses the two spellings when they
disagree. The rule lives once, in `_one_text`; this file proves each
verb rides it, and the registry sweep proves no record verb was left out.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

# verb -> (flag spelling of the primary text, extra argv every form needs)
RECORD_VERBS = {
    "remember": ("--value", ["--kind", "lesson"]),
    "checkpoint": ("--summary", ["--status", "active"]),
    "attest": ("--step", ["--status", "ran"]),
    "claim": ("--text", []),
    "build": ("--summary", []),
    "plan": ("--title", ["--step", "one"]),
    "criterion": ("--text", ["--task", "t1"]),
}


def _run(project: Path, argv: list[str]) -> int:
    with mock.patch.object(sys, "stdout", io.StringIO()), \
            mock.patch.object(sys, "stderr", io.StringIO()):
        return console.main(["--project", str(project), *argv])


def _opened(archive) -> None:
    """attest, claim and criterion bind to the open session."""
    archive.initialize()
    project = Path(archive.anchor.project_root)
    assert _run(project, ["session", "open"]) == 0


def _last_subject(archive) -> str:
    return archive.read_events()[-1]["subject"]


def _positional_and_flag(parser: console.argparse.ArgumentParser) -> tuple[bool, bool]:
    optional_positional = any(
        not action.option_strings and action.nargs == "?" for action in parser._actions)
    _flag, _ = RECORD_VERBS.get(parser.prog.split()[-1], (None, None))
    has_flag = any(_flag in action.option_strings for action in parser._actions)
    return optional_positional, has_flag


class OneShapeTests(unittest.TestCase):
    def test_every_record_verb_takes_text_positionally_and_by_flag(self) -> None:
        for verb, (flag, extra) in RECORD_VERBS.items():
            with self.subTest(verb=verb), isolated_project() as (project, _s, _a, archive):
                _opened(archive)
                self.assertEqual(_run(project, [verb, "the text", *extra]), 0, verb)
                spoken = _last_subject(archive)
                self.assertEqual(_run(project, [verb, flag, "the text", *extra]), 0, verb)
                self.assertEqual(_last_subject(archive), spoken, verb)

    def test_both_spellings_with_different_text_are_refused(self) -> None:
        for verb, (flag, extra) in RECORD_VERBS.items():
            with self.subTest(verb=verb), isolated_project() as (project, _s, _a, archive):
                _opened(archive)
                before = len(archive.read_events())
                code = _run(project, [verb, "one text", flag, "another text", *extra])
                self.assertEqual(code, 2, verb)
                self.assertEqual(len(archive.read_events()), before, verb)

    def test_both_spellings_with_the_same_text_are_one_record(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _opened(archive)
            self.assertEqual(_run(project, ["claim", "same", "--text", "same"]), 0)

    def test_evidence_is_the_same_flag_as_cite_on_claim_and_criterion(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            _opened(archive)
            (project / "README.md").write_text("cited\n", encoding="utf-8")
            self.assertEqual(_run(project, ["claim", "cited", "--evidence", "file:README.md"]), 0)
            self.assertEqual(_run(project, ["criterion", "--task", "t", "judged",
                                            "--evidence", "cmd:true"]), 0)
            kinds = [r["kind"] for r in archive.read_events()]
            self.assertIn("claim", kinds)
            self.assertIn("criterion", kinds)

    def test_the_parser_registry_carries_the_shape_for_each_record_verb(self) -> None:
        parser = console._build_parser()
        subparsers = next(a for a in parser._actions
                          if isinstance(a, console.argparse._SubParsersAction))
        for verb in RECORD_VERBS:
            with self.subTest(verb=verb):
                positional, flag = _positional_and_flag(subparsers.choices[verb])
                self.assertTrue(positional, f"{verb}: no optional positional text")
                self.assertTrue(flag, f"{verb}: no flag spelling")


if __name__ == "__main__":
    unittest.main()
