"""G-7: `status remaining --digest`'s gate counts must reflect THIS
session's refusals exactly - no artificial 500-record cap, and no
filter that can never match a real refusal record
(`godmode_console.session_digest`).

Fix round 1: a `refusal` record carries no `session` field at all -
`godmode_session_hook.py` writes it mid-tool-call, with no notion of the
chronicle's own `S-<hash>` session key - so an exact-match filter on
that field matched zero real refusals and counted 0 forever. Scoped
"this session" instead by the same sequence-range convention
`godmode_contribution._session_records` already uses for other untagged
record kinds: a `session`-kind boundary record via `open_session`.

Fix rounds 2-3 (withdrawn in round 4): tried tagging each refusal with
its own host session's chronicle key at write time
(`record_refusal` + `godmode_attest.resolve_host_session`), to keep two
CONCURRENT host sessions on one checkout from stealing each other's
refusals. Withdrawn because no hook ever opens a chronicle session with
a host session id - only the CLI's `session open --host-session-id` and
tests did - so on a live host every refusal would resolve to a
`host:<id>` tag that can never match a real session's `S-<hash>` key:
the per-session count would read 0 after release, on every real
deployment. `session_digest` is back to round 1's rule only - sequence
position decides membership - which is exact for sessions that do not
overlap in time; see this fix's changelog fragment for the concurrent-
session limit that remains.
"""

from __future__ import annotations

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
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, session_digest  # noqa: E402
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

    def test_recording_a_refusal_never_creates_a_session_record(self) -> None:
        """G-7 fix round 4: `record_refusal` (the real function both the
        enforcement and observe-mode write sites call) must never mint a
        `session`-kind record as a side effect of writing a refusal - the
        failure mode round 2/3's session-tagging attempt introduced and
        round 4 withdrew. A refusal record also carries no `session` key
        at all any more, matching round 0/1's shape exactly."""
        with _runtime() as runtime:
            archive = runtime.archive
            record = record_refusal(
                archive, {"session_id": "host-session-aaa"}, "destructive",
                {"operation": "rm -rf /", "operation_truncated": False,
                 "tool": "bash", "tier": "R5", "category": "destructive"},
            )
            self.assertNotIn("session", record["data"])
            self.assertEqual(
                [r for r in archive.read_events() if r["kind"] == "session"], [],
                "a refusal must never mint a session-kind record")


if __name__ == "__main__":
    unittest.main()
