"""CX-6: the live-host layer.

Everything in `test_host_e2e.py` proves the hook subprocess behaves
correctly when FED a real host's payload shape. It never proves a real
Codex or Grok binary actually calls this plugin the way its own manifest
claims - that stronger claim needs the real binary, on the real machine it
is installed on, running a real session against a real godmode-governed
project.

This file is that layer, and it is deliberately NOT part of the ordinary
CI/local run: it is env-gated (`GODMODE_E2E_CODEX=1` / `GODMODE_E2E_GROK=1`)
and skips CLEANLY, with an honest message naming exactly what was missing,
whenever the gate is off or the named binary is not present on PATH. This
is structure only, matching the plan's own instruction ("CX-3's Codex event
names and CX-6's live runs depend on the operator's Codex environment for
final verification; unit layers must pass without it") - an operator runs
this deliberately, against their own real Codex/Grok install, to close the
gap `docs/CAPABILITY-COVERAGE.md`'s interception row states honestly as
open.

What "passes" here proves: `godmode hooks probe --host <name>` (CX-1's own
self-injection probe) reaches `HARD` when run from inside a real Codex/Grok
session - i.e., the real host's own runtime is wired to call this plugin's
hook on a real tool call, not merely that the hook script behaves correctly
when invoked directly (that gap is named explicitly in `godmode_hookproof.
run_probe`'s own docstring: "It does NOT prove a live host's own runtime is
wired to call this script on real tool calls").
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PLUGIN_ROOT / "scripts"
GODMODE_CLI = SCRIPTS / "godmode.py"

LIVE_HOSTS = {
    "codex": {"env": "GODMODE_E2E_CODEX", "binary": "codex"},
    "grok": {"env": "GODMODE_E2E_GROK", "binary": "grok"},
}


def _skip_reason(host: str) -> str | None:
    """`None` when this live-host run should proceed; otherwise an honest,
    specific reason a reader can act on (set the env var, or install/PATH
    the named binary) - never a bare "skipped"."""
    spec = LIVE_HOSTS[host]
    if not os.environ.get(spec["env"]):
        return (f"live {host} verification is operator-run: set "
                f"{spec['env']}=1 to enable it (skipped by default so the "
                "ordinary suite never depends on a host binary being "
                "installed on this machine)")
    if shutil.which(spec["binary"]) is None:
        return (f"{spec['env']}=1 is set, but no {spec['binary']!r} binary "
                f"was found on PATH - install/PATH the real {host} CLI to "
                "run this layer for real")
    return None


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GODMODE_CLI), "--project", str(cwd), "--json", *args],
        capture_output=True, text=True, cwd=str(cwd), timeout=60,
    )


class LiveCodexHooksProbeTests(unittest.TestCase):
    HOST = "codex"

    def setUp(self) -> None:
        reason = _skip_reason(self.HOST)
        if reason:
            self.skipTest(reason)

    def test_hooks_probe_reaches_hard_from_inside_a_real_codex_session(self) -> None:
        """Run from inside a real Codex session, against THIS repository
        (the operator's own real godmode-governed project) - a synthetic
        temp project would not be wired into the operator's actual Codex
        plugin installation, and this test exists specifically to prove
        that live wiring, not the hook script in isolation.
        """
        completed = _run_cli("hooks", "probe", "--host", self.HOST, cwd=PLUGIN_ROOT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["state"], "HARD", report)

    def test_hooks_status_agrees_afterward(self) -> None:
        completed = _run_cli("hooks", "status", "--host", self.HOST, cwd=PLUGIN_ROOT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["verdict"], "HARD", report)


class LiveGrokHooksProbeTests(unittest.TestCase):
    HOST = "grok"

    def setUp(self) -> None:
        reason = _skip_reason(self.HOST)
        if reason:
            self.skipTest(reason)

    def test_hooks_probe_reaches_hard_from_inside_a_real_grok_session(self) -> None:
        completed = _run_cli("hooks", "probe", "--host", self.HOST, cwd=PLUGIN_ROOT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["state"], "HARD", report)

    def test_hooks_status_agrees_afterward(self) -> None:
        completed = _run_cli("hooks", "status", "--host", self.HOST, cwd=PLUGIN_ROOT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["verdict"], "HARD", report)


class SkipMessageHonestyTests(unittest.TestCase):
    """The skip message itself is part of this file's contract: a reader
    hitting a skipped live-host test must be told exactly what to do, never
    left with a bare 'skipped'."""

    def test_an_unset_env_var_names_the_exact_variable_to_set(self) -> None:
        env_backup = os.environ.pop("GODMODE_E2E_CODEX", None)
        try:
            reason = _skip_reason("codex")
            self.assertIsNotNone(reason)
            self.assertIn("GODMODE_E2E_CODEX", reason)
        finally:
            if env_backup is not None:
                os.environ["GODMODE_E2E_CODEX"] = env_backup

    def test_a_set_env_var_with_no_binary_names_the_missing_binary(self) -> None:
        env_backup = os.environ.get("GODMODE_E2E_CODEX")
        os.environ["GODMODE_E2E_CODEX"] = "1"
        try:
            if shutil.which("codex") is not None:
                self.skipTest("a real codex binary is on PATH in this environment; "
                             "the missing-binary message cannot be exercised here")
            reason = _skip_reason("codex")
            self.assertIsNotNone(reason)
            self.assertIn("codex", reason)
            self.assertIn("PATH", reason)
        finally:
            if env_backup is None:
                os.environ.pop("GODMODE_E2E_CODEX", None)
            else:
                os.environ["GODMODE_E2E_CODEX"] = env_backup


if __name__ == "__main__":
    unittest.main()
