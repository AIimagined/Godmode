"""The MCP ledger adapter, driven over real stdio JSON-RPC.

MCP tools are additive - no hook over a host's other tools exists in the
protocol - so this adapter is the ledger only, and the battery proves the
protocol conversation works: initialize, tools/list, a real claim call
that lands a record in a real archive.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402

SERVER = PLUGIN_ROOT / "adapters" / "goose" / "godmode_mcp_server.py"


@contextmanager
def _project():
    with tempfile.TemporaryDirectory(prefix="godmode-mcp-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        (root / "README.md").write_text("# bed\n", encoding="utf-8")
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield root, archive


def _converse(project: Path, requests: list[dict]) -> list[dict]:
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    done = subprocess.run(
        [sys.executable, str(SERVER), "--project", str(project)],
        input=payload, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
        env=dict(os.environ))
    return [json.loads(line) for line in done.stdout.splitlines() if line.strip()]


class McpAdapterTests(unittest.TestCase):
    def test_initialize_and_list(self) -> None:
        with _project() as (root, _archive):
            replies = _converse(root, [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ])
            self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "godmode")
            names = [t["name"] for t in replies[1]["result"]["tools"]]
            self.assertIn("godmode_claim", names)
            self.assertEqual(len(names), 4)

    def test_a_claim_call_lands_a_real_record(self) -> None:
        with _project() as (root, archive):
            replies = _converse(root, [
                {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "godmode_claim",
                            "arguments": {"text": "the mcp bed claim holds",
                                          "cites": ["file:README.md"]}}},
            ])
            text = replies[1]["result"]["content"][0]["text"]
            self.assertIn("observed", text)
            claims = [r for r in archive.read_events(verify=False)
                      if r.get("kind") == "claim"]
            self.assertTrue(any("mcp bed claim" in str(r.get("subject", ""))
                                for r in claims))

    def test_unknown_method_answers_method_not_found(self) -> None:
        with _project() as (root, _archive):
            replies = _converse(root, [
                {"jsonrpc": "2.0", "id": 9, "method": "prompts/list"},
            ])
            self.assertEqual(replies[0]["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
