"""Static shape of the pi extension shim - the contract, testable without pi.

A live pi session grades the adapter later (SOFT until a chronicled
block, same ladder as OpenCode); what this battery pins is the doctrine
the file must carry: fail-closed once configured, warn-and-allow when
unconfigured, no decision logic of its own, ask folded to deny.
"""

from __future__ import annotations

from pathlib import Path
import unittest

SHIM = Path(__file__).resolve().parents[1] / "adapters" / "pi" / "godmode-pi-extension.ts"


class PiShimShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SHIM.read_text(encoding="utf-8")

    def test_registers_the_pre_execution_event(self) -> None:
        self.assertIn('pi.on("tool_call"', self.text)

    def test_fails_closed_on_non_allow(self) -> None:
        self.assertIn('if (decision !== "allow")', self.text)
        self.assertIn("throw new Error(`godmode: ${reason}`)", self.text)

    def test_unconfigured_warns_and_allows(self) -> None:
        self.assertIn("GODMODE_PLUGIN_ROOT is not set", self.text)
        self.assertIn("warnedUnconfigured", self.text)

    def test_no_bypass_variable_once_configured(self) -> None:
        self.assertNotIn("GODMODE_BYPASS", self.text)
        self.assertNotIn("GODMODE_DISABLE", self.text)

    def test_the_gate_owns_every_decision(self) -> None:
        # The shim maps tools and relays; it must not contain allow-listing
        # of operations - only tool-name mapping.
        self.assertNotIn("force", self.text.lower())
        self.assertIn("godmode_gate_fast.py", self.text)

    def test_identifies_its_host_to_the_gate(self) -> None:
        self.assertIn('GODMODE_HOST: "pi"', self.text)


if __name__ == "__main__":
    unittest.main()
