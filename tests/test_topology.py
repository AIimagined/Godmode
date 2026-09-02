"""Trace topology: the archive's own record-kind transitions as a map.

Split the archive into sessions, walk each session's record-kind
sequence as bigram transitions, and mark each transition with how
often it appears in FAILURE-shaped sessions (one containing an
incident or a failed resolution) versus clean ones. The report names
the transitions whose failure share is high enough to be a warning
sign - counts only, no model, and an archive without enough sessions
says so honestly.
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
from godmode_runtime.godmode_topology import trace_topology  # noqa: E402


@contextmanager
def _archive():
    with tempfile.TemporaryDirectory(prefix="godmode-topo-") as temporary:
        base = Path(temporary)
        root = base / "project"
        root.mkdir()
        state = base / "state"
        with mock.patch.dict(os.environ, {"GODMODE_STATE_HOME": str(state)},
                             clear=False):
            archive = Chronicle(resolve_anchor(root))
            archive.initialize()
            yield archive


def _session(archive, kinds, failing=False):
    archive.append("session", "session open", {"host": "test"})
    for kind in kinds:
        if kind == "incident":
            archive.append("incident", "something broke",
                           {"failure_class": "environment-failure"})
        elif kind == "lesson":
            archive.append("lesson", "a lesson", {"value": "v"})
        elif kind == "action":
            archive.append("action", "an action", {})
        elif kind == "checkpoint":
            archive.append("checkpoint", "a checkpoint", {"status": "progress"})
    if failing and "incident" not in kinds:
        archive.append("incident", "late failure",
                       {"failure_class": "environment-failure"})


class TopologyTests(unittest.TestCase):
    def test_failure_associated_transitions_are_named(self) -> None:
        with _archive() as archive:
            # Clean sessions go action -> checkpoint; failing ones go
            # action -> action -> incident: the doubled action is the
            # failure-shaped transition.
            for _ in range(3):
                _session(archive, ["action", "checkpoint"])
            for _ in range(3):
                _session(archive, ["action", "action", "incident"])
            report = trace_topology(archive)
            self.assertEqual(report["sessions"], 6)
            warnings = {w["transition"] for w in report["warnings"]}
            self.assertIn("action->action", warnings)
            self.assertNotIn("action->checkpoint", warnings)

    def test_too_few_sessions_is_honest(self) -> None:
        with _archive() as archive:
            _session(archive, ["action"])
            report = trace_topology(archive)
            self.assertEqual(report["verdict"], "insufficient-sessions")

    def test_deterministic(self) -> None:
        with _archive() as archive:
            for _ in range(4):
                _session(archive, ["action", "checkpoint"])
            self.assertEqual(trace_topology(archive), trace_topology(archive))


if __name__ == "__main__":
    unittest.main()
