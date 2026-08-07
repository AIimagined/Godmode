"""The portable manifest, asserted locally because only other clients read it.

The composite action failed to load for a fortnight because nothing but GitHub
ever parsed it. A manifest written to a published specification has the same
shape of risk: it is validated by clients this project does not run, so a
violation is invisible here until somebody else's installer rejects it.

The specification's schema is closed — ten permitted top-level fields and no
others — so conformance is checkable without fetching anything, and it is
checked that way. The schema URL in the manifest is a string, never a request.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PLUGIN_ROOT / "plugin.json"

# Agent Plugins 1.0.0, §5: the closed set of permitted top-level fields.
PERMITTED = frozenset({
    "$schema", "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords", "extensions",
})
SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class ConformanceTests(unittest.TestCase):
    def test_the_manifest_sits_at_the_plugin_root(self) -> None:
        """Clients must find it at `plugin.json` in the root; a manifest in a
        host-specific directory is invisible to every other client."""
        self.assertTrue(MANIFEST.is_file(), MANIFEST)

    def test_only_permitted_fields_are_declared(self) -> None:
        extra = sorted(set(_manifest()) - PERMITTED)
        self.assertEqual(extra, [], f"the schema is closed; these are not allowed: {extra}")

    def test_the_schema_field_is_the_exact_constant(self) -> None:
        self.assertEqual(_manifest().get("$schema"), SCHEMA_URL)

    def test_the_name_matches_the_required_pattern(self) -> None:
        import re

        name = _manifest()["name"]
        self.assertRegex(name, r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
        self.assertLessEqual(len(name), 64)

    def test_host_specific_data_lives_under_a_reverse_domain_namespace(self) -> None:
        """Anything host-specific belongs in `extensions`, keyed so a client
        that does not implement the namespace ignores it without validating."""
        extensions = _manifest().get("extensions", {})
        self.assertIsInstance(extensions, dict)
        for namespace, value in extensions.items():
            self.assertRegex(namespace, r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$", namespace)
            self.assertIsInstance(value, dict, namespace)

    def test_component_locations_are_not_overridden(self) -> None:
        """`plugin.json` cannot relocate components or configure them inline;
        the host manifests carry a `skills` path and this one must not."""
        manifest = _manifest()
        for forbidden in ("skills", "mcpServers", "hooks", "commands", "agents"):
            self.assertNotIn(forbidden, manifest, forbidden)


class LayoutTests(unittest.TestCase):
    def test_skills_are_discoverable_at_the_fixed_location(self) -> None:
        skills = sorted(p.parent.name for p in (PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 1, skills)

    def test_no_mcp_manifest_is_shipped(self) -> None:
        """This product declares no MCP server, and an empty `mcp.json` would
        advertise one that does not exist."""
        self.assertFalse((PLUGIN_ROOT / "mcp.json").exists())


class HonestyTests(unittest.TestCase):
    def test_the_description_states_what_the_portable_package_omits(self) -> None:
        """A client without hook support installs the skills and none of the
        enforcement. A governance tool that does not say so is mis-sold."""
        description = _manifest()["description"].lower()
        self.assertIn("hook", description)

    def test_the_version_matches_the_other_surfaces(self) -> None:
        host = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(_manifest()["version"], host["version"])


if __name__ == "__main__":
    unittest.main()
