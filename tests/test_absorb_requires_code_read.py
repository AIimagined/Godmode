"""An absorb decision that adopts or extends must cite source code.

A README-level read may only park, skip, diverge or mark unread. This is
the write-time refusal for the standing guard: the miss recurred once
because the guard was advice.

Fix round 1: the vocabulary must match the reader (`godmode_parity`) and the
skill doc, a prefixed key must not satisfy the gate by accident, and the
`cmd_remember` wiring itself - not just the standalone validator - needs its
own coverage.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from scripts.godmode_runtime.godmode_absorb import validate_absorb

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(PLUGIN_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

from godmode_runtime import godmode_console as console  # noqa: E402
from godmode_runtime.godmode_errors import ArchiveError  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402


class AbsorbValidationTests(unittest.TestCase):
    def test_adopt_with_readme_only_refused(self) -> None:
        gaps = validate_absorb(
            "import_verdict: adopt. behaviour_verdict: unverified.",
            ["file:README.md", "file:docs/design.md"])
        self.assertIn("adopt_or_extend_needs_source_cite", gaps)

    def test_extend_with_source_cite_accepted(self) -> None:
        gaps = validate_absorb(
            "import_verdict: extend. behaviour_verdict: confirmed-have.",
            ["file:src/sync_plan.py"])
        self.assertEqual(gaps, [])

    def test_skip_needs_no_cite(self) -> None:
        self.assertEqual(validate_absorb("import_verdict: skip. behaviour_verdict: unverified.", []), [])

    def test_missing_verdicts_named(self) -> None:
        gaps = validate_absorb("read it, looks fine", [])
        self.assertIn("missing:import_verdict", gaps)
        self.assertIn("missing:behaviour_verdict", gaps)

    def test_n_a_needs_no_cite(self) -> None:
        # The union ruling: godmode_parity's own "n-a" joins this module's
        # vocabulary exactly as `exists`/`unread` joined the reader's.
        self.assertEqual(validate_absorb("import_verdict: n-a. behaviour_verdict: unverified.", []), [])

    def test_a_prefixed_key_does_not_satisfy_the_gate(self) -> None:
        # Without a `\b` before the key, `re.search` matches `import_verdict`
        # as a substring of `no_import_verdict` - a negated key would have
        # silently satisfied the gate.
        gaps = validate_absorb(
            "no_import_verdict: adopt. behaviour_verdict: unverified.", [])
        self.assertIn("missing:import_verdict", gaps)


class CmdRememberAbsorbWiringTests(unittest.TestCase):
    """H6's validator only matters if `cmd_remember` actually calls it."""

    def test_an_absorb_decision_with_a_readme_only_cite_is_refused(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            args = console._build_parser().parse_args([
                "remember", "--kind", "decision", "--subject", "absorb:widget",
                "--value", "import_verdict: adopt. behaviour_verdict: unverified.",
                "--evidence", "file:README.md"])
            with self.assertRaises(ArchiveError):
                console.cmd_remember(args, runtime)

    def test_an_absorb_decision_with_a_source_cite_persists_both_verdicts(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            args = console._build_parser().parse_args([
                "remember", "--kind", "decision", "--subject", "absorb:widget",
                "--value", "import_verdict: extend. behaviour_verdict: confirmed-have.",
                "--evidence", "file:src/sync_plan.py"])
            console.cmd_remember(args, runtime)
            record = archive.read_events()[-1]
            self.assertEqual(record["data"].get("import_verdict"), "extend")
            self.assertEqual(record["data"].get("behaviour_verdict"), "confirmed-have")

    def test_a_decision_not_named_absorb_skips_the_gate(self) -> None:
        with isolated_project() as (_project, _state, _anchor, archive):
            archive.initialize()
            runtime = console.Runtime(anchor=archive.anchor, archive=archive)
            args = console._build_parser().parse_args([
                "remember", "--kind", "decision", "--subject", "not-absorb:widget",
                "--value", "whatever, no verdicts here"])
            console.cmd_remember(args, runtime)  # must not raise
            record = archive.read_events()[-1]
            self.assertNotIn("import_verdict", record["data"])
            self.assertNotIn("behaviour_verdict", record["data"])


if __name__ == "__main__":
    unittest.main()
