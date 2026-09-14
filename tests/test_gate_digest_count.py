"""G-7: `status remaining --digest`'s gate counts must reflect THIS
session's refusals exactly - no artificial 500-record cap, and no
filter that can never match a real refusal record, and no filter that
lets a later session steal an earlier one's refusals
(`godmode_console.session_digest`).

Fix round 1: a `refusal` record carries no `session` field at all -
`godmode_session_hook.py` writes it mid-tool-call, with no notion of the
chronicle's own `S-<hash>` session key - so an exact-match filter on
that field matched zero real refusals and counted 0 forever. Scoped
"this session" instead by the same sequence-range convention
`godmode_contribution._session_records` already uses for other untagged
record kinds: a `session`-kind boundary record via `open_session`.

Fix round 2: the sequence range alone cannot tell two CONCURRENT host
sessions apart - a refusal session A appends after session B opens has
a "later" sequence number than B's own boundary, and got counted into
B, not A. `record_refusal` (`godmode_session_hook.py`) now tags a new
refusal with its own host session's key at write time
(`resolve_host_session`), and `session_digest` counts a tagged record by
exact match; the sequence-range rule is now only a fallback for
records with no tag at all (every refusal written before this
shipped). The interleaved-session test below writes through
`record_refusal` itself, not a hand-built record, so it exercises the
real tagging path.

Fix round 3 (Critical): round 2's `resolve_host_session` MINTED a new
`session`-kind record on a session's first refusal whenever no tagged
boundary existed yet - which was every real session, since
`cmd_session_open` never actually recorded `host_session_id` on the
boundary it opens. That minted record became `latest_session()` for the
WHOLE chronicle - the "current session" every DEFAULT caller resolves
to (`status remaining --digest` with no `--session`, `_session()` claim
scoping, handover, `godmode_report.py`) - so a session's first refusal
could silently steal "current session" identity from another session
genuinely open at the same time. `resolve_host_session` is now
read-only (never mints); `cmd_session_open` now records
`host_session_id` when given one, so a session opened through it
resolves read-only from then on.
`test_default_digest_path_is_not_corrupted_by_concurrent_refusals`
below opens both sessions through `cmd_session_open` itself (not
`open_session` directly) and reads the DEFAULT digest path via
`latest_session()`, with no explicit `--session` / session key anywhere
in the test - the exact path round 2's own interleaved test did not
exercise.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT, PLUGIN_ROOT / "hooks"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import (  # noqa: E402
    latest_session, open_session, resolve_host_session)
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import (  # noqa: E402
    Runtime, cmd_session_open, session_digest)
from godmode_session_hook import record_refusal  # noqa: E402


@contextmanager
def _runtime():
    with tempfile.TemporaryDirectory(prefix="godmode-gate-digest-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            anchor = resolve_anchor(root)
            archive = Chronicle(anchor)
            archive.initialize()
            yield Runtime(anchor=anchor, archive=archive)


def _refuse(archive: Chronicle, *, observed: bool = False,
            would_have: str | None = None) -> None:
    """Write a `refusal` record shaped exactly like the hook's own
    `archive.append("refusal", ...)` calls (`godmode_session_hook.py`)
    - no `session` field anywhere in `data`."""
    data = {
        "operation": "rm -rf /",
        "operation_truncated": False,
        "tool": "bash",
        "tier": "R5",
        "category": "destructive",
    }
    if observed:
        data["observed"] = True
        data["would_have"] = would_have
    archive.append("refusal", "destructive", data, evidence=[])


class GateDigestCountTests(unittest.TestCase):
    def test_per_session_counts_are_exact_past_the_old_500_cap(self) -> None:
        with _runtime() as runtime:
            archive = runtime.archive
            session_a = open_session(archive, "session-a")
            # Session A: 550 plain denials, 20 would-ask, 10 would-deny -
            # 580 refusals for A alone, already past the old 500 cap -
            # written with no session tag, the way the hook writes them.
            for _ in range(550):
                _refuse(archive)
            for _ in range(20):
                _refuse(archive, observed=True, would_have="ask")
            for _ in range(10):
                _refuse(archive, observed=True, would_have="deny")

            session_b = open_session(archive, "session-b")
            # Session B: 15 plain denials, 5 would-ask - 600 refusals total
            # across the two sessions, all still untagged.
            for _ in range(15):
                _refuse(archive)
            for _ in range(5):
                _refuse(archive, observed=True, would_have="ask")

            digest_a = session_digest(runtime, session_a, None)
            digest_b = session_digest(runtime, session_b, None)

            self.assertEqual(
                digest_a["gate"],
                {"denied": 550, "would-ask": 20, "would-deny": 10},
            )
            self.assertEqual(
                digest_b["gate"],
                {"denied": 15, "would-ask": 5, "would-deny": 0},
            )

    def test_interleaved_sessions_do_not_steal_each_others_refusals(self) -> None:
        """Two host sessions that never went through `cmd_session_open` at
        all (neither ever tags a chronicle boundary) - not sequential,
        INTERLEAVED: A refuses, then B refuses, then A refuses AGAIN
        after B's first refusal. Every write goes through
        `record_refusal`, the real function both the enforcement and
        observe-mode paths in `godmode_session_hook.py` call - never a
        hand-built record carrying the digest's own key. Since round 3,
        neither resolves to a chronicle `S-<hash>` key at all (no
        boundary was ever opened for either) - each falls back to its
        own distinct `host:<id>` tag instead, which is exactly what
        keeps them apart here; `test_default_digest_path_is_not_
        corrupted_by_concurrent_refusals` below covers the
        `cmd_session_open`-backed, `S-<hash>`-keyed case instead."""
        with _runtime() as runtime:
            archive = runtime.archive
            submitted_a = {"session_id": "host-session-aaa"}
            submitted_b = {"session_id": "host-session-bbb"}

            def _write(submitted: dict) -> None:
                record_refusal(
                    archive, submitted, "destructive",
                    {"operation": "rm -rf /", "operation_truncated": False,
                     "tool": "bash", "tier": "R5", "category": "destructive"},
                )

            _write(submitted_a)  # A's 1st refusal, no boundary was ever opened
            _write(submitted_b)  # B's 1st refusal, likewise
            _write(submitted_a)  # A's 2nd refusal - after B's first write

            session_a = resolve_host_session(archive, "host-session-aaa")
            session_b = resolve_host_session(archive, "host-session-bbb")
            self.assertNotEqual(session_a, session_b)
            # Round 3: no boundary was ever opened for either, so neither
            # resolves to a minted session record any more.
            self.assertEqual(session_a, "host:host-session-aaa")
            self.assertEqual(session_b, "host:host-session-bbb")
            self.assertEqual(
                [r for r in archive.read_events() if r["kind"] == "session"], [],
                "a refusal must never mint a session-kind record")

            digest_a = session_digest(runtime, session_a, None)
            digest_b = session_digest(runtime, session_b, None)

            # A's sequence-range fallback would end at B's boundary and
            # miss A's 3rd write entirely if tagging did not work; a
            # sequence-range-only scoping would instead count that 3rd
            # write into B (it is "later" than B's own boundary). Exact
            # tag counts each one where it actually belongs.
            self.assertEqual(digest_a["gate"], {"denied": 2, "would-ask": 0, "would-deny": 0})
            self.assertEqual(digest_b["gate"], {"denied": 1, "would-ask": 0, "would-deny": 0})

    def test_default_digest_path_is_not_corrupted_by_concurrent_refusals(self) -> None:
        """Critical, fix round 3. Two sessions opened for real, through
        `cmd_session_open` (the actual CLI command, not `open_session`
        directly) - session A, then session B, each with its own host
        session id. `latest_session()` - the "current session" every
        DEFAULT caller resolves to with no explicit `--session`
        (`status remaining --digest`, `_session()` claim scoping,
        handover, `godmode_report.py`) - is B's key right after both
        real opens, exactly as it should be: B opened last.

        Round 2's `resolve_host_session` minted a fresh `session`-kind
        record on a session's first refusal whenever `cmd_session_open`
        had not tagged the boundary with `host_session_id` - which was
        EVERY session, because `cmd_session_open` never passed it
        through at all. That minted record became the new
        `latest_session()` for the whole chronicle, silently reassigning
        "current session" away from B to whichever session happened to
        refuse a command next - even though B's own session was still
        genuinely open. This test resolves the digest's session via
        `latest_session()` itself, never an explicit key, so it actually
        exercises the path round 2's interleaved test bypassed."""
        with _runtime() as runtime:
            archive = runtime.archive

            def _open(label: str, host_session_id: str) -> str:
                args = argparse.Namespace(label=label, transcript=None,
                                          host_session_id=host_session_id)
                return cmd_session_open(args, runtime).payload["session"]

            session_a = _open("session-a", "host-aaa")
            session_b = _open("session-b", "host-bbb")
            baseline_latest = latest_session(archive)
            self.assertEqual(baseline_latest, session_b)

            submitted_a = {"session_id": "host-aaa"}
            submitted_b = {"session_id": "host-bbb"}

            def _write(submitted: dict) -> None:
                record_refusal(
                    archive, submitted, "destructive",
                    {"operation": "rm -rf /", "operation_truncated": False,
                     "tool": "bash", "tier": "R5", "category": "destructive"},
                )

            _write(submitted_a)  # A refuses first
            _write(submitted_b)  # B refuses
            _write(submitted_a)  # A refuses again, after B's own refusal

            session_records = [r for r in archive.read_events() if r["kind"] == "session"]
            self.assertEqual(len(session_records), 2,
                             "a refusal must never mint a session-kind record")
            self.assertEqual(latest_session(archive), baseline_latest,
                             "latest_session() must be unchanged by refusals")

            # The DEFAULT digest path: exactly what `cmd_remaining`
            # resolves with no --session flag
            # (`args.session or latest_session(runtime.archive)`).
            default_digest = session_digest(runtime, latest_session(archive), None)
            self.assertEqual(default_digest["session"], session_b)
            self.assertEqual(default_digest["gate"],
                             {"denied": 1, "would-ask": 0, "would-deny": 0})

            # Each session's own count is still exact when queried by its
            # own (real, S-<hash>) key.
            digest_a = session_digest(runtime, session_a, None)
            digest_b = session_digest(runtime, session_b, None)
            self.assertEqual(digest_a["gate"], {"denied": 2, "would-ask": 0, "would-deny": 0})
            self.assertEqual(digest_b["gate"], {"denied": 1, "would-ask": 0, "would-deny": 0})

    def test_latest_session_with_no_session_marker_counts_everything(self) -> None:
        """No `session`-kind record has ever been written (e.g. a fresh
        archive queried before any `open_session` call) - there is no
        boundary to scope by, so every untagged refusal counts, matching
        the pre-boundary behavior `godmode_contribution._session_records`
        already relies on for other untagged record kinds."""
        with _runtime() as runtime:
            archive = runtime.archive
            for _ in range(3):
                _refuse(archive)
            digest = session_digest(runtime, None, None)
            self.assertEqual(digest["gate"], {"denied": 3, "would-ask": 0, "would-deny": 0})


if __name__ == "__main__":
    unittest.main()
