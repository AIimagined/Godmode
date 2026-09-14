"""A hook returns on the first complete JSON payload, not on EOF.

Sweep 2026-09-07 (a hook-bearing plugin in the research ledger fixed the
same class in three of its own issues): under the Windows pipe
implementation a host's stdin close can lag arbitrarily, so a
hook that reads to EOF sits with its work done until the host's timeout.
Every godmode hook read to EOF. Each now resolves on the first complete
JSON object (2 MiB cap) and exits while the host still holds the pipe open.
Obligation 9863.
"""
from __future__ import annotations

import importlib.util
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

_spec = importlib.util.spec_from_file_location("godmode_stdin", HOOKS / "godmode_stdin.py")
godmode_stdin = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(godmode_stdin)

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
        except OSError:  # godmode: swallow-ok: best-effort read: the failure is the non-event here
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


class ParseFirstJsonBomMalformedTests(unittest.TestCase):
    """Fix round 1: `parse_first_json` must distinguish "nothing meaningful
    was ever sent" (truly empty/whitespace-only stdin - not malformed, the
    pre-existing contract) from "something was sent and none of it is a
    JSON value" (a bare BOM, or a BOM plus only whitespace - malformed,
    exactly as `json.loads` treated it before this module's decode existed:
    `"﻿".strip()` is truthy in Python, a BOM is content, not
    whitespace, to `str.strip()`). `_LSTRIP_PREFIX` treats a BOM as
    whitespace for `read_first_json`'s OWN "is the object complete yet"
    question, which is a different question from "was this empty" - the
    bug this fixes conflated the two and silently turned a bare BOM into
    `({}, False)`, indistinguishable from a TTY.
    """

    def test_bare_bom_is_malformed(self) -> None:
        value, malformed = godmode_stdin.parse_first_json(b"\xef\xbb\xbf")
        self.assertEqual(value, {})
        self.assertTrue(malformed)

    def test_bom_followed_by_crlf_is_malformed(self) -> None:
        value, malformed = godmode_stdin.parse_first_json(b"\xef\xbb\xbf\r\n")
        self.assertEqual(value, {})
        self.assertTrue(malformed)

    def test_bom_followed_by_only_spaces_is_malformed(self) -> None:
        value, malformed = godmode_stdin.parse_first_json(b"\xef\xbb\xbf   ")
        self.assertEqual(value, {})
        self.assertTrue(malformed)

    def test_truly_empty_stdin_is_not_malformed(self) -> None:
        value, malformed = godmode_stdin.parse_first_json(b"")
        self.assertEqual(value, {})
        self.assertFalse(malformed)

    def test_whitespace_only_with_no_bom_is_not_malformed(self) -> None:
        """Green control, not a new claim: this shape has always meant
        "nothing sent" (pre-b7cfe61 `_input()` used the identical
        `str.strip()` emptiness test), and the fix must not widen
        `malformed` to cover it - only a BOM (or other `_LSTRIP_PREFIX`
        content) with nothing behind it is new territory."""
        value, malformed = godmode_stdin.parse_first_json(b"   \r\n  ")
        self.assertEqual(value, {})
        self.assertFalse(malformed)

    def test_bom_prefixed_valid_object_still_parses_clean(self) -> None:
        """Regression guard for the round-0 fix this round corrects: a BOM
        prefix in front of a REAL JSON object must still parse successfully,
        never malformed."""
        raw = b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode("utf-8")
        value, malformed = godmode_stdin.parse_first_json(raw)
        self.assertEqual(value, {"a": 1})
        self.assertFalse(malformed)

    def test_bom_prefixed_object_with_trailing_data_still_parses_the_first_object(self) -> None:
        raw = (b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode("utf-8")
               + b"\nnot json at all")
        value, malformed = godmode_stdin.parse_first_json(raw)
        self.assertEqual(value, {"a": 1})
        self.assertFalse(malformed)


if __name__ == "__main__":
    unittest.main()
