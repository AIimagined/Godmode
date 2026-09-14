"""G-7: `status remaining --digest`'s gate counts must reflect THIS
session's refusals exactly - no artificial 500-record cap, and no
filter tautology that folds every session in the archive together
(`godmode_console.session_digest`).
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


def _refuse(archive: Chronicle, session: str, *, observed: bool = False,
            would_have: str | None = None) -> None:
    data = {
        "operation": "rm -rf /",
        "tool": "bash",
        "tier": "R5",
        "category": "destructive",
        "session": session,
    }
    if observed:
        data["observed"] = True
        data["would_have"] = would_have
    archive.append("refusal", "destructive", data, evidence=[])


class GateDigestCountTests(unittest.TestCase):
    def test_per_session_counts_are_exact_past_the_old_500_cap(self) -> None:
        with _runtime() as runtime:
            archive = runtime.archive
            # Session A: 550 plain denials, 20 would-ask, 10 would-deny -
            # 580 refusals for A alone, already past the old 500 cap.
            for _ in range(550):
                _refuse(archive, "A")
            for _ in range(20):
                _refuse(archive, "A", observed=True, would_have="ask")
            for _ in range(10):
                _refuse(archive, "A", observed=True, would_have="deny")
            # Session B: 15 plain denials, 5 would-ask - 600 refusals total
            # across the two sessions.
            for _ in range(15):
                _refuse(archive, "B")
            for _ in range(5):
                _refuse(archive, "B", observed=True, would_have="ask")

            digest_a = session_digest(runtime, "A", None)
            digest_b = session_digest(runtime, "B", None)

            self.assertEqual(
                digest_a["gate"],
                {"denied": 550, "would-ask": 20, "would-deny": 10},
            )
            self.assertEqual(
                digest_b["gate"],
                {"denied": 15, "would-ask": 5, "would-deny": 0},
            )


if __name__ == "__main__":
    unittest.main()
