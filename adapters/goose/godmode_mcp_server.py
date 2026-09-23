"""Godmode's goose MCP extension entry point.

The real, host-generic server lives at `scripts/godmode_mcp_server.py`
(NS-10l: one implementation, two hosts). This file is the thin shim
goose's own extension config points at, fixing the host identity to
"goose" so its serverInfo name and manifest posture are unchanged by this
task - the wire protocol, the tool table, and the per-request/no-port/
no-daemon shape (decision seq 11) all live in the one file this shim
imports.

MCP tools are ADDITIVE - the protocol has no hook over a host's other
tools, so this adapter cannot gate anything and does not pretend to.

Wire into goose as a stdio extension:
    command: python3   # or python / py - whichever `-c "import sys"` answers on this machine
    args: [<godmode root>/adapters/goose/godmode_mcp_server.py,
           --project, <the project directory>]
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.godmode_mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main(host="goose")
