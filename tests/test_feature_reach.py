"""Feature reach per host, in code (obligation 10119, program items 1, 2, 5, 6).

docs/HOST-FEATURE-REACH.md was written by hand on 2026-09-08 because no
artefact stated which feature can fire on which host. This table is that
artefact in code: every hook-borne feature carries a status on every host,
`hooks status` and `doctor --host` render it, and the preflight gate treats
a declared host with no live proof as a finding instead of silence.
"""
from __future__ import annotations

import argparse
import os
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

from godmode_runtime import godmode_reach as reach  # noqa: E402
from godmode_runtime.godmode_console import Runtime, cmd_hooks, cmd_doctor  # noqa: E402
from test_godmode_runtime import isolated_project  # noqa: E402

STATUSES = {"yes", "partial", "no"}


class ReachTableTests(unittest.TestCase):
    def test_every_feature_has_a_status_and_a_reason_on_every_host(self) -> None:
        table = reach.reach_table()
        self.assertGreaterEqual(len(reach.FEATURES), 10)
        for host in reach.HOSTS:
            for feature in reach.FEATURES:
                cell = table[host][feature]
                self.assertIn(cell["status"], STATUSES, (host, feature))
                self.assertTrue(cell["reason"].strip(), (host, feature))

    def test_the_hosts_are_the_declared_hosts_plus_the_hookless_adapters(self) -> None:
        self.assertEqual(set(reach.HOSTS), {
            "claude", "codex", "grok", "cursor", "gemini", "antigravity",
            "copilot", "kiro", "opencode", "pi", "goose"})

    def test_claude_is_the_baseline_and_a_hookless_adapter_cannot_fire_prompt_features(self) -> None:
        table = reach.reach_table()
        self.assertEqual(table["claude"]["pre-tool-gate"]["status"], "yes")
        self.assertEqual(table["goose"]["prompt-nudges"]["status"], "no")

    def test_a_host_summary_names_what_cannot_fire(self) -> None:
        summary = reach.host_reach("gemini")
        self.assertIn("cannot_fire", summary)
        self.assertIn("done-bar", summary["cannot_fire"])
        self.assertEqual(summary["host"], "gemini")

    def test_every_host_carries_a_tier_from_the_closed_set(self) -> None:
        # R-3a: a host with no hook dispatch gets a named fallback tier
        # instead of reading as "unverifiable" - opencode is a shim,
        # goose is mcp, pi is none; every hook-dispatch host is "hook".
        self.assertEqual(reach.validate_tiers(), [])
        for host in reach.HOSTS:
            self.assertIn(reach.host_tier(host), reach.TIERS, host)
        for host in reach.HOOK_HOSTS:
            self.assertEqual(reach.host_tier(host), "hook", host)
        self.assertEqual(reach.host_tier("opencode"), "shim")
        self.assertEqual(reach.host_tier("goose"), "mcp")
        self.assertEqual(reach.host_tier("pi"), "none")

    def test_a_host_without_a_tier_fails_the_matrix_test(self) -> None:
        # The matrix-test guard R-3a's acceptance names: seed a row that is
        # missing its tier and prove `validate_tiers()` catches it, rather
        # than defaulting it to something that would read as fine.
        with mock.patch.dict(reach.TIER, {}, clear=True):
            self.assertEqual(set(reach.validate_tiers()), set(reach.HOSTS))
        with mock.patch.dict(reach.TIER, {"claude": "not-a-real-tier"}):
            self.assertIn("claude", reach.validate_tiers())

    def test_a_stale_tier_entry_for_an_undeclared_host_fails_the_matrix_test(self) -> None:
        # N4 (task-3-review.md): validate_tiers() iterating HOSTS alone
        # would never notice a TIER key for a host that no longer exists -
        # a symmetric-difference check is needed, not just the one-way scan.
        with mock.patch.dict(reach.TIER, {"retired-host": "hook"}):
            self.assertIn("retired-host", reach.validate_tiers())
            # Every real host's own tier is unaffected by the stray entry.
            for host in reach.HOSTS:
                self.assertNotIn(host, reach.validate_tiers())

    def test_unverifiable_hosts_are_the_declared_hosts_with_no_live_proof(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            hosts = reach.unverifiable_hosts(archive)
            # No proof recorded for anybody: every declared hook host is listed.
            self.assertEqual(set(hosts), {"claude", "codex", "grok", "cursor", "gemini",
                                          "antigravity", "copilot", "kiro"})
            finding = reach.reach_finding(archive)
            self.assertEqual(finding["check"], "host-reach")
            self.assertIn("unverifiable", finding["detail"])


class ReachRenderingTests(unittest.TestCase):
    def test_hooks_status_carries_the_reach_row_for_the_host(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            runtime = Runtime(archive=archive, anchor=_anchor)
            args = argparse.Namespace(hooks_command="status", host="codex", git=False)
            payload = cmd_hooks(args, runtime).payload
            self.assertIn("reach", payload)
            self.assertIn("pre-tool-gate", payload["reach"])
            # R-3a: `hooks status` prints the named fallback tier alongside
            # the reach row.
            self.assertEqual(payload["tier"], "hook")

    def test_doctor_host_names_the_features_that_cannot_fire(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            runtime = Runtime(archive=archive, anchor=_anchor)
            args = argparse.Namespace(host="gemini", verbs=False)
            payload = cmd_doctor(args, runtime).payload
            self.assertIn("reach", payload)
            self.assertIn("done-bar", payload["reach"]["cannot_fire"])


if __name__ == "__main__":
    unittest.main()
