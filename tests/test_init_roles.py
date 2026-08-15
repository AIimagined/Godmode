"""godmode init --roles scaffolds genuinely unbound authority roles.

Built alongside a real pre-existing bug this work surfaced: assess's
missing_roles read a role's UNMATCHED CANDIDATE PATTERNS as if they meant
the role itself was unbound. operating-guide binds fine through GODMODE.md
while its other three candidates (OPERATING-GUIDE.md/AGENTS.md/CLAUDE.md)
all miss - and the old computation still listed it as missing. Fixed in the
same pass (assess now subtracts bound roles from the missing set) because
init --roles needs the CORRECT unbound set, or it scaffolds a role that
already has a real home.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from test_godmode_runtime import isolated_project  # noqa: E402
from godmode_runtime.godmode_assess import assess  # noqa: E402


def _init_roles(project, anchor, archive):
    import argparse
    from godmode_runtime.godmode_console import Runtime, cmd_init
    return cmd_init(argparse.Namespace(roles=True), Runtime(anchor=anchor, archive=archive))


class MissingRolesFixTests(unittest.TestCase):
    def test_a_role_bound_through_one_pattern_is_not_missing(self) -> None:
        # The bug this pass fixed: operating-guide binds via GODMODE.md but
        # its other three candidates all miss - must not appear as missing.
        with isolated_project() as (project, _s, archive_anchor, archive):
            (project / "GODMODE.md").write_text("# Guide\n", encoding="utf-8")
            report = assess(project, budget=100_000, archive=archive)
        self.assertNotIn("operating-guide", report["authority"]["missing_roles"])

    def test_a_role_with_zero_bindings_is_still_missing(self) -> None:
        with isolated_project() as (project, _s, _a, archive):
            (project / "GODMODE.md").write_text("# Guide\n", encoding="utf-8")
            report = assess(project, budget=100_000, archive=archive)
        self.assertIn("state", report["authority"]["missing_roles"])


class InitRolesTests(unittest.TestCase):
    def test_scaffolds_every_role_on_an_empty_project(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            result = _init_roles(project, anchor, archive)
        written = result.payload["roles_scaffolded"]["written"]
        self.assertEqual(len(written), 9)
        self.assertIn("GODMODE.md", written)
        self.assertIn("docs/STATE.md", written)

    def test_assess_reports_zero_missing_after_scaffold(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            _init_roles(project, anchor, archive)
            report = assess(project, budget=100_000, archive=archive)
        self.assertEqual(report["authority"]["missing_roles"], [])

    def test_never_overwrites_an_existing_file(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            (project / "GODMODE.md").write_text("SENTINEL\n", encoding="utf-8")
            result = _init_roles(project, anchor, archive)
            content = (project / "GODMODE.md").read_text(encoding="utf-8")
        self.assertIn("SENTINEL", content)
        self.assertNotIn("GODMODE.md", result.payload["roles_scaffolded"]["written"])

    def test_a_bound_role_is_never_attempted(self) -> None:
        # Not just "not overwritten" - the role must not even reach the
        # existence check, since resolve_roles already says it is satisfied.
        with isolated_project() as (project, _s, anchor, archive):
            (project / "GODMODE.md").write_text("SENTINEL\n", encoding="utf-8")
            result = _init_roles(project, anchor, archive)
        skipped_roles = {s["role"] for s in result.payload["roles_scaffolded"]["skipped"]}
        self.assertNotIn("operating-guide", skipped_roles)

    def test_stub_content_names_the_role(self) -> None:
        with isolated_project() as (project, _s, anchor, archive):
            _init_roles(project, anchor, archive)
            content = (project / "docs" / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("State", content)
        self.assertTrue(len(content.strip()) > 10)

    def test_plain_init_does_not_scaffold(self) -> None:
        import argparse
        from godmode_runtime.godmode_console import Runtime, cmd_init
        with isolated_project() as (project, _s, anchor, archive):
            result = cmd_init(argparse.Namespace(roles=False), Runtime(anchor=anchor, archive=archive))
        self.assertNotIn("roles_scaffolded", result.payload)
        self.assertFalse((project / "GODMODE.md").exists())


if __name__ == "__main__":
    unittest.main()
