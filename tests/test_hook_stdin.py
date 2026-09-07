"""A hook returns on the first complete JSON payload, not on EOF.

Sweep 2026-09-07 (a hook-bearing plugin in the research ledger 9ed2c39, their #729/#833/#949): under the
Windows pipe implementation a host's stdin close can lag arbitrarily, so a
hook that reads to EOF sits with its work done until the host's timeout.
Every godmode hook read to EOF. Each now resolves on the first complete
JSON object (2 MiB cap) and exits while the host still holds the pipe open.
Obligation 9863.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS = PLUGIN_ROOT / "hooks"
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from _host_env import HOST_MARKERS  # noqa: E402

HOLD_OPEN_SECONDS = 20


def _exits_with_stdin_held_open(argv: list[str], payload: dict, cwd: Path) -> subprocess.Popen:
    environment = {k: v for k, v in os.environ.items() if k not in HOST_MARKERS}
    environment["CLAUDE_CODE_ENTRYPOINT"] = "cli"
    proc = subprocess.Popen(
        [sys.executable, *argv], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd=str(cwd), env=environment)
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload).encode("utf-8"))
    proc.stdin.flush()
    # The pipe stays open: no close(), no communicate(). A reader that waits
    # for EOF never returns from here.
    try:
        proc.wait(timeout=HOLD_OPEN_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise AssertionError(f"{argv[0]} waited for EOF instead of the payload")
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
    return proc


class FirstJsonTests(unittest.TestCase):
    def test_the_fast_gate_returns_on_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc = _exits_with_stdin_held_open(
                [str(HOOKS / "godmode_gate_fast.py")],
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git status"}, "cwd": temporary},
                Path(temporary))
        self.assertEqual(proc.returncode, 0)

    def test_the_session_hook_returns_on_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc = _exits_with_stdin_held_open(
                [str(HOOKS / "godmode_session_hook.py"), "pre-action"],
                {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "git status"}, "cwd": temporary},
                Path(temporary))
        self.assertEqual(proc.returncode, 0)

    def test_the_post_edit_hook_returns_on_the_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "notes.md"
            target.write_text("x\n", encoding="utf-8")
            proc = _exits_with_stdin_held_open(
                [str(HOOKS / "godmode_post_edit.py")],
                {"hook_event_name": "PostToolUse", "tool_name": "Write",
                 "tool_input": {"file_path": str(target)}, "cwd": temporary},
                Path(temporary))
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
