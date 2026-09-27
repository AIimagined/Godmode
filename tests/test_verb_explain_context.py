"""`explain-context` (0.3.31 task 14, verb consolidation): the retired
top-level name is kept for one release as a deprecated alias of
`context why`. Invoking it must still run exactly what `context why` runs
(same payload, same exit code) and must print a one-line deprecation note
naming the replacement to stderr before it does."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


def _run(project: Path, *arguments: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
        code = console.main(["--project", str(project), "--json", *arguments])
    return code, out.getvalue(), err.getvalue()


class ExplainContextAliasTests(unittest.TestCase):
    def test_explain_context_prints_the_deprecation_note_on_stderr(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, _out, err = _run(project, "explain-context")
        self.assertEqual(code, 0)
        self.assertIn("explain-context", err)
        self.assertIn("context why", err)
        self.assertIn("deprecated", err.lower())

    def test_explain_context_still_runs_and_matches_context_why(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            archive.append(
                "decision", "release-cadence",
                {"value": "ship weekly, not nightly", "status": "active"},
                evidence=["seq:1"],
            )
            alias_code, alias_out, _alias_err = _run(project, "explain-context")
            canonical_code, canonical_out, canonical_err = _run(project, "context", "why")
        self.assertEqual(alias_code, canonical_code)
        self.assertEqual(json.loads(alias_out), json.loads(canonical_out))
        # `context why` itself is the live command, never deprecated.
        self.assertEqual(canonical_err, "")

    def test_context_why_with_about_is_not_reachable_through_the_alias(self) -> None:
        # `explain-context` never took `--about` - the alias preserves that
        # exact surface rather than growing a new argument during the
        # deprecation window.
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            code, _out, err = _run(project, "explain-context", "--about", "release-cadence")
        self.assertNotEqual(code, 0)
        self.assertIn("unrecognized", err.lower())


if __name__ == "__main__":
    unittest.main()
