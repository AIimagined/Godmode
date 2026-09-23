"""Godmode as an MCP server: the record-layer verbs for MCP-extension hosts.

MCP hosts load extensions as MCP servers, and MCP tools are ADDITIVE - the
protocol has no hook over a host's other tools, so this adapter cannot gate
anything and does not pretend to. What it offers is the record layer:
claim, checkpoint, status, and resume as tools the model can call, each
shelling to the godmode CLI so the Python runtime owns every record and
every grade. The capability table grades such a host
`tool_call_interception: none (ledger only)` - an honest rung below the
hook-carrying hosts, stated rather than implied.

Native JSON-RPC 2.0 over stdio, no SDK dependency: initialize, tools/list,
tools/call. Anything else answers method-not-found.

NS-10l (decision seq 11 - no daemons/listeners): one implementation, host-
generic. `--host` selects only the `serverInfo.name` suffix and which
manifest documents it (goose's own extension config; Cursor's `mcp.json`)
- the wire protocol, the tool table, and the per-request/no-port/no-daemon
shape are identical for every host this file serves.
`adapters/goose/godmode_mcp_server.py` is a thin shim that imports this
module and fixes host="goose", so goose's own manifest and this server's
identity are unchanged by this file having moved.

Wire into an MCP host as a stdio extension:
    command: python3   # or python / py - whichever `-c "import sys"` answers on this machine
    args: [<godmode root>/scripts/godmode_mcp_server.py,
           --project, <the project directory>, --host, <goose|cursor>]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _runtime_version() -> str:
    """The runtime's own declared version, never a literal that a bump can miss."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from godmode_runtime.godmode_constants import RUNTIME_VERSION
        return str(RUNTIME_VERSION)
    except Exception:  # godmode: swallow-ok: a version string is advisory in a handshake
        return "unknown"

ROOT = Path(__file__).resolve().parents[1]
GODMODE = ROOT / "scripts" / "godmode.py"

# Every host this one implementation is wired to today. Adding a host is
# adding a manifest that points here with a new `--host` value and a name
# in this tuple - never a fork of `serve`.
HOSTS = ("goose", "cursor")

TOOLS = [
    {
        "name": "godmode_claim",
        "description": "Record a claim with citations; unsupported claims are "
                       "downgraded, not warned about. Cite evidence as "
                       "file:<path>, cmd:<command>, seq:<n>, doc:/url:.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "cites": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "godmode_checkpoint",
        "description": "Record a recoverable handoff point with a status and "
                       "next actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "status": {"type": "string"},
                "next": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "status"],
        },
    },
    {
        "name": "godmode_status_remaining",
        "description": "The work frontier: ready and blocked items with "
                       "evidence tiers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "godmode_resume",
        "description": "The bounded continuity brief reconstructed from the "
                       "local record.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _cli(project: str, *args: str) -> str:
    done = subprocess.run(
        [sys.executable, str(GODMODE), "--project", project, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180)
    body = (done.stdout or "").strip() or (done.stderr or "").strip()
    return body[:8000]


def _call(project: str, name: str, arguments: dict) -> str:
    if name == "godmode_claim":
        args = ["claim", str(arguments.get("text", ""))]
        for cite in arguments.get("cites", []) or []:
            args += ["--cite", str(cite)]
        if arguments.get("confidence") is not None:
            args += ["--confidence", str(arguments["confidence"])]
        return _cli(project, *args)
    if name == "godmode_checkpoint":
        args = ["checkpoint", "--summary", str(arguments.get("summary", "")),
                "--status", str(arguments.get("status", "progress"))]
        for step in arguments.get("next", []) or []:
            args += ["--next", str(step)]
        return _cli(project, *args)
    if name == "godmode_status_remaining":
        return _cli(project, "status", "remaining")
    if name == "godmode_resume":
        return _cli(project, "resume")
    return json.dumps({"error": f"unknown tool {name}"})


def _server_name(host: str) -> str:
    """goose keeps the bare name it shipped with before this file was
    host-generic (its manifest, and any operator-visible identity, already
    say "godmode"); every other host gets a `-<host>` suffix so two servers
    of this kind never collide in a host that lists MCP servers by name."""
    return "godmode" if host == "goose" else f"godmode-{host}"


def serve(project: str, host: str = "goose") -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        request_id = request.get("id")
        method = request.get("method", "")
        if method == "initialize":
            # An MCP initialize IS a session boundary: open the godmode
            # session here so record-writing tools work without the model
            # having to know the opening ritual. Best-effort - an already-
            # open session or a refusal must not fail the handshake.
            try:
                _cli(project, "session", "open")
            except Exception:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
                pass
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": _server_name(host), "version": _runtime_version()},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params", {})
            text = _call(project, str(params.get("name", "")),
                         params.get("arguments", {}) or {})
            result = {"content": [{"type": "text", "text": text}]}
        elif method.startswith("notifications/"):
            continue
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": request_id,
                              "error": {"code": -32601,
                                        "message": f"method not found: {method}"}}),
                  flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": request_id,
                          "result": result}), flush=True)


def main(host: str | None = None) -> None:
    """Entry point shared by every host's own file. `host`, when given,
    fixes the server identity regardless of what `--host` argv carries (or
    whether it is present at all) - the shape `adapters/goose/
    godmode_mcp_server.py`'s shim calls with (`main(host="goose")`), so
    goose needs no `--host` argument in its own manifest at all."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--host", default="goose", choices=HOSTS)
    args = parser.parse_args()
    serve(args.project, host or args.host)


if __name__ == "__main__":
    main()
