"""G-7: `status remaining --digest`'s gate counts must reflect THIS
session's refusals exactly - no artificial 500-record cap, and no
filter that can never match a real refusal record
(`godmode_console.session_digest`).

Fix round 1: a `refusal` record carries no `session` field at all -
`godmode_session_hook.py` writes it mid-tool-call, with no notion of the
chronicle's own `S-<hash>` session key - so these tests build refusal
records the same shape the hook writes (no `session` key in `data`),
and scope "this session" by the same sequence-range convention
`godmode_contribution._session_records` already uses for other untagged
record kinds: a `session`-kind boundary record via `open_session`.
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
for entry in (PLUGIN_ROOT / "scripts", PLUGIN_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from godmode_runtime.godmode_anchor import resolve_anchor  # noqa: E402
from godmode_runtime.godmode_attest import open_session  # noqa: E402
from godmode_runtime.godmode_chronicle import Chronicle  # noqa: E402
from godmode_runtime.godmode_console import Runtime, session_digest  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
