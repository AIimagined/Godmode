"""The AGENTS.md section is generated, traceable, and merge-not-overwrite.

Hosts that read AGENTS.md and wire no hooks get godmode's commands and
boundaries for free. The section can never drift from the CLI: every
command line comes from the registered day-one verbs, checked against
the live subparsers in both directions, and the boundary rows come from
the one tier table. Everything outside the markers is the project's and
survives byte-for-byte; re-emitting is idempotent.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from godmode_runtime.godmode_console import (  # noqa: E402
    _BOUNDARY_TIERS,
    _DAY_ONE_VERBS,
    _build_parser,
    _subparser_action,
    agentsmd_section,
    emit_agentsmd,
)


class TraceabilityTests(unittest.TestCase):
    def test_every_emitted_command_is_a_registered_subparser(self) -> None:
        parser = _build_parser()
        registered = set(_subparser_action(parser).choices)
        section = agentsmd_section(parser)
        for name, _blurb in _DAY_ONE_VERBS:
            self.assertIn(f"`godmode {name}`", section)
            self.assertIn(name, registered)

    def test_every_boundary_tier_is_rendered(self) -> None:
        section = agentsmd_section(_build_parser())
        for tier, _detail in _BOUNDARY_TIERS:
            self.assertIn(f"**{tier}**", section)


class MergeTests(unittest.TestCase):
    def test_a_fresh_file_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = emit_agentsmd(_build_parser(), Path(tmp))
            self.assertEqual(report["action"], "created")
            self.assertIn("## Godmode", (Path(tmp) / "AGENTS.md").read_text(encoding="utf-8"))

    def test_foreign_content_survives_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "AGENTS.md"
            target.write_text("# Ours\n\nHouse rules stay.\n", encoding="utf-8")
            emit_agentsmd(_build_parser(), Path(tmp))
            merged = target.read_text(encoding="utf-8")
            self.assertTrue(merged.startswith("# Ours\n\nHouse rules stay."))
            self.assertIn("## Godmode", merged)

    def test_reemit_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "AGENTS.md"
            target.write_text("# Ours\n", encoding="utf-8")
            emit_agentsmd(_build_parser(), Path(tmp))
            first = target.read_text(encoding="utf-8")
            report = emit_agentsmd(_build_parser(), Path(tmp))
            self.assertEqual(report["action"], "refreshed")
            self.assertEqual(first, target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
