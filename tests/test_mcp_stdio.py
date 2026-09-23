"""One stdio MCP adapter serves two hosts identically; it is per-request, portless."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER = PLUGIN_ROOT / "scripts" / "godmode_mcp_server.py"


class McpStdioTests(unittest.TestCase):
    def _rpc(self, host: str, project: Path, messages: list[dict]) -> list[dict]:
        env = dict(os.environ, GODMODE_STATE_HOME=str(project / ".state"))
        stdin = "".join(json.dumps(m) + "\n" for m in messages)
        proc = subprocess.run([sys.executable, str(SERVER), "--project", str(project), "--host", host], input=stdin, capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    def test_two_hosts_same_tools(self) -> None:
        import tempfile
        project = Path(tempfile.mkdtemp()); self.addCleanup(__import__("shutil").rmtree, project, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "nope", "params": {}}]
        goose = self._rpc("goose", project, msgs); cursor = self._rpc("cursor", project, msgs)
        self.assertEqual([t["name"] for t in goose[1]["result"]["tools"]], [t["name"] for t in cursor[1]["result"]["tools"]])
        self.assertEqual(goose[2]["error"]["code"], -32601)
        self.assertIn("godmode", cursor[0]["result"]["serverInfo"]["name"])

    def test_cursor_manifest_is_generated(self) -> None:
        from importlib import import_module
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
        hm = import_module("godmode_runtime.godmode_host_manifests")
        manifest = hm.build_cursor_mcp_manifest(PLUGIN_ROOT)  # adapt to the real builder name you add
        self.assertIn("godmode", manifest["mcpServers"])


class McpBindingsDriftTests(unittest.TestCase):
    """Fix round 1: the Cursor MCP manifest must be drift-checked by the same
    `godmode_bindings.check()`/`write()` mechanism as the identity and hook
    manifests - not merely generated once by hand and then invisible to a
    later change in `build_cursor_mcp_manifest`."""

    def _built_project(self) -> Path:
        import tempfile

        project = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, project, ignore_errors=True)
        (project / "packaging").mkdir()
        (project / "packaging" / "hosts.json").write_text(
            (PLUGIN_ROOT / "packaging" / "hosts.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        (project / "hooks").mkdir()
        (project / "hooks" / "hooks.json").write_text(
            (PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        return project

    def test_an_edited_cursor_mcp_manifest_is_drifted_and_write_restores_it(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
        from godmode_runtime import godmode_bindings as bindings

        project = self._built_project()
        bindings.write(project)
        target = project / ".cursor-plugin" / "mcp.json"
        self.assertTrue(target.is_file())
        original = target.read_text(encoding="utf-8")
        self.assertEqual(bindings.check(project)["verdict"], "current")

        target.write_text(original.replace("godmode", "not-godmode"), encoding="utf-8")
        report = bindings.check(project)
        mcp_entries = [r for r in report["hosts"] if r.get("kind") == "mcp"]
        self.assertEqual(len(mcp_entries), 1, report["hosts"])
        self.assertEqual(mcp_entries[0]["state"], "drifted", mcp_entries)
        self.assertEqual(mcp_entries[0]["path"], ".cursor-plugin/mcp.json")
        self.assertEqual(report["verdict"], "drifted")

        restored = bindings.write(project)
        self.assertIn(".cursor-plugin/mcp.json", restored["written"], restored)
        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(bindings.check(project)["verdict"], "current")


if __name__ == "__main__":
    unittest.main()
