"""The OpenCode shim: a Bun plugin that throws on the gate's deny.

OpenCode (opencode.ai/docs/plugins) loads JS/TS modules from
`.opencode/plugins/`; the documented way to stop a tool is to throw from
`tool.execute.before`. The shim spawns the real gate with a Claude-shaped
payload and GODMODE_HOST=opencode, so every decision and record stays in
Python. These tests drive the shipped file through Bun when Bun is on this
machine, and fall back to static checks when it is not - a missing runtime
skips the behavioural half rather than faking it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

SHIM = PLUGIN_ROOT / "adapters" / "opencode" / "godmode.opencode.js"
BUN = shutil.which("bun")

HARNESS = """
import plugin from %(shim)s;
const hooks = await plugin({ directory: %(directory)s });
const tool = process.argv[2];
const args = JSON.parse(process.argv[3]);
try {
  await hooks["tool.execute.before"]({ tool, sessionID: "s1" }, { args });
  console.log(JSON.stringify({ blocked: false }));
} catch (error) {
  console.log(JSON.stringify({ blocked: true, message: String(error.message) }));
}
"""


class StaticShapeTests(unittest.TestCase):
    def test_the_shim_uses_the_documented_hook_and_the_real_gate(self) -> None:
        text = SHIM.read_text(encoding="utf-8")
        self.assertIn('"tool.execute.before"', text)
        self.assertIn("hooks/godmode_gate_fast.py", text)
        self.assertIn("GODMODE_HOST", text)
        self.assertIn("throw new Error", text)

    def test_the_adapter_doc_names_the_shim(self) -> None:
        doc = (PLUGIN_ROOT / "adapters" / "opencode" / "AGENTS-godmode.md").read_text(encoding="utf-8")
        self.assertIn("godmode.opencode.js", doc)
        self.assertIn("GODMODE_PLUGIN_ROOT", doc)


@unittest.skipUnless(BUN, "bun is not installed on this machine")
class BunBehaviourTests(unittest.TestCase):
    def _run(self, project: Path, state: Path, tool: str, args: dict) -> dict:
        harness = project / "harness.mjs"
        harness.write_text(HARNESS % {
            "shim": json.dumps(SHIM.as_posix()),
            "directory": json.dumps(project.as_posix()),
        }, encoding="utf-8")
        env = {**os.environ, "GODMODE_PLUGIN_ROOT": PLUGIN_ROOT.as_posix(),
               "GODMODE_STATE_HOME": str(state), "GODMODE_PYTHON": sys.executable}
        env.pop("GODMODE_HOST", None)
        done = subprocess.run([BUN, "run", str(harness), tool, json.dumps(args)],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=180, env=env, cwd=str(project))
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_a_force_push_is_thrown_and_a_read_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                Chronicle(resolve_anchor(project)).initialize()
            blocked = self._run(project, state, "bash", {"command": "git push --force origin main"})
            self.assertTrue(blocked["blocked"], blocked)
            self.assertIn("git-history-or-remote", blocked["message"])
            allowed = self._run(project, state, "bash", {"command": "git status"})
            self.assertFalse(allowed["blocked"], allowed)

    def test_an_ask_tier_call_folds_to_a_throw_with_the_staged_remedy(self) -> None:
        # OpenCode cannot render "ask"; the gate folds it to deny for this
        # host and names the staged-capability escape hatch.
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                Chronicle(resolve_anchor(project)).initialize()
            result = self._run(project, state, "bash", {"command": "rm -rf build"})
            self.assertTrue(result["blocked"], result)
            self.assertIn("authorize stage", result["message"])

    def test_a_missing_root_warns_and_allows(self) -> None:
        # Field report 2026-08-29: the old fail-closed-on-unset-root bricked
        # a live session down to `dir`. Unconfigured is not hostile: the call
        # passes, and the warning names exactly what is not running.
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            harness = project / "harness.mjs"
            harness.write_text(HARNESS % {
                "shim": json.dumps(SHIM.as_posix()),
                "directory": json.dumps(project.as_posix()),
            }, encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k != "GODMODE_PLUGIN_ROOT"}
            done = subprocess.run([BUN, "run", str(harness), "bash", json.dumps({"command": "ls"})],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=60, env=env, cwd=str(project))
            result = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertFalse(result["blocked"], result)
            self.assertIn("GODMODE_PLUGIN_ROOT", done.stderr)
            self.assertIn("NOT", done.stderr)

    def test_the_node_runtime_blocks_the_same_deny(self) -> None:
        # Field report 2026-08-29: the host ran Node while the shim called
        # Bun.spawn. The same protected command must block under Node.
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed on this machine")
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            project.mkdir()
            state = base / "state"
            with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)}, clear=False):
                Chronicle(resolve_anchor(project)).initialize()
            harness = project / "harness.mjs"
            # Node's ESM loader refuses a bare Windows absolute path
            # (ERR_UNSUPPORTED_ESM_URL_SCHEME); a file:// URL loads on both.
            harness.write_text(HARNESS % {
                "shim": json.dumps(SHIM.as_uri()),
                "directory": json.dumps(project.as_posix()),
            }, encoding="utf-8")
            env = {**os.environ, "GODMODE_PLUGIN_ROOT": PLUGIN_ROOT.as_posix(),
                   "GODMODE_STATE_HOME": str(state), "GODMODE_PYTHON": sys.executable}
            env.pop("GODMODE_HOST", None)
            done = subprocess.run([node, str(harness), "bash",
                                   json.dumps({"command": "rm -rf build"})],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=180, env=env, cwd=str(project))
            self.assertEqual(done.returncode, 0, done.stderr)
            result = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertTrue(result["blocked"], result)


if __name__ == "__main__":
    unittest.main()
