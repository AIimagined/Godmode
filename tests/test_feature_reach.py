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
            "opencode", "pi", "goose"})

    def test_claude_is_the_baseline_and_a_hookless_adapter_cannot_fire_prompt_features(self) -> None:
        table = reach.reach_table()
        self.assertEqual(table["claude"]["pre-tool-gate"]["status"], "yes")
        self.assertEqual(table["goose"]["prompt-nudges"]["status"], "no")

    def test_a_host_summary_names_what_cannot_fire(self) -> None:
        summary = reach.host_reach("gemini")
        self.assertIn("cannot_fire", summary)
        self.assertIn("done-bar", summary["cannot_fire"])
        self.assertEqual(summary["host"], "gemini")

    def test_unverifiable_hosts_are_the_declared_hosts_with_no_live_proof(self) -> None:
        with isolated_project() as (project, _state, _anchor, archive):
            archive.initialize()
            hosts = reach.unverifiable_hosts(archive)
            # No proof recorded for anybody: every declared hook host is listed.
            self.assertEqual(set(hosts), {"claude", "codex", "grok", "cursor", "gemini", "antigravity"})
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
